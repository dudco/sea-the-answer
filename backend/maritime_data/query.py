"""Bounded, parameterized queries over the two approved maritime_data views."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError


class QueryBase(BaseModel):
    model_config = ConfigDict(extra='forbid')
    limit: int = Field(default=50, ge=1, le=200, strict=True)
    offset: int = Field(default=0, ge=0, le=100000, strict=True)


class AnnualQuery(QueryBase):
    dataset: Literal['real_annual']
    year_start: int = Field(ge=1900, le=2100, strict=True)
    year_end: int = Field(ge=1900, le=2100, strict=True)
    vessel_id: str | None = Field(default=None, pattern=r'^REAL:IMO:[0-9]{7}$')

    @model_validator(mode='after')
    def period(self):
        if not 0 <= self.year_end - self.year_start <= 10:
            raise ValueError('연도 범위는 시작부터 종료까지 최대 10년 차이입니다.')
        return self


class NoonQuery(QueryBase):
    dataset: Literal['synthetic_noon']
    start: date
    end: date
    vessel_id: str | None = Field(default=None, pattern=r'^SYN:[A-Za-z0-9_-]+$', max_length=120)
    voyage_id: str | None = Field(default=None, pattern=r'^SYN:[A-Za-z0-9_-]+$', max_length=120)

    @model_validator(mode='after')
    def period(self):
        if not 0 <= (self.end - self.start).days <= 366:
            raise ValueError('조회 기간은 최대 366일 차이입니다.')
        return self


MaritimeDataQuery = Annotated[AnnualQuery | NoonQuery, Field(discriminator='dataset')]


def json_value(value):
    # Keep PostgreSQL NUMERIC precision; preserve NULL and original JSON metadata.
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    return value


def query(engine, body: AnnualQuery | NoonQuery):
    """Internal Tool entry point. HTTP callers must pass admin authorization first."""
    if engine.dialect.name != 'postgresql':
        raise HTTPException(503, '해사 데이터 조회는 PostgreSQL과 적재된 maritime_data 스키마가 필요합니다.')
    annual = isinstance(body, AnnualQuery)
    # All SQL identifiers and clauses are server-owned constants.
    view = 'maritime_data.real_annual_query' if annual else 'maritime_data.development_noon_query'
    period = 'r.reporting_year BETWEEN :year_start AND :year_end' if annual else 'r.report_date BETWEEN :start AND :end'
    clauses = [period]
    if body.vessel_id is not None:
        clauses.append('r.vessel_id = :vessel_id')
    if not annual and body.voyage_id is not None:
        clauses.append('r.voyage_id = :voyage_id')
    where = ' AND '.join(clauses)
    order = 'r.reporting_year, r.vessel_id, r.record_id' if annual else 'r.report_date, r.vessel_id, r.record_id'
    params = body.model_dump()
    params['fetch_limit'] = body.limit + 1
    try:
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
                conn.execute(text("SET LOCAL statement_timeout = '5s'"))
                total = conn.execute(text(f'SELECT count(*) FROM {view} r WHERE {where}'), params).scalar_one()
                rows = conn.execute(text(f'''SELECT r.*, s.dataset_id, s.filename AS source_filename,
                    s.sha256 AS source_sha256, s.source_url, s.data_origin
                    FROM {view} r JOIN maritime_data.source_files s ON s.source_id = r.source_id
                    WHERE {where} ORDER BY {order} LIMIT :fetch_limit OFFSET :offset'''), params).mappings().all()
    except SQLAlchemyError:
        raise HTTPException(503, '해사 데이터 DB 연결·스키마 상태를 확인하거나 조회 범위를 줄여 주세요.') from None
    has_more = len(rows) > body.limit
    return {
        'contract_version': '1.0', 'dataset': body.dataset,
        'data_origin': 'REAL' if annual else 'SYNTHETIC',
        'granularity': 'reporting_period' if annual else 'daily',
        'filters': body.model_dump(mode='json', exclude={'limit', 'offset'}),
        'units': {'fuel_t': 't', 'co2_t': 't CO2', 'sea_hours': 'h', 'fuel_kg_per_nm': 'kg/nm',
                  'distance_nm_estimate': 'nm (estimated)', 'dwt_t': 't'} if annual else
                 {'fuel_t': 't', 'distance_nm': 'nm', 'dwt_t': 't', 'speed_kn': 'kn', 'engine_hours': 'h'},
        'numeric_encoding': 'decimal_string',
        'rows': [json_value(dict(row)) for row in rows[:body.limit]],
        'total': total, 'limit': body.limit, 'offset': body.offset,
        'has_more': has_more, 'next_offset': body.offset + body.limit if has_more else None,
        'warnings': [
            '공식 CII 계산·등급 판정 결과가 아닙니다.',
            'VALID는 전처리 규칙 통과를 의미합니다.',
            *(['PARTIAL 및 집계 부적격 레코드는 제외됩니다.',
               '역산 거리는 추정치이며 연간 자료를 일별·항차별로 해석하지 않습니다.',
               '연도별 보고 선박 집단이 같다고 가정하지 않습니다.'] if annual else
              ['개발용 합성 데이터입니다. 실제 선박 운항으로 해석하지 않습니다.'])
        ],
    }
