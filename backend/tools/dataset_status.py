"""Read-only inventory of prepared maritime records, never model-authored SQL."""
import re
from sqlalchemy import bindparam, text
from .port_reference import valid_imo


TABLES = {
    'mrv': ('annual_reports', 'reporting_year', "quality_status='VALID' AND aggregate_eligible AND report_type<>'PARTIAL'"),
    'noon': ('synthetic_noon', 'report_date', "quality_status='VALID'"),
    'dwt': ('capacity_candidates', None, "candidate_dwt_t IS NOT NULL AND capacity_status<>'CONFLICT_OVER_5_PERCENT'"),
}


def read_status(engine, dataset, *, vessel_id=None, years=()):
    if dataset not in TABLES or engine.dialect.name != 'postgresql':
        raise ValueError('Unsupported inventory source')
    if vessel_id is not None:
        # Identities are resolved by the app; reject arbitrary SQL fragments too.
        if not re.fullmatch(r'REAL:IMO:[0-9]{7}',vessel_id) or not valid_imo(vessel_id[-7:]):
            raise ValueError('Invalid inventory identity')
    if len(years)>3 or any(type(y) is not int or not 1900<=y<=2100 for y in years):
        raise ValueError('Invalid inventory years')
    table,period,eligible=TABLES[dataset]
    if dataset=='dwt' and years or dataset=='noon' and vessel_id:
        return {'status':'unsupported_scope','notice':'이 자료는 해당 선박/연도 조건으로 해석하지 않습니다.'}
    clauses=[];params={}
    if vessel_id:
        clauses.append('vessel_id=:vessel');params['vessel']=vessel_id
    if years:
        clauses.append(('reporting_year' if dataset=='mrv' else 'EXTRACT(YEAR FROM report_date)')+' IN :years')
        params['years']=list(years)
    where=' WHERE '+' AND '.join(clauses) if clauses else ''
    def statement(sql):
        query=text(sql)
        return query.bindparams(bindparam('years',expanding=True)) if years else query
    with engine.connect() as conn, conn.begin():
        conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        conn.execute(text("SET LOCAL statement_timeout='5s'"))
        dates=f', min({period}) AS first_period, max({period}) AS last_period' if period else ''
        row=dict(conn.execute(statement(f'''SELECT count(*) AS row_count,
            count(DISTINCT vessel_id) AS vessel_count, count(*) FILTER (WHERE {eligible}) AS eligible_count
            {dates} FROM maritime_data.{table}{where}'''),params).mappings().one())
        if dataset!='dwt':
            sources=conn.execute(statement(f'''SELECT s.dataset_id, s.source_url, count(*) AS row_count
                FROM maritime_data.source_files s JOIN maritime_data.{table} r USING(source_id)
                {where} GROUP BY s.dataset_id,s.source_url ORDER BY s.dataset_id,s.source_url LIMIT 8'''),params).mappings().all()
            row['sources']=[dict(s) for s in sources]
        else:
            row['sources']=([{'dataset_id':'Wikidata','source_url':'https://www.wikidata.org/'},
                             {'dataset_id':'MarineVessels','source_url':'https://github.com/rich-iannone/MarineVessels'}]
                            if row['row_count'] else [])
        for key in ('first_period','last_period'):
            if row.get(key) is not None:row[key]=str(row[key])
        return {**row,'status':'available' if row['row_count'] else 'empty',
            'notice':{'mrv':'연간 보고의 등록 건수입니다. 부분 보고·집계 부적격을 포함하며 공식 CII 산정 가능 건수가 아닙니다.',
                      'noon':'개발용 합성 일별 자료이며 실제 선박 운항 자료가 아닙니다.',
                      'dwt':'미검증 공개 용량 후보입니다. 후보 유효 건수는 법정·해당 연도 검증 건수가 아닙니다.'}[dataset]}
