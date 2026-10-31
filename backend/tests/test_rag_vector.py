"""Offline deterministic encoder + REAL temporary Chroma; no network/app DB."""
import json

import pytest

from api.rag_embeddings import VectorUnavailable, content_hash, split_passage
from api.rag_hybrid import rrf
from api.rag_search import search
from api.rag_vector import VectorIndex


def chunk(identity, text="선급 정지", **changes):
    return {"id": identity, "document_id": "doc-" + identity, "title": "테스트 문서",
            "reference": "901", "heading": "선급 정지", "page": 21, "text": text, **changes}


class Encoder:
    def documents(self, chunks, batch_size=16):
        return [[1., 0., 0.] if "선급" in row["text"] else [0., 1., 0.] for row in chunks]

    def query(self, text):
        return [1., 0., 0.]


@pytest.fixture
def index(tmp_path):
    import chromadb
    from chromadb.config import Settings
    db = chromadb.PersistentClient(path=str(tmp_path), settings=Settings(anonymized_telemetry=False))
    return VectorIndex(create=True, db=db, encoder=Encoder(), model_contract={"test": 1}), db


def test_rrf_dedup_tie_empty():
    a, b, c = [chunk(x) for x in "abc"]
    result = rrf([[a, a, b], [c, b]], top_k=3)
    assert [row["id"] for row in result] == ["b", "a", "c"]
    assert result[0]["score"] == pytest.approx(2 / 62)
    assert rrf([[], []]) == []
    assert rrf([[{**a, "score": 1000}], [{**b, "score": -1000}]])[0]["id"] == "a"


@pytest.mark.parametrize("field", ["id", "document_id", "title", "reference", "heading", "text", "page"])
def test_fingerprint_all_fields(field):
    original = chunk("a")
    assert content_hash(original) != content_hash({**original, field: "changed"})


def test_long_passage_lossless():
    text = "heading\n" + "한글 English 긴 문장. " * 100
    parts = split_passage(text, len, 64)
    assert "".join(parts) == text
    assert all(len("passage: " + part) <= 64 for part in parts)


def test_real_chroma_upsert_scope_restart_stale(index):
    ix, db = index
    a, b = chunk("a"), chunk("b", "연료 황 함유량")
    assert ix.index([a, b])["indexed"] == 2
    assert ix.index([a, b])["already_current"] == 2
    restored = VectorIndex(db=db, encoder=Encoder(), model_contract={"test": 1})
    assert restored.search("선급", [a, b])[0]["id"] == "a"
    # The globally best 'a' is inaccessible: only b enters ANN query.
    assert [r["id"] for r in restored.search("선급", [b])] == ["b"]
    assert restored.search("", [a]) == []
    revised = {**a, "text": "선급 수정 본문"}
    with pytest.raises(VectorUnavailable, match="stale"):
        restored.search("선급", [revised, b])
    assert restored.index([revised])["indexed"] == 1
    assert restored.search("선급", [revised])[0]["text"] == revised["text"]
    # Old vectors may remain, but their IDs are outside the permitted query.
    assert restored.collection.count() == 3
    with pytest.raises(VectorUnavailable, match="not_ready"):
        VectorIndex(db=db, model_contract={"test": 2})


def test_missing_and_mismatched_metadata(index):
    ix, _ = index
    a = chunk("a")
    ix.index([a])
    with pytest.raises(VectorUnavailable):
        ix.search("선급", [a, chunk("missing")])
    ix.collection.update(ids=[ix.record_id(a)], metadatas=[{"content_hash": "corrupt"}])
    with pytest.raises(VectorUnavailable):
        ix.search("선급", [a])


def test_reuse_embedding_input_across_revisions_but_keep_metadata(index):
    ix, _ = index
    calls = []
    original = ix.encoder.documents
    ix.encoder.documents = lambda rows, batch_size: calls.append(len(rows)) or original(rows, batch_size)
    a = chunk("a")
    ix.index([a, chunk("same-input")])
    assert calls == [1]
    revised = chunk("revision", page=25, version="2", meta={"scope": "admin"})
    assert ix.index([revised])["indexed"] == 1
    assert calls == [1]
    assert ix.search("선급", [revised])[0]["page"] == 25
    for field in ("title", "reference", "heading", "text"):
        ix.index([{**revised, field: "different " + field}])
    assert calls == [1, 1, 1, 1, 1]


def test_legacy_vector_metadata_still_searchable(index):
    ix, _ = index
    a = chunk("legacy")
    meta = {k: v for k, v in ix.metadata(a).items() if k != "embedding_input_hash"}
    ix.collection.upsert(ids=[ix.record_id(a)], embeddings=Encoder().documents([a]), metadatas=[meta])
    assert ix.index([a])["already_current"] == 1
    assert ix.search("선급", [a])[0]["id"] == "legacy"


@pytest.mark.parametrize("reuse_first", [True, False])
def test_mixed_reused_and_new_vectors_resume_and_reindex(index, reuse_first):
    """Real Chroma returns ndarray; our encoder returns lists. Both orders work."""
    ix, db = index
    calls = []
    encode = ix.encoder.documents
    ix.encoder.documents = lambda rows, batch_size: calls.append(len(rows)) or encode(rows, batch_size)
    original = chunk("original")
    ix.index([original])  # A previously completed batch survives worker failure.
    reused = chunk("new-revision", page=22)
    new = chunk("new-content", "연료 황 함유량")
    batch = [reused, new] if reuse_first else [new, reused]
    assert ix.index([original, *batch]) == {"requested": 3, "indexed": 2, "already_current": 1}
    assert calls == [1, 1]  # Only the genuinely new input needs encoding.
    restored = VectorIndex(db=db, encoder=Encoder(), model_contract={"test": 1})
    assert restored.index([original, *batch])["already_current"] == 3
    assert restored.collection.count() == 3
    result = restored.search("선급", batch)
    assert result[0]["id"] == reused["id"]
    assert result[0]["page"] == 22


def test_dispatch_default_and_fallback(monkeypatch, caplog):
    import api.rag_search as module
    a = chunk("a")
    calls = []
    monkeypatch.setattr(module, "bm25", lambda q, c, k: calls.append((q, c, k)) or [{**a, "score": 3}])
    assert search("선급", [a], mode="bm25")["effective_mode"] == "bm25"
    class Failed:
        def search(self, *args):
            raise RuntimeError("secret body and DSN")
    result = search("선급", [a], mode="hybrid", vector_index=Failed())
    assert result["effective_mode"] == "bm25"
    assert result["fallback_reason"] == "vector_backend_failure"
    assert "secret" not in caplog.text
    assert result["results"][0]["score"] == 3
    assert search("", [a], mode="vector")["results"] == []


def test_hybrid_uses_sufficient_candidates(monkeypatch):
    import api.rag_search as module
    a, b = chunk("a"), chunk("b")
    sizes = []
    monkeypatch.setattr(module, "bm25", lambda q, c, k: sizes.append(k) or [{**a, "score": 90}, {**b, "score": 1}])
    class V:
        def search(self, q, rows, k):
            sizes.append(k)
            return [{**b, "score": .9}, {**a, "score": .1}]
    result = search("query", [a, b], top_k=1, mode="hybrid", vector_index=V())
    assert result["effective_mode"] == "hybrid"
    assert sizes == [30, 30]
    assert result["results"][0]["id"] == "a"
    assert result["results"][0]["score"] == pytest.approx(1 / 61 + 1 / 62)


@pytest.mark.parametrize("legacy_mode", [None, "bm25", "vector", "hybrid"])
def test_web_hybrid_ignores_legacy_environment(monkeypatch, legacy_mode):
    import api.rag_search as module
    import api.store.documents as documents
    if legacy_mode is None:
        monkeypatch.delenv("HAEDAP_RETRIEVAL_MODE", raising=False)
    else:
        monkeypatch.setenv("HAEDAP_RETRIEVAL_MODE", legacy_mode)
    rows = [chunk(str(i)) for i in range(7)]
    sizes = []
    def lexical(q, candidates, k):
        assert candidates == rows
        sizes.append(k)
        return [{**row, "score": 100 - i} for i, row in enumerate(rows)]
    class V:
        def search(self, q, candidates, k):
            assert candidates == rows
            sizes.append(k)
            return [{**row, "score": .9} for row in reversed(rows)]
    monkeypatch.setattr(module, "bm25", lexical)
    monkeypatch.setattr("api.rag_vector.VectorIndex", V)
    report = module.search("query", rows)
    assert report["requested_mode"] == report["effective_mode"] == "hybrid"
    assert report["fallback_reason"] is None
    expected = rrf([lexical("query", rows, 30), V().search("query", rows, 30)])
    assert report["results"] == expected
    store = documents.DocumentStore()
    monkeypatch.setattr(store, "search_candidates", lambda *args: rows)
    evidence = store.search({"role": "operator"}, "query")
    assert len(evidence) == 5
    assert [row["id"] for row in evidence] == [row["id"] for row in expected]
    assert all("score" not in row for row in evidence)
    assert set(sizes) == {30}


@pytest.mark.parametrize("legacy_mode", [None, "bm25", "vector"])
def test_store_final_current_db_recheck(monkeypatch, legacy_mode):
    import api.store.documents as module
    if legacy_mode is None:
        monkeypatch.delenv("HAEDAP_RETRIEVAL_MODE", raising=False)
    else:
        monkeypatch.setenv("HAEDAP_RETRIEVAL_MODE", legacy_mode)
    a, b = chunk("a"), chunk("b")
    snapshots = iter([[a, b], [{**b, "text": "changed"}]])
    store = module.DocumentStore()
    monkeypatch.setattr(store, "search_candidates", lambda *args: next(snapshots))
    monkeypatch.setattr(module, "retrieve", lambda q, rows, top_k: rows)
    assert store.search({"role": "guest"}, "선급") == []


def test_compare_no_body(monkeypatch):
    from scripts.debug_retrieval import compare
    import scripts.debug_retrieval as module
    a = chunk("a", "PRIVATE-BODY")
    monkeypatch.setattr(module, "search", lambda *a, **kw: {"effective_mode": kw["mode"], "results": [{**chunk("a", "PRIVATE-BODY"), "score": .5}]})
    report = compare("선급", [a])
    assert "PRIVATE-BODY" not in json.dumps(report)
    assert set(report["methods"]) == {"bm25", "vector", "hybrid"}


@pytest.mark.parametrize("reason", [None, "model_not_prepared", "index_incomplete_or_stale", "vector_backend_failure"])
def test_compare_explicit_modes_and_fallback(monkeypatch, caplog, reason):
    from scripts.debug_retrieval import compare
    import api.rag_search as module
    monkeypatch.setenv("HAEDAP_RETRIEVAL_MODE", "bm25")
    a, b = chunk("a"), chunk("b")
    monkeypatch.setattr(module, "bm25", lambda *args: [{**a, "score": 3}, {**b, "score": 1}])
    class V:
        def search(self, *args):
            if reason:
                raise VectorUnavailable(reason)
            return [{**b, "score": .9}, {**a, "score": .1}]
    methods = compare("선급", [a, b], vector_index=V())["methods"]
    assert methods["bm25"]["effective_mode"] == "bm25"
    assert methods["bm25"]["fallback_reason"] is None
    for mode in ("vector", "hybrid"):
        assert methods[mode]["requested_mode"] == mode
        assert methods[mode]["effective_mode"] == ("bm25" if reason else mode)
        assert methods[mode]["fallback_reason"] == reason
    if reason:
        assert f"reason={reason}" in caplog.text
    else:
        assert methods["vector"]["results"][0]["id"] == "b"
        assert methods["hybrid"]["results"][0]["score"] == pytest.approx(1 / 61 + 1 / 62)


def test_cli_readonly_load(monkeypatch):
    from scripts import rag_index
    commands = []
    class Store:
        def __init__(self, dsn): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def run(self, sql): commands.append(sql)
        def search_candidates(self, user, kind, ids):
            assert user["role"] == "guest"
            return [chunk("a"), chunk("b", title="Other")]
    monkeypatch.setattr(rag_index, "DebugStore", Store)
    assert len(rag_index.load_candidates("", document_title="테스트", limit=1)) == 1
    assert "READ ONLY" in commands[0]


def test_model_not_prepared_no_download(tmp_path):
    from api.rag_embeddings import LocalEmbedder
    with pytest.raises(VectorUnavailable, match="not_prepared"):
        LocalEmbedder(str(tmp_path))


def test_missing_local_index_creates_no_directory(tmp_path, monkeypatch):
    from api.rag_vector import client
    path = tmp_path / "missing-index"
    monkeypatch.delenv("HAEDAP_CHROMA_HOST", raising=False)
    monkeypatch.setenv("HAEDAP_CHROMA_PATH", str(path))
    with pytest.raises(VectorUnavailable, match="index_not_ready"):
        client()
    assert not path.exists()


def test_cli_dry_run_no_index_initialization(monkeypatch, capsys):
    from scripts import rag_index
    monkeypatch.setattr(rag_index, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.setattr(rag_index, "load_candidates", lambda *a, **kw: [chunk("a")])
    monkeypatch.setattr("api.rag_vector.VectorIndex", lambda **kw: pytest.fail("dry run initialized index"))
    assert rag_index.main(["index", "--dry-run", "--limit", "1"]) == 0
    assert json.loads(capsys.readouterr().out)["chunks"] == 1


@pytest.mark.parametrize("mode", ["vector", "hybrid"])
def test_filter_before_dispatch(monkeypatch, mode):
    import api.store.documents as module
    from api.rag_search import search as dispatch
    monkeypatch.setenv("HAEDAP_RETRIEVAL_MODE", mode)
    public = chunk("public", meta={"scope": "all", "status": "active"}, kind="onboard", reviewed_at="2026-01-01")
    admin = {**public, "id": "admin", "meta": {"scope": "admin", "status": "active"}}
    deleted = {**public, "id": "deleted", "meta": {"scope": "all", "status": "deleted"}}
    retired = {**deleted, "meta": {"scope": "all", "status": "retired"}}
    official = {**public, "id": "official", "kind": "official-summary"}
    store = module.DocumentStore()
    def all_rows(sql, *args):
        assert "d.active=true" in sql
        return [public, admin, deleted, retired, official]
    monkeypatch.setattr(store, "all", all_rows, raising=False)
    class V:
        def search(self, q, rows, k):
            assert [r["id"] for r in rows] == ["public"]
            return [{**rows[0], "score": .7}]
    monkeypatch.setattr(module, "retrieve", lambda q, rows, top_k: dispatch(q, rows, top_k, mode=mode, vector_index=V())["results"])
    result = store.search({"role": "guest"}, "선급 정지", kind="manual")
    assert [row["id"] for row in result] == ["public"]
    assert "score" not in result[0]
