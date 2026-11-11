"""Run one validated model tool call with the existing executors (ADR 0024).

Model arguments are wording, not identifiers: ships, documents and ports are
resolved here against registered records, dates by the existing date parser.
"""
import json
import re
from uuid import uuid4

from psycopg.types.json import Jsonb
from pydantic import ValidationError

from . import dataset_status, navigation_query, question_intent as intent, question_workflows as flow
from .validation import utc_now

ACTIONS = {'summarize_operations': 'operations_summary', 'calculate_mrv_reference': 'mrv_reference',
           'calculate_operations_and_mrv': 'combined', 'ask_selected_documents': 'selected_document'}
CLARIFY = {'task': '확인할 작업', 'ships': '선박', 'periods': '기간', 'years': '보고 연도', 'documents': '문서', 'ports': '항구'}
DECLINE = {
    'realtime_position': '실시간 선박 위치·추적은 지원하지 않습니다. 등록된 AIS 수집본의 현황은 확인할 수 있습니다.',
    'weather': '기상·해상 상태 정보는 제공하지 않습니다.',
    'forecast': '미래 수치 예측은 제공하지 않습니다. 기록된 실적의 합계·비교는 확인할 수 있습니다.',
    'data_change': '질문으로 자료를 등록·수정·삭제할 수 없습니다. 해당 관리 화면을 사용해 주세요.',
    'entry_approval': '실제 입항 가능·불가 판정은 제공하지 않습니다. 공개 선석 제한값과의 참고 비교는 확인할 수 있습니다.',
    'off_topic': '해사 업무와 관련된 질문만 지원합니다.',
}


class ArgumentError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def compact(value):
    return re.sub(r'\s+', '', str(value or '').casefold())


def mentions(call):
    args = call.args
    values = []
    for field in ('ship_mentions', 'port_mentions', 'document_mentions'):
        values += list(getattr(args, field, []) or [])
    for field in ('ship_mention', 'berth_mention'):
        values.append(getattr(args, field, '') or '')
    return [v for v in values if v.strip()]


def source_text(question, summary=None):
    return compact(question) + compact(json.dumps(summary or {}, ensure_ascii=False))


def check_mentions(call, question, summary=None):
    """Every ship, port, berth or document name the model passes must be wording the user actually used."""
    source = source_text(question, summary)
    if any(compact(value) not in source for value in mentions(call)):
        raise ArgumentError('MODEL_ARGUMENT_NOT_IN_QUESTION')


def period_source(call, question, summary=None):
    """Return (text for the existing date parser, origin).

    The model's period wording is used only when the user actually wrote it. A paraphrase
    (e.g. "지난달" -> "마지막 달") falls back to parsing the original question.
    """
    text = (getattr(call.args, 'period_text', '') or '').strip()
    if not text:
        return '', 'none'
    if compact(text) in source_text(question, summary):
        return text, 'model'
    return question, 'question'


def resolve_ship(mention, question, ships):
    """Complete a shortened ship name only when exactly one registered ship's full name is in the question.

    Observed 2026-11-12: "가상 선박 해답 2호 · 왕복 시나리오" came back as "가상 선박 해답 2호".
    """
    value = compact(mention)
    if not value or any(compact(s['name']) == value or compact(s.get('imo')) == value.removeprefix('imo')
                        for s in ships):
        return mention
    found = [s for s in ships if value in compact(s['name']) and compact(s['name']) in compact(question)]
    return found[0]['name'] if len(found) == 1 else mention


def save(ctx, fields):
    q = ctx.body['question']
    language = ctx.body.get('language', 'auto')
    if language == 'auto':
        language = 'ko' if re.search(r'[가-힣]', q) else 'en'
    answer = {'id': str(uuid4()), 'question': q, 'task': 'tool', 'language': language, 'generation': 'tool',
              'status': 'completed', 'notice': '', 'statements': [], 'evidence': [], 'toolRuns': [], 'warnings': [],
              'reportSuggested': False, **fields}
    ctx.db.run('INSERT INTO queries VALUES(%s,%s,%s,%s)', (answer['id'], q, Jsonb(answer), utc_now()))
    ctx.db.run('INSERT INTO query_owner VALUES(%s,%s)', (answer['id'], ctx.user['id']))
    ctx.db.audit(ctx.user, 'query', '질의', answer['id'], {'question': q, 'task': answer['task']})
    return answer


def clarification(ctx, code, notice):
    return save(ctx, {'task': 'clarification', 'status': 'needs_input', 'notice': notice, 'warnings': [code]})


def workflow(ctx, action, args, period=None):
    q = ctx.body['question']
    current = ctx.db.ships()
    prior = flow.previous(ctx, current) if (ctx.body.get('context') or {}).get('previousQueryId') else None
    parent = prior[0]['id'] if prior else None
    routing = {'method': 'model_tools', 'model_attempted': True}
    scope = flow.Scope(action=action)
    try:
        if action == 'selected_document':
            documents = ctx.db.documents(ctx.user)
            ids = []
            for mention in args.document_mentions:
                found = [d['id'] for d in documents if compact(d['title']) == compact(mention)]
                if len(found) != 1:
                    return flow.save(ctx, scope, 'needs_input', '', ['document_ids'], routing, parent=parent)
                ids.append(found[0])
            scope.document_ids = list(dict.fromkeys(ids))
            scope.document_question = q
            return flow.execute(ctx, scope, routing, parent)
        text = (args.period_text if period is None else period).strip()
        years, periods = intent.date_slots(text, today=intent.local_today()) if text else ([], [])
        if years:
            scope.years = years
        if periods:
            scope.periods = periods
        elif years and action in ('operations_summary', 'combined'):
            scope.periods = [intent.Period(start=f'{y}-01-01', end=f'{y}-12-31') for y in years]
        names = [resolve_ship(m, q, current) for m in args.ship_mentions]
        ships = flow.explicit_ships(' '.join(names), current, names) if names else []
        if ships:
            scope.ships = [flow.snapshot(s) for s in ships]
        else:
            selected = (ctx.body.get('context') or {}).get('ship')
            scope.ships = [flow.snapshot(s) for s in current if s['id'] == selected]
        if action == 'operations_summary' and args.display != 'text':
            scope.presentation_question = q
        if action in ('mrv_reference', 'combined'):
            earlier = prior[1] if prior and prior[1].action in ('mrv_reference', 'combined') else None
            prompted = bool(earlier and prior[0]['workflow'].get('missing', [None])[:1] == ['reference_ack'])
            # Consent comes from the user's reply to an explicit prompt, or a consent already given in this thread.
            scope.reference_ack = bool(args.accept_reference and prompted) or bool(earlier and earlier.reference_ack)
        return flow.execute(ctx, scope, routing, parent)
    except (ValueError, ValidationError) as exc:
        try:
            scope = flow.Scope.model_validate(scope.model_dump())
        except (ValueError, ValidationError):
            scope = flow.Scope(action=action)
        notice = str(exc)[:300] if not isinstance(exc, ValidationError) else '선박·기간·연도 입력 형식을 확인해 주세요.'
        return flow.save(ctx, scope, 'needs_input', notice, flow.missing_fields(scope), routing, parent=parent)


def port_comparison(ctx, args):
    ship = resolve_ship(args.ship_mention, ctx.body['question'], ctx.db.ships()) if args.ship_mention else ''
    conditions = {'filters': [{'kind': f.dimension, 'op': f.op, 'value_m': '%g' % f.value_m} for f in args.filters],
                  'sort': {'kind': args.sort.dimension, 'direction': args.sort.direction} if args.sort else None,
                  'status': args.status_filter}
    ports = ' '.join([*args.port_mentions, *([f'선석 {args.berth_mention}'] if args.berth_mention else [])])
    return navigation_query.try_answer(ctx, planned={'ship_text': ship, 'ports_text': ports,
                                                    'conditions': conditions})


def run(ctx, call, period=None):
    name, args = call.tool.name, call.args
    if name in ACTIONS:
        return workflow(ctx, ACTIONS[name], args, period)
    if name == 'get_dataset_status':
        names = [resolve_ship(m, ctx.body['question'], ctx.db.ships()) for m in args.ship_mentions]
        scope_text = ' '.join([args.period_text if period is None else period, *names]).strip()
        fields = dataset_status.answer(ctx, list(args.datasets), scope_text=scope_text)
        return save(ctx, {'task': 'data_status', **fields})
    if name == 'get_ais_catalog_status':
        names = [resolve_ship(m, ctx.body['question'], ctx.db.ships()) for m in args.ship_mentions]
        return navigation_query.catalog_status_answer(ctx, ctx.body['question'], scope_text=' '.join(names))
    if name == 'compare_port_conditions':
        return port_comparison(ctx, args)
    if name == 'calculate_emissions':
        result = ctx.db.calculate_emissions({'fuel': args.fuel_t, 'factor': args.factor, 'dwt': args.dwt,
                                             'distance': args.distance_nm})
        return save(ctx, {'toolRuns': [result], 'notice': '질문에 주어진 값으로 계산했습니다. 공식 CII 등급이 아닙니다.'})
    if name == 'voyage_time':
        result = ctx.db.voyage_time({'start': args.start, 'end': args.end, 'before': args.start_offset_min,
                                     'after': args.end_offset_min})
        return save(ctx, {'toolRuns': [result], 'notice': '질문에 주어진 UTC 시각과 시차로 계산했습니다.'})
    if name == 'request_clarification':
        labels = '·'.join(CLARIFY[m] for m in args.missing)
        return clarification(ctx, 'QUESTION_SCOPE_REQUIRED', f'질문을 처리하려면 {labels}을(를) 알려 주세요.')
    if name == 'decline_request':
        return save(ctx, {'task': 'unsupported', 'status': 'unsupported', 'notice': DECLINE[args.reason],
                          'warnings': ['UNSUPPORTED_REQUEST']})
    raise ArgumentError('MODEL_UNKNOWN_TOOL')
