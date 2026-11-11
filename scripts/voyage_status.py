"""Show where a simulated ship is at a given moment (default: now).

The answer is computed from the departure date and the route alone, so no
SQLite log or app connection is needed. Use the same --departure (and
--round-trip) as the simulation that was published to the app.

    python -m scripts.voyage_status --departure 2026-11-01
    python -m scripts.voyage_status --round-trip --departure 2026-10-13 --at 2026-11-10T09:00+09:00
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, time, timedelta
import json
import sys

from scripts.simulate_round_trip import DEFAULT_DEPARTURE, SHIP_NAME as ROUND_TRIP_NAME, plan_round_trip
from scripts.simulate_voyage import (ROUTE_PATH, STATUS_LABELS, VOYAGE_DAYS, Waypoint, format_duration, schedule,
                                     state_at, voyage_warnings)

ONE_WAY_NAME = "가상 선박 해답호"


def _event(label: str, at: datetime, now: datetime) -> dict:
    return {"label": label, "at": at.isoformat(), "in_hours": round((at - now).total_seconds() / 3600, 2)}


def voyage_status(departure: date, at: datetime, round_trip: bool = False) -> dict:
    """Return the simulated ship's state at `at` for a voyage that left on `departure`."""
    if at.utcoffset() is None:
        raise ValueError("--at must include a UTC offset, such as Z or +09:00")
    now = at.astimezone(UTC)
    if round_trip:
        plan = plan_round_trip(departure)
        legs, hour = plan.legs, plan.hour(now)
        ship = {"id": plan.ship_id, "name": ROUND_TRIP_NAME}
        start, end, total_nm = plan.incheon_departure, plan.incheon_arrival, plan.total_nm
        events = [("인천항 출항", start), ("포트사이드 입항", plan.port_said_arrival),
                  ("포트사이드 출항", plan.port_said_departure), ("인천항 도착", end)]
        # Distance to the next port of call: Port Said on the way out, Incheon afterwards.
        next_port_nm = plan.outward_nm if now < plan.port_said_arrival else total_nm
        next_port = "이집트 포트사이드항" if now < plan.port_said_arrival else "인천항"
    else:
        route = json.loads(ROUTE_PATH.read_text(encoding="utf-8"))
        legs = schedule([Waypoint(**point) for point in route["waypoints"]])
        start = datetime.combine(departure, time(), UTC)
        end = start + timedelta(days=VOYAGE_DAYS)
        hour = (now - start).total_seconds() / 3600
        ship = {"id": f"sim-inc-psd-{departure.isoformat()}", "name": ONE_WAY_NAME}
        total_nm = legs[-1].start_nm + legs[-1].distance_nm
        events = [("인천항 출항", start), ("포트사이드항 도착", end)]
        next_port_nm, next_port = total_nm, "이집트 포트사이드항"

    state = state_at(legs, hour)
    sailed = state["distance_nm"]
    upcoming = next(((label, when) for label, when in events if when > now), None)
    return {
        "ship": ship,
        "as_of": now.isoformat(),
        "status": state["status"],
        "status_label": STATUS_LABELS[state["status"]],
        "underway": start <= now < end,
        "location": state["location"],
        "latitude": state["latitude"],
        "longitude": state["longitude"],
        "speed_kn": state["speed_kn"],
        "heading_deg": state["heading_deg"],
        "distance_sailed_nm": round(sailed, 1),
        "total_distance_nm": round(total_nm, 1),
        "progress_pct": round(100 * sailed / total_nm, 1),
        "next_port": None if now >= end else next_port,
        "distance_to_next_port_nm": None if now >= end else round(max(0.0, next_port_nm - sailed), 1),
        "departure_at": start.isoformat(),
        "arrival_at": end.isoformat(),
        "next_event": None if upcoming is None else _event(*upcoming, now),
        "elapsed_hours": round(max(0.0, (now - start).total_seconds() / 3600), 2),
        "warnings": voyage_warnings(start, end, now),
        "sample": True,
    }


def format_text(status: dict, tz) -> str:
    def when(value: str) -> str:
        return datetime.fromisoformat(value).astimezone(tz).strftime("%Y-%m-%d %H:%M %Z")

    lines = [f"{status['ship']['name']} ({status['ship']['id']}) · {when(status['as_of'])} 기준 · 가상 자료",
             f"상태: {status['status_label']} — {status['location']}",
             f"위치: {status['latitude']:.5f}, {status['longitude']:.5f}"
             + (f" · 속력 {status['speed_kn']:.1f} kn" if status["speed_kn"] else "")
             + (f" · 침로 {status['heading_deg']:.0f}°" if status["heading_deg"] is not None else ""),
             f"항해 거리: {status['distance_sailed_nm']:,.1f} / {status['total_distance_nm']:,.1f} nm "
             f"(진행률 {status['progress_pct']:.1f}%)"]
    if status["next_port"]:
        lines.append(f"다음 기항지: {status['next_port']}까지 {status['distance_to_next_port_nm']:,.1f} nm")
    lines.append(f"출항: {when(status['departure_at'])} · 종료(도착): {when(status['arrival_at'])}")
    if status["next_event"]:
        event = status["next_event"]
        remaining = format_duration(timedelta(hours=event["in_hours"]))
        lines.append(f"다음 일정: {event['label']} {when(event['at'])} ({remaining} 남음)")
    lines += [f"경고: {warning}" for warning in status["warnings"]]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--departure", type=date.fromisoformat,
                        help=f"departure date (one-way: required, UTC midnight; round trip: 12:00 UTC, default {DEFAULT_DEPARTURE})")
    parser.add_argument("--round-trip", action="store_true", help="query the Incheon–Port Said–Incheon scenario")
    parser.add_argument("--at", type=datetime.fromisoformat, help="query time with offset (default: now)")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="output format")
    args = parser.parse_args()
    if not args.round_trip and args.departure is None:
        parser.error("--departure is required for a one-way voyage")
    at = args.at or datetime.now().astimezone()
    try:
        status = voyage_status(args.departure or DEFAULT_DEPARTURE, at, args.round_trip)
    except ValueError as exc:
        parser.exit(1, f"voyage_status: {exc}\n")
    sys.stdout.reconfigure(encoding="utf-8")
    if args.format == "json":
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        print(format_text(status, at.tzinfo))


if __name__ == "__main__":
    main()
