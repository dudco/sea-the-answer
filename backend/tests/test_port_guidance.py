"""Official scopes, provenance and explicit review survive offline refresh and API use."""
from copy import deepcopy
from datetime import timedelta
import json

import pytest
from pydantic import ValidationError

from scripts import prepare_port_guidance as prep, navigation_bundle
from scripts.prepare_navigation_references import digest
from tools.navigation_guidance import DOCUMENTS, PortGuidance, guidance_context
from tools.navigation_references import NavigationCatalog, NavigationScreenRequest, screen_references
from api.navigation_query import is_navigation_question
from test_navigation_quality import quality_data
from test_navigation_references import NOW, VESSEL, PORT

TEXT = {
 'gothenburg_draught': '''Maximum Draught Maximum draught at mean sea level (MW), in the fairways to:
 Tor Harbour via the North Channel *) 18.9 m Tor Bay 5.5 m Arendal Harbour 9.1 m Skandia Harbour 13.5 m
 Skarvik Harbour (berths 510 and 519) 12.5 m Fairway Skarvik – Rya 9.3 m Fairway Rya – Lindholmen 7.7 m
 Fairway Lindholmen – Free Port 6.7 m Please note density variations.
 Minimum UKC in fairways are 0.7m and at berths 0.5m. Last updated 2021-01-31''',
 'gothenburg_tugs': '''Tug Regulations Escort towing is compulsory for: All loaded tankers over 30 000 dwt
 Tankers in ballast condition over 30 000 dwt with empty but not gasfree tanks (residues with flashpoint below 60 degrees C).
 Inerted tanks are not to be considered as “gasfree” tanks. Tug is ordered by master or agent in advance. Last updated 2021-01-30''',
 'gothenburg_weather': '''Visibility Wind Darkness Tankers with LOA 230 m – 290 m Max wind: 15 m/s (average wind force at Måvholmsbådan)
 Min visibility loaded: > 2 NM Min visibility ballast: > 1 NM
 Tankers with LOA equal to or exceeding 290 m (VLCC) Arrival shall be done in daylight.
 Exceptional departure only subject to consultation between the Pilot/Captain and the Port Captain and Pilot Area Manager.
 Max wind: 10 m/s (average wind force at Måvholmsbådan) Min visibility: > 2 NM
 Car carriers - Berth 601 LOA > 190 m Arrival: Max wind: 16 m/s (average wind force at "Karet") Departure: Max wind: 18 m/s (average wind force at "Karet").
 Exceptional departure only if consultation between the Pilot/Master, Port Captain and Pilot Area Manager. Last updated 2021-01-31''',
 'gothenburg_control': '''Port Control All vessels that are due to call at the Port of Gothenburg must issue notification at least 24 hours before arrival.
 Do you need to know what kinds of work are under way in the port area? Contact Port Control, which is best placed to answer such questions.''',
 'helsinki_regulations': '''Port of Helsinki Harbour Regulations The vessel shall be moored or anchored in the location indicated by the Port of Helsinki, and it may not be moved to another location without the Port’s permission.
 The master of the vessel shall verify the current depth at the vessel’s location.
 Tug assistance shall be used when mooring and unmooring the vessel, if necessary. The Port of Helsinki may also order the vessel to use tug assistance and/or a pilot.
 These harbour regulations entered into force 7.2.2023.''',
 'helsinki_cruise_navigation': '''Navigation & Safety Maximum Vessel’s Draft West Harbour 10,8m South Harbour 7,9m Katajanokka Harbour 9,3 m
 Pilotage Advance Notice Compulsory for vesels Loa. over 70m Arrival min. 3h / Departure min. 2h''',
}


def baseline(tmp_path):
    data=quality_data()
    for label in ('519','601'):
        berth=deepcopy(data['ports'][0]['berths'][0]);berth['label']=label;berth['berth_id']=PORT+':BERTH:'+label
        data['ports'][0]['berths'].append(berth)
    path=tmp_path/'base.json';path.write_text(json.dumps(data),encoding='utf-8')
    return path


def capture(monkeypatch,base,raw,texts=None,chrome=''):
    texts=texts or TEXT
    def download(url,path,**kwargs):
        assert url in kwargs['allowed_urls']
        key=next(k for k,row in DOCUMENTS.items() if row[1]==url)
        html='<html><nav>wrong port 999</nav><main><script>wrong 999</script>'+texts[key]+'</main>'+chrome+'</html>'
        path.write_text(html,encoding='utf-8')
    monkeypatch.setattr(prep,'download',download)
    return prep.fetch(base,raw)


@pytest.fixture
def prepared(tmp_path,monkeypatch):
    base=baseline(tmp_path);raw=tmp_path/'raw';capture(monkeypatch,base,raw)
    reviewed=tmp_path/'review.json';receipt=prep.review(base,raw,reviewed)
    path=tmp_path/'catalog.json';prep.prepare(base,raw,reviewed,receipt['review_sha256'],path)
    return base,raw,reviewed,path


def test_official_units_dates_and_scopes_are_preserved_without_changing_comparison(prepared):
    base,raw,reviewed,path=prepared
    old=NavigationCatalog.model_validate_json(base.read_bytes());new=NavigationCatalog.model_validate_json(path.read_bytes())
    assert len(new.port_guidance)==6 and sum(len(d.facts) for d in new.port_guidance)==21
    assert new.sources==old.sources and new.observations==old.observations and new.ports==old.ports
    assert new.static_references==old.static_references and new.environment_observations==old.environment_observations
    sources={d.id:d for d in new.port_guidance}
    assert str(sources['gothenburg_draught'].displayed_updated_on)=='2021-01-31'
    assert str(sources['helsinki_regulations'].effective_on)=='2023-02-07'
    assert sources['gothenburg_control'].effective_on is None
    vals=sources['gothenburg_tugs'].facts[0].values
    assert [str(v.value) for v in vals]==['30000','30000','60']
    assert [v.unit for v in vals]==['DWT','DWT','°C']
    request=NavigationScreenRequest(vessel_id=VESSEL,port_id=PORT)
    before=screen_references(old,request);after=screen_references(new,request)
    assert before['berths']==after['berths'] and before['readiness']==after['readiness']
    assert after['admission']=='not_assessed' and not after['official_guidance']['used_for_automatic_comparison']


def test_known_berth_and_port_bindings_exclude_other_berth_rules(prepared):
    catalog=NavigationCatalog.model_validate_json(prepared[-1].read_bytes())
    docs=catalog.port_guidance
    context=guidance_context(docs,PORT,PORT+':BERTH:510',NOW+timedelta(hours=1))
    ids={f['id'] for d in context['documents'] for f in d['facts']}
    assert 'skarvik' in ids and 'car-carrier-601' not in ids
    ids={f['id'] for d in guidance_context(docs,PORT,PORT+':BERTH:601',NOW+timedelta(hours=1))['documents'] for f in d['facts']}
    assert 'car-carrier-601' in ids and 'skarvik' not in ids
    assert len(guidance_context(docs,'WPI:28190',None,NOW)['documents'])==2
    assert guidance_context(docs,'WPI:30400',None,NOW)['documents']==[]


def test_old_displayed_revision_is_not_renewed_by_capture(prepared):
    docs=NavigationCatalog.model_validate_json(prepared[-1].read_bytes()).port_guidance
    now=docs[0].retrieved_at+timedelta(hours=1)
    doc=guidance_context(docs,PORT,None,now)['documents'][0]
    assert doc['capture_age_status']=='within_age_window' and doc['displayed_revision_age_status']=='older_than_one_year'
    assert doc['applicability']=='requires_review'
    assert guidance_context(docs,PORT,None,now+timedelta(days=8))['documents'][0]['capture_age_status']=='stale'
    assert guidance_context(docs,PORT,None,now-timedelta(days=1))['documents'][0]['capture_age_status']=='time_in_future'


def test_raw_chrome_change_and_meaningful_number_change_are_distinguished(prepared,tmp_path,monkeypatch):
    _,_,_,base=prepared
    raw=tmp_path/'same';capture(monkeypatch,base,raw,chrome='<!-- different footer -->')
    report=prep.candidate(base,raw)
    assert all(r['change']=='unchanged' and r['raw_changed'] for r in report['changes'])
    texts={**TEXT,'gothenburg_draught':TEXT['gothenburg_draught'].replace('18.9','18.8')}
    changed=tmp_path/'changed';capture(monkeypatch,base,changed,texts)
    diff=next(r for r in prep.candidate(base,changed)['changes'] if r['id']=='gothenburg_draught')
    assert diff['change']=='content_changed' and diff['facts_changed']
    assert diff['previous_published_values']['tor-north'][0]['value']=='18.9'
    assert diff['published_values']['tor-north'][0]['value']=='18.8'


@pytest.mark.parametrize('tamper',['review_hash','review_facts','raw','manifest','base'])
def test_unreviewed_or_changed_inputs_do_not_create_catalog(prepared,tmp_path,tamper):
    base,raw,reviewed,_=prepared
    sha=digest(reviewed.read_bytes())
    if tamper=='review_hash':sha='f'*64
    if tamper=='review_facts':
        report=json.loads(reviewed.read_text(encoding='utf-8'));report['documents'][0]['facts'][0]['values'][0]['value']='1'
        reviewed.write_text(json.dumps(report));sha=digest(reviewed.read_bytes())
    if tamper=='raw':(raw/'gothenburg_draught.html').write_text('changed')
    if tamper=='manifest':
        m=json.loads((raw/'manifest.json').read_text());m['sources']['gothenburg_draught']['retrieved_at']='2026-01-01T00:00:00Z'
        (raw/'manifest.json').write_text(json.dumps(m))
    if tamper=='base':base.write_bytes(base.read_bytes()+b' ')
    output=tmp_path/'unreviewed.json'
    with pytest.raises(ValueError):prep.prepare(base,raw,reviewed,sha,output)
    assert not output.exists()


def test_parser_does_not_pick_one_conflicting_value_or_ignore_qualifications():
    original=TEXT['gothenburg_draught']
    with pytest.raises(ValueError):prep.extract('gothenburg_draught',original.replace('mean sea level (MW)','unknown datum'))
    with pytest.raises(ValueError):prep.extract('gothenburg_draught',original+' Tor Bay 6.0 m')
    with pytest.raises(ValueError):prep.extract('gothenburg_tugs',TEXT['gothenburg_tugs'].replace('not gasfree','gasfree'))
    with pytest.raises(ValueError):prep.extract('gothenburg_weather',TEXT['gothenburg_weather'].replace('LOA > 190 m','LOA > 200 m'))
    with pytest.raises(ValueError):prep.extract('gothenburg_weather',TEXT['gothenburg_weather'].replace('Karet','Vinga'))
    repeated=TEXT['gothenburg_control']*2
    assert len(prep.extract('gothenburg_control',repeated))==2
    with pytest.raises(ValueError):prep.main_text(b'<main>first</main><main>second</main>','gothenburg_control')


def test_source_failure_is_recorded_and_keeps_baseline(prepared,tmp_path,monkeypatch):
    base,*_=prepared;before=base.read_bytes()
    def fail(*args,**kwargs):raise OSError('unavailable')
    monkeypatch.setattr(prep,'download',fail)
    raw=tmp_path/'failed'
    with pytest.raises(ValueError):prep.fetch(base,raw)
    assert base.read_bytes()==before
    manifest=json.loads((raw/'manifest.json').read_text())
    assert len(manifest['sources'])==6 and all(r['status']=='failed' for r in manifest['sources'].values())


@pytest.mark.parametrize('destination',['http://www.sjofartsverket.se/plain','https://unreviewed.example/redirect'])
def test_source_redirect_cannot_downgrade_tls_or_change_origin(destination):
    from urllib.request import Request
    from scripts.prepare_navigation_quality import SameOriginTLSRedirect
    handler=SameOriginTLSRedirect()
    request=Request(DOCUMENTS['gothenburg_draught'][1])
    with pytest.raises(ValueError):handler.redirect_request(request,None,302,'Found',{},destination)


@pytest.mark.parametrize('tamper',['old_version','missing_review','wrong_url','wrong_port','duplicate_document','wrong_berth'])
def test_catalog_rejects_unbound_guidance(prepared,tamper):
    data=json.loads(prepared[-1].read_text(encoding='utf-8'))
    if tamper=='old_version':data['version']='NAVIGATION-REFERENCES-1.3'
    if tamper=='missing_review':data['guidance_review_sha256']=None
    if tamper=='wrong_url':data['port_guidance'][0]['url']='https://example.org/source'
    if tamper=='wrong_port':data['port_guidance'][0]['port_id']='WPI:28190'
    if tamper=='duplicate_document':data['port_guidance'][1]=deepcopy(data['port_guidance'][0])
    if tamper=='wrong_berth':data['port_guidance'][0]['facts'][0]['berth_ids']=[PORT+':BERTH:999']
    with pytest.raises(ValidationError):NavigationCatalog.model_validate(data)


def test_offline_bundle_preserves_guidance_and_lists_its_sources(prepared,tmp_path,monkeypatch):
    path=prepared[-1]
    def fail(*args,**kwargs):raise AssertionError('Network must not run')
    monkeypatch.setattr(prep,'download',fail)
    bundle=tmp_path/'bundle';navigation_bundle.export_bundle(path,bundle)
    sources=(bundle/'SOURCES.txt').read_text(encoding='utf-8')
    assert 'Sjöfartsverket / Maximum Draught' in sources and '2021-01-31' in sources
    target=tmp_path/'installed.json';navigation_bundle.install_bundle(bundle,target)
    assert target.read_bytes()==path.read_bytes()


@pytest.mark.parametrize('question',['우리 배가 헬싱키에 입항하려면 어떤 조건을 확인해야 해?',
    '우리 배가 예테보리 항구를 이용하기 전에 뭘 확인해야 해?',
    'What conditions should our vessel check before entering Helsinki?'])
def test_bounded_port_condition_questions_enter_existing_tool_route(question):
    assert is_navigation_question(question)


@pytest.mark.parametrize('question',['헬싱키 입항 절차를 문서만 사용해서 알려줘','예선 규정의 정의를 알려줘','어떻게 입항 신고 서류를 제출해?'])
def test_document_only_and_procedure_requests_keep_existing_rag_route(question):
    assert not is_navigation_question(question)
