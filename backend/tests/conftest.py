"""Explicit opt-in engine fixtures; never connect to application services."""
import os
from uuid import uuid4

import httpx
import pytest


@pytest.fixture
def lexical_index():
    from api.rag_lexical import LexicalIndex
    url = os.getenv("HAEDAP_TEST_OPENSEARCH_URL")
    if not url:
        pytest.skip("HAEDAP_TEST_OPENSEARCH_URL not configured (isolated OpenSearch/Nori required)")
    client = httpx.Client(base_url=url, timeout=30, trust_env=False)
    index = LexicalIndex(index="haedap-lexical-test-" + uuid4().hex, client=client)
    index.create()
    index.request("PUT", f"/{index.name}/_settings", {"index": {"refresh_interval": "10ms"}})
    try:
        yield index
    finally:
        index.request("DELETE", f"/{index.name}", missing=True)
        client.close()


@pytest.fixture
def prepared_lexical(lexical_index, monkeypatch):
    """Legacy ranking/CLI regressions explicitly prepare synthetic inputs.

    Preparation belongs ONLY to this fixture, never production retrieval.
    Tests of readiness/missing indexes use lexical_index directly instead.
    """
    from api import rag_retrieval
    original = lexical_index.search

    def prepared(query, rows, top_k=5, **kwargs):
        complete = kwargs.get("complete_chunks") or rows
        if rows:
            lexical_index.index(complete)
            lexical_index.verify(complete, publish=True)
        return original(query, rows, top_k, **kwargs)

    monkeypatch.setattr(lexical_index, "search", prepared)
    monkeypatch.setattr(rag_retrieval, "LexicalIndex", lambda: lexical_index)
    return lexical_index


@pytest.fixture
def stub_lexical(monkeypatch):
    """Vector orchestration tests isolate lexical service, not its ranking."""
    def retrieve(q, rows, top_k=5, **kwargs):
        return [{**r, "score": 1.0} for r in rows[:top_k]]
    monkeypatch.setattr("api.rag_search.bm25", retrieve)
    return retrieve
