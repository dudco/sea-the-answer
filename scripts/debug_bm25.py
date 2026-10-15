"""Read-only BM25 diagnostics over the app's PostgreSQL chunks (no HTTP/LLM)."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

# Direct script execution works both in the repository and in /app/scripts
# mounted next to the Docker image's /app/api package.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" if (ROOT / "backend/api").is_dir() else ROOT))

import psycopg
from dotenv import load_dotenv

from api.errors import ApiError, require
from api.rag_retrieval import chunk_tokens, query_tokens, retrieve
from api.store.base import Database
from api.store.documents import DocumentStore


class DebugStore(Database, DocumentStore):
    """Only connection/query helpers and document operations; never bootstrap."""


def build_report(query: str, candidates: list[dict], *, top_k: int = 5,
                 document_id: str | None = None, document_title: str | None = None,
                 preview_chars: int = 240) -> dict:
    """Candidates MUST already be permission-filtered, as in retrieve().

    Matched tokens are set overlap, not score attribution. A future attribution
    helper should receive the SAME BM25 index and ask get_scores([token]); it
    must not rebuild an index on top-k results or reproduce the BM25 formula.
    """
    if type(preview_chars) is not int or preview_chars < 0:
        raise ValueError("preview_chars must be a non-negative integer")
    corpus = [row for row in candidates
              if (document_id is None or row["document_id"] == document_id)
              and (document_title is None or document_title.casefold() in row["title"].casefold())]
    terms = query_tokens(query)
    results = []
    # The production function owns matching, scoring, ordering and top-k.
    for rank, row in enumerate(retrieve(query, corpus, top_k=top_k), 1):
        tokens = set(chunk_tokens(row))
        body = " ".join(row["text"].split())
        preview = (body[:preview_chars] + ("…" if len(body) > preview_chars else "")) if preview_chars else ""
        results.append({"rank": rank, "chunk_id": row["id"],
                        "document_id": row["document_id"], "title": row["title"],
                        "page": row.get("page"), "heading": row["heading"],
                        "score": row["score"],
                        "matched_tokens": [term for term in terms if term in tokens],
                        "preview": preview})
    return {"query": query, "query_tokens": terms, "corpus_size": len(corpus),
            "top_k": top_k, "filters": {"document_id": document_id, "document_title": document_title},
            "results": results}


def load_report(dsn: str, query: str, *, username: str | None = None,
                kind: str = "all", **options) -> dict:
    with DebugStore(dsn) as store:
        # First command: PostgreSQL itself rejects writes in this transaction.
        store.run("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        user = {"role": "guest"}
        if username is not None:
            user = store.one("SELECT id,role FROM users WHERE username=%s AND active=true", (username,))
            require(bool(user), "활성 사용자 계정을 찾을 수 없습니다.")
        report = build_report(query, store.search_candidates(user, kind), **options)
        report["role"] = user["role"]
        report["filters"]["kind"] = kind
        return report


def format_report(report: dict) -> str:
    lines = [f"Query: {report['query']}", "Query tokens:",
             json.dumps(report["query_tokens"], ensure_ascii=False),
             f"Corpus: {report['corpus_size']} chunks | Role: {report['role']} | Top-K: {report['top_k']}",
             "Filters: " + json.dumps(report["filters"], ensure_ascii=False),
             "Matched tokens: title/reference/heading/text overlap; NOT per-token score contributions.",
             "Scores depend on the filtered corpus; zero/negative scores are valid."]
    for row in report["results"]:
        lines.extend(["", f"Rank {row['rank']}", f"document: {row['title']}",
                      f"document_id: {row['document_id']}", f"chunk_id: {row['chunk_id']}",
                      f"page: {row['page']}", f"heading: {row['heading']}", f"score: {row['score']}",
                      "matched tokens: " + json.dumps(row["matched_tokens"], ensure_ascii=False),
                      f"text: {row['preview']}"])
    if not report["results"]:
        lines.append("\nNo matching chunks (check tokens, filters and access scope).")
    return "\n".join(lines)


def positive_int(value: str) -> int:
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


def nonnegative_int(value: str) -> int:
    result = int(value)
    if result < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--top-k", type=positive_int, default=5)
    parser.add_argument("--document-id", help="Exact active revision ID, not logical ID")
    parser.add_argument("--document-title", help="Case-insensitive title substring (narrows BM25 corpus)")
    parser.add_argument("--kind", choices=("all", "imo", "manual"), default="all")
    parser.add_argument("--username", help="Simulate an existing active account's scope; default: guest")
    parser.add_argument("--preview-chars", type=nonnegative_int, default=240, help="0 hides body text")
    parser.add_argument("--json", action="store_true", help="Machine-readable report with full float scores")
    args = parser.parse_args(argv)
    if len(args.query) > 2000:
        parser.error("query must contain at most 2000 characters")
    # Docker/environment settings win over the optional host .env. Never print DSN.
    load_dotenv(ROOT / ".env", override=False)
    try:
        report = load_report(os.getenv("DATABASE_URL", ""), args.query,
                             username=args.username, kind=args.kind, top_k=args.top_k,
                             document_id=args.document_id, document_title=args.document_title,
                             preview_chars=args.preview_chars)
    except ApiError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1
    except psycopg.Error:
        print("Error: DB 조회 실패. 연결 설정·스키마·읽기 권한을 확인하세요. 접속 정보는 출력하지 않습니다.", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else format_report(report))
    return 0


if __name__ == "__main__":
    # Korean output is also readable when redirected to a file on Windows.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
