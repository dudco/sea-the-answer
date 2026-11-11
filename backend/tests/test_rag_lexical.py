"""Contract unit tests and opt-in REAL OpenSearch/Nori integration tests."""
import httpx
import pytest

from api.rag_lexical import LexicalIndex, LexicalUnavailable, fields, fingerprint, identifiers, record_id, receipt_id
from api.rag_embeddings import VectorUnavailable
from api.errors import ApiError
from api import rag_search


def row(id="a", text="선급이 자동으로 정지된다.", doc=None):
    return dict(id=id, document_id=doc or "doc-"+id, title="Synthetic maritime", reference="901.1",
                heading="Inspection", text=text, page=1)


def test_contract_and_hash_track_input_not_scope():
    source = row()
    assert record_id(source) == record_id({**source, "meta": {"scope": "admin"}})
    for key in ("id", "document_id", "title", "reference", "heading", "text", "page"):
        assert record_id(source) != record_id({**source, key: "changed"})
    assert identifiers("901.1 0.50% 5-2-1 901.1") == ["901.1", "0.50", "5-2-1"]
    assert fields({"text": "ＦＵＥＬ"}).endswith("fuel")


def test_remote_errors_do_not_expose_response_or_credentials():
    def fail(request):
        return httpx.Response(500, json={"error": "PRIVATE BODY SECRET"})
    ix = LexicalIndex(client=httpx.Client(base_url="http://test", transport=httpx.MockTransport(fail)))
    with pytest.raises(LexicalUnavailable, match="^lexical_backend_failure$"):
        ix.resolve()


@pytest.mark.parametrize("lexical_ok,vector_ok,mode", [(True,True,"hybrid"),(True,False,"bm25"),
                                                       (False,True,"vector"),(False,False,"unavailable")])
def test_independent_availability_and_explicit_unavailable(monkeypatch, lexical_ok, vector_ok, mode, caplog):
    def bm(q, rows, k, **kwargs):
        if not lexical_ok:
            raise LexicalUnavailable("lexical_no_ready_documents")
        return [{**rows[0], "score": 9}]
    class V:
        def search(self, q, rows, k, **kwargs):
            if not vector_ok:
                raise VectorUnavailable("no_ready_documents")
            return [{**rows[0], "score": .8}]
    monkeypatch.setattr(rag_search, "bm25", bm)
    monkeypatch.setattr("api.rag_vector.VectorIndex", V)
    report = rag_search.search("query", [row()])
    assert report["effective_mode"] == mode
    if mode == "unavailable":
        with pytest.raises(ApiError) as error:
            rag_search.retrieve("query", [row()])
        assert error.value.status == 503 and error.value.code == "SEARCH_UNAVAILABLE"
    else:
        assert report["results"]
    assert "PRIVATE" not in caplog.text


def test_successful_zero_hits_is_not_backend_failure(monkeypatch):
    monkeypatch.setattr(rag_search, "bm25", lambda *a, **kw: [])
    result = rag_search.search("unmatched", [row()], mode="bm25")
    assert result["effective_mode"] == "bm25" and result["results"] == []


def test_blank_input_and_invalid_k_never_connect(monkeypatch):
    from api import rag_retrieval
    monkeypatch.setattr(rag_retrieval, "LexicalIndex", lambda: pytest.fail("unexpected connection"))
    assert rag_retrieval.retrieve("", [row()]) == []
    assert rag_retrieval.retrieve("query", []) == []
    assert rag_retrieval.tokenize("") == []
    with pytest.raises(ValueError): rag_retrieval.retrieve("", [], top_k=0)


def test_unknown_typed_errors_are_sanitized():
    assert rag_search.safe_reason(VectorUnavailable("PRIVATE BODY"), "vector") == "vector_backend_failure"
    assert rag_search.safe_reason(LexicalUnavailable("password=SECRET"), "lexical") == "lexical_backend_failure"


def test_worker_create_follows_promoted_alias_without_creating_default_index(monkeypatch):
    calls=[]
    target="haedap-lexical-rebuilt"
    def respond(request):
        calls.append(request.url.path)
        return httpx.Response(200,json={target:{"mappings":{"_meta":{"fingerprint":fingerprint()}}}})
    ix=LexicalIndex(client=httpx.Client(base_url="http://test",transport=httpx.MockTransport(respond)))
    assert ix.create()==target
    assert calls==["/haedap-lexical/_mapping"]


def test_alias_promotion_replays_current_documents_and_tombstones(monkeypatch):
    from scripts import lexical_index
    seen=[]
    class Store:
        def all(self,query):
            assert "UNION SELECT document_id AS id FROM rag_lexical_jobs" in query
            return [{"id":"current"},{"id":"deleted"}]
    monkeypatch.setattr(lexical_index,"enqueue",lambda store,doc:seen.append(doc))
    assert lexical_index.reconcile_after_promotion(Store())==2
    assert seen==["current","deleted"]


def test_real_nori_language_negation_numbers_and_aliases(lexical_index):
    ix = lexical_index
    tokens = ix.analyze("선급이 자동으로 정지되는 경우는? 연료를 연료의 검사하지 않는다.")
    assert {"선급", "자동", "정지", "경우", "연료", "않"} <= set(tokens)
    assert not {"으로", "되는", "를", "의"} & set(tokens)
    tokens = ix.analyze("the fuel must not exceed 0.50% and 5 m. 901.1 없다.")
    assert {"fuel", "not", "0.50", "5", "m", "901.1", "없"} <= set(tokens)
    assert not {"the", "and"} & set(tokens)
    assert "평형수" in ix.query_tokens("ballast water inspection")
    assert "평형수" not in ix.query_tokens("ballast pump water")
    assert "연료" not in ix.query_tokens("refuelling")


def test_real_search_partial_readiness_prefilter_global_statistics(lexical_index):
    ix = lexical_index
    public, private, pending = row(), row("private", "선급 선급 선급"), row("pending")
    ix.index([public]); ix.verify([public], publish=True)
    before = ix.search("선급", [public])[0]["score"]
    ix.index([private])
    ix.verify([public, private], publish=True)
    diagnostics = {}
    hits = ix.search("선급", [public, pending], diagnostics=diagnostics)
    assert [r["id"] for r in hits] == [public["id"]]
    assert diagnostics["status"] == "partial" and diagnostics["ready_chunks"] == 1
    assert all(r["id"] != private["id"] for r in hits)
    assert hits[0]["score"] != before  # Accepted global corpus IDF, filtered hits.
    assert ix.search("nonexistentword", [public]) == []
    with pytest.raises(LexicalUnavailable, match="lexical_no_ready_documents"):
        ix.search("선급", [pending])


def test_real_idempotence_content_change_partial_and_repair(lexical_index):
    ix = lexical_index
    a,b = row(doc="doc"),row("b",doc="doc")
    assert ix.index([a]) == 1 and ix.index([a]) == 0
    assert ix.verify([a,b], publish=True)["missing_chunks"] == 1
    with pytest.raises(LexicalUnavailable):
        ix.search("선급", [a,b])
    ix.index([b]); ix.verify([a,b],publish=True)
    changed = {**a,"text":"평형수 처리"}
    with pytest.raises(LexicalUnavailable):
        ix.search("평형수", [changed,b])
    ix.index([changed]); ix.verify([changed,b],publish=True)
    # Late old certification cannot certify the new snapshot by accident.
    ix.verify([a,b],publish=True)
    assert ix.search("평형수",[changed,b])[0]["id"] == "a"
    ix.request("DELETE",f"/{ix.name}/_doc/{record_id(changed)}?refresh=true")
    assert ix.verify([changed,b],publish=True)["missing_chunks"] == 1
    with pytest.raises(LexicalUnavailable): ix.search("평형수",[changed,b])
    ix.index([changed]); ix.verify([changed,b],publish=True)
    assert ix.search("평형수",[changed,b])


def test_real_storage_replacement_contract_and_no_search_writes(lexical_index, monkeypatch):
    ix=lexical_index; a=row()
    ix.index([a]); ix.verify([a],publish=True)
    calls=[]; request=ix.request
    def tracked(method,path,*args,**kwargs):
        calls.append((method,path))
        return request(method,path,*args,**kwargs)
    monkeypatch.setattr(ix,"request",tracked)
    ix.search("선급",[a])
    assert not any(method in {"PUT","DELETE"} or "_bulk" in path for method,path in calls)
    assert sum("_mget" in path for _,path in calls)==1
    assert not any("_doc/" in path for _,path in calls)
    ix.request("DELETE",f"/{ix.name}"); ix.create()
    with pytest.raises(LexicalUnavailable,match="lexical_no_ready_documents"): ix.search("선급",[a])
    ix.request("PUT",f"/{ix.name}/_mapping", {"_meta":{"fingerprint":"old-analysis"}})
    with pytest.raises(LexicalUnavailable,match="lexical_contract_mismatch"): ix.search("선급",[a])
