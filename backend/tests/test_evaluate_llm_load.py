"""Fixed-input load-matrix checks; model responses are mocked, never real calls."""

from copy import deepcopy
import json

import httpx
import pytest

from api import config, llm
from scripts import evaluate_llm as fixed
from scripts import evaluate_llm_load as load

SETTINGS = config.LLMSettings("http://localhost:11434/v1", "mock-model", "", "json_schema")


def matrix(*scenarios, case_id="sulphur-limits"):
    case = next(case for case in fixed.load_cases() if case["id"] == case_id)
    return load.build_matrix([case], scenarios or tuple(load.SCENARIOS))


def transport(monkeypatch, reply=None, *, failure=None):
    calls = []

    def handler(request):
        calls.append(request)
        if failure is not None:
            raise failure("PRIVATE upstream key and host", request=request)
        if reply is None:
            supplied = json.loads(json.loads(request.content)["messages"][1]["content"])["evidence"][0]
            answer = {"insufficient": False, "statements": [{"text": "검토할 모의 답변입니다.",
                       "chunkId": supplied["chunkId"], "quote": supplied["text"]}]}
        else:
            answer = reply
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "role": "assistant", "content": json.dumps(answer, ensure_ascii=False)}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(llm.httpx, "post", client.post)
    return calls, client


def test_matrix_varies_actual_sections_without_changing_labelled_question_or_source():
    rows = matrix()
    assert [row["scenario"] for row in rows] == ["one", "three", "five", "five-long"]
    assert [len(row["evidence"]) for row in rows] == [1, 3, 5, 5]
    assert all(row["question"] == rows[0]["question"] for row in rows)
    assert all(row["expected"] == rows[0]["expected"] for row in rows)
    assert all(row["evidence"][0] == rows[0]["evidence"][0] for row in rows)
    assert all(len({item["id"] for item in row["evidence"]}) == len(row["evidence"]) for row in rows)
    assert sum(len(item["text"].encode("utf-8")) for item in rows[3]["evidence"]) > sum(
        len(item["text"].encode("utf-8")) for item in rows[2]["evidence"])
    seed = json.loads(fixed.DEFAULT_SEED.read_text(encoding="utf-8"))
    sections = {(doc["id"], section["heading"], section["text"])
                for doc in seed for section in doc.get("sections", [])}
    for row in rows:
        assert row["additional_section_policy"] == "distinct_seed_sections_not_labelled_irrelevant"
        for item in row["evidence"]:
            assert (item["document_id"], item["heading"], item["text"]) in sections
    assert load.fingerprint(rows) == load.fingerprint(matrix())


def test_default_eight_scenarios_are_offline_and_never_claim_semantic_accuracy(monkeypatch, capsys):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Offline load evaluation must not read settings or call a model")

    monkeypatch.setattr(config, "llm_settings", forbidden)
    monkeypatch.setattr(llm, "grounded_statements", forbidden)
    monkeypatch.setattr(llm.httpx, "post", forbidden)
    assert load.main([]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["cases"] == report["summary"]["answered"] == 8
    assert report["summary"]["model_calls"] == 0
    assert report["execution"] == "extractive" and report["model_call_attempted"] is False
    assert report["model"] is None and report["semantic_review"] == "pending"
    assert "without_retrieval_db_auth_or_browser" in report["evaluation_scope"]
    assert "not model tokens" in report["input_units"]
    for row in report["results"]:
        assert row["semantic_review"] == "pending" and "accuracy" not in row
        assert row["generation_seconds"] is None and row["citation_valid"] is True
        assert row["generationStats"]["usedEvidence"] <= row["supplied_evidence_count"]
        assert row["generationStats"]["payloadBytes"] <= row["generationStats"]["payloadByteBudget"]


def test_real_mode_records_actual_transport_and_admitted_input_separately(monkeypatch):
    calls, client = transport(monkeypatch)
    with client:
        report = load.evaluate(matrix("one", "five-long"), "llm", settings=SETTINGS)
    assert len(calls) == report["summary"]["model_calls"] == 2
    assert report["execution"] == "real_model"
    assert report["model"] == "mock-model"  # This test is explicitly mocked.
    large = report["results"][1]
    assert large["supplied_evidence_count"] == large["generationStats"]["usedEvidence"] == 5
    assert large["generationStats"]["omittedEvidence"] == 0
    assert 8192 < large["generationStats"]["payloadBytes"] <= large["generationStats"]["payloadByteBudget"] == 32_768
    assert len(large["used_evidence_ids"]) == large["generationStats"]["usedEvidence"]
    assert len(large["omitted_evidence_ids"]) == large["generationStats"]["omittedEvidence"]
    assert large["labelled_evidence_included"] is True
    assert len(large["selected_input_sha256"]) == 64
    assert all(row["model_call_attempted"] for row in report["results"])
    assert all(row["semantic_review"] == "pending" for row in report["results"])
    assert all(row["generation_seconds"] >= 0 for row in report["results"])


def test_offline_preview_limit_preserves_the_full_supplied_source():
    rows = matrix("one")
    rows[0]["evidence"][0]["text"] = "x" * 4500
    report = load.evaluate(rows, "extractive")
    row = report["results"][0]
    assert row["outcome"] == "answered" and row["extractive_output_truncated"] is True
    assert len(row["source_evidence"][0]["text"]) == 4500
    assert len(row["statements"][0]["quote"]) == report["extractive_excerpt_limit_chars"] == 4000
    assert row["statements"][0]["quote"] in row["source_evidence"][0]["text"]


def test_omitted_labelled_source_is_visible_without_claiming_accuracy():
    rows = matrix("five")
    rows[0]["evidence"][0]["text"] = "긴 원문입니다." * 4000
    row = load.evaluate(rows, "extractive")["results"][0]
    assert row["outcome"] == "answered"  # Other sections remain available.
    assert row["labelled_evidence_included"] is False
    assert rows[0]["labelled_evidence_ids"][0] in row["omitted_evidence_ids"]
    assert rows[0]["labelled_evidence_ids"][0] not in row["used_evidence_ids"]
    assert row["semantic_review"] == "pending" and "accuracy" not in row


def test_valid_citation_with_wrong_number_is_still_pending(monkeypatch):
    rows = matrix("one")
    source = rows[0]["evidence"][0]
    wrong = {"insufficient": False, "statements": [{"text": "황 한도는 99%입니다.",
             "chunkId": source["id"], "quote": source["text"]}]}
    calls, client = transport(monkeypatch, wrong)
    with client:
        row = load.evaluate(rows, "llm", settings=SETTINGS)["results"][0]
    assert len(calls) == 1 and row["citation_valid"] is True
    assert "99%" in row["statements"][0]["text"]
    assert row["semantic_review"] == "pending" and "semantic_correct" not in row


def test_expected_insufficiency_is_normal_and_not_semantic_pass(monkeypatch):
    _, client = transport(monkeypatch, {"insufficient": True, "statements": []})
    with client:
        row = load.evaluate(matrix("one", case_id="unsupported-captain-name"), "llm", settings=SETTINGS)["results"][0]
    assert row["outcome"] == "insufficient" and row["expected_insufficient_matches"] is True
    assert row["citation_valid"] is None and row["semantic_review"] == "pending"


@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ConnectError])
def test_model_failures_keep_only_class_name_and_do_not_fallback(monkeypatch, failure):
    _, client = transport(monkeypatch, failure=failure)
    with client:
        report = load.evaluate(matrix("one"), "llm", settings=SETTINGS)
    row = report["results"][0]
    assert row["outcome"] == "model_error" and row["error_type"] == failure.__name__
    assert row["model_call_attempted"] is True and row["statements"] == []
    assert row["expected_insufficient_matches"] is None
    assert "PRIVATE" not in json.dumps(report)


def test_invalid_model_quote_is_technical_error(monkeypatch):
    source = matrix("one")[0]["evidence"][0]
    _, client = transport(monkeypatch, {"insufficient": False, "statements": [{
        "text": "모의 응답", "chunkId": source["id"], "quote": "source does not contain this quote"}]})
    with client:
        row = load.evaluate(matrix("one"), "llm", settings=SETTINGS)["results"][0]
    assert row["outcome"] == "model_error" and row["citation_valid"] is False
    assert row["statements"] == []


def test_oversized_single_source_is_rejected_without_any_model_call(monkeypatch):
    rows = matrix("one")
    rows[0]["evidence"][0]["text"] = "긴 원문입니다." * 4000

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Nothing fits input budget; model must not be called")

    monkeypatch.setattr(llm, "grounded_statements", forbidden)
    report = load.evaluate(rows, "llm", settings=SETTINGS)
    row = report["results"][0]
    assert row["outcome"] == "input_rejected" and row["error_type"] == "InputBudgetExceeded"
    assert row["generationStats"]["usedEvidence"] == 0 and row["model_call_attempted"] is False
    assert report["execution"] == "no_model_calls" and report["summary"]["model_calls"] == 0


def test_selected_utf8_report_and_existing_file_preservation(tmp_path, capsys):
    output = tmp_path / "입력량-평가.json"
    args = ["--case", "sulphur-limits", "--scenario", "one", "--scenario", "five-long", "--output", str(output)]
    assert load.main(args) == 0
    original = output.read_bytes()
    report = json.loads(original)
    assert [row["scenario"] for row in report["results"]] == ["one", "five-long"]
    assert "황" in output.read_text(encoding="utf-8")
    assert load.main(args) == 1 and output.read_bytes() == original
    assert capsys.readouterr().err.startswith("Load evaluation failed:")


@pytest.mark.parametrize("reason", ["existing", "unknown_case", "missing_settings", "missing_parent"])
def test_cli_invalid_paths_or_selection_never_spend_a_model_call(monkeypatch, tmp_path, capsys, reason):
    calls = []
    monkeypatch.setattr(llm, "grounded_statements", lambda *_args, **_kwargs: calls.append(True))
    monkeypatch.setattr(config, "llm_settings", lambda: None if reason == "missing_settings" else SETTINGS)
    args = ["--mode", "llm", "--case", "sulphur-limits", "--scenario", "one"]
    if reason == "existing":
        output = tmp_path / "existing.json"
        output.write_text("preserve", encoding="utf-8")
        args += ["--output", str(output)]
    elif reason == "unknown_case":
        args += ["--case", "unknown"]
    elif reason == "missing_parent":
        args += ["--output", str(tmp_path / "absent" / "report.json")]
    assert load.main(args) == 1 and calls == []
    assert "PRIVATE" not in capsys.readouterr().err


def test_unknown_scenario_is_cli_syntax_error():
    with pytest.raises(SystemExit) as exc:
        load.main(["--scenario", "not-a-scenario"])
    assert exc.value.code == 2


def test_matrix_rejects_duplicate_selection_and_multiple_labelled_sources():
    cases = fixed.load_cases()[:1]
    with pytest.raises(ValueError):
        load.build_matrix(cases, ["one", "one"])
    changed = deepcopy(cases)
    changed[0]["evidence"].append(deepcopy(changed[0]["evidence"][0]))
    with pytest.raises(ValueError):
        load.build_matrix(changed, ["one"])
