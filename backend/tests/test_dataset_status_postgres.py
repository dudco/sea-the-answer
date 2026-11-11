"""Real PostgreSQL inventory and authenticated HTTP queries; disposable databases only."""
from pathlib import Path

from fastapi.testclient import TestClient
import psycopg
import pytest
from sqlalchemy import create_engine, event

from api import dataset_status, main
from tools.dataset_status import read_status
from test_maritime_migrations import postgres_dsn, apply_initial, apply_maritime, seed_source_data
from test_workflow_skills import database
from rag_postgres_support import login


@pytest.fixture
def inventory(postgres_dsn):
    apply_initial(postgres_dsn);apply_maritime(postgres_dsn);seed_source_data(postgres_dsn)
    migration=Path(__file__).resolve().parents[2]/'migrations/20261013020000_capacity_candidates.sql'
    with psycopg.connect(postgres_dsn) as db:
        db.execute(migration.read_text(encoding='utf-8').split('-- migrate:up',1)[1].split('-- migrate:down',1)[0])
        db.execute('UPDATE maritime_data.source_files SET row_count=999')
    engine=create_engine('postgresql+psycopg://',creator=lambda:psycopg.connect(postgres_dsn),hide_parameters=True)
    try:yield engine,postgres_dsn
    finally:engine.dispose()


def test_actual_rows_eligible_rows_empty_sources_and_year_scope_are_distinct(inventory):
    engine,dsn=inventory;commands=[]
    event.listen(engine,'before_cursor_execute',lambda c,cu,s,p,ct,m:commands.append(s))
    result=read_status(engine,'mrv')
    assert result['row_count']==1 and result['eligible_count']==1 and result['vessel_count']==1
    assert result['first_period']==result['last_period']=='2025'
    assert result['sources'][0]['row_count']==1  # not the declared source file count of 999
    assert read_status(engine,'mrv',years=[2024])['status']=='empty'
    assert read_status(engine,'noon')['row_count']==0 and read_status(engine,'dwt')['row_count']==0
    with psycopg.connect(dsn) as db:
        db.execute("UPDATE maritime_data.annual_reports SET quality_status='REVIEW',aggregate_eligible=false")
    updated=read_status(engine,'mrv',vessel_id='REAL:IMO:9074729',years=[2025])
    assert updated['row_count']==1 and updated['eligible_count']==0
    assert any('READ ONLY' in c for c in commands) and any('statement_timeout' in c for c in commands)
    with psycopg.connect(dsn) as db:
        assert db.execute('SELECT count(*) FROM maritime_data.annual_reports').fetchone()[0]==1


@pytest.mark.parametrize('dataset,vessel,years',[
    ('annual_reports; DROP TABLE ships',None,()),('mrv',"REAL:IMO:9074729' OR true --",()),
    ('mrv',None,('2025',)),('mrv',None,(True,)),
])
def test_nonapproved_identifiers_and_filters_never_reach_sql(inventory,dataset,vessel,years):
    with pytest.raises(ValueError):read_status(inventory[0],dataset,vessel_id=vessel,years=years)


def test_inventory_http_uses_registered_sql_and_distinguishes_missing_conditions(database,inventory,monkeypatch):
    engine,_=inventory
    monkeypatch.setattr(dataset_status,'create_engine_for',lambda _:engine)
    monkeypatch.setattr(dataset_status.config,'database_url',lambda:'postgresql://fixture.invalid')
    def no_document_fallback(*a,**k):raise AssertionError('inventory must not retrieve unrelated evidence')
    monkeypatch.setattr(type(database),'search',no_document_fallback)
    client=TestClient(main.app,base_url='http://localhost:5173')
    assert client.post('/api/ask',json={'question':'MRV 데이터 있어?'}).status_code in (401,403)
    headers=login(client,'crew')
    for q in ['mrv 관련 데이터 있어?','MRV 관련 정보를 알려줘','2025년 MRV 자료가 몇 건이야?', 'Do we have MRV data?']:
        response=client.post('/api/ask',headers=headers,json={'question':q,'task':'auto','mode':'llm'})
        assert response.status_code==200,response.text
        value=response.json()
        assert value['dataStatus']['datasets'][0]['row_count']==1
        assert value['dataStatus']['datasets'][0]['eligible_count']==1
        assert value['generation']=='tool' and value['evidence']==[]
    empty=client.post('/api/ask',headers=headers,json={'question':'2024년 MRV 데이터 있어?'}).json()
    assert empty['dataStatus']['datasets'][0]['status']=='empty'
    assert empty['dataStatus']['datasets'][0]['row_count']==0
    unsupported=client.post('/api/ask',headers=headers,json={'question':'2025년 1월 MRV 자료 있어?'}).json()
    assert unsupported['dataStatus']['datasets'][0]['status']=='unsupported_scope'
    ops=client.post('/api/ask',headers=headers,json={'question':'등록된 일별 운항 기록이 몇 건이야?'}).json()
    assert ops['dataStatus']['datasets'][0]['row_count']==0
    history=client.get('/api/history').json()['history']
    assert len(history)==7
