"""Hybrid web retrieval with independent lexical/vector availability."""
import logging
import os

from .errors import ApiError
from .rag_embeddings import VectorUnavailable
from .rag_hybrid import rrf
from .rag_lexical import LexicalUnavailable, coverage as lexical_coverage
from .rag_readiness import coverage
from .rag_retrieval import retrieve as bm25

logger = logging.getLogger(__name__)
SAFE_REASONS = frozenset({
    "candidate_snapshot_mismatch", "index_contract_mismatch", "index_not_ready",
    "index_result_incomplete", "index_result_stale", "index_scope_mismatch", "index_verification_failed",
    "invalid_embedding", "model_contract_mismatch", "model_not_prepared", "no_ready_documents",
    "passage_too_long", "query_too_long", "index_incomplete_or_stale",
    "invalid_lexical_configuration", "lexical_bulk_failure", "lexical_backend_failure",
    "lexical_index_missing", "lexical_contract_mismatch", "lexical_analysis_mismatch",
    "lexical_verification_failed", "lexical_snapshot_mismatch", "lexical_no_ready_documents",
    "lexical_partial_failure"})


def safe_reason(exc, engine):
    return str(exc) if isinstance(exc, (LexicalUnavailable, VectorUnavailable)) and str(exc) in SAFE_REASONS else f"{engine}_backend_failure"


def search(query, chunks, top_k=5, *, mode=None, vector_index=None, complete_chunks=None):
    if type(top_k) is not int or not 1 <= top_k <= 1000:
        raise ValueError("top_k must be 1..1000")
    requested = mode or "hybrid"
    if requested not in {"bm25", "vector", "hybrid"}:
        raise ValueError("invalid retrieval mode")
    report = {"requested_mode": requested, "effective_mode": requested, "fallback_reason": None,
              "coverage": coverage(chunks), "lexical_coverage": lexical_coverage(chunks), "errors": {}}
    if not chunks or not query.strip():
        return {**report, "results": []}
    try:
        count = max(top_k, int(os.getenv("HAEDAP_RAG_CANDIDATES", "30")))
        k = int(os.getenv("HAEDAP_RRF_K", "60"))
        if not 1 <= count <= 1000 or k < 1:
            raise ValueError
    except ValueError:
        return {**report, "effective_mode": "unavailable", "fallback_reason": "invalid_configuration", "results": []}
    lexical, vectors = None, None
    # Explicit modes diagnose their engine. Preserve vector-to-BM25 fallback.
    if requested != "vector":
        try:
            lexical = bm25(query, chunks, count, diagnostics=report["lexical_coverage"], complete_chunks=complete_chunks)
        except Exception as exc:
            report["errors"]["bm25"] = safe_reason(exc, "lexical")
    if requested != "bm25":
        try:
            if vector_index is None:
                from .rag_vector import VectorIndex
                vector_index = VectorIndex()
            vectors = vector_index.search(query, chunks, count, diagnostics=report["coverage"], complete_chunks=complete_chunks)
        except Exception as exc:
            report["errors"]["vector"] = safe_reason(exc, "vector")
            report["coverage"]["status"] = "fallback"
            if requested == "vector":
                try:
                    lexical = bm25(query, chunks, count, diagnostics=report["lexical_coverage"], complete_chunks=complete_chunks)
                except Exception as error:
                    report["errors"]["bm25"] = safe_reason(error, "lexical")
    if lexical is not None and vectors is not None:
        results = rrf([lexical, vectors], top_k=top_k, k=k)
    elif lexical is not None:
        report["effective_mode"], results = "bm25", lexical[:top_k]
    elif vectors is not None:
        report["effective_mode"], results = "vector", vectors[:top_k]
    else:
        report["effective_mode"], results = "unavailable", []
    if report["errors"]:
        report["fallback_reason"] = next(iter(report["errors"].values()))
        logger.warning("rag_fallback requested=%s effective=%s reason=%s engines=%s", requested,
                       report["effective_mode"], report["fallback_reason"], report["errors"])
    for engine, info in (("bm25", report["lexical_coverage"]), ("vector", report["coverage"])):
        if info["status"] == "partial":
            logger.info("rag_partial engine=%s ready_documents=%s allowed_documents=%s", engine,
                        info["ready_documents"], info["allowed_documents"])
    return {**report, "results": results}


def retrieve(query, chunks, top_k=5):
    result = search(query, chunks, top_k, mode="hybrid")
    if result["effective_mode"] == "unavailable":
        raise ApiError(503, "SEARCH_UNAVAILABLE", "검색 색인이 준비되지 않았거나 검색 서비스에 연결할 수 없습니다.")
    return result["results"]
