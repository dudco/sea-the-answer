"""Explicit Docker smoke check: synthetic documents in an owned disposable schema.

Run only against the e2e-db service with the baked model and isolated Chroma.
No document text or connection strings are printed.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from api.rag_search import search
from api.rag_vector import VectorIndex
from api.store.base import Database
from api.store.documents import DocumentStore


class Store(Database, DocumentStore):
    pass


def main():
    dsn = os.environ["DATABASE_URL"]
    if conninfo_to_dict(dsn).get("host") != "e2e-db":
        raise RuntimeError("Only the isolated e2e-db service is allowed")
    schema = "auto_index_smoke_" + uuid4().hex
    scoped = make_conninfo(dsn, options=f"-c search_path={schema}")
    env = {**os.environ, "DATABASE_URL": scoped}
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            with psycopg.connect(scoped) as db:
                for name in ("20261013000000_init.sql", "20261029000000_rag_index_jobs.sql"):
                    db.execute((Path("/migrations") / name).read_text().split("-- migrate:up", 1)[1].split("-- migrate:down", 1)[0])
            data = {"document": {"id": "synthetic-auto-" + uuid4().hex, "title": "Synthetic safety manual",
                "kind": "onboard", "reference": "Public synthetic test", "version": "1",
                "reviewedAt": "2026-10-29", "language": "en", "sections": [
                    {"page": 1, "heading": "Classification", "text": "선박의 선급은 정기 검사를 받지 않으면 정지될 수 있다."},
                    {"page": 2, "heading": "Fuel", "text": "Fuel sulphur content limits apply in emission control areas."},
                    {"page": 3, "heading": "Deck", "text": "Heavy deck cargo requires deck strengthening."}]},
                "meta": {"scope": "all", "status": "active"}}
            with Store(scoped) as store:
                identity = store.save_document(data)["id"]
                with Store(scoped) as observer:
                    assert observer.one("SELECT count(*) AS n FROM rag_index_jobs")["n"] == 0
            def work(extra_env=None):
                result = subprocess.run([sys.executable, "-m", "api.rag_worker", "run", "--once"],
                                        env={**env, **(extra_env or {})}, capture_output=True, timeout=180)
                if result.returncode:
                    raise RuntimeError("Synthetic worker process failed")
            # Genuine HTTP connection failure must not undo the committed source.
            work({"HAEDAP_CHROMA_PORT": "1"})
            with Store(scoped) as store:
                assert store.one("SELECT state,error_code FROM rag_index_jobs")["state"] == "failed"
                assert store.one("SELECT id FROM documents WHERE id=%s", (identity,))
            retry = subprocess.run([sys.executable, "-m", "api.rag_worker", "retry", "--apply"],
                                   env=env, capture_output=True, timeout=30)
            assert retry.returncode == 0
            work()
            with Store(scoped) as store:
                assert store.one("SELECT state FROM rag_index_jobs WHERE document_id=%s", (identity,))["state"] == "done"
                rows = store.search_candidates({"role": "guest"})
                index = VectorIndex()
                assert len(index.present(rows)) == 3
                reports = {mode: search("선급 정지", rows, mode=mode, vector_index=index)
                           for mode in ("bm25", "vector", "hybrid")}
                assert all(report["effective_mode"] == mode for mode, report in reports.items())
                assert reports["vector"]["results"][0]["page"] == 1
                assert reports["hybrid"]["results"][0]["page"] == 1
                count = index.collection.count()
                store.save_document(data)  # identical content; ensure repair job and idempotence
            work()  # new process / model startup, same persisted vectors
            assert VectorIndex().collection.count() == count
            with Store(scoped) as store:
                data["document"]["version"] = "2"
                revised = store.save_document(data)["id"]
                assert revised != identity
            # Concurrent processes compete for one committed job.
            workers = [subprocess.Popen([sys.executable, "-m", "api.rag_worker", "run", "--once"],
                        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
            for worker in workers:
                worker.communicate(timeout=180)
                assert worker.returncode == 0
            with Store(scoped) as store:
                assert store.one("SELECT state FROM rag_index_jobs WHERE document_id=%s", (revised,))["state"] == "done"
                assert len(VectorIndex().present(store.search_candidates({"role": "guest"}))) == 3
                store.delete_document(revised)
                assert not store.search_candidates({"role": "guest"})
            # One document is certified, another is still pending. Validate real
            # CPU E5 + HTTP Chroma partial retrieval without any web query writes.
            pending_ids = []
            for suffix in ("ready", "waiting"):
                data["document"]["id"] = "synthetic-partial-" + suffix + uuid4().hex
                with Store(scoped) as store:
                    pending_ids.append(store.save_document(data)["id"])
            work()  # Process only the first document.
            with Store(scoped) as store:
                rows = store.search_candidates({"role": "guest"})
                index = VectorIndex()
                partial = search("선급 정지", rows, vector_index=index)
                assert partial["effective_mode"] == "hybrid"
                assert partial["coverage"]["status"] == "partial"
                assert partial["coverage"]["ready_documents"] == 1
                assert partial["coverage"]["allowed_documents"] == 2
                lexical = search("선급 정지", rows, mode="bm25")
                assert {row["document_id"] for row in lexical["results"]} == set(pending_ids)
                vector = search("선급 정지", rows, mode="vector", vector_index=index)
                assert {row["document_id"] for row in vector["results"]} == {pending_ids[0]}
                assert index.verify(rows, apply=True)["failed_documents"] == 1
                assert search("선급 정지", rows, vector_index=index)["coverage"]["status"] == "partial"
                # Same certification path as manual CLI, even while a job is pending.
                index.index(rows)
                assert index.verify(rows, apply=True)["failed_documents"] == 0
                assert search("선급 정지", rows, vector_index=index)["coverage"]["status"] == "full"
                for mode in ("vector", "hybrid"):
                    limited = search("선급 정지", rows[:1], mode=mode, vector_index=index,
                                     complete_chunks=rows)
                    assert limited["effective_mode"] == mode
                    assert [row["id"] for row in limited["results"]] == [rows[0]["id"]]
            print(json.dumps({"automatic_index": True, "chunks": 3, "commit_visibility": True,
                "worker_restart_idempotent": True, "vector_hybrid_page": 1,
                "chroma_outage_retry": True, "concurrent_workers_revision": True,
                "partial_hybrid": True, "manual_certification": True,
                "baked_model": True, "offline_model": os.getenv("HF_HUB_OFFLINE") == "1"}))
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    main()
