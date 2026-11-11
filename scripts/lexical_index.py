"""OpenSearch prepare/index/verify/promote. Dry-run by default; no source writes."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" if (ROOT / "backend/api").is_dir() else ROOT))

from dotenv import load_dotenv
from api.rag_jobs import chunks, eligible
from api.rag_lexical import LexicalIndex
from api.rag_lexical_jobs import enqueue, process_one
from api.rag_worker import positive
from api.store.base import Database


def reconcile_after_promotion(store):
    """Replay current documents AND deletion tombstones after an alias swap.

    Changes after the verification snapshot may have reached the old index.
    Generation increments fence those jobs and the new claims resolve the alias.
    """
    rows = store.all("SELECT id FROM documents UNION SELECT document_id AS id FROM rag_lexical_jobs ORDER BY id")
    for row in rows:
        enqueue(store, row["id"])
    return len(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "index", "verify", "promote"))
    parser.add_argument("--index", help="Versioned physical index, haedap-lexical-...")
    parser.add_argument("--document-id")
    parser.add_argument("--document-title")
    parser.add_argument("--limit", type=positive, help="Maximum chunks; partial documents are NOT certified")
    parser.add_argument("--batch-size", type=positive, default=100)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true")
    action.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.batch_size > 500:
        parser.error("batch-size must not exceed 500")
    if args.command == "promote" and (not args.index or args.limit or args.document_id or args.document_title):
        parser.error("promote requires --index and a full, unfiltered verification")
    load_dotenv(ROOT / ".env", override=False)
    index = LexicalIndex(index=args.index)
    try:
        if args.command == "prepare":
            print(json.dumps({"dry_run": not args.apply, "index": index.create() if args.apply else index.name}))
            return 0
        with Database(os.getenv("DATABASE_URL", "")) as store:
            store.run("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            docs = store.all("""SELECT d.id FROM documents d LEFT JOIN document_meta m ON m.id=d.id
                WHERE d.active AND COALESCE(m.body->>'status','active')='active'
                AND (%s::text IS NULL OR d.id=%s)
                AND (%s::text IS NULL OR position(lower(%s) in lower(d.title))>0) ORDER BY d.id""",
                (args.document_id, args.document_id, args.document_title, args.document_title))
            selections = []
            remaining = args.limit
            for doc in docs:
                rows = chunks(store, doc["id"])
                take = len(rows) if remaining is None else min(len(rows), remaining)
                if take:
                    selections.append((doc["id"], rows, take))
                if remaining is not None:
                    remaining -= take
                    if not remaining:
                        break
        report = {"dry_run": not args.apply, "documents": len(selections),
                  "chunks": sum(take for _, _, take in selections), "partial_documents": sum(take<len(rows) for _,rows,take in selections)}
        if args.command == "index" and args.apply:
            for doc, rows, take in selections:
                with Database(os.getenv("DATABASE_URL", "")) as store:
                    enqueue(store, doc)
                with Database(os.getenv("DATABASE_URL", "")) as store:
                    process_one(store, document_id=doc, index_factory=lambda: LexicalIndex(index=args.index),
                                batch_size=args.batch_size, limit=take)
            with Database(os.getenv("DATABASE_URL", "")) as store:
                report["jobs"] = store.all("""SELECT document_id,state,error_code FROM rag_lexical_jobs
                    WHERE document_id=ANY(%s) ORDER BY document_id""", ([d for d,_,_ in selections],))
        elif args.command in {"verify", "promote"}:
            report["verification"] = index.verify([r for _, rows, take in selections for r in rows[:take]])
            if args.apply and args.command == "verify":
                # Recovery goes through the same outbox/fencing as the worker.
                for doc, _, _ in selections:
                    with Database(os.getenv("DATABASE_URL", "")) as store:
                        enqueue(store, doc)
                    if args.index:
                        with Database(os.getenv("DATABASE_URL", "")) as store:
                            process_one(store, document_id=doc,
                                        index_factory=lambda: LexicalIndex(index=args.index), batch_size=args.batch_size)
                report["recovery_enqueued"] = len(selections)
            if args.apply and args.command == "promote":
                if report["verification"]["missing_chunks"]:
                    raise RuntimeError("incomplete_index")
                # Certify only by worker; verify readiness as well as records.
                for _, rows, _ in selections:
                    from api.rag_lexical import receipt, receipt_id
                    if index.mget(index.resolve(), [receipt_id(rows)]).get(receipt_id(rows)) != receipt(rows):
                        raise RuntimeError("uncertified_index")
                index.promote()
                report["promoted"] = True
                with Database(os.getenv("DATABASE_URL", "")) as store:
                    report["reconciliation_enqueued"] = reconcile_after_promotion(store)
        print(json.dumps(report, indent=2))
        return 1 if any(j["state"] != "done" for j in report.get("jobs", [])) else 0
    except Exception:
        print('{"error":"lexical_preparation_failed"}', file=sys.stderr)
        return 1
    finally:
        index.close()


if __name__ == "__main__":
    raise SystemExit(main())
