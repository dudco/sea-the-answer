# 데이터 확보·공개 범위

이 저장소에는 코드, 데이터 정의, SQL, 계약, 검증 기록과 직접 작성한 PDF만 포함합니다. 원본·전처리 CSV, PostgreSQL 데이터 디렉터리, 로그인 정보는 포함하지 않습니다. 공개 열람 가능과 재배포 허용은 다르므로 이용조건이 확인되지 않은 원본을 GitHub에 재게시하지 않았습니다.

## 전처리 원본 6종

`scripts/prepare_role4.py`는 아래 파일명을 기준으로 원본 폴더를 재귀 검색합니다. 팀 보유본 또는 출처에서 해당 버전을 확보해야 하며 최신 웹 다운로드가 동일 파일·동일 건수를 보장하지는 않습니다.

| ID | 원본 파일 | 용도 |
|---|---|---|
| DS-001 | `eu_mrv_vessel_annual_2018_2022.csv` | 실제 MRV 과거 보고기간 자료 |
| DS-002 | `해양수산부_선박_AIS_동적정보_20220101.csv` | 마스킹 AIS 참고자료, 선박 자동 연결 제외 |
| DS-003 | `UpdatedPub150.csv` | WPI 항구 참조 |
| DS-004 | `Smart-Maritime-Council-Standardised-Vessel-Dataset-SVD-for-Noon-Reports-and-Emissions-Reporting-V2-May-2025.xlsx` | SVD 컬럼 설계 참고 |
| DS-005 | `2025-v57-12092026-EU_MRV_Publication_of_information.xlsx` | 실제 MRV 보고 자료 |
| DS-006 | `synthetic_noon_daily_2025.csv` | 개발·검증용 합성 Noon |

출처와 선정 근거는 [1단계](stages/01_데이터선정과출처.md), [전처리 검증](VALIDATION.md)에 있습니다. 원본별 URL·SHA256은 전처리 출력 `source_files.csv`와 `summary.json`에 보존됩니다. 팀에서 데이터 전달 시 이 두 파일과 CSV 6개를 함께 전달하세요. 정확한 기존 버전의 재확보가 안 되면 새 자료를 기존 정답 건수에 맞추지 말고 새 데이터 버전으로 검증해야 합니다.

## 공개 참조 자료

| 자료 | 보유 결과 및 제한 | 처리 코드 |
|---|---|---|
| GISIS EEDI | 11,244행, 익명·반올림, IMO 번호 없음 | `prepare_gisis_eedi.py` |
| IMO DCS 연차 보고서 | 2019~2024 공개 집계, 선박 단위 결합 불가 | `prepare_open_cii_references.py` |
| Wikidata / MarineVessels | MRV 25,240척 중 15,956척에 DWT 후보, 법정 검증값 아님 | `prepare_open_cii_references.py` |

GISIS 정규화는 `python scripts/prepare_gisis_eedi.py INPUT.xlsx OUTPUT_DIR`로 실행합니다. 공개 CII 참조 처리 스크립트는 `data/role4/2026-09-30-v2/reference/`의 수집 완료 파일을 입력으로 요구하며 자동 수집기가 아닙니다. 필요한 파일 구조와 수집 근거는 [8단계](stages/08_GISIS공개데이터와EEDI참조세트.md), [9단계](stages/09_공개데이터_CII입력보완.md)를 참고하세요.

공식 CII 산정에 필요한 동일 선박·동일 연도의 검증된 연료별 사용량, 항해거리, 적용 선종·용량 및 보정 조건은 아직 충분히 확보되지 않았습니다. 공개 집계와 제원 후보를 공식 입력으로 자동 승격하지 않습니다.
