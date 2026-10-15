"""Opt-in real DB tests. Set HAEDAP_TEST_DATABASE_URL; no production rows changed."""
import os
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from api import main
from rag_postgres_support import configure_api, isolated_workspace, login


@pytest.fixture
def database(monkeypatch):
    dsn = os.getenv("HAEDAP_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("HAEDAP_TEST_DATABASE_URL not configured")
    with isolated_workspace(dsn) as (store, request_workspace):
        configure_api(monkeypatch, request_workspace)
        yield store


def payload():
    return {"document": {"id": "rag-synthetic", "title": "Synthetic maritime manual",
            "kind": "onboard", "reference": "Fictional reference", "version": "1",
            "reviewedAt": "2026-10-13", "language": "en", "sections": [
                {"page": 7, "heading": "페이지 7", "text": "1.1 Checks\n" + "Fictionalquartz equipment checks are required. " * 60},
                {"page": 9, "heading": "페이지 9", "text": "2 Records\nSyntheticamber records are retained."}]},
            "expectedId": "", "meta": {"scope": "all", "status": "active"}}


def post(client, headers, data):
    return client.post("/api/changes", headers=headers, json={"kind": "document.save", "payload": data})


def test_real_document_upload_search_revision_access_and_rollback(database):
    client = TestClient(main.app, base_url="http://localhost:5173")
    guest = TestClient(main.app, base_url="http://localhost:5173")
    guest_headers = {"X-Haedap-Token": guest.get("/api/health").json()["csrfToken"]}
    assert post(guest, guest_headers, payload()).status_code == 403
    headers = login(client)
    data = payload()
    assert post(client, headers, data).status_code == 200
    doc = next(d for d in client.get("/api/documents").json()["documents"] if d["logical_id"] == "rag-synthetic")
    original_id = doc["id"]
    assert len(doc["sections"]) > 2
    assert all(len(s["text"]) <= 900 for s in doc["sections"])
    evidence = guest.post("/api/search", headers=guest_headers, json={"question": "Syntheticamber"}).json()["evidence"]
    assert evidence and evidence[0]["document_id"] == original_id
    assert evidence[0]["page"] == 9 and evidence[0]["title"] == data["document"]["title"]
    assert evidence[0]["heading"] == "2 Records"
    answer = guest.post("/api/ask", headers=guest_headers, json={"question": "Fictionalquartz", "task": "documents"}).json()
    assert answer["statements"]
    for statement in answer["statements"]:
        source = next(e for e in answer["evidence"] if e["id"] == statement["chunkId"])
        assert statement["quote"] in source["text"]
    before = database.all("SELECT * FROM chunks WHERE document_id=%s ORDER BY position", (original_id,))
    data["expectedId"] = original_id
    assert post(client, headers, data).status_code == 200
    assert database.all("SELECT * FROM chunks WHERE document_id=%s ORDER BY position", (original_id,)) == before
    assert post(client, headers, payload()).status_code == 409  # stale expectedId
    # A real content revision gets new IDs; historical chunks stay intact.
    revised = deepcopy(data)
    revised["document"]["sections"][1]["text"] += " Revisedsynthetic requirement."
    assert post(client, headers, revised).status_code == 200
    new_id = database.one("SELECT id FROM documents WHERE logical_id='rag-synthetic' AND active")["id"]
    assert new_id != original_id
    assert database.all("SELECT * FROM chunks WHERE document_id=%s ORDER BY position", (original_id,)) == before
    revised["expectedId"] = new_id
    revised["meta"]["scope"] = "admin"
    assert post(client, headers, revised).status_code == 200
    assert guest.post("/api/search", headers=guest_headers, json={"question": "Revisedsynthetic"}).json()["evidence"] == []
    assert client.post("/api/search", headers=headers, json={"question": "Revisedsynthetic"}).json()["evidence"]
    assert guest.get(f"/api/documents/{new_id}/pdf").status_code == 403
    assert database.one("SELECT count(*) AS n FROM documents WHERE logical_id='rag-synthetic'")["n"] == 2
    # Restoring a previous revision reuses its exact original chunks and IDs.
    data["expectedId"] = new_id
    assert post(client, headers, data).json()["result"]["id"] == original_id
    assert database.all("SELECT * FROM chunks WHERE document_id=%s ORDER BY position", (original_id,)) == before
    removed = client.post("/api/changes", headers=headers,
                          json={"kind": "document.delete", "payload": {"id": original_id}})
    assert removed.status_code == 200
    assert client.post("/api/search", headers=headers, json={"question": "Fictionalquartz"}).json()["evidence"] == []
    # An invalid PDF discovered after chunk insertion must roll back the request.
    invalid = payload()
    invalid["document"]["id"] = "invalid-upload"
    invalid["file"] = {"name": "invalid.pdf", "base64": "not base64"}
    assert post(client, headers, invalid).status_code == 400
    assert database.one("SELECT count(*) AS n FROM documents WHERE logical_id='invalid-upload'")["n"] == 0


def test_legacy_same_hash_keeps_existing_chunks(database):
    # Simulate a pre-improvement document: same source/hash, different old chunking.
    data = payload()
    old_id = database.save_document(data)["id"]
    database.run("UPDATE chunks SET text='Legacy exact stored quote' WHERE document_id=%s", (old_id,))
    before = database.all("SELECT * FROM chunks WHERE document_id=%s ORDER BY position", (old_id,))
    data["expectedId"] = old_id
    assert database.save_document(data) == {"id": old_id, "status": "unchanged"}
    assert database.all("SELECT * FROM chunks WHERE document_id=%s ORDER BY position", (old_id,)) == before


def test_bm25_api_ranking_filters_and_original_citations(database):
    documents = []
    for name, content in [
        ("broad", "ballast inspection 평형수 검사 " + "navigation 항로 기록 " * 25),
        ("focused", "ballast inspection 평형수 검사 " * 4),
        *[(f"unrelated-{i}", "galley cooking 식당 조리") for i in range(6)],
    ]:
        data = payload()
        data["document"].update(id="bm25-" + name, title="Synthetic " + name,
                                sections=[{"page": 11, "heading": "Checks", "text": content}])
        identifier = database.save_document(data)["id"]
        documents.append((data, identifier))
    guest = TestClient(main.app, base_url="http://localhost:5173")
    headers = {"X-Haedap-Token": guest.get("/api/health").json()["csrfToken"]}
    for question in ("ballast inspection", "평형수 검사"):
        response = guest.post("/api/search", headers=headers, json={"question": question})
        assert response.status_code == 200
        evidence = response.json()["evidence"]
        assert [e["document_id"] for e in evidence[:2]] == [documents[1][1], documents[0][1]]
        first = evidence[0]
        assert first["title"] == "Synthetic focused" and first["page"] == 11
        assert first["heading"] == "Checks" and "score" not in first
        answer = guest.post("/api/ask", headers=headers,
                            json={"question": question, "task": "documents"}).json()
        assert answer["statements"][0]["chunkId"] == first["id"]
        assert answer["statements"][0]["quote"] == first["text"]
    assert guest.post("/api/search", headers=headers,
                      json={"question": "ballast", "filter": "imo"}).json()["evidence"] == []
    # Restrict the previously top-ranked document; it must disappear immediately.
    focused, focused_id = documents[1]
    focused["expectedId"] = focused_id
    focused["meta"]["scope"] = "admin"
    database.save_document(focused)
    result = guest.post("/api/search", headers=headers, json={"question": "ballast"}).json()["evidence"]
    assert [e["document_id"] for e in result] == [documents[0][1]]
    broad, broad_id = documents[0]
    broad["expectedId"] = broad_id
    broad["meta"]["status"] = "retired"
    database.save_document(broad)
    assert guest.post("/api/search", headers=headers, json={"question": "ballast"}).json()["evidence"] == []
