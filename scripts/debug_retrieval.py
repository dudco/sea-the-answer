"""Read-only comparison of BM25, vector and RRF over the SAME authorized corpus."""
from __future__ import annotations

import argparse
import json
import os
import sys
from time import perf_counter

try:
    from .rag_index import ROOT, add_filters, filter_options, load_candidates, positive_int
except ImportError:
    from rag_index import ROOT, add_filters, filter_options, load_candidates, positive_int
from dotenv import load_dotenv
from api.rag_search import search


def compare(query, candidates, top_k=5, vector_index=None):
    report = {"query": query, "corpus_size": len(candidates), "methods": {}}
    for mode in ("bm25", "vector", "hybrid"):
        start = perf_counter()
        result = search(query, candidates, top_k, mode=mode, vector_index=vector_index)
        report["methods"][mode] = {**result, "seconds": round(perf_counter() - start, 4),
            "results": [{"rank": rank, **{key: row.get(key) for key in
                        ("id", "document_id", "title", "page", "heading", "score")}}
                        for rank, row in enumerate(result["results"], 1)]}
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--top-k", type=positive_int, default=5)
    add_filters(parser)
    args = parser.parse_args(argv)
    if not args.query.strip() or len(args.query) > 2000:
        parser.error("query must contain 1..2000 characters")
    load_dotenv(ROOT / ".env", override=False)
    try:
        start = perf_counter()
        rows = load_candidates(os.getenv("DATABASE_URL", ""), **filter_options(args))
        db_seconds = perf_counter() - start
        report = compare(args.query, rows, args.top_k)
        report["db_seconds"] = round(db_seconds, 4)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception:
        print("Comparison failed. Check DB, scope and settings; no secrets printed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
