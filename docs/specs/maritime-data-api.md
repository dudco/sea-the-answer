# 해사 데이터 API 계약

- 상태: 구현됨
- 작성: 역할4 · 2026-10-08 (기존 2026-10-05 독립 Tool 계약의 문서 위치 정리)
- 관련: [데이터 명세](maritime-data.md), [운영 안내](../user-guide.md#10-해사-데이터-tool-선택), [모듈 경계 ADR 제안](../adr/0008-maritime-data-tool-boundary.md), [정리 계획](../plans/2026-10-08-maritime-data-docs-alignment.md)

## 목적과 범위

PostgreSQL 해사 데이터를 읽는 독립 Python Tool의 요청·응답·오류·산술 범위를 정의합니다. 내부 API(현재 Node)의 기존 [앱 API](api.md)와 별도 서비스이며, 팀 앱의 HTTP 어댑터·선박 ID 매핑·접근 정책·영구 감사 기록 및 LLM 연결은 아직 구현되지 않았습니다.

| 메서드·경로 | 역할 | Bearer 토큰 |
|---|---|---|
| `GET /api/health` | 프로세스 상태만 확인, `database_checked=false` | 불필요 |
| `POST /api/maritime-data/query` | 승인 뷰의 조건 조회 | 필요 |
| `GET /api/maritime-data/factors` | 고정 버전의 계수 카탈로그 | 필요 |
| `POST /api/maritime-data/calculate` | CO₂ 산술 및 입력 준비 상태 | 필요 |
| `POST /api/maritime-data/ask` | 고정 scope의 규칙 기반 조회 도우미 | 필요 |

필드 계약과 오류는 아래에, 설치·실행은 운영 안내에 정의합니다.

## 읽기 전용 조회



### 실행 및 접근

해사 데이터 전용 API의 기본 주소는 `http://127.0.0.1:8001`입니다. 모든 Tool 요청에 `Authorization: Bearer <MARITIME_DATA_API_TOKEN>`이 필요합니다. 토큰은 서버의 `.env.local`에 설정하며 로그인 세션·CSRF·기존 public 앱 테이블은 사용하지 않습니다. 실행 예제는 [운영 안내](../user-guide.md#10-해사-데이터-tool-선택)를 참고하세요.

내부 Python 진입점은 `backend.maritime_data.query.query(engine, body)`입니다. 팀 앱에 직접 연결할 때는 호출자가 사용자 권한을 검사해야 합니다. `/api/maritime-data/ask`는 고정 scope의 규칙 기반 조회 도우미이며 LLM 연결은 포함하지 않습니다.

### 입력

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

### 출력

- `contract_version`: 1.0, `dataset`, `data_origin`: REAL 또는 SYNTHETIC.
- `granularity`: reporting_period 또는 daily. `filters`는 적용한 입력 조건.
- `rows`: 해당 승인 뷰의 원본 컬럼 전체와 `dataset_id`, `source_filename`, `source_sha256`, `source_url`, `data_origin`. record_id, source_id, 원본 행 번호, provenance_json, quality_status를 유지합니다.
- `units`: 수치 필드별 단위. MRV co2_t는 원본 보고 CO2이며 재계산이나 CO2eq가 아닙니다.
- `numeric_encoding`: decimal_string. PostgreSQL numeric을 십진 문자열로 직렬화합니다. 정수형 연도·행 번호는 JSON 숫자, 결측은 null, 원본 0은 "0" 등 십진 표현, 날짜·시각은 ISO 문자열입니다. provenance_json 내부 원본 메타데이터 타입은 유지합니다.
- `total`: 페이지가 아닌 필터에 일치하는 전체 행 수. `limit`, `offset`, `has_more`, `next_offset`으로 페이지 이동합니다. 빈 결과에도 total과 경고를 반환합니다.
- `warnings`: 전처리 VALID의 의미, 실제/합성 구분, 역산 거리 한계, 공식 CII 미검증 경고.

MRV는 reporting_year/vessel_id/record_id, Noon은 report_date/vessel_id/record_id 순입니다. 총수와 행 조회는 같은 반복 읽기 스냅샷에서 수행합니다. 서로 다른 페이지 요청 사이에 데이터를 다시 적재하면 결과가 바뀔 수 있습니다.

### DB 및 오류

`maritime_data.real_annual_query`와 `maritime_data.development_noon_query`만 조회하며 출처 테이블을 조인합니다. MRV Partial 및 집계 부적격 레코드와 Noon 비VALID를 제외합니다. 연간 자료를 일별로 분해하거나 실제와 합성을 조인하지 않습니다.

SQL 식별자는 서버 고정값, 입력은 바인딩 매개변수입니다. PostgreSQL READ ONLY / REPEATABLE READ 트랜잭션, SQL 문장당 5초 제한을 적용합니다. 조회 성공 이벤트는 서버 logger(maritime_data.audit)에 기록합니다. 영구 감사 저장은 팀 앱 연동 범위입니다. maritime_data·원본 파일은 수정하지 않습니다.

| HTTP | 의미 |
|---|---|
| 200 | 정상 조회 또는 빈 결과 |
| 401 | Bearer 토큰 누락 |
| 403 | API 토큰 불일치 |
| 422 | 입력 계약 위반 |
| 503 | PostgreSQL 미사용, 연결·스키마·SQL 실행 오류 또는 시간 초과 |

DB 예외의 SQL·연결 문자열은 응답에 노출하지 않습니다. 자료 이용조건, 실제 DWT 및 지원 계수 부분집합 밖의 연료·규정 조건 검증은 별도 과제입니다.


## CO₂ 계산과 준비 상태

이 Tool은 PostgreSQL 입력을 읽고 Python Decimal로 연료 기준 CO2 및 개발용 기간 집약도를 계산합니다. 공식 CII 등급 계산기나 규정 적합성 판정기가 아닙니다.

### 근거와 적용 범위

- [IMO MEPC.364(79) §2.2.1](https://wwwcdn.imo.org/localresources/en/KnowledgeCentre/IndexofIMOResolutions/MEPCDocuments/MEPC.364%2879%29.pdf): Diesel/Gas Oil 3.206, LFO 3.151, HFO 3.114 tCO2/t-fuel의 고정 부분집합을 사용합니다. 계수 버전은 `IMO-MEPC364-79-2.2.1-FOSSIL-SUBSET-v1`입니다.
- [IMO MEPC.352(78) G1](https://wwwcdn.imo.org/localresources/en/KnowledgeCentre/IndexofIMOResolutions/MEPCDocuments/MEPC.352%2878%29.pdf): 배출량·수송능력·거리의 관계와 선종별 용량 기준을 참고했습니다.
- [IMO CII 안내](https://www.imo.org/en/mediacentre/hottopics/pages/eexi-cii-faq.aspx): 공식 연간 평가에는 적용 범위와 연간 자료, 보정 및 등급 기준 검증이 필요합니다.

위 고정 버전의 산술 근거를 사용하는 것이며 최신 규정 전체를 구현했다고 주장하지 않습니다. 바이오·혼합·대체연료, CH4/N2O, CO2eq 및 전 과정 배출량은 지원하지 않습니다. 원본 MGO/VLSFO 라벨을 연료 등급으로 자동 확정하지 않습니다. 특히 VLSFO를 HFO로 자동 매핑하지 않습니다.

### API와 입력

`GET /api/maritime-data/factors`는 계수·버전·근거를 반환합니다. `POST /api/maritime-data/calculate`는 아래 입력을 받습니다. 독립 API(8001)의 두 경로는 `Authorization: Bearer <MARITIME_DATA_API_TOKEN>`이 필요합니다. 팀 앱 연결 시 내부 API 어댑터에서 팀의 접근 정책과 POST CSRF를 적용해야 합니다. 이 어댑터는 아직 구현되지 않았습니다. 독립 도구 자체는 앱 계정을 제공하지 않습니다. 현재 실행·인증 방법은 운영 안내를 참고하세요.

합성 예제의 VLSFO→HFO는 **개발용 가정**이며 실제 연료 증빙이 아닙니다.

```json
{
  "scope": {
    "dataset": "synthetic_noon",
    "vessel_id": "SYN:SIM-BULK-01",
    "start": "2025-01-01",
    "end": "2025-12-31"
  },
  "factor_version": "IMO-MEPC364-79-2.2.1-FOSSIL-SUBSET-v1",
  "fuel_mappings": [
    {"fuel_label":"VLSFO","category":"HFO","evidence":"Development assumption only; not certified fuel evidence"}
  ]
}
```

실제 MRV 준비 상태 확인:

```json
{"scope":{"dataset":"real_annual","vessel_id":"REAL:IMO:6602898","year":2020}}
```

- 단일 선박 필수. Noon 날짜 양 끝 포함, 최대 366일 차이. MRV 단일 연도는 1900~2100 정수.
- 연료 매핑은 MGO/VLSFO 라벨별 1개, 총 2개 이하. category는 DIESEL_GAS_OIL/LFO/HFO 중 하나, evidence는 공백 제외 8자 이상. 이 근거는 사용자 선언으로 보존하며 `mapping_verified=false`입니다.
- 매핑 생략은 허용하지만 사용된 연료가 매핑되지 않으면 전체 CO2는 계산하지 않습니다. 일부 연료만 계산한 값을 총량으로 내보내지 않습니다.
- 실제 MRV는 연료별 내역이 없으므로 매핑 입력을 거절합니다. 추정거리·임의 DWT·임의 계수·페이지 limit/offset 입력도 허용하지 않습니다.

### 계산과 응답

CO2_t = Σ(연료종류별 사용량 t × CF). 기간 DWT 집약도 = CO2_t × 1,000,000 / (DWT t × 거리 nm). Decimal 정밀도 50자리로 계산하며 마지막 표시값만 소수 6자리 ROUND_HALF_UP으로 반올림합니다. 연료별 breakdown은 반올림 전 십진 문자열입니다.

상위 응답 필드:

- `status`: calculated는 CO2 산술 완료, blocked는 입력 부족. 공식 적용성 보증이 아닙니다.
- `calculated_co2_t`: 연료로 계산한 CO2. `source_reported_co2_t`: 실제 MRV 원본 보고값. 두 값을 합치거나 서로 대체하지 않습니다.
- `period_dwt_intensity`: Bulk carrier/Container ship/Oil tanker의 합성 입력에서만, 동일한 양수 DWT와 양수 총거리일 때 계산. Ro-ro 및 그 외 선종은 용량 기준 재검토가 필요해 null입니다.
- `blockers`, `intensity_blockers`: 계산 불가 이유. 거리 0인 날짜도 연료량과 입력 스냅샷에 보존합니다. 총거리가 0이면 CO2는 계산 가능하나 집약도는 null입니다.
- `warnings`: 합성·누락 날짜·미검증 매핑·비공식 기간 지표 등의 경고. 누락일을 채우거나 연간값으로 확대 추정하지 않습니다.
- `input_snapshot`, `request_snapshot`: 모든 선택 입력과 출처·해시·매핑 근거. `factor_catalog`, `version`, `formulas`, `rounding`, `units`: 재현에 필요한 계산 정의.
- `official_cii`, `official_cii_rating`: 항상 null. `compliance=not_assessed`. `official_readiness_missing`은 추가 검증 항목이며 단순 파일 존재 검사로 충족 처리하지 않습니다.

실제 MRV의 현재 데이터는 연료 내역·검증 거리·용량 부족으로 blocked입니다. 한 선박·연도에서 여러 승인 기록이 발견되면 자동 합산하지 않고 검토를 요구합니다. 합성 입력의 날짜 중복도 CO2 계산을 차단합니다.

### 실행 경계와 오류

승인 뷰에서 한 선박의 전체 범위를 한 번의 READ ONLY/REPEATABLE READ 트랜잭션으로 가져옵니다. 문장 제한은 5초이며 1001행을 읽어 1000행 초과 여부를 확인하고 초과하면 422로 거절합니다. 화면의 첫 20행만 계산하는 방식이 아닙니다. 성공한 계산의 요약은 서버 logger에 기록하며 DB·원본은 변경하지 않습니다.

200은 산술 완료 또는 명시적인 blocked 결과, 401은 토큰 누락, 403은 토큰 불일치, 422는 입력 오류·상한 초과, 503은 DB 미지원·연결·스키마·조회 오류입니다. 내부 진입점 `calculate(engine, request)` 사용자는 HTTP 바깥에서도 같은 권한 경계를 적용해야 합니다.

## 고정 조건 조회 도우미

`POST /api/maritime-data/ask`는 `question`(1~2000자), `scope`(위 조회 입력과 동일), `use_model`(boolean, 기본 false)을 받습니다. 추가 필드는 거절합니다. 질문에서 선박·기간을 추출하거나 scope를 바꾸지 않습니다.

응답은 `routing`, `actions`, `result`, `answer`, `warnings`입니다. 지원되는 요청은 고정 scope로 한 번 조회하고 `actions=["query_maritime_data"]` 및 조회 결과를 반환합니다. 계산·등급·쓰기·집계·비교·보고서 요청은 조회를 실행하지 않고 `actions=[]`, `result=null`, `UNSUPPORTED_MARITIME_DATA_REQUEST`를 반환합니다.

독립 API의 모델 게이트웨이는 비활성입니다. `use_model=true`여도 외부 모델을 호출하지 않으며 `LLM_NOT_CONFIGURED` 경고와 규칙 기반 조회 결과를 반환합니다. 다른 Python 호출자가 자체 모델 게이트웨이를 제공하는 경우의 선택적 코드가 있으나 실제 모델 연결 검증 완료를 의미하지 않습니다.

## 수용 기준

- Bearer 누락·불일치를 거절하고 입력 추가 필드·임의 SQL·식별자 혼용을 허용하지 않는다.
- 조회 결과의 출처·단위·NULL·원본 0·정밀한 십진 문자열 및 페이지 정보를 보존한다.
- 전체 계산 범위·READ ONLY·REPEATABLE READ·시간 제한을 적용하고 DB 상세 오류를 노출하지 않는다.
- 연료 매핑·검증 입력이 부족하면 blocked 또는 null과 이유를 반환한다. 공식 CII·등급과 규정 적합성을 생성하지 않는다.
- 독립 API의 조회 도우미는 질문으로 scope를 바꾸거나 실제 모델을 호출하지 않는다.

검증 범위와 실 DB 테스트의 실행 여부는 [changelog](../changelog.md)를 확인하세요.

## 열린 질문

- 팀 내부 API와의 HTTP 연결 방식, 실제 선박 키와 앱 `ships.id`의 매핑, 사용자 접근 정책 및 감사·오류 전달 방식을 팀 연결 단계에서 합의한다.
