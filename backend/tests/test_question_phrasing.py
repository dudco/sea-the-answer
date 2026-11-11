"""Question wording audit: status, metric fragments and scoped document follow-ups."""
import pytest
from api import navigation_query as navigation
from api import question_workflows as workflow
from test_navigation_query import setup
from test_question_workflows import DB,ask,mock_reference


@pytest.mark.parametrize('question',[
    'AIS 있어?', 'AIS 데이터 있는지 확인해줘', 'AIS데이터 등록됐어?',
    '수집한 AIS 데이터가 몇 건이야?', 'AIS 자료는 언제 받아온 거야?',
    '실시간 AIS 데이터야?', 'AIS 정보는 최신이야?', 'AIS가 아니라 MRV의 뜻을 알려줘',
    'AIS 자료 확보되어 있나?', 'AIS 자료 출처 알려줘', 'Do we have AIS data?',
    'Is there AIS data?', 'AIS snapshot status', 'AIS 자료 목록 보여줘',
    'AIS 관련 정보를 알려줘', 'AIS 정보 알려줘', 'ais 관련 데이터 보여 주세요',
    'AIS에 대한 자료를 간단히 정리해 줘', '선박자동식별시스템 관련 정보 조회해줘',
    'Tell me about AIS information', 'Please show me AIS data',
    'Give me information about AIS', 'ＡＩＳ 관련 정보를 알려줘',
])
def test_status_wording_uses_current_catalog_and_explanations_stay_documents(setup,question):
    ctx,loader,calculator=setup;ctx.body['question']=question
    answer=navigation.try_answer(ctx)
    if '뜻' in question:
        assert answer is None
    else:
        assert answer is not None and answer['navigation']['kind']=='catalog-status'
        assert answer['navigation']['catalog']['ais_observation_count']>0
    calculator.assert_not_called()


@pytest.mark.parametrize('question',[
    'AIS 관련 규정을 알려줘', 'AIS 정보 보호 절차를 설명해줘',
    'AIS 수신기 오류 정보를 알려줘', 'AIS 자료 등록하는 방법은?',
    'AIS 데이터 구조를 알려줘', 'AIS에 대해 알려줘',
    'AIS 정보와 MRV 정보를 알려줘', 'Show me AIS receiver fault information',
    'Tell me how to use AIS data', 'AIS 관련 정보 삭제해 줘',
])
def test_specific_ais_topics_are_not_replaced_with_snapshot_totals(setup,question):
    ctx,loader,calculator=setup;ctx.body['question']=question
    assert navigation.try_answer(ctx) is None
    loader.assert_not_called();calculator.assert_not_called()


@pytest.mark.parametrize('question',[
    '해답호 2025년 1월 연료 사용량 알려줘', '우리 배 지난달 기름 얼마나 썼어?',
    '2025년 1월 연료 사용량', '2025년 CO2 배출량은?', '올해 항해거리는?',
    '해답호 2025년 1월 운항 실적 좀 보여줘', '지난달 연료 소비량은?',
    '해답호 2024년 MRV 참고 탄소집약도 알려줘',
])
def test_metric_question_fragments_are_not_sent_to_unrelated_document_search(question,monkeypatch):
    db=DB();mock_reference(monkeypatch,db)
    answer=ask(db,question)
    assert answer is not None and answer['task']=='workflow'


@pytest.mark.parametrize('question',[
    'CO2 배출계수를 알려줘','연료 사용량 계산식 알려줘','CII의 뜻과 적용 대상을 설명해줘',
    '연료 황 함유량 기준을 알려줘','AIS 데이터의 정의는?',
    '2025년 1월 입항 절차를 알려줘','해답호 소화기 점검 방법은?',
])
def test_definitions_and_formulas_are_not_misread_as_a_sum(question):
    assert ask(DB(),question) is None


@pytest.mark.parametrize('question',[
    '해답호 지난달 연료 사용량이 늘어난 원인을 분석해줘',
    '해답호 지난달 연료 사용량이 왜 늘었어?',
    '해답호 다음달 예상 연료 사용량을 계산해줘',
    '해답호 내일 연료 사용량 알려줘',
])
def test_causal_or_forecast_requests_are_not_answered_with_an_unrelated_total(question):
    db=DB();answer=ask(db,question,{'ship':'a','from':'2025-01-01','to':'2025-01-31'})
    assert answer is not None and answer['status']=='needs_input'
    assert not db.calls and not answer['workflow']['results']


def test_formula_explanation_never_calls_task_planner_even_in_ai_mode(monkeypatch):
    seen=[]
    monkeypatch.setattr(workflow.intent,'plan_with_model',lambda *a,**k:seen.append(a))
    assert ask(DB(),'연료 사용량 계산식 알려줘',mode='llm') is None
    assert not seen


def test_same_document_pronoun_reuses_authorized_ids_but_searches_the_new_question(monkeypatch):
    db=DB();seen=[]
    monkeypatch.setattr(workflow.skills,'selected_evidence',lambda d,u,b:seen.append((b.question,b.document_ids)) or [])
    monkeypatch.setattr(workflow.skills,'evidence_statements',lambda *a:([],'extractive'))
    first=ask(db,'선택한 문서에서 소화기 점검 항목을 알려줘')
    second=ask(db,'조건 보완',{'previousQueryId':first['id']},{'document_ids':['doc-a']})
    new_question='그 문서에서 연료 전환 절차도 알려줘'
    third=ask(db,new_question,{'previousQueryId':second['id']})
    assert third is not None and seen[-1]==(new_question,['doc-a'])
    db.allowed.remove('doc-a')
    assert ask(db,'같은 문서에서 점검 항목 알려줘',{'previousQueryId':third['id']})['workflow']['missing']==['document_ids']
