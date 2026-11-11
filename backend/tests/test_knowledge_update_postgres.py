"""Actual SQL transactions in an isolated rollback-only schema.

Set HAEDAP_KNOWLEDGE_TEST_DATABASE_URL to a disposable PostgreSQL endpoint.
The optional local PGlite smoke run uses the same PostgreSQL SQL/psycopg path,
not the Docker/multi-process/model integration environment.
"""
import base64
import json
import os
import pytest
from api import rag_jobs
from api.knowledge_update import UPDATE_KEY
from api.store import Workspace
from rag_postgres_support import isolated_workspace
from test_knowledge_update import BUNDLE, KNOWLEDGE

@pytest.fixture
def dsn(monkeypatch):
    value = os.getenv('HAEDAP_KNOWLEDGE_TEST_DATABASE_URL')
    if not value:
        pytest.skip('HAEDAP_KNOWLEDGE_TEST_DATABASE_URL is required')
    monkeypatch.setattr(rag_jobs, 'fingerprint', lambda: 'knowledge-test-no-model')
    return value


@pytest.mark.usefixtures("prepared_lexical")
def test_new_database_full_registration_and_page_search(dsn):
    from api.rag_retrieval import retrieve
    with isolated_workspace(dsn) as (db, _):
        assert db.one('SELECT count(*) n FROM documents')['n'] == 20
        assert db.one('SELECT count(*) n FROM document_files')['n'] == 15
        for raw in BUNDLE:
            row = db.one('SELECT * FROM documents WHERE logical_id=%s', (raw['id'],))
            assert row and row['title'] == raw['title'] and row['active']
            pdf = db.one('SELECT base64 FROM document_files WHERE id=%s', (row['id'],))
            assert base64.b64decode(pdf['base64']) == (KNOWLEDGE / raw['file']).read_bytes()
            candidates = db.search_candidates({'role':'admin'}, document_ids=[row['id']])
            assert candidates and all(c['page'] for c in candidates)
            if raw['id'] == 'mepc-400-83':
                result = retrieve('2027 reduction factor 13.625', candidates)
                assert any('13.625' in r['text'] and r['page'] == 2 for r in result)
        before = db.all('SELECT * FROM rag_index_jobs ORDER BY id')
        db.bootstrap()
        assert db.all('SELECT * FROM rag_index_jobs ORDER BY id') == before


def test_old_database_upgrade_preserves_references_and_later_deletions(dsn, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr('api.store.apply_mepc_update', lambda *args: None)
        with isolated_workspace(dsn) as (db, _):
            patch.undo()
            db.run("UPDATE documents SET title=replace(title,'(테스트용) ','')")
            db.run("UPDATE documents SET title=title || ' (가상)' WHERE kind='sample'")
            originals = db.all('SELECT id,hash FROM documents ORDER BY id')
            chunks = db.all('SELECT * FROM chunks ORDER BY id')
            files = db.all('SELECT * FROM document_files ORDER BY id')
            db.bootstrap()
            ids = [r['id'] for r in originals]
            assert db.all('SELECT id,hash FROM documents WHERE id=ANY(%s) ORDER BY id',(ids,)) == originals
            assert db.all('SELECT * FROM chunks WHERE document_id=ANY(%s) ORDER BY id',(ids,)) == chunks
            assert db.all('SELECT * FROM document_files WHERE id=ANY(%s) ORDER BY id',(ids,)) == files
            assert all(r['title'].startswith('(테스트용) ') and not r['title'].endswith('(가상)')
                       for r in db.all('SELECT title FROM documents WHERE id=ANY(%s)',(ids,)))
            assert db.one('SELECT count(*) n FROM documents')['n'] == 20
            deleted = db.one("SELECT id FROM documents WHERE logical_id='mepc-400-83'")['id']
            db.delete_document(deleted)
            db.bootstrap()
            assert not db.one('SELECT active FROM documents WHERE id=%s',(deleted,))['active']
            assert db.one('SELECT count(*) n FROM documents')['n'] == 20


def test_import_failure_rolls_back_title_changes_and_partial_documents(dsn, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr('api.store.apply_mepc_update', lambda *args: None)
        with isolated_workspace(dsn) as (db, _):
            patch.undo()
            db.run("UPDATE documents SET title=replace(title,'(테스트용) ','')")
            before = db.all('SELECT * FROM documents ORDER BY id')
            jobs = db.all('SELECT * FROM rag_index_jobs ORDER BY id')
            save = db.save_document
            def fail(payload):
                if payload['document']['id'] == BUNDLE[2]['id']:
                    raise RuntimeError('simulated failed import')
                return save(payload)
            with monkeypatch.context() as failure:
                failure.setattr(db, 'save_document', fail)
                with pytest.raises(RuntimeError, match='simulated failed import'):
                    with db.db.transaction():
                        db.bootstrap()
            assert db.all('SELECT * FROM documents ORDER BY id') == before
            assert db.all('SELECT * FROM rag_index_jobs ORDER BY id') == jobs
            assert not db.one('SELECT value FROM settings WHERE key=%s',(UPDATE_KEY,))
            db.bootstrap()
            assert db.one('SELECT count(*) n FROM documents')['n'] == 20
