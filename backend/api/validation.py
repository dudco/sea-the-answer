"""Small input-validation and formatting helpers shared by the store and routes."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone

from .errors import ApiError, require


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stamp(value):
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def source_quote(quote, source, maximum=4000):
    """Return the exact source span; only whitespace layout may differ."""
    if not isinstance(quote,str) or not isinstance(source,str):return None
    if quote in source:return quote
    tokens=re.split(r'\s+',quote.strip())
    if not tokens or not tokens[0]:return None
    match=re.search(r'\s+'.join(re.escape(token) for token in tokens),source)
    return match.group(0) if match and len(match.group(0))<=maximum else None


def text(value, label: str, maximum: int) -> str:
    require(isinstance(value, str) and 0 < len(value.strip()) <= maximum, f"{label}을(를) 확인해 주세요.")
    return value.strip()


def number(value, label: str, low: float, high: float) -> float:
    require(type(value) in (int, float) and low <= value <= high, f"{label}의 숫자 범위를 확인해 주세요.")
    return value


def iso_date(value, label="일자") -> str:
    require(isinstance(value, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)), f"{label}를 확인해 주세요.")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ApiError(400, "INVALID_INPUT", f"{label}를 확인해 주세요.") from exc
    return value


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def public_user(user: dict | None) -> dict | None:
    return {key: value for key, value in user.items() if key != "password"} if user else None
