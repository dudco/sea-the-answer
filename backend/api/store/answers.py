"""Integrated answers (/api/ask), optional grounded LLM statements, criterion checks, history."""

from __future__ import annotations

import re
from time import monotonic
from uuid import uuid4

import httpx
from psycopg.types.json import Jsonb

from .. import config, llm
from ..question_intent import definition_request
from ..answer_presentation import (UnsupportedMetric, excerpt_table, operation_presentation, output_format,
                                   wants_operation_table)
from ..errors import require
from ..validation import number, stamp, text, utc_now


class AnswerStore:
    def compare_criterion(self, user: dict, criterion: dict | None, summary: dict) -> dict:
        unknown = {"status": "unknown", "label": "판단 불가", "reason": "검증한 기준과 적용 조건이 지정되지 않았습니다."}
        if not criterion:
            return unknown
        require(criterion.get("confirmed") is True, "기준 적용 조건을 확인해 주세요.")
        doc_id, chunk_id = criterion.get("documentId"), criterion.get("chunkId")
        require(doc_id in self.allowed_document_ids(user), "열람 가능한 적용 문서가 필요합니다.", "FORBIDDEN", 403)
        chunk = self.one("SELECT text FROM chunks WHERE id=%s AND document_id=%s", (chunk_id, doc_id))
        quote = criterion.get("quote")
        require(chunk and isinstance(quote, str) and len(quote) >= 8 and quote in chunk["text"], "기준 원문 구절을 확인해 주세요.")
        metric, operator = criterion.get("metric"), criterion.get("operator")
        require(metric in ("fuel", "emission", "intensity", "speed") and operator in ("lte", "gte"), "비교 조건을 확인해 주세요.")
        limit = number(criterion.get("limit"), "기준값", 0, 1e12)
        actual = summary[metric]
        if not summary["count"] or actual is None:
            return {**unknown, "reason": "해당 기간에 비교 가능한 운항 데이터가 없습니다."}
        passed = actual <= limit if operator == "lte" else actual >= limit
        return {"status": "met" if passed else "unmet", "label": "입력 기준 충족" if passed else "입력 기준 미충족",
                "actual": actual, "limit": limit, "rule": criterion,
                "reason": "사용자가 확인·입력한 단일 기준과의 수치 비교입니다. 공식 판정은 아닙니다."}

    def answer(self, user: dict, payload: dict) -> dict:
        started = monotonic()
        question = text(payload.get("question"), "질문", 2000)
        language = payload.get("language", "auto")
        require(language in ("auto", "ko", "en"), "언어를 확인해 주세요.")
        language = "ko" if language == "auto" and re.search(r"[가-힣]", question) else "en" if language == "auto" else language
        mode = payload.get("mode", "extractive")
        require(mode in ("extractive", "llm"), "답변 모드를 확인해 주세요.")
        task = payload.get("task", "auto")
        require(task in ("auto", "documents", "operations", "integrated", "report"), "질문 유형을 확인해 주세요.")
        requested = payload.get("outputFormat", "auto")
        require(isinstance(requested, str) and requested in ("auto", "text", "table", "chart"), "출력 형식을 확인해 주세요.")
        kind = output_format(question, requested)
        en = language == "en"
        notices = []
        needs_ops = task in ("operations", "integrated", "report") or task == "auto" and bool(re.search(
            r"운항|연료|배출|거리|속력|선박|항차|추이|계산|보고서|noon|mrv|vessel|ship|fuel|emission|distance|speed|report", question, re.I))
        needs_ops = needs_ops or kind == "chart" and task != "documents"
        if task == 'auto' and definition_request(question):
            needs_ops = False
        retrieval_started = monotonic()
        evidence = [] if task == "operations" else self.search(user, question, payload.get("filter", "all"))
        retrieval_ms = max(0, (monotonic() - retrieval_started) * 1000)
        statements = [{"text": item["text"], "chunkId": item["id"], "quote": item["text"]} for item in evidence[:3]]
        warnings = []
        generation = "extractive"
        generation_ms = 0
        presentation = None
        runs = []
        if payload.get("calculation") is not None:
            runs.append(self.calculate_emissions(payload["calculation"]))
        summary = None
        notice = "검색된 문단을 그대로 표시합니다. 인용과 적용 조건을 확인하세요."
        operation_notice = None
        compliance = None
        if needs_ops:
            context = payload.get("context") or {}
            if not context.get("ship") or not context.get("from") or not context.get("to"):
                operation_notice = "운항 분석을 위해 선박과 기간을 선택해 주세요."
                warnings.append("OPERATIONS_CONTEXT_REQUIRED")
            else:
                summary = self.operation_summary(context)
                compliance = self.compare_criterion(user, payload.get("criterion"), summary)
                if not summary["count"]:
                    warnings.append("OPERATIONS_NOT_FOUND")
        operation_table = kind == "table" and needs_ops and wants_operation_table(question, task)
        if kind == "chart" or operation_table:
            try:
                presentation = operation_presentation(summary, kind, question, language)
            except UnsupportedMetric:
                notices.append("Charts support recorded fuel, CO₂ emissions, distance or speed. Official CII ratings and other metrics are unavailable." if en else
                               "차트는 실제 운항 기록의 연료·CO₂ 배출량·거리·속력만 지원합니다. 공식 CII 등급이나 다른 지표는 표시할 수 없습니다.")
            except (ValueError, KeyError, TypeError, OverflowError):
                notices.append("The selected records contain invalid chart/table values." if en else
                               "선택한 운항 기록의 수치를 확인할 수 없어 표·차트를 표시하지 않습니다.")
            if presentation is None and not notices:
                notices.append("Select a ship and period with saved operation records for this table/chart." if en else
                               "표·차트를 표시하려면 선박·기간을 선택하고 해당 운항 기록을 준비해 주세요.")
        elif kind == "unsupported":
            notices.append("New figures and diagrams are not supported. Open the original document to inspect its figures." if en else
                           "새 그림·도식 생성과 원문 그림 자동 추출은 지원하지 않습니다. 기존 원문 열람으로 확인해 주세요.")

        # Observability describes the exact user-message projection, not token counts.
        selected, stats = llm.bound_evidence(question, evidence)
        stats["modelCallAttempted"] = False
        failure=None
        settings=config.llm_settings()
        generation_limit=getattr(settings,'generation_timeout',25)
        generation_budget=generation_limit+3
        if mode == "llm" and evidence and kind not in {"chart", "unsupported"} and not operation_table:
            if not config.llm_configured():
                warnings.append("MODEL_NOT_CONFIGURED")
                failure={'code':'MODEL_NOT_CONFIGURED','retryable':False}
            elif not selected:
                warnings.append("MODEL_INPUT_TOO_LARGE")
                notices.append("No complete source fits the model byte budget; showing source excerpts." if en else
                               "참고할 원문이 답변 입력 한도보다 커서 원문 발췌를 표시합니다. 질문 범위를 좁혀 주세요.")
            elif generation_budget - (monotonic() - started) < 1:
                warnings.append("MODEL_TIME_BUDGET_EXHAUSTED")
                notices.append("Search and preceding work used the generation budget; showing source excerpts." if en else
                               "검색·선행 처리 후 남은 생성 시간이 부족해 원문 발췌를 표시합니다.")
            else:
                timeout = min(generation_limit, generation_budget - (monotonic() - started))
                generation_started = monotonic()
                diagnostics = {}
                try:
                    result = self.grounded_response(question, evidence, language, output_format="table" if kind == "table" else "text",
                                                    timeout=timeout, diagnostics=diagnostics)
                    statements = result["statements"]
                    presentation = result.get("presentation")
                    generation = "llm"
                except (ValueError, KeyError, TypeError, httpx.HTTPError) as exc:
                    warnings.append("MODEL_FAILED_EXTRACTIVE_FALLBACK")
                    failure=llm.failure_details(exc)
                    if kind == "table":
                        notices.append("The model table could not be verified; showing cited source excerpts." if en else
                                       "모델 표의 형식·인용을 검증하지 못해 근거 원문 발췌 표를 표시합니다.")
                finally:
                    generation_ms = max(0, (monotonic() - generation_started) * 1000)
                    stats = {key: diagnostics.get(key, stats[key]) for key in stats}
        if mode == "llm" and stats["omittedEvidence"]:
            notices.append("Some complete sources were omitted from model input to respect the byte budget." if en else
                           "답변 입력 한도로 일부 근거를 제외했습니다. 검색된 원문을 확인하거나 질문 범위를 좁혀 주세요.")
        if kind == "table" and not operation_table and presentation is None and generation == "extractive":
            presentation = excerpt_table(evidence, language)
            if presentation:
                notices.append("This table contains source excerpts, not generated comparisons." if en else
                               "이 표는 모델의 비교 결과가 아닌 근거 원문 발췌입니다.")
        if kind == "table" and presentation is None and not notices:
            notices.append("No supported table evidence is available." if en else "표로 표시할 검증된 근거가 부족합니다.")
        if presentation and presentation.get("truncated"):
            notices.append("Only the bounded first rows/points are shown; the total count is displayed separately." if en else
                           "표시 한도로 처음 일부 행·점만 표시하며 전체 개수를 함께 안내합니다.")
        if summary is not None and len(summary["rows"]) > 200:
            notices.append("Operation totals include all selected records; the input-record preview shows only the first 200." if en else
                           "운항 합계는 선택 기간의 전체 기록으로 계산했으며 입력 기록 미리보기는 처음 200건만 표시합니다.")
        status = "data_found" if summary and summary["count"] else "evidence_found" if statements else "insufficient_evidence"
        if status == "insufficient_evidence":
            notice = "근거 또는 운항 데이터가 부족합니다. 담당자에게 확인해 주세요."
        answer_id = str(uuid4())
        answer = {"id": answer_id, "question": question, "task": "integrated" if needs_ops else "documents",
                  "language": language, "generation": generation, "status": status, "notice": notice,
                  "warnings": warnings, "statements": statements, "evidence": evidence, "toolRuns": runs,
                  "generationStats": stats,
                  "timings": {"retrievalMs": round(retrieval_ms, 3), "generationMs": round(generation_ms, 3),
                              "totalMs": round(max(0, (monotonic() - started) * 1000), 3)},
                  "reportSuggested": task == "report" or bool(re.search(r"보고서|noon|mrv|report", question, re.I))}
        if failure:
            answer['generationFailure']=failure
            self.audit(user,'error','AI 답변 생성 실패',answer_id,{
                **failure,'generationMs':round(generation_ms,3),'modelCallAttempted':stats['modelCallAttempted']})
        if presentation:
            answer["presentation"] = presentation
        if notices:
            answer["presentationNotice"] = " ".join(notices)
        if summary is not None:
            answer["operations"] = {**summary, "rows": summary["rows"][:200],
                                    "rowsTruncated": len(summary["rows"]) > 200,
                                    "totalRows": len(summary["rows"])}
            answer["compliance"] = compliance
        if operation_notice:
            answer["operationNotice"] = operation_notice
        self.run("INSERT INTO queries VALUES(%s,%s,%s,%s)", (answer_id, question, Jsonb(answer), utc_now()))
        self.run("INSERT INTO query_owner VALUES(%s,%s)", (answer_id, user["id"]))
        self.audit(user, "query", "질의", answer_id, {"question": question, "task": answer["task"]})
        return answer

    @staticmethod
    def grounded_statements(question: str, evidence: list[dict], language: str) -> list[dict]:
        settings = config.llm_settings()
        if settings is None:
            raise ValueError("Model not configured")
        return llm.grounded_statements(question, evidence, language, settings)

    @staticmethod
    def grounded_response(question: str, evidence: list[dict], language: str, **options) -> dict:
        settings = config.llm_settings()
        if settings is None:
            raise ValueError("Model not configured")
        return llm.grounded_response(question, evidence, language, settings, **options)

    def history(self, user: dict) -> list[dict]:
        rows = self.all("""SELECT q.* FROM queries q JOIN query_owner o ON o.id=q.id
            WHERE o.owner=%s ORDER BY q.created_at DESC LIMIT 100""", (user["id"],))
        result = []
        for row in rows:
            answer = row["response"]
            visible = all(self.can_read_document(user, item["document_id"]) for item in answer.get("evidence", []))
            result.append({"id": row["id"], "question": row["question"], "at": stamp(row["created_at"]),
                           "answer": answer if visible else None, "unavailable": not visible})
        return result
