# 역할 4 읽기 전용 조회 Tool 계약 v1

2026-09-30. 구현된 API 기준 계약이며 팀의 Agent 연동 승인을 의미하지 않습니다.

## 실행 및 접근

현재 역할4 전용 API는 `python -m uvicorn service.app:create_app --factory --host 127.0.0.1 --port 8000`으로 실행합니다. 모든 Tool 요청에 `Authorization: Bearer <ROLE4_API_TOKEN>`이 필요합니다. 토큰은 서버의 `.env.local`에 설정하며 로그인 세션·CSRF·기존 public 앱 테이블은 사용하지 않습니다. 실행 예제는 루트 README를 참고하세요.

내부 Python 진입점은 `service.role4.query(engine, body)`입니다. 팀 앱에 직접 연결할 때는 호출자가 사용자 권한을 검사해야 합니다. `/api/role4/ask`는 고정 scope의 규칙 기반 조회 도우미이며 LLM 연결은 포함하지 않습니다.

## 입력

실제 보고기간 MRV:

```json
{"dataset":"real_annual","year_start":2020,"year_end":2025,"limit":20,"offset":0}
```

개발용 합성 일별 Noon:

```json
{"dataset":"synthetic_noon","start":"2025-01-01","end":"2025-01-31","vessel_id":"SYN:SIM-BULK-01","limit":20}
```

| 필드 | 규칙 |
|---|---|
| dataset | real_annual 또는 synthetic_noon, 필수 |
| year_start / year_end | MRV 필수 정수, 1900~2100, 종료 ≥ 시작, 차이 ≤ 10년 |
| start / end | Noon 필수 ISO 날짜, 종료 ≥ 시작, 차이 ≤ 366일 |
| vessel_id | 선택. MRV는 REAL:IMO:7자리, Noon은 SYN:원본ID |
| voyage_id | Noon에만 선택. SYN:원본항차ID |
| limit | 정수 1~200, 기본 50 |
| offset | 정수 0~100000, 기본 0 |

기간 양 끝을 포함합니다. 모든 추가 필드·임의 SQL·정렬·테이블명은 거절합니다. 실제/합성 키 혼용도 거절합니다. 존재하지 않는 유효 형식의 키 또는 일치하지 않는 선박·항차 조합은 빈 결과입니다.

## 출력

- `contract_version`: 1.0, `dataset`, `data_origin`: REAL 또는 SYNTHETIC.
- `granularity`: reporting_period 또는 daily. `filters`는 적용한 입력 조건.
- `rows`: 해당 승인 뷰의 원본 컬럼 전체와 `dataset_id`, `source_filename`, `source_sha256`, `source_url`, `data_origin`. record_id, source_id, 원본 행 번호, provenance_json, quality_status를 유지합니다.
- `units`: 수치 필드별 단위. MRV co2_t는 원본 보고 CO2이며 재계산이나 CO2eq가 아닙니다.
- `numeric_encoding`: decimal_string. PostgreSQL numeric을 십진 문자열로 직렬화합니다. 정수형 연도·행 번호는 JSON 숫자, 결측은 null, 원본 0은 "0" 등 십진 표현, 날짜·시각은 ISO 문자열입니다. provenance_json 내부 원본 메타데이터 타입은 유지합니다.
- `total`: 페이지가 아닌 필터에 일치하는 전체 행 수. `limit`, `offset`, `has_more`, `next_offset`으로 페이지 이동합니다. 빈 결과에도 total과 경고를 반환합니다.
- `warnings`: 전처리 VALID의 의미, 실제/합성 구분, 역산 거리 한계, 공식 CII 미검증 경고.

MRV는 reporting_year/vessel_id/record_id, Noon은 report_date/vessel_id/record_id 순입니다. 총수와 행 조회는 같은 반복 읽기 스냅샷에서 수행합니다. 서로 다른 페이지 요청 사이에 데이터를 다시 적재하면 결과가 바뀔 수 있습니다.

## DB 및 오류

`role4.real_annual_query`와 `role4.development_noon_query`만 조회하며 출처 테이블을 조인합니다. MRV Partial 및 집계 부적격 레코드와 Noon 비VALID를 제외합니다. 연간 자료를 일별로 분해하거나 실제와 합성을 조인하지 않습니다.

SQL 식별자는 서버 고정값, 입력은 바인딩 매개변수입니다. PostgreSQL READ ONLY / REPEATABLE READ 트랜잭션, SQL 문장당 5초 제한을 적용합니다. 조회 성공 이벤트는 서버 logger(role4.audit)에 기록합니다. 영구 감사 저장은 팀 앱 연동 범위입니다. role4·원본 파일은 수정하지 않습니다.

| HTTP | 의미 |
|---|---|
| 200 | 정상 조회 또는 빈 결과 |
| 401 | Bearer 토큰 누락 |
| 403 | API 토큰 불일치 |
| 422 | 입력 계약 위반 |
| 503 | PostgreSQL 미사용, 연결·스키마·SQL 실행 오류 또는 시간 초과 |

DB 예외의 SQL·연결 문자열은 응답에 노출하지 않습니다. 자료 이용조건, 실제 DWT와 공식 계산 계수 보강은 별도 과제입니다.

## 검증

`python -m pytest -q`로 계약·접근권한·기존 서비스 회귀를 실행합니다. `ROLE4_TEST_DATABASE_URL`을 기존 적재 PostgreSQL에 설정하면 실제 데이터 비교 테스트도 실행합니다. 실제 DB는 조회만 하며 테스트 로그인·감사는 임시 SQLite에서 처리합니다. 미설정 시 PostgreSQL 테스트 2개는 skip입니다.

2026-09-30 실행 결과: PostgreSQL 테스트를 활성화한 전체 서비스 48개 통과. 이어서 DB 오류 메시지 보호 및 실제 트랜잭션 설정·Noon 전체 페이지 검증을 보강한 역할 4 테스트 21개 통과. Starlette TestClient의 httpx 사용 관련 폐기 예정 경고 1건이 있으며 실패는 없습니다.

실제 DB에서 MRV 79,032행, Noon 4,380행과 거리 0인 557행을 확인했습니다. 페이지 중복 없음, 날짜·선박·항차 필터, 빈 결과, 원본 numeric 정밀도·NULL·출처 보존, READ ONLY/REPEATABLE READ/5초 제한을 검증했습니다. 기존 `verify_load.sql` 적재 검증도 읽기 전용으로 재실행하여 통과했습니다. 생성기의 데이터 계약·DDL·사전 출력이 저장된 파일과 일치합니다. 실제 LLM 추론·화면 연결 검증은 이 범위에 포함하지 않습니다.
