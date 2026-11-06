"""Source-bound operational checks and explicitly hypothetical inputs; no admission approval."""
from decimal import Decimal
import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wind_m_s: Annotated[Decimal, Field(ge=0, le=100, allow_inf_nan=False)] | None = None
    available_tugs: Annotated[int, Field(strict=True, ge=0, le=20)] | None = None
    ukc_m: Annotated[Decimal, Field(ge=0, le=20, allow_inf_nan=False)] | None = None


def readiness(scenario=None):
    items = [
        ("verified_dimensions", "현재 검증된 선박 제원", "제원 원본·측정/확인 시각·확인 주체가 필요합니다."),
        ("verified_draught", "현재 실측 흘수·적재 상태", "선수/선미 흘수·트림·측정 시각을 확인해야 합니다. AIS 신고값으로 대신하지 않습니다."),
        ("approach_clearance", "접근 항로·회전 공간·높이 제한", "선석까지 전체 경로의 최신 해도·수심·항로 폭·수면 위 높이 제한을 확인해야 합니다."),
        ("water_weather", "예정 시점의 수위·기상·선저 여유", "수위 기준면·수밀도·풍속·조류·파랑·시정과 운항 중 침하를 포함한 선저 여유 검토가 필요합니다."),
        ("pilot_tugs", "도선·예선의 실제 확보", "도선 의무와 예약·배정된 예선의 수/능력·선박 설비 상태를 확인해야 합니다."),
        ("terminal_cargo", "선종·화물·터미널 적합성", "화물 취급·계류·장비·인접 선석 조건은 별도 확인해야 합니다."),
        ("port_acceptance", "최신 공고·선석 배정·관련 승인", "항만 최신 공고·운항 제한·선석 배정과 해당 승인 절차의 확인이 필요합니다."),
    ]
    return {"status":"requires_review", "admission":"not_assessed", "verified_current_ship_state":False,
        "scenario_only":scenario is not None, "scenario":scenario.model_dump(mode="json") if scenario else None,
        "items":[{"id":key,"title":title,"status":"needs_information","reason":reason} for key,title,reason in items],
        "notice":"일부 원문 조건을 정리한 검토 지원입니다. 가정값은 실측·기상 관측·예선 확보 증빙이 아니며 입항 승인을 생성하지 않습니다."}


def operational_checks(berth, reported_length, *, usable_report=False, scenario=None, duplicate=False, source_issues=()):
    """Only reviewed, exact source patterns become checks. Other source text remains unassessed."""
    source = berth.source_ref.source_id
    body = "\n".join(berth.conditions)
    normalized = " ".join(body.split())
    rules = []
    if source == "berths":
        if berth.label == "508-509":
            match = re.search(r"overall length of >([0-9]+) metres arrives at berth 509 and the wind speed is more than ([0-9]+) m/s, the use of one \(1\) tug is compulsory", normalized)
            if match:
                rules.append({"id":"gothenburg-509-tug", "kind":"tug", "length_over_m":match[1],
                    "wind_over_m_s":match[2],"required_tugs":1,"scope":"509번 선석 입항 시 조건 (508번에 확대 적용하지 않음)", "source_text":match[0]})
        if berth.label == "551":
            match = re.search(r"during arrival the wind speed is more than ([0-9]+) m/s, the use of one \(1\) tug is compulsory", normalized)
            if match:
                rules.append({"id":"gothenburg-551-tug", "kind":"tug", "wind_over_m_s":match[1],
                    "required_tugs":1,"scope":"551번 선석 입항 조건; 출항·가스선 설비 조건은 별도 확인", "source_text":match[0]})
        if berth.label == "644":
            match = re.search(r"UKC \(under keel clearance\) ([0-9]+(?:[.,][0-9]+)?) metres", normalized)
            if match:
                rules.append({"id":"gothenburg-644-ukc","kind":"ukc","minimum_m":match[1].replace(",","."),
                    "scope":"644번 선석의 게시 UKC 조건; 전체 항로·회사 기준 별도", "source_text":match[0]})
    if source == "aalborg_berths":
        match = re.search(r"Minimum (0[.,]1) m clearance should be maintained between vessel keel and seabed under arrival and departure", normalized)
        if match:
            rules.append({"id":"aalborg-ukc","kind":"ukc","minimum_m":match[1].replace(",","."),
                "scope":"Oil terminal 게시 최소값; 회사 선저 여유 정책·최신 수심 확인 필요", "source_text":match[0]})
        match = re.search(r"Max\. draft.*?depends on pilo\s*t restrictions and latest soundings", normalized)
        if match:
            rules.append({"id":"aalborg-soundings","kind":"external_confirmation",
                "scope":"최대 흘수의 각주 조건", "source_text":match[0]})
    output = []
    for rule in rules:
        result = {**rule,"source_ref":berth.source_ref.model_dump(),"status":"needs_information",
                  "scenario_only":scenario is not None,"missing_inputs":[],"values":{}}
        if duplicate:
            result["missing_inputs"] = ["unambiguous_berth_source"]
        elif source_issues:
            result["missing_inputs"] = ["current_port_source"]
        elif rule["kind"] == "external_confirmation":
            result["missing_inputs"] = ["latest_soundings_and_pilot_restrictions", "port_control_confirmation"]
        elif rule["kind"] == "ukc":
            value = scenario.ukc_m if scenario else None
            result["values"] = {"scenario_ukc_m":str(value) if value is not None else None}
            if value is None:
                result["missing_inputs"] = ["assessed_under_keel_clearance"]
            else:
                result["status"] = "within_scenario" if value >= Decimal(rule["minimum_m"]) else "action_required"
        else:
            length = reported_length if usable_report else None
            wind = scenario.wind_m_s if scenario else None
            tugs = scenario.available_tugs if scenario else None
            result["values"] = {"reported_length_m":str(length) if length is not None else None,
                "scenario_wind_m_s":str(wind) if wind is not None else None,"scenario_available_tugs":tugs}
            if "length_over_m" in rule and length is None:
                result["missing_inputs"].append("reported_length_for_provisional_trigger")
            if wind is None:
                result["missing_inputs"].append("wind_at_arrival")
            if not result["missing_inputs"]:
                triggered = wind > Decimal(rule["wind_over_m_s"]) and ("length_over_m" not in rule or length > Decimal(rule["length_over_m"]))
                if not triggered:
                    result["status"] = "not_triggered_in_scenario"
                elif tugs is None:
                    result["missing_inputs"] = ["available_tugs"]
                else:
                    result["status"] = "within_scenario" if tugs >= rule["required_tugs"] else "action_required"
        output.append(result)
    return output
