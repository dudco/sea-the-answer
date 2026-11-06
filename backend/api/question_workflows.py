"""Authenticated read-only orchestration, explicit clarification and owner-bound continuation."""
from datetime import date
from decimal import Decimal, localcontext
import os
import re
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from pydantic import Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from . import question_intent as intent, workflow_skills as skills, config
from .errors import ApiError, require
from .maritime_context import resolve_real_ship
from .validation import utc_now
from tools.api import create_engine_for
from tools.port_reference import valid_imo
from tools.reference_intensity import ReferenceIntensityRequest, calculate_reference

VERSION='HAEDAP-QUESTION-WORKFLOW-1.0'


class Ship(intent.Strict):
    id: str = Field(min_length=1,max_length=100)
    name: str = Field(max_length=100)
    version: int
    imo: str = Field(default='',max_length=30)


class Scope(intent.Strict):
    action: intent.Action
    ships: list[Ship] = Field(default_factory=list,max_length=2)
    years: list[int] = Field(default_factory=list,max_length=3)
    periods: list[intent.Period] = Field(default_factory=list,max_length=2)
    document_ids: list[str] = Field(default_factory=list,max_length=5)
    document_question: str = Field(default='',max_length=2000)
    reference_ack: bool = False
    mappings: dict[str,str|None] = Field(default_factory=dict,max_length=2)


class Reply(intent.Strict):
    ships: list[str] | None = Field(default=None,max_length=2)
    years: list[int] | None = Field(default=None,max_length=3)
    periods: list[intent.Period] | None = Field(default=None,max_length=2)
    document_ids: list[str] | None = Field(default=None,max_length=5)
    reference_ack: bool | None = Field(default=None,strict=True)


def norm(value):return ' '.join(str(value or '').casefold().split())
def snapshot(ship):return Ship(id=ship['id'],name=ship['name'],version=ship['version'],imo=str(ship.get('imo') or ''))


def explicit_ships(question,ships,mentions=()):
    imos=re.findall(r'\bIMO\s*[:#]?\s*(\d{7})\b',question,re.I)
    if any(not valid_imo(i) for i in imos):raise ValueError('IMO 번호의 자리수·검증 숫자를 확인해 주세요.')
    names=[s for s in ships if len(norm(s['name']))>=2 and re.search(
        r'(?<![가-힣a-z0-9_-])'+re.escape(norm(s['name']))+r'(?=$|[\s,/.·?!]|(?:의|와|과|를|을|는|은|도|에|로|이|가)(?:\s|$))',norm(question))]
    if len({norm(s['name']) for s in names})<len(names) and not imos:
        raise ValueError('같은 이름의 선박이 여러 척입니다. IMO 번호 또는 선박 선택으로 구분해 주세요.')
    matched={s['id']:s for s in ships if s in names or re.sub(r'^IMO\s*','',str(s.get('imo','')),flags=re.I) in imos}
    for mention in mentions:
        if re.sub(r'\s+','',norm(mention)) in ('우리배','우리선박','이배','해당선박','ourship','ourvessel','thisship'):
            continue
        rows=[s for s in ships if norm(s['name'])==norm(mention) or norm(s.get('imo'))==norm(mention).removeprefix('imo ').strip()]
        if not rows:raise ValueError('질문에 있는 선박을 등록 선박 목록에서 확인할 수 없습니다.')
        matched.update((s['id'],s) for s in rows)
    if imos and any(not any(i==re.sub(r'^IMO\s*','',str(s.get('imo','')),flags=re.I) for s in matched.values()) for i in imos):
        raise ValueError('해당 IMO의 앱 선박을 먼저 등록·연결해 주세요.')
    if len(matched)>2:raise ValueError('선박 범위를 최대 두 척으로 좁혀 주세요.')
    if not matched and re.search(r'[가-힣A-Za-z0-9_-]{2,30}호(?:의|를|는|도|\s|$)',question):
        raise ValueError('이름이 일치하는 등록 선박을 선택해 주세요.')
    return list(matched.values())


def previous(ctx,ships):
    value=(ctx.body.get('context') or {}).get('previousQueryId')
    if not isinstance(value,str):return None
    try:
        if str(UUID(value))!=value.lower():return None
    except ValueError:return None
    row=ctx.db.one('SELECT q.response FROM queries q JOIN query_owner o ON o.id=q.id WHERE q.id=%s AND o.owner=%s',(value,ctx.user['id']))
    answer=row['response'] if row else None
    flow=answer.get('workflow') if isinstance(answer,dict) else None
    if not flow or flow.get('version')!=VERSION:return None
    try:scope=Scope.model_validate(flow['scope'])
    except (ValueError,KeyError):return None
    current={s['id']:snapshot(s) for s in ships}
    if any(current.get(s.id)!=s for s in scope.ships):return None
    selected=(ctx.body.get('context') or {}).get('ship')
    if selected and scope.ships and selected not in {s.id for s in scope.ships}:return None
    if any(not ctx.db.can_read_document(ctx.user,d) for d in scope.document_ids):return None
    return answer,scope


def comparisons(rows):
    result=[]
    if len(rows)<2:return result
    for kind in ('mrv_reference','operations_summary'):
        same=[r for r in rows if r['kind']==kind]
        if len(same)<2:continue
        for current in same[1:]:
            first=same[0]
            fields=[('reference_dwt_intensity','gCO2/(DWT t * nm)')] if kind=='mrv_reference' else [('fuel_t','t'),('calculated_co2_t','t CO2'),('distance_nm','nm')]
            for field,unit in fields:
                a,b=first['result'].get(field),current['result'].get(field)
                usable=a is not None and b is not None and first['status'] not in ('blocked','unavailable') and current['status'] not in ('blocked','unavailable')
                # Sample and real operation data must not produce a shared change rate.
                if kind=='operations_summary' and (not first['result'].get('count') or not current['result'].get('count') or first['result'].get('sample')!=current['result'].get('sample')):usable=False
                with localcontext() as context:
                    context.prec=50
                    delta=Decimal(str(b))-Decimal(str(a)) if usable else None
                    percent=delta/Decimal(str(a))*100 if usable and Decimal(str(a))!=0 else None
                result.append({'kind':kind,'metric':field,'unit':unit,'base':first['label'],'target':current['label'],
                    'difference':skills.decimal_text(delta) if delta is not None else None,
                    'percent_change':skills.decimal_text(percent) if percent is not None else None,
                    'status':'arithmetic_only' if usable else 'not_comparable','reference_only':True,
                    'notice':'두 입력 결과의 산술 차이입니다. 보고 누락·기간 길이·자료 범위·제원 기준연도와 원인/규정 적용은 별도 확인해야 합니다.'})
    return result


def run_tools(ctx,scope):
    rows=[];evidence=[];statements=[];warnings=[];engine=None
    try:
        if scope.action in ('mrv_reference','combined'):
            engine=create_engine_for(os.getenv('MARITIME_DATA_DATABASE_URL') or config.database_url())
            for ship in scope.ships:
                resolved=resolve_real_ship(ctx.db,engine,ship.id)
                if ship.id in scope.mappings and scope.mappings[ship.id]!=resolved.vessel_id:
                    raise ApiError(409,'VERSION_CONFLICT','MRV 선박 연결이 바뀌었습니다. 새 질문으로 다시 조회해 주세요.')
                scope.mappings[ship.id]=resolved.vessel_id
                for year in scope.years:
                    request=ReferenceIntensityRequest(scope={'dataset':'real_annual','vessel_id':resolved.vessel_id,'year':year},accept_reference_limitations=True) if resolved.vessel_id else None
                    result=calculate_reference(engine,request) if request else {'status':'blocked','reference_only':True,'reference_dwt_intensity':None,'official_cii':None,'official_cii_rating':None,'blockers':['SHIP_MAPPING_REQUIRED']}
                    rows.append({'kind':'mrv_reference','label':f'{ship.name} · {year}','ship':ship.model_dump(),'year':year,'status':result['status'],'result':result})
            for ship in scope.ships:
                if resolve_real_ship(ctx.db,engine,ship.id).vessel_id!=scope.mappings[ship.id]:
                    raise ApiError(409,'VERSION_CONFLICT','MRV 연결이 변경되었습니다. 다시 조회해 주세요.')
        if scope.action in ('operations_summary','combined'):
            for ship in scope.ships:
                for period in scope.periods:
                    request=skills.SkillRequest(skill='operation-summary',question=ctx.body['question'],context={'ship':ship.id,'from':period.start,'to':period.end})
                    result=skills.operation_result(ctx.db,request)
                    rows.append({'kind':'operations_summary','label':f'{ship.name} · {period.start}~{period.end}','ship':ship.model_dump(),
                        'period':period.model_dump(),'status':'completed' if result['count'] else 'no_data','result':result})
        if scope.action=='selected_document':
            request=skills.SkillRequest(skill='selected-document-answer',question=scope.document_question or ctx.body['question'],document_ids=scope.document_ids,use_model=ctx.body.get('mode')=='llm')
            evidence=skills.selected_evidence(ctx.db,ctx.user,request)
            statements,_=skills.evidence_statements(request,evidence,'selected-document-answer',warnings)
    except SQLAlchemyError:
        raise ApiError(503,'DATA_SOURCE_UNAVAILABLE','해사 DB·입력 자료·매핑을 확인해 주세요.') from None
    except HTTPException as exc:
        raise ApiError(exc.status_code,'DATA_SOURCE_UNAVAILABLE' if exc.status_code==503 else 'INVALID_INPUT',str(exc.detail)) from None
    finally:
        if engine is not None:engine.dispose()
    return rows,evidence,statements,warnings


def save(ctx,scope,status,notice,missing,routing,*,rows=(),evidence=(),statements=(),warnings=(),parent=None):
    # Recheck app versions after potentially slow model/DB work.
    current={s['id']:snapshot(s) for s in ctx.db.ships()}
    require(all(current.get(s.id)==s for s in scope.ships),'선박 정보가 변경되었습니다. 새 질문으로 다시 조회해 주세요.','VERSION_CONFLICT',409)
    require(all(ctx.db.can_read_document(ctx.user,e['document_id']) for e in evidence),'문서 권한이 변경되었습니다.','FORBIDDEN',403)
    options={'ships':[{'id':s.id,'name':s.name,'imo':s.imo} for s in current.values()][:100] if 'ships' in missing else [],
        'documents':[{'id':d['id'],'title':d['title']} for d in ctx.db.documents(ctx.user)][:50] if 'document_ids' in missing else []}
    workflow={'version':VERSION,'scope':scope.model_dump(mode='json'),'missing':missing,'options':options,'routing':routing,
        'results':list(rows),'comparisons':comparisons(rows),'previous_query_id':parent}
    answer={'id':str(uuid4()),'question':ctx.body['question'],'task':'workflow','language':'en' if ctx.body.get('language')=='en' else 'ko',
        'generation':'workflow','status':status,'notice':notice,'warnings':list(warnings),'statements':list(statements),
        'evidence':list(evidence),'toolRuns':[],'reportSuggested':False,'workflow':workflow}
    ctx.db.run('INSERT INTO queries VALUES(%s,%s,%s,%s)',(answer['id'],ctx.body['question'],Jsonb(answer),utc_now()))
    ctx.db.run('INSERT INTO query_owner VALUES(%s,%s)',(answer['id'],ctx.user['id']))
    ctx.db.audit(ctx.user,'query','자연어 업무 실행',answer['id'],{'action':scope.action,'status':status,'calls':len(rows)})
    return answer


def try_answer(ctx):
    body=ctx.body;q=body.get('question')
    if not isinstance(q,str) or not q.strip() or len(q)>2000 or body.get('task','auto')!='auto':return None
    action=intent.classify(q)
    follow=bool(re.match(r'\s*(그럼|그러면|그중|then\b|what about\b)',q,re.I))
    linked=bool((body.get('context') or {}).get('previousQueryId'))
    model_candidate=body.get('mode')=='llm' and bool(re.search(r'연료|탄소|기름|소모|consumption|fuel|intensity',q,re.I)) and bool(re.search(r'얼마|수치|통계|사용량|소비량|소모량|추이|비교|요약|합계',q))
    if re.search(r'표로|차트|그래프|\btable\b|\bchart\b|\bplot\b',q,re.I):return None
    if action=='unknown' and re.search(r'정의|뜻|번역|절차|방법|어떻게|문서만|규정|지침|매뉴얼|기준|한도|함유량|regulation|sulphur|sulfur',q,re.I):return None
    if action=='unknown' and not (model_candidate or linked or body.get('workflowInput') is not None):return None
    current=ctx.db.ships()
    prior=previous(ctx,current) if (body.get('context') or {}).get('previousQueryId') else None
    short_reply=bool(prior and prior[0]['status']=='needs_input' and len(q)<=160 and
        (re.search(r'\d{4}|참고|선택|^예$|^네$|문서',q) or any(norm(s['name'])==norm(q) for s in current)))
    scope_cue=bool(re.search(r'\d{4}|\d{1,2}월|오늘|어제|그제|이번|지난|최근|작년|올해|참고|동의|같은|다시|재조회',q) or any(norm(s['name']) in norm(q) for s in current))
    continuing=(follow and (action!='unknown' or scope_cue)) or short_reply or body.get('workflowInput') is not None
    if not continuing and action=='unknown' and not model_candidate:return None
    # Explanation/document-only requests must never inherit an unrelated operation plan.
    if action=='unknown' and re.search(r'정의|뜻|번역|절차|방법|어떻게|문서만',q):return None
    routing={'method':'rules','model_attempted':False};scope=Scope(action=action)
    if continuing:
        if not prior:return save(ctx,scope,'needs_input','현재 표시한 내 업무 답변에서 이어서 질문하거나 선박·기간을 다시 알려 주세요.',[],routing)
        scope=prior[1]
        if action!='unknown':scope.action=action
        action=scope.action
        if action=='selected_document':scope=Scope(action=action,document_ids=scope.document_ids,document_question=scope.document_question)
    try:
        if re.search(r'(?:다른|나머지)\s*(?:선박|배)',q) and not explicit_ships(q,current):
            scope.ships=[];scope.mappings={}
            return save(ctx,scope,'needs_input','비교할 선박을 등록 목록에서 지정해 주세요.',['ships'],routing,parent=prior[0]['id'] if continuing and prior else None)
        if scope.action=='selected_document' and body.get('workflowInput') is None:
            scope.document_question=q
        if re.search(r'(?:모든|전체)\s*(?:선박|배)|all\s+(?:ships|vessels)',q,re.I):
            raise ValueError('한 번에 조회할 선박을 최대 두 척으로 지정해 주세요.')
        defaults={int(p.start[:4]) for p in scope.periods} or set(scope.years)
        slots=intent.Intent(action='selected_document') if scope.action=='selected_document' else intent.extract_rules(q,default_year=next(iter(defaults)) if len(defaults)==1 else None)
        if body.get('mode')=='llm' and not continuing and action!='selected_document':
            routing['model_attempted']=True
            try:
                proposal=intent.plan_with_model(q,today=intent.local_today())
                if any(norm(s) not in norm(q) for s in proposal.ship_mentions):raise ValueError('Model invented ship mention')
                if proposal.action=='unknown':raise ValueError('Model requested no supported action')
                if action!='unknown' and proposal.action not in (action,'unknown'):raise ValueError('Model action conflicts with explicit request')
                if action=='unknown':scope.action=action=proposal.action
                slots.ship_mentions=proposal.ship_mentions
                routing['method']='llm'
            except (ValueError,KeyError,TypeError,ValidationError,httpx.HTTPError):routing['fallback']='RULES_AFTER_MODEL_FAILURE'
        selected=[] if scope.action=='selected_document' else explicit_ships(q,current,slots.ship_mentions)
        if scope.action=='unknown':return None
        if selected:
            scope.ships=[snapshot(s) for s in selected]
            scope.mappings={s.id:scope.mappings[s.id] for s in scope.ships if s.id in scope.mappings}
        elif not scope.ships and scope.action!='selected_document':
            selected_id=(body.get('context') or {}).get('ship')
            scope.ships=[snapshot(s) for s in current if s['id']==selected_id]
        if slots.years:scope.years=slots.years
        if scope.action in ('operations_summary','combined') and len(slots.years)>1 and not slots.periods and re.search(r'부터|까지|~|\bto\b',q,re.I) and not re.search(r'비교|compare',q,re.I):
            raise ValueError('366일을 넘는 합계 기간입니다. 날짜 범위를 좁히거나 연도별 비교로 질문해 주세요.')
        if slots.periods:scope.periods=slots.periods
        elif slots.years and scope.action in ('operations_summary','combined'):
            scope.periods=[intent.Period(start=f'{y}-01-01',end=f'{y}-12-31') for y in slots.years]
        if re.search(r'참고|reference',q,re.I):scope.reference_ack=True
        if prior and 'reference_ack' in prior[0]['workflow'].get('missing',[]) and q.strip() in ('네','예','동의','yes'):
            scope.reference_ack=True
        if body.get('workflowInput') is not None:
            require(prior is not None,'되묻기 응답의 소유자와 이전 답변을 확인해 주세요.')
            reply=Reply.model_validate(body['workflowInput'])
            if reply.ships is not None:
                require(len(set(reply.ships))==len(reply.ships),'선박을 중복 선택할 수 없습니다.')
                scope.ships=[snapshot(s) for s in current if s['id'] in reply.ships]
                require(len(scope.ships)==len(reply.ships),'등록 선박을 선택해 주세요.')
                scope.mappings={s.id:scope.mappings[s.id] for s in scope.ships if s.id in scope.mappings}
            for field in ('years','periods','document_ids','reference_ack'):
                if getattr(reply,field) is not None:setattr(scope,field,getattr(reply,field))
            scope=Scope.model_validate(scope.model_dump())
        if scope.action in ('operations_summary','combined') and not scope.periods:
            context=body.get('context') or {}
            if context.get('from') and context.get('to'):scope.periods=[intent.Period(start=context['from'],end=context['to'])]
        scope=Scope.model_validate(scope.model_dump())
        if any(type(y) is not int or not 1900<=y<=2100 for y in scope.years):raise ValueError('연도를 확인해 주세요.')
        if len(set(scope.years))!=len(scope.years) or len(set(scope.document_ids))!=len(scope.document_ids) or len({(p.start,p.end) for p in scope.periods})!=len(scope.periods):raise ValueError('연도·기간·문서를 중복 지정할 수 없습니다.')
        if scope.action not in ('mrv_reference','operations_summary','combined','selected_document'):raise ValueError('지원할 작업을 확인해 주세요.')
        require(all(ctx.db.can_read_document(ctx.user,d) for d in scope.document_ids),'선택 문서 열람 권한이 없습니다.','FORBIDDEN',403)
        if re.search(r'삭제|수정|등록|저장|DROP|UPDATE|INSERT',q,re.I):raise ValueError('이 질문 경로는 조회·계산만 지원합니다. 변경은 해당 관리 화면을 사용해 주세요.')
        if re.search(r'공식\s*CII|CII\s*등급|official CII|rating',q,re.I) and not re.search(r'(?:말고|대신|아닌|not).*?(?:참고|reference)',q,re.I):
            scope.reference_ack=False
        missing=[]
        if scope.action!='selected_document' and not scope.ships:missing.append('ships')
        if scope.action in ('mrv_reference','combined') and not scope.years:missing.append('years')
        if scope.action in ('mrv_reference','combined') and not scope.reference_ack:missing.append('reference_ack')
        if scope.action in ('operations_summary','combined') and not scope.periods:missing.append('periods')
        if scope.action=='selected_document' and not scope.document_ids:missing.append('document_ids')
        if missing:return save(ctx,scope,'needs_input','필요한 조건을 알려 주면 현재 자료로 다시 조회합니다. MRV 계산은 참고값이며 공식 CII·등급을 제공하지 않습니다.',missing,routing,parent=prior[0]['id'] if continuing and prior else None)
        calls=len(scope.ships)*((len(scope.years) if scope.action in ('mrv_reference','combined') else 0)+(len(scope.periods) if scope.action in ('operations_summary','combined') else 0))
        if calls>4:raise ValueError('한 번에 최대 4회 조회할 수 있습니다. 선박·연도·기간 범위를 좁혀 주세요.')
        rows,evidence,statements,warnings=run_tools(ctx,scope)
        status='partial' if any(r['status'] in ('blocked','unavailable','no_data') for r in rows) else 'completed'
        if scope.action=='selected_document' and not statements:status='insufficient_evidence'
        notice='선택 문서 안에서 답변 근거를 찾지 못했습니다.' if status=='insufficient_evidence' else '검증한 범위로 기존 도구를 실행했습니다. 자료 유형·단위·계산 불가 사유를 함께 확인하세요.'
        return save(ctx,scope,status,notice,[],routing,
            rows=rows,evidence=evidence,statements=statements,warnings=warnings,parent=prior[0]['id'] if continuing and prior else None)
    except (ValueError,ValidationError) as exc:
        # A failed assignment (for example, three operation periods) must never
        # persist an invalid continuation scope. Discard an invalid scope.
        try:scope=Scope.model_validate(scope.model_dump())
        except (ValueError,ValidationError):scope=Scope(action=action)
        return save(ctx,scope,'needs_input',str(exc)[:300] if not isinstance(exc,ValidationError) else '선박·기간·연도 입력 형식을 확인해 주세요.',[],routing)
