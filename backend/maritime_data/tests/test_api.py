import pytest
from fastapi.testclient import TestClient
from backend.maritime_data.api import create_app
from backend.maritime_data import query as maritime_data, calculations as maritime_data_calculations
from backend.maritime_data.tests.api_support import app, login, TOKEN

QUERY = {'dataset': 'real_annual', 'year_start': 2020, 'year_end': 2025}
CALC = {'scope': {'dataset': 'real_annual', 'vessel_id': 'REAL:IMO:1234567', 'year': 2020}}

@pytest.mark.parametrize('path,payload', [
    ('/api/maritime-data/query', QUERY), ('/api/maritime-data/calculate', CALC),
    ('/api/maritime-data/ask', {'question': '기록 조회', 'scope': QUERY}),
    ('/api/maritime-data/factors', None)])
def test_all_tools_require_token(app, path, payload):
    client = TestClient(app)
    def request(headers):
        return client.get(path, headers=headers) if payload is None else client.post(path, json=payload, headers=headers)
    assert request({}).status_code == 401
    assert request({'Authorization': 'Bearer wrong'}).status_code == 403
    assert request({'Authorization': 'Basic ' + TOKEN}).status_code == 401

def test_query_validation_and_dispatch(app, monkeypatch):
    seen = []
    monkeypatch.setattr(maritime_data, 'query', lambda engine, body: seen.append(body) or {'rows': [], 'total': 0})
    client = login(app)
    assert client.post('/api/maritime-data/query', json={**QUERY, 'sql': 'SELECT 1'}).status_code == 422
    assert not seen
    assert client.post('/api/maritime-data/query', json=QUERY).json()['total'] == 0
    assert len(seen) == 1

def test_calculation_dispatch_and_factors(app, monkeypatch):
    monkeypatch.setattr(maritime_data_calculations, 'calculate', lambda engine, body: {'status': 'blocked'})
    client = login(app)
    assert client.get('/api/maritime-data/factors').json()['factors']['HFO'] == '3.114'
    assert client.post('/api/maritime-data/calculate', json=CALC).json()['status'] == 'blocked'

def test_rule_helper_rejects_unsupported_and_preserves_scope(app, monkeypatch):
    seen = []
    monkeypatch.setattr(maritime_data, 'query', lambda engine, body: seen.append(body.model_dump()) or {'rows': [], 'total': 0})
    client = login(app)
    result = client.post('/api/maritime-data/ask', json={'question': 'CII 등급 계산', 'scope': QUERY}).json()
    assert result['result'] is None and not seen
    result = client.post('/api/maritime-data/ask', json={'question': '기록 조회', 'scope': QUERY, 'use_model': True}).json()
    assert result['routing'] == 'rules' and 'LLM_NOT_CONFIGURED' in result['warnings']
    assert seen[0]['year_start'] == QUERY['year_start']

def test_missing_token_fails_closed(monkeypatch):
    with pytest.raises(RuntimeError):
        create_app('sqlite://', '')
