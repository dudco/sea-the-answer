> 이 문서는 기존 통합 앱에서 수행한 단계별 작업 기록입니다. 현재 역할4 전용 배포판의 실행·인증 방법과 포함 범위는 루트 README를 따릅니다.

# 8단계: GISIS 공개 데이터 확인과 EEDI 참조 세트 준비

## 목적

기존 MRV 데이터에서 빠진 DWT·연료종류·전 세계 연간 항해거리 등을 IMO GISIS 공개 계정으로 보완할 수 있는지 확인했습니다. 공개 계정으로 접근 가능한 자료만 사용하고, 개별 선박과 연결할 수 없는 익명 자료는 별도 참조 세트로 분리했습니다.

## GISIS에서 직접 확인한 내용

공개 계정으로 로그인한 뒤 `Ship Fuel Oil Consumption` 모듈에 접근했지만 권한 거부 화면이 표시됐습니다. 따라서 선박별 연간 DCS 원본인 연료종류별 사용량, 연간 거리, 운항시간과 CII 자료는 내려받지 못했습니다.

`Ship and Company Particulars`에서는 IMO 번호, 선명, 과거 선명, 국적, 선종, GT, 건조연도, 호출부호, MMSI, 소유회사 IMO 번호와 상태를 개별 조회할 수 있었습니다. 그러나 DWT가 없고, S&P Global과 IMO 간 협약에 따른 조회 화면이므로 기존 25,252척을 자동 대량수집하는 방식은 채택하지 않았습니다.

`MARPOL Annex VI > EEDI Database Information`에서는 IMO가 익명화·반올림한 Excel 원본을 내려받을 수 있었습니다. 원본 갱신일은 2025-12-02이며, SHA-256은 `8c8835a09f9ca9aa87747fbaafde0c710fd96d4f928cbb39b2fcabc4fd4562b0`입니다.

## 전처리 방법

원본의 Bulk, Gas, Tanker, Container, General, Refrigerated, Combination, LNG, Ro-ro 3종, Cruise 시트를 읽었습니다. 시트별 익명 선박 번호가 있는 행만 선택하고 공통 필드로 정규화했습니다.

- 선종과 적용 EEDI 단계
- 용량과 단위: 11,165행 DWT, 79행 GT
- 인도연도, 선박 치수
- 요구 EEDI와 달성 EEDI
- 기준속도 Vref와 주기관 출력 PME
- 기준선 대비 감축률
- 공개된 경우 연료종류·가스 보정계수·빙등급·설계 설명

`reference_id`는 시트명과 시트 내부 익명 번호로 만들었습니다. 실제 IMO 번호처럼 취급하지 않습니다. 원본 행 번호와 원본 페이지 URL을 각 행에 남겨 추적할 수 있게 했습니다.

## 결과와 검증

정규화 결과는 11,244행이며 원본 Summary 시트의 총계와 일치합니다. `reference_id`는 모두 고유합니다. 용량과 달성 EEDI는 11,244행 모두 존재합니다. 인도연도는 11,234행, Vref는 8,690행, 주기관 출력은 8,676행, 연료종류는 2,865행에 있습니다. 인도연도 10행 결측은 값을 만들지 않고 검토 상태로 표시했습니다.

선종별 행 수는 Bulk carrier 4,457, Tanker 3,000, Containership 1,841, General cargo 661, Gas carrier 603, LNG carrier 243, Ro-ro vehicle carrier 172, Cruise 79, Ro-ro cargo 76, Refrigerated cargo 61, Ro-ro passenger 46, Combination carrier 5입니다.

## 기존 데이터와의 관계

이 참조 세트는 MRV 선박의 누락 DWT를 채우지 않습니다. 익명 EEDI 행과 MRV의 IMO 번호를 연결할 식별자가 없기 때문입니다. 또한 EEDI는 설계효율이고 MRV·DCS·CII는 운항기간 실적을 다룹니다. 따라서 다음 용도로만 사용합니다.

1. 선종·용량 구간별 설계효율 분포 참고
2. 합성 개발자료의 DWT·속도·출력 범위가 극단적으로 벗어나지 않는지 점검
3. 향후 EEDI와 운항 CII를 구분해 설명하는 교육·분석 자료

`role4.real_annual_query`, 공식 CII 계산 입력과 PostgreSQL 운영 테이블에는 넣지 않았습니다. 원본과 정규화 자료는 `data/role4/2026-09-30-v2/reference/gisis-eedi-2025/`에 보관합니다. 재현 스크립트는 `scripts/prepare_gisis_eedi.py`입니다.

## 남은 제한

완전한 연간 DCS 입력 세트는 여전히 확보되지 않았습니다. 선박별 연료종류 사용량, 검증된 전 세계 연간 항해거리, DWT 또는 적용 GT, 보정·제외 내역과 검증된 CII 결과가 필요합니다. GISIS 공개 EEDI 페이지에는 별도 재이용 라이선스가 표시되지 않아 외부 재배포 전 이용조건 확인도 필요합니다.
