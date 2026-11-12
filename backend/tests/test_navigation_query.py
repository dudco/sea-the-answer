"""Natural questions select current app identities and sources without touching generic RAG."""
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from api import navigation_query as query, deps, main
from api.errors import ApiError
from api.web import security
from test_fastapi_api import FakeWorkspace, ADMIN
from test_navigation_expansion import expanded_data
from test_navigation_references import IMO, NOW
from tools.navigation_references import NavigationCatalog, NavigationScreenRequest, screen_references
from test_workflow_skills import database  # rollback-only PostgreSQL fixture
from rag_postgres_support import login

SHIPS=[{'id':'ship-1','name':'검증 선박','imo':IMO,'version':3},
       {'id':'ship-2','name':'별빛호','imo':'9074729','version':1}]


class Store:
    def __init__(self):
        self.rows=deepcopy(SHIPS);self.writes=[];self.audits=[]
    def ships(self): return self.rows
    def run(self,*args): self.writes.append(args)
    def audit(self,*args): self.audits.append(args)


@pytest.fixture
def setup(monkeypatch):
    catalog=NavigationCatalog.model_validate(expanded_data())
    snapshot=(catalog,'a'*64)
    loader=Mock(return_value=snapshot)
    monkeypatch.setattr(query.service,'load_snapshot',loader)
    def compare(db,ship,*,port_ids,berth_id,snapshot):
        s=next(s for s in db.ships() if s['id']==ship)
        return {'status':'ok','context':{'ship':ship,'ship_version':s['version'],'vessel_id':'REAL:IMO:'+s['imo'],'imo_number':s['imo']},
            'results':[screen_references(snapshot[0],NavigationScreenRequest(vessel_id='REAL:IMO:'+s['imo'],port_id=p,berth_id=berth_id),now=NOW,sha256=snapshot[1]) for p in port_ids]}
    calculator=Mock(side_effect=compare)
    monkeypatch.setattr(query.service,'compare_ship',calculator)
    ctx=SimpleNamespace(db=Store(),user=ADMIN,body={'question':'우리 배가 입항 가능한 항구가 어디야?','context':{'ship':'ship-1'}})
    return ctx,loader,calculator


@pytest.mark.parametrize('question',['우리 배가 입항 가능한 항구가 어디야?','우리배가입항가능한항구',
    '우리 선박이 들어갈 수 있는 항만 알려줘','Which ports can our ship enter?'])
def test_list_question_uses_all_available_ports_and_saves_owned_answer(setup,question):
    ctx,loader,calculator=setup;ctx.body['question']=question
    reply=query.try_answer(ctx)
    assert calculator.call_args.kwargs['port_ids']==['WPI:24020','WPI:28190']
    assert reply['generation']=='tool' and reply['evidence']==[] and reply['statements']==[]
    assert reply['navigation']['admission']=='not_assessed' and len(reply['navigation']['ports'])==2
    assert len(ctx.db.writes)==2 and ctx.db.writes[1][1][1]==ADMIN['id']


@pytest.mark.parametrize('question',[f'IMO {IMO} 선박이 헬싱키에 입항 가능해?',
    f'Can IMO {IMO} enter Helsinki?',f'IMO {IMO} 헬싱키 LHD 선석에 입항 가능해?'])
def test_exact_imo_and_named_port_override_a_different_selected_context(setup,question):
    ctx,loader,calculator=setup;ctx.body.update(question=question,context={'ship':'ship-2'})
    reply=query.try_answer(ctx)
    assert calculator.call_args.args[1]=='ship-1'
    assert calculator.call_args.kwargs['port_ids']==['WPI:28190']
    assert reply['navigation']['context']['imo_number']==IMO


@pytest.mark.parametrize('question',['부산항에 입항 가능해?','우리 배가 Oslo에 입항 가능해?',
    'Can our ship enter Oslo?','헬싱키 선석 999에 접안 가능해?'])
def test_unknown_port_or_berth_never_substitutes_another_target(setup,question):
    ctx,loader,calculator=setup;ctx.body['question']=question
    reply=query.try_answer(ctx)
    assert reply['navigation']['status'] in ('unsupported_port','unsupported_berth')
    calculator.assert_not_called()


@pytest.mark.parametrize('question',['문서만 사용해서 입항 가능한 항구를 설명해줘','입항 규정의 뜻이 뭐야?',
    '입항 전 항만에 보고할 사항은?', '항구에 입항하는 방법 알려줘',
    '어느 항구에 입항 서류를 제출해야 해?', 'Which documents are required to enter Helsinki?',
    '연료 사용량을 계산해줘','What is the definition of a berth?'])
def test_unrelated_or_document_questions_keep_existing_pipeline(setup,question):
    ctx,loader,calculator=setup;ctx.body['question']=question
    assert query.try_answer(ctx) is None and not ctx.db.writes
    loader.assert_not_called();calculator.assert_not_called()


def test_explicit_documents_mode_is_never_intercepted(setup):
    ctx,loader,calculator=setup;ctx.body['task']='documents'
    assert query.try_answer(ctx) is None
    loader.assert_not_called()


@pytest.mark.parametrize('question',['AIS 관련 데이터 있어?','AIS데이터 있어?','AIS 자료 등록되어 있어?','AIS 데이터 출처와 수집 현황 알려줘','Do we have AIS data?'])
def test_ais_availability_uses_loaded_catalog_not_document_search_or_ship_mapping(setup,question,monkeypatch):
    ctx,loader,calculator=setup;ctx.body['question']=question
    summarize=query.catalog_summary
    clock=max(s.retrieved_at for s in loader.return_value[0].sources)+timedelta(days=2)
    monkeypatch.setattr(query,'catalog_summary',lambda c,h:summarize(c,h,now=clock))
    answer=query.try_answer(ctx);nav=answer['navigation'];catalog=loader.return_value[0]
    assert nav['kind']=='catalog-status' and nav['status']=='available'
    assert nav['catalog']['ais_observation_count']==len(catalog.observations)
    assert nav['catalog']['ais_unique_vessels']==len({o.vessel_id for o in catalog.observations})
    assert nav['catalog']['sources'] and nav['catalog']['freshness']['ais_capture_issue']=='AIS_CAPTURE_STALE'
    assert nav['ship'] is None and answer['evidence']==[] and answer['status']=='completed'
    assert 'ship_check' not in nav and nav['admission']=='not_assessed'
    calculator.assert_not_called()


def test_ais_availability_distinguishes_empty_snapshot_from_unreadable_connection(setup):
    ctx,loader,calculator=setup;ctx.body['question']='AIS 데이터 있어?'
    catalog,sha=loader.return_value
    loader.return_value=(catalog.model_copy(update={'observations':[]}),sha)
    empty=query.try_answer(ctx)['navigation']
    assert empty['status']=='empty' and empty['catalog']['ais_observation_count']==0
    loader.side_effect=ApiError(503,'DATA_SOURCE_UNAVAILABLE','synthetic-private-path')
    unavailable=query.try_answer(ctx)
    assert unavailable['navigation']['status']=='unavailable' and unavailable['navigation']['catalog'] is None
    assert 'synthetic-private-path' not in str(unavailable) and '전혀 없다는 뜻' in unavailable['notice']
    calculator.assert_not_called()


def test_specific_ship_ais_presence_uses_exact_current_registered_imo(setup):
    ctx,loader,calculator=setup;ctx.body['question']='우리 배 AIS 데이터 있어?'
    nav=query.try_answer(ctx)['navigation']
    assert nav['ship_check']['status']=='found' and nav['ship_check']['imo_number']==IMO
    ctx.body['question']='IMO 9074729 선박의 AIS 자료 있어?'
    nav=query.try_answer(ctx)['navigation']
    count=sum(o.vessel_id=='REAL:IMO:9074729' for o in loader.return_value[0].observations)
    assert nav['ship']['id']=='ship-2' and nav['ship_check']['observation_count']==count
    assert nav['ship_check']['status']==('found' if count else 'not_in_snapshot')
    ctx.db.rows[0]['sample']=True;ctx.body['question']='우리 배 AIS 자료 있어?'
    assert query.try_answer(ctx)['navigation']['ship_check']['status']=='sample_ship'
    calculator.assert_not_called()


@pytest.mark.parametrize('question',['AIS가 뭐야?','AIS 데이터의 정의를 알려줘','AIS 자료 등록하는 방법은?','AIS 데이터 문서만 사용해서 설명해줘'])
def test_ais_explanations_keep_document_search(setup,question):
    ctx,loader,calculator=setup;ctx.body['question']=question
    assert query.try_answer(ctx) is None
    loader.assert_not_called();calculator.assert_not_called()


@pytest.mark.parametrize('question',['미등록호가 입항 가능한 항구는?','Can vessel TITAN enter Helsinki?',
    'Can TITAN enter Helsinki?', '타이탄이 헬싱키에 입항 가능해?',
    'IMO 12345678 선박이 입항 가능한 항구는?', 'IMO 번호 모르는 선박이 입항 가능한 항구는?',
    'IMO 1234567 선박이 입항 가능한 항구는?',f'IMO {IMO}와 IMO 9074729가 입항 가능한 항구는?'])
def test_unknown_or_ambiguous_ship_does_not_fall_back_to_selected_ship(setup,question):
    ctx,loader,calculator=setup;ctx.body['question']=question
    assert query.try_answer(ctx)['navigation']['status']=='needs_ship'
    calculator.assert_not_called()


def test_missing_context_uses_only_a_unique_real_ship(setup):
    ctx,loader,calculator=setup;ctx.body['context']={}
    assert query.try_answer(ctx)['navigation']['status']=='needs_ship'
    ctx.db.rows=ctx.db.rows[:1]
    assert query.try_answer(ctx)['navigation']['status']=='reference_only'


@pytest.mark.parametrize('question',['우리 배가 입항 가능한 가장 가까운 항구는?',
    '흘수 8m인 우리 배가 입항 가능한 항구는?'])
def test_positions_routes_and_hypothetical_dimensions_are_not_invented(setup,question):
    ctx,loader,calculator=setup;ctx.body['question']=question
    assert query.try_answer(ctx)['navigation']['status'] in ('unsupported_scope','needs_verified_inputs')
    calculator.assert_not_called()


def test_sample_unmapped_and_unavailable_inputs_are_explained(setup):
    ctx,loader,calculator=setup
    ctx.db.rows[0]['sample']=True
    assert query.try_answer(ctx)['navigation']['status']=='needs_real_ship'
    ctx.db.rows[0]['sample']=False
    calculator.side_effect=None;calculator.return_value={'status':'needs_mapping','context':{'ship':'ship-1'},'results':[],'notice':'mapping needed'}
    assert query.try_answer(ctx)['navigation']['status']=='needs_mapping'
    calculator.side_effect=ApiError(503,'DATA_SOURCE_UNAVAILABLE','private details must not escape')
    reply=query.try_answer(ctx)
    assert reply['navigation']['status']=='unavailable' and 'private details' not in str(reply)


def test_normal_ask_endpoint_uses_session_csrf_and_never_calls_generic_rag_for_port_question(setup,monkeypatch):
    monkeypatch.setenv('HAEDAP_QUESTION_ROUTER','legacy')  # rule path kept by ADR 0024
    ctx,loader,calculator=setup
    class BrowserStore(FakeWorkspace,Store):
        writes=[]
        def __init__(self,dsn):
            FakeWorkspace.__init__(self,dsn);self.rows=deepcopy(SHIPS)
        def ships(self): return self.rows
        def run(self,*args): self.writes.append(args)
        def answer(self,*args): raise AssertionError('generic RAG should not run for this question')
    monkeypatch.setattr(deps,'Workspace',BrowserStore);monkeypatch.setattr(deps,'initialized',False)
    security.sessions.clear()
    client=TestClient(main.app,base_url='http://localhost:5173')
    assert client.post('/api/ask',json=ctx.body).status_code==403
    token=client.get('/api/health').json()['csrfToken'];headers={'X-Haedap-Token':token}
    assert client.post('/api/ask',headers=headers,json=ctx.body).status_code==401
    assert client.post('/api/auth/login',headers=headers,json={'username':'admin','password':'1234'}).status_code==200
    reply=client.post('/api/ask',headers=headers,json=ctx.body)
    assert reply.status_code==200 and reply.json()['navigation']['admission']=='not_assessed'
    assert BrowserStore.writes[-1][1][1]==ADMIN['id']
    security.sessions.clear()


def test_navigation_history_is_owned_in_actual_postgres(database,setup):
    ctx,loader,calculator=setup
    actor=database.one("SELECT * FROM users WHERE username='admin'")
    database.change(actor,'ship.save',{'id':'ship-1','name':'검증 선박','imo':IMO,'dwt':1000,'type':'Bulk carrier','version':0})
    crew=TestClient(main.app,base_url='http://localhost:5173');headers=login(crew,'crew')
    answer=crew.post('/api/ask',headers=headers,json=ctx.body)
    assert answer.status_code==200
    answer_id=answer.json()['id']
    own=crew.get('/api/history').json()['history']
    assert any(r['id']==answer_id and r['answer']['navigation']['reference_only'] for r in own)
    other=TestClient(main.app,base_url='http://localhost:5173');login(other,'admin')
    assert all(r['id']!=answer_id for r in other.get('/api/history').json()['history'])


def test_mid_request_account_revocation_rolls_back_navigation_history(database,setup):
    ctx,loader,calculator=setup
    actor=database.one("SELECT * FROM users WHERE username='admin'")
    database.change(actor,'ship.save',{'id':'ship-1','name':'검증 선박','imo':IMO,'dwt':1000,'type':'Bulk carrier','version':0})
    crew_id=database.one("SELECT id FROM users WHERE username='crew'")['id']
    original=calculator.side_effect
    def revoke(*args,**kwargs):
        result=original(*args,**kwargs)
        args[0].run('UPDATE users SET active=false WHERE id=%s',(crew_id,))
        return result
    calculator.side_effect=revoke
    before=database.one('SELECT count(*) AS n FROM queries')['n']
    client=TestClient(main.app,base_url='http://localhost:5173');headers=login(client,'crew')
    response=client.post('/api/ask',headers=headers,json=ctx.body)
    assert response.status_code==401
    assert database.one('SELECT count(*) AS n FROM queries')['n']==before
    assert database.one('SELECT active FROM users WHERE id=%s',(crew_id,))['active'] is True
