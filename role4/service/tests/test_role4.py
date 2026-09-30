import os
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import create_engine, text, event
from sqlalchemy.exc import OperationalError
from fastapi import HTTPException
from unittest.mock import MagicMock

from service import role4
from service.tests.api_support import app, login


ANNUAL = {'dataset': 'real_annual', 'year_start': 2015, 'year_end': 2025}
NOON = {'dataset': 'synthetic_noon', 'start': '2025-01-01', 'end': '2025-12-31'}
adapter = TypeAdapter(role4.Role4Query)


@pytest.mark.parametrize('body', [
    {**ANNUAL, 'year_start': 2026}, {**ANNUAL, 'year_start': 2010},
    {**ANNUAL, 'year_start': '2020'}, {**ANNUAL, 'limit': 201},
    {**ANNUAL, 'offset': -1}, {**ANNUAL, 'limit': True},
    {**ANNUAL, 'vessel_id': 'SYN:SIM-BULK-01'},
    {**ANNUAL, 'sql': 'DROP SCHEMA role4 CASCADE'},
    {**ANNUAL, 'vessel_id': "REAL:IMO:1234567' OR 1=1--"},
    {**NOON, 'vessel_id': 'REAL:IMO:1234567'},
    {**NOON, 'start': '2025-02-30'}, {**NOON, 'end': '2024-01-01'},
    {**NOON, 'end': '2027-01-01'}, {**NOON, 'voyage_id': "'; DELETE FROM role4.vessels--"},
    {**NOON, 'dataset': 'source_files'},
])
def test_invalid_contract(body):
    with pytest.raises(ValidationError):
        adapter.validate_python(body)




def test_unavailable_database_is_explicit(app):
    response = login(app).post('/api/role4/query', json=ANNUAL)
    assert response.status_code == 503
    assert 'PostgreSQL' in response.json()['detail']


def test_decimal_null_and_zero_preserved():
    assert role4.json_value({'fuel_t': Decimal('123456789.123456789'), 'dwt_t': None,
                             'distance_nm': Decimal('0')}) == {
        'fuel_t': '123456789.123456789', 'dwt_t': None, 'distance_nm': '0'}


def test_db_failure_does_not_expose_sql_or_credentials():
    engine = MagicMock()
    engine.dialect.name = 'postgresql'
    engine.connect.side_effect = OperationalError('SECRET SQL', {}, Exception('SECRET PASSWORD'))
    with pytest.raises(HTTPException) as exc:
        role4.query(engine, adapter.validate_python(ANNUAL))
    assert exc.value.status_code == 503 and 'SECRET' not in exc.value.detail


@pytest.fixture
def pg_engine():
    # Opt-in only. Use the already-loaded dataset without creating or changing tables.
    url = os.getenv('ROLE4_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set ROLE4_TEST_DATABASE_URL to validate the existing PostgreSQL dataset')
    engine = create_engine(url, connect_args={'connect_timeout': 5}, hide_parameters=True)
    yield engine
    engine.dispose()


def test_postgres_queries_match_loaded_dataset(pg_engine):
    settings = []

    def inspect_transaction(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith('SELECT'):
            cursor.execute("SELECT current_setting('transaction_read_only'), "
                           "current_setting('transaction_isolation'), current_setting('statement_timeout')")
            settings.append(cursor.fetchone())

    event.listen(pg_engine, 'before_cursor_execute', inspect_transaction)
    annual = role4.query(pg_engine, adapter.validate_python({**ANNUAL, 'limit': 2}))
    event.remove(pg_engine, 'before_cursor_execute', inspect_transaction)
    assert len(settings) == 2 and all(tuple(s) == ('on', 'repeatable read', '5s') for s in settings)
    assert annual['total'] == 79032
    assert annual['has_more'] and annual['next_offset'] == 2
    assert all(r['quality_status'] == 'VALID' and r['report_type'] != 'PARTIAL'
               and r['data_origin'] == 'REAL' and r['dwt_t'] is None for r in annual['rows'])
    second = role4.query(pg_engine, adapter.validate_python({**ANNUAL, 'limit': 2, 'offset': 2}))
    assert {r['record_id'] for r in annual['rows']}.isdisjoint(r['record_id'] for r in second['rows'])
    assert annual == role4.query(pg_engine, adapter.validate_python({**ANNUAL, 'limit': 2}))
    record = annual['rows'][0]
    with pg_engine.connect() as conn:
        conn.execute(text('SET TRANSACTION READ ONLY'))
        raw = conn.execute(text('SELECT fuel_t, source_id FROM role4.annual_reports WHERE record_id=:id'),
                           {'id': record['record_id']}).one()
    assert record['fuel_t'] == str(raw.fuel_t) and record['source_id'] == raw.source_id
    assert len(record['source_sha256']) == 64 and record['source_filename']
    scoped = role4.query(pg_engine, adapter.validate_python({**ANNUAL, 'vessel_id': record['vessel_id']}))
    assert scoped['rows'] and all(r['vessel_id'] == record['vessel_id'] for r in scoped['rows'])
    empty = role4.query(pg_engine, adapter.validate_python({**ANNUAL, 'year_start': 1900, 'year_end': 1900}))
    assert empty['total'] == 0 and empty['rows'] == [] and empty['next_offset'] is None
    beyond = role4.query(pg_engine, adapter.validate_python({**ANNUAL, 'offset': 80000}))
    assert beyond['total'] == 79032 and beyond['rows'] == [] and not beyond['has_more']

    noon = role4.query(pg_engine, adapter.validate_python(NOON))
    assert noon['total'] == 4380 and noon['data_origin'] == 'SYNTHETIC'
    first = noon['rows'][0]
    scoped = role4.query(pg_engine, adapter.validate_python({**NOON,
        'vessel_id': first['vessel_id'], 'voyage_id': first['voyage_id']}))
    assert scoped['rows'] and all(r['vessel_id'] == first['vessel_id'] and
                                 r['voyage_id'] == first['voyage_id'] for r in scoped['rows'])
    day = role4.query(pg_engine, adapter.validate_python({**NOON, 'start': first['report_date'],
                                                         'end': first['report_date']}))
    assert day['rows'] and all(r['report_date'] == first['report_date'] for r in day['rows'])
    zero_count = 0
    seen = set()
    offset = 0
    while True:
        page = role4.query(pg_engine, adapter.validate_python({**NOON, 'limit': 200, 'offset': offset}))
        for row in page['rows']:
            assert row['record_id'] not in seen and row['data_origin'] == 'SYNTHETIC'
            seen.add(row['record_id'])
            zero_count += Decimal(row['distance_nm']) == 0
        if not page['has_more']:
            break
        offset = page['next_offset']
    assert len(seen) == 4380 and zero_count == 557


def test_postgres_api_with_isolated_auth(app, pg_engine, monkeypatch):
    original = role4.query
    monkeypatch.setattr(role4, 'query', lambda engine, body: original(pg_engine, body))
    # Token authentication is isolated; the loaded PostgreSQL data is read only.
    response = login(app).post('/api/role4/query', json={**NOON, 'limit': 1})
    assert response.status_code == 200
    result = response.json()
    assert result['total'] == 4380 and len(result['rows']) == 1
    assert isinstance(result['rows'][0]['fuel_t'], str)
    assert result['rows'][0]['provenance_json']
