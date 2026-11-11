"""Evaluator correctness, independent of whether the search baseline succeeds."""
import copy
import json

import pytest

from scripts.evaluate_retrieval import (
    ROOT, digest, evaluate, load_inputs, main, percentile, score_results, seed_digest,
)


def case():
    return {"id": "multi", "category": "answerable", "question": "test",
            "expected_behavior": "find both", "evidence": [
                {"document_id": "a", "quote": "first relevant evidence"},
                {"document_id": "b", "quote": "second relevant evidence"}]}


def row(id, doc, text):
    return {"id": id, "document_id": doc, "text": text, "score": 1.0}


def test_recall_counts_each_evidence_once_and_mrr_uses_first_relevant_rank():
    rows = [row("x", "wrong", "first relevant evidence"),
            row("a1", "a", "first relevant evidence"),
            row("a2", "a", "first relevant evidence")]
    result = score_results(case(), rows)
    assert result["hit"] is True
    assert result["recall"] == .5
    assert result["reciprocal_rank"] == .5
    assert result["status"] == "partial"
    assert score_results(case(), rows + [row("b", "b", "second relevant evidence")])["recall"] == 1


def test_wrong_document_does_not_count_and_empty_results_are_a_miss():
    for rows in ([], [row("x", "wrong", "first relevant evidence")]):
        result = score_results(case(), rows)
        assert result["hit"] is False and result["recall"] == 0
        assert result["reciprocal_rank"] == 0 and result["status"] == "miss"


def test_identical_quote_in_inland_rule_does_not_satisfy_international_label():
    question = {**case(), "evidence": [{"document_id": "a", "quote": "first relevant evidence",
                                        "heading_contains": "International"}]}
    candidate = {**row("a", "a", "first relevant evidence"), "heading": "Inland Rule 5"}
    assert score_results(question, [candidate])["status"] == "miss"
    candidate["heading"] = "International Rule 5"
    assert score_results(question, [candidate])["status"] == "complete"


def test_unanswerable_candidates_are_not_labelled_as_hallucinations():
    negative = {**case(), "category": "unanswerable", "evidence": []}
    found = score_results(negative, [row("x", "a", "anything")])
    assert found["status"] == "candidate_review" and found["recall"] is None
    assert score_results(negative, [])["empty_results"] is True


@pytest.fixture
def snapshot(tmp_path):
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps([{"id": "a", "title": "manual", "kind": "sample", "reference": "test",
                                 "sections": [{"heading": "test", "text": "first relevant evidence"}]}]), encoding="utf-8")
    dataset = {"version": 1, "seed_hash_format": "canonical-json-v1",
               "seed_sha256": seed_digest(json.loads(seed.read_text(encoding="utf-8"))), "cases": [
        {**case(), "evidence": case()["evidence"][:1]}]}
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps(dataset), encoding="utf-8")
    return seed, cases, dataset


def test_seed_labels_accept_lf_crlf_and_equivalent_json_formatting(snapshot):
    seed, cases, _ = snapshot
    content = json.loads(seed.read_text(encoding="utf-8"))
    for newline in ("\n", "\r\n"):
        formatted = json.dumps(content, ensure_ascii=False, indent=2) + "\n"
        seed.write_bytes(formatted.replace("\n", newline).encode("utf-8"))
        _, corpus = load_inputs(seed, cases)
        assert corpus[0]["text"] == "first relevant evidence"


def test_changed_seed_content_is_rejected(snapshot):
    seed, cases, _ = snapshot
    content = json.loads(seed.read_text(encoding="utf-8"))
    content[0]["sections"][0]["text"] += " changed"
    seed.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ValueError, match="원문 해시"):
        load_inputs(seed, cases)


@pytest.mark.parametrize("mutation", ["missing_quote", "wrong_hash", "duplicate_id", "empty_evidence", "wrong_document"])
def test_invalid_labels_fail_before_running_search(snapshot, mutation):
    seed, path, dataset = snapshot
    if mutation == "missing_quote":
        dataset["cases"][0]["evidence"][0]["quote"] = "absent evidence that must not silently pass"
    elif mutation == "wrong_hash":
        dataset["seed_sha256"] = "wrong"
    elif mutation == "duplicate_id":
        dataset["cases"].append(copy.deepcopy(dataset["cases"][0]))
    elif mutation == "empty_evidence":
        dataset["cases"][0]["evidence"] = []
    else:
        dataset["cases"][0]["evidence"][0]["document_id"] = "other"
    path.write_text(json.dumps(dataset), encoding="utf-8")
    with pytest.raises(ValueError):
        load_inputs(seed, path)


def test_aggregate_metrics_keep_negative_questions_out_of_recall_denominator():
    positive = case()
    negative = {**case(), "id": "negative", "question": "negative", "category": "unanswerable", "evidence": []}
    retrieved = [row("a", "a", "first relevant evidence")]
    report = evaluate([positive, negative], [], repeats=2,
                      retriever=lambda query, corpus, top_k: retrieved if query == "test" else [])
    assert report["metrics"] == {"hit_rate_at_k": 1, "recall_at_k": .5,
                                  "mrr_at_k": 1, "unanswerable_empty_rate": 1}
    assert len(report["cases"][0]["latency_ms"]["runs"]) == 2
    assert percentile([10, 20, 30], .95) == 29


def test_changed_repeat_rankings_are_rejected():
    calls = []
    def unstable(*args, **kwargs):
        calls.append(1)
        return [row(str(len(calls)), "a", "first relevant evidence")]
    with pytest.raises(ValueError, match="반복 검색 결과"):
        evaluate([case()], [], repeats=2, retriever=unstable)


def test_pilot_labels_resolve_against_the_production_chunker():
    dataset, corpus = load_inputs(ROOT / "backend/knowledge/seed.json",
                                  ROOT / "backend/knowledge/evaluation/maritime-questions.json")
    assert len(dataset["cases"]) == 20
    assert sum(c["category"] == "answerable" for c in dataset["cases"]) == 16
    assert any(r["source_file"] for r in corpus)


@pytest.mark.usefixtures("prepared_lexical")
def test_cli_writes_machine_readable_and_human_reports(snapshot, tmp_path):
    seed, cases, _ = snapshot
    output = tmp_path / "report"
    assert main(["--seed", str(seed), "--cases", str(cases), "--output", str(output), "--repeats", "1"]) == 0
    report = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert report["metrics"]["hit_rate_at_k"] == 1
    assert report["provenance"]["sha256"]["seed"] == digest(seed)
    assert (output / "results.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    assert "LLM" in (output / "results.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("args", [["--top-k", "0"], ["--repeats", "-1"]])
def test_cli_rejects_invalid_counts(args):
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2
