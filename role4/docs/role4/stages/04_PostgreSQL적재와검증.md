> 이 문서는 기존 통합 앱에서 수행한 단계별 작업 기록입니다. 현재 역할4 전용 배포판의 실행·인증 방법과 포함 범위는 루트 README를 따릅니다.

# 4단계 | PostgreSQL 적재와 검증

## 실제 DB 위치

설계 파일과 전처리 산출물은 OneDrive 저장소에 있고 실제 조회는 PC에서 실행 중인 PostgreSQL이 담당합니다. 연결 주소는 127.0.0.1:55432, 데이터베이스는 haedap, 앱 DB 계정은 haedap_app입니다. 데이터는 role4 스키마에 있습니다. 비밀번호는 .env.local에 있으며 과제 PDF와 공유 폴더에 복사하지 않습니다.

기존 public 앱 테이블을 바꾸지 않고 별도 스키마를 적재했습니다. 적재 입력은 data/role4/2026-09-30-v2의 전처리 CSV 6개이며 raw_records.jsonl은 원본 보존용으로 별도 유지합니다. PostgreSQL 데이터 디렉터리는 저장소의 data/postgres입니다.

## 적재 스크립트의 흐름

scripts/load-role4.ps1은 .env.local의 DATABASE_URL을 읽고 로컬 호스트인지 확인합니다. role4 스키마가 이미 존재하면 덮어쓰지 않고 중단합니다. 원본 파일과 전처리 CSV를 다시 만들거나 변경하지 않습니다.

단일 트랜잭션 안에서 DDL 실행, CSV 복사, verify_load.sql 검사를 순서대로 수행합니다. 출처·선박을 먼저 넣고 합성 항차, 실제 보고서, 합성 일별 기록, 품질 이슈 순으로 넣어 외래키 의존성을 맞췄습니다. 검증에 성공할 때만 COMMIT하고 실패하면 전체 적재를 롤백합니다.

CSV는 UTF-8, 헤더 포함, 빈 셀은 NULL로 읽습니다. 최초 적재 시 한글 절대경로 처리 오류가 발생해 롤백됐고, 입력 디렉터리에서 상대 파일명을 읽는 방식으로 수정한 뒤 정상 적재했습니다. 이는 DB_LOAD_RESULT.md에 기록된 이전 작업 결과입니다.

## 적재된 행 수

- source_files: 6행
- vessels: 25,252행
- synthetic_voyages: 238행
- annual_reports: 80,552행
- synthetic_noon: 4,380행
- quality_issues: 26,249행

real_annual_query는 과거 연간 61,860행과 Full 17,172행을 합친 79,032행입니다. Partial 1,520행은 REVIEW 상태로 보존하고 기본 조회에서 제외합니다. development_noon_query는 4,380행이며 거리 0인 557행도 남아 있습니다.

## 실제 검증 항목

verify_load.sql은 선정된 입력 버전의 행 수를 기준으로 검사합니다. 실제 보고서는 실제 선박·실제 출처만 참조하는지, 합성 Noon은 합성 선박·합성 출처를 참조하는지 확인합니다. 일별 기록의 선박과 해당 항차의 선박이 같은지도 검사합니다. 품질 이슈가 가리키는 record_id가 연간 또는 Noon에 존재하는지 확인합니다.

이 검사는 적재 구조와 선정 자료의 일관성을 확인합니다. 원본 자료의 사실성, CII 계산 가능성, 세계 전체 배출량을 보증하지 않습니다. 선정 MRV 합계를 전 세계 배출량으로 해석하거나 연도마다 같은 선박 집단이라고 가정하지 않습니다.

## 사용자가 직접 켜고 조회하는 방법

저장소 루트에서 .venv/Scripts/python.exe -m service.manage local-db를 실행하면 로컬 DB를 시작합니다. 이미 실행 중이면 유지합니다. pgAdmin에는 서버 이름을 임의로 정하고 Host 127.0.0.1, Port 55432, Maintenance database haedap, Username haedap_app을 입력합니다. 서버 등록은 연결 정보 저장이며 자동 시작 설정과는 별개입니다.

haedap 우클릭 후 Query Tool에서 SELECT * FROM role4.real_annual_query LIMIT 20;을 실행하면 조회할 수 있습니다. 테이블과 적재 SQL을 다시 실행할 필요는 없습니다. 자료 버전이 바뀌면 기존 데이터를 무조건 덮어쓰기보다 별도 버전과 이관 절차를 먼저 마련해야 합니다.

근거: scripts/load-role4.ps1, docs/role4/verify_load.sql, docs/role4/DB_LOAD_RESULT.md, service/manage.py. 기존 적재 검증은 후속 조회 API 작업에서도 읽기 전용 트랜잭션으로 재실행해 통과했습니다.
