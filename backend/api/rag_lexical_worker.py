"""Durable OpenSearch jobs: run/status/enqueue/retry (independent of Chroma)."""
import argparse
import json
import os
import signal
from threading import Event

from .rag_lexical_jobs import enqueue, process_one
from .rag_worker import positive
from .store.base import Database


def manage(store, command, *, document_id=None, limit=100, apply=False):
    if command == "status":
        return store.all("""SELECT document_id,generation,state,attempts,fingerprint,error_code,
            updated_at,next_attempt_at FROM rag_lexical_jobs
            WHERE (%s::text IS NULL OR document_id=%s) ORDER BY updated_at DESC LIMIT %s""",
            (document_id, document_id, limit))
    if command == "enqueue":
        rows = store.all("""SELECT id FROM
            (SELECT id FROM documents UNION SELECT document_id AS id FROM rag_lexical_jobs) sources
            WHERE (%s::text IS NULL OR id=%s) ORDER BY id LIMIT %s""", (document_id, document_id, limit))
    else:
        rows = store.all("""SELECT document_id AS id FROM rag_lexical_jobs WHERE state='failed'
            AND (%s::text IS NULL OR document_id=%s) ORDER BY document_id LIMIT %s""", (document_id, document_id, limit))
    if apply:
        for row in rows:
            enqueue(store, row["id"])
    return {"documents": len(rows), "applied": apply}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "status", "enqueue", "retry"))
    parser.add_argument("--document-id")
    parser.add_argument("--limit", type=positive, default=100)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--drain", action="store_true", help="Process available jobs, then exit; nonzero if unfinished jobs remain")
    parser.add_argument("--batch-size", type=positive, default=100)
    args = parser.parse_args(argv)
    if args.batch_size > 500:
        parser.error("batch-size must not exceed 500")
    stopped = Event()
    if args.command == "run":
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stopped.set())
    try:
        if args.command != "run":
            with Database(os.getenv("DATABASE_URL", "")) as store:
                result = manage(store, args.command, document_id=args.document_id, limit=args.limit, apply=args.apply)
            print(json.dumps(result, default=str, indent=2))
            return 0
        while not stopped.is_set():
            try:
                with Database(os.getenv("DATABASE_URL", "")) as store:
                    worked = process_one(store, document_id=args.document_id, batch_size=args.batch_size)
                if args.once:
                    print(json.dumps({"processed": worked}))
                    return 0
                if args.drain and not worked:
                    with Database(os.getenv("DATABASE_URL", "")) as store:
                        unfinished = store.one("SELECT count(*) AS n FROM rag_lexical_jobs WHERE state<>'done'")["n"]
                    print(json.dumps({"unfinished": unfinished}))
                    return 1 if unfinished else 0
                if not worked:
                    stopped.wait(5)
            except Exception:
                print('{"worker_error":"lexical_worker_unavailable"}', flush=True)
                if args.once:
                    return 1
                stopped.wait(5)
        return 0
    except Exception:
        print('{"error":"lexical_command_failed"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
