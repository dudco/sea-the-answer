"""Question modifiers change actual reference selection without claiming entry approval."""
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api import navigation_query as query, main
from api.navigation_intent import parse_conditions, select_results
from scripts.prepare_helsinki_references import helsinki_berths
from test_navigation_expansion import expanded_data, table, HEL
from test_navigation_query import setup
from test_workflow_skills import database
from rag_postgres_support import login
from test_navigation_references import IMO
from tools.navigation_references import NavigationCatalog


@pytest.fixture
def multiple(setup):
    ctx, loader, calculator = setup
    data = expanded_data()
    data['ports'][1]['berths'] = helsinki_berths(table('LHB', '8m') + table('LHC', '8.9m') +
        table('LHD', '10.8m') + table('EPL', '5.3m') + table('EMA', 'unknown'), HEL)
    loader.return_value = NavigationCatalog.model_validate(data), 'b'*64
    ctx.body['question'] = '우리 배가 헬싱키에 입항 가능해?'
    return ctx, loader, calculator


@pytest.mark.parametrize('question', ['우리 배가 이용할 수 있는 항구는 어디야?', '우리 배를 받아줄 수 있는 항구는 어디야?',
    'Which ports can our vessel use?', '타이탄이 이용할 수 있는 항구는 어디야?'])
def test_paraphrases_are_routed_without_unknown_ship_fallback(setup, question):
    ctx, loader, calculator = setup; ctx.body['question'] = question
    reply = query.try_answer(ctx)
    assert reply['task'] == 'navigation'
    assert reply['navigation']['status'] == ('needs_ship' if '타이탄' in question else 'reference_only')


@pytest.mark.parametrize(('condition', 'expected'), [
    ('흘수 제한이 8m 이상인 곳만', ['LHB', 'LHC', 'LHD']),
    ('흘수 제한이 8m 초과인 곳만', ['LHC', 'LHD']),
    ('흘수 제한이 8m 이하인 곳만', ['LHB', 'EPL']),
    ('흘수 제한이 8m 미만인 곳만', ['EPL']),
    ('흘수 제한이 8m 동일인 곳만', ['LHB']),
    ('흘수 제한이 8,9미터 이상인 곳만', ['LHC', 'LHD']),
    ('흘수 한계가 큰 순서대로', ['LHD', 'LHC', 'LHB', 'EPL', 'EMA']),
    ('흘수 제한이 작은 순서대로', ['EPL', 'LHB', 'LHC', 'LHD', 'EMA']),
    ('흘수 제한이 8m 이상이고 흘수 한계가 큰 순서대로', ['LHD', 'LHC', 'LHB']),
    ('흘수 제한이 20m 이상인 곳만', []),
])
def test_numeric_limits_filter_and_order_actual_berths(multiple, condition, expected):
    ctx, loader, calculator = multiple
    ctx.body['question'] = '우리 배가 헬싱키에 입항 가능한 선석 중 ' + condition + ' 알려줘'
    before = loader.return_value[0].model_dump()
    nav = query.try_answer(ctx)['navigation']
    assert [b['berth_id'].split(':BERTH:')[1] for b in nav['results'][0]['berths']] == expected
    assert nav['compared_berth_count'] == 5 and nav['matched_berth_count'] == len(expected)
    assert nav['excluded_unknown_count'] == (1 if nav['query']['filters'] else 0)
    assert nav['ports'][0]['available_berth_count'] == 5
    assert nav['status'] == ('reference_only' if expected else 'no_reference_matches')
    assert nav['admission'] == 'not_assessed' and loader.return_value[0].model_dump() == before


@pytest.mark.parametrize(('condition', 'status'), [
    ('입항 불가능한 선석만', 'needs_reference_scope'),
    ('흘수 제한이 8ft 이상인 곳만', 'unsupported_condition'),
    ('흘수 제한이 8m 이상 또는 5m 이하인 곳만', 'unsupported_condition'),
    ('흘수 제한이 8m', 'unsupported_condition'),
    ('흘수 제한이 8m 이상인 곳을 제외하고', 'unsupported_condition'),
    ('수심이 깊은 순서대로', 'unsupported_condition'),
])
def test_unsupported_conditions_do_not_return_the_default_list(multiple, condition, status):
    ctx, loader, calculator = multiple
    ctx.body['question'] = '우리 배가 헬싱키에 입항 가능한 선석 중 ' + condition + ' 알려줘'
    nav = query.try_answer(ctx)['navigation']
    assert nav['status'] == status and nav['results'] == []
    calculator.assert_not_called()


@pytest.mark.parametrize('state', ['published_reference_exceeded', 'insufficient_data', 'partial_reference_check'])
def test_public_status_filter_is_not_an_entry_decision(multiple, state):
    ctx, loader, calculator = multiple
    from api.navigation_intent import STATES
    ctx.body['question'] = f'우리 배가 헬싱키에 입항 가능한 선석 중 {STATES[state][1]} 알려줘'
    nav = query.try_answer(ctx)['navigation']
    assert nav['query']['status'] == state
    assert all(b['status'] == state for b in nav['results'][0]['berths'])
    assert nav['admission'] == 'not_assessed'


def parent_context(ctx, monkeypatch):
    parent = query.try_answer(ctx)
    monkeypatch.setattr(ctx.db, 'one', lambda sql, params: {'response': deepcopy(parent)}
        if params == (parent['id'], ctx.user['id']) else None, raising=False)
    ctx.body['context']['previousQueryId'] = parent['id']
    return parent


def test_followup_uses_explicit_owned_parent_and_requeries_current_sources(multiple, monkeypatch):
    ctx, loader, calculator = multiple
    ctx.body['question'] = '우리 배가 헬싱키 LHD 선석에 입항 가능해?'
    parent = parent_context(ctx, monkeypatch)
    ctx.body['question'] = '그럼 예테보리는?'
    nav = query.try_answer(ctx)['navigation']
    assert nav['previous_query_id'] == parent['id']
    assert calculator.call_args.kwargs['port_ids'] == ['WPI:24020']
    assert calculator.call_args.kwargs['berth_id'] is None
    assert calculator.call_count == 2 and loader.call_count == 2
    assert nav['context'] == parent['navigation']['context']


def test_filter_carries_only_for_followup_and_current_values_are_used(multiple, monkeypatch):
    ctx, loader, calculator = multiple
    ctx.body['question'] = '우리 배가 헬싱키에 입항 가능한 선석 중 흘수 제한이 8m 이상인 곳만 알려줘'
    parent = parent_context(ctx, monkeypatch)
    data = expanded_data()
    data['ports'][1]['berths'] = helsinki_berths(table('LHD', '7m'), HEL)
    loader.return_value = NavigationCatalog.model_validate(data), 'c'*64
    ctx.body['question'] = '그럼 헬싱키는?'
    nav = query.try_answer(ctx)['navigation']
    assert nav['query']['filters'] == parent['navigation']['query']['filters']
    assert nav['status'] == 'no_reference_matches' and nav['compared_berth_count'] == 1
    ctx.body['question'] = '우리 배가 헬싱키에 입항 가능해?'
    nav = query.try_answer(ctx)['navigation']
    assert nav['query']['filters'] == [] and nav['matched_berth_count'] == 1


def test_condition_only_followup_preserves_the_previous_port(multiple, monkeypatch):
    ctx, loader, calculator = multiple; parent_context(ctx, monkeypatch)
    ctx.body['question'] = '그럼 흘수 제한이 8m 이상인 선석만 알려줘'
    nav = query.try_answer(ctx)['navigation']
    assert calculator.call_args.kwargs['port_ids'] == [HEL]
    assert nav['matched_berth_count'] == 3 and nav['previous_query_id']


def test_english_public_limit_filter_does_not_become_an_unknown_port(multiple):
    ctx, loader, calculator = multiple
    ctx.body['question'] = 'Which berths can our ship enter with draft limit >= 8m?'
    nav = query.try_answer(ctx)['navigation']
    assert nav['query']['filters'] == [{'kind':'draught', 'op':'>=', 'value_m':'8'}]
    assert nav['matched_berth_count'] == 3 and nav['admission'] == 'not_assessed'


@pytest.mark.parametrize('change', ['missing', 'malformed', 'foreign', 'different_ship', 'version', 'mapping', 'not_navigation'])
def test_unverified_previous_answers_never_leak_or_supply_context(multiple, monkeypatch, change):
    ctx, loader, calculator = multiple
    parent = parent_context(ctx, monkeypatch)
    ctx.body['question'] = '그럼 헬싱키는?'
    calculator.reset_mock()
    if change == 'missing': ctx.body['context'].pop('previousQueryId')
    if change == 'malformed': ctx.body['context']['previousQueryId'] = "' OR 1=1 --"
    if change == 'foreign': ctx.body['context']['previousQueryId'] = str(uuid4())
    if change == 'different_ship': ctx.body['context']['ship'] = 'ship-2'
    if change == 'version': ctx.db.rows[0]['version'] += 1
    if change == 'not_navigation': parent['task'] = 'documents'
    if change == 'mapping': parent['navigation']['context']['vessel_id'] = 'REAL:IMO:9074729'
    nav = query.try_answer(ctx)['navigation']
    assert nav['status'] == 'needs_previous_query' and nav['results'] == []
    if change != 'mapping': calculator.assert_not_called()


@pytest.mark.parametrize('question', ['그럼 소화기는?', '그럼 헬싱키 입항 절차는?', '문서만 사용해서 헬싱키 입항 가능한지 알려줘'])
def test_prior_context_never_intercepts_document_questions(multiple, monkeypatch, question):
    ctx, loader, calculator = multiple; parent_context(ctx, monkeypatch)
    ctx.body['question'] = question
    assert query.try_answer(ctx) is None


def test_filtering_unknowns_and_sorting_never_mutate_source_results():
    rows = [{'berths':[{'status':'insufficient_data', 'checks':[{'kind':'beam', 'berth_listed_m':None}]}]}]
    before = deepcopy(rows)
    conditions, issue = parse_conditions('선석 폭 제한이 30m 이상인 곳만')
    assert issue is None
    selected, counts = select_results(rows, conditions)
    assert selected[0]['berths'] == [] and counts['excluded_unknown_count'] == 1 and rows == before


def test_actual_postgres_followup_requires_the_parent_owner(database, setup):
    ctx, loader, calculator = setup
    actor = database.one("SELECT * FROM users WHERE username='admin'")
    database.change(actor, 'ship.save', {'id':'ship-1', 'name':'검증 선박', 'imo':IMO,
        'dwt':1000, 'type':'Bulk carrier', 'version':0})
    crew = TestClient(main.app, base_url='http://localhost:5173'); headers = login(crew, 'crew')
    parent = crew.post('/api/ask', headers=headers, json=ctx.body).json()
    body = {'question':'그럼 헬싱키는?', 'context':{'ship':'ship-1', 'previousQueryId':parent['id']}}
    other = TestClient(main.app, base_url='http://localhost:5173'); other_headers = login(other, 'admin')
    foreign = other.post('/api/ask', headers=other_headers, json=body)
    assert foreign.status_code == 200 and foreign.json()['navigation']['status'] == 'needs_previous_query'
    assert foreign.json()['navigation']['results'] == []
    own = crew.post('/api/ask', headers=headers, json=body)
    assert own.status_code == 200 and own.json()['navigation']['status'] == 'reference_only'
    assert own.json()['navigation']['previous_query_id'] == parent['id']
