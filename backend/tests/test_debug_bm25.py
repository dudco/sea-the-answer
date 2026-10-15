"""Diagnostics use production tokenization/ranking; fixtures contain no PDFs."""

from copy import deepcopy
import json

import psycopg
import pytest

from api.errors import ApiError
from api.rag_retrieval import chunk_tokens, query_tokens, retrieve
from api.store.documents import DocumentStore
from scripts import debug_bm25 as debug


def chunk(identifier, content="", **fields):
    return {"id": identifier, "document_id": "doc-" + identifier,
            "title": "Synthetic manual", "reference": "", "heading": "Checks",
            "text": content, "page": 7, "kind": "onboard", "reviewed_at": "2026-10-15",
            "meta": {"status": "active", "scope": "all"}, **fields}


@pytest.mark.parametrize("query", ["heavy deck cargo", "선급이 자동으로 정지되는 경우는?", "fuel"])
def test_report_preserves_production_ranking_scores_and_metadata(query):
    corpus = [chunk("one", "heavy deck cargo 선급 정지"),
              chunk("two", "선급이 자동으로 정지되는 경우 연료를 확인한다."),
              chunk("three", "galley equipment"), chunk("four", "galley equipment")]
    original = deepcopy(corpus)
    report = debug.build_report(query, corpus, top_k=2, preview_chars=12)
    expected = retrieve(query, corpus, top_k=2)
    assert report["query"] == query
    assert report["query_tokens"] == query_tokens(query)
    assert report["corpus_size"] == len(corpus)
    assert len(report["results"]) == len(expected) > 0
    for rank, (actual, source) in enumerate(zip(report["results"], expected), 1):
        assert actual["rank"] == rank
        assert actual["chunk_id"] == source["id"]
        assert actual["score"] == source["score"]
        for field in ("document_id", "title", "page", "heading"):
            assert actual[field] == source[field]
        assert actual["matched_tokens"] == [t for t in query_tokens(query) if t in chunk_tokens(source)]
        assert len(actual["preview"]) <= 13  # Optional truncation marker.
    assert corpus == original


@pytest.mark.parametrize("field", ["title", "reference", "heading", "text"])
def test_matches_include_all_actual_search_fields_and_expanded_synonyms(field):
    report = debug.build_report("fuel", [chunk("one", **{field: "연료"})])
    assert report["query_tokens"] == ["fuel", "연료"]
    assert report["results"][0]["matched_tokens"] == ["연료"]
    assert "contributions" not in report["results"][0]


def test_document_filters_narrow_corpus_before_scoring_and_are_combined():
    corpus = [chunk("a", "ballast", title="Alpha manual"), chunk("b", "ballast", title="Beta manual")]
    report = debug.build_report("ballast", corpus, document_title="ALPHA", document_id="doc-a")
    assert report["corpus_size"] == 1
    assert report["results"][0]["score"] == retrieve("ballast", corpus[:1])[0]["score"] < 0
    assert debug.build_report("ballast", corpus, document_title="Beta", document_id="doc-a")["results"] == []
    assert debug.build_report("ballast", corpus, document_id="missing")["corpus_size"] == 0


@pytest.mark.parametrize(("query", "corpus"), [("", [chunk("a", "ballast")]),
    ("!", [chunk("a", "ballast")]), ("ballast", []), ("absent", [chunk("a", "ballast")])])
def test_no_matches(query, corpus):
    assert debug.build_report(query, corpus)["results"] == []


def test_zero_score_ties_missing_page_and_preview_are_preserved():
    corpus = [chunk("a", "ballast\ninspection", page=None), chunk("b", "galley checks")]
    row = debug.build_report("ballast", corpus, preview_chars=0)["results"][0]
    assert row["score"] == 0 and row["page"] is None and row["preview"] == ""
    assert debug.build_report("ballast", corpus)["results"][0]["preview"] == "ballast inspection"
    tied = [chunk(str(i), "ballast") for i in range(7)]
    assert [r["chunk_id"] for r in debug.build_report("ballast", tied, top_k=3)["results"]] == ["0", "1", "2"]


@pytest.fixture
def fake_store(monkeypatch):
    events = []

    class FakeStore(DocumentStore):
        def __init__(self, _dsn): pass
        def __enter__(self): return self
        def __exit__(self, *args): events.append("closed")
        def run(self, sql):
            assert sql == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            events.append("read-only")
        def one(self, sql, params):
            assert events == ["read-only"]
            assert "active=true" in sql and "password" not in sql
            assert params == ("tester",)
            return {"id": "test-user", "role": "operator"}
        def all(self, sql):
            assert events == ["read-only"]
            assert "WHERE d.active=true ORDER BY d.id,c.position" in sql
            return [chunk("all", "ballast"),
                    chunk("operator", "ballast", meta={"scope": "operator", "status": "active"}),
                    chunk("admin", "ballast", meta={"scope": "admin", "status": "active"}),
                    chunk("retired", "ballast", meta={"scope": "all", "status": "retired"}),
                    chunk("deleted", "ballast", meta={"scope": "all", "status": "deleted"})]

    monkeypatch.setattr(debug, "DebugStore", FakeStore)
    return FakeStore, events


@pytest.mark.parametrize(("username", "expected"), [(None, ["all"]), ("tester", ["all", "operator"])])
def test_read_only_first_and_shared_access_filter(fake_store, username, expected):
    _, events = fake_store
    report = debug.load_report("not-a-real-dsn", "ballast", username=username)
    assert [r["chunk_id"] for r in report["results"]] == expected
    assert report["corpus_size"] == len(expected)
    assert events == ["read-only", "closed"]


def test_unknown_or_inactive_account_is_not_treated_as_guest(fake_store, monkeypatch):
    store, events = fake_store
    monkeypatch.setattr(store, "one", lambda *args: None)
    with pytest.raises(ApiError):
        debug.load_report("not-a-real-dsn", "ballast", username="missing")
    assert events == ["read-only", "closed"]


def test_cli_json_text_and_env_precedence(fake_store, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "environment-value")
    def dotenv(_path, override):
        assert override is False
    monkeypatch.setattr(debug, "load_dotenv", dotenv)
    assert debug.main(["ballast", "--top-k", "1", "--preview-chars", "0", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["top_k"] == 1 and report["results"][0]["preview"] == ""
    output = debug.format_report(report)
    assert "Rank 1" in output and "NOT per-token score contributions" in output
    assert "chunk_id: all" in output and "page: 7" in output
    report["results"] = []
    assert "No matching chunks" in debug.format_report(report)


@pytest.mark.parametrize("args", [["fuel", "--top-k", "0"], ["fuel", "--top-k", "x"],
    ["fuel", "--preview-chars", "-1"], ["fuel", "--kind", "bad"], ["x" * 2001]])
def test_bad_options_fail_before_db(monkeypatch, args):
    monkeypatch.setattr(debug, "load_report", lambda *a, **k: pytest.fail("DB should not be opened"))
    with pytest.raises(SystemExit) as exc:
        debug.main(args)
    assert exc.value.code == 2


def test_db_errors_do_not_leak_connection_details(monkeypatch, capsys):
    monkeypatch.setattr(debug, "load_dotenv", lambda *a, **k: None)
    def broken(*args, **kwargs):
        raise psycopg.OperationalError("secret-user:secret-password@secret-host")
    monkeypatch.setattr(debug, "load_report", broken)
    assert debug.main(["fuel"]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "secret" not in captured.err
    assert "DB 조회 실패" in captured.err
