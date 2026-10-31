"""Small synthetic fixtures: ranking, tokenization and the store's access boundary."""

from copy import deepcopy
from datetime import date
import math
import unicodedata

import pytest

from api.errors import ApiError
from api.rag_retrieval import query_tokens, retrieve, tokenize
from api.store.documents import DocumentStore


def chunk(identifier, content="", **fields):
    return {"id": identifier, "document_id": "doc-" + identifier, "title": "",
            "reference": "", "heading": "", "text": content, "page": 7,
            "kind": "onboard", "url": None, "version": "1", "hash": "synthetic",
            "reviewed_at": date(2026, 10, 14), "meta": {"scope": "all", "status": "active"},
            **fields}


def test_tokenizer_normalizes_mixed_language_and_retains_frequency():
    assert tokenize("ＦＵＥＬ fuel / IMO-2020 § A 1") == ["fuel", "fuel", "imo", "2020", "1"]
    assert tokenize("연료를") == ["연료"]
    assert tokenize(unicodedata.normalize("NFD", "연료를")) == tokenize("연료를")
    assert tokenize("!? \n") == []


def test_kiwi_particles_endings_compounds_and_no_artificial_bigrams():
    tokens = tokenize("선급이 자동으로 정지되는 경우는? 평형수의 검사를 실시한다.")
    assert {"선급", "자동", "정지", "경우", "평형수", "검사"} <= set(tokens)
    assert not {"으로", "동으", "되는", "형수", "선", "급"} & set(tokens)
    assert tokenize("연료를 연료의") == ["연료", "연료"]


def test_stopwords_keep_negation_thresholds_units_and_references():
    tokens = tokenize("the fuel must not exceed 0.50% and 5 m. 901.1 적용하지 않는다. 허용되지 않고 없다.")
    assert {"fuel", "not", "0.50", "5", "m", "901.1", "적용", "않", "없"} <= set(tokens)
    assert not {"the", "and", "지", "고"} & set(tokens)
    assert query_tokens("the and 및 또는") == []


@pytest.mark.parametrize(("query", "content"), [
    ("평형수의 검사", "ballast water inspection"),
    ("heavy deck cargo", "중량 갑판화물 강화"),
    ("중량 갑판 화물", "heavy deck cargoes strengthening"),
    ("선급이 정지되는 기준", "suspension of class criteria"),
    ("흘수", "draught requirements"),
])
def test_maritime_aliases_match_foreign_language_documents(query, content):
    corpus = [chunk("target", content)] + [chunk(str(i), "galley cooking") for i in range(5)]
    assert retrieve(query, corpus)[0]["id"] == "target"


def test_expansion_uses_whole_terms_and_phrases_not_substrings_or_cascades():
    assert "연료" not in query_tokens("refuelling")
    assert "cii" not in query_tokens("carbon steel intensity")
    assert "평형수" not in query_tokens("ballast pump water")
    assert "cii" in query_tokens("carbon intensity")


def test_grammatical_overlap_no_longer_matches_unrelated_document():
    corpus = [chunk("target", "선급이 자동으로 정지된다."),
              chunk("unrelated", "갑자기 수동으로 변경된다.")]
    assert [r["id"] for r in retrieve("선급이 자동으로 정지되는 경우는?", corpus)] == ["target"]


def test_case_word_is_searchable_in_query_and_corpus():
    from api.rag_retrieval import chunk_tokens
    source = chunk("case", "검사를 생략하는 경우에는 별도의 승인이 필요하다.")
    assert "경우" in query_tokens("어떤 경우에 검사를 생략하나?")
    assert "경우" in chunk_tokens(source)
    assert retrieve("경우", [source])[0]["id"] == "case"


@pytest.mark.parametrize(("query", "focused", "broad", "unrelated"), [
    ("ballast inspection", "ballast inspection ballast inspection",
     "ballast inspection " + "maintenance navigation records " * 40, "galley cooking"),
    ("평형수 검사", "평형수 검사 평형수 검사",
     "평형수 검사 " + "운항 항로 기록 " * 40, "식당 조리"),
])
def test_relevant_focused_passage_ranks_above_long_incidental_mention(query, focused, broad, unrelated):
    # Literal counting ties these two matches. BM25 accounts for TF and length.
    corpus = [chunk("broad", broad), chunk("focused", focused)]
    corpus += [chunk(str(i), unrelated) for i in range(6)]
    results = retrieve(query, corpus)
    assert [r["id"] for r in results] == ["focused", "broad"]
    assert results[0]["score"] > results[1]["score"] > 0


@pytest.mark.parametrize(("query", "content"), [
    ("fuel", "연료를 기록한다"), ("연료", "Fuel consumption records"),
    ("평형수", "평형수의 처리 절차"), ("CII", "Carbon intensity requirements"),
])
def test_korean_suffixes_and_existing_bilingual_synonyms(query, content):
    assert [r["id"] for r in retrieve(query, [chunk("match", content)])] == ["match"]


@pytest.mark.parametrize("field", ["title", "reference", "heading", "text"])
def test_all_search_fields_and_original_metadata_are_preserved(field):
    source = chunk("metadata", **{field: "QUARTZTEST"})
    original = deepcopy(source)
    result = retrieve("quartztest", [source])[0]
    assert {k: v for k, v in result.items() if k != "score"} == original
    assert source == original and "score" not in source
    assert isinstance(result["score"], float) and math.isfinite(result["score"])


@pytest.mark.parametrize(("query", "corpus"), [
    ("", [chunk("one", "ballast")]), ("  \n", [chunk("one", "ballast")]),
    ("!!!", [chunk("one", "ballast")]), ("ballast", []),
    ("ballast", [chunk("empty"), chunk("punctuation", "!?")]),
    ("unknown", [chunk("one", "ballast")]),
])
def test_empty_or_unmatched_input_returns_no_evidence(query, corpus):
    assert retrieve(query, corpus) == []


def test_zero_and_negative_scores_do_not_hide_matching_small_corpus():
    singleton = retrieve("ballast", [chunk("one", "ballast")])
    assert singleton[0]["score"] < 0
    pair = retrieve("ballast", [chunk("unrelated", "galley"), chunk("match", "ballast")])
    assert [r["id"] for r in pair] == ["match"]
    assert pair[0]["score"] == 0
    assert retrieve("ballast", [chunk("empty"), chunk("match", "ballast")])[0]["id"] == "match"


def test_top_k_ties_and_repeated_query_are_deterministic():
    corpus = [chunk(str(i), "ballast") for i in range(7)]
    assert [r["id"] for r in retrieve("ballast", corpus)] == [str(i) for i in range(5)]
    assert len(retrieve("ballast", corpus, top_k=2)) == 2
    assert retrieve("ballast ballast", corpus) == retrieve("ballast", corpus)


@pytest.mark.parametrize("top_k", [0, -1, True, 1.5, "5"])
def test_invalid_top_k(top_k):
    with pytest.raises(ValueError):
        retrieve("ballast", [], top_k=top_k)


@pytest.mark.parametrize(("role", "kind", "expected"), [
    ("guest", "all", ["public", "official"]),
    ("operator", "all", ["public", "operator", "official"]),
    ("admin", "all", ["public", "operator", "admin", "official"]),
    ("admin", "imo", ["official"]),
    ("admin", "manual", ["public", "operator", "admin"]),
])
def test_store_filters_before_bm25_and_preserves_response(monkeypatch, role, kind, expected):
    rows = [chunk("public", "ballast", meta=None),
            chunk("operator", "ballast", meta={"scope": "operator", "status": "active"}),
            chunk("admin", "ballast", meta={"scope": "admin", "status": "active"}),
            chunk("retired", "ballast", meta={"scope": "all", "status": "retired"}),
            chunk("deleted", "ballast", meta={"scope": "all", "status": "deleted"}),
            chunk("official", "ballast", kind="official-summary")]
    original = deepcopy(rows)
    seen = []

    def authorized_retrieve(query, candidates, top_k):
        seen.extend(r["id"] for r in candidates)
        return retrieve(query, candidates, top_k)

    def read(sql, _params=()):
        assert "WHERE d.active=true" in sql
        return rows

    monkeypatch.setattr("api.store.documents.retrieve", authorized_retrieve)
    store = DocumentStore()
    store.all = read
    result = store.search({"role": role}, "ballast", kind)
    assert seen == expected  # Unauthorized rows must not even affect IDF.
    assert [r["id"] for r in result] == expected
    assert all(set(r) == set(rows[0]) for r in result)
    assert all(r["reviewed_at"] == "2026-10-14" and r["page"] == 7 for r in result)
    assert rows == original


def test_store_keeps_existing_question_and_filter_validation():
    store = DocumentStore()
    for query, kind in [("", "all"), ("x" * 2001, "all"), ("fuel", "invalid")]:
        with pytest.raises(ApiError):
            store.search({"role": "guest"}, query, kind)


def test_selected_documents_are_sql_filtered_before_bm25(monkeypatch):
    selected = chunk("selected", "ballast")
    store = DocumentStore()
    store.allowed_document_ids = lambda user: [selected["document_id"], "doc-other"]
    seen = []

    def read(sql, params):
        assert "WHERE d.active=true AND d.id = ANY(%s)" in sql
        assert params == ([selected["document_id"]],)
        return [selected]

    def scoped_retrieve(query, candidates, top_k):
        seen.extend(c["document_id"] for c in candidates)
        return retrieve(query, candidates, top_k)

    store.all = read
    monkeypatch.setattr("api.store.documents.retrieve", scoped_retrieve)
    results = store.search({"role": "guest"}, "ballast", document_ids=[selected["document_id"]])
    assert seen == [selected["document_id"]]
    assert results[0]["id"] == selected["id"] and "score" not in results[0]


@pytest.mark.parametrize("document_ids", [[], ["doc-a", "doc-a"], [""], [1], "doc-a",
    [str(i) for i in range(21)], ["inaccessible"]])
def test_invalid_or_inaccessible_selection_never_reaches_sql_or_bm25(monkeypatch, document_ids):
    store = DocumentStore()
    store.allowed_document_ids = lambda user: ["doc-a"]
    store.all = lambda *args: pytest.fail("Invalid selection reached SQL")
    monkeypatch.setattr("api.store.documents.retrieve", lambda *a, **k: pytest.fail("Invalid selection reached BM25"))
    with pytest.raises(ApiError):
        store.search({"role": "guest"}, "ballast", document_ids=document_ids)
