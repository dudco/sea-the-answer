from __future__ import annotations

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api import config, deps, main
from api.errors import ApiError
from api.store import Workspace
from api.web import backup_job, concurrency, security
from test_maritime_migrations import ROOT, postgres_dsn


ADMIN = {"id": "admin-1", "username": "admin", "name": "관리자", "role": "admin", "active": True, "version": 1}


class FakeWorkspace:
    def __init__(self, _dsn):
        self.db = SimpleNamespace(commit=lambda: None)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def bootstrap(self):
        pass

    def one(self, query, _params=()):
        if "pg_try_advisory_xact_lock" in query:
            return {"locked": True}
        if "pg_advisory_xact_lock" in query:
            return None
        raise AssertionError(query)

    def allowed_document_ids(self, _user):
        return ["doc-1"]

    def user_by_id(self, user_id):
        return ADMIN if user_id == ADMIN["id"] else None

    def authenticate(self, username, password):
        if username != "admin" or password != "1234":
            raise ApiError(401, "LOGIN_FAILED", "아이디 또는 비밀번호가 올바르지 않습니다.")
        return ADMIN

    def audit(self, *_args):
        pass

    def answer(self, user, body):
        return {"id": "answer-1", "question": body["question"], "user": user["id"],
                "status": "insufficient_evidence", "evidence": [], "statements": []}


def test_browser_health_auth_and_question_contract(monkeypatch):
    # HTTP auth/CSRF contract on the legacy rule path; model routing is covered in test_tool_selection.py.
    monkeypatch.setenv("HAEDAP_QUESTION_ROUTER", "legacy")
    monkeypatch.setattr(deps, "Workspace", FakeWorkspace)
    monkeypatch.setattr(deps, "initialized", False)
    security.sessions.clear()
    client = TestClient(main.app, base_url="http://localhost:5173")
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["storage"] == "postgresql"
    assert health.json()["retrieval"] == "hybrid-rrf"
    assert health.json()["user"]["role"] == "guest"
    assert health.json()["documents"] == 0
    assert health.json()["publicAccess"] is False
    token = health.json()["csrfToken"]
    assert "haedap_guest=" in health.headers["set-cookie"]

    no_token = client.post("/api/ask", json={"question": "규정"})
    assert no_token.status_code == 403
    assert no_token.json()["error"]["code"] == "SESSION_EXPIRED"
    headers = {"X-Haedap-Token": token}
    answer = client.post("/api/ask", headers=headers, json={"question": "규정"})
    assert answer.status_code == 401
    login = client.post("/api/auth/login", headers=headers, json={"username": "admin", "password": "1234"})
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "admin"
    assert client.get("/api/health").json()["authenticated"] is True
    assert client.post("/api/ask", headers=headers, json={"question": "규정"}).json()["user"] == ADMIN["id"]
    assert client.post("/api/auth/logout", headers=headers, json={}).status_code == 200
    assert client.get("/api/health").json()["authenticated"] is False


def test_request_origin_and_json_errors(monkeypatch):
    monkeypatch.setattr(deps, "Workspace", FakeWorkspace)
    monkeypatch.setattr(deps, "initialized", False)
    client = TestClient(main.app, base_url="http://localhost:5173")
    token = client.get("/api/health").json()["csrfToken"]
    wrong_origin = client.post("/api/ask", headers={"X-Haedap-Token": token, "Origin": "https://other.example"},
                               json={"question": "규정"})
    assert wrong_origin.status_code == 403
    malformed = client.post("/api/ask", headers={"X-Haedap-Token": token, "Content-Type": "application/json"},
                            content=b"{bad")
    assert malformed.status_code == 400
    assert malformed.json()["error"]["code"] == "INVALID_JSON"
    denied = client.get("/api/health", headers={"Host": "rebind.example"})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "HOST_DENIED"


def test_restore_requires_exclusive_request_slot():
    concurrency.reserve_request("health")
    try:
        with pytest.raises(ApiError) as error:
            concurrency.reserve_request("backups/restore")
        assert error.value.status == 409
    finally:
        concurrency.release_request("health")
    concurrency.reserve_request("backups/restore")
    try:
        with pytest.raises(ApiError) as error:
            concurrency.reserve_request("health")
        assert error.value.status == 409
    finally:
        concurrency.release_request("backups/restore")


def test_restore_rejects_database_lock_held_by_another_worker():
    db = SimpleNamespace(one=lambda _sql, _params: {"locked": False})
    with pytest.raises(ApiError) as error:
        concurrency.database_request_lock(db, exclusive=True)
    assert error.value.status == 409
    assert error.value.code == "BUSY"


def test_automatic_backup_runs_once_per_utc_day(monkeypatch, tmp_path):
    today = datetime.now(timezone.utc).date().isoformat()
    calls = []
    state = {"autoBackup": "daily", "autoBackupDay": ""}

    class BackupWorkspace(FakeWorkspace):
        def one(self, query, _params=()):
            if "pg_try_advisory_xact_lock" in query:
                return {"locked": True}
            if "autoBackupDay" in query:
                return {"value": state["autoBackupDay"]}
            if "autoBackup" in query:
                return {"value": state["autoBackup"]}
            if "FROM users" in query:
                return ADMIN
            raise AssertionError(query)

        def run(self, query, params=()):
            if "UPDATE settings" in query:
                state["autoBackupDay"] = params[0]

        def create_backup(self, _admin, _directory, _label):
            calls.append("backup")

    monkeypatch.setattr(deps, "Workspace", BackupWorkspace)
    monkeypatch.setattr(deps, "initialized", True)
    monkeypatch.setattr(config, "backup_directory", lambda: tmp_path)
    backup_job.automatic_backup_once()
    backup_job.automatic_backup_once()
    assert calls == ["backup"]
    assert state["autoBackupDay"] == today
    state["autoBackup"] = "off"
    state["autoBackupDay"] = ""
    backup_job.automatic_backup_once()
    assert calls == ["backup"]


def test_automatic_backup_lock_rejects_restore_without_changes_then_allows_retry(postgres_dsn, monkeypatch, tmp_path):
    # Commit migrations and fixture data so independent HTTP and backup sessions
    # exercise the actual PostgreSQL locks, not one shared mock connection.
    with Workspace(postgres_dsn) as db:
        for path in sorted((ROOT / 'migrations').glob('*.sql')):
            db.db.execute(path.read_text(encoding='utf-8').split('-- migrate:up', 1)[1].split('-- migrate:down', 1)[0])
        db.save_user(ADMIN, {'username': 'restore-lock-admin', 'name': 'Restore lock fixture',
                            'role': 'admin', 'password': 'Restore-lock-test-only-2026'})
        db.run('UPDATE users SET must_change_password=false')
        db.run("INSERT INTO settings(key,value) VALUES('autoBackup','daily')")
        db.run("INSERT INTO ships(id,body,version) VALUES('restore-fixture','{\"name\":\"before\"}'::jsonb,1)")
    monkeypatch.setenv('DATABASE_URL', postgres_dsn)
    monkeypatch.setattr(deps, 'initialized', True)
    monkeypatch.setattr(security, 'sessions', {})
    monkeypatch.setattr(security, 'login_attempts', {})
    monkeypatch.setattr(config, 'backup_directory', lambda: tmp_path)
    client = TestClient(main.app, base_url='http://localhost:5173')
    headers = {'X-Haedap-Token': client.get('/api/health').json()['csrfToken']}
    assert client.post('/api/auth/login', headers=headers, json={
        'username': 'restore-lock-admin', 'password': 'Restore-lock-test-only-2026'}).status_code == 200
    saved = client.post('/api/backups', headers=headers, json={})
    assert saved.status_code == 200
    body = {'id': saved.json()['backup']['id'], 'confirm': '복구'}
    with Workspace(postgres_dsn) as db:
        db.run("UPDATE ships SET body='{\"name\":\"after\"}'::jsonb WHERE id='restore-fixture'")
    session = client.cookies.get('haedap_session')
    before_files = set(tmp_path.glob('*.json'))
    entered, release = Event(), Event()
    create_backup = Workspace.create_backup

    def hold_automatic_backup(db, user, directory, label='수동 백업'):
        if label == '정기 자동 백업':
            entered.set()
            assert release.wait(15), 'test did not release the automatic backup'
        return create_backup(db, user, directory, label)

    monkeypatch.setattr(Workspace, 'create_backup', hold_automatic_backup)
    with ThreadPoolExecutor(max_workers=1) as worker:
        task = worker.submit(backup_job.automatic_backup_once)
        try:
            assert entered.wait(10), 'automatic backup did not reach its protected work'
            rejected = client.post('/api/backups/restore', headers=headers, json=body)
            assert rejected.status_code == 409
            assert rejected.json()['error']['code'] == 'BUSY'
            assert client.cookies.get('haedap_session') == session
            assert security.digest(session) in security.sessions
            assert set(tmp_path.glob('*.json')) == before_files  # No pre-restore safety backup or partial restore.
            with Workspace(postgres_dsn) as db:
                assert db.one("SELECT body FROM ships WHERE id='restore-fixture'")['body']['name'] == 'after'
            assert concurrency.active_requests == 0 and not concurrency.restoring
        finally:
            release.set()
        task.result(timeout=10)
    restored = client.post('/api/backups/restore', headers=headers, json=body)
    assert restored.status_code == 200, restored.text
    assert restored.json()['safetyBackup']
    assert not security.sessions
    with Workspace(postgres_dsn) as db:
        assert db.one("SELECT body FROM ships WHERE id='restore-fixture'")['body']['name'] == 'before'
    assert client.get('/api/operations').status_code == 401


@pytest.mark.usefixtures("prepared_lexical")
def test_bilingual_document_search_matches_korean_evidence():
    store = object.__new__(Workspace)
    store.all = lambda _sql, _params=(): [{
        "id": "chunk-1", "document_id": "doc-1", "heading": "", "text": "연료 사용량 기록",
        "page": 1, "title": "운항 매뉴얼", "kind": "onboard", "url": None,
        "reference": "선박", "version": "1", "reviewed_at": "2026-01-01", "hash": "hash",
        "meta": {"scope": "all", "status": "active"},
    }]
    result = store.search({"role": "guest"}, "fuel")
    assert [item["id"] for item in result] == ["chunk-1"]


def test_ship_update_rejects_a_version_changed_during_save():
    store = object.__new__(Workspace)
    store.validate_ship = lambda payload: {"id": payload["id"], "name": "Test Ship"}

    def query(sql, _params=()):
        if "FROM pg_attribute" in sql:
            return {"ready": False}  # This version-conflict case has no maritime mapping.
        if sql.startswith("SELECT version FROM ships"):
            return {"version": 1}
        if sql.startswith("UPDATE ships"):
            return None  # A concurrent request already advanced the version.
        raise AssertionError(sql)

    store.one = query
    with pytest.raises(ApiError) as error:
        store.apply_change("ship.save", {"id": "ship-1", "version": 1})
    assert error.value.status == 409
    assert error.value.code == "VERSION_CONFLICT"


def test_postgresql_operation_summary_and_calculation_formulas():
    store = object.__new__(Workspace)
    store.one = lambda _sql, _params=(): {"body": {"id": "ship-1", "name": "시험선", "dwt": 50000}, "version": 1}
    store.all = lambda _sql, _params=(): [{"body": {"id": "row-1", "ship": "ship-1", "date": "2026-09-22",
                                             "fuel": 10, "factor": 3, "distance": 100, "speed": 12}, "version": 1}]
    store.run = lambda *_args: None
    summary = store.operation_summary({"ship": "ship-1", "from": "2026-09-22", "to": "2026-09-22"})
    assert summary["count"] == 1
    assert summary["emission"] == 30
    assert summary["intensity"] == 6
    assert summary["cii"]["rating"] is None
    calculation = store.calculate_emissions({"fuel": 10, "factor": 3, "dwt": 50000, "distance": 100})
    assert calculation["emission"] == 30
    assert calculation["intensity"] == 6
