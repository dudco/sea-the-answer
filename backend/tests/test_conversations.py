"""Conversation persistence, access isolation, old records and deletion."""
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from api import main, rag_jobs
from api.errors import ApiError
from rag_postgres_support import isolated_workspace, configure_api, login
from test_maritime_migrations import postgres_dsn


@pytest.fixture(autouse=True)
def isolate_unused_vector_worker(monkeypatch):
    # These tests exercise saved conversations, not the optional embedding worker.
    monkeypatch.setattr(rag_jobs, 'fingerprint', lambda: 'conversation-test-no-embeddings')


def test_conversation_history_restore_delete_and_permissions(postgres_dsn, monkeypatch):
    with isolated_workspace(postgres_dsn) as (db, request_db):
        configure_api(monkeypatch, request_db)
        client = TestClient(main.app, base_url='http://localhost:5173')
        headers = login(client)
        # Run the normal document answer path, with deterministic empty retrieval.
        monkeypatch.setattr(request_db, 'search', lambda *a, **kw: [])
        first = client.post('/api/ask', headers=headers, json={'question':'첫 질문', 'task':'documents'}).json()
        root = first['id']
        for i in range(3):
            response = client.post('/api/ask', headers=headers, json={'question':f'후속 질문 {i}', 'task':'documents', 'conversationId':root})
            assert response.status_code == 200, response.text
            assert response.json()['conversationId'] == root
        history = client.get('/api/conversations').json()['history']
        assert len(history) == 1 and history[0]['count'] == 4
        restored = client.get('/api/conversations/'+root).json()
        assert [t['question'] for t in restored['turns']] == ['첫 질문','후속 질문 0','후속 질문 1','후속 질문 2']
        assert restored['turns'][0]['answer'] == first  # no translation / regeneration
        # Same storage path supports historical singleton records lacking conversationId.
        other = client.post('/api/ask', headers=headers, json={'question':'별도 질문', 'task':'documents'}).json()['id']
        assert len(client.get('/api/conversations').json()['history']) == 2
        crew = TestClient(main.app, base_url='http://localhost:5173')
        crew_headers = login(crew, 'crew')
        assert crew.get('/api/conversations').json()['history'] == []
        assert crew.get('/api/conversations/'+root).status_code == 404
        assert crew.post('/api/conversations/delete', headers=crew_headers, json={'id':root}).status_code == 404
        assert crew.post('/api/ask', headers=crew_headers, json={'question':'타인 대화', 'conversationId':root}).status_code == 404
        assert client.post('/api/conversations/delete', json={'id':root}).status_code == 403
        deleted = client.post('/api/conversations/delete', headers=headers, json={'id':root})
        assert deleted.status_code == 200 and deleted.json()['count'] == 4
        assert client.get('/api/conversations/'+root).status_code == 404
        assert client.post('/api/ask', headers=headers, json={'question':'삭제 후', 'conversationId':root}).status_code == 404
        assert [h['id'] for h in client.get('/api/conversations').json()['history']] == [other]
        assert db.one('SELECT count(*) AS n FROM query_owner')['n'] == 1


def test_conversation_rechecks_each_turn_evidence_and_no_100_turn_limit(postgres_dsn, monkeypatch):
    with isolated_workspace(postgres_dsn) as (db, _):
        user = db.one("SELECT * FROM users WHERE username='admin'")
        root = str(uuid4())
        from api.validation import utc_now
        for i in range(105):
            ident = root if i == 0 else str(uuid4())
            answer = {'id':ident, 'conversationId':root, 'evidence':[{'document_id':'denied'}] if i==7 else []}
            db.run('INSERT INTO queries VALUES(%s,%s,%s,%s)', (ident,str(i),Jsonb(answer),utc_now()))
            db.run('INSERT INTO query_owner VALUES(%s,%s)', (ident,user['id']))
        monkeypatch.setattr(db,'can_read_document',lambda u,d: d!='denied')
        turns = db.conversation(user,root)['turns']
        assert len(turns) == 105
        assert turns[7]['answer'] is None and turns[7]['unavailable']
        assert turns[8]['answer']['id'] == turns[8]['id']
        assert len(db.conversations(user)) == 1
