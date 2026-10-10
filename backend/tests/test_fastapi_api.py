from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.pyapi import workspace_api
from backend.pyapi.workspace_store import ApiError, Workspace
from backend.pyapi.workspace_store import BACKUP_TABLES
from backend.pyapi.migrate_sqlite import migrate


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
        from backend.pyapi.workspace_store import ApiError

        if username != "admin" or password != "1234":
            raise ApiError(401, "LOGIN_FAILED", "아이디 또는 비밀번호가 올바르지 않습니다.")
        return ADMIN

    def audit(self, *_args):
        pass

    def answer(self, user, body):
        return {"id": "answer-1", "question": body["question"], "user": user["id"],
                "status": "insufficient_evidence", "evidence": [], "statements": []}


def test_browser_health_auth_and_question_contract(monkeypatch):
    monkeypatch.setattr(workspace_api, "Workspace", FakeWorkspace)
    monkeypatch.setattr(workspace_api, "initialized", False)
    workspace_api.sessions.clear()
    client = TestClient(workspace_api.app, base_url="http://localhost:5173")
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["storage"] == "postgresql"
    assert health.json()["user"]["role"] == "guest"
    assert health.json()["documents"] == 1
    token = health.json()["csrfToken"]
    assert "haedap_guest=" in health.headers["set-cookie"]

    no_token = client.post("/api/ask", json={"question": "규정"})
    assert no_token.status_code == 403
    assert no_token.json()["error"]["code"] == "SESSION_EXPIRED"
    headers = {"X-Haedap-Token": token}
    answer = client.post("/api/ask", headers=headers, json={"question": "규정"})
    assert answer.status_code == 200
    assert answer.json()["user"].startswith("guest_")
    login = client.post("/api/auth/login", headers=headers, json={"username": "admin", "password": "1234"})
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "admin"
    assert client.get("/api/health").json()["authenticated"] is True
    assert client.post("/api/auth/logout", headers=headers, json={}).status_code == 200
    assert client.get("/api/health").json()["authenticated"] is False


def test_request_origin_and_json_errors(monkeypatch):
    monkeypatch.setattr(workspace_api, "Workspace", FakeWorkspace)
    monkeypatch.setattr(workspace_api, "initialized", False)
    client = TestClient(workspace_api.app, base_url="http://localhost:5173")
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
    workspace_api.reserve_request("health")
    try:
        with pytest.raises(ApiError) as error:
            workspace_api.reserve_request("backups/restore")
        assert error.value.status == 409
    finally:
        workspace_api.release_request("health")
    workspace_api.reserve_request("backups/restore")
    try:
        with pytest.raises(ApiError) as error:
            workspace_api.reserve_request("health")
        assert error.value.status == 409
    finally:
        workspace_api.release_request("backups/restore")


def test_restore_rejects_database_lock_held_by_another_worker():
    db = SimpleNamespace(one=lambda _sql, _params: {"locked": False})
    with pytest.raises(ApiError) as error:
        workspace_api.database_request_lock(db, exclusive=True)
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

    monkeypatch.setattr(workspace_api, "Workspace", BackupWorkspace)
    monkeypatch.setattr(workspace_api, "initialized", True)
    monkeypatch.setattr(workspace_api, "backup_directory", lambda: tmp_path)
    workspace_api.automatic_backup_once()
    workspace_api.automatic_backup_once()
    assert calls == ["backup"]
    assert state["autoBackupDay"] == today
    state["autoBackup"] = "off"
    state["autoBackupDay"] = ""
    workspace_api.automatic_backup_once()
    assert calls == ["backup"]


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


def test_sqlite_migration_preview_is_read_only(tmp_path):
    path = tmp_path / "old.sqlite"
    with sqlite3.connect(path) as source:
        for table in BACKUP_TABLES:
            source.execute(f"CREATE TABLE {table}(id TEXT)")
        source.execute("INSERT INTO documents VALUES('old-doc')")
    counts = migrate(path, "postgresql://not-used-in-preview", apply=False)
    assert counts["documents"] == 1
    assert counts["operations"] == 0
    with sqlite3.connect(path) as source:
        assert source.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
