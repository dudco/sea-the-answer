"""Disposable PostgreSQL schema for document API tests; always rolled back."""
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from api import deps
from api.store import Workspace
from api.web import security


@contextmanager
def isolated_workspace(dsn):
    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=5) as connection:
        with connection.transaction(force_rollback=True):
            schema = "rag_test_" + uuid4().hex
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            connection.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(schema)))
            migration = Path(__file__).resolve().parents[2] / "migrations/20261013000000_init.sql"
            # Only the app migration's up section, scoped to this temporary
            # schema. Never run down or the public maritime migration here.
            app_sql = migration.read_text(encoding="utf-8").split("-- migrate:up", 1)[1].split("-- migrate:down", 1)[0]
            connection.execute(app_sql)
            jobs = migration.parent / "20261029000000_rag_index_jobs.sql"
            connection.execute(jobs.read_text(encoding="utf-8").split("-- migrate:up", 1)[1].split("-- migrate:down", 1)[0])
            auth_migration = migration.parent / "20261021000000_user_password_change.sql"
            connection.execute(auth_migration.read_text(encoding="utf-8").split("-- migrate:up", 1)[1].split("-- migrate:down", 1)[0])
            store = object.__new__(Workspace)
            store.db, store.dsn = connection, dsn
            store.bootstrap()
            # Disposable test accounts, never production defaults.
            for username, role in (("admin", "admin"), ("crew", "operator")):
                store.save_user({"id": "fixture", "name": "Test fixture", "role": "admin"}, {
                    "username": username, "name": username, "role": role,
                    "password": "Test-only-password-2026",
                })
            store.run("UPDATE users SET must_change_password=false")

            class RequestWorkspace(Workspace):
                def __init__(self, _dsn):
                    self.db, self.dsn = connection, dsn

                def __enter__(self):
                    # Each request gets a savepoint. The outer transaction
                    # owns rollback and the connection; never commit it here.
                    self.request_transaction = connection.transaction()
                    self.request_transaction.__enter__()
                    return self

                def __exit__(self, *args):
                    return self.request_transaction.__exit__(*args)

            yield store, RequestWorkspace


def configure_api(monkeypatch, request_workspace):
    monkeypatch.setattr(deps, "Workspace", request_workspace)
    # bootstrap above already ran inside the rollback-only transaction.
    monkeypatch.setattr(deps, "initialized", True)
    monkeypatch.setattr(security, "sessions", {})
    monkeypatch.setattr(security, "login_attempts", {})


def login(client, username="admin", password="Test-only-password-2026"):
    health = client.get("/api/health")
    assert health.status_code == 200
    headers = {"X-Haedap-Token": health.json()["csrfToken"]}
    result = client.post("/api/auth/login", headers=headers, json={"username": username, "password": password})
    assert result.status_code == 200
    return headers
