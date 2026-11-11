"""Run the synthetic Incheon–Port Said voyage and export daily operations.

Run from the repository root with Python 3.12 or later. The SQLite file
contains a single voyage. Run again with the same departure to catch up.
"""

from __future__ import annotations

import argparse
import csv
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
import hashlib
import io
import json
from math import asin, atan2, cos, degrees, radians, sin, sqrt
from pathlib import Path
import sqlite3
import sys


VOYAGE_DAYS = 28
ROUTE_PATH = Path(__file__).with_name("fixtures") / "incheon_port_said_route.json"
CSV_COLUMNS = (
    "id", "ship", "date", "fuel", "factor", "distance", "speed", "fuelType",
    "position", "voyage", "engineHours", "note", "sample",
)
STATUS_LABELS = {
    "scheduled": "출항 예정", "departure": "출항", "underway": "항해 중",
    "waiting": "운하 통과 대기", "canal": "수에즈운하 통과", "arrived": "입항 완료",
    "berthed": "포트사이드 정박", "approach": "인천항 접근",
}


@dataclass(frozen=True)
class Waypoint:
    name: str
    latitude: float
    longitude: float
    status: str


@dataclass(frozen=True)
class Leg:
    start: Waypoint
    finish: Waypoint
    status: str
    start_hour: float
    end_hour: float
    start_nm: float
    distance_nm: float
    speed_kn: float


def distance_nm(start: Waypoint, finish: Waypoint) -> float:
    lat1, lat2 = radians(start.latitude), radians(finish.latitude)
    delta_lon = radians(finish.longitude - start.longitude)
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return 2 * 3440.065 * asin(min(1.0, sqrt(a)))


def bearing(start: Waypoint, finish: Waypoint) -> float:
    lat1, lat2 = radians(start.latitude), radians(finish.latitude)
    delta_lon = radians(finish.longitude - start.longitude)
    east = sin(delta_lon) * cos(lat2)
    north = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(delta_lon)
    return round(degrees(atan2(east, north)) % 360, 1) % 360


def schedule(waypoints: list[Waypoint]) -> list[Leg]:
    """Allocate the illustrative 28 days across sea legs and slower approaches."""
    distances = [distance_nm(a, b) for a, b in zip(waypoints, waypoints[1:])]
    # Vary cruise speed by section. Reserve time for slower port/canal passage
    # and a fictional wait before entering the canal.
    wait_hours = 12.0
    speed_weights = [1 + 0.08 * sin(i * 1.7) for i in range(len(distances))]
    slow_hours = sum(d / 8 for w, d in zip(waypoints, distances) if w.status != "underway")
    sea_hours = VOYAGE_DAYS * 24 - wait_hours - slow_hours
    cruise_kn = sum(d / weight for w, d, weight in zip(waypoints, distances, speed_weights)
                    if w.status == "underway") / sea_hours

    legs = []
    hour = miles = 0.0
    waited = False
    for i, (start, finish, distance, weight) in enumerate(zip(waypoints, waypoints[1:], distances, speed_weights)):
        if start.status == "canal" and not waited:
            legs.append(Leg(start, start, "waiting", hour, hour + wait_hours, miles, 0.0, 0.0))
            hour += wait_hours
            waited = True
        speed = cruise_kn * weight if start.status == "underway" else 8.0
        end = VOYAGE_DAYS * 24 if i == len(distances) - 1 else hour + distance / speed
        legs.append(Leg(start, finish, start.status, hour, end, miles, distance, speed))
        hour = end
        miles += distance
    return legs


def state_at(legs: list[Leg], hour: float) -> dict:
    last = legs[-1]
    # A scenario may start mid-day (e.g. 12:00 UTC), so compare with the first leg.
    if hour < legs[0].start_hour or hour >= last.end_hour:
        scheduled = hour < legs[0].start_hour
        point = legs[0].start if scheduled else last.finish
        return {"status": "scheduled" if scheduled else "arrived", "location": point.name,
                "latitude": point.latitude, "longitude": point.longitude, "speed_kn": 0.0,
                "heading_deg": None, "distance_nm": 0.0 if scheduled else round(last.start_nm + last.distance_nm, 3)}
    leg = next(leg for leg in legs if hour < leg.end_hour)
    fraction = (hour - leg.start_hour) / (leg.end_hour - leg.start_hour)
    return {
        "status": leg.status,
        "location": leg.start.name if leg.start.name == leg.finish.name else f"{leg.start.name} → {leg.finish.name}",
        "latitude": round(leg.start.latitude + fraction * (leg.finish.latitude - leg.start.latitude), 6),
        "longitude": round(leg.start.longitude + fraction * (leg.finish.longitude - leg.start.longitude), 6),
        "speed_kn": round(leg.speed_kn, 2),
        "heading_deg": bearing(leg.start, leg.finish) if leg.speed_kn else None,
        "distance_nm": round(leg.start_nm + leg.distance_nm * fraction, 3),
    }


def format_utc(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def format_duration(delta: timedelta) -> str:
    hours = int(delta.total_seconds() // 3600)
    days, hours = divmod(hours, 24)
    return f"{days}일 {hours}시간" if days else f"{hours}시간"


def voyage_warnings(departure_at: datetime, arrival_at: datetime, through: datetime) -> list[str]:
    """Explain why a snapshot has no ongoing voyage: not departed yet, or already over."""
    if through < departure_at:
        return [f"출항 전입니다: 출항 예정 {format_utc(departure_at)}이며 조회 시점 {format_utc(through)}에는 "
                "아직 운항하지 않습니다. 기록할 운항일이 없습니다."]
    if through >= arrival_at:
        return [f"이미 종료된 항해입니다: {format_utc(arrival_at)}에 도착해 조회 시점 {format_utc(through)}에는 "
                f"운항 중이 아닙니다(도착 후 {format_duration(through - arrival_at)} 경과). "
                "운항 기록은 도착일까지만 생성됩니다. 현재 운항 중인 시연이 필요하면 더 최근 출발일을 지정하세요."]
    return []


def daily_row(legs: list[Leg], departure: date, index: int, ship_id: str) -> dict:
    start, finish = index * 24, (index + 1) * 24
    fuel = engine_hours = distance = 0.0
    for leg in legs:
        hours = min(finish, leg.end_hour) - max(start, leg.start_hour)
        if hours <= 0:
            continue
        distance += hours * leg.distance_nm / (leg.end_hour - leg.start_hour)
        # Illustrative fuel curve in tonnes/day, including auxiliary use.
        fuel += hours * (3.0 + 24.0 * (leg.speed_kn / 14) ** 3) / 24
        if leg.speed_kn:
            engine_hours += hours
    end_state = state_at(legs, finish)
    day = (departure + timedelta(days=index)).isoformat()
    return {
        "id": f"{ship_id}-{day}", "ship": ship_id, "date": day,
        "fuel": round(fuel, 3), "factor": 3.114, "fuelType": "HFO",
        "distance": round(distance, 3), "speed": round(distance / 24, 2),
        "position": f"{end_state['latitude']:.5f}, {end_state['longitude']:.5f}",
        "voyage": f"SIM-INC-PSD-{departure.isoformat()}",
        "engineHours": round(engine_hours, 3),
        "note": f"가상 운항 · {STATUS_LABELS[end_state['status']]} · {end_state['location']} · UTC 일자",
        "sample": True,
    }


def advance(db_path: Path, departure: date, through: datetime) -> dict:
    """Store completed UTC days and return a snapshot at the requested instant."""
    if through.utcoffset() is None:
        raise ValueError("--through must include a UTC offset, such as Z or +09:00")
    through = through.astimezone(UTC)
    start = datetime.combine(departure, time(), UTC)
    arrival = start + timedelta(days=VOYAGE_DAYS)
    hours = (through - start).total_seconds() / 3600
    completed_days = min(VOYAGE_DAYS, max(0, int(hours // 24)))
    route = json.loads(ROUTE_PATH.read_text(encoding="utf-8"))
    waypoints = [Waypoint(**point) for point in route["waypoints"]]
    legs = schedule(waypoints)
    # Use a date-specific ID so a different voyage can coexist in the app.
    ship_id = f"sim-inc-psd-{departure.isoformat()}"
    signature = hashlib.sha256(json.dumps([1, departure.isoformat(), VOYAGE_DAYS, route["waypoints"]],
                                          sort_keys=True).encode()).hexdigest()

    with closing(sqlite3.connect(db_path, timeout=10)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS voyage (id INTEGER PRIMARY KEY CHECK(id = 1), signature TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS daily (day INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        db.execute("INSERT OR IGNORE INTO voyage VALUES (1, ?)", (signature,))
        if db.execute("SELECT signature FROM voyage WHERE id = 1").fetchone()[0] != signature:
            raise ValueError("This log belongs to a different departure or route version. Use a new database file.")
        saved = {i for (i,) in db.execute("SELECT day FROM daily")}
        for i in range(completed_days):
            if i not in saved:
                db.execute("INSERT INTO daily VALUES (?, ?)", (i, json.dumps(daily_row(legs, departure, i, ship_id))))
        records = [json.loads(payload) for (payload,) in
                   db.execute("SELECT payload FROM daily WHERE day < ? ORDER BY day", (completed_days,))]

    return {
        "ships": [{"id": ship_id, "name": "가상 선박 해답호", "type": "컨테이너선", "dwt": 65000,
                   "imo": "", "from": "인천항", "to": "이집트 포트사이드항", "sample": True}],
        "records": records,
        "simulation": {"sample": True, "departure_at": start.isoformat(), "arrival_at": arrival.isoformat(),
                       "as_of": through.isoformat(), "days_recorded": len(records),
                       "current": state_at(legs, hours), "references": route["references"],
                       "warnings": voyage_warnings(start, arrival, through)},
    }


def operation_csv(records: list[dict]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    writer.writerows({**row, "sample": "true"} for row in records)
    return output.getvalue()


def print_warnings(result: dict) -> None:
    for warning in result.get("simulation", {}).get("warnings", []):
        print(f"경고: {warning}", file=sys.stderr)


def write_export(result: dict, output_format: str, path: Path | None) -> None:
    output = (operation_csv(result["records"]) if output_format == "csv" else
              json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if path is not None:
        with path.open("x", encoding="utf-8", newline="") as file:
            file.write(output)
    else:
        sys.stdout.reconfigure(encoding="utf-8", newline="")
        sys.stdout.write(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True, help="SQLite voyage log to create or resume")
    parser.add_argument("--departure", type=date.fromisoformat, required=True, help="departure date (UTC midnight)")
    parser.add_argument("--through", type=datetime.fromisoformat, help="snapshot timestamp with offset (default: now)")
    parser.add_argument("--format", choices=("json", "csv"), default="json", help="export format")
    parser.add_argument("--output", type=Path, help="new UTF-8 export file (default: stdout)")
    args = parser.parse_args()
    try:
        result = advance(args.database, args.departure, args.through or datetime.now(UTC))
        print_warnings(result)
        write_export(result, args.format, args.output)
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"simulate_voyage: {exc}\n")


if __name__ == "__main__":
    main()
