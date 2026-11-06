"""Natural slots, safe model plans, clarification and current owner-bound execution."""
from copy import deepcopy
from datetime import date
import json
from types import SimpleNamespace

import httpx
import pytest

from api import config,question_intent as intent,question_workflows as flow
from api.errors import ApiError

SHIPS=[{'id':'a','name':'해답호','version':1,'imo':'7422881','dwt':1000},
       {'id':'b','name':'별빛호','version':2,'imo':'9074729','dwt':2000}]


class DB:
    def __init__(self):
        self.fleet=deepcopy(SHIPS);self.answers={};self.owners={};self.calls=[];self.allowed={'doc-a','doc-b'}
    def ships(self):return deepcopy(self.fleet)
    def one(self,sql,args=()):
        if 'query_owner' in sql:
            return {'response':deepcopy(self.answers[args[0]])} if self.owners.get(args[0])==args[1] else None
        return None
    def run(self,sql,args=()):
        if sql.startswith('INSERT INTO queries '):self.answers[args[0]]=deepcopy(args[2].obj)
        if sql.startswith('INSERT INTO query_owner '):self.owners[args[0]]=args[1]
    def audit(self,*args):pass
    def can_read_document(self,user,identifier):return identifier in self.allowed
    def documents(self,user):return [{'id':i,'title':i} for i in sorted(self.allowed)]
    def operation_summary(self,scope):
        self.calls.append(deepcopy(scope));ship=next(s for s in self.fleet if s['id']==scope['ship'])
        fuel=10 if '-01-' in scope['from'] else 15
        return {**scope,'ship':ship,'rows':[{'id':'op','version':1,'date':scope['from'],'fuel':fuel,'factor':3.114,'distance':100,'speed':12}],
            'sample':False,'count':1}


def ask(db,question,context=None,reply=None,mode='extractive',owner='user-a'):
    body={'question':question,'context':context or {},'mode':mode}
    if reply is not None:body['workflowInput']=reply
    return flow.try_answer(SimpleNamespace(db=db,user={'id':owner},body=body))


def test_months_years_and_relative_dates_are_explicit_and_bounded():
    today=date(2026,11,6)
    row=intent.extract_rules('2025년 1월과 2월 연료 사용량 비교해줘',today)
    assert row.action=='operations_summary' and [(p.start,p.end) for p in row.periods]==[('2025-01-01','2025-01-31'),('2025-02-01','2025-02-28')]
    assert intent.date_slots('지난달과 이번달',today)[1][1].end=='2026-11-06'
    assert intent.date_slots('작년',today)[0]==[2025]
    assert intent.date_slots('최근 7일',today)[1][0].start=='2026-10-31'
    with pytest.raises(ValueError):intent.date_slots('1월',today)
    with pytest.raises(ValueError):intent.date_slots('2025-02-30',today)
    with pytest.raises(ValueError):intent.date_slots('최근 3개월',today)


def test_original_tool_is_called_with_natural_scope_over_ui_and_comparisons_are_server_arithmetic():
    db=DB();answer=ask(db,'해답호의 2025년 1월과 2월 연료 사용량을 비교해줘',{'ship':'b','from':'2020-01-01','to':'2020-01-02'})
    assert answer['status']=='completed' and len(db.calls)==2
    assert {c['ship'] for c in db.calls}=={'a'}
    assert [c['from'] for c in db.calls]==['2025-01-01','2025-02-01']
    delta=next(c for c in answer['workflow']['comparisons'] if c['metric']=='fuel_t')
    assert delta['difference']=='5.000000' and delta['percent_change']=='50.000000'


def test_missing_conditions_are_saved_then_structured_reply_completes_without_global_latest():
    db=DB();first=ask(db,'운항 실적을 요약해줘')
    assert set(first['workflow']['missing'])=={'ships','periods'} and not db.calls
    answer=ask(db,'조건을 보완해서 다시 실행해줘',{'previousQueryId':first['id']},
        {'ships':['a'],'periods':[{'start':'2025-01-01','end':'2025-01-31'}]})
    assert answer['status']=='completed' and answer['workflow']['previous_query_id']==first['id']
    assert db.calls[0]['ship']=='a'


def test_short_month_followup_reuses_year_but_independent_question_resets_previous_scope():
    db=DB();first=ask(db,'해답호의 2025년 1월 연료 사용량을 알려줘')
    answer=ask(db,'그럼 2월은?',{'ship':'a','previousQueryId':first['id']})
    assert db.calls[-1]['from']=='2025-02-01'
    other=ask(db,'별빛호의 2024년 3월 연료 사용량을 알려줘',{'ship':'a','previousQueryId':answer['id']})
    assert other['workflow']['scope']['ships'][0]['id']=='b' and db.calls[-1]['from']=='2024-03-01'
    assert other['workflow']['previous_query_id'] is None


@pytest.mark.parametrize('change',['owner','ship_version','selected_ship','bad_id'])
def test_invalid_previous_scope_never_executes_a_followup(change):
    db=DB();first=ask(db,'해답호의 2025년 1월 연료 사용량을 알려줘');db.calls=[]
    context={'ship':'a','previousQueryId':first['id']};owner='user-a'
    if change=='owner':owner='user-b'
    if change=='ship_version':db.fleet[0]['version']+=1
    if change=='selected_ship':context['ship']='b'
    if change=='bad_id':context['previousQueryId']='not-a-uuid'
    answer=ask(db,'그럼 2월은?',context,owner=owner)
    assert answer['status']=='needs_input' and not db.calls and not answer['workflow']['results']


def mock_reference(monkeypatch,db):
    calls=[];engine=SimpleNamespace(dispose=lambda:None)
    monkeypatch.setattr(flow,'create_engine_for',lambda *a:engine)
    monkeypatch.setattr(flow,'resolve_real_ship',lambda d,e,s:SimpleNamespace(vessel_id='REAL:IMO:'+next(r['imo'] for r in db.fleet if r['id']==s)))
    def calculate(engine,body):
        calls.append(body)
        return {'reference_only':True,'reference_dwt_intensity':'1.500000' if body.scope.year==2024 else None,
            'status':'estimated' if body.scope.year==2024 else 'blocked','blockers':[] if body.scope.year==2024 else ['NO_ELIGIBLE_ANNUAL_RECORD'],
            'official_cii':None,'official_cii_rating':None}
    monkeypatch.setattr(flow,'calculate_reference',calculate)
    return calls


def test_multi_year_reference_keeps_blocked_year_and_never_invents_rating(monkeypatch):
    db=DB();calls=mock_reference(monkeypatch,db)
    answer=ask(db,'해답호 2024년과 2025년 MRV 참고 탄소집약도를 비교해줘')
    assert len(calls)==2 and answer['status']=='partial'
    assert [r['year'] for r in answer['workflow']['results']]==[2024,2025]
    assert answer['workflow']['comparisons'][0]['status']=='not_comparable'
    assert all(r['result']['official_cii_rating'] is None for r in answer['workflow']['results'])


def test_reference_consent_and_combined_tools_need_exact_scope(monkeypatch):
    db=DB();calls=mock_reference(monkeypatch,db)
    first=ask(db,'해답호 2024년 공식 CII 등급 계산해줘')
    assert 'reference_ack' in first['workflow']['missing'] and not calls
    second=ask(db,'참고값으로 계산해줘',{'ship':'a','previousQueryId':first['id']})
    assert len(calls)==1 and second['workflow']['results'][0]['result']['reference_only']
    combined=ask(db,'해답호 2024년 1월 운항 실적과 MRV 참고 탄소집약도를 분석해줘')
    assert {r['kind'] for r in combined['workflow']['results']}=={'mrv_reference','operations_summary'}


def test_call_limits_and_unknown_ships_do_not_silently_use_a_broader_scope(monkeypatch):
    db=DB();calls=mock_reference(monkeypatch,db)
    answer=ask(db,'해답호와 별빛호의 2023년 2024년 2025년 MRV 참고 탄소집약도를 비교해줘')
    assert answer['status']=='needs_input' and not calls
    answer=ask(db,'미등록호의 2025년 1월 연료 사용량 알려줘',{'ship':'a'})
    assert answer['status']=='needs_input' and not db.calls
    answer=ask(db,'모든 선박의 2025년 1월 연료 사용량 알려줘',{'ship':'a'})
    assert answer['status']=='needs_input' and not db.calls


def test_selected_document_asks_before_search_and_rechecks_acl(monkeypatch):
    db=DB();seen=[]
    monkeypatch.setattr(flow.skills,'selected_evidence',lambda d,u,b:seen.append(b.document_ids) or [{'id':'c','document_id':'doc-a','text':'exact evidence'}])
    monkeypatch.setattr(flow.skills,'evidence_statements',lambda *a:([{'text':'supported','chunkId':'c','quote':'exact evidence'}],'extractive'))
    first=ask(db,'선택한 문서만 사용해서 요약해줘',{'ship':'a'})
    assert first['workflow']['missing']==['document_ids'] and not seen
    second=ask(db,'조건 보완',{'ship':'a','previousQueryId':first['id']},{'document_ids':['doc-a']})
    assert seen==[['doc-a']] and second['evidence'][0]['document_id']=='doc-a'
    db.allowed.clear()
    with pytest.raises(ApiError):ask(db,'조건 보완',{'previousQueryId':first['id']},{'document_ids':['doc-a']})


def test_role_or_ship_changes_while_tools_run_rolls_back_save(monkeypatch):
    db=DB();original=db.operation_summary
    def changed(scope):
        result=original(scope);db.fleet[0]['version']+=1;return result
    db.operation_summary=changed
    with pytest.raises(ApiError):ask(db,'해답호 2025년 1월 연료 사용량 알려줘')
    assert not db.answers


def test_document_and_presentation_routes_do_not_invoke_new_planner():
    db=DB()
    for q in ['선박 안전 규정을 알려줘','헬싱키 입항 절차를 문서만 사용해서 알려줘','연료 추이를 차트로 보여줘','연료 황 함유량 기준을 알려줘']:
        assert ask(db,q,mode='llm') is None


def test_valid_model_transport_is_bounded_and_rejects_invented_slots(monkeypatch):
    monkeypatch.setattr(config,'llm_settings',lambda:config.LLMSettings('http://localhost/v1','qwen2.5:3b','', 'json_schema'))
    plan={'action':'operations_summary'}
    def response(request):
        body=json.loads(request.content);assert body['max_tokens']==64 and body['response_format']['type']=='json_schema'
        assert len(body['messages'])==2 and 'SQL' in body['messages'][0]['content']
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(plan)}}]})
    client=httpx.Client(transport=httpx.MockTransport(response))
    assert intent.plan_with_model('2025년 연료 사용량 보여줘',today=date(2026,11,6),client=client).years==[2025]
    plan['years']=[2024]
    with pytest.raises(ValueError):intent.plan_with_model('2025년 연료 사용량 보여줘',today=date(2026,11,6),client=client)
    plan.pop('years');plan['ship_mentions']=['없는 선박']
    with pytest.raises(ValueError):intent.plan_with_model('2025년 연료 사용량 보여줘',today=date(2026,11,6),client=client)


def test_model_failure_falls_back_to_validated_rules_without_invented_scope(monkeypatch):
    db=DB();monkeypatch.setattr(intent,'plan_with_model',lambda *a,**k:(_ for _ in ()).throw(ValueError('invalid model')))
    answer=ask(db,'해답호의 2025년 1월 연료 사용량을 알려줘',mode='llm')
    assert answer['status']=='completed' and answer['workflow']['routing']['fallback']
    assert db.calls[0]['from']=='2025-01-01'


def test_korean_days_month_ranges_and_weeks_never_expand_to_the_wrong_scope():
    today=date(2026,11,6)
    for q,start,end in [
        ('2025년 1월 15일','2025-01-15','2025-01-15'),
        ('2025년 1월 15일부터 20일까지','2025-01-15','2025-01-20'),
        ('2025년 1월부터 3월까지','2025-01-01','2025-03-31'),
        ('지난주','2026-10-26','2026-11-01'),('이번 주','2026-11-02','2026-11-06')]:
        periods=intent.date_slots(q,today)[1]
        assert [(p.start,p.end) for p in periods]==[(start,end)]
    assert len(intent.date_slots('2025년 1월과 3월 비교',today)[1])==2


def test_unrelated_followup_never_repeats_previous_tools_and_explicit_task_can_change(monkeypatch):
    db=DB();calls=mock_reference(monkeypatch,db)
    first=ask(db,'해답호 2024년 1월 연료 사용량 알려줘');db.calls=[]
    assert ask(db,'그럼 점심은 뭘 먹지?',{'ship':'a','previousQueryId':first['id']}) is None
    assert not db.calls
    answer=ask(db,'그럼 MRV 참고 탄소집약도를 계산해줘',{'ship':'a','previousQueryId':first['id']})
    assert len(calls)==1 and not db.calls and answer['workflow']['scope']['action']=='mrv_reference'


def test_invalid_oversized_scope_is_not_saved_for_continuation_and_writes_do_not_run():
    db=DB()
    answer=ask(db,'해답호의 2023년 2024년 2025년 연료 사용량 비교해줘')
    assert answer['status']=='needs_input' and not db.calls
    flow.Scope.model_validate(answer['workflow']['scope'])
    answer=ask(db,'해답호 2025년 1월 연료 사용량 조회하고 삭제해줘')
    assert answer['status']=='needs_input' and not db.calls


def test_selected_document_clarification_uses_original_question_not_form_placeholder(monkeypatch):
    db=DB();seen=[]
    monkeypatch.setattr(flow.skills,'selected_evidence',lambda d,u,b:seen.append(b.question) or [])
    monkeypatch.setattr(flow.skills,'evidence_statements',lambda *a:([],'extractive'))
    q='선택한 문서에서 소화기 점검 항목을 알려줘'
    first=ask(db,q)
    answer=ask(db,'조건을 보완해서 다시 실행해줘',{'previousQueryId':first['id']},{'document_ids':['doc-a']})
    assert seen==[q] and answer['status']=='insufficient_evidence'


def test_four_calls_are_allowed_but_changed_mapping_or_duplicate_input_cannot_execute(monkeypatch):
    db=DB();calls=mock_reference(monkeypatch,db)
    first=ask(db,'해답호와 별빛호의 2024년 2025년 MRV 참고 탄소집약도를 비교해줘')
    assert len(calls)==4
    monkeypatch.setattr(flow,'resolve_real_ship',lambda *a:SimpleNamespace(vessel_id='REAL:CHANGED'))
    with pytest.raises(ApiError) as exc:ask(db,'그럼 2023년은?',{'ship':'a','previousQueryId':first['id']})
    assert exc.value.status==409 and len(calls)==4
    pending=ask(db,'운항 실적을 요약해줘')
    with pytest.raises(ApiError):ask(db,'조건 보완',{'previousQueryId':pending['id']},{'ships':['a','a']})


def test_no_data_sample_mismatch_and_zero_base_never_produce_a_false_rate():
    def row(fuel,count=1,sample=False):
        return {'kind':'operations_summary','label':'test','status':'completed','result':{'count':count,'sample':sample,'fuel_t':fuel}}
    assert flow.comparisons([row('0'),row('10')])[0]['percent_change'] is None
    assert flow.comparisons([row('1'),row('2',sample=True)])[0]['status']=='not_comparable'
    assert flow.comparisons([row('1'),row('0',count=0)])[0]['difference'] is None


def test_ship_names_do_not_match_prefixes_and_duplicate_names_require_disambiguation():
    db=DB();db.fleet[1]['name']='해답호2'
    answer=ask(db,'해답호2의 2025년 1월 연료 사용량 알려줘')
    assert [s['id'] for s in answer['workflow']['scope']['ships']]==['b']
    db.fleet[1]['name']='해답호';db.calls=[]
    answer=ask(db,'해답호의 2025년 1월 연료 사용량 알려줘')
    assert answer['status']=='needs_input' and not db.calls


def test_year_ranges_and_ambiguous_baselines_never_silently_become_endpoint_comparisons():
    assert intent.date_slots('2020년부터 2022년까지')[0]==[2020,2021,2022]
    for q in ['2020년부터 2025년까지','2025년 1월 전월 대비','2025년 1월 작년보다']:
        with pytest.raises(ValueError):intent.date_slots(q)
    db=DB();first=ask(db,'해답호 2025년 1월 연료 사용량 알려줘');db.calls=[]
    answer=ask(db,'그럼 같은 기간 다른 선박은?',{'ship':'a','previousQueryId':first['id']})
    assert answer['workflow']['missing']==['ships'] and not db.calls
