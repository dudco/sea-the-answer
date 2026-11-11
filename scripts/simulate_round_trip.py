"""Export the Incheon–Port Said round-trip demonstration as UTC daily records.

The scenario starts at 12:00 UTC on --departure. By default only UTC days that
have finished by --through (default: now) are exported, so the log runs from
the departure date up to the present. --include-projected adds the remaining
scenario days, labelled as projected.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
import json
from pathlib import Path

from scripts.simulate_voyage import (ROUTE_PATH, Leg, Waypoint, daily_row, print_warnings, schedule, state_at,
                                     voyage_warnings, write_export)


DEFAULT_DEPARTURE = date(2026, 10, 13)
DEPARTURE_TIME = time(12, tzinfo=UTC)
OUTBOUND_DAYS = 27
PORT_SAID_STAY = timedelta(hours=18)
RETURN_DAYS = 31
SHIP_NAME = "가상 선박 해답 2호 · 왕복 시나리오"

TIMING_REFERENCES = [
    # IPA's North Africa Express announcement gives 27 days to Port Said.
    "https://eng.icpa.or.kr/article/view.do?articleKey=31994&boardKey=217&currentPageNo=1&menuKey=3996",
    # 29 days Port Said–Shanghai plus 2 days Shanghai–Incheon give a return benchmark.
    "https://www.cma-cgm.com/ebusiness/schedules/line-services/schedules/BEX2?Direction=Next&LastPageIndex=1",
    "https://www.pancon-acs.com/doc/426c15ae809fd15a6d7de8396d26bf444dbd4a30.pdf",
]


@dataclass(frozen=True)
class RoundTripPlan:
    ship_id: str
    start_date: date
    incheon_departure: datetime
    port_said_arrival: datetime
    port_said_departure: datetime
    incheon_arrival: datetime
    outward_nm: float
    total_nm: float
    legs: list[Leg]
    references: list[str]

    def hour(self, at: datetime) -> float:
        """Hours since UTC midnight of the departure date, the legs' time origin."""
        return (at - datetime.combine(self.start_date, time(), UTC)).total_seconds() / 3600

    @property
    def total_days(self) -> int:
        return (self.incheon_arrival.date() - self.start_date).days + 1


def retime(legs: list[Leg], days: int, start_hour: float, start_nm: float) -> list[Leg]:
    """Match the scenario duration by scaling cruising legs, retaining slow passages and waits."""
    target = days * 24
    cruising = sum(leg.end_hour - leg.start_hour for leg in legs if leg.status == "underway")
    other = legs[-1].end_hour - cruising
    scale = (target - other) / cruising
    result = []
    hour = start_hour
    for index, leg in enumerate(legs):
        duration = leg.end_hour - leg.start_hour
        if leg.status == "underway":
            duration *= scale
        end = start_hour + target if index == len(legs) - 1 else hour + duration
        result.append(replace(leg, start_hour=hour, end_hour=end, start_nm=start_nm + leg.start_nm,
                              speed_kn=leg.distance_nm / (end - hour)))
        hour = end
    return result


def reverse_route(points: list[Waypoint]) -> list[Waypoint]:
    result = []
    for index in range(len(points) - 1, 0, -1):
        # Status describes the outgoing segment, so take it from the other endpoint.
        status = points[index - 1].status
        if index == len(points) - 1:
            status = "departure"
        elif index <= 4:  # Dongbaek to the Incheon W-1 anchorage
            status = "approach"
        result.append(replace(points[index], status=status))
    return result + [replace(points[0], status="arrived")]


def plan_round_trip(departure: date = DEFAULT_DEPARTURE) -> RoundTripPlan:
    route = json.loads(ROUTE_PATH.read_text(encoding="utf-8"))
    points = [Waypoint(**point) for point in route["waypoints"]]
    incheon_departure = datetime.combine(departure, DEPARTURE_TIME)
    port_said_arrival = incheon_departure + timedelta(days=OUTBOUND_DAYS)
    port_said_departure = port_said_arrival + PORT_SAID_STAY
    incheon_arrival = port_said_departure + timedelta(days=RETURN_DAYS)
    midnight = datetime.combine(departure, time(), UTC)

    def hour(at: datetime) -> float:
        return (at - midnight).total_seconds() / 3600

    outward = retime(schedule(points), OUTBOUND_DAYS, hour(incheon_departure), 0)
    outward_nm = outward[-1].start_nm + outward[-1].distance_nm
    port = points[-1]
    berth = Leg(port, port, "berthed", hour(port_said_arrival), hour(port_said_departure), outward_nm, 0, 0)
    homeward = retime(schedule(reverse_route(points)), RETURN_DAYS, hour(port_said_departure), outward_nm)
    legs = [*outward, berth, *homeward]
    # The ID keeps the Port Said arrival date, so the default departure keeps the
    # existing "sim-inc-psd-roundtrip-2026-11-09" ship.
    return RoundTripPlan(
        ship_id=f"sim-inc-psd-roundtrip-{port_said_arrival.date().isoformat()}", start_date=departure,
        incheon_departure=incheon_departure, port_said_arrival=port_said_arrival,
        port_said_departure=port_said_departure, incheon_arrival=incheon_arrival,
        outward_nm=outward_nm, total_nm=legs[-1].start_nm + legs[-1].distance_nm, legs=legs,
        references=[*TIMING_REFERENCES, *route["references"]])


def completed_days(plan: RoundTripPlan, through: datetime) -> int:
    return min(plan.total_days, max(0, int(plan.hour(through) // 24)))


def build_round_trip(departure: date = DEFAULT_DEPARTURE, through: datetime | None = None,
                     include_projected: bool = False) -> dict:
    through = datetime.now(UTC) if through is None else through
    if through.utcoffset() is None:
        raise ValueError("--through must include a UTC offset, such as Z or +09:00")
    through = through.astimezone(UTC)
    plan = plan_round_trip(departure)
    done = completed_days(plan, through)
    count = plan.total_days if include_projected else done

    departure_date = plan.port_said_departure.date().isoformat()
    arrival_date = plan.incheon_arrival.date().isoformat()
    milestones = {
        plan.start_date.isoformat(): "12:00 UTC 인천항 출항",
        plan.port_said_arrival.date().isoformat(): "12:00 UTC 포트사이드 입항, 정박",
        departure_date: "06:00 UTC 포트사이드 출항",
        arrival_date: "06:00 UTC 인천항 도착",
    }
    records = []
    for index in range(count):
        row = daily_row(plan.legs, plan.start_date, index, plan.ship_id)
        homeward_day = row["date"] >= departure_date
        projected = index >= done
        row["voyage"] = "모의 귀항 PSD→INC" if homeward_day else "모의 출항 INC→PSD"
        if projected:
            row["note"] = row["note"].replace("가상 운항", "가상 예상 운항", 1)
            if row["date"] == arrival_date:
                row["note"] = row["note"].replace("입항 완료", "입항 예정", 1)
        if row["date"] in milestones:
            row["note"] += f" · {milestones[row['date']]}"
        records.append(row)

    return {
        "ships": [{"id": plan.ship_id, "name": SHIP_NAME, "type": "컨테이너선",
                   "dwt": 80000, "imo": "", "from": "인천항", "to": "포트사이드 경유 인천항", "sample": True}],
        "records": records,
        "simulation": {
            "sample": True, "date_basis": "UTC", "as_of": through.isoformat(),
            "days_recorded": done, "projected_days": count - done,
            "current": state_at(plan.legs, plan.hour(through)),
            "outbound": {"departure_at": plan.incheon_departure.isoformat(),
                         "arrival_at": plan.port_said_arrival.isoformat(),
                         "duration_days": OUTBOUND_DAYS, "record_count": OUTBOUND_DAYS + 1},
            "return": {"departure_at": plan.port_said_departure.isoformat(),
                       "arrival_at": plan.incheon_arrival.isoformat(),
                       "duration_days": RETURN_DAYS, "record_count": RETURN_DAYS + 1},
            "warnings": voyage_warnings(plan.incheon_departure, plan.incheon_arrival, through),
            "references": plan.references,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--departure", type=date.fromisoformat, default=DEFAULT_DEPARTURE,
                        help=f"Incheon departure date, 12:00 UTC (default: {DEFAULT_DEPARTURE})")
    parser.add_argument("--through", type=datetime.fromisoformat, help="snapshot timestamp with offset (default: now)")
    parser.add_argument("--include-projected", action="store_true",
                        help="also export scenario days after --through, labelled as projected")
    parser.add_argument("--format", choices=("json", "csv"), default="json", help="export format")
    parser.add_argument("--output", type=Path, help="new UTF-8 export file (default: stdout)")
    args = parser.parse_args()
    try:
        result = build_round_trip(args.departure, args.through, args.include_projected)
        print_warnings(result)
        write_export(result, args.format, args.output)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"simulate_round_trip: {exc}\n")


if __name__ == "__main__":
    main()
