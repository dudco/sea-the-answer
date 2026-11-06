"""Additional sources do not manufacture metre units, static clocks or admission approvals."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from scripts.prepare_navigation_sources import norway_observations, aalborg_berths, captured
from scripts import navigation_bundle
from scripts.prepare_navigation_references import berth_references
from tools.navigation_references import NavigationCatalog, NavigationScreenRequest, screen_references
from tools.navigation_readiness import Scenario
from test_navigation_expansion import expanded_data
from test_navigation_references import IMO, VESSEL, NOW, PORT
from test_navigation_query import setup
from api import navigation_query
from api.routes import navigation
from api.errors import ApiError
from test_navigation_app import adapter


def norway(imo=int(IMO), mmsi=123456789, **extra):
    return {'type':'Feature','properties':{'imo':imo,'mmsi':mmsi,'ship_name':'Reference ship',
        'length':100,'breadth':20,'draught':6.5,'date_time_utc':'2026-11-05T08:55:31',**extra}}


def geojson(*rows):
    return {'type':'FeatureCollection','features':list(rows)}


def aalborg_page():
    rows = []
    for label in ('4121','4122','4123','4124','4125','0700'):
        conditional = label not in ('4122','4124')
        rows.append(f"Quay {label} "+('130 m 8,9 m 9,0 m*' if label=='4124' else
            '250 m '+('(depends on vessel position of manifold) ' if conditional else '')+'9,4 m 9,5 m*'))
    return '\n'.join(rows)+'''\n✱ Max. draft depends on pilot restrictions and latest soundings.
    Due to change in waterdepth always contact Port control and operation for latest update!
    QUAY MAX. LOA MAX. DRAFT MIN. WATER DEPTH
    3.5. Tide +/- 30 cm
    3.8. Under keel clearance policy
    Minimum 0.1 m clearance should be maintained between vessel keel and seabed under arrival and departure.
    Follow the ship/company under keel clearance policy.
    3.4. Berth limitations'''


def extended():
    data = expanded_data(); data['version']='NAVIGATION-REFERENCES-1.2'
    for key in ('ais_no','schema_no','aalborg_berths'):
        data['sources'].append({**deepcopy(data['sources'][0]),'id':key})
    data['observations'].extend(norway_observations(geojson(norway()), {IMO}))
    data['ports'].append({'port_id':'WPI:30400','unlocode':'DKAAL','name':'Aalborg',
        'source_id':'aalborg_berths','reference_scope':'Oil terminals only','berths':aalborg_berths(aalborg_page(),'WPI:30400')})
    return data


def test_norway_exact_join_keeps_raw_units_and_position_clock_separate():
    rows = norway_observations(geojson(norway(),norway(imo=7422880),norway(imo=9074729)), {IMO})
    assert len(rows)==1 and rows[0]['vessel_id']==VESSEL
    row=rows[0]
    assert row['raw_reported_fields']=={'length':'100','breadth':'20','draught':'6.5'}
    assert row['position_reported_at']=='2026-11-05T08:55:31+00:00'
    assert row['metadata_received_at'] is None
    assert all(row[key] is None for key in ('reported_length_m','reported_beam_m','reported_draught_m'))
    assert row['source_ref']=={'source_id':'ais_no','locator':'/features/0/properties'}


def test_norway_conflicts_are_checked_even_outside_the_mrv_subset():
    rows=norway_observations(geojson(norway(),norway(imo=9074729)),{IMO})
    assert 'AIS_IDENTITY_AMBIGUOUS' in rows[0]['issues']


@pytest.mark.parametrize('rows',[None,{},['bad'],[{'type':'Feature','properties':[]}], [{'properties':{}}]])
def test_changed_geojson_contract_never_silently_becomes_an_empty_source(rows):
    with pytest.raises(ValueError):norway_observations({'type':'FeatureCollection','features':rows},{IMO})


@pytest.mark.parametrize('change',[{'metadata_received_at':NOW.isoformat()},{'reported_length_m':'100'},
    {'reported_draught_m':'6.5'},{'issues':[]}])
def test_position_or_undocumented_units_cannot_be_promoted_in_catalog(change):
    data=extended();data['observations'][-1].update(change)
    with pytest.raises(ValidationError):NavigationCatalog.model_validate(data)


def test_multiple_sources_for_the_same_imo_are_preserved_and_not_arbitrarily_selected():
    result=screen_references(NavigationCatalog.model_validate(extended()),NavigationScreenRequest(vessel_id=VESSEL,port_id=PORT),now=NOW)
    assert result['observation'] is None and result['observation_candidate_count']==2
    assert {r['source_ref']['source_id'] for r in result['observation_candidates']}=={'ais','ais_no'}
    assert 'AIS_IDENTITY_AMBIGUOUS' in result['ship_issues']
    assert all(c['status']=='unavailable' for b in result['berths'] for c in b['checks'])
    assert result['admission']=='not_assessed'


def test_norway_only_source_reports_missing_unit_static_clock_without_finnish_attribution():
    data=extended();data['observations']=data['observations'][1:]
    result=screen_references(NavigationCatalog.model_validate(data),NavigationScreenRequest(vessel_id=VESSEL,port_id=PORT),now=NOW)
    assert {'AIS_STATIC_TIME_UNVERIFIED','AIS_UNITS_UNVERIFIED'} <= set(result['ship_issues'])
    assert {s['id'] for s in result['sources']}=={'ais_no','schema_no','berths'}
    assert result['observation']['raw_reported_fields']['draught']=='6.5'


def test_aalborg_footnotes_do_not_become_exact_draft_or_manifold_independent_limits():
    berths=aalborg_berths(aalborg_page(),'WPI:30400')
    assert len(berths)==6 and all(b['max_draught_m'] is None for b in berths)
    assert {b['label']:b['max_loa_m'] for b in berths}=={'4121':None,'4122':'250','4123':None,'4124':'130','4125':None,'0700':None}
    assert all('latest soundings' in b['conditions'][0] and 'clearance policy' in b['conditions'][0] for b in berths)


@pytest.mark.parametrize('old,new',[('Quay 0700','Quay 9999'),('9,4 m','9,3 m'),('pilot restrictions','no restrictions'),
    ('Minimum 0.1 m','Minimum 0.2 m'),('MAX. DRAFT','DRAUGHT UNKNOWN')])
def test_aalborg_changes_need_review_not_guessed_values(old,new):
    with pytest.raises(ValueError):aalborg_berths(aalborg_page().replace(old,new),'WPI:30400')


def test_aalborg_catalog_rejects_promoting_footnoted_draft_even_if_variant_is_edited():
    data=extended();berth=data['ports'][-1]['berths'][1]
    berth['max_draught_m']='9.4';berth['variants'][0]['max_draught_m']='9.4'
    with pytest.raises(ValidationError):NavigationCatalog.model_validate(data)


def gothenburg(rule, label='551', scenario=None):
    data=expanded_data()
    data['ports'][0]['berths']=berth_references(f'<h5>Berth {label}</h5><p>Max. LOA: 150 metres</p><p>{rule}</p>',PORT)
    return screen_references(NavigationCatalog.model_validate(data),NavigationScreenRequest(vessel_id=VESSEL,port_id=PORT,scenario=scenario),now=NOW)


TUG='If during arrival the wind speed is more than 12 m/s, the use of one (1) tug is compulsory.'


@pytest.mark.parametrize('scenario,status,missing',[
    (None,'needs_information',['wind_at_arrival']),
    ({'wind_m_s':'13'},'needs_information',['available_tugs']),
    ({'wind_m_s':'13','available_tugs':0},'action_required',[]),
    ({'wind_m_s':'13','available_tugs':1},'within_scenario',[]),
    ({'wind_m_s':'12','available_tugs':0},'not_triggered_in_scenario',[]),
    ({'wind_m_s':'0','available_tugs':0},'not_triggered_in_scenario',[]),
])
def test_tug_trigger_differentiates_unknown_zero_and_threshold_equality(scenario,status,missing):
    result=gothenburg(TUG,scenario=scenario)
    check=result['berths'][0]['operational_checks'][0]
    assert check['status']==status and check['missing_inputs']==missing
    assert check['source_text'] in TUG and check['source_ref']['source_id']=='berths'
    assert result['readiness']['status']=='requires_review' and result['admission']=='not_assessed'
    assert result['readiness']['verified_current_ship_state'] is False


@pytest.mark.parametrize('ukc,status',[('0','action_required'),('0.99','action_required'),('1.0','within_scenario'),('1.01','within_scenario')])
def test_published_ukc_uses_decimal_and_never_grants_admission(ukc,status):
    result=gothenburg('Special restrictions: UKC (under keel clearance) 1.0 metres.',label='644',scenario={'ukc_m':ukc})
    check=result['berths'][0]['operational_checks'][0]
    assert check['status']==status and check['scenario_only'] is True and result['safe_draft_m'] is None


def test_aalborg_checks_still_require_latest_depth_and_pilot_confirmation_after_scenario_pass():
    data=extended();data['observations']=data['observations'][:1]
    result=screen_references(NavigationCatalog.model_validate(data),NavigationScreenRequest(vessel_id=VESSEL,port_id='WPI:30400',scenario={'ukc_m':'0.1'}),now=NOW)
    checks=result['berths'][0]['operational_checks']
    assert [c['status'] for c in checks]==['within_scenario','needs_information']
    assert result['berths'][0]['conditions_evaluated'] is False
    assert len(result['readiness']['items'])==7


@pytest.mark.parametrize('scenario',[{'wind_m_s':-1},{'wind_m_s':'NaN'},{'wind_m_s':101},{'wind_m_s':True},
    {'available_tugs':True},{'available_tugs':1.5},{'available_tugs':'1'},{'ukc_m':-1},{'ukc_m':21},{'verified':True}])
def test_scenario_rejects_invalid_bounds_and_claimed_verification(scenario):
    with pytest.raises(ValidationError):Scenario.model_validate(scenario)


def test_v12_offline_bundle_keeps_source_ages_and_original_bytes(tmp_path, monkeypatch):
    path=tmp_path/'catalog.json';path.write_text(NavigationCatalog.model_validate(extended()).model_dump_json(),encoding='utf-8')
    network=Mock(side_effect=AssertionError('network forbidden'))
    monkeypatch.setattr('urllib.request.urlopen',network)
    result=navigation_bundle.export_bundle(path,tmp_path/'bundle')
    assert result['version']=='NAVIGATION-REFERENCES-1.2'
    assert (tmp_path/'bundle/catalog.json').read_bytes()==path.read_bytes()
    network.assert_not_called()


def test_aalborg_natural_question_resolves_the_explicit_new_port(setup):
    ctx,loader,calculator=setup
    loader.return_value=(NavigationCatalog.model_validate(extended()),'b'*64)
    ctx.body['question']='우리 배가 올보르에 입항 가능해?'
    reply=navigation_query.try_answer(ctx)
    assert calculator.call_args.kwargs['port_ids']==['WPI:30400']
    assert reply['navigation']['admission']=='not_assessed'


def test_adapter_passes_only_a_validated_scenario_without_updating_source_data(adapter):
    ctx,engine,calculate=adapter
    ctx.body['scenario']={'wind_m_s':'13','available_tugs':0,'ukc_m':'0.1'}
    reply=navigation.screen(ctx)
    supplied=calculate.call_args.args[1]
    assert supplied.scenario.wind_m_s==Decimal('13') and supplied.scenario.available_tugs==0
    assert reply['result']['admission']=='not_assessed'
    ctx.db.run.assert_not_called()


@pytest.mark.parametrize('scenario',[{'verified':True},{'available_tugs':True},{'ukc_m':-1},{'wind_m_s':'Infinity'}])
def test_adapter_rejects_bad_scenarios_before_comparing(adapter,scenario):
    ctx,engine,calculate=adapter;ctx.body['scenario']=scenario
    with pytest.raises(ApiError) as exc:navigation.screen(ctx)
    assert exc.value.status==400
    calculate.assert_not_called()


def test_old_port_rule_cannot_become_within_scenario():
    from datetime import timedelta
    data=expanded_data()
    data['sources'][2]['retrieved_at']=(NOW-timedelta(days=31)).isoformat()
    data['ports'][0]['berths']=berth_references('<h5>Berth 644</h5><p>Special restrictions: UKC (under keel clearance) 1.0 metres.</p>',PORT)
    result=screen_references(NavigationCatalog.model_validate(data),NavigationScreenRequest(vessel_id=VESSEL,port_id=PORT,scenario={'ukc_m':'2'}),now=NOW)
    check=result['berths'][0]['operational_checks'][0]
    assert check['status']=='needs_information' and check['missing_inputs']==['current_port_source']


@pytest.mark.parametrize('question',['우리 배가 풍속 13일 때 입항 가능해?', '우리 배가 예선 0척으로 입항 가능해?',
    'Can our ship enter with wind 13 m/s?'])
def test_operational_assumptions_in_text_are_not_silently_ignored(setup,question):
    ctx,loader,calculator=setup;ctx.body['question']=question
    reply=navigation_query.try_answer(ctx)
    assert reply['navigation']['status']=='unsupported_scope'
    calculator.assert_not_called()


def test_unrelated_finnish_capture_age_does_not_contaminate_norway_only_record():
    from datetime import timedelta
    data=extended();data['observations']=data['observations'][1:]
    data['sources'][0]['retrieved_at']=(NOW-timedelta(days=2)).isoformat()
    result=screen_references(NavigationCatalog.model_validate(data),NavigationScreenRequest(vessel_id=VESSEL,port_id=PORT),now=NOW)
    assert 'AIS_CAPTURE_STALE' not in result['ship_issues']
    assert 'AIS_STATIC_TIME_UNVERIFIED' in result['ship_issues']


def test_source_capture_rejects_changed_hash_and_manifest_path(tmp_path):
    from scripts.prepare_navigation_sources import URLS
    from scripts.prepare_navigation_references import digest
    url,name=URLS['ais_no'];content=b'{}';(tmp_path/name).write_bytes(content)
    manifest={'ais_no':{'status':'captured','url':url,'filename':name,'sha256':digest(content)}}
    assert captured(tmp_path,manifest,'ais_no')==content
    manifest['ais_no']['filename']='../private.env'
    with pytest.raises(ValueError):captured(tmp_path,manifest,'ais_no')
    manifest['ais_no'].update(filename=name,sha256='0'*64)
    with pytest.raises(ValueError):captured(tmp_path,manifest,'ais_no')
