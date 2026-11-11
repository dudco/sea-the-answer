"""Real authenticated HTTP/SQL path for form-free clarification and fresh results."""
from fastapi.testclient import TestClient

from api import main
from api import navigation_query
from rag_postgres_support import login
from test_workflow_skills import database
from test_navigation_expansion import expanded_data
from tools.navigation_references import NavigationCatalog


def test_typed_replies_complete_one_conversation_and_requery_current_period(database):
    actor={'id':'fixture','role':'admin'}
    for identifier,name in [('conversation-a','해답호'),('conversation-b','별빛호')]:
        database.change(actor,'ship.save',{'id':identifier,'name':name,'type':'Bulk carrier','dwt':1000,'sample':True})
    for day,fuel in [('2025-01-01',2),('2025-02-01',3)]:
        database.change(actor,'operation.save',{'ship':'conversation-a','date':day,'fuel':fuel,'factor':3.114,
            'distance':100,'speed':10,'fuelType':'가상 연료','version':0,'sample':True})
    client=TestClient(main.app,base_url='http://localhost:5173');headers=login(client,'crew')
    def ask(question,parent=None,conversation=None):
        body={'question':question,'task':'auto','mode':'extractive','context':{}}
        if parent:body['context']['previousQueryId']=parent['id']
        if conversation:body['conversationId']=conversation
        response=client.post('/api/ask',headers=headers,json=body)
        assert response.status_code==200,response.text
        return response.json()
    first=ask('우리 배 연료 사용량을 알려줘')
    assert first['workflow']['clarification']['field']=='ships'
    second=ask('해답호',first,first['id'])
    assert second['workflow']['clarification']['field']=='periods'
    third=ask('2025년 1월',second,first['id'])
    january=third['workflow']['results'][0]['result']
    assert january['fuel_t']=='2.000000' and january['missing_days']==30
    fourth=ask('2월은?',third,first['id'])
    february=fourth['workflow']['results'][0]['result']
    assert february['fuel_t']=='3.000000' and february['missing_days']==27
    assert fourth['workflow']['previous_query_id']==third['id']
    turns=client.get('/api/conversations/'+first['id']).json()['turns']
    assert len(turns)==4 and all(t['answer'].get('conversationId',t['id'])==first['id'] for t in turns)
    # A parent from the same account but another conversation cannot supply slots.
    another=ask('별빛호 2025년 3월 운항 실적을 요약해줘')
    rejected=ask('그럼 2월은?',third,another['id'])
    assert rejected['status']=='needs_input' and not rejected['workflow']['results']
    assert rejected['workflow']['previous_query_id'] is None


def test_ais_status_wording_in_ai_mode_uses_actual_http_catalog_reader_not_generated_text(database,monkeypatch):
    catalog=NavigationCatalog.model_validate(expanded_data())
    monkeypatch.setattr(navigation_query.service,'load_snapshot',lambda:(catalog,'a'*64))
    def unrelated_path(*args,**kwargs):
        raise AssertionError('AIS snapshot questions must not invoke document search or generation')
    monkeypatch.setattr(database,'search',unrelated_path)
    monkeypatch.setattr(database,'grounded_response',unrelated_path)
    client=TestClient(main.app,base_url='http://localhost:5173');headers=login(client,'crew')
    questions=['AIS 있어?','AIS 관련 데이터 있어?','실시간 AIS 데이터야?',
               'AIS 정보는 최신이야?','수집한 AIS 데이터가 몇 건이야?','Do we have AIS data?',
               'AIS 관련 정보를 알려줘','AIS 정보 알려줘','Please show me AIS data']
    for question in questions:
        response=client.post('/api/ask',headers=headers,json={'question':question,'task':'auto','mode':'llm'})
        assert response.status_code==200,response.text
        answer=response.json()
        assert answer['navigation']['kind']=='catalog-status' and answer['generation']=='tool'
        assert answer['navigation']['catalog']['ais_observation_count']==len(catalog.observations)
        assert not answer['evidence'] and not answer['statements']
        assert '실시간 수신 여부' in answer['notice'] or 'live feed' in answer['notice']
        assert answer['navigation']['admission']=='not_assessed'
    history=client.get('/api/history').json()['history']
    assert len(history)==len(questions)


def test_formula_explanation_does_not_attach_unrequested_operation_totals(database, prepared_lexical):
    actor={'id':'fixture','role':'admin'}
    database.change(actor,'ship.save',{'id':'formula-ship','name':'계산 검증호','type':'Bulk carrier','dwt':1000,'sample':True})
    database.change(actor,'operation.save',{'ship':'formula-ship','date':'2025-01-01','fuel':2,'factor':3.114,
        'distance':100,'speed':10,'fuelType':'가상 연료','version':0,'sample':True})
    client=TestClient(main.app,base_url='http://localhost:5173');headers=login(client,'crew')
    for question in ['연료 사용량 계산식 알려줘','CO2 배출계수를 알려줘','CII의 뜻을 알려줘']:
        response=client.post('/api/ask',headers=headers,json={'question':question,'task':'auto','mode':'extractive',
            'context':{'ship':'formula-ship','from':'2025-01-01','to':'2025-01-31'}})
        assert response.status_code==200,response.text
        answer=response.json()
        assert not answer.get('workflow') and not answer.get('operations') and not answer.get('toolRuns')
        assert 'OPERATIONS_CONTEXT_REQUIRED' not in answer['warnings']
