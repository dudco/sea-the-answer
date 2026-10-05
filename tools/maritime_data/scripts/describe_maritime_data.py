"""Generate matching PostgreSQL DDL, dictionary and ERD from the pipeline contract."""
import argparse,json
from pathlib import Path
from prepare_maritime_data import FIELDS

TITLES={'source_files':'원본 파일·출처','vessels':'실제·합성 선박 식별','annual_reports':'실제 MRV 보고기간 집계','synthetic_noon':'개발용 합성 일별 기록','synthetic_voyages':'개발용 합성 항차','quality_issues':'전처리 품질 이슈'}

def generate(out, docs):
    out.mkdir(parents=True,exist_ok=True)
    docs.mkdir(parents=True,exist_ok=True)
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
    md=['# 해사 데이터 계약 v1','', '2026-09-30. 원본 컬럼을 확인한 구현 기준안입니다. 기존 전사 19개 테이블 정의서를 대체하지 않습니다. 공식 계수·항구 매핑·실제 DWT 보강은 미확정입니다. 조회·계산 계약은 `API.md`, 데이터 확보 방법은 `DATA_ACCESS.md`를 확인하세요.','',
        '## 용도와 경계','',
        '- DS-001/005: 실제 보고기간 집계 조회. 연간 자료를 일별·항차별로 분해하지 않습니다.',
        '- DS-006: 개발용으로 선정. 가상 표식을 유지한 채 일별 조회·항차 집계·Tool 테스트에 사용합니다.',
        '- DS-003: 항구 기준정보로 보존. 항구명만 보고 자동 조인하지 않습니다.',
        '- DS-004: 컬럼 설계 참고. 운항 관측 데이터에 포함하지 않습니다.',
        '- DS-002: 마스킹 AIS 참고. 좌표 스케일을 추정 변환하거나 실제 선박과 연결하지 않습니다.','',
        '## 키·결측·중복 정책','',
        '- 실제 선박 키 `REAL:IMO:번호`, 가상 선박 키 `SYN:원본ID`로 충돌을 방지합니다. 실제 IMO 형식·체크섬을 검사하고 발급 여부는 검증하지 않습니다.',
        '- 원본 파일 SHA256, 시트, 행으로 출처를 추적합니다. CSV 행 번호는 줄바꿈을 포함하는 물리 행이 아닌 논리 레코드 번호입니다.',
        '- `raw_records.jsonl`은 모든 원본 관측 레코드와 안정적인 record_id를 보존합니다. XLSX 중복 헤더는 순서 배열로 보존합니다.',
        '- 빈칸·N/A·원본 나눗셈 오류·음수·비정상 숫자를 구분합니다. 빈 CSV 셀은 DB NULL이며 0은 실제 원본 0입니다.',
        '- 역사 MRV 운항시간은 명시적 원본 별칭을 확인합니다. 별칭 간 값이 다르면 선택하지 않고 결측·충돌로 남깁니다.',
        '- 역산 거리는 추정치이며 원본 총량과 거리당 지표의 범위 일치가 검증되지 않았습니다. 공식 계산이나 독립 검증의 정답으로 사용하지 않습니다.',
        '- Partial 보고서는 원본별 보존하고 Full과 합산하지 않습니다. 선박·연도·보고유형 중복의 모든 행을 REVIEW로 처리합니다.',
        '- 가상 항차 첫/마지막 보고일을 실제 입출항 시각으로 바꾸지 않습니다. 2025 첫 Noon 구간은 2024-12-31에 시작할 수 있습니다.',
        '- VALID는 지정 전처리 규칙 통과일 뿐 원본 사실성·규정 적합성의 인증이 아닙니다. REVIEW/REJECT는 기본 집계에서 제외합니다.','',
        '## ERD','', '```mermaid','erDiagram',
        '  source_files ||--o{ annual_reports : provenance',
        '  source_files ||--o{ synthetic_noon : provenance',
        '  source_files ||--o{ quality_issues : records',
        '  vessels ||--o{ annual_reports : real',
        '  vessels ||--o{ synthetic_voyages : synthetic',
        '  vessels ||--o{ synthetic_noon : synthetic',
        '  synthetic_voyages ||--o{ synthetic_noon : contains','```','',
        '`quality_issues.record_id`는 연간/일별 레코드 중 하나를 가리키는 논리 참조입니다. SQL의 외래키는 source_id에만 적용합니다. 원본 조회는 record_id 및 출처 키로 수행합니다.','',
        '## 컬럼 정의','']
    for name,fields in FIELDS.items():
        md += [f'### {name} — {TITLES[name]}','','| 컬럼 | PostgreSQL 타입 | 제약 | 의미·단위 |','|---|---|---|---|']
        md += [f'| {field} | {typ} | {rule} | {meaning} |' for field,typ,rule,meaning in fields]
        md.append('')
    md += ['## 적재 전 확인','',
           'DDL은 별도 `maritime_data` 스키마에만 새 테이블을 생성하도록 작성했습니다. DDL 생성만으로 CSV를 적재하지는 않습니다. 기존 앱 화면·Agent는 이를 자동 조회하지 않습니다. 관리자 조회 API 계약과 적재 결과는 별도 문서를 확인하세요.',
           '정상·검토 레코드와 거절 레코드의 적재 경로를 나누고 필수값이 없는 REJECT는 원본/이슈 저장소에만 보관하세요. INSERT 시 숫자·날짜를 파싱하고 JSON 필드는 JSONB로 적재합니다. 원본 판정 충족률을 공식 CII 준비율로 사용하지 않습니다.','']
    (docs/'DATA_CONTRACT.md').write_text('\n'.join(md),encoding='utf-8')
    payload={'tables':TITLES,'fields':FIELDS}
    (out/'dictionary.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path(__file__).resolve().parents[1]/'schema');p.add_argument('--docs',type=Path,default=Path(__file__).resolve().parents[3]/'docs/maritime-data');a=p.parse_args();generate(a.out,a.docs)
