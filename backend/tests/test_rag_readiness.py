"""Readiness and partial hybrid regressions with isolated real Chroma, no model."""
from time import perf_counter

import pytest

from api.rag_embeddings import VectorUnavailable
from api.rag_readiness import Readiness, complete_selection, coverage, snapshot
from api.rag_search import search
from api.rag_vector import VectorIndex
from test_rag_vector import Encoder, chunk, index


def certify(ix, rows):
    ix.index(rows)
    assert ix.verify(rows, apply=True)["failed_documents"] == 0


def test_partial_hybrid_keeps_unindexed_bm25_candidates(index, monkeypatch):
    ix, _ = index
    a, b = chunk("ready"), chunk("pending")
    certify(ix, [a])
    seen = []
    def lexical(query, rows, k, **kwargs):
        seen.extend(rows)
        return [{**b, "score": 8}, {**a, "score": 2}]
    monkeypatch.setattr("api.rag_search.bm25", lexical)
    report = search("선급", [a, b], vector_index=ix)
    assert seen == [a, b]
    assert {r["id"] for r in report["results"]} == {a["id"], b["id"]}
    assert report["effective_mode"] == "hybrid" and report["fallback_reason"] is None
    assert report["coverage"] == {"allowed_documents": 2, "allowed_chunks": 2,
        "ready_documents": 1, "ready_chunks": 1, "excluded_documents": 1, "excluded_chunks": 1,
        "status": "partial", "exclusion_reasons": {
            "document_unverified_or_changed": {"documents": 1, "chunks": 1}}}
    assert search("선급", [b], vector_index=ix)["fallback_reason"] == "no_ready_documents"
    assert [r["id"] for r in search("선급", [a, b], mode="vector", vector_index=ix)["results"]] == [a["id"]]


def test_partial_batch_cannot_publish_whole_document(index):
    ix, _ = index
    a, b = chunk("a", document_id="doc"), chunk("b", document_id="doc")
    ix.index([a])
    assert complete_selection([a, b], [a]) == []
    assert Readiness(ix).collection() is None
    assert search("선급", [a, b], vector_index=ix)["fallback_reason"] == "no_ready_documents"
    assert ix.verify([a, b])["failed_documents"] == 1
    ix.index([b])
    assert ix.verify([a, b], apply=True)["ready_documents"] == 1
    assert search("선급", [a, b], vector_index=ix)["coverage"]["status"] == "full"


def test_audit_does_not_label_never_certified_documents_as_corruption(index):
    ix, _ = index
    a, b = chunk("ready"), chunk("pending")
    certify(ix, [a])
    assert ix.verify([a, b], apply=True)["failed_documents"] == 1
    report = search("선급", [a, b], vector_index=ix)
    assert report["effective_mode"] == "hybrid"
    assert report["coverage"]["status"] == "partial"
    assert report["coverage"]["ready_documents"] == 1


@pytest.mark.parametrize("field", ["id", "document_id", "title", "reference", "heading", "text", "page"])
def test_receipt_bound_to_exact_content_and_revision(index, field):
    ix, _ = index
    a = chunk("a")
    certify(ix, [a])
    changed = {**a, field: "changed"}
    assert search("선급", [changed], vector_index=ix)["fallback_reason"] == "no_ready_documents"
    # Reordered input and authorization metadata do not invalidate content.
    assert snapshot([a, changed]) == snapshot([changed, a])
    assert snapshot([a]) == snapshot([{**a, "meta": {"scope": "admin"}}])


def test_replacement_collection_cannot_reuse_old_receipts(index):
    ix, db = index
    a = chunk("a")
    certify(ix, [a])
    previous_id = str(ix.collection.id)
    db.delete_collection(ix.collection.name)
    replacement = VectorIndex(create=True, db=db, encoder=Encoder(), model_contract={"test": 1})
    assert str(replacement.collection.id) != previous_id
    replacement.index([a])
    assert search("선급", [a], vector_index=replacement)["fallback_reason"] == "no_ready_documents"
    replacement.verify([a], apply=True)
    assert search("선급", [a], vector_index=replacement)["effective_mode"] == "hybrid"
    model = VectorIndex(create=True, db=db, encoder=Encoder(), model_contract={"test": 2})
    assert search("선급", [a], vector_index=model)["fallback_reason"] == "no_ready_documents"


@pytest.mark.parametrize("damage", ["delete", "metadata", "receipt"])
def test_damage_fallback_audit_and_explicit_repair(index, damage):
    ix, _ = index
    a = chunk("a")
    certify(ix, [a])
    if damage == "delete":
        ix.collection.delete(ids=[ix.record_id(a)])
    elif damage == "metadata":
        ix.collection.update(ids=[ix.record_id(a)], metadatas=[{"content_hash": "damaged"}])
    else:
        receipts = Readiness(ix).collection()
        receipts.update(ids=receipts.get()["ids"], metadatas=[{"state": "invalid"}])
    report = search("선급", [a], vector_index=ix)
    assert report["effective_mode"] == "bm25" and report["coverage"]["status"] == "fallback"
    # Chroma may itself reject an ID-restricted query after record deletion.
    assert report["fallback_reason"] in {"index_result_incomplete", "index_result_stale",
                                          "index_verification_failed", "vector_backend_failure"}
    if damage != "receipt":
        assert ix.verify([a], apply=True)["failed_documents"] == 1
        assert search("선급", [a], vector_index=ix)["fallback_reason"] == "index_verification_failed"
    certify(ix, [a])
    assert search("선급", [a], vector_index=ix)["effective_mode"] == "hybrid"


def test_late_old_snapshot_does_not_overwrite_new(index):
    ix, _ = index
    old = chunk("a")
    new = {**old, "text": "new content"}
    certify(ix, [old])
    certify(ix, [new])
    ix.verify([old], apply=True)
    assert search("query", [new], vector_index=ix)["effective_mode"] == "hybrid"
    # A new source chunk makes the receipt stale even if the old chunk remains.
    added = chunk("added", document_id=new["document_id"])
    assert search("query", [new, added], vector_index=ix)["fallback_reason"] == "no_ready_documents"


def test_comparison_exposes_partial_coverage_without_body(index):
    import json
    from scripts.debug_retrieval import compare
    ix, _ = index
    a, b = chunk("a", text="PRIVATE"), chunk("b")
    certify(ix, [a])
    report = compare("query", [a, b], vector_index=ix)
    assert report["methods"]["bm25"]["coverage"]["status"] == "not_checked"
    for mode in ("vector", "hybrid"):
        assert report["methods"][mode]["coverage"]["status"] == "partial"
    assert "PRIVATE" not in json.dumps(report)


def test_comparison_cli_limit_checks_full_document_but_ranks_only_subset(index, monkeypatch, capsys):
    import json
    from scripts import debug_retrieval
    ix, _ = index
    a, b = chunk("a", document_id="doc"), chunk("b", document_id="doc")
    certify(ix, [a, b])
    monkeypatch.setattr(debug_retrieval, "load_dotenv", lambda *a, **kw: None)
    def load(*args, **kwargs):
        assert kwargs.get("limit") is None
        return [a, b]
    monkeypatch.setattr(debug_retrieval, "load_candidates", load)
    monkeypatch.setattr("api.rag_vector.VectorIndex", lambda: ix)
    assert debug_retrieval.main(["선급", "--limit", "1"]) == 0
    methods = json.loads(capsys.readouterr().out)["methods"]
    for mode in ("vector", "hybrid"):
        assert methods[mode]["effective_mode"] == mode
        assert methods[mode]["coverage"]["ready_chunks"] == 1
        assert [r["id"] for r in methods[mode]["results"]] == ["a"]


def test_subset_cannot_certify_changed_content_from_old_snapshot(index):
    ix, _ = index
    a, b = chunk("a", document_id="doc"), chunk("b", document_id="doc")
    certify(ix, [a, b])
    report = search("query", [{**a, "text": "changed"}], vector_index=ix, complete_chunks=[a, b])
    assert report["fallback_reason"] == "candidate_snapshot_mismatch"


def test_cli_limit_and_verify_share_publication(index, monkeypatch, capsys):
    import json
    from scripts import rag_index
    ix, _ = index
    rows = [chunk("a", document_id="doc"), chunk("b", document_id="doc")]
    monkeypatch.setattr(rag_index, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.setattr(rag_index, "load_candidates", lambda *a, **kw: rows)
    monkeypatch.setattr("api.rag_vector.VectorIndex", lambda **kw: ix)
    assert rag_index.main(["index", "--apply", "--limit", "1"]) == 0
    partial = json.loads(capsys.readouterr().out)
    assert partial["partial_documents_not_certified"] == 1
    assert Readiness(ix).collection() is None
    assert rag_index.main(["verify"]) == 0
    assert json.loads(capsys.readouterr().out)["verification"]["failed_documents"] == 1
    assert Readiness(ix).collection() is None
    assert rag_index.main(["index", "--apply"]) == 0
    assert json.loads(capsys.readouterr().out)["verification"]["ready_documents"] == 1
    assert rag_index.main(["verify", "--apply"]) == 0
    assert json.loads(capsys.readouterr().out)["verification"]["failed_documents"] == 0


def test_no_full_present_and_batched_readiness_cost(index, monkeypatch):
    """Same synthetic corpus; timings informative, call/record counts asserted."""
    ix, _ = index
    rows = [chunk(str(i), document_id=f"doc-{i // 100}") for i in range(1000)]
    certify(ix, rows)
    start = perf_counter()
    assert len(ix.present(rows)) == len(rows)
    before = perf_counter() - start
    calls = []
    from chromadb.api.models.Collection import Collection
    original = Collection.get
    def tracked(self, *args, **kwargs):
        calls.append((self.name, len(kwargs.get("ids", []))))
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Collection, "get", tracked)
    monkeypatch.setattr(ix, "present", lambda *args, **kwargs: pytest.fail("search called full present"))
    diagnostics = coverage(rows)
    start = perf_counter()
    assert Readiness(ix).select(rows, diagnostics) == rows
    after = perf_counter() - start
    assert calls == [(Readiness(ix).name, 10)]
    ix.search("query", rows, top_k=5)
    assert calls == [(Readiness(ix).name, 10)] * 2
    print(f"readiness synthetic chunks=1000 documents=10 old_records=1000 new_records=10 "
          f"old_get_calls=4 new_get_calls=1 before_ms={before*1000:.2f} after_ms={after*1000:.2f}")


pytestmark = pytest.mark.usefixtures("stub_lexical")
