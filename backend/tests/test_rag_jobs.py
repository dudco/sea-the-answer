"""Offline unit tests and disposable-schema commit/concurrency integration tests."""
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from api import rag_jobs as jobs
from api.rag_embeddings import VectorUnavailable, content_hash, digest
from api.rag_worker import manage
from api.store.base import Database
from api.store.documents import DocumentStore
from test_rag_postgres import payload

FP = digest({"test": 1})


class Store(Database, DocumentStore):
    pass


class Index:
    fingerprint = FP

    def __init__(self):
        self.stored = set()
        self.created = 0
        self.hook = None

    def index(self, rows, batch_size):
        if self.hook:
            self.hook()
        keys = {content_hash(row) for row in rows}
        self.created += len(keys - self.stored)
        self.stored.update(keys)


@pytest.fixture
def db_factory(monkeypatch):
    dsn = os.getenv("HAEDAP_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("HAEDAP_TEST_DATABASE_URL not configured (disposable schema required)")
    schema = "rag_jobs_test_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    scoped = make_conninfo(dsn, options=f"-c search_path={schema}")
    try:
        with psycopg.connect(scoped) as connection:
            root = Path(__file__).resolve().parents[2] / "migrations"
            for name in ("20261013000000_init.sql", "20261029000000_rag_index_jobs.sql"):
                connection.execute((root / name).read_text(encoding="utf-8").split("-- migrate:up", 1)[1].split("-- migrate:down", 1)[0])
        monkeypatch.setattr(jobs, "fingerprint", lambda: FP)
        monkeypatch.setattr("api.rag_worker.fingerprint", lambda: FP)
        yield lambda: Store(scoped)
    finally:
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def run(factory, index):
    with factory() as store:
        return jobs.process_one(store, index_factory=lambda: index, model_fingerprint=index.fingerprint)


def saved(factory, data=None):
    with factory() as store:
        return store.save_document(data or payload())["id"]


def state(factory, document_id):
    with factory() as store:
        return store.one("SELECT * FROM rag_index_jobs WHERE document_id=%s AND fingerprint=%s", (document_id, FP))


def test_retry_and_error_codes_do_not_leak():
    assert [jobs.retry_delay(n) for n in (1, 2, 5, 20)] == [5, 10, 80, 300]
    assert jobs.error_code(ValueError("private document and password")) == "index_backend_failure"
    assert jobs.error_code(VectorUnavailable("unexpected private content")) == "index_backend_failure"
    assert jobs.error_code(VectorUnavailable("model_not_prepared")) == "model_not_prepared"


def test_snapshot_tracks_embedding_fields_but_not_scope():
    row = {"id": "c", "document_id": "d", "title": "a", "text": "text", "meta": {"scope": "all"}}
    assert jobs.snapshot_hash([row]) == jobs.snapshot_hash([{**row, "meta": {"scope": "admin"}}])
    for key in ("title", "reference", "heading", "text", "page"):
        assert jobs.snapshot_hash([row]) != jobs.snapshot_hash([{**row, key: "changed"}])


def test_commit_rollback_and_no_query_time_work(db_factory):
    index = Index()
    with db_factory() as writer:
        identity = writer.save_document(payload())["id"]
        assert not run(db_factory, index)  # uncommitted outbox invisible
        assert not index.stored
    assert run(db_factory, index)
    assert state(db_factory, identity)["state"] == "done"
    failed = payload()
    failed["document"]["id"] = "rollback-document"
    with pytest.raises(RuntimeError), db_factory() as writer:
        writer.save_document(failed)
        raise RuntimeError("rollback")
    with db_factory() as store:
        assert not store.one("SELECT id FROM documents WHERE logical_id='rollback-document'")
    assert not run(db_factory, index)


def test_unchanged_scope_missing_index_and_model_change(db_factory):
    index = Index()
    identity = saved(db_factory)
    run(db_factory, index)
    created = index.created
    data = payload()
    data["expectedId"] = identity
    data["meta"]["scope"] = "admin"
    saved(db_factory, data)
    run(db_factory, index)
    assert index.created == created
    with db_factory() as store:
        assert store.search_candidates({"role": "guest"}) == []
    index.stored.clear()
    saved(db_factory, data)
    run(db_factory, index)
    assert index.created == created * 2
    index.fingerprint = digest({"test": 2})
    with db_factory() as store:
        jobs.enqueue(store, identity, index.fingerprint)
    assert run(db_factory, index)
    with db_factory() as store:
        assert store.one("SELECT state FROM rag_index_jobs WHERE fingerprint=%s", (index.fingerprint,))["state"] == "done"


def test_double_worker_and_crashed_session_recovery(db_factory):
    identity = saved(db_factory)
    index = Index()
    first = db_factory()
    try:
        claimed = jobs.claim(first, FP)
        assert claimed["state"] == "processing"
        assert not run(db_factory, index)  # session lock survives transaction commit
    finally:
        first.db.close()  # simulate killed worker, no explicit unlock
    assert run(db_factory, index)
    assert state(db_factory, identity)["state"] == "done"
    assert state(db_factory, identity)["attempts"] == 2


def test_chroma_failure_backoff_retry_and_idempotent_partial_write(db_factory):
    identity = saved(db_factory)
    index = Index()
    def failing():
        raise RuntimeError("secret payload must not be logged")
    index.hook = failing
    assert run(db_factory, index)
    assert state(db_factory, identity)["error_code"] == "index_backend_failure"
    assert not run(db_factory, index)  # backoff
    with db_factory() as store:
        assert manage(store, "retry")["applied"] is False
        manage(store, "retry", apply=True)
    index.hook = None
    assert run(db_factory, index)
    assert state(db_factory, identity)["state"] == "done"
    with db_factory() as store:
        # Simulate crash after Chroma success but before PG completion.
        jobs.enqueue(store, identity, FP)
    created = index.created
    assert run(db_factory, index)
    assert index.created == created


@pytest.mark.parametrize("change", ["revision", "delete", "retire", "scope", "same"])
def test_change_during_embedding_cannot_complete_new_generation(db_factory, change):
    identity = saved(db_factory)
    index = Index()
    data = payload()
    data["expectedId"] = identity
    changed_id = []
    def change_document():
        index.hook = None
        with db_factory() as store:
            if change == "delete":
                store.delete_document(identity)
                return
            if change == "revision":
                data["document"]["sections"][0]["text"] += " revised safety check"
            elif change == "retire":
                data["meta"]["status"] = "retired"
            elif change == "scope":
                data["meta"]["scope"] = "admin"
            changed_id.append(store.save_document(data)["id"])
    index.hook = change_document
    run(db_factory, index)
    if change in ("scope", "same", "retire"):
        assert state(db_factory, identity)["state"] == "pending"
        assert state(db_factory, identity)["generation"] == 2
    else:
        assert state(db_factory, identity)["state"] == "cancelled"
    run(db_factory, index)
    if change == "retire":
        assert state(db_factory, identity)["state"] == "cancelled"
    elif change != "delete":
        assert state(db_factory, changed_id[0])["state"] == "done"
    with db_factory() as store:
        candidates = store.search_candidates({"role": "guest"})
        if change in ("delete", "retire", "scope"):
            assert not candidates
        elif change == "revision":
            assert {row["document_id"] for row in candidates} == {changed_id[0]}


def test_preexisting_inactive_jobs_and_explicit_repair_only(db_factory):
    identity = saved(db_factory)
    with db_factory() as store:
        store.run("DELETE FROM rag_index_jobs")
        assert manage(store, "enqueue")["documents"] == 1
    assert not run(db_factory, Index())
    with db_factory() as store:
        manage(store, "enqueue", document_id=identity, apply=True)
        assert manage(store, "status")[0]["state"] == "pending"
        store.delete_document(identity)
    index = Index()
    run(db_factory, index)
    assert state(db_factory, identity)["state"] == "cancelled"
    assert not index.stored


def test_real_chroma_automatic_index_and_search(db_factory, tmp_path):
    import chromadb
    from chromadb.config import Settings
    from api.rag_vector import VectorIndex
    from api.rag_search import search
    from test_rag_vector import Encoder
    client = chromadb.PersistentClient(path=str(tmp_path), settings=Settings(anonymized_telemetry=False))
    index = VectorIndex(create=True, db=client, encoder=Encoder(), model_contract={"test": 1})
    identity = saved(db_factory)
    assert run(db_factory, index)
    with db_factory() as store:
        rows = store.search_candidates({"role": "guest"})
        for mode in ("vector", "hybrid"):
            report = search("equipment checks", rows, mode=mode, vector_index=index)
            assert report["effective_mode"] == mode
            assert report["results"][0]["document_id"] == identity
            assert report["results"][0]["page"] in (7, 9)
    assert state(db_factory, identity)["state"] == "done"


def test_retry_limit_and_current_model_only(db_factory):
    identity = saved(db_factory)
    index = Index()
    def fail():
        raise VectorUnavailable("model_not_prepared")
    index.hook = fail
    for attempt in range(1, jobs.MAX_ATTEMPTS + 1):
        assert run(db_factory, index)
        assert state(db_factory, identity)["attempts"] == attempt
        with db_factory() as store:
            store.run("UPDATE rag_index_jobs SET next_attempt_at=now()")
    assert not run(db_factory, index)
    with db_factory() as store:
        jobs.enqueue(store, identity, "other-model")
        assert not jobs.claim(store, "unrelated-model")
        manage(store, "retry", apply=True)
    index.hook = None
    assert run(db_factory, index)
    with db_factory() as store:
        assert store.one("SELECT state FROM rag_index_jobs WHERE fingerprint='other-model'")["state"] == "pending"


def test_worker_real_chroma_mixed_vectors_after_content_revision(db_factory, tmp_path):
    import chromadb
    from chromadb.config import Settings
    from api.rag_vector import VectorIndex
    from api.rag_search import search
    from test_rag_vector import Encoder
    client = chromadb.PersistentClient(path=str(tmp_path), settings=Settings(anonymized_telemetry=False))
    index = VectorIndex(create=True, db=client, encoder=Encoder(), model_contract={"test": 1})
    data = payload()
    data["document"]["sections"] = [
        {"page": 1, "heading": "Checks", "text": "선급 검사를 진행하는 가상 문서입니다."},
        {"page": 2, "heading": "Fuel", "text": "Synthetic fuel inspection instructions."},
    ]
    first = saved(db_factory, data)
    assert run(db_factory, index)
    assert state(db_factory, first)["state"] == "done"
    data["expectedId"] = first
    data["document"]["sections"][1]["text"] += " Revised instructions."
    revised = saved(db_factory, data)
    assert revised != first
    assert run(db_factory, index)  # Reused first vector + new second vector, same batch.
    assert state(db_factory, revised)["state"] == "done"
    with db_factory() as store:
        rows = store.search_candidates({"role": "operator"})
        assert {r["document_id"] for r in rows} == {revised}
        for mode in ("vector", "hybrid"):
            report = search("선급 검사", rows, mode=mode, vector_index=index)
            assert report["effective_mode"] == mode
            assert report["results"][0]["page"] == 1


def test_job_generation_fences_late_completion(db_factory):
    identity = saved(db_factory)
    with db_factory() as worker:
        job = jobs.claim(worker, FP)
        with db_factory() as writer:
            jobs.enqueue(writer, identity, FP)
        jobs.finish(worker, job, "done")
        jobs.unlock(worker, job["id"])
    assert state(db_factory, identity)["state"] == "pending"
    assert state(db_factory, identity)["generation"] == 2


def test_metadata_save_reactivation_repair_and_rollback(db_factory):
    identity = saved(db_factory)
    index = Index()
    run(db_factory, index)
    with db_factory() as store:
        original = jobs.chunks(store, identity)

    def edit(status):
        with db_factory() as store:
            meta = store.document_meta(identity)
            return store.save_document({"mode": "metadata", "document": {"id": "rag-synthetic"},
                "expectedId": identity, "expectedMetaRevision": meta["revision"],
                "meta": {"status": status}})

    edit("retired")
    run(db_factory, index)
    assert state(db_factory, identity)["state"] == "cancelled"
    index.stored.clear()  # A missing derived index must be repairable.
    edit("active")
    assert run(db_factory, index)
    assert state(db_factory, identity)["state"] == "done"
    with db_factory() as store:
        assert jobs.chunks(store, identity) == original
    generation = state(db_factory, identity)["generation"]
    with pytest.raises(RuntimeError), db_factory() as store:
        meta = store.document_meta(identity)
        store.save_document({"mode": "metadata", "document": {"id": "rag-synthetic"},
            "expectedId": identity, "expectedMetaRevision": meta["revision"],
            "meta": {"scope": "admin"}})
        raise RuntimeError("rollback")
    assert state(db_factory, identity)["generation"] == generation
    assert edit("active")["status"] == "unchanged"
    assert state(db_factory, identity)["generation"] == generation + 1
    assert run(db_factory, index)
    assert state(db_factory, identity)["state"] == "done"


def test_new_migration_down_up_and_foreign_key_cleanup(db_factory):
    identity = saved(db_factory)
    migration = Path(__file__).resolve().parents[2] / "migrations/20261029000000_rag_index_jobs.sql"
    source = migration.read_text(encoding="utf-8")
    with db_factory() as store:
        store.run(source.split("-- migrate:down", 1)[1])
        assert store.one("SELECT count(*) AS n FROM documents")["n"] == 1
        store.run(source.split("-- migrate:up", 1)[1].split("-- migrate:down", 1)[0])
        jobs.enqueue(store, identity, FP)
        # Match backup restore ordering for existing non-cascading source FKs.
        store.run("DELETE FROM chunk_pages WHERE id IN (SELECT id FROM chunks WHERE document_id=%s)", (identity,))
        store.run("DELETE FROM chunks WHERE document_id=%s", (identity,))
        store.run("DELETE FROM document_meta WHERE id=%s", (identity,))
        store.run("DELETE FROM documents WHERE id=%s", (identity,))
        assert store.one("SELECT count(*) AS n FROM rag_index_jobs")["n"] == 0
