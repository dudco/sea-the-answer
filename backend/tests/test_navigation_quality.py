"""Historical dimensions and station readings never manufacture current admission inputs."""
from copy import deepcopy
from datetime import timedelta
import json

import pytest
from pydantic import ValidationError

from scripts import navigation_bundle
from scripts.prepare_navigation_quality import registry_records, environment_record, period_for, static_url, extend, URLS, STATIC
from tools.navigation_context import StaticReference, ReferencePeriod, EnvironmentObservation, static_summary, environment_context
from tools.navigation_references import NavigationCatalog, NavigationScreenRequest, screen_references
from test_navigation_sources_readiness import extended
from test_navigation_references import IMO, VESSEL, NOW, PORT

PERIOD = period_for(NOW)


def registered(**changes):
    return {'mmsi':123456789,'imoNumber':int(IMO),'dimensionToBow':113,'dimensionToStern':27,
        'dimensionToPort':19,'dimensionToStarboard':4,'draught':8.02,'validFrom':'2021-01-08T00:00:00','validTo':None,**changes}


def references(*rows):
    return [StaticReference.model_validate(r) for r in registry_records({'success':True,'data':list(rows)}, {'123456789':IMO})]


def weather(key='smhi_water_gothenburg', **change):
    water = key=='smhi_water_gothenburg'
    station = '35120' if water else '71380'
    name = 'Göteborg-Tångudden' if water else 'Vinga A'
    payload = {'station':{'key':station,'name':name},'parameter':{'key':'13' if water else '4',
        'unit':'cm' if water else 'meter per sekund','summary':'medelvärde 10 min, 1 gång/tim'},
        'period':{'key':'latest-hour'},'value':[
            {'date':int((NOW-timedelta(minutes=15)).timestamp()*1000),'value':'-13.7' if water else '2','quality':'G'},
            {'date':int((NOW-timedelta(minutes=10)).timestamp()*1000),'value':'-13.4' if water else '3','quality':'O'}]}
    metadata = {'key':station,'name':name,'active':True,'mobile':False,'latitude':57.6821,'longitude':11.8722,
        'position':[{'from':0,'to':int(NOW.timestamp()*1000),'latitude':57.632214,'longitude':11.604796}]}
    source = {'url':URLS[key+'_metadata'],'sha256':'d'*64}
    datum = {'url':URLS['smhi_water_datum'],'sha256':'e'*64}
    datum_text = f'{name};{station};57.6821;11.8722\nHöjdsystem: RH2000'
    row = environment_record(key,payload,metadata,source,datum,datum_text)
    row.update(change)
    return row, payload, metadata, source, datum, datum_text


def quality_data():
    data=extended();data['version']='NAVIGATION-REFERENCES-1.3'
    for key in ('norway_static','schema_no_static','smhi_water_gothenburg'):
        data['sources'].append({**deepcopy(data['sources'][0]),'id':key})
    data['static_reference_period']=PERIOD.model_dump(mode='json')
    data['static_references']=[r.model_dump(mode='json') for r in references(registered())]
    data['environment_observations']=[weather()[0]]
    return data


def test_documented_registered_metres_keep_current_raw_draught_separate():
    catalog=NavigationCatalog.model_validate(quality_data())
    result=screen_references(catalog,NavigationScreenRequest(vessel_id=VESSEL,port_id=PORT),now=NOW)
    assert result['static_reference']['length_m']=='140' and result['static_reference']['beam_m']=='23'
    assert result['static_reference']['candidates'][0]['registry_draught_m']=='8.02'
    assert catalog.observations[-1].raw_reported_fields['draught']=='6.5'
    assert catalog.observations[-1].reported_draught_m is None
    assert all(c['kind']!='draught' for b in result['berths'] for c in b['static_reference_checks'])
    assert result['admission']=='not_assessed' and result['readiness']['status']=='requires_review'
    assert all(c['status']=='unavailable' for b in result['berths'] for c in b['checks'])
    assert {'norway_static','schema_no_static','smhi_water_gothenburg'} <= {s['id'] for s in result['sources']}


def test_multiple_records_require_all_values_consistent_per_axis():
    rows=references(registered(),registered(dimensionToBow=112))
    summary=static_summary(rows,PERIOD,VESSEL)
    assert summary['length_m'] is None and summary['beam_m']=='23'
    assert 'REGISTRY_LENGTH_CONFLICT' in summary['issues']
    rows=references(registered(),registered(dimensionToBow=0))
    assert static_summary(rows,PERIOD,VESSEL)['length_m'] is None


@pytest.mark.parametrize('change',[{'imoNumber':9074729},{'imoNumber':None}])
def test_identity_conflicts_are_retained_and_block_even_matching_candidates(change):
    rows=references(registered(),registered(**change))
    summary=static_summary(rows,PERIOD,VESSEL)
    assert summary['candidate_count']==2 and summary['status']=='identity_conflict'
    assert summary['length_m'] is None


def test_inactive_records_do_not_override_active_values_or_hide_unknown_periods():
    rows=references(registered(),registered(dimensionToBow=50,validTo='2022-01-01T00:00:00'))
    assert static_summary(rows,PERIOD,VESSEL)['length_m']=='140'
    rows=references(registered(validFrom=None))
    assert static_summary(rows,PERIOD,VESSEL)['status']=='period_unknown'
    rows=references(registered(validFrom='not a date'))
    assert 'REGISTRY_TIME_INVALID' in rows[0].issues


@pytest.mark.parametrize('change',[{'dimensionToBow':511},{'dimensionToStern':0},{'dimensionToPort':63},
    {'dimensionToStarboard':False},{'dimensionToBow':1.2},{'dimensionToBow':'100'}])
def test_invalid_offsets_never_become_complete_reference_dimensions(change):
    row=references(registered(**change))[0]
    assert row.reference_length_m is None or row.reference_beam_m is None


def test_truncated_and_out_of_request_registry_responses_fail_closed():
    for payload in ({'success':False,'data':[]},{'success':True,'data':[registered()]*10000},
                    {'success':True,'data':[registered(mmsi=999999999)]}):
        with pytest.raises(ValueError):registry_records(payload,{'123456789':IMO})


def test_latest_unchecked_signed_water_level_is_preserved_with_datum():
    row,*_=weather()
    model=EnvironmentObservation.model_validate(row)
    assert str(model.value)=='-13.4' and model.quality=='O' and model.vertical_datum=='RH2000'
    sources={s.id:s for s in NavigationCatalog.model_validate(quality_data()).sources}
    result=environment_context([model],PORT,sources,NOW)
    assert result['observations'][0]['quality_status']=='unchecked'
    assert result['observations'][0]['comparison_use']=='context_only'
    assert environment_context([model],'WPI:28190',sources,NOW)['observations']==[]
    old=environment_context([model],PORT,sources,NOW+timedelta(hours=3))['observations'][0]
    assert old['age_status']==old['capture_age_status']=='stale'
    future=environment_context([model],PORT,sources,NOW-timedelta(hours=1))['observations'][0]
    assert future['age_status']=='time_in_future'


@pytest.mark.parametrize('change',[{'port_id':'WPI:28190'},{'unit':'m/s'},{'station_id':'99999'},
    {'vertical_datum':None},{'datum_evidence':None},{'parameter_id':'4'}])
def test_environment_model_rejects_unreviewed_binding_units_and_missing_datum(change):
    row,*_=weather(**change)
    with pytest.raises(ValidationError):EnvironmentObservation.model_validate(row)


def test_environment_parser_rejects_changed_unit_station_datum_and_duplicate_latest():
    _,payload,metadata,source,datum,text=weather()
    for key,value in [('unit','m'),('key','999')]:
        changed=deepcopy(payload);changed['parameter'][key]=value
        with pytest.raises(ValueError):environment_record('smhi_water_gothenburg',changed,metadata,source,datum,text)
    with pytest.raises(ValueError):environment_record('smhi_water_gothenburg',payload,metadata,source,datum,text.replace('RH2000','other'))
    payload['value'].append(deepcopy(payload['value'][-1]))
    with pytest.raises(ValueError):environment_record('smhi_water_gothenburg',payload,metadata,source,datum,text)


def test_wind_position_uses_its_valid_period_not_first_historical_location():
    row,payload,metadata,source,_,_=weather('smhi_wind_vinga')
    metadata.pop('name');metadata['title']='Vindhastighet - Vinga A: Välj tidsutsnitt'
    metadata['position'].insert(0,{'from':0,'to':100,'latitude':58,'longitude':12})
    result=environment_record('smhi_wind_vinga',payload,metadata,source)
    assert result['latitude']=='57.632214'
    metadata['position'].append(deepcopy(metadata['position'][-1]))
    with pytest.raises(ValueError):environment_record('smhi_wind_vinga',payload,metadata,source)


def test_registry_and_weather_do_not_fill_scenario_or_change_existing_checks():
    data=quality_data()
    catalog=NavigationCatalog.model_validate(data)
    request=NavigationScreenRequest(vessel_id=VESSEL,port_id=PORT)
    result=screen_references(catalog,request,now=NOW)
    old=screen_references(NavigationCatalog.model_validate(extended()),request,now=NOW)
    assert result['readiness']==old['readiness']
    assert [b['checks'] for b in result['berths']]==[b['checks'] for b in old['berths']]
    assert [b['operational_checks'] for b in result['berths']]==[b['operational_checks'] for b in old['berths']]


@pytest.mark.parametrize('change',['old_version','unknown_identity','ambiguous_identity','missing_schema','duplicate_station','future_period'])
def test_catalog_checks_lineage_and_backward_version_boundaries(change):
    data=quality_data()
    if change=='old_version':data['version']='NAVIGATION-REFERENCES-1.2'
    if change=='unknown_identity':data['static_references'][0]['mmsi']='987654321'
    if change=='ambiguous_identity':data['observations'][-1]['issues'].append('AIS_IDENTITY_AMBIGUOUS')
    if change=='missing_schema':data['sources']=[s for s in data['sources'] if s['id']!='schema_no_static']
    if change=='duplicate_station':data['environment_observations']*=2
    if change=='future_period':data['static_reference_period']['end']=(NOW+timedelta(days=31)).isoformat()
    with pytest.raises(ValidationError):NavigationCatalog.model_validate(data)


def test_bundle_roundtrip_preserves_original_capture_times_and_old_catalogs(tmp_path):
    for version,data in [('old',extended()),('quality',quality_data())]:
        path=tmp_path/(version+'.json');path.write_text(json.dumps(data),encoding='utf-8')
        bundle=tmp_path/(version+'-bundle');navigation_bundle.export_bundle(path,bundle)
        target=tmp_path/(version+'-installed.json');navigation_bundle.install_bundle(bundle,target)
        assert target.read_bytes()==path.read_bytes()


def test_preparation_rejects_raw_hash_tamper_before_parsing(tmp_path):
    from scripts.prepare_navigation_references import digest
    base=tmp_path/'base.json';base.write_text(json.dumps(extended()),encoding='utf-8')
    raw=tmp_path/'raw';raw.mkdir()
    catalog=NavigationCatalog.model_validate_json(base.read_bytes())
    expected={'norway_static':static_url(catalog,PERIOD),**URLS}
    records={}
    for key,url in expected.items():
        filename=key+('.csv' if key=='smhi_water_datum' else '.json')
        (raw/filename).write_bytes(b'{}')
        records[key]={'status':'captured','request_url':url,'url':STATIC if key=='norway_static' else url,
            'filename':filename,'sha256':'0'*64,'bytes':2}
    (raw/'manifest.json').write_text(json.dumps({'base_sha256':digest(base.read_bytes()),
        'period':PERIOD.model_dump(mode='json'),'sources':records}),encoding='utf-8')
    with pytest.raises(ValueError,match='hash/size'):extend(base,raw,tmp_path/'new.json')
    assert not (tmp_path/'new.json').exists()


def test_route_audit_keeps_expired_unbound_routes_outside_catalog(monkeypatch,tmp_path):
    from scripts import prepare_navigation_quality as prep
    row={'routenumber':'NO-420012','validityperiodstart':'2025-02-19T00:00:00+00:00','validityperiodstop':'2026-08-05T00:00:00+00:00'}
    def download(url,target):
        if url.endswith('/download'):
            target.write_bytes(b'<route xmlns="http://www.cirm.org/RTZ/1/1"><waypoints><waypoint id="1"/></waypoints></route>')
        else:
            target.write_text(json.dumps([row] if url.endswith('/list') or url.endswith('/NOBGO') else []),encoding='utf-8')
    monkeypatch.setattr(prep,'download',download)
    summary=prep.capture_routes(tmp_path/'routes')
    assert summary['currently_valid_records']==0 and summary['catalog_routes_added']==0
    assert summary['supported_port_route_counts']=={'SEGOT':0,'FIHEL':0,'DKAAL':0}
    manifest=json.loads((tmp_path/'routes/manifest.json').read_text())
    assert manifest['rtz_sample']['waypoints']==1
