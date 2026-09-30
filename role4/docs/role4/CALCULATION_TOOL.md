# 역할 4 CO2 계산·CII 준비 상태 Tool v1

2026-09-30. LLM 설치·연결은 역할 4 후속 범위에서 보류합니다. 이 Tool은 PostgreSQL 입력을 읽고 Python Decimal로 연료 기준 CO2 및 개발용 기간 집약도를 계산합니다. 공식 CII 등급 계산기나 규정 적합성 판정기가 아닙니다.

## 근거와 적용 범위

- [IMO MEPC.364(79) §2.2.1](https://wwwcdn.imo.org/localresources/en/KnowledgeCentre/IndexofIMOResolutions/MEPCDocuments/MEPC.364%2879%29.pdf): Diesel/Gas Oil 3.206, LFO 3.151, HFO 3.114 tCO2/t-fuel의 고정 부분집합을 사용합니다. 계수 버전은 `IMO-MEPC364-79-2.2.1-FOSSIL-SUBSET-v1`입니다.
- [IMO MEPC.352(78) G1](https://wwwcdn.imo.org/localresources/en/KnowledgeCentre/IndexofIMOResolutions/MEPCDocuments/MEPC.352%2878%29.pdf): 배출량·수송능력·거리의 관계와 선종별 용량 기준을 참고했습니다.
- [IMO CII 안내](https://www.imo.org/en/mediacentre/hottopics/pages/eexi-cii-faq.aspx): 공식 연간 평가에는 적용 범위와 연간 자료, 보정 및 등급 기준 검증이 필요합니다.

위 고정 버전의 산술 근거를 사용하는 것이며 최신 규정 전체를 구현했다고 주장하지 않습니다. 바이오·혼합·대체연료, CH4/N2O, CO2eq 및 전 과정 배출량은 지원하지 않습니다. 원본 MGO/VLSFO 라벨을 연료 등급으로 자동 확정하지 않습니다. 특히 VLSFO를 HFO로 자동 매핑하지 않습니다.

## API와 입력

`GET /api/role4/factors`는 계수·버전·근거를 반환합니다. `POST /api/role4/calculate`는 아래 입력을 받습니다. 두 경로 모두 `Authorization: Bearer <ROLE4_API_TOKEN>`이 필요합니다. 현재 실행·인증 방법은 루트 README를 참고하세요.

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

## 계산과 응답

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

## 실행 경계와 오류

승인 뷰에서 한 선박의 전체 범위를 한 번의 READ ONLY/REPEATABLE READ 트랜잭션으로 가져옵니다. 문장 제한은 5초이며 1001행을 읽어 1000행 초과 여부를 확인하고 초과하면 422로 거절합니다. 화면의 첫 20행만 계산하는 방식이 아닙니다. 성공한 계산의 요약은 서버 logger에 기록하며 DB·원본은 변경하지 않습니다.

200은 산술 완료 또는 명시적인 blocked 결과, 401은 토큰 누락, 403은 토큰 불일치, 422는 입력 오류·상한 초과, 503은 DB 미지원·연결·스키마·조회 오류입니다. 내부 진입점 `calculate(engine, request)` 사용자는 HTTP 바깥에서도 같은 권한 경계를 적용해야 합니다.

## 테스트

`service/tests/test_role4_calculations.py`는 손계산 정답, Decimal 반올림, 미매핑 연료, 거리 0, 선종·DWT 불일치, 날짜 중복·누락, 원본 보고 CO2 분리, 토큰 인증 및 실제 PostgreSQL 전체 365일 계산을 검증합니다. 10t HFO + 5t Diesel/Gas Oil의 정답은 47.170t CO2, DWT 1000t·거리 100nm의 기간 지표는 471.7gCO2/(DWT t·nm)입니다.

실제 PostgreSQL 테스트는 ROLE4_TEST_DATABASE_URL 설정 시 실행되며 인증은 테스트 전용 토큰으로 격리합니다. 이 테스트의 VLSFO 매핑은 산술 검증용 가정이고 실제 연료 분류 검증이 아닙니다.

2026-09-30 실제 실행: 전체 서비스 83개 통과(기존 TestClient 폐기 예정 경고 1건). SYN:SIM-BULK-01의 2025년 365행에 VLSFO→HFO 개발 가정을 적용한 결과는 연료 4335.936000t, CO2 13502.104704t, 거리 83913.740000nm, 기간 DWT 집약도 5.028268입니다. 기존 조회 화면·Agent는 조회 전용으로 유지하며 새 계산 API에 자동 연결하지 않았습니다.
