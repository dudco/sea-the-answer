"""Wording coverage, closed semantic choices, and reuse of validated executors.

HTTP model replies here are fixtures, not measured LLM classification accuracy.
"""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from api import dataset_intent, dataset_status, question_router as router
from test_question_workflows import DB


class Store(DB):
    def __init__(self):super().__init__();self.document_questions=[]
    def answer(self,user,body):
        self.document_questions.append(deepcopy(body))
        return {'id':'document-answer','task':'documents','evidence':[],'statements':[]}


def context(question, *, mode='extractive', task='auto'):
    return SimpleNamespace(db=Store(),user={'id':'crew-1','role':'operator'},
                           body={'question':question,'mode':mode,'task':task,'context':{}})


@pytest.mark.parametrize('source,dataset',[('MRV','mrv'),('AIS','ais'),('DWT','dwt'),('Noon','noon')])
@pytest.mark.parametrize('wording',[
    '{} 관련 데이터 있어?', '{} 자료가 등록되어 있나요?', '{} 자료 출처를 알려줘',
    '{} 자료는 언제 수집했어?', '{} 데이터가 몇 건이야?', '{} 관련 정보를 알려줘',
    '{}에 대한 자료를 간단히 정리해 줘', 'Do we have {} data?', 'Please show me {} data',
])
def test_inventory_wording_does_not_require_one_literal_question(source,dataset,wording):
    assert dataset_intent.inventory_request(wording.format(source))==[dataset]


@pytest.mark.parametrize('question',[
    'MRV가 뭐야?', 'MRV 원리를 알려줘', 'MRV 데이터 조회 방법은?',
    'MRV가 없으면 어떻게 계산해?', 'AIS 수신기 오류 정보를 알려줘',
    'DWT의 뜻은?', 'AIS 추적해 줘', 'MRV 데이터 삭제해 줘',
    '연료 사용량 계산식 알려줘', 'What is MRV data?',
    '오늘 날씨 정보 있어?', 'MRV 계산에 문제 없어?',
    '항만 기상 자료가 있어?', 'AIS 자료와 실시간 위치도 알려줘',
    '선택한 문서에서 MRV 자료가 있는지 확인해줘', '그 문서에 AIS 정보 있어?',
])
def test_definitions_procedures_mutations_and_conditionals_are_not_inventory(question):
    assert not dataset_intent.inventory_request(question)


@pytest.mark.parametrize('question',['어떤 자료가 있어?','현재 등록된 데이터 종류 알려줘','What data do we have?',
    '지금 어떤 해사 자료들을 사용할 수 있는지 궁금해'])
def test_generic_inventory_only_means_all_when_no_unknown_topic_is_discarded(question):
    assert dataset_intent.inventory_request(question)==list(dataset_intent.DATASETS)


@pytest.mark.parametrize('question',[
    'MRV 관련 데이터 있어?', 'mrv 자료가 등록됐어?', 'MRV 관련 정보를 알려줘',
    'Do we have MRV data?', 'MRV 데이터 출처와 연도 범위를 알려줘',
])
def test_mrv_availability_reads_database_instead_of_rag_or_llm(question,monkeypatch):
    ctx=context(question,mode='llm');engine=Mock()
    monkeypatch.setattr(dataset_status,'create_engine_for',lambda _:engine)
    monkeypatch.setattr(dataset_status.config,'database_url',lambda:'postgresql://fixture')
    reader=Mock(return_value={'status':'available','row_count':12,'vessel_count':3,
        'eligible_count':8,'first_period':'2024','last_period':'2025','sources':[], 'notice':'fixture'})
    monkeypatch.setattr(dataset_status,'read_status',reader)
    planner=Mock(side_effect=AssertionError('deterministic inventory must not call a model'))
    monkeypatch.setattr(router,'model_route',planner)
    answer=router.answer(ctx)
    assert answer['dataStatus']['datasets'][0]['row_count']==12
    assert answer['dataStatus']['datasets'][0]['eligible_count']==8
    assert answer['generation']=='tool' and answer['evidence']==[] and not ctx.db.document_questions
    assert ctx.db.answers[answer['id']]['dataStatus']==answer['dataStatus']
    reader.assert_called_once_with(engine,'mrv',vessel_id=None,years=[])
    engine.dispose.assert_called_once();planner.assert_not_called()


def test_inventory_zero_and_failed_read_are_different(monkeypatch):
    monkeypatch.setattr(dataset_status,'create_engine_for',lambda _:Mock())
    monkeypatch.setattr(dataset_status.config,'database_url',lambda:'postgresql://fixture')
    reader=Mock(return_value={'status':'empty','row_count':0,'vessel_count':0,'eligible_count':0})
    monkeypatch.setattr(dataset_status,'read_status',reader)
    empty=router.answer(context('MRV 데이터 있어?'))['dataStatus']['datasets'][0]
    assert empty['status']=='empty' and empty['row_count']==0
    reader.side_effect=ValueError('private server path')
    failed=router.answer(context('MRV 데이터 있어?'))['dataStatus']['datasets'][0]
    assert failed['status']=='unavailable' and 'row_count' not in failed
    assert 'private server path' not in str(failed)


def test_unknown_ship_and_month_scope_do_not_get_global_counts(monkeypatch):
    reader=Mock(side_effect=AssertionError('unresolved scopes must not query'))
    monkeypatch.setattr(dataset_status,'read_status',reader)
    unknown=router.answer(context('미등록호 MRV 데이터 있어?'))
    assert unknown['status']=='needs_input' and not unknown['dataStatus']['datasets']
    month=router.answer(context('2025년 1월 MRV 데이터 있어?'))
    assert month['dataStatus']['datasets'][0]['status']=='unsupported_scope'
    reader.assert_not_called()


def test_document_inventory_counts_only_current_user_documents():
    ctx=context('등록된 문서가 몇 개 있어?');ctx.db.allowed={'doc-a'}
    answer=router.answer(ctx)
    assert answer['dataStatus']['datasets'][0]['row_count']==1
    assert 'doc-b' not in str(answer)


def test_inventory_followup_keeps_owned_source_but_reads_current_counts(monkeypatch):
    ctx=context('MRV 데이터 있어?');engine=Mock()
    monkeypatch.setattr(dataset_status,'create_engine_for',lambda _:engine)
    monkeypatch.setattr(dataset_status.config,'database_url',lambda:'postgresql://fixture')
    reader=Mock(side_effect=[{'status':'available','row_count':1},{'status':'available','row_count':2}])
    monkeypatch.setattr(dataset_status,'read_status',reader)
    first=router.answer(ctx)
    ctx.body.update(question='그럼 몇 건이야?',context={'previousQueryId':first['id']})
    second=router.answer(ctx)
    assert second['dataStatus']['datasets'][0]['dataset']=='mrv'
    assert second['dataStatus']['datasets'][0]['row_count']==2
    assert second['routing']['previous_query_id']==first['id'] and reader.call_count==2
    ctx.body['conversationId']='different-conversation'
    assert router.answer(ctx)['routing']['reason']=='OWNED_INVENTORY_CONTEXT_REQUIRED'
    assert reader.call_count==2
    ctx.body.pop('conversationId')
    ctx.db.owners[first['id']]='other-account'
    rejected=router.answer(ctx)
    assert rejected['routing']['reason']=='OWNED_INVENTORY_CONTEXT_REQUIRED' and reader.call_count==2


@pytest.mark.parametrize('question,route',[
    ('뱃전에서 사용한 벙커 양을 뽑고 싶어','operations_summary'),
    ('벙커 소모 추세를 보고 싶네','operations_summary'),
    ('연간 배출 효율을 따져 줄래','mrv_reference'),
    ('실적과 연간 효율을 한꺼번에 보고 싶네','combined'),
    ('아까 고른 책으로만 대답해','selected_document'),
    ('이 선체를 받아 줄 부두를 찾고 싶어','navigation'),
    ('운항할 때 지켜야 할 의무를 풀어 줘','documents'),
])
def test_unmatched_meanings_can_choose_existing_handlers(question,route,monkeypatch):
    ctx=context(question,mode='llm')
    monkeypatch.setattr(router.config,'llm_settings',lambda:SimpleNamespace())
    planner=Mock(return_value=router.Choice(route=route,dataset=None,certainty='clear'))
    monkeypatch.setattr(router,'model_route',planner)
    answer=router.answer(ctx)
    planner.assert_called_once_with(question)
    if route=='documents':assert answer['task']=='documents'
    elif route=='navigation':assert answer['navigation']['status']=='needs_ship'
    else:
        assert answer['workflow']['scope']['action']==route
        assert answer['status']=='needs_input' and not answer['workflow']['results']
        assert answer['workflow']['routing']['method']=='semantic_model'


@pytest.mark.parametrize('choice',[
    router.Choice(route='clarify',dataset=None,certainty='ambiguous'),
    router.Choice(route='unsupported',dataset=None,certainty='clear'),
    ValueError('private model endpoint'), httpx.ReadTimeout('private endpoint'),
])
def test_unclear_unsupported_or_failed_routing_never_returns_unrelated_law(choice,monkeypatch):
    ctx=context('현재 계류지의 상황을 파악하고 싶어',mode='llm')
    monkeypatch.setattr(router.config,'llm_settings',lambda:SimpleNamespace())
    monkeypatch.setattr(router,'model_route',Mock(side_effect=choice) if isinstance(choice,Exception) else Mock(return_value=choice))
    answer=router.answer(ctx)
    assert answer['status']=='needs_input' and answer['routing']['route']=='clarify'
    assert not answer['evidence'] and not ctx.db.document_questions and not ctx.db.calls
    assert 'private' not in str(answer)


def test_explicit_document_mode_keeps_original_contract():
    ctx=context('MRV 관련 데이터 있어?',task='documents')
    assert router.answer(ctx)['task']=='documents' and ctx.db.document_questions


@pytest.mark.parametrize('payload',[
    {'route':'operations_summary','dataset':None,'certainty':'clear','sql':'DROP TABLE ships'},
    {'route':'delete','dataset':None,'certainty':'clear'},
    {'route':'mrv_reference','dataset':'mrv','certainty':'clear'},
    {'route':'data_status','dataset':None,'certainty':'clear'},
])
def test_semantic_transport_rejects_free_commands_or_scope_invention(payload,monkeypatch):
    settings=SimpleNamespace(model='fixture',base_url='https://fixture.invalid',api_key='',
                             completions_path='/v1/chat/completions',response_format='json_schema')
    monkeypatch.setattr(router.config,'llm_settings',lambda:settings)
    def respond(request):
        body=json.loads(request.content)
        assert body['max_tokens']==32 and body['response_format']['type']=='json_schema'
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop',
            'message':{'role':'assistant','content':json.dumps(payload)}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ValueError):router.model_route('선내 질문',client=client)
