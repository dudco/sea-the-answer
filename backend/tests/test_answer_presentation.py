"""Requested presentations and generation budgets; model/DB IO is mocked."""

from copy import deepcopy
import json

import httpx
import pytest

from api import answer_presentation as presentation, config, llm
from api.store import answers
from api.store.answers import AnswerStore

EVIDENCE = [{"id": "chunk-1", "document_id": "doc-1", "title": "Source",
             "text": "Verified fuel limit is 0.50 percent outside the designated area."}]
STATEMENT = {"text": "The limit is 0.50 percent.", "chunkId": "chunk-1", "quote": EVIDENCE[0]["text"]}
TABLE = {"type": "table", "title": "Limits", "columns": ["Area", "Limit"],
         "rows": [{"cells": ["Outside designated area", "0.50 percent"],
                   "citations": [{"chunkId": "chunk-1", "quote": EVIDENCE[0]["text"]}]}]}
SETTINGS = config.LLMSettings("http://localhost:11434/v1", "test-model", "", "json_schema")


class Workspace(AnswerStore):
    def __init__(self, *, evidence=None, summary=None, clock=None, retrieval=0, preceding=0):
        self.evidence = deepcopy(EVIDENCE if evidence is None else evidence)
        self.summary = summary
        self.clock, self.retrieval, self.preceding = clock, retrieval, preceding

    def search(self, *_args):
        if self.clock is not None:
            self.clock["now"] += self.retrieval
        return self.evidence

    def operation_summary(self, _context):
        if self.clock is not None:
            self.clock["now"] += self.preceding
        return self.summary

    def run(self, *_args):
        pass

    def audit(self, *_args):
        pass


@pytest.fixture
def model(monkeypatch):
    clients = []
    monkeypatch.setattr(config, "llm_configured", lambda: True)
    monkeypatch.setattr(config, "llm_settings", lambda: SETTINGS)

    def install(answer, *, elapsed=None, wrap_table=True):
        calls = []

        def handler(request):
            calls.append(request)
            if elapsed:
                elapsed()
            content = {"answer": answer} if wrap_table and isinstance(answer, dict) and "table" in answer else answer
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps(content)}}]})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        clients.append(client)
        monkeypatch.setattr(llm.httpx, "post", client.post)
        return calls

    yield install
    for client in clients:
        client.close()


def answer(workspace=None, **payload):
    return (workspace or Workspace()).answer({"id": "test-user"}, {
        "question": "Show the limit in a table", "task": "documents", "language": "en", "mode": "llm", **payload})


def operations(count=1):
    return {"count": count, "rows": [{"date": f"day-{i:03}", "fuel": 2.5, "factor": 3.2,
                                     "distance": 12, "speed": 6} for i in range(count)]}


@pytest.mark.parametrize("question,expected", [
    ("규정 조건을 표로 정리해", "table"), ("show a table", "table"),
    ("연료 막대 그래프", "chart"), ("plot emissions", "chart"),
    ("절차를 그림으로 만들어", "unsupported"), ("draw a diagram", "unsupported"),
    ("발표 내용을 설명해", "text"), ("plain question", "text"),
])
def test_explicit_presentation_intent_without_incidental_table_match(question, expected):
    assert presentation.output_format(question) == expected
    assert presentation.output_format(question, "text") == "text"


def test_document_table_uses_one_model_call_with_cited_rows_and_bounded_stats(model):
    calls = model({"insufficient": False, "statements": [STATEMENT], "table": TABLE})
    result = answer()
    assert len(calls) == 1
    body = json.loads(calls[0].content)
    schema = body["response_format"]["json_schema"]["schema"]
    assert schema["type"] == "object" and schema["required"] == ["answer"]
    assert schema["additionalProperties"] is False and "anyOf" not in schema
    supported, insufficient = schema["properties"]["answer"]["anyOf"]
    assert supported["properties"]["insufficient"]["enum"] == [False]
    assert supported["properties"]["statements"]["minItems"] == 1
    assert supported["properties"]["table"]["type"] == "object"
    assert insufficient["properties"]["insufficient"]["enum"] == [True]
    assert insufficient["properties"]["statements"]["maxItems"] == 0
    assert insufficient["properties"]["table"] == {"type": "null"}
    assert all(set(branch["required"]) == {"insufficient", "statements", "table"}
               and branch["additionalProperties"] is False for branch in (supported, insufficient))
    assert '"answer":{"insufficient":false' in body["messages"][0]["content"]
    assert result["generation"] == "llm"
    assert result["presentation"]["rows"] == TABLE["rows"]
    assert result["presentation"]["source"] == "documents"
    assert result["presentation"]["totalRows"] == 1 and result["presentation"]["truncated"] is False
    assert result["generationStats"]["payloadBytes"] == len(body["messages"][1]["content"].encode("utf-8"))
    assert result["generationStats"]["modelCallAttempted"] is True
    assert set(result["timings"]) == {"retrievalMs", "generationMs", "totalMs"}
    assert all(value >= 0 for value in result["timings"].values())


@pytest.mark.parametrize("mutation", ["quote", "id", "cells", "cell_length", "number", "columns", "rows"])
def test_invalid_model_table_discards_all_model_output_and_shows_excerpts(model, mutation):
    table = deepcopy(TABLE)
    row = table["rows"][0]
    if mutation == "quote":
        row["citations"][0]["quote"] = "A quote that is absent from every source."
    elif mutation == "id":
        row["citations"][0]["chunkId"] = "not-authorized"
    elif mutation == "cells":
        row["cells"].pop()
    elif mutation == "cell_length":
        row["cells"][0] = "a" * 1001
    elif mutation == "number":
        row["cells"][0] = 0.5
    elif mutation == "columns":
        table["columns"] = ["column"] * 9
    else:
        table["rows"] = [deepcopy(row) for _ in range(51)]
    calls = model({"insufficient": False, "statements": [STATEMENT], "table": table})
    result = answer()
    assert len(calls) == 1
    assert result["generation"] == "extractive"
    assert result["generationStats"]["modelCallAttempted"] is True
    assert result["warnings"] == ["MODEL_FAILED_EXTRACTIVE_FALLBACK"]
    assert result["statements"][0]["text"] == EVIDENCE[0]["text"]
    assert result["presentation"]["rows"][0]["citations"][0]["quote"] == EVIDENCE[0]["text"]
    assert result["presentationNotice"]


def test_table_insufficiency_requires_null_table_and_preserves_empty_statements(model):
    calls = model({"insufficient": True, "statements": [], "table": None})
    result = answer()
    assert len(calls) == 1 and result["generation"] == "llm"
    assert result["statements"] == [] and "presentation" not in result
    assert result["presentationNotice"]


@pytest.mark.parametrize("invalid", [
    {"insufficient": False, "statements": [STATEMENT], "table": None},
    {"insufficient": True, "statements": [], "table": TABLE},
])
def test_server_rejects_inconsistent_table_branch_without_relaxing_schema_or_citations(model, invalid):
    calls = model(invalid)
    result = answer()
    assert len(calls) == 1 and result["generation"] == "extractive"
    assert result["warnings"] == ["MODEL_FAILED_EXTRACTIVE_FALLBACK"]
    assert result["presentation"]["title"] == "Source excerpts"


def test_server_rejects_obsolete_unwrapped_table_shape(model):
    calls = model({"insufficient": False, "statements": [STATEMENT], "table": TABLE}, wrap_table=False)
    result = answer()
    assert len(calls) == 1 and result["generation"] == "extractive"
    assert result["warnings"] == ["MODEL_FAILED_EXTRACTIVE_FALLBACK"]


def test_operations_chart_uses_actual_numbers_and_never_contacts_model(model):
    calls = model({})
    result = answer(Workspace(summary=operations()), question="Show fuel as a bar chart", task="operations",
                    context={"ship": "ship-1", "from": "2026-11-01", "to": "2026-11-03"})
    chart = result["presentation"]
    assert calls == []
    assert result["generationStats"]["modelCallAttempted"] is False
    assert chart["type"] == "chart" and chart["chartType"] == "bar"
    assert chart["source"] == "operations" and chart["unit"] == "t"
    assert chart["points"] == [{"label": "day-000", "value": 2.5}]


def test_operation_table_truncates_honestly_without_fabricated_document_citations():
    table = presentation.operation_presentation(operations(51), "table", "fuel", "en")
    assert len(table["rows"]) == 50 and table["totalRows"] == 51 and table["truncated"] is True
    assert all(row["citations"] == [] for row in table["rows"])
    chart = presentation.operation_presentation(operations(101), "chart", "emission", "en")
    assert len(chart["points"]) == 100 and chart["totalPoints"] == 101 and chart["truncated"] is True
    assert chart["points"][0]["value"] == 8.0


@pytest.mark.parametrize("kind,shown", [("table", 50), ("chart", 100)])
def test_answer_bounds_legacy_operation_rows_after_full_aggregation_and_presentation(kind, shown):
    summary = operations(250)
    summary.update(fuel=625.0, emission=2000.0, distance=3000.0, speed=6.0)
    result = answer(Workspace(summary=summary), question="Show fuel records", task="operations", outputFormat=kind,
                    context={"ship": "ship-1", "from": "2026-01-01", "to": "2026-11-03"})
    preview = result["operations"]
    assert len(preview["rows"]) == 200 and preview["rowsTruncated"] is True and preview["totalRows"] == 250
    assert preview["count"] == 250 and preview["fuel"] == 625.0 and preview["emission"] == 2000.0
    assert preview["distance"] == 3000.0 and preview["speed"] == 6.0
    assert len(summary["rows"]) == 250  # Shared summary/global API data was not mutated.
    display = result["presentation"]
    assert len(display["rows"] if kind == "table" else display["points"]) == shown
    assert display["totalRows" if kind == "table" else "totalPoints"] == 250
    assert "all selected records" in result["presentationNotice"] and "200" in result["presentationNotice"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True, "3"])
def test_invalid_operation_numbers_cannot_become_chart_points(value):
    summary = operations()
    summary["rows"][0]["fuel"] = value
    with pytest.raises(ValueError):
        presentation.operation_presentation(summary, "chart", "emission", "en")


def test_selected_ship_does_not_turn_document_comparison_into_operation_table(model):
    calls = model({"insufficient": False, "statements": [STATEMENT], "table": TABLE})
    result = answer(Workspace(summary=operations()), question="Show ship regulation limits as a table", task="auto",
                    context={"ship": "ship-1", "from": "2026-11-01", "to": "2026-11-03"})
    assert len(calls) == 1 and result["presentation"]["source"] == "documents"


def test_fuel_regulation_comparison_with_selected_ship_still_uses_document_table(model):
    calls = model({"insufficient": False, "statements": [STATEMENT], "table": TABLE})
    result = answer(Workspace(summary=operations()), question="ECA 안과 밖의 연료 황 함유량 한도를 표로 비교해줘",
                    task="auto", context={"ship": "ship-1", "from": "2026-11-01", "to": "2026-11-03"})
    assert len(calls) == 1 and result["presentation"]["source"] == "documents"


@pytest.mark.parametrize("question", ["Show official CII ratings in a chart", "소음 수치를 그래프로", "show a chart"])
def test_unsupported_chart_metric_does_not_substitute_unrelated_co2_data(model, question):
    calls = model({})
    result = answer(Workspace(summary=operations()), question=question, task="operations",
                    context={"ship": "ship-1", "from": "2026-11-01", "to": "2026-11-03"})
    assert calls == [] and "presentation" not in result
    assert "CII" in result["presentationNotice"]


def test_missing_operations_and_unsupported_figure_have_clear_notices_without_model(model):
    calls = model({})
    chart = answer(question="Show emissions in a chart", task="auto")
    figure = answer(question="Draw a diagram of this rule")
    assert calls == []
    assert "presentation" not in chart and chart["presentationNotice"]
    assert "presentation" not in figure and figure["presentationNotice"]


def test_utf8_byte_budget_keeps_whole_evidence_and_order():
    evidence = deepcopy(EVIDENCE) + [{"id": "large", "title": "Large", "text": "가" * 3000}]
    selected, stats = llm.bound_evidence("질문", evidence)
    assert selected == EVIDENCE and stats["usedEvidence"] == 1 and stats["omittedEvidence"] == 1
    assert stats["payloadBytes"] <= stats["payloadByteBudget"] == 8192
    assert evidence[1]["text"] == "가" * 3000


def test_oversized_sources_skip_model_and_keep_honest_excerpt_fallback(model):
    calls = model({})
    huge = [{**EVIDENCE[0], "text": "source words " * 1000}]
    diagnostics = {}
    with pytest.raises(llm.InputBudgetExceeded):
        llm.grounded_statements("question", huge, "en", SETTINGS, diagnostics=diagnostics)
    assert calls == [] and diagnostics["modelCallAttempted"] is False and diagnostics["usedEvidence"] == 0
    result = answer(Workspace(evidence=huge))
    assert calls == [] and result["generation"] == "extractive"
    assert result["generationStats"]["modelCallAttempted"] is False
    assert result["warnings"] == ["MODEL_INPUT_TOO_LARGE"]
    assert result["presentationNotice"] and result["presentation"]["rows"][0]["citations"][0]["quote"] in huge[0]["text"]


def test_remaining_generation_budget_includes_retrieval_and_operation_work(monkeypatch, model):
    clock = {"now": 0.0}
    monkeypatch.setattr(answers, "monotonic", lambda: clock["now"])
    calls = model({"insufficient": False, "statements": [STATEMENT]},
                  elapsed=lambda: clock.update(now=clock["now"] + 1.5))
    workspace = Workspace(summary=operations(), clock=clock, retrieval=6, preceding=2)
    result = answer(workspace, question="Explain fuel limits", task="integrated", outputFormat="text",
                    context={"ship": "ship-1", "from": "2026-11-01", "to": "2026-11-03"})
    assert len(calls) == 1 and calls[0].extensions["timeout"]["read"] == 55
    assert result["timings"] == {"retrievalMs": 6000.0, "generationMs": 1500.0, "totalMs": 9500.0}


def test_exhausted_generation_budget_skips_http(monkeypatch, model):
    clock = {"now": 0.0}
    monkeypatch.setattr(answers, "monotonic", lambda: clock["now"])
    calls = model({})
    result = answer(Workspace(clock=clock, retrieval=62.5), outputFormat="text")
    assert calls == [] and result["generation"] == "extractive"
    assert result["generationStats"]["modelCallAttempted"] is False
    assert result["warnings"] == ["MODEL_TIME_BUDGET_EXHAUSTED"]
    assert result["timings"]["generationMs"] == 0 and result["presentationNotice"]


def test_plain_text_wrapper_and_explicit_text_keep_original_contract(model):
    calls = model({"insufficient": False, "statements": [STATEMENT]})
    assert llm.grounded_statements("question", EVIDENCE, "en", SETTINGS) == [STATEMENT]
    result = answer(outputFormat="text")
    assert len(calls) == 2 and result["statements"] == [STATEMENT] and "presentation" not in result
    assert set(json.loads(calls[0].content)["response_format"]["json_schema"]["schema"]["required"]) == {"insufficient", "statements"}


def test_extractive_stats_report_projection_without_claiming_a_model_call(model):
    calls = model({})
    result = answer(mode="extractive")
    assert calls == [] and result["generationStats"]["modelCallAttempted"] is False
    assert result["generationStats"]["usedEvidence"] == 1
