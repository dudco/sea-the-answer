from datetime import date
from decimal import Decimal as D
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from service import role4_calculations as calc
from service.tests.api_support import app, login
from service.tests.test_role4 import pg_engine

SCOPE={'dataset':'synthetic_noon','vessel_id':'SYN:SIM-BULK-01','start':'2025-01-01','end':'2025-01-02'}
MAPS=[{'fuel_label':'VLSFO','category':'HFO','evidence':'Development test assumption, not certified fuel mapping'},
      {'fuel_label':'MGO','category':'DIESEL_GAS_OIL','evidence':'Development test diesel gas oil mapping assumption'}]


def row(day=1,fuel='10',label='VLSFO',distance='50',dwt='1000',ship='Bulk carrier'):
    return {'record_id':str(day),'report_date':date(2025,1,day),'fuel_t':D(fuel),'fuel_type':label,
            'distance_nm':D(distance),'dwt_t':D(dwt),'ship_type':ship,'source_id':'source-test'}


def body(**changes):
    return calc.CalculationRequest(**{'scope':SCOPE,'fuel_mappings':MAPS,**changes})


def test_independent_hand_calculated_reference():
    result=calc.compute([row(),row(2,'5','MGO')],body())
    # 10*3.114 + 5*3.206 = 47.170; 47.170e6/(1000*100)=471.7
    assert result['calculated_co2_t']=='47.170000'
    assert result['period_dwt_intensity']=='471.700000'
    assert result['fuel_t']=='15.000000'
    assert result['official_cii'] is None and result['official_cii_rating'] is None
    assert result['input_snapshot'][0]['fuel_t']=='10'
    assert result==calc.compute([row(),row(2,'5','MGO')],body())


def test_no_rounding_before_sum():
    result=calc.compute([row(1,'0.000001'),row(2,'0.000001')],body())
    assert result['calculated_co2_t']=='0.000006'
    assert result['fuel_breakdown'][0]['co2_t']=='0.000006228'


def test_unmapped_fuel_never_reports_partial_total():
    result=calc.compute([row(),row(2,'5','MGO')],body(fuel_mappings=[MAPS[1]]))
    assert result['status']=='blocked' and result['calculated_co2_t'] is None
    assert result['blockers']==['UNMAPPED_FUEL:VLSFO']


@pytest.mark.parametrize('rows,reason',[
    ([row(distance='0')],'ZERO_TOTAL_DISTANCE'),
    ([row(ship='Ro-ro ship')],'CAPACITY_BASIS_REQUIRES_REVIEW_GT_OR_OTHER'),
    ([row(),row(2,dwt='2000')],'MISSING_OR_INCONSISTENT_DWT')])
def test_intensity_blocked_but_co2_preserved(rows,reason):
    result=calc.compute(rows,body())
    assert result['calculated_co2_t'] is not None and result['period_dwt_intensity'] is None
    assert reason in result['intensity_blockers']


def test_zero_fuel_and_incomplete_dates():
    result=calc.compute([row(fuel='0')],body())
    assert result['calculated_co2_t']=='0.000000' and result['period_dwt_intensity']=='0.000000'
    assert 'INCOMPLETE_REQUESTED_DATES' in result['warnings']


def test_duplicate_dates_and_empty():
    result=calc.compute([row(),row()],body())
    assert 'DUPLICATE_REPORT_DATES' in result['blockers'] and result['calculated_co2_t'] is None
    result=calc.compute([],body())
    assert result['fuel_t'] is None and result['blockers']==['NO_ELIGIBLE_RECORDS']


def test_annual_reported_value_separate_from_calculation():
    request=body(scope={'dataset':'real_annual','vessel_id':'REAL:IMO:6602898','year':2020},fuel_mappings=[])
    result=calc.compute([{'fuel_t':D('10'),'co2_t':D('32'),'distance_nm_estimate':D('100')}],request)
    assert result['source_reported_co2_t']=='32.000000'
    assert result['calculated_co2_t'] is None and result['distance_nm'] is None
    assert 'MISSING_FUEL_BREAKDOWN' in result['blockers']
    ambiguous=calc.compute([{'fuel_t':D('10'),'co2_t':D('32')}]*2,request)
    assert ambiguous['source_reported_co2_t'] is None


@pytest.mark.parametrize('change',[
    {'fuel_mappings':MAPS+[MAPS[0]]},
    {'fuel_mappings':[{**MAPS[0],'category':'VLSFO'}]},
    {'fuel_mappings':[{**MAPS[0],'evidence':'        '}]},
    {'fuel_mappings':[{**MAPS[0],'factor':'3.0'}]},
    {'factor_version':'latest'},
    {'scope':{**SCOPE,'vessel_id':'REAL:IMO:1234567'}},
    {'scope':{**SCOPE,'end':'2024-01-01'}},
    {'scope':{**SCOPE,'limit':20}},
])
def test_invalid_inputs(change):
    with pytest.raises(ValidationError): body(**change)




def test_postgres_full_year_not_first_page(pg_engine):
    from sqlalchemy import text
    request=body(scope={**SCOPE,'end':'2025-12-31'})
    result=calc.calculate(pg_engine,request)
    assert result['record_count']==365 and result['status']=='calculated'
    with pg_engine.connect() as conn:
        conn.execute(text('SET TRANSACTION READ ONLY'))
        raw=conn.execute(text("SELECT sum(fuel_t)*3.114, sum(distance_nm), count(*) FILTER(WHERE distance_nm=0) FROM role4.development_noon_query WHERE vessel_id='SYN:SIM-BULK-01' AND report_date BETWEEN '2025-01-01' AND '2025-12-31'")).one()
    assert D(result['calculated_co2_t'])==raw[0]
    assert D(result['distance_nm'])==raw[1]
    assert sum(D(r['distance_nm'])==0 for r in result['input_snapshot'])==raw[2]
    blocked=calc.calculate(pg_engine,body(scope={'dataset':'real_annual','vessel_id':'REAL:IMO:6602898','year':2020},fuel_mappings=[]))
    assert blocked['status']=='blocked' and blocked['source_reported_co2_t'] is not None


def test_postgres_api_with_isolated_auth(app,pg_engine,monkeypatch):
    original=calc.calculate
    monkeypatch.setattr(calc,'calculate',lambda engine,request: original(pg_engine,request))
    response=login(app).post('/api/role4/calculate',json=body().model_dump(mode='json'))
    assert response.status_code==200 and response.json()['record_count']==2
