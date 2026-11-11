"""Bounded, cited tables and operation-data charts; no model or database IO."""

from __future__ import annotations

from copy import deepcopy
import math
import re
from .validation import source_quote

MAX_COLUMNS, MAX_ROWS, MAX_POINTS = 8, 50, 100
MAX_CELL, MAX_TITLE, MAX_COLUMN, MAX_LABEL, MAX_UNIT = 1000, 200, 80, 80, 40


class UnsupportedMetric(ValueError):
    """The request cannot be represented by the supported operation metrics."""


_REGULATION = r"규정|법규|법령|규칙|조항|한도|황\s*(?:함유|함량)|용어|\b(?:regulation|rule|limit|sulphur|sulfur|glossary|definition)\b"

TABLE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["type", "title", "columns", "rows"],
    "properties": {
        "type": {"type": "string", "enum": ["table"]},
        "title": {"type": "string", "minLength": 1, "maxLength": MAX_TITLE},
        "columns": {"type": "array", "minItems": 1, "maxItems": MAX_COLUMNS,
                    "items": {"type": "string", "minLength": 1, "maxLength": MAX_COLUMN}},
        "rows": {"type": "array", "minItems": 1, "maxItems": MAX_ROWS, "items": {
            "type": "object", "additionalProperties": False, "required": ["cells", "citations"],
            "properties": {
                "cells": {"type": "array", "minItems": 1, "maxItems": MAX_COLUMNS,
                          "items": {"type": "string", "maxLength": MAX_CELL}},
                "citations": {"type": "array", "minItems": 1, "maxItems": 5, "items": {
                    "type": "object", "additionalProperties": False, "required": ["chunkId", "quote"],
                    "properties": {"chunkId": {"type": "string"},
                                   "quote": {"type": "string", "minLength": 8, "maxLength": MAX_CELL}}}},
            },
        }},
    },
}


def output_format(question: str, requested: str = "auto") -> str:
    if not isinstance(requested, str) or requested not in {"auto", "text", "table", "chart"}:
        raise ValueError("Invalid output format")
    if requested != "auto":
        return requested
    if re.search(r"차트|그래프|시각화|막대|꺾은선|\b(?:chart|graph|plot|visuali[sz]ation)\b", question, re.I):
        return "chart"
    if re.search(r"표로|표를|표\s*(?:형태|형식|만들)|비교\s*표|테이블|\b(?:table|tabular)\b", question, re.I):
        return "table"
    if re.search(r"그림|도식|다이어그램|\b(?:figure|diagram|picture|image)\b", question, re.I):
        return "unsupported"
    return "text"


def wants_operation_table(question: str, task: str) -> bool:
    if task == "operations":
        return True
    if task == "documents" or re.search(_REGULATION, question, re.I):
        return False
    return bool(re.search(
        r"운항\s*(?:기록|데이터|자료)|사용량|소모량|소비량|배출량|항해\s*거리|일별|월별|날짜별|추이|"
        r"\b(?:operations?|records?|consumption|usage|daily|monthly|time.series|emissions?)\b", question, re.I))


def _text(value: object, limit: int, *, blank: bool = False) -> bool:
    return isinstance(value, str) and len(value) <= limit and (blank or bool(value.strip()))


def validate_document_table(table: object, evidence: list[dict]) -> dict:
    table=deepcopy(table)
    if (not isinstance(table, dict) or set(table) != {"type", "title", "columns", "rows"}
            or table["type"] != "table" or not _text(table["title"], MAX_TITLE)
            or not isinstance(table["columns"], list) or not 1 <= len(table["columns"]) <= MAX_COLUMNS
            or any(not _text(value, MAX_COLUMN) for value in table["columns"])
            or not isinstance(table["rows"], list) or not 1 <= len(table["rows"]) <= MAX_ROWS):
        raise ValueError("Invalid document table")
    sources = {item["id"]: item["text"] for item in evidence}
    for row in table["rows"]:
        if (not isinstance(row, dict) or set(row) != {"cells", "citations"}
                or not isinstance(row["cells"], list) or len(row["cells"]) != len(table["columns"])
                or any(not _text(value, MAX_CELL, blank=True) for value in row["cells"])
                or not any(value.strip() for value in row["cells"])
                or not isinstance(row["citations"], list) or not 1 <= len(row["citations"]) <= 5):
            raise ValueError("Invalid document table row")
        for citation in row["citations"]:
            if (not isinstance(citation, dict) or set(citation) != {"chunkId", "quote"}
                    or not isinstance(citation["chunkId"], str) or citation["chunkId"] not in sources
                    or not _text(citation["quote"], MAX_CELL) or len(citation["quote"].strip()) < 8):
                raise ValueError("Invalid document table citation")
            exact=source_quote(citation['quote'],sources[citation['chunkId']],MAX_CELL)
            if exact is None:raise ValueError('Invalid document table citation')
            citation['quote']=exact
    return {**deepcopy(table), "source": "documents", "truncated": False, "totalRows": len(table["rows"])}


def excerpt_table(evidence: list[dict], language: str) -> dict | None:
    rows = []
    for item in evidence[:MAX_ROWS]:
        quote = item["text"][:MAX_CELL]
        if len(quote.strip()) < 8:
            continue
        rows.append({"cells": [item["title"][:MAX_CELL], quote],
                     "citations": [{"chunkId": item["id"], "quote": quote}]})
    if not rows:
        return None
    table = validate_document_table({"type": "table", "title": "Source excerpts" if language == "en" else "문서 근거 발췌",
                                     "columns": ["Document", "Source excerpt"] if language == "en" else ["문서", "원문 발췌"],
                                     "rows": rows}, evidence)
    table.update(truncated=len(evidence) > len(rows), totalRows=len(evidence))
    return table


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("Invalid operation number")
    return value


def operation_presentation(summary: dict | None, kind: str, question: str, language: str) -> dict | None:
    if not summary or not summary.get("count"):
        return None
    rows = summary.get("rows")
    if not isinstance(rows, list) or not rows or summary["count"] != len(rows):
        raise ValueError("Invalid operation records")
    en = language == "en"
    # Only values from the server's selected ship/period records are projected.
    for row in rows:
        if not isinstance(row, dict) or not _text(row.get("date"), MAX_LABEL):
            raise ValueError("Invalid operation label")
        for field in ("fuel", "factor", "distance", "speed"):
            _number(row.get(field))
        _number(row["fuel"] * row["factor"])
    if kind == "table":
        return {"type": "table", "source": "operations", "title": "Operation records" if en else "운항 기록",
                "columns": ["Date", "Fuel (t)", "CO₂ (t)", "Distance (nm)", "Speed (kn)"] if en else
                           ["일자", "연료 (t)", "CO₂ (t)", "거리 (nm)", "속력 (kn)"],
                "rows": [{"cells": [row["date"], str(row["fuel"]), str(row["fuel"] * row["factor"]),
                                     str(row["distance"]), str(row["speed"])], "citations": []}
                         for row in rows[:MAX_ROWS]], "truncated": len(rows) > MAX_ROWS, "totalRows": len(rows)}
    if kind != "chart":
        raise ValueError("Invalid operation presentation")
    if re.search(r"CII|등급|집약도|\b(?:rating|intensity)\b", question, re.I) or re.search(_REGULATION, question, re.I):
        raise UnsupportedMetric("Unsupported chart metric")
    if re.search(r"배출|CO[₂2]|\b(?:carbon|emissions?)\b", question, re.I):
        metric, unit, label = "emission", "tCO₂", "CO₂ emissions" if en else "CO₂ 배출량"
    elif re.search(r"연료|\bfuel\b", question, re.I):
        metric, unit, label = "fuel", "t", "Fuel" if en else "연료"
    elif re.search(r"거리|\bdistance\b", question, re.I):
        metric, unit, label = "distance", "nm", "Distance" if en else "거리"
    elif re.search(r"속력|속도|\bspeed\b", question, re.I):
        metric, unit, label = "speed", "kn", "Speed" if en else "속력"
    else:
        raise UnsupportedMetric("Specify a supported operation metric")
    return {"type": "chart", "source": "operations", "chartType": "bar" if re.search(r"막대|\bbar\b", question, re.I) else "line",
            "title": label, "xLabel": "Date" if en else "일자", "yLabel": label, "unit": unit,
            "points": [{"label": row["date"], "value": row["fuel"] * row["factor"] if metric == "emission" else row[metric]}
                       for row in rows[:MAX_POINTS]], "truncated": len(rows) > MAX_POINTS, "totalPoints": len(rows)}
