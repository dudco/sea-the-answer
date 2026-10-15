"""Small synthetic fixtures: ranking, tokenization and the store's access boundary."""

from copy import deepcopy
from datetime import date
import math
import unicodedata

import pytest

from api.errors import ApiError
from api.rag_retrieval import retrieve, tokenize
from api.store.documents import DocumentStore


def chunk(identifier, content="", **fields):
    return {"id": identifier, "document_id": "doc-" + identifier, "title": "",
            "reference": "", "heading": "", "text": content, "page": 7,
            "kind": "onboard", "url": None, "version": "1", "hash": "synthetic",
            "reviewed_at": date(2026, 10, 14), "meta": {"scope": "all", "status": "active"},
            **fields}


def test_tokenizer_normalizes_mixed_language_and_retains_frequency():
    assert tokenize("ＦＵＥＬ fuel / IMO-2020 § A 1") == ["fuel", "fuel", "imo", "2020"]
    assert tokenize("연료를") == ["연료를", "연료", "료를"]
    assert tokenize(unicodedata.normalize("NFD", "연료를")) == tokenize("연료를")
    assert tokenize("!? \n") == []


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
