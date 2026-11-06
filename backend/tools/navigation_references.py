"""Bounded offline reference snapshots and deterministic, non-authoritative screening."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import os
from pathlib import Path
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, ValidationError, model_validator
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .port_reference import valid_imo
from .navigation_readiness import Scenario, readiness, operational_checks
from .navigation_context import StaticReference, ReferencePeriod, EnvironmentObservation, static_summary, reference_checks, environment_context
from .navigation_guidance import PortGuidance, guidance_context

Quantity = Annotated[Decimal, Field(gt=0, lt=10000, allow_inf_nan=False)]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
AIS_MAX_AGE = timedelta(hours=24)
PORT_MAX_AGE = timedelta(days=30)
SourceId = Literal["ais", "schema", "berths", "helsinki_berths", "ais_no", "schema_no", "aalborg_berths",
    "norway_static", "schema_no_static", "smhi_wind_vinga", "smhi_wind_gothenburg", "smhi_water_gothenburg"]
PortSourceId = Literal["berths", "helsinki_berths", "aalborg_berths"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(Strict):
    id: SourceId
    url: HttpUrl
    sha256: Hash
    retrieved_at: AwareDatetime
    effective_at: AwareDatetime | None
    attribution: str = Field(max_length=500)
    license_url: HttpUrl | None


class SourceRef(Strict):
    source_id: SourceId
    locator: str = Field(max_length=300)


class Observation(Strict):
    vessel_id: str = Field(pattern=r"^REAL:IMO:[0-9]{7}$")
    imo_number: str
    mmsi: str | None = Field(pattern=r"^[0-9]{9}$")
    name: str = Field(max_length=80)
    metadata_received_at: AwareDatetime | None
    reported_length_m: Quantity | None
    reported_beam_m: Quantity | None
    reported_draught_m: Quantity | None
    draught_lower_bound_m: Quantity | None
    source_ref: SourceRef
    issues: list[str] = Field(max_length=20)
    position_reported_at: AwareDatetime | None = None
    raw_reported_fields: dict[Literal["length", "breadth", "draught"], Annotated[str, Field(max_length=40)]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def identity(self):
        if not valid_imo(self.imo_number) or self.vessel_id != "REAL:IMO:" + self.imo_number:
            raise ValueError("Invalid real IMO identity")
        if self.source_ref.source_id not in ("ais", "ais_no"):
            raise ValueError("Observation must reference the AIS source")
        if self.source_ref.source_id == "ais_no" and (self.metadata_received_at is not None or
                any(value is not None for value in (self.reported_length_m,self.reported_beam_m,self.reported_draught_m,self.draught_lower_bound_m))
                or not {"AIS_STATIC_TIME_UNVERIFIED","AIS_UNITS_UNVERIFIED"}.issubset(self.issues)):
            raise ValueError("Norway position/undocumented raw dimensions cannot become verified static metre data")
        if self.reported_draught_m is not None and self.draught_lower_bound_m is not None:
            raise ValueError("A lower-bound draught must not be treated as an exact observation")
        return self


class Variant(Strict):
    heading: str = Field(max_length=80)
    text: str = Field(max_length=6000)
    max_loa_m: Quantity | None
    max_draught_m: Quantity | None
    source_ref: SourceRef


class Berth(Strict):
    berth_id: str = Field(pattern=r"^WPI:[0-9]+:BERTH:[0-9A-Z-]+$")
    label: str = Field(max_length=40)
    variants: list[Variant] = Field(min_length=1, max_length=10)
    source_ref: SourceRef
    issues: list[str] = Field(max_length=20)
    conditions: list[Annotated[str, Field(max_length=6000)]] = Field(max_length=10)
    max_loa_m: Quantity | None
    max_draught_m: Quantity | None
    max_beam_m: Quantity | None

    @model_validator(mode="after")
    def source_values(self):
        if self.source_ref.source_id not in ("berths", "helsinki_berths", "aalborg_berths") or any(
                v.source_ref.source_id != self.source_ref.source_id for v in self.variants):
            raise ValueError("Berth must reference the berth source")
        if self.conditions != [v.text for v in self.variants] or self.source_ref != self.variants[0].source_ref:
            raise ValueError("Berth conditions or locator differ from preserved source variants")
        for field in ("max_loa_m", "max_draught_m"):
            expected = getattr(self.variants[0], field) if len(self.variants) == 1 else None
            if getattr(self, field) != expected:
                raise ValueError("Catalog limit does not match its preserved source variant")
        if self.max_beam_m is not None:
            raise ValueError("This source parser does not verify beam limits")
        if self.source_ref.source_id == "aalborg_berths":
            if self.max_draught_m is not None or any(v.max_draught_m is not None for v in self.variants):
                raise ValueError("Aalborg footnoted draught requires latest sounding/pilot confirmation")
            if any("depends on vessel" in v.text for v in self.variants) and self.max_loa_m is not None:
                raise ValueError("Aalborg manifold-dependent LOA must remain conditional")
        return self


class Port(Strict):
    port_id: str = Field(pattern=r"^WPI:[0-9]+$")
    unlocode: str = Field(pattern=r"^[A-Z]{2}[A-Z0-9]{3}$")
    name: str = Field(max_length=100)
    source_id: PortSourceId = "berths"
    reference_scope: str = Field(default="Public berth references; terminal suitability not assessed", max_length=200)
    berths: list[Berth] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def berth_identity(self):
        if len({b.berth_id for b in self.berths}) != len(self.berths):
            raise ValueError("Duplicate berth identity")
        if any(b.berth_id != self.port_id + ":BERTH:" + b.label for b in self.berths):
            raise ValueError("Port and berth identity mismatch")
        if any(b.source_ref.source_id != self.source_id for b in self.berths):
            raise ValueError("Port and berth source mismatch")
        return self


class NavigationCatalog(Strict):
    version: Literal["NAVIGATION-REFERENCES-1.0", "NAVIGATION-REFERENCES-1.1", "NAVIGATION-REFERENCES-1.2", "NAVIGATION-REFERENCES-1.3", "NAVIGATION-REFERENCES-1.4"]
    generated_at: AwareDatetime
    mrv_vessels_sha256: Hash
    wpi_sha256: Hash
    sources: list[Source] = Field(min_length=3, max_length=12)
    observations: list[Observation] = Field(max_length=10000)
    ports: list[Port] = Field(min_length=1, max_length=20)
    static_references: list[StaticReference] = Field(default_factory=list,max_length=20000)
    static_reference_period: ReferencePeriod | None = None
    environment_observations: list[EnvironmentObservation] = Field(default_factory=list,max_length=12)
    port_guidance: list[PortGuidance] = Field(default_factory=list,max_length=6)
    guidance_review_sha256: Hash | None = None

    @model_validator(mode="after")
    def unique_sources(self):
        ids = {s.id for s in self.sources}
        if not {"ais", "schema", "berths"}.issubset(ids) or len(ids) != len(self.sources):
            raise ValueError("Required source identities are missing")
        if len({p.port_id for p in self.ports}) != len(self.ports):
            raise ValueError("Duplicate port identity")
        if len({p.unlocode for p in self.ports}) != len(self.ports):
            raise ValueError("Duplicate UN/LOCODE")
        if any(o.source_ref.source_id not in ids for o in self.observations):
            raise ValueError("Observation source missing")
        if "ais_no" in ids and "schema_no" not in ids:
            raise ValueError("Norway source contract missing")
        if self.version in ("NAVIGATION-REFERENCES-1.0","NAVIGATION-REFERENCES-1.1") and ids & {"ais_no","schema_no","aalborg_berths"}:
            raise ValueError("Extended sources require catalog 1.2")
        extra = {"norway_static","schema_no_static","smhi_wind_vinga","smhi_wind_gothenburg","smhi_water_gothenburg"}
        if self.version not in ("NAVIGATION-REFERENCES-1.3", "NAVIGATION-REFERENCES-1.4") and (ids & extra or self.static_references or self.environment_observations or self.static_reference_period):
            raise ValueError("Reference inputs require catalog 1.3")
        if self.version != 'NAVIGATION-REFERENCES-1.4' and (self.port_guidance or self.guidance_review_sha256):
            raise ValueError('Official guidance requires catalog 1.4')
        if len({d.id for d in self.port_guidance}) != len(self.port_guidance):
            raise ValueError('Duplicate official guidance document')
        if self.port_guidance and not self.guidance_review_sha256:
            raise ValueError('Exact guidance review required')
        ports_by_id = {p.port_id:p for p in self.ports}
        for doc in self.port_guidance:
            if doc.port_id not in ports_by_id or doc.retrieved_at > self.generated_at:
                raise ValueError('Guidance port/capture time invalid')
            berths = {b.berth_id for b in ports_by_id[doc.port_id].berths}
            if any(berth not in berths for fact in doc.facts for berth in fact.berth_ids):
                raise ValueError('Guidance berth is not in the reviewed port catalog')
        if self.static_references:
            if not self.static_reference_period or not {'norway_static','schema_no_static'}.issubset(ids):
                raise ValueError('Static reference period/source contract missing')
            pairs = {(o.vessel_id,o.imo_number,o.mmsi) for o in self.observations
                     if o.source_ref.source_id=='ais_no' and 'AIS_IDENTITY_AMBIGUOUS' not in o.issues}
            if any((r.vessel_id,r.imo_number,r.mmsi) not in pairs for r in self.static_references):
                raise ValueError('Registry cannot establish a new IMO/MMSI binding')
            if self.static_reference_period.end > self.generated_at:
                raise ValueError('Future historical reference period')
            source = next(s for s in self.sources if s.id=='norway_static')
            if not self.static_reference_period.end <= source.retrieved_at <= self.generated_at:
                raise ValueError('Invalid historical source capture time')
        if len({e.source_ref.source_id for e in self.environment_observations}) != len(self.environment_observations):
            raise ValueError('Duplicate environment source')
        if any(e.source_ref.source_id not in ids or not any(p.port_id==e.port_id and p.unlocode=='SEGOT' for p in self.ports) for e in self.environment_observations):
            raise ValueError('Environment port/source missing')
        for port in self.ports:
            expected = {"berths": "SEGOT", "helsinki_berths": "FIHEL", "aalborg_berths":"DKAAL"}[port.source_id]
            if port.source_id not in ids or port.unlocode != expected:
                raise ValueError("Port source missing or outside its reviewed UN/LOCODE")
        return self


class NavigationScreenRequest(Strict):
    vessel_id: str = Field(pattern=r"^REAL:IMO:[0-9]{7}$")
    port_id: str = Field(pattern=r"^WPI:[0-9]+$")
    berth_id: str | None = Field(default=None, pattern=r"^WPI:[0-9]+:BERTH:[0-9A-Z-]+$")
    scenario: Scenario | None = None

    @model_validator(mode="after")
    def identity(self):
        if not valid_imo(self.vessel_id.removeprefix("REAL:IMO:")):
            raise ValueError("Invalid IMO checksum")
        if self.berth_id and not self.berth_id.startswith(self.port_id + ":BERTH:"):
            raise ValueError("Berth is outside the selected port")
        return self


def load_catalog(path):
    """Configured by the server only, freshly read and validated on every request."""
    if not path:
        path=Path(os.getenv('HAEDAP_IMPORT_DIR') or Path(__file__).resolve().parents[1]/'data/imports')/'navigation/catalog.json'
    try:
        with Path(path).open("rb") as stream:
            payload = stream.read(8 * 1024 * 1024 + 1)
        if len(payload) > 8 * 1024 * 1024:
            raise ValueError("Snapshot exceeds 8 MiB")
        catalog = NavigationCatalog.model_validate_json(payload)
        return catalog, hashlib.sha256(payload).hexdigest()
    except (OSError, ValueError, ValidationError):
        raise HTTPException(503, "항구 참조 snapshot의 형식·크기·출처 및 준비 상태를 확인하세요.") from None


def catalog_summary(catalog, sha256, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("A timezone-aware server clock is required")
    sources = {s.id: s for s in catalog.sources}
    record_states = Counter(age_issue(o.metadata_received_at, now, AIS_MAX_AGE, "AIS_RECORD") or "within_age_window"
                            for o in catalog.observations)
    return {"version": catalog.version, "catalog_sha256": sha256, "reference_only": True,
        "admission": "not_assessed", "generated_at": catalog.generated_at.isoformat(),
        "ais_observation_count": len(catalog.observations),
        "ais_source_counts": dict(Counter(o.source_ref.source_id for o in catalog.observations)),
        "ais_unique_vessels":len({o.vessel_id for o in catalog.observations}),
        "static_reference_records":len(catalog.static_references),
        "static_reference_vessels":len({r.vessel_id for r in catalog.static_references}),
        "official_guidance_documents":len(catalog.port_guidance),
        "environment":environment_context(catalog.environment_observations,'WPI:24020',sources,now),
        "sources": [s.model_dump(mode="json") for s in catalog.sources],
        "ports": [{"port_id": p.port_id, "unlocode": p.unlocode, "name": p.name,
                   "source_id": p.source_id, "reference_scope": p.reference_scope,
                   "retrieved_at": sources[p.source_id].retrieved_at.isoformat(),
                   "capture_issue": age_issue(sources[p.source_id].retrieved_at, now, PORT_MAX_AGE, "PORT_CAPTURE"),
                   "berths": [{"berth_id": b.berth_id, "label": b.label, "issues": b.issues} for b in p.berths]}
                  for p in catalog.ports],
        "coverage": "Fintraffic Finnish receiving coverage and Kystverket Norwegian public feed; not worldwide or continuous" if "ais_no" in sources else "AIS snapshot from Finnish receiving coverage; not worldwide or continuous",
        "freshness": {"assessed_at": now.isoformat(),
            "ais_capture_issue": age_issue(sources["ais"].retrieved_at, now, AIS_MAX_AGE, "AIS_CAPTURE"),
            "port_capture_issue": age_issue(sources["berths"].retrieved_at, now, PORT_MAX_AGE, "PORT_CAPTURE"),
            "catalog_issue": age_issue(catalog.generated_at, now, PORT_MAX_AGE, "CATALOG"),
            "ais_record_age_counts": dict(record_states), "port_effective_date_verified": False},
        "freshness_policy": {"ais_record_hours": 24, "port_capture_days": 30,
                             "basis": "application policy, not a navigation regulation"}}


def age_issue(when, now, maximum, prefix):
    if when is None:
        return prefix + "_TIME_UNKNOWN"
    if when > now:
        return prefix + "_TIME_IN_FUTURE"
    if now - when > maximum:
        return prefix + "_STALE"
    return None


def screen_references(catalog, body, *, now=None, sha256=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("A timezone-aware server clock is required")
    ports = [p for p in catalog.ports if p.port_id == body.port_id]
    if not ports:
        raise HTTPException(404, "해당 항구의 선석 참조 자료가 없습니다.")
    port = ports[0]
    berths = [b for b in port.berths if not body.berth_id or b.berth_id == body.berth_id]
    if not berths:
        raise HTTPException(404, "해당 선석의 참조 자료가 없습니다.")
    sources = {s.id: s for s in catalog.sources}
    candidates = [o for o in catalog.observations if o.vessel_id == body.vessel_id]
    observation = candidates[0] if len(candidates) == 1 else None
    ship_issues = []
    if observation is None:
        ship_issues.append("AIS_OBSERVATION_UNAVAILABLE" if not candidates else "AIS_IDENTITY_AMBIGUOUS")
    else:
        # Recheck across the catalog rather than trusting only stored quality labels.
        associated = {o.imo_number for o in catalog.observations if o.mmsi and o.mmsi == observation.mmsi}
        if observation.mmsi is None or len(associated) > 1 or "AIS_IDENTITY_AMBIGUOUS" in observation.issues:
            ship_issues.append("AIS_IDENTITY_AMBIGUOUS")
        ship_issues.extend(i for i in observation.issues if i in ("AIS_STATIC_TIME_UNVERIFIED","AIS_UNITS_UNVERIFIED"))
        issue = age_issue(observation.metadata_received_at, now, AIS_MAX_AGE, "AIS_RECORD")
        if issue:
            ship_issues.append(issue)
    capture_ids = {o.source_ref.source_id for o in candidates} or {key for key in ("ais","ais_no") if key in sources}
    for key in sorted(capture_ids):
        issue = age_issue(sources[key].retrieved_at, now, AIS_MAX_AGE, "AIS_CAPTURE")
        if issue:
            ship_issues.append(issue)
    port_issues = []
    issue = age_issue(sources[port.source_id].retrieved_at, now, PORT_MAX_AGE, "PORT_CAPTURE")
    if issue:
        port_issues.append(issue)
    issue = age_issue(catalog.generated_at, now, PORT_MAX_AGE, "CATALOG")
    if issue:
        ship_issues.append(issue)
        port_issues.append(issue)
    results = []
    registered = static_summary(catalog.static_references,catalog.static_reference_period,body.vessel_id)
    for berth in berths:
        checks = []
        for kind, vessel_field, limit_field in (
            ("length", "reported_length_m", "max_loa_m"),
            ("beam", "reported_beam_m", "max_beam_m"),
            ("draught", "reported_draught_m", "max_draught_m"),
        ):
            value = getattr(observation, vessel_field) if observation else None
            limit = getattr(berth, limit_field)
            reasons = [*ship_issues, *port_issues]
            if value is None:
                reasons.append("AIS_" + kind.upper() + "_UNAVAILABLE")
                if kind == "draught" and observation and observation.draught_lower_bound_m is not None:
                    reasons.append("AIS_DRAUGHT_LOWER_BOUND")
            if limit is None:
                reasons.append("BERTH_" + kind.upper() + "_LIMIT_UNKNOWN_OR_CONDITIONAL")
            if len(berth.variants) != 1:
                reasons.append("DUPLICATE_BERTH_VARIANTS_REQUIRE_REVIEW")
            state = "unavailable" if reasons else (
                "above_listed_reference" if value > limit else "within_listed_reference")
            checks.append({"kind": kind, "vessel_reported_m": str(value) if value is not None else None,
                "berth_listed_m": str(limit) if limit is not None else None, "status": state,
                "reasons": sorted(set(reasons))})
        has_excess = any(c["status"] == "above_listed_reference" for c in checks)
        has_comparison = any(c["status"] != "unavailable" for c in checks)
        results.append({"berth_id": berth.berth_id,
            "status": "published_reference_exceeded" if has_excess else
                      "partial_reference_check" if has_comparison else "insufficient_data",
            "checks": checks, "conditions": berth.conditions, "conditions_evaluated": False,
            "operational_checks":operational_checks(berth,observation.reported_length_m if observation else None,
                usable_report=not ship_issues,scenario=body.scenario,duplicate=len(berth.variants)!=1,source_issues=port_issues),
            "static_reference_checks":reference_checks(registered,berth) if not port_issues else [],
            "berth_issues": berth.issues, "source_ref": berth.source_ref.model_dump()})
    return {"version": catalog.version, "catalog_sha256": sha256, "assessed_at": now.isoformat(),
        "vessel_id": body.vessel_id, "port_id": port.port_id, "port_name": port.name,
        "port_source_id": port.source_id, "port_reference_scope": port.reference_scope,
        "reference_only": True, "admission": "not_assessed", "safe_draft_m": None,
        "observation": observation.model_dump(mode="json") if observation else None,
        "observation_candidates":[o.model_dump(mode="json") for o in candidates[:20]],
        "observation_candidate_count":len(candidates),
        "readiness":readiness(body.scenario),
        "static_reference":registered,
        "environment":environment_context(catalog.environment_observations,port.port_id,sources,now),
        "official_guidance":guidance_context(catalog.port_guidance,port.port_id,body.berth_id,now),
        "ship_issues": sorted(set(ship_issues)), "berths": results,
        "sources": [s.model_dump(mode="json") for s in catalog.sources if s.id in
            ({port.source_id} | {key for o in candidates for key in
                (o.source_ref.source_id, "schema_no" if o.source_ref.source_id=="ais_no" else "schema")} |
                ({s.id for s in catalog.sources if s.id in ("ais","schema","ais_no","schema_no")} if not candidates else set()) |
                ({'norway_static','schema_no_static'} if registered['candidate_count'] else set()) |
                {e.source_ref.source_id for e in catalog.environment_observations if e.port_id==port.port_id})],
        "required_before_admission": ["CURRENT_VERIFIED_SHIP_DIMENSIONS_AND_DRAUGHT",
            "LATEST_PORT_NOTICES_AND_SELECTED_BERTH_APPROVAL", "APPROACH_TIDE_DENSITY_UKC_AND_WEATHER",
            "AIR_DRAUGHT_CARGO_TUG_PILOT_AND_ADJACENT_BERTH_CONDITIONS"],
        "warnings": ["AIS_IS_REPORTED_NOT_VERIFIED_OR_CERTIFIED", "METADATA_TIME_IS_NOT_DRAUGHT_MEASUREMENT_TIME",
            "PORT_SOURCE_EFFECTIVE_DATE_UNVERIFIED", "BERTH_CONDITIONS_NOT_AUTOMATICALLY_EVALUATED",
            "NO_ROUTE_OR_TERMINAL_SUITABILITY_ASSESSMENT", "NO_ENTRY_PERMISSION"]}


def screen_from_database(engine, body, catalog, sha256):
    if engine.dialect.name != "postgresql":
        raise HTTPException(503, "PostgreSQL의 실제 선박 목록이 필요합니다.")
    try:
        with engine.connect() as connection, connection.begin():
            connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout='5s'"))
            vessel = connection.execute(text("""SELECT vessel_id,imo_number,data_origin
                FROM maritime_data.vessels WHERE vessel_id=:vessel_id AND data_origin='REAL'"""),
                {"vessel_id": body.vessel_id}).mappings().one_or_none()
    except SQLAlchemyError:
        raise HTTPException(503, "실제 선박 DB·migration·적재 상태를 확인하세요.") from None
    if not vessel:
        raise HTTPException(404, "현재 DB에 해당 실제 MRV 선박이 없습니다.")
    if vessel["vessel_id"] != body.vessel_id or vessel["imo_number"] != body.vessel_id.removeprefix("REAL:IMO:"):
        raise HTTPException(409, "선박 식별자가 일치하지 않습니다.")
    return screen_references(catalog, body, sha256=sha256)
