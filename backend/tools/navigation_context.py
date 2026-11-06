"""Historical registered dimensions and regional observations, isolated from admission inputs."""
from datetime import timedelta
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator

from .port_reference import valid_imo

Q = Annotated[Decimal, Field(gt=0, lt=10000, allow_inf_nan=False)]
HASH = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
ContextSourceId = Literal['norway_static','smhi_wind_vinga','smhi_wind_gothenburg','smhi_water_gothenburg']


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Ref(Strict):
    source_id: ContextSourceId
    locator: str = Field(max_length=300)


class Supplement(Strict):
    url: HttpUrl
    sha256: HASH


class ReferencePeriod(Strict):
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode='after')
    def ordered(self):
        if self.start >= self.end:
            raise ValueError('Invalid historical reference period')
        return self


class StaticReference(Strict):
    vessel_id: str = Field(pattern=r'^REAL:IMO:[0-9]{7}$')
    imo_number: str
    mmsi: str = Field(pattern=r'^[1-9][0-9]{8}$')
    registry_imo_number: str | None = Field(default=None,max_length=20)
    reference_length_m: Q | None
    reference_beam_m: Q | None
    registry_draught_m: Annotated[Decimal,Field(gt=0,lt=50,allow_inf_nan=False)] | None
    valid_from: AwareDatetime | None
    valid_to: AwareDatetime | None
    source_ref: Ref
    issues: list[str] = Field(max_length=20)

    @model_validator(mode='after')
    def bound_identity(self):
        if not valid_imo(self.imo_number) or self.vessel_id != 'REAL:IMO:'+self.imo_number or self.source_ref.source_id != 'norway_static':
            raise ValueError('Invalid reference identity/source')
        if self.registry_imo_number != self.imo_number and 'REGISTRY_IDENTITY_MISMATCH' not in self.issues:
            raise ValueError('Registry identity conflict must remain visible')
        if self.valid_from and self.valid_to and self.valid_from >= self.valid_to:
            raise ValueError('Invalid registry validity interval')
        return self


# Reviewed association with the port region, never a berth sensor mapping.
STATIONS = {
    'smhi_wind_vinga': ('71380','4','m/s','Vinga A'),
    'smhi_wind_gothenburg': ('71420','4','m/s','Göteborg A'),
    'smhi_water_gothenburg': ('35120','13','cm','Göteborg-Tångudden'),
}


class EnvironmentObservation(Strict):
    port_id: Literal['WPI:24020']
    station_id: str
    station_name: str = Field(max_length=100)
    latitude: Annotated[Decimal,Field(ge=-90,le=90,allow_inf_nan=False)]
    longitude: Annotated[Decimal,Field(ge=-180,le=180,allow_inf_nan=False)]
    parameter_id: str
    unit: Literal['m/s','cm']
    value: Annotated[Decimal,Field(ge=-1000,le=1000,allow_inf_nan=False)]
    observed_at: AwareDatetime
    quality: str = Field(max_length=10)
    aggregation: Literal['10-minute mean, hourly publication','minute observation']
    vertical_datum: Literal['RH2000'] | None = None
    station_metadata: Supplement
    datum_evidence: Supplement | None = None
    source_ref: Ref

    @model_validator(mode='after')
    def reviewed_binding(self):
        expected = STATIONS.get(self.source_ref.source_id)
        if not expected or (self.station_id,self.parameter_id,self.unit,self.station_name) != expected:
            raise ValueError('Unreviewed station/parameter/port binding')
        if self.unit == 'm/s' and (not 0 <= self.value <= 100 or self.vertical_datum or self.aggregation != '10-minute mean, hourly publication'):
            raise ValueError('Invalid wind observation contract')
        if self.unit == 'cm' and (self.vertical_datum != 'RH2000' or not self.datum_evidence or self.aggregation != 'minute observation'):
            raise ValueError('Water datum evidence required')
        return self


def static_summary(references, period, vessel_id):
    rows = [r for r in references if r.vessel_id == vessel_id]
    base = {'status':'unavailable','reference_only':True,'current_verified':False,'candidate_count':len(rows),
        'as_of':period.end.isoformat() if period else None,'length_m':None,'beam_m':None,'issues':[],
        'candidates':[r.model_dump(mode='json') for r in rows[:20]],
        'notice':'요청한 과거 기간의 등록 제원 참고값입니다. 현재 실측/신고값을 대체하지 않으며 등록 흘수는 현재 흘수 비교에 사용하지 않습니다.'}
    if not rows or not period:
        return base
    asof = period.end - timedelta(microseconds=1)
    if any('REGISTRY_TIME_INVALID' in r.issues or r.valid_from is None for r in rows):
        return {**base,'status':'period_unknown','issues':['REGISTRY_PERIOD_UNKNOWN']}
    active = [r for r in rows if r.valid_from <= asof and (r.valid_to is None or r.valid_to > asof)]
    base['active_candidate_count'] = len(active)
    if not active:
        return base
    if any(r.registry_imo_number != r.imo_number or 'REGISTRY_IDENTITY_MISMATCH' in r.issues for r in active):
        return {**base,'status':'identity_conflict','issues':['REGISTRY_IDENTITY_MISMATCH']}
    for axis in ('length','beam'):
        values = [getattr(r,'reference_'+axis+'_m') for r in active]
        if any(v is None for v in values):
            base['issues'].append('REGISTRY_'+axis.upper()+'_MISSING')
        elif len(set(values)) != 1:
            base['issues'].append('REGISTRY_'+axis.upper()+'_CONFLICT')
        else:
            base[axis+'_m'] = str(values[0])
    base['status'] = 'reference_available' if base['length_m'] or base['beam_m'] else 'insufficient_reference'
    return base


def reference_checks(summary, berth):
    checks = []
    for axis,field in (('length','max_loa_m'),('beam','max_beam_m')):
        value,limit = summary[axis+'_m'],getattr(berth,field)
        checks.append({'kind':axis,'reference_value_m':value,'berth_listed_m':str(limit) if limit is not None else None,
            'status':'unavailable' if value is None or limit is None else
                'reference_value_exceeded' if Decimal(value)>limit else 'within_historical_reference',
            'reference_only':True,'current_verified':False})
    return checks


def environment_context(observations, port_id, sources, now):
    rows = []
    def age(when):
        return 'time_in_future' if when > now else 'stale' if now-when > timedelta(hours=2) else 'within_age_window'
    for reading in observations:
        if reading.port_id != port_id:
            continue
        row = reading.model_dump(mode='json')
        row.update(age_status=age(reading.observed_at),capture_age_status=age(sources[reading.source_ref.source_id].retrieved_at),
            quality_status='checked' if reading.quality=='G' else 'suspect_or_aggregated' if reading.quality=='Y' else
                'unchecked' if reading.quality=='O' else 'unknown',comparison_use='context_only')
        rows.append(row)
    return {'reference_only':True,'scope':'regional_station_observations','observations':rows,
        'notice':'지역 관측소의 수집본입니다. 선석 현장값·입항 예정 시각의 예보가 아니며 가정값/입항 규칙/UKC 계산에 자동 투입하지 않습니다.',
        'freshness_policy_hours':2}
