"""Generate PostgreSQL DDL and a machine-readable dictionary from the pipeline contract."""
import argparse,json
from pathlib import Path
from prepare_maritime_data import FIELDS

TITLES={'source_files':'원본 파일·출처','vessels':'실제·합성 선박 식별','annual_reports':'실제 MRV 보고기간 집계','synthetic_noon':'개발용 합성 일별 기록','synthetic_voyages':'개발용 합성 항차','quality_issues':'전처리 품질 이슈'}

def generate(out):
    out.mkdir(parents=True,exist_ok=True)
    sql=['-- Maritime data v1. Does not modify the existing public app schema.',
         '-- Review before application. Import only validated rows; this file does not load CSV.',
         'BEGIN;','CREATE SCHEMA IF NOT EXISTS maritime_data;']
    for name in ['source_files','vessels','synthetic_voyages','annual_reports','synthetic_noon','quality_issues']:
        cols=[]
        for field,typ,rule,meaning in FIELDS[name]:
            col=f'  {field} {typ}'
            if rule=='PK':col+=' PRIMARY KEY'
            elif rule.startswith('FK '):
                target=rule.split()[1];key=FIELDS[target][0][0];col+=f' NOT NULL REFERENCES maritime_data.{target}({key}) ON DELETE RESTRICT'
            elif rule=='required':col+=' NOT NULL'
            cols.append(col)
        if name in {'annual_reports','synthetic_noon'}:
            cols.append("  CHECK (quality_status IN ('VALID','REVIEW','REJECT'))")
            cols.append("  CHECK (vessel_id LIKE '"+('REAL:IMO:%' if name=='annual_reports' else 'SYN:%')+"')")
        if name=='annual_reports':
            cols.extend(["  CHECK (report_type IN ('FULL','PARTIAL','ARCHIVE_ANNUAL'))","  CHECK (NOT aggregate_eligible OR (quality_status = 'VALID' AND report_type <> 'PARTIAL'))","  CHECK (period_end >= period_start)"])
        if name=='synthetic_noon':
            cols.extend(['  CHECK (dwt_t > 0 AND distance_nm >= 0 AND fuel_t >= 0 AND speed_kn >= 0)',
                         '  CHECK (engine_hours BETWEEN 0 AND 24)',
                         "  CHECK (observed_at_utc > period_start_utc AND observed_at_utc <= period_start_utc + interval '24 hours')"])
        sql.append(f'CREATE TABLE maritime_data.{name} (\n'+',\n'.join(cols)+'\n);')
    sql += ['CREATE INDEX annual_vessel_year ON maritime_data.annual_reports(vessel_id, reporting_year);',
            'CREATE INDEX noon_vessel_date ON maritime_data.synthetic_noon(vessel_id, report_date);',
            'CREATE INDEX noon_voyage ON maritime_data.synthetic_noon(voyage_id);',
            "CREATE VIEW maritime_data.real_annual_query AS SELECT * FROM maritime_data.annual_reports WHERE aggregate_eligible;",
            "CREATE VIEW maritime_data.development_noon_query AS SELECT * FROM maritime_data.synthetic_noon WHERE quality_status='VALID';",'COMMIT;']
    (out/'schema.sql').write_text('\n\n'.join(sql)+'\n',encoding='utf-8')
    # ERD and field explanations are maintained in docs/data-model.md.
    payload={'tables':TITLES,'fields':FIELDS}
    (out/'dictionary.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parents[1] / 'schema')
    args = parser.parse_args()
    generate(args.out)
