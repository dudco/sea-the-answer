# 역할 4 PostgreSQL 적재 결과

검증일: 2026-09-30

## 완료 범위

기존 1차 전처리 결과 `data/role4/2026-09-30-v2`를 `.env.local`에 설정된 로컬 PostgreSQL의 별도 `role4` 스키마에 적재했다. Python 구현 파일과 원본 CSV는 변경하지 않았다. 기존 public 앱 테이블은 변경하지 않았다.

| 테이블 | 적재 행 수 |
|---|---:|
| source_files | 6 |
| vessels | 25,252 |
| synthetic_voyages | 238 |
| annual_reports | 80,552 |
| synthetic_noon | 4,380 |
| quality_issues | 26,249 |

## 실제 검증

- 단일 트랜잭션에서 테이블 생성, CSV 적재, 검증 후 COMMIT 성공.
- 최초 실행은 한글 절대경로 처리 오류로 롤백됨. 입력 디렉터리에서 상대경로로 읽도록 수정 후 정상 적재.
- 테이블별 행 수, PK와 FK, 실제/합성 출처 분리, 항차와 일별 기록의 선박 일치, 품질 이슈 record_id 참조 검사 통과.
- `real_annual_query`: 79,032행 (ARCHIVE_ANNUAL 61,860 + FULL 17,172).
- PARTIAL 1,520행은 REVIEW 상태로 보존하며 기본 연간 조회에서 제외.
- `development_noon_query`: 4,380행, 238항차, 거리 0인 기록 557행 보존.

## 조회 예제

```sql
SELECT reporting_year, count(*) AS report_count,
       sum(fuel_t) AS fuel_t, sum(co2_t) AS reported_co2_t
FROM role4.real_annual_query
GROUP BY reporting_year ORDER BY reporting_year;

SELECT vessel_id, voyage_id, count(*) AS noon_count,
       sum(distance_nm) AS synthetic_distance_nm,
       sum(fuel_t) AS synthetic_fuel_t
FROM role4.development_noon_query
GROUP BY vessel_id, voyage_id ORDER BY vessel_id, voyage_id;
```

연간 합계는 선정된 MRV 보고서 범위의 합계이며 전 세계 배출량이나 동일 선박 집단의 시계열로 해석하지 않는다. 합성 항차 조회는 개발용이다.

## 남은 사항

1. 읽기 전용 SQL 조회 Tool·관리자 API v1 구현 완료 (`QUERY_TOOL.md`). 관리자 조회 화면·도우미도 연결했습니다. 팀 연동 합의와 실제 LLM 검증은 후속 작업.
2. 실제 DWT, 연료종류, 공식 계수·버전, 거리 범위 검증 및 자료 이용조건 확인.
3. 항구 매핑과 실제 항차 자료 보강.
4. 계산 Tool·Agent 통합 검증.

VALID는 지정 전처리 규칙 통과를 의미한다. DB 적재 성공이 데이터 사실성 또는 공식 CII 계산 가능성을 보증하지 않는다. 전처리를 처음부터 다시 수행할 필요는 없으며, 미확정 항목을 보강하고 재검증하는 것이 다음 작업이다.
