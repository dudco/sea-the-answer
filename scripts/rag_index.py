"""Explicit model preparation and read-only-PG / write-only-index batch preparation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" if (ROOT / "backend/api").is_dir() else ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
from debug_bm25 import DebugStore, positive_int
from api.errors import require


def load_candidates(dsn: str, *, username=None, kind="all", document_id=None,
                    document_title=None, limit=None) -> list[dict]:
    with DebugStore(dsn) as store:
        store.run("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        user = {"role": "guest"}
        if username:
            user = store.one("SELECT id,role FROM users WHERE username=%s AND active=true", (username,))
            require(bool(user), "활성 사용자 계정을 찾을 수 없습니다.")
        rows = store.search_candidates(user, kind, [document_id] if document_id else None)
        rows = [row for row in rows if not document_title or document_title.casefold() in row["title"].casefold()]
        return rows[:limit] if limit else rows


def add_filters(parser):
    parser.add_argument("--username", help="Existing active account; default guest scope")
    parser.add_argument("--kind", choices=("all", "imo", "manual"), default="all")
    parser.add_argument("--document-id", help="Exact active revision ID")
    parser.add_argument("--document-title", help="Case-insensitive title substring")
    parser.add_argument("--limit", type=positive_int, help="Restrict to the first N authorized chunks")


def filter_options(args):
    return {key: getattr(args, key) for key in ("username", "kind", "document_id", "document_title", "limit")}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare", help="Download pinned public model ONLY (about 0.5 GB)")
    index = sub.add_parser("index", help="Default is dry-run; no vector/DB changes")
    add_filters(index)
    action = index.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true")
    action.add_argument("--dry-run", action="store_true")
    index.add_argument("--batch-size", type=positive_int, default=16)
    args = parser.parse_args(argv)
    load_dotenv(ROOT / ".env", override=False)
    start = perf_counter()
    try:
        if args.command == "prepare":
            from api.rag_embeddings import prepare_model
            prepare_model()
            result = {"model_prepared": True}
        else:
            if args.batch_size > 256:
                parser.error("batch-size must not exceed 256")
            rows = load_candidates(os.getenv("DATABASE_URL", ""), **filter_options(args))
            if not args.apply:
                result = {"dry_run": True, "chunks": len(rows),
                          "documents": len({row["document_id"] for row in rows}),
                          "note": "No model/index initialization; no DB writes"}
            else:
                from api.rag_vector import VectorIndex
                result = VectorIndex(create=True).index(rows, args.batch_size)
        result["seconds"] = round(perf_counter() - start, 3)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception:
        print("RAG preparation failed. Check DB/scope, model readiness and Chroma settings. No secrets printed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
