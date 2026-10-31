"""Durable RAG jobs: python -m api.rag_worker run|status|enqueue|retry."""
from __future__ import annotations

import argparse
import json
import os
import signal
from threading import Event

from .rag_jobs import enqueue, fingerprint, process_one
from .store.base import Database


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def manage(store, command, *, document_id=None, limit=100, apply=False):
    fp = fingerprint()
    if command == "status":
        return store.all("""SELECT j.id,j.document_id,j.fingerprint,j.generation,j.state,j.attempts,j.error_code,
            j.next_attempt_at,j.updated_at,(j.fingerprint=%s) AS current_model,d.active AS active_revision,
            COALESCE(m.body->>'status','active') AS document_status
            FROM rag_index_jobs j JOIN documents d ON d.id=j.document_id
            LEFT JOIN document_meta m ON m.id=d.id
            WHERE (%s::text IS NULL OR j.document_id=%s) ORDER BY j.updated_at DESC LIMIT %s""",
            (fp, document_id, document_id, limit))
    if command == "enqueue":
        rows = store.all("""SELECT d.id FROM documents d LEFT JOIN document_meta m ON m.id=d.id
            WHERE d.active AND COALESCE(m.body->>'status','active')='active'
            AND (%s::text IS NULL OR d.id=%s) ORDER BY d.id LIMIT %s""", (document_id, document_id, limit))
        if apply:
            for row in rows:
                enqueue(store, row["id"], fp)
    else:
        rows = store.all("""SELECT id FROM rag_index_jobs WHERE fingerprint=%s AND state='failed'
            AND (%s::text IS NULL OR document_id=%s) ORDER BY id LIMIT %s""", (fp, document_id, document_id, limit))
        if apply:
            store.run("""UPDATE rag_index_jobs SET state='pending',attempts=0,generation=generation+1,
                claim_token=NULL,error_code=NULL,next_attempt_at=now(),updated_at=now()
                WHERE id=ANY(%s) AND state='failed'""", ([row["id"] for row in rows],))
    return {"documents": len(rows), "applied": apply, "fingerprint": fp}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "status", "enqueue", "retry"))
    parser.add_argument("--document-id")
    parser.add_argument("--limit", type=positive, default=100)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--once", action="store_true", help="Process at most one job")
    parser.add_argument("--poll-seconds", type=positive, default=5)
    parser.add_argument("--batch-size", type=positive, default=16)
    args = parser.parse_args(argv)
    if args.batch_size > 256:
        parser.error("batch-size must not exceed 256")
    stopped = Event()
    if args.command == "run":
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stopped.set())
    try:
        if args.command != "run":
            with Database(os.getenv("DATABASE_URL", "")) as store:
                result = manage(store, args.command, document_id=args.document_id,
                                limit=args.limit, apply=args.apply)
            print(json.dumps(result, default=str, ensure_ascii=False, indent=2))
            return 0
        while not stopped.is_set():
            try:
                with Database(os.getenv("DATABASE_URL", "")) as store:
                    worked = process_one(store, batch_size=args.batch_size)
                if args.once:
                    print(json.dumps({"processed": worked}))
                    return 0
                if not worked:
                    stopped.wait(args.poll_seconds)
            except Exception:
                print('{"worker_error":"database_or_worker_unavailable"}', flush=True)
                if args.once:
                    return 1
                stopped.wait(args.poll_seconds)
        return 0
    except Exception:
        print('{"error":"job_command_failed"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
