"""Model tool selection: registry schemas, response validation and validated dispatch.

Model replies here are fixtures. They test server validation, not model accuracy.
"""
import json
from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest

from api import config, question_router as router, tool_planner as planner, tool_registry as registry
from api.errors import ApiError
from test_question_workflows import DB

SETTINGS = config.LLMSettings('http://model.test/v1', 'qwen-test', '', 'json_schema')


def reply(*calls, content=None, finish='tool_calls'):
    message = {'role': 'assistant', 'content': content}
    if calls:
        message['tool_calls'] = [{'id': f'c{i}', 'type': 'function',
            'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}} for i, (name, args) in enumerate(calls)]
    return {'choices': [{'finish_reason': finish, 'message': message}]}


class Client:
    def __init__(self, payload):
        self.payload, self.bodies = payload, []
    def post(self, url, json=None, **_):
        self.bodies.append(json)
        return httpx.Response(200, json=self.payload, request=httpx.Request('POST', url))


# Registry ---------------------------------------------------------------

def test_registry_lists_only_read_only_tools_with_closed_inline_schemas():
    tools = registry.model_tools()
    names = [t['function']['name'] for t in tools]
    assert names == list(registry.TOOLS)
    assert {'get_dataset_status', 'summarize_operations', 'calculate_mrv_reference', 'compare_port_conditions',
            'request_clarification', 'decline_request'} <= set(names)
    assert not {'query_maritime_data', 'save_report', 'import_operations'} & set(names)
    for tool in tools:
        schema = tool['function']['parameters']
        assert schema['type'] == 'object' and schema['additionalProperties'] is False
        assert '$ref' not in json.dumps(schema) and '$defs' not in schema


def test_catalog_describes_every_tool_and_its_kind():
    catalog = registry.catalog()
    assert [t['name'] for t in catalog] == list(registry.TOOLS)
    assert {t['kind'] for t in catalog} == {'data', 'control'}
    assert all(t['description'] and t['parameters']['type'] == 'object' for t in catalog)


def test_arguments_reject_extra_fields_and_out_of_range_values():
    with pytest.raises(registry.ToolCallError):
        registry.parse_call('get_dataset_status', '{"datasets":["mrv"],"sql":"select 1"}')
    with pytest.raises(registry.ToolCallError):
        registry.parse_call('get_dataset_status', '{"datasets":["weather"]}')
    with pytest.raises(registry.ToolCallError):
        registry.parse_call('summarize_operations', '{"ship_mentions":["a","b","c"]}')
    with pytest.raises(registry.ToolCallError):
        registry.parse_call('delete_everything', '{}')
    with pytest.raises(registry.ToolCallError):
        registry.parse_call('get_dataset_status', 'not json')
    tool, args = registry.parse_call('compare_port_conditions',
        '{"port_mentions":["부산"],"filters":[{"dimension":"draught","op":">=","value_m":12}]}')
    assert tool.kind == 'data' and args.filters[0].value_m == 12


# Planner ----------------------------------------------------------------

def plan(payload, **options):
    client = Client(payload)
    result = planner.plan('MRV 자료 있어?', today='2026-11-12', settings=SETTINGS, client=client, **options)
    return result, client.bodies[0]


def test_planner_sends_tools_question_today_and_previous_summary_but_no_documents():
    calls, body = plan(reply(('get_dataset_status', {'datasets': ['mrv']})), summary={'task': 'data_status'})
    assert [c.tool.name for c in calls] == ['get_dataset_status'] and calls[0].args.datasets == ['mrv']
    assert body['tools'] == registry.model_tools() and body['temperature'] == 0
    user = json.loads(body['messages'][-1]['content'])
    assert user == {'question': 'MRV 자료 있어?', 'today': '2026-11-12', 'previous': {'task': 'data_status'}}


def test_planner_without_tool_calls_means_documents_only():
    calls, _ = plan(reply(content='문서 검색만 필요합니다.', finish='stop'))
    assert calls == []


def test_planner_reads_a_tool_call_wrapped_in_text():
    text = '<tool_call>{"name":"get_dataset_status","arguments":{"datasets":["ais"]}}</tool_call>'
    calls, _ = plan(reply(content=text, finish='stop'))
    assert calls[0].tool.name == 'get_dataset_status' and calls[0].args.datasets == ['ais']


@pytest.mark.parametrize('payload', [
    reply(('unknown_tool', {})),
    reply(('get_dataset_status', {'datasets': ['mrv'], 'vessel_id': 'REAL:IMO:1234567'})),
    reply(*[('get_dataset_status', {'datasets': ['mrv']})] * 4),
    {'choices': [{'finish_reason': 'length', 'message': {'role': 'assistant', 'content': ''}}]},
    {'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': None, 'refusal': 'no'}}]},
])
def test_planner_rejects_invalid_model_replies(payload):
    with pytest.raises(planner.PlanError):
        plan(payload)


def test_planner_requires_configured_model():
    with pytest.raises(planner.PlanError) as error:
        planner.plan('질문', today='2026-11-12', settings=None)
    assert error.value.code == 'MODEL_NOT_CONFIGURED'


# Router -----------------------------------------------------------------

EVIDENCE = [{'id': 'chunk-1', 'document_id': 'doc-a', 'title': 'MRV 규정', 'text': 'MRV는 보고 제도이다.'}]


class Store(DB):
    def __init__(self):
        super().__init__()
        self.document_calls = []
        self.searches = []
    def search(self, user, question, kind='all', document_ids=None):
        self.searches.append(question)
        return deepcopy(EVIDENCE)
    def answer(self, user, body, *, evidence=None):
        self.document_calls.append((deepcopy(body), evidence))
        answer = {'id': 'doc-answer', 'question': body['question'], 'task': 'documents',
                  'evidence': deepcopy(evidence or []), 'statements': []}
        self.answers['doc-answer'] = deepcopy(answer)
        self.owners['doc-answer'] = user['id']
        return answer
    def run(self, sql, args=()):
        super().run(sql, args)
        if sql.startswith('UPDATE queries SET response'):
            self.answers[args[1]] = deepcopy(args[0].obj)


def ask(question, calls, monkeypatch, *, body=None, settings=SETTINGS):
    db = Store()
    monkeypatch.setattr(router.config, 'llm_settings', lambda: settings)
    def fake_plan(q, *, today, summary=None, settings=None, client=None):
        if isinstance(calls, Exception):
            raise calls
        return [registry.Call(*registry.parse_call(name, json.dumps(args, ensure_ascii=False))) for name, args in calls]
    monkeypatch.setattr(router.tool_planner, 'plan', fake_plan)
    ctx = SimpleNamespace(db=db, user={'id': 'crew-1', 'role': 'operator'},
                          body={'question': question, 'task': 'auto', 'context': {}, **(body or {})})
    return router.answer(ctx), db


def test_model_not_configured_is_an_error_not_a_rule_fallback(monkeypatch):
    with pytest.raises(ApiError) as error:
        ask('MRV 자료 있어?', [], monkeypatch, settings=None)
    assert error.value.status == 503 and error.value.code == 'MODEL_NOT_CONFIGURED'


def test_definition_question_always_searches_and_answers_from_documents(monkeypatch):
    answer, db = ask('CII가 뭐야?', [], monkeypatch, body={'mode': 'extractive'})
    assert db.searches == ['CII가 뭐야?']
    body, evidence = db.document_calls[0]
    assert body['task'] == 'documents' and body['mode'] == 'llm' and evidence == EVIDENCE
    assert answer['routing']['method'] == 'model_tools'
    assert [c['name'] for c in answer['routing']['toolCalls']] == ['search_documents']
    assert db.answers['doc-answer']['routing'] == answer['routing']


def test_data_tool_runs_with_validated_arguments_and_keeps_related_documents(monkeypatch):
    seen = {}
    def status(ctx, datasets, *, scope_text=None):
        seen.update(datasets=datasets, scope_text=scope_text)
        return {'status': 'completed', 'dataStatus': {'datasets': [{'dataset': d} for d in datasets]}}
    monkeypatch.setattr(router.dataset_status, 'answer', status)
    answer, db = ask('엠알브이 데이터 들어와 있나?', [('get_dataset_status', {'datasets': ['mrv']})], monkeypatch)
    assert seen == {'datasets': ['mrv'], 'scope_text': ''}
    assert answer['task'] == 'data_status' and answer['relatedEvidence'] == EVIDENCE
    assert [c['name'] for c in answer['routing']['toolCalls']] == ['search_documents', 'get_dataset_status']
    assert answer['routing']['toolCalls'][1]['arguments'] == {'datasets': ['mrv'], 'ship_mentions': [], 'period_text': ''}
    assert not db.document_calls


def test_planner_failure_asks_the_user_again(monkeypatch):
    answer, _ = ask('MRV 자료 있어?', planner.PlanError('MODEL_TIMEOUT'), monkeypatch)
    assert answer['status'] == 'needs_input' and 'MODEL_ROUTING_UNAVAILABLE' in answer['warnings']
    assert answer['routing']['toolCalls'][0]['name'] == 'search_documents'


def test_more_than_one_data_tool_is_clarified_not_guessed(monkeypatch):
    answer, _ = ask('MRV와 AIS 현황, 운항 합계', [('get_dataset_status', {'datasets': ['mrv']}),
        ('summarize_operations', {'ship_mentions': ['해답호'], 'period_text': '지난달'})], monkeypatch)
    assert answer['status'] == 'needs_input' and 'MULTIPLE_TOOLS_REQUESTED' in answer['warnings']


def test_mentions_must_come_from_the_question_or_previous_summary(monkeypatch):
    answer, _ = ask('우리 배 지난달 연료 합계 알려줘',
        [('summarize_operations', {'ship_mentions': ['별빛호'], 'period_text': '지난달'})], monkeypatch)
    assert answer['status'] == 'needs_input' and 'MODEL_ARGUMENT_NOT_IN_QUESTION' in answer['warnings']


def test_operations_tool_resolves_ships_and_dates_on_the_server(monkeypatch):
    monkeypatch.setattr(router.tool_dispatch.intent, 'local_today', lambda: __import__('datetime').date(2026, 11, 12))
    answer, db = ask('해답호 2025년 1월 연료 합계',
        [('summarize_operations', {'ship_mentions': ['해답호'], 'period_text': '2025년 1월'})], monkeypatch)
    assert answer['workflow']['scope']['ships'][0]['id'] == 'a'
    assert answer['workflow']['scope']['periods'] == [{'start': '2025-01-01', 'end': '2025-01-31'}]
    assert db.calls[0]['ship'] == 'a'


def test_mrv_reference_consent_is_never_set_without_a_prior_prompt(monkeypatch):
    answer, _ = ask('해답호 2024년 탄소집약도',
        [('calculate_mrv_reference', {'ship_mentions': ['해답호'], 'period_text': '2024년', 'accept_reference': True})], monkeypatch)
    assert answer['status'] == 'needs_input' and answer['workflow']['missing'] == ['reference_ack']


def test_decline_and_clarification_are_saved_answers(monkeypatch):
    answer, _ = ask('지금 배 위치 알려줘', [('decline_request', {'reason': 'realtime_position'})], monkeypatch)
    assert answer['status'] == 'unsupported' and 'UNSUPPORTED_REQUEST' in answer['warnings']
    answer, _ = ask('그거 알려줘', [('request_clarification', {'missing': ['task']})], monkeypatch)
    assert answer['status'] == 'needs_input' and 'QUESTION_SCOPE_REQUIRED' in answer['warnings']


def test_legacy_router_is_used_only_when_configured(monkeypatch):
    monkeypatch.setenv('HAEDAP_QUESTION_ROUTER', 'legacy')
    monkeypatch.setattr(router, 'legacy_answer', lambda ctx: {'id': 'legacy'})
    answer, _ = ask('MRV 자료 있어?', [], monkeypatch)
    assert answer == {'id': 'legacy'}


def test_follow_up_passes_an_owned_summary_and_accepts_names_from_it(monkeypatch):
    db = Store()
    first = {'id': '11111111-1111-4111-8111-111111111111', 'question': '해답호 2025년 1월 연료 합계', 'task': 'workflow',
             'workflow': {'version': 'HAEDAP-QUESTION-WORKFLOW-1.0', 'missing': [],
                          'scope': {'action': 'operations_summary', 'ships': [{'id': 'a', 'name': '해답호', 'version': 1, 'imo': '7422881'}],
                                    'years': [], 'periods': [{'start': '2025-01-01', 'end': '2025-01-31'}]}}}
    db.answers[first['id']] = first
    db.owners[first['id']] = 'crew-1'
    seen = {}
    monkeypatch.setattr(router.config, 'llm_settings', lambda: SETTINGS)
    def fake_plan(q, *, today, summary=None, settings=None, client=None):
        seen['summary'] = summary
        return [registry.Call(*registry.parse_call('summarize_operations',
                '{"ship_mentions":["해답호"],"period_text":"2025년 2월"}'))]
    monkeypatch.setattr(router.tool_planner, 'plan', fake_plan)
    ctx = SimpleNamespace(db=db, user={'id': 'crew-1', 'role': 'operator'},
                          body={'question': '그럼 2025년 2월은?', 'task': 'auto', 'context': {'previousQueryId': first['id']}})
    answer = router.answer(ctx)
    assert seen['summary']['ships'] == ['해답호'] and seen['summary']['action'] == 'operations_summary'
    assert answer['workflow']['scope']['periods'] == [{'start': '2025-02-01', 'end': '2025-02-28'}]
    assert answer['workflow']['previous_query_id'] == first['id']


def test_another_users_answer_is_never_summarized(monkeypatch):
    db = Store()
    other = '22222222-2222-4222-8222-222222222222'
    db.answers[other] = {'id': other, 'question': '비밀 질문', 'task': 'documents'}
    db.owners[other] = 'someone-else'
    ctx = SimpleNamespace(db=db, user={'id': 'crew-1'}, body={'question': '그럼?', 'context': {'previousQueryId': other}})
    assert router.previous_summary(ctx) is None


def test_port_tool_becomes_explicit_conditions_for_the_existing_comparison(monkeypatch):
    seen = {}
    monkeypatch.setattr(router.tool_dispatch.navigation_query, 'try_answer',
                        lambda ctx, *, force=False, planned=None: seen.update(planned) or {'id': 'nav', 'status': 'reference_only', 'evidence': []})
    answer, _ = ask('부산항 선석 3에서 흘수 12.5m 이상인 곳만 큰 순으로',
        [('compare_port_conditions', {'port_mentions': ['부산항'], 'berth_mention': '3',
          'filters': [{'dimension': 'draught', 'op': '>=', 'value_m': 12.5}],
          'sort': {'dimension': 'draught', 'direction': 'desc'}})], monkeypatch)
    assert seen == {'ship_text': '', 'ports_text': '부산항 선석 3', 'conditions': {
        'filters': [{'kind': 'draught', 'op': '>=', 'value_m': '12.5'}],
        'sort': {'kind': 'draught', 'direction': 'desc'}, 'status': None}}
    assert answer['relatedEvidence'] == EVIDENCE


def test_tools_endpoint_lists_the_assistant_registry():
    from api.routes import system
    assert [t['name'] for t in system.tools(None)['assistantTools']] == list(registry.TOOLS)


def test_model_path_forces_model_generation_for_downstream_executors(monkeypatch):
    seen = {}
    def workflow(ctx, action, args):
        seen['mode'] = ctx.body['mode']
        return {'id': 'wf', 'status': 'completed', 'evidence': []}
    monkeypatch.setattr(router.tool_dispatch, 'workflow', workflow)
    ask('선박 안전 문서만 근거로 요약해줘', [('ask_selected_documents', {'document_mentions': ['선박 안전 문서']})],
        monkeypatch, body={'mode': 'extractive'})
    assert seen == {'mode': 'llm'}


def test_truncated_reply_reports_finish_reason_and_budget_is_configurable(monkeypatch):
    with pytest.raises(planner.PlanError) as error:
        plan({'choices': [{'finish_reason': 'length', 'message': {'role': 'assistant', 'content': '<think>...'}}]})
    assert (error.value.code, error.value.detail) == ('MODEL_INCOMPLETE_OUTPUT', 'length')
    monkeypatch.setenv('HAEDAP_PLANNER_MAX_TOKENS', '2048')
    _, body = plan(reply(content='문서', finish='stop'))
    assert body['max_tokens'] == 2048


def test_reasoning_effort_is_sent_only_when_configured(monkeypatch):
    _, body = plan(reply(content='문서', finish='stop'))
    assert 'reasoning_effort' not in body
    monkeypatch.setenv('HAEDAP_PLANNER_REASONING_EFFORT', 'none')
    _, body = plan(reply(content='문서', finish='stop'))
    assert body['reasoning_effort'] == 'none'
    monkeypatch.setenv('HAEDAP_PLANNER_REASONING_EFFORT', 'everything')
    _, body = plan(reply(content='문서', finish='stop'))
    assert 'reasoning_effort' not in body


def test_text_none_for_an_optional_argument_means_omitted():
    # Observed from qwen3.6:35b on Ollama (2026-11-12): "status_filter":"None".
    _, args = registry.parse_call('compare_port_conditions',
        '{"ship_mention":"","port_mentions":["부산항"],"berth_mention":"","filters":[],'
        '"sort":{"dimension":"length","direction":"desc"},"status_filter":"None"}')
    assert args.status_filter is None and args.sort.direction == 'desc'
    with pytest.raises(registry.ToolCallError):
        registry.parse_call('decline_request', '{"reason":"None"}')
