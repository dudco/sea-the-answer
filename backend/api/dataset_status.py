"""Authenticated inventory adapter; unavailable is distinct from a confirmed zero."""
import os
import re

import psycopg
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from tools.api import create_engine_for
from tools.dataset_status import read_status
from tools.navigation_references import catalog_summary
from . import config, navigation_query, navigation_service
from .dataset_intent import DATASETS
from .errors import ApiError
from .maritime_context import resolve_real_ship
from .question_intent import date_slots
from .validation import utc_now

LABELS={'ais':'AIS 수집본','mrv':'실제 MRV 연간 보고','dwt':'DWT 공개 후보',
        'noon':'Synthetic Noon','operations':'일별 운항 기록','documents':'열람 가능한 문서','ports':'항만·선석 공개 참조'}


def answer(ctx, datasets, *, scope_text=None):
    """scope_text: model-provided ship/period wording; defaults to the question (legacy rules)."""
    if not datasets or len(set(datasets))!=len(datasets) or any(d not in DATASETS for d in datasets):
        raise ValueError('Invalid inventory request')
    q=ctx.body['question'] if scope_text is None else scope_text;engine=None
    result={'datasets':[],'scope':{'coverage':'server_inventory'},'assessed_at':utc_now()}
    try:
        years,periods=date_slots(q)
        ships=ctx.db.ships() if any(d!='documents' for d in datasets) else []
        scoped=bool(re.search(r'우리\s*(?:배|선박)|본선|\b(?:IMO|ship|vessel)\b|[0-9]{7}|[가-힣a-z0-9_-]{2,30}호(?:의|는|\s|$)',q,re.I)
                    or any(navigation_query.mentions(q,s['name']) for s in ships))
        ship=navigation_query.select_ship(q,ships,ctx.body.get('context') or {}) if scoped else None
        if scoped and (not ship or ship.get('sample')):
            return {'status':'needs_input','notice':'자료를 확인할 실제 등록 선박의 이름이나 IMO 번호를 알려 주세요.',
                    'dataStatus':result,'warnings':['DATASET_SCOPE_REQUIRED']}
        result['scope'].update(years=years,periods=[p.model_dump() for p in periods],
                              ship={k:ship.get(k) for k in ('id','name','imo','version')} if ship else None)
        for dataset in datasets:
            item={'dataset':dataset,'label':LABELS[dataset]}
            try:
                if dataset in ('mrv','noon','dwt'):
                    if periods or dataset=='dwt' and years or dataset=='noon' and scoped:
                        item.update(status='unsupported_scope',notice='해당 기간/선박 조건은 이 자료 현황에 적용할 수 없습니다. MRV는 보고 연도로, 합성 Noon은 실제 선박과 구분해 질문해 주세요.')
                    else:
                        if engine is None:engine=create_engine_for(os.getenv('MARITIME_DATA_DATABASE_URL') or config.database_url())
                        vessel=None
                        if scoped:
                            identity=resolve_real_ship(ctx.db,engine,ship['id'])
                            if not identity.vessel_id:
                                raise ApiError(503,'MAPPING_REQUIRED','실제 선박 매핑을 확인해 주세요.')
                            vessel=identity.vessel_id
                        item.update(read_status(engine,dataset,vessel_id=vessel,years=years))
                elif dataset in ('ais','ports'):
                    if years or periods:
                        item.update(status='unsupported_scope',notice='AIS 수집본 시점은 MRV 보고 연도/일별 운항 기간과 다릅니다. 날짜 조건 없이 수집 현황을 확인해 주세요.')
                    elif scoped:
                        item.update(status='unsupported_scope',notice='해당 선박의 AIS 포함 여부는 선박 이름/IMO와 함께 AIS 자료 유무로 질문해 주세요.')
                    elif dataset=='ports':
                        data,digest=navigation_service.load_snapshot()
                        count=sum(len(p.berths) for p in data.ports)
                        item.update(status='available' if count else 'empty',row_count=count,port_count=len(data.ports),
                            notice='공개 선석 항목의 수입니다. 현재 실측 조건·실시간 혼잡·입항 승인은 확인하지 않습니다.')
                    else:
                        data,digest=navigation_service.load_snapshot();summary=catalog_summary(data,digest)
                        item.update(status='available' if summary['ais_observation_count'] else 'empty',
                            row_count=summary['ais_observation_count'],vessel_count=summary['ais_unique_vessels'],
                            sources=[{'dataset_id':s['id'],'source_url':s['url']} for s in summary['sources'] if s['id'] in ('ais','ais_no')],
                            notice='공개 수집본이며 실시간 수신/현재 위치/입항 승인을 의미하지 않습니다.',freshness=summary['freshness'])
                elif dataset=='documents':
                    if scoped or years or periods:
                        item.update(status='unsupported_scope',notice='문서 현황은 현재 계정의 열람 가능 범위입니다. 선박/운항 기간 조건을 문서 발행 조건으로 바꾸지 않습니다.')
                    else:
                        count=len(ctx.db.documents(ctx.user))
                        item.update(status='available' if count else 'empty',row_count=count,
                                    notice='현재 계정이 열람할 수 있는 문서만 포함합니다.')
                else:
                    clauses=[];params=[]
                    if ship:clauses.append('ship=%s');params.append(ship['id'])
                    if years:clauses.append('EXTRACT(YEAR FROM date::date)=ANY(%s)');params.append(years)
                    if periods:
                        clauses.append('('+' OR '.join('date BETWEEN %s AND %s' for _ in periods)+')')
                        for p in periods:params.extend([p.start,p.end])
                    where=' WHERE '+' AND '.join(clauses) if clauses else ''
                    with ctx.db.db.transaction():
                        old_timeout=ctx.db.one("SELECT current_setting('statement_timeout') AS value")['value']
                        ctx.db.run("SET LOCAL statement_timeout='5s'")
                        row=ctx.db.one('SELECT count(*) AS row_count,count(DISTINCT ship) AS vessel_count,'
                            'count(*) FILTER (WHERE body->>\'sample\'=\'true\') AS sample_count,'
                            'min(date) AS first_period,max(date) AS last_period FROM operations'+where,tuple(params))
                        ctx.db.one("SELECT set_config('statement_timeout',%s,true)",(old_timeout,))
                    item.update(row,status='available' if row['row_count'] else 'empty',
                                notice='앱 일별 기록이며 MRV 연간 보고와 별개입니다. 가상 예시 건수를 따로 표시합니다.')
            except (SQLAlchemyError,HTTPException,ApiError,ValueError,psycopg.Error):
                item.update(status='unavailable',notice='현재 연결·스키마·매핑 또는 자료 형식을 확인할 수 없습니다. 자료가 없다는 뜻은 아닙니다.')
            result['datasets'].append(item)
        complete=all(i['status'] in ('available','empty') for i in result['datasets'])
        return {'status':'completed' if complete else 'partial',
                'notice':'현재 서버의 실제 등록 현황입니다. 전체 등록 건수·집계 적격 건수·자료 유형을 구분해 확인하세요.',
                'dataStatus':result,'warnings':['DATASET_STATUS_ONLY']}
    except (ValueError,psycopg.Error):
        return {'status':'needs_input','notice':'자료 종류와 선박·보고 연도 또는 날짜 범위를 다시 알려 주세요. 확인하지 못한 건수를 임의로 표시하지 않습니다.',
                'dataStatus':result,'warnings':['DATASET_SCOPE_REQUIRED']}
    finally:
        if engine is not None:engine.dispose()
