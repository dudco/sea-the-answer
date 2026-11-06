"""App-owned ship comparison shared by detailed HTTP lookup and question answers."""
import os

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from tools.api import create_engine_for
from tools.navigation_references import NavigationScreenRequest, load_catalog, screen_from_database
from tools.port_reference import positive
from . import config
from .errors import ApiError, require
from .maritime_context import resolve_real_ship
from .operation_uploads import reference_path


def unavailable(exc):
    if isinstance(exc, HTTPException):
        return ApiError(exc.status_code, "DATA_SOURCE_UNAVAILABLE" if exc.status_code == 503 else "INVALID_INPUT", str(exc.detail))
    return ApiError(503, "DATA_SOURCE_UNAVAILABLE", "해사 DB·선박 연결·참조 자료의 준비 상태를 확인해 주세요.")


def load_snapshot():
    try:
        return load_catalog(reference_path())
    except HTTPException as exc:
        raise unavailable(exc) from None


def latest_draught(db, ship):
    row = db.one("""SELECT body,version FROM operations WHERE ship=%s
        AND body->>'draft' IS NOT NULL AND body->>'draft'<>'' ORDER BY date DESC,id DESC LIMIT 1""", (ship,))
    if not row:
        return None
    record = row["body"]
    value = positive(record.get("draft"))
    return {"record_id": record["id"], "version": row["version"], "date": record["date"],
        "draught_m": str(value) if value is not None else None, "sample": bool(record.get("sample")),
        "measurement_time": None, "used_for_comparison": False,
        "notice": "운항 기록의 입력값입니다. 측정 시각·현재 적재 상태 확인이 필요합니다."}


def compare_ship(db, ship, *, port_ids=None, berth_id=None, snapshot=None, scenario=None):
    engine = None
    try:
        engine = create_engine_for(os.getenv("MARITIME_DATA_DATABASE_URL") or config.database_url())
        resolved = resolve_real_ship(db, engine, ship)
        require(not resolved.body.get("sample"), "가상 예시 선박은 실제 항구 참조 비교에 사용할 수 없습니다.",
                "SAMPLE_SHIP_NOT_SUPPORTED")
        context = {"ship": ship, "ship_version": resolved.version, "vessel_id": resolved.vessel_id,
                   "imo_number": resolved.imo_number}
        if not resolved.vessel_id:
            return {"status": "needs_mapping", "context": context, "results": [],
                    "notice": "앱 선박과 실제 MRV 선박의 명시적 연결이 필요합니다."}
        data, sha256 = snapshot if snapshot is not None else load_snapshot()
        selected = [p.port_id for p in data.ports] if port_ids is None else port_ids
        require(bool(selected) and len(selected) <= 20 and len(set(selected)) == len(selected), "항구 범위를 확인해 주세요.")
        require(not berth_id or len(selected) == 1, "선석을 지정하려면 항구 하나를 확인해 주세요.")
        results = [screen_from_database(engine, NavigationScreenRequest(vessel_id=resolved.vessel_id,
                    port_id=port, berth_id=berth_id, scenario=scenario), data, sha256) for port in selected]
        record = latest_draught(db, ship)
        current = resolve_real_ship(db, engine, ship)
        require(current.version == resolved.version and current.vessel_id == resolved.vessel_id
                and current.imo_number == resolved.imo_number,
                "선박 정보 또는 연결이 변경되었습니다. 다시 조회해 주세요.", "VERSION_CONFLICT", 409)
        return {"status": "ok", "context": context, "results": results, "latest_record_draught": record,
                "notice": "신고값과 선석의 공개 조건을 부분 비교한 결과입니다. 입항 허가는 별도 확인이 필요합니다."}
    except (HTTPException, SQLAlchemyError) as exc:
        raise unavailable(exc) from None
    finally:
        if engine is not None:
            engine.dispose()
