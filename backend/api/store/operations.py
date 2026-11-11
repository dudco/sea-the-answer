"""Ships and daily operation records: validation and period summaries."""

from __future__ import annotations

from uuid import uuid4

from ..errors import ApiError, require
from ..validation import iso_date, number, text


class OperationStore:
    def ships(self) -> list[dict]:
        return [{**row["body"], "version": row["version"]} for row in self.all("SELECT * FROM ships ORDER BY seq,id")]

    def operations(self) -> list[dict]:
        return [{**row["body"], "version": row["version"]}
                for row in self.all("SELECT * FROM operations ORDER BY date,id")]

    def validate_ship(self, payload: dict) -> dict:
        return {"id": payload.get("id") or str(uuid4()), "name": text(payload.get("name"), "선박명", 100),
                "type": text(payload.get("type"), "선종", 80), "dwt": number(payload.get("dwt"), "DWT", 1, 1e7),
                "imo": str(payload.get("imo") or "")[:30], "from": str(payload.get("from") or "")[:100],
                "to": str(payload.get("to") or "")[:100], "sample": bool(payload.get("sample"))}

    def validate_operation(self, payload: dict, check_previous=True) -> dict:
        ship = text(payload.get("ship"), "선박", 80)
        require(bool(self.one("SELECT 1 FROM ships WHERE id=%s", (ship,))), "등록된 선박을 선택해 주세요.")
        day = iso_date(payload.get("date"))
        row = {"id": payload.get("id") or str(uuid4()), "ship": ship, "date": day,
               "fuel": number(payload.get("fuel"), "연료(t)", 0, 1e7),
               "factor": number(payload.get("factor"), "배출계수", 0.000001, 10),
               "distance": number(payload.get("distance"), "거리(nm)", 0, 1e7),
               "speed": number(payload.get("speed"), "속력(kn)", 0, 100),
               "position": str(payload.get("position") or "")[:100],
               "voyage": str(payload.get("voyage") or "")[:100],
               "fuelType": text(payload.get("fuelType"), "연료 종류", 80),
               "weather": str(payload.get("weather") or "")[:200],
               "draft": None if payload.get("draft") in (None, "") else number(payload["draft"], "흘수(m)", 0, 40),
               "engineHours": None if payload.get("engineHours") in (None, "") else number(payload["engineHours"], "기관 운전시간(h)", 0, 24),
               "note": str(payload.get("note") or "")[:1000], "sample": bool(payload.get("sample"))}
        old = self.one("SELECT version FROM operations WHERE id=%s", (row["id"],))
        require((old or {}).get("version", 0) == payload.get("version", 0), "운항 기록이 변경되었습니다.", "VERSION_CONFLICT", 409)
        require(not self.one("SELECT 1 FROM operations WHERE ship=%s AND date=%s AND id<>%s", (ship, day, row["id"])),
                "동일 선박·일자의 기록이 이미 있습니다.")
        previous = self.one("SELECT body FROM operations WHERE ship=%s AND date<%s ORDER BY date DESC LIMIT 1", (ship, day))
        if check_previous and previous and row["fuel"] > max(1, previous["body"]["fuel"]) * 2:
            require(len(row["note"]) >= 5, "연료 증가 점검 사유를 5자 이상 기록해 주세요.", "ANOMALY")
        return {**row, "version": (old or {}).get("version", 0)}

    def validate_rows(self, rows: list) -> dict:
        require(isinstance(rows, list) and 0 < len(rows) <= 1000, "1~1,000개의 운항 기록이 필요합니다.")
        valid, errors, seen = [], [], set()
        for index, payload in enumerate(rows, 1):
            try:
                row = self.validate_operation(payload, False)
                key = (row["ship"], row["date"])
                require(key not in seen, "파일 안에 선박·일자가 중복되어 있습니다.")
                seen.add(key)
                valid.append(row)
            except ApiError as exc:
                errors.append({"row": index, "message": exc.message})
                valid.append(None)
        existing = self.operations()
        for index, row in enumerate(valid, 1):
            if not row:
                continue
            # Include imported rows; ignore a replaced version of this row.
            prior = [candidate for candidate in existing + [r for r in valid if r]
                     if candidate["ship"] == row["ship"] and candidate["date"] < row["date"]
                     and candidate["id"] != row["id"]]
            if prior and row["fuel"] > max(1, max(prior, key=lambda r: r["date"])["fuel"]) * 2 and len(row["note"]) < 5:
                errors.append({"row": index, "message": "이전 기록보다 연료가 2배 이상입니다. 점검 사유를 5자 이상 기록해 주세요."})
        return {"rows": valid, "errors": errors}

    def recent_positions(self, ship_id: str, through: str) -> list[dict]:
        """The two newest records on or before ``through`` (ISO date) that store a position."""
        return [{**row["body"], "version": row["version"]} for row in self.all(
            "SELECT body,version FROM operations WHERE ship=%s AND date<=%s AND COALESCE(body->>'position','')<>'' "
            "ORDER BY date DESC,id DESC LIMIT 2", (ship_id, through))]

    def operation_summary(self, context: dict) -> dict:
        ship_id = context.get("ship")
        ship_row = self.one("SELECT body,version FROM ships WHERE id=%s", (ship_id,))
        require(ship_row, "대상 선박을 선택해 주세요.")
        start, end = iso_date(context.get("from"), "시작일"), iso_date(context.get("to"), "종료일")
        require(start <= end, "기간을 확인해 주세요.")
        rows = [{**row["body"], "version": row["version"]} for row in
                self.all("SELECT body,version FROM operations WHERE ship=%s AND date BETWEEN %s AND %s ORDER BY date,id",
                         (ship_id, start, end))]
        ship = {**ship_row["body"], "version": ship_row["version"]}
        fuel = sum(row["fuel"] for row in rows)
        emission = sum(row["fuel"] * row["factor"] for row in rows)
        distance = sum(row["distance"] for row in rows)
        return {"ship": ship, "from": start, "to": end, "rows": rows, "count": len(rows),
                "fuel": fuel, "emission": emission, "distance": distance,
                "speed": sum(row["speed"] for row in rows) / len(rows) if rows else None,
                "intensity": emission * 1e6 / (ship["dwt"] * distance) if distance else None,
                "sample": bool(ship.get("sample") or any(row.get("sample") for row in rows)),
                "cii": {"status": "unavailable", "value": None, "rating": None,
                        "reason": "공식 CII 계산에 필요한 선종·보정·제외 조건과 연간 완전성을 검증하지 않았습니다."}}
