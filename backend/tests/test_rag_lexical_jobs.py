"""Real isolated PostgreSQL + OpenSearch synchronization, no application data."""
from pathlib import Path

import pytest

from api import rag_lexical_jobs as jobs
from api.rag_lexical import LexicalUnavailable, record_id
from test_rag_jobs import db_factory, payload


@pytest.fixture
def database(db_factory):
    with db_factory() as store:
        migration = Path(__file__).resolve().parents[2] / "migrations/20261111000000_rag_lexical_jobs.sql"
        store.run(migration.read_text(encoding="utf-8").split("-- migrate:up",1)[1].split("-- migrate:down",1)[0])
    return db_factory


def state(factory, doc):
    with factory() as store:
        return store.one("SELECT * FROM rag_lexical_jobs WHERE document_id=%s",(doc,))


def run(factory,index,**kwargs):
    with factory() as store:
        return jobs.process_one(store,index_factory=lambda:index,**kwargs)


def save(factory):
    with factory() as store:
        return store.save_document(payload())["id"]


def test_commit_rollback_coalescing_and_idempotent_sync(database,lexical_index):
    with pytest.raises(RuntimeError):
        with database() as store:
            doc=store.save_document(payload())["id"]
            # Another session cannot claim uncommitted jobs.
            assert run(database,lexical_index) is False
            raise RuntimeError("rollback")
    assert state(database,doc) is None
    doc=save(database)
    assert state(database,doc)["generation"]==1
    assert run(database,lexical_index)
    assert state(database,doc)["state"]=="done"
    with database() as store:
        rows=jobs.chunks(store,doc)
        jobs.enqueue(store,doc)
    assert lexical_index.search("Fictionalquartz",rows)
    assert run(database,lexical_index)
    assert lexical_index.index(rows)==0


def test_partial_failure_retry_recovery_and_duplicate_worker(database,lexical_index,monkeypatch):
    doc=save(database)
    assert run(database,lexical_index,limit=1)
    assert state(database,doc)["error_code"]=="partial_index"
    with database() as store:
        rows=jobs.chunks(store,doc)
        jobs.enqueue(store,doc)
    with pytest.raises(LexicalUnavailable): lexical_index.search("fuel",rows)
    original=lexical_index.index
    called=[]
    def while_locked(rows,batch_size):
        called.append(run(database,lexical_index))
        return original(rows,batch_size)
    monkeypatch.setattr(lexical_index,"index",while_locked)
    run(database,lexical_index)
    assert called and not any(called)
    assert state(database,doc)["state"]=="done"
    # Processing job left by dead session is claimable immediately.
    with database() as store:
        jobs.enqueue(store,doc)
    with database() as store:
        abandoned=jobs.claim(store)
        assert abandoned
    run(database,lexical_index)
    assert state(database,doc)["state"]=="done"


def test_change_during_index_and_deletion_cannot_publish_stale(database,lexical_index,monkeypatch):
    doc=save(database)
    original=lexical_index.index
    changed=[]
    def mutate(rows,batch_size):
        if not changed:
            with database() as store:
                store.run("UPDATE documents SET title='changed synthetic' WHERE id=%s",(doc,))
            changed.append(True)
        return original(rows,batch_size)
    monkeypatch.setattr(lexical_index,"index",mutate)
    run(database,lexical_index)
    assert state(database,doc)["state"]=="pending"
    run(database,lexical_index)
    assert state(database,doc)["state"]=="done"
    with database() as store:
        store.delete_document(doc)
    assert state(database,doc)["state"]=="pending"
    run(database,lexical_index)
    result=lexical_index.request("POST",f"/{lexical_index.name}/_count",{"query":{"term":{"document_id":doc}}})
    assert result["count"]==0 and state(database,doc)["state"]=="done"


def test_metadata_scope_queue_and_backend_failure_preserve_source(database,lexical_index,monkeypatch):
    doc=save(database)
    run(database,lexical_index)
    with database() as store:
        store.run("UPDATE document_meta SET body=jsonb_set(body,'{scope}','\"admin\"') WHERE id=%s",(doc,))
    assert state(database,doc)["state"]=="pending"
    def fail(*args,**kwargs): raise RuntimeError("PRIVATE SECRET")
    original=lexical_index.index
    monkeypatch.setattr(lexical_index,"index",fail)
    run(database,lexical_index)
    assert state(database,doc)["error_code"]=="lexical_backend_failure"
    with database() as store:
        assert store.one("SELECT id FROM documents WHERE id=%s",(doc,))
        assert store.search_candidates({"role":"guest"})==[]
        jobs.enqueue(store,doc)
    monkeypatch.setattr(lexical_index,"index",original)
    run(database,lexical_index)
    assert state(database,doc)["state"]=="done"


def test_physical_delete_keeps_tombstone_and_new_migration_down_up(database,lexical_index):
    doc=save(database)
    run(database,lexical_index)
    with database() as store:
        store.run("DELETE FROM chunk_pages WHERE id IN (SELECT id FROM chunks WHERE document_id=%s)",(doc,))
        store.run("DELETE FROM chunks WHERE document_id=%s",(doc,))
        store.run("DELETE FROM document_meta WHERE id=%s",(doc,))
        store.run("DELETE FROM document_files WHERE id=%s",(doc,))
        store.run("DELETE FROM documents WHERE id=%s",(doc,))
    assert state(database,doc)["state"]=="pending"
    run(database,lexical_index)
    assert lexical_index.request("POST",f"/{lexical_index.name}/_count",{"query":{"term":{"document_id":doc}}})["count"]==0
    from api.rag_lexical_worker import manage
    with database() as store:
        assert manage(store,"enqueue",document_id=doc,apply=True)["documents"]==1
    assert state(database,doc)["state"]=="pending"
    run(database,lexical_index)
    migration=Path(__file__).resolve().parents[2]/"migrations/20261111000000_rag_lexical_jobs.sql"
    script=migration.read_text(encoding="utf-8")
    with database() as store:
        store.run(script.split("-- migrate:down",1)[1])
        store.run(script.split("-- migrate:up",1)[1].split("-- migrate:down",1)[0])
    assert state(database,doc) is None
