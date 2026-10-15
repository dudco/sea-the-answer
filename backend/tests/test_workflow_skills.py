"""Workflow contracts and opt-in transactional PostgreSQL integration tests."""

from copy import deepcopy
import os
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
import httpx
import pytest

from api import main, workflow_skills as skills
from api.errors import ApiError
from rag_postgres_support import configure_api, isolated_workspace

USER = {"id": "guest-1", "role": "guest"}
EVIDENCE = [
    {
        "id": "chunk-a",
        "document_id": "doc-a",
        "title": "검증용 가상 절차서",
        "version": "1",
        "page": 7,
        "text": "Fictionalquartz 점검 전 연료 기록을 확인한다.",
    }
]


def body(skill="selected-document-answer", **extra):
    return {"skill": skill, "question": "Fictionalquartz 확인 절차", **extra}


class MemoryStore:
    def __init__(self):
        self.writes = []
        self.calls = []

    def run(self, *args):
        self.writes.append(args)

    def audit(self, *args):
        pass

    def can_read_document(self, *args):
        return True

    def search(self, user, question, kind, document_ids=None):
        self.calls.append(document_ids)
        return deepcopy(EVIDENCE)


@pytest.mark.parametrize("skill", list(skills.DEFINITIONS))
def test_each_skill_is_discoverable_and_has_instructions(skill):
    assert skills.instructions(skill)
    assert any(v["id"] == skill for v in skills.catalog()["skills"])


@pytest.mark.parametrize(
    "extra",
    [
        {"skill": "../../arbitrary"},
        {"use_model": "yes"},
        {"year": True},
        {"document_ids": ["doc-a", "doc-a"]},
        {"sql": "DROP TABLE"},
        {"question": "   "},
        {"document_ids": [1]},
        {"context": {"ship": "x", "from": "x", "to": "y", "sql": "ignored"}},
    ],
)
def test_invalid_scopes_never_execute_or_store(extra):
    db = MemoryStore()
    with pytest.raises(ApiError):
        skills.run(db, USER, body(**extra))
    assert db.writes == [] and db.calls == []


@pytest.mark.parametrize("skill", list(skills.DEFINITIONS))
def test_missing_required_scope_is_explicit_without_model_or_data_access(
    monkeypatch, skill
):
    model = Mock(side_effect=AssertionError("Must not call model"))
    monkeypatch.setattr(skills.llm, "grounded_statements", model)
    db = MemoryStore()
    result = skills.run(db, USER, body(skill))
    assert result["status"] == "needs_input"
    assert not db.calls and not model.called


def test_selected_document_execution_preserves_scope_without_llm(monkeypatch):
    model = Mock(side_effect=AssertionError("No model"))
    monkeypatch.setattr(skills.llm, "grounded_statements", model)
    db = MemoryStore()
    result = skills.run(db, USER, body(document_ids=["doc-a"]))
    assert result["status"] == "evidence_found" and result["generation"] == "extractive"
    assert (
        db.calls == [["doc-a"]]
        and result["statements"][0]["quote"] == EVIDENCE[0]["text"]
    )
    assert not model.called and len(db.writes) == 2


def test_model_is_optional_and_falls_back_on_transport_failure(monkeypatch):
    monkeypatch.setattr(skills.config, "llm_settings", lambda: object())
    mock = Mock(side_effect=httpx.ConnectError("synthetic"))
    monkeypatch.setattr(skills.llm, "grounded_statements", mock)
    result = skills.run(
        MemoryStore(), USER, body(document_ids=["doc-a"], use_model=True)
    )
    assert (
        result["generation"] == "extractive"
        and "MODEL_FAILED_EXTRACTIVE_FALLBACK" in result["warnings"]
    )
    assert (
        "selected-document-answer" not in mock.call_args.kwargs["skill_instructions"]
    )  # body rather than frontmatter
    assert "선택 문서" in mock.call_args.kwargs["skill_instructions"]


def test_checklist_items_start_unchecked_and_keep_citations():
    r = skills.run(MemoryStore(), USER, body("checklist", document_ids=["doc-a"]))
    assert (
        len(r["result"]["items"]) == 1 and r["result"]["items"][0]["checked"] is False
    )
    assert r["result"]["items"][0]["chunkId"] == "chunk-a"


def test_short_source_text_does_not_make_an_invalid_citation():
    request = skills.SkillRequest(**body(document_ids=["doc-a"]))
    evidence = [{**EVIDENCE[0], "text": "점검"}]
    statements, generation = skills.evidence_statements(
        request, evidence, request.skill, []
    )
    assert statements == [] and generation == "extractive"


def test_model_abstention_keeps_original_evidence_for_review(monkeypatch):
    monkeypatch.setattr(skills.config, "llm_settings", lambda: object())
    monkeypatch.setattr(skills.llm, "grounded_statements", lambda *args, **kwargs: [])
    result = skills.run(
        MemoryStore(), USER, body(document_ids=["doc-a"], use_model=True)
    )
    assert result["status"] == "insufficient_evidence" and result["generation"] == "llm"
    assert result["evidence"] == EVIDENCE and result["statements"] == []
    assert "AI가" in result["notice"]


def test_invalid_maritime_configuration_returns_safe_error_before_writes(monkeypatch):
    from sqlalchemy.exc import ArgumentError
    from tools import api as tool_api

    monkeypatch.setattr(
        tool_api,
        "create_engine_for",
        Mock(side_effect=ArgumentError("synthetic-private-dsn")),
    )
    db = MemoryStore()
    db.one = lambda *args: {"id": "app-ship"}
    with pytest.raises(ApiError) as error:
        skills.run(
            db, USER, body("mrv-analysis", context={"ship": "app-ship"}, year=2018)
        )
    assert error.value.status == 503
    assert "synthetic-private-dsn" not in error.value.message
    assert not db.writes


def test_decimal_summary_coverage_and_sample_are_not_invented():
    rows = [
        {
            "id": "r1",
            "version": 1,
            "date": "2026-01-01",
            "fuel": 0.1,
            "factor": 3.114,
            "distance": 10,
            "speed": 8,
        },
        {
            "id": "r2",
            "version": 1,
            "date": "2026-01-03",
            "fuel": 0.2,
            "factor": 3.114,
            "distance": 20,
            "speed": 10,
        },
    ]
    db = SimpleNamespace(
        operation_summary=lambda scope: {
            "rows": rows,
            "from": scope["from"],
            "to": scope["to"],
            "ship": {"name": "가상", "dwt": 100},
            "sample": True,
        }
    )
    request = skills.SkillRequest(
        **body(
            "operation-summary",
            context={"ship": "s", "from": "2026-01-01", "to": "2026-01-03"},
        )
    )
    result = skills.operation_result(db, request)
    assert result["fuel_t"] == "0.300000" and result["calculated_co2_t"] == "0.934200"
    assert (
        result["reported_days"] == 2
        and result["missing_days"] == 1
        and result["sample"]
    )
    assert (
        result["mean_record_speed_kn"] == "9.000000" and result["official_cii"] is None
    )


@pytest.mark.parametrize(
    "start,end",
    [("2026-01-02", "2026-01-01"), ("bad", "2026-01-01"), ("2020-01-01", "2026-01-01")],
)
def test_summary_rejects_invalid_or_excessive_period(start, end):
    request = skills.SkillRequest(
        **body("operation-summary", context={"ship": "s", "from": start, "to": end})
    )
    with pytest.raises(ApiError):
        skills.period(request)


@pytest.fixture
def database(monkeypatch):
    dsn = os.getenv("HAEDAP_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("HAEDAP_TEST_DATABASE_URL not configured")
    with isolated_workspace(dsn) as (store, request_workspace):
        configure_api(monkeypatch, request_workspace)
        yield store


def client_headers():
    client = TestClient(main.app, base_url="http://localhost:5173")
    data = client.get("/api/health").json()
    return client, {"X-Haedap-Token": data["csrfToken"]}


def save_doc(db, name, text, scope="all"):
    return db.save_document(
        {
            "document": {
                "id": name,
                "title": name,
                "kind": "onboard",
                "reference": "synthetic",
                "version": "1",
                "reviewedAt": "2026-10-15",
                "language": "ko",
                "sections": [{"page": 7, "heading": "Synthetic", "text": text}],
            },
            "expectedId": "",
            "meta": {"scope": scope, "status": "active"},
        }
    )["id"]


def test_postgres_selected_document_scope_and_permission_before_ranking(database):
    a = save_doc(
        database, "skill-allowed", "Fictionalquartz 선택 문서에 있는 절차입니다."
    )
    b = save_doc(
        database,
        "skill-distractor",
        "Fictionalquartz 다른 문서에만 있는 Secretamber 수치 9999입니다.",
    )
    locked = save_doc(
        database, "skill-admin", "Fictionalquartz 관리자만 보는 문서입니다.", "admin"
    )
    client, headers = client_headers()
    response = client.post(
        "/api/skills/run", headers=headers, json=body(document_ids=[a])
    )
    assert response.status_code == 200
    answer = response.json()
    assert answer["evidence"] and {e["document_id"] for e in answer["evidence"]} == {a}
    assert "9999" not in str(answer)
    empty = client.post(
        "/api/skills/run",
        headers=headers,
        json={**body(document_ids=[a]), "question": "Secretamber"},
    )
    assert (
        empty.json()["status"] == "insufficient_evidence"
        and empty.json()["evidence"] == []
    )
    forbidden = client.post(
        "/api/skills/run", headers=headers, json=body(document_ids=[locked])
    )
    assert forbidden.status_code == 403
    assert (
        client.post("/api/skills/run", json=body(document_ids=[a])).status_code == 403
    )  # CSRF still required
    direct = database.search(
        {"role": "guest"}, "Fictionalquartz", "all", document_ids=[a]
    )
    assert {e["document_id"] for e in direct} == {a} and b not in {
        e["document_id"] for e in direct
    }


@pytest.mark.parametrize("template", ["mrv", "noon"])
def test_postgres_report_is_preview_until_explicit_save_and_qa_is_owned(database, template):
    database.change(
        {"id": "admin", "role": "admin"},
        "ship.save",
        {
            "id": "skills-ship",
            "name": "가상 선박",
            "type": "Bulk carrier",
            "dwt": 1000,
            "sample": True,
        },
    )
    database.change(
        {"id": "admin", "role": "admin"},
        "operation.save",
        {
            "ship": "skills-ship",
            "date": "2026-01-01",
            "fuel": 2,
            "factor": 3.114,
            "distance": 100,
            "speed": 10,
            "fuelType": "가상 연료",
            "version": 0,
            "sample": True,
        },
    )
    client, headers = client_headers()
    before = database.one("SELECT count(*) AS n FROM reports")["n"]
    response = client.post(
        "/api/skills/run",
        headers=headers,
        json=body(
            "report-draft",
            template=template,
            context={"ship": "skills-ship", "from": "2026-01-01", "to": "2026-01-03"},
        ),
    )
    assert response.status_code == 200
    answer = response.json()
    assert answer["result"]["missing_days"] == (2 if template == "mrv" else 0)
    assert answer["result"]["sample"] is True
    assert database.one("SELECT count(*) AS n FROM reports")["n"] == before
    saved = client.post("/api/reports", headers=headers, json=answer["result"]["draft"])
    assert saved.status_code == 200 and saved.json()["report"]["status"] == "draft"
    assert database.one("SELECT count(*) AS n FROM reports")["n"] == before + 1
    metadata = saved.json()["report"]["body"]
    assert metadata["ship"] == "skills-ship" and metadata["template"] == template
    assert metadata["from"] == "2026-01-01"
    assert metadata["to"] == ("2026-01-03" if template == "mrv" else "2026-01-01")
    assert metadata["scope"]["to"] == "2026-01-03"  # Original requested range is retained.
    evaluated = client.post(
        "/api/skills/run",
        headers=headers,
        json=body("qa-evaluation", answer_id=answer["id"]),
    )
    assert (
        evaluated.status_code == 200
        and evaluated.json()["result"]["checks"][-1]["status"]
        == "manual_review_required"
    )
    other, other_headers = client_headers()
    assert (
        other.post(
            "/api/skills/run",
            headers=other_headers,
            json=body("qa-evaluation", answer_id=answer["id"]),
        ).status_code
        == 404
    )


def test_postgres_evaluation_detects_forged_citation(database):
    a = save_doc(
        database, "skill-eval", "Fictionalquartz 인용을 검증하는 가상 문서입니다."
    )
    client, headers = client_headers()
    answer = client.post(
        "/api/skills/run", headers=headers, json=body(document_ids=[a])
    ).json()
    corrupted = deepcopy(answer)
    corrupted["statements"][0]["quote"] = "실제 문서에는 없는 가상의 구절입니다."
    from psycopg.types.json import Jsonb

    database.run(
        "UPDATE queries SET response=%s WHERE id=%s", (Jsonb(corrupted), answer["id"])
    )
    check = client.post(
        "/api/skills/run",
        headers=headers,
        json=body("qa-evaluation", answer_id=answer["id"]),
    ).json()
    assert check["result"]["status"] == "fail"
    assert check["result"]["checks"][0]["status"] == "fail"
