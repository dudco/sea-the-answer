"""Tool selection evaluation CLI; model replies are mock HTTP fixtures, never a real LLM."""
import json

import httpx

from api import config
from scripts import evaluate_tool_selection as evaluation

SETTINGS = config.LLMSettings('http://localhost:11434/v1', 'mock-model', '', 'json_schema')


class Client:
    def __init__(self, replies):
        self.replies = replies
    def post(self, url, json=None, **_):
        question = __import__('json').loads(json['messages'][-1]['content'])['question']
        name, args = self.replies.get(question, (None, None))
        message = {'role': 'assistant', 'content': '문서' if name is None else None}
        if name:
            message['tool_calls'] = [{'type': 'function', 'function': {'name': name, 'arguments': __import__('json').dumps(args, ensure_ascii=False)}}]
        return httpx.Response(200, json={'choices': [{'finish_reason': 'tool_calls' if name else 'stop', 'message': message}]},
                              request=httpx.Request('POST', url))


def test_checked_in_cases_load_and_reference_registered_tools():
    from api import tool_registry
    cases = evaluation.load_cases()
    assert len(cases) >= 20
    assert all(set(c['expected']['tools']) <= set(tool_registry.TOOLS) for c in cases)


def test_scores_tool_and_argument_subsets_separately():
    cases = [c for c in evaluation.load_cases() if c['id'] in ('definition-cii', 'status-mrv', 'ops-last-month')]
    client = Client({'MRV 자료 있어?': ('get_dataset_status', {'datasets': ['mrv', 'ais']}),
                     '해답호 지난달 연료 사용량 합계 알려줘': ('summarize_operations', {'ship_mentions': ['별빛호'], 'period_text': '지난달'})})
    result = evaluation.evaluate(cases, settings=SETTINGS, client=client)
    rows = {r['id']: r for r in result['rows']}
    assert rows['definition-cii']['tool_match'] and rows['definition-cii']['argument_match']
    assert rows['status-mrv']['argument_match']
    assert rows['ops-last-month']['tool_match'] and not rows['ops-last-month']['argument_match']
    assert (result['tool_match'], result['argument_match'], result['errors']) == (3, 2, 0)


def test_cli_refuses_without_a_model(monkeypatch, capsys):
    monkeypatch.setattr(evaluation.config, 'llm_settings', lambda: None)
    assert evaluation.main([]) == 2
