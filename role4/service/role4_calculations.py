"""Versioned CO2 arithmetic and readiness checks, never official CII ratings."""
from datetime import date
from decimal import Decimal, localcontext, ROUND_HALF_UP
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from .role4 import json_value

FACTOR_VERSION = 'IMO-MEPC364-79-2.2.1-FOSSIL-SUBSET-v1'
FACTOR_SOURCE = 'https://wwwcdn.imo.org/localresources/en/KnowledgeCentre/IndexofIMOResolutions/MEPCDocuments/MEPC.364%2879%29.pdf'
CII_SOURCE = 'https://wwwcdn.imo.org/localresources/en/KnowledgeCentre/IndexofIMOResolutions/MEPCDocuments/MEPC.352%2878%29.pdf'
FACTORS = {'DIESEL_GAS_OIL': Decimal('3.206'), 'LFO': Decimal('3.151'), 'HFO': Decimal('3.114')}
VERSION = 'ROLE4-CO2-1.0'


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class FuelMapping(Strict):
    fuel_label: Literal['MGO', 'VLSFO']
    category: Literal['DIESEL_GAS_OIL', 'LFO', 'HFO']
    evidence: str = Field(min_length=8, max_length=1000)

    @model_validator(mode='after')
    def nonblank_evidence(self):
        if len(self.evidence.strip()) < 8:
            raise ValueError('연료 매핑의 근거 또는 개발용 가정을 적어 주세요.')
        return self


class AnnualScope(Strict):
    dataset: Literal['real_annual']
    vessel_id: str = Field(pattern=r'^REAL:IMO:[0-9]{7}$')
    year: int = Field(ge=1900, le=2100, strict=True)


class NoonScope(Strict):
    dataset: Literal['synthetic_noon']
    vessel_id: str = Field(pattern=r'^SYN:[A-Za-z0-9_-]+$', max_length=120)
    start: date
    end: date

    @model_validator(mode='after')
    def period(self):
        if not 0 <= (self.end-self.start).days <= 366:
            raise ValueError('기간은 시작부터 종료까지 최대 366일 차이입니다.')
        return self


class CalculationRequest(Strict):
    scope: Annotated[AnnualScope | NoonScope, Field(discriminator='dataset')]
    factor_version: Literal['IMO-MEPC364-79-2.2.1-FOSSIL-SUBSET-v1'] = FACTOR_VERSION
    fuel_mappings: list[FuelMapping] = Field(default_factory=list, max_length=2)

    @model_validator(mode='after')
    def unique_mappings(self):
        labels = [m.fuel_label for m in self.fuel_mappings]
        if len(labels) != len(set(labels)):
            raise ValueError('동일 연료의 매핑은 한 번만 지정하세요.')
        if self.scope.dataset == 'real_annual' and self.fuel_mappings:
            raise ValueError('연료종류·사용량 구분이 없는 MRV 총량에 매핑을 적용할 수 없습니다.')
        return self


def catalog():
    return {'version': FACTOR_VERSION, 'source': FACTOR_SOURCE, 'section': '2.2.1',
            'unit': 'tCO2/t-fuel', 'factors': {k: str(v) for k,v in FACTORS.items()},
            'notice': '고정 버전의 화석연료 계수 부분집합입니다. 원본 라벨 매핑은 사용자의 근거·개발 가정이며 공식 적용 승인이나 최신 규정 전체 구현이 아닙니다.'}


def formatted(number):
    if number is None:
        return None
    return format(number.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP), 'f')


def compute(records, body):
    """Pure function: selected full DB slice, explicit mapping, Decimal arithmetic."""
    annual = body.scope.dataset == 'real_annual'
    mappings = {m.fuel_label:m for m in body.fuel_mappings}
    blockers = []
    warnings = ['OFFICIAL_CII_NOT_ASSESSED', 'NO_CH4_N2O_OR_LIFECYCLE_EMISSIONS']
    if not annual:
        warnings.append('SYNTHETIC_DATA_DEVELOPMENT_ONLY')
    fuel_total = co2 = intensity = reported = distance = None
    breakdown = []
    intensity_blockers = []
    with localcontext() as ctx:
        ctx.prec = 50
        if not records:
            blockers.append('NO_ELIGIBLE_RECORDS')
        elif annual:
            # Do not add possibly overlapping reporting records or invent a fuel split.
            blockers += ['MISSING_FUEL_BREAKDOWN', 'MISSING_VERIFIED_DISTANCE', 'MISSING_CAPACITY']
            if len(records) != 1:
                blockers.append('MULTIPLE_ANNUAL_RECORDS_REQUIRE_REVIEW')
            else:
                fuel_total = records[0]['fuel_t']
                reported = records[0]['co2_t']
        else:
            fuel_total = sum((r['fuel_t'] for r in records), Decimal(0))
            distance = sum((r['distance_nm'] for r in records), Decimal(0))
            if len({r['report_date'] for r in records}) != len(records):
                blockers.append('DUPLICATE_REPORT_DATES')
            for label in sorted({r['fuel_type'] for r in records}):
                if label not in mappings:
                    blockers.append('UNMAPPED_FUEL:' + label)
                    continue
                mapping = mappings[label]
                amount = sum((r['fuel_t'] for r in records if r['fuel_type'] == label), Decimal(0))
                factor = FACTORS[mapping.category]
                breakdown.append({'fuel_label': label, 'category': mapping.category,
                                  'fuel_t': str(amount), 'factor': str(factor),
                                  'co2_t': str(amount*factor), 'mapping_evidence': mapping.evidence,
                                  'mapping_verified': False})
            if not blockers:
                co2 = sum((Decimal(x['co2_t']) for x in breakdown), Decimal(0))
            dwts = {r['dwt_t'] for r in records}
            types = {r['ship_type'] for r in records}
            if not types.issubset({'Bulk carrier', 'Container ship', 'Oil tanker'}) or len(types) != 1:
                intensity_blockers.append('CAPACITY_BASIS_REQUIRES_REVIEW_GT_OR_OTHER')
            if len(dwts) != 1 or None in dwts or any(v is not None and v <= 0 for v in dwts):
                intensity_blockers.append('MISSING_OR_INCONSISTENT_DWT')
            if distance <= 0:
                intensity_blockers.append('ZERO_TOTAL_DISTANCE')
            if co2 is None:
                intensity_blockers.append('CO2_UNAVAILABLE')
            if not intensity_blockers:
                intensity = co2 * Decimal(1000000) / (next(iter(dwts))*distance)
            expected = (body.scope.end-body.scope.start).days+1
            if len({r['report_date'] for r in records}) != expected:
                warnings.append('INCOMPLETE_REQUESTED_DATES')
            warnings += ['PERIOD_INTENSITY_NOT_ANNUAL_CII', 'USER_FUEL_MAPPING_NOT_VERIFIED']
        if annual or not records:
            intensity_blockers = ['INSUFFICIENT_VERIFIED_INPUTS']
        result = {'tool': 'role4_co2', 'version': VERSION, 'factor_catalog': catalog(),
                  'scope': body.scope.model_dump(mode='json'),
                  'data_origin': 'REAL' if annual else 'SYNTHETIC', 'record_count': len(records),
                  'status': 'calculated' if co2 is not None else 'blocked',
                  'fuel_t': formatted(fuel_total), 'calculated_co2_t': formatted(co2),
                  'source_reported_co2_t': formatted(reported), 'distance_nm': formatted(distance),
                  'period_dwt_intensity': formatted(intensity), 'fuel_breakdown': breakdown,
                  'blockers': blockers, 'intensity_blockers': intensity_blockers,
                  'warnings': warnings, 'official_cii': None, 'official_cii_rating': None,
                  'compliance': 'not_assessed',
                  'official_readiness_missing': ['verified_real_inputs', 'applicable_ship_type_and_capacity',
                      'complete_calendar_year_and_DCS_scope', 'corrections_and_exclusions',
                      'year_specific_reference_reduction_rating_rules', 'verification'],
                  'formulas': {'co2_t':'sum(fuel_t_by_type * CF)',
                      'period_dwt_intensity':'CO2_t * 1000000 / (DWT_t * distance_nm)'},
                  'units': {'fuel_t':'t', 'calculated_co2_t':'t CO2', 'source_reported_co2_t':'t CO2',
                      'distance_nm':'nm', 'period_dwt_intensity':'gCO2/(DWT t * nm)'},
                  'rounding': 'Decimal precision=50; final values 6 places ROUND_HALF_UP; breakdown unrounded',
                  'input_snapshot': json_value(records),
                  'request_snapshot': body.model_dump(mode='json'), 'method_source': CII_SOURCE}
    return result


def calculate(engine, body):
    if engine.dialect.name != 'postgresql':
        raise HTTPException(503, 'PostgreSQL role4 적재가 필요합니다.')
    annual = body.scope.dataset == 'real_annual'
    view = 'role4.real_annual_query' if annual else 'role4.development_noon_query'
    predicate = 'r.reporting_year=:year' if annual else 'r.report_date BETWEEN :start AND :end'
    try:
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
                conn.execute(text("SET LOCAL statement_timeout = '5s'"))
                rows = conn.execute(text(f'''SELECT r.*, s.sha256 AS source_sha256, s.filename AS source_filename
                    FROM {view} r JOIN role4.source_files s USING(source_id)
                    WHERE r.vessel_id=:vessel_id AND {predicate} ORDER BY r.record_id LIMIT 1001'''),
                    body.scope.model_dump()).mappings().all()
    except SQLAlchemyError:
        raise HTTPException(503, '계산 입력의 DB 연결·스키마·조회 범위를 확인하세요.') from None
    if len(rows) > 1000:
        raise HTTPException(422, '1000행을 초과하는 입력은 계산하지 않습니다. 조회 범위를 줄여 주세요.')
    return compute([dict(r) for r in rows], body)
