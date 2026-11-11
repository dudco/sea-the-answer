"""Real search/answer/auth boundaries with in-memory SQL rows and mock model HTTP."""

from copy import deepcopy
from datetime import date
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from api import deps, llm, main
from api.store.documents import DocumentStore
from api.web import security
from test_llm_provider import MemoryWorkspace, completion


def document_chunk(name, *, scope="all", status="active", active=True):
    return {
        "id": "chunk-" + name, "document_id": "doc-" + name,
        "title": name + " document", "heading": "Synthetic procedure",
        "text": "Fictionalquartz " + name + " source passage for permission checks.",
        "page": 7, "kind": "onboard", "url": None, "reference": "Synthetic source",
        "version": "1", "reviewed_at": date(2026, 10, 28),
        "meta": {"scope": scope, "status": status}, "active": active,
    }


@pytest.fixture
def access_client(monkeypatch):
    accounts = {
        role: {"id": role, "username": role, "name": role, "role": role,
               "active": True, "version": 1, "must_change_password": False}
        for role in ("operator", "viewer", "admin")
    }
    rows = [
        document_chunk("publicmarker"),
        document_chunk("crewmarker", scope="operator"),
        document_chunk("adminmarker", scope="admin"),
        document_chunk("retiredmarker", status="retired"),
        document_chunk("deletedmarker", status="deleted"),
        document_chunk("oldrevisionmarker", active=False),
    ]
    reads = []

    class AccessWorkspace(DocumentStore, MemoryWorkspace):
        # Keep the production search, candidate filtering, BM25 and answer flow.
        # Only SQL row loading, accounts and persistence are in memory.
        def all(self, query, _params=()):
            assert "WHERE d.active=true" in query
            reads.append(query)
            # Simulate the SQL WHERE condition; PostgreSQL itself is not tested here.
            return [{key: value for key, value in row.items() if key != "active"}
                    for row in rows if row["active"]]

        def one(self, query, params=()):
            if query in ("SELECT id FROM documents WHERE id=%s", "SELECT body FROM document_meta WHERE id=%s"):
                row = next((row for row in rows if row["document_id"] == params[0]), None)
                if row is None:
                    return None
                return {"id": row["document_id"]} if query.startswith("SELECT id") else {"body": row["meta"]}
            return super().one(query, params)

        def allowed_document_ids(self, user):
            return [row["document_id"] for row in self.search_candidates(user)]

        def user_by_id(self, user_id):
            return accounts.get(user_id)

        def authenticate(self, username, password):
            assert password == "Test-only-password"
            return deepcopy(accounts[username])

    monkeypatch.setenv("LLM_API_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("OPENAI_MODEL", "local-model")
    monkeypatch.setenv("LLM_RESPONSE_FORMAT", "text")
    monkeypatch.delenv("HAEDAP_HTTPS", raising=False)
    monkeypatch.setattr(deps, "Workspace", AccessWorkspace)
    monkeypatch.setattr(deps, "initialized", False)
    monkeypatch.setattr(security, "sessions", {})
    monkeypatch.setattr(security, "login_attempts", {})
    with TestClient(main.app, base_url="http://localhost:5173") as client:
        headers = {"X-Haedap-Token": client.get("/api/health").json()["csrfToken"]}
        yield client, headers, accounts, rows, reads


@pytest.fixture
def captured_model(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        prompt = json.loads(json.loads(request.content)["messages"][1]["content"])
        evidence = prompt["evidence"][0]
        statement = {"text": "허용된 문서의 근거입니다.", "chunkId": evidence["chunkId"],
                     "quote": evidence["text"]}
        return httpx.Response(200, json=completion({"insufficient": False, "statements": [statement]}))

    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        monkeypatch.setattr(llm.httpx, "post", transport.post)
        yield calls


def login(client, headers, role):
    response = client.post("/api/auth/login", headers=headers, json={
        "username": role, "password": "Test-only-password",
    })
    assert response.status_code == 200


def ask(client, headers, question="Fictionalquartz"):
    return client.post("/api/ask", headers=headers, json={
        "question": question, "language": "ko", "task": "documents", "mode": "llm",
    })


@pytest.mark.parametrize("role,visible", [
    ("viewer", {"publicmarker"}),
    ("operator", {"publicmarker", "crewmarker"}),
    ("admin", {"publicmarker", "crewmarker", "adminmarker"}),
])
@pytest.mark.usefixtures("prepared_lexical")
def test_only_readable_current_evidence_reaches_model(access_client, captured_model, role, visible):
    client, headers, _accounts, rows, reads = access_client
    login(client, headers, role)

    response = ask(client, headers)

    assert response.status_code == 200
    answer = response.json()
    assert answer["generation"] == "llm" and answer["warnings"] == []
    assert {item["id"] for item in answer["evidence"]} == {"chunk-" + name for name in visible}
    assert len(captured_model) == 1 and reads
    request_body = json.loads(captured_model[0].content)
    prompt = json.loads(request_body["messages"][1]["content"])
    assert {item["chunkId"] for item in prompt["evidence"]} == {"chunk-" + name for name in visible}
    serialized_request = json.dumps(request_body, ensure_ascii=False)
    for row in rows:
        if row["id"] not in {"chunk-" + name for name in visible}:
            for field in ("id", "title", "text"):
                assert row[field] not in serialized_request


@pytest.mark.usefixtures("prepared_lexical")
def test_question_matching_only_admin_document_does_not_contact_model(access_client, captured_model):
    client, headers, _accounts, _rows, _reads = access_client
    login(client, headers, "operator")

    response = ask(client, headers, "adminmarker")

    assert response.status_code == 200
    answer = response.json()
    assert answer["status"] == "insufficient_evidence"
    assert answer["evidence"] == [] and answer["statements"] == []
    assert captured_model == []


@pytest.mark.parametrize("state,status,code", [
    ("anonymous", 401, "AUTH_REQUIRED"),
    ("initial-password", 403, "PASSWORD_CHANGE_REQUIRED"),
    ("inactive", 401, "AUTH_REQUIRED"),
    ("revoked-version", 401, "AUTH_REQUIRED"),
])
def test_blocked_account_never_searches_or_contacts_model(
        access_client, captured_model, state, status, code):
    client, headers, accounts, _rows, reads = access_client
    if state == "initial-password":
        accounts["operator"]["must_change_password"] = True
    if state != "anonymous":
        login(client, headers, "operator")
    if state == "inactive":
        accounts["operator"]["active"] = False
    elif state == "revoked-version":
        accounts["operator"]["version"] += 1

    response = ask(client, headers)

    assert response.status_code == status and response.json()["error"]["code"] == code
    assert reads == [] and captured_model == []
