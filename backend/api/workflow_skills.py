"""Six fixed, authenticated workflows. Models may phrase evidence, never change scope."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from typing import Literal
from uuid import uuid4
import re
import os

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from psycopg.types.json import Jsonb

from . import config, llm
from .errors import ApiError, require
from .validation import utc_now

DEFINITIONS = {
    "mrv-analysis": (
        "MRV 참고 탄소집약도 분석",
        "선택 선박의 MRV와 공개 DWT 후보로 참고값을 계산합니다.",
    ),
    "selected-document-answer": (
        "선택 문서 기반 답변",
        "선택한 문서 안에서만 질문의 근거를 찾습니다.",
    ),
    "operation-summary": (
        "운항 실적 요약",
        "앱 일별 운항기록의 연료·배출량·거리를 요약합니다.",
    ),
    "report-draft": (
        "보고서 초안 작성",
        "운항자료와 선택 문서로 검토용 초안을 만듭니다. 저장은 별도입니다.",
    ),
    "checklist": (
        "점검 체크리스트 생성",
        "선택 문서의 근거로 확인 항목 초안을 만듭니다.",
    ),
    "qa-evaluation": (
        "질의·응답 평가",
        "내 저장 응답의 인용·범위·참고값 계약을 검사합니다.",
    ),
}
SkillID = Literal[
    "mrv-analysis",
    "selected-document-answer",
    "operation-summary",
    "report-draft",
    "checklist",
    "qa-evaluation",
]
VERSION = "HAEDAP-SKILLS-1.0"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Context(Strict):
    ship: str = Field(default="", max_length=100)
    # Keep JSON date input explicit and validate only for workflows using it.
    start: str = Field(default="", alias="from", max_length=10)
    end: str = Field(default="", alias="to", max_length=10)


class SkillRequest(Strict):
    skill: SkillID
    question: str = Field(min_length=1, max_length=2000)
    document_ids: list[str] = Field(default_factory=list, max_length=20)
    context: Context = Field(default_factory=Context)
    year: int | None = Field(default=None, ge=1900, le=2100)
    use_model: bool = False
    answer_id: str = Field(default="", max_length=100)
    template: Literal["noon", "mrv"] = "mrv"


@lru_cache(maxsize=6)
def instructions(skill):
    # Only a validated catalogue ID is converted to a path.
    require(skill in DEFINITIONS, "알 수 없는 스킬입니다.")
    content = (config.BACKEND_DIR / "knowledge/skills" / skill / "SKILL.md").read_text(
        encoding="utf-8"
    )
    require(
        content.startswith("---\n"),
        "스킬 지침을 읽을 수 없습니다.",
        "SKILL_RESOURCE_INVALID",
        503,
    )
    return content.split("---", 2)[2].strip()


def catalog():
    return {
        "version": VERSION,
        "skills": [
            {
                "id": k,
                "name": v[0],
                "description": v[1],
                "optional_model": k
                in {"selected-document-answer", "checklist", "report-draft"},
                "version": VERSION,
            }
            for k, v in DEFINITIONS.items()
        ],
    }


def decimal_text(number):
    return str(
        Decimal(str(number)).quantize(Decimal(".000001"), rounding=ROUND_HALF_UP)
    )


def period(body):
    require(
        bool(body.context.ship and body.context.start and body.context.end),
        "선박과 시작일·종료일을 선택해 주세요.",
    )
    try:
        start, end = (
            date.fromisoformat(body.context.start),
            date.fromisoformat(body.context.end),
        )
    except ValueError as exc:
        raise ApiError(400, "INVALID_INPUT", "기간을 확인해 주세요.") from exc
    require(
        0 <= (end - start).days <= 366,
        "기간은 시작부터 최대 366일 차이로 선택해 주세요.",
    )
    return {"ship": body.context.ship, "from": start.isoformat(), "to": end.isoformat()}


def operation_result(db, body):
    scope = period(body)
    raw = db.operation_summary(scope)
    if body.skill == "report-draft" and body.template == "noon" and raw["rows"]:
        day = raw["rows"][-1]["date"]
        raw = db.operation_summary({"ship": scope["ship"], "from": day, "to": day})
    rows = raw["rows"]
    fuel = sum((Decimal(str(r["fuel"])) for r in rows), Decimal(0))
    emission = sum(
        (Decimal(str(r["fuel"])) * Decimal(str(r["factor"])) for r in rows), Decimal(0)
    )
    distance = sum((Decimal(str(r["distance"])) for r in rows), Decimal(0))
    dates = {r["date"] for r in rows}
    count_days = (
        date.fromisoformat(raw["to"]) - date.fromisoformat(raw["from"])
    ).days + 1
    dwt = Decimal(str(raw["ship"]["dwt"]))
    return {
        "ship": raw["ship"],
        "from": raw["from"],
        "to": raw["to"],
        "count": len(rows),
        "fuel_t": decimal_text(fuel),
        "calculated_co2_t": decimal_text(emission),
        "distance_nm": decimal_text(distance),
        "period_dwt_intensity": decimal_text(emission * 1000000 / (dwt * distance))
        if distance > 0 and dwt > 0
        else None,
        "mean_record_speed_kn": decimal_text(
            sum((Decimal(str(r["speed"])) for r in rows), Decimal(0)) / len(rows)
        )
        if rows
        else None,
        "sample": raw["sample"],
        "reported_days": len(dates),
        "calendar_days": count_days,
        "missing_days": count_days - len(dates),
        "official_cii": None,
        "official_cii_rating": None,
        "records": [
            {
                "id": r["id"],
                "version": r["version"],
                "date": r["date"],
                "fuel_t": str(r["fuel"]),
                "factor": str(r["factor"]),
                "distance_nm": str(r["distance"]),
            }
            for r in rows
        ],
        "units": {
            "fuel_t": "t",
            "calculated_co2_t": "t CO2",
            "distance_nm": "nm",
            "period_dwt_intensity": "gCO2/(DWT t * nm)",
        },
        "notice": "앱 일별 기록의 집계입니다. 공개 연간 MRV나 공식 CII 결과와 구분합니다. 속력은 기록별 단순 평균입니다.",
    }


def selected_evidence(db, user, body, required=True):
    if not body.document_ids:
        require(not required, "사용할 문서를 선택해 주세요.")
        return []
    return db.search(user, body.question, "all", document_ids=body.document_ids)


def evidence_statements(body, evidence, skill, warnings):
    statements = [
        {"text": e["text"], "chunkId": e["id"], "quote": e["text"]}
        for e in evidence[:5]
        if len(e["text"].strip()) >= 8
    ]
    generation = "extractive"
    if body.use_model and evidence:
        settings = config.llm_settings()
        if settings is None:
            warnings.append("MODEL_NOT_CONFIGURED")
        else:
            try:
                statements = llm.grounded_statements(
                    body.question,
                    evidence,
                    "ko",
                    settings,
                    skill_instructions=instructions(skill),
                )
                generation = "llm"
            except (ValueError, KeyError, httpx.HTTPError):
                warnings.append("MODEL_FAILED_EXTRACTIVE_FALLBACK")
    # Both deterministic output and model output must remain within the server evidence.
    llm.validate_statements(
        {"insufficient": not statements, "statements": statements}, evidence
    )
    return statements, generation


def evaluate_saved_answer(db, user, answer_id):
    require(bool(answer_id), "평가할 내 질의 이력을 선택해 주세요.")
    row = db.one(
        """SELECT q.response FROM queries q JOIN query_owner o ON o.id=q.id
                 WHERE q.id=%s AND o.owner=%s""",
        (answer_id, user["id"]),
    )
    require(row, "본인의 평가 가능한 질의가 없습니다.", "NOT_FOUND", 404)
    answer = row["response"]
    evidence = answer.get("evidence", [])
    require(
        all(db.can_read_document(user, e["document_id"]) for e in evidence),
        "평가 대상의 문서 열람 권한을 확인해 주세요.",
        "FORBIDDEN",
        403,
    )
    checks = []

    def add(name, status, detail):
        checks.append({"check": name, "status": status, "detail": detail})

    statements = answer.get("statements", [])
    if statements:
        try:
            llm.validate_statements(
                {"insufficient": False, "statements": statements}, evidence
            )
            add("인용 원문·청크 일치", "pass", "인용 구절이 저장된 근거에 존재합니다.")
        except (ValueError, KeyError, TypeError):
            add("인용 원문·청크 일치", "fail", "근거와 일치하지 않는 인용이 있습니다.")
    else:
        add("인용 원문·청크 일치", "not_applicable", "문서 인용이 없는 응답입니다.")
    ids = answer.get("document_ids")
    if ids:
        add(
            "선택 문서 범위",
            "pass" if all(e["document_id"] in ids for e in evidence) else "fail",
            "선택 문서 ID와 근거의 문서 ID를 대조합니다.",
        )
    else:
        add("선택 문서 범위", "not_applicable", "특정 문서로 제한한 응답이 아닙니다.")
    result = answer.get("result", {})
    if answer.get("skill", {}).get("id") == "mrv-analysis" and "official_cii" in result:
        from tools.reference_intensity import (
            ReferenceIntensityRequest,
            compute_reference,
        )

        try:
            expected = compute_reference(
                result["input_snapshot"],
                result.get("capacity_reference"),
                ReferenceIntensityRequest(**result["request_snapshot"]),
            )
            same = (
                result.get("status") == expected["status"]
                and result.get("reference_dwt_intensity")
                == expected["reference_dwt_intensity"]
                and result.get("official_cii") is None
                and result.get("official_cii_rating") is None
                and result.get("reference_only") is True
            )
            add(
                "MRV 참고 계산 계약",
                "pass" if same else "fail",
                "저장된 입력 스냅샷으로 기존 계산 Tool을 다시 실행했습니다. 원본 사실성 검증은 아닙니다.",
            )
        except (ValueError, KeyError, TypeError, ValidationError):
            add("MRV 참고 계산 계약", "fail", "계산 스냅샷 계약을 검증할 수 없습니다.")
    else:
        add("MRV 참고 계산 계약", "not_applicable", "MRV 참고 계산 응답이 아닙니다.")
    add(
        "의미적 정답성·규정 적용성",
        "manual_review_required",
        "원문 내용과 질문의 의미를 사람이 검토해야 합니다. 자동 정답 점수가 아닙니다.",
    )
    return {
        "answer_id": answer_id,
        "checks": checks,
        "status": "fail"
        if any(c["status"] == "fail" for c in checks)
        else "review_required",
        "notice": "저장된 응답의 구조·인용·범위·계산 일관성 점검입니다. 전체 정답성 평가는 별도입니다.",
    }


def run(db, user, payload):
    try:
        body = SkillRequest.model_validate(payload)
    except ValidationError as exc:
        raise ApiError(
            400, "INVALID_INPUT", "스킬 입력 필드·자료형·범위를 확인해 주세요."
        ) from exc
    require(bool(body.question.strip()), "질문을 입력해 주세요.")
    require(
        all(isinstance(i, str) and 0 < len(i) <= 200 for i in body.document_ids)
        and len(set(body.document_ids)) == len(body.document_ids),
        "문서 ID를 확인해 주세요.",
    )
    instructions(body.skill)
    answer = {
        "id": str(uuid4()),
        "question": body.question,
        "task": "documents",
        "language": "ko",
        "generation": "workflow",
        "status": "completed",
        "notice": "선택한 업무 스킬을 실행했습니다.",
        "warnings": [],
        "statements": [],
        "evidence": [],
        "toolRuns": [],
        "reportSuggested": False,
        "document_ids": body.document_ids,
        "skill": {
            "id": body.skill,
            "name": DEFINITIONS[body.skill][0],
            "version": VERSION,
        },
        "result": {},
    }
    if body.skill in {"selected-document-answer", "checklist"}:
        if not body.document_ids:
            answer.update(status="needs_input", notice="사용할 문서를 선택해 주세요.")
        else:
            evidence = selected_evidence(db, user, body)
            statements, generation = evidence_statements(
                body, evidence, body.skill, answer["warnings"]
            )
            answer.update(
                evidence=evidence,
                statements=statements,
                generation=generation,
                status="evidence_found" if statements else "insufficient_evidence",
                notice=(
                    "선택한 문서의 근거만 사용했습니다."
                    if statements
                    else "AI가 선택 문서만으로 답변하기에 근거가 부족하다고 판단했습니다. 검색된 원문을 확인해 주세요."
                    if evidence and generation == "llm"
                    else "선택한 문서에서 답변 근거를 찾지 못했습니다."
                ),
            )
            if body.skill == "checklist":
                answer["result"] = {
                    "items": [
                        {
                            "text": "확인할 원문: " + s["text"],
                            "chunkId": s["chunkId"],
                            "quote": s["quote"],
                            "checked": False,
                        }
                        for s in statements
                    ],
                    "notice": "원문에 기반한 점검 항목 초안입니다. 필수 점검항목의 완전성이나 규정 적용을 확정하지 않습니다.",
                }
    elif body.skill in {"operation-summary", "report-draft"}:
        if not (body.context.ship and body.context.start and body.context.end):
            answer.update(
                status="needs_input", notice="선박과 시작일·종료일을 선택해 주세요."
            )
        else:
            result = operation_result(db, body)
            answer["result"] = result
            answer["notice"] = result["notice"]
            if not result["count"]:
                answer.update(
                    status="insufficient_evidence",
                    notice="선택 기간의 운항 기록이 없습니다.",
                )
            if result["sample"]:
                answer["warnings"].append("SYNTHETIC_OR_SAMPLE_OPERATIONS")
            if result["missing_days"]:
                answer["warnings"].append("PERIOD_HAS_UNREPORTED_DAYS")
            if body.skill == "report-draft" and result["count"]:
                evidence = selected_evidence(db, user, body, required=False)
                statements, generation = evidence_statements(
                    body, evidence, body.skill, answer["warnings"]
                )
                answer.update(
                    evidence=evidence, statements=statements, generation=generation
                )
                lines = [
                    "# 검토용 "
                    + ("Noon" if body.template == "noon" else "MRV")
                    + " 보고서 초안",
                    "선박: " + result["ship"]["name"],
                    f"기간: {result['from']} ~ {result['to']}",
                    "자료: 앱 일별 운항기록"
                    + (" (가상 예시 포함)" if result["sample"] else ""),
                    "연료: " + result["fuel_t"] + " t",
                    "계산 CO2: " + result["calculated_co2_t"] + " t CO2",
                    "거리: " + result["distance_nm"] + " nm",
                    f"보고일 {result['reported_days']} / 달력일 {result['calendar_days']}",
                    "공식 CII·등급: 산출하지 않음",
                    "이 초안은 공식 MRV 제출물 또는 승인된 보고서가 아닙니다.",
                ]
                if statements:
                    lines += ["", "## 선택 문서 근거"]
                    by_id = {e["id"]: e for e in evidence}
                    for st in statements:
                        e = by_id[st["chunkId"]]
                        lines += [
                            st["text"],
                            f"근거: {e['title']} / {e['version']} / 페이지 {e.get('page') or '미제공'} / {e['id']}",
                        ]
                result["draft"] = {
                    "title": (result["ship"]["name"] + " · 검토용 보고서")[:120],
                    "type": "일일 운항" if body.template == "noon" else "배출량 검토",
                    "text": "\n".join(lines),
                    "sources": list(dict.fromkeys(e["document_id"] for e in evidence)),
                    "version": 0,
                    "body": {
                        "skill": body.skill,
                        "template": body.template,
                        "ship": result["ship"]["id"],
                        "from": result["from"],
                        "to": result["to"],
                        "scope": body.context.model_dump(by_alias=True),
                        "recordIds": [
                            {"id": r["id"], "version": r["version"]}
                            for r in result["records"]
                        ],
                        "sample": result["sample"],
                    },
                }
    elif body.skill == "mrv-analysis":
        if not body.context.ship or body.year is None:
            answer.update(
                status="needs_input", notice="앱 선박과 MRV 보고연도를 선택해 주세요."
            )
        else:
            require(
                db.one("SELECT id FROM ships WHERE id=%s", (body.context.ship,)),
                "선택한 앱 선박이 없습니다.",
            )
            url = os.getenv("MARITIME_DATA_DATABASE_URL") or config.database_url()
            from tools.api import create_engine_for
            from tools.reference_intensity import (
                ReferenceIntensityRequest,
                calculate_reference,
            )
            from sqlalchemy import text
            from sqlalchemy.exc import SQLAlchemyError

            engine = None
            try:
                engine = create_engine_for(url)
                with engine.connect() as conn, conn.begin():
                    conn.execute(text("SET TRANSACTION READ ONLY"))
                    conn.execute(text("SET LOCAL statement_timeout='5s'"))
                    candidates = (
                        conn.execute(
                            text(
                                "SELECT vessel_id,imo_number FROM maritime_data.vessels WHERE ship_id=:ship AND data_origin='REAL'"
                            ),
                            {"ship": body.context.ship},
                        )
                        .mappings()
                        .all()
                    )
                if len(candidates) != 1:
                    answer.update(
                        status="needs_input",
                        notice="이 앱 선박과 실제 MRV 선박의 명시적 연결이 필요합니다.",
                    )
                else:
                    app_ship = db.one(
                        "SELECT body FROM ships WHERE id=%s", (body.context.ship,)
                    )["body"]
                    imo = re.sub(
                        r"^IMO\s*", "", str(app_ship.get("imo", "")).strip(), flags=re.I
                    )
                    require(
                        not app_ship.get("sample")
                        and imo == candidates[0]["imo_number"],
                        "앱 선박과 MRV 선박의 정체성이 일치하지 않습니다. 연결을 검토해 주세요.",
                        "MARITIME_SHIP_IDENTITY_CONFLICT",
                        409,
                    )
                    request = ReferenceIntensityRequest(
                        scope={
                            "dataset": "real_annual",
                            "vessel_id": candidates[0]["vessel_id"],
                            "year": body.year,
                        },
                        accept_reference_limitations=True,
                    )
                    result = calculate_reference(engine, request)
                    answer.update(
                        result=result,
                        status=result["status"],
                        notice="공개 DWT 후보·추정거리 기반 MRV 참고값입니다. 공식 CII가 아닙니다.",
                    )
                    answer["warnings"] += result["warnings"]
            except HTTPException as exc:
                raise ApiError(
                    exc.status_code,
                    "DATA_SOURCE_UNAVAILABLE"
                    if exc.status_code == 503
                    else "INVALID_INPUT",
                    str(exc.detail),
                ) from exc
            except SQLAlchemyError as exc:
                raise ApiError(
                    503,
                    "DATA_SOURCE_UNAVAILABLE",
                    "해사 DB·migration·원본·선박 연결 상태를 확인해 주세요.",
                ) from exc
            finally:
                if engine is not None:
                    engine.dispose()
    else:
        if not body.answer_id:
            answer.update(
                status="needs_input", notice="평가할 내 질의 이력을 선택해 주세요."
            )
        else:
            answer["result"] = evaluate_saved_answer(db, user, body.answer_id)
            answer["notice"] = answer["result"]["notice"]
    # Access can change while optional model requests are in progress.
    require(
        all(db.can_read_document(user, e["document_id"]) for e in answer["evidence"]),
        "문서 권한이 변경되었습니다. 다시 실행해 주세요.",
        "FORBIDDEN",
        403,
    )
    db.run(
        "INSERT INTO queries VALUES(%s,%s,%s,%s)",
        (answer["id"], body.question, Jsonb(answer), utc_now()),
    )
    db.run("INSERT INTO query_owner VALUES(%s,%s)", (answer["id"], user["id"]))
    db.audit(
        user,
        "skill",
        "업무 스킬 실행",
        answer["id"],
        {"skill": body.skill, "status": answer["status"], "version": VERSION},
    )
    return answer
