# 운항 자료 가져오기

- 상태: 구현됨 (로컬 검증 완료, 원격 배포 제외)
- 작성: 2026-11-06
- 관련: [앱 API](api.md), [정형 자료](prepare-data.md), [항만 참조](port-references.md)

## 범위

기존 CSV 버튼은 일별 CSV와 준비된 MRV/Noon/출처/선박/품질 CSV, DWT 후보 CSV, AIS/항만 JSON 및 반입 ZIP을 받는다. 모든 요청은 관리자 로그인·CSRF·현재 계정 검사를 따른다. 업로드는 임시 저장이며 미리보기 전 영구 자료를 수정하지 않는다. 알려진 헤더만 인식하고 날짜·단위·실제/가상·출처를 추측해 바꾸지 않는다. 실행 파일·SQL·임의 경로를 업로드로 실행하지 않는다.

## API

모든 경로는 `POST /api/operations/import/` 아래에 있으며 기존 관리자 세션·CSRF 검사를 재사용한다. 서버 파일 경로는 요청으로 받지 않는다.

| 경로 | 요청 JSON | 주요 응답 |
|---|---|---|
| `start` | `files: [{name, size}]` (`size`는 정수 byte 수) | `id`, `chunk_bytes`, `expires_in` |
| `chunk` | `id`, `index`, `offset`, `data` (base64) | `received` (해당 파일의 누적 byte 수) |
| `preview` | `id` | `preview_hash`, `datasets`, `has_database`, `existing_ship_links`, `reference`, `reference_previous_sha256`, `ignored_files`, `notice` |
| `commit` | `id`, `preview_hash`, 선택 `map_existing: boolean` (기본 false) | `status`, `datasets`, `linked_ships`, `notice` |
| `reference` | `id`, `preview_hash`, 선택 `replace: boolean` (기본 false) | `status` (`completed`/`unchanged`), `sha256`, `reference`, `notice` |
| `cancel` | `id` | `cancelled: true` |

`datasets`의 각 항목은 `kind`, `rows`, `new`, `unchanged`, `storage`를 갖는다. `reference`는 기존 카탈로그 요약 형식이며 자료가 없으면 null이다. `preview_hash`는 업로드 파일 이름·크기·본문에 결합된 SHA256이다. `chunk`는 0부터 시작하는 file index와 정확한 offset을 순서대로 받으며 재전송 블록을 덧붙이지 않는다. 전송 오류 뒤에는 다시 파일을 선택해 검증한다.

블록 384KiB, 파일 최대 16개·입력 총 128MiB·ZIP 해제 총 160MiB·JSON당 8MiB를 제한한다. ZIP은 stored/deflate 방식과 최대 64개 항목을 지원하며 경로 탈출·중복 경로·심볼릭 링크·암호화·과도한 압축률을 거절한다. CSV와 `catalog.json`/`summary.json`만 읽고 묶음의 실행 파일과 안내 등은 건너뛴다. 소유자당 진행 중 2개, 입력 크기와 해제 예약량을 포함한 프로세스 총 512MiB를 제한한다. 업로드 상태는 단일 서버 프로세스의 메모리와 임시 파일에 보관한다. 20분 비활동 업로드는 다음 업로드 요청에서 정리하며 서버 재시작 후에는 다시 업로드한다. 영구 DB·참조 파일과는 수명이 다르다.

`preview`는 업로드 해시·서식·행수·대상·중복/충돌·연결 필요 상태와 preview hash를 반환한다. `commit`은 해시를 요구하고 파일과 현재 DB를 다시 검증하여 일별/정형 자료를 트랜잭션으로 등록한다. 동일 자료는 재등록하지 않으며 내용이 다른 동일 키는 409로 전체 DB 등록을 중단한다. 필요한 참조 파일이 없으면 누락 항목을 안내한다. `reference`는 별도 단계로 참조 JSON을 검증해 지정 서버 위치에 원자 설치한다. DB 등록과 파일 설치 결과를 각각 표시하며 파일 설치 실패를 DB 롤백으로 설명하지 않는다. `cancel`은 본인 임시 업로드만 정리한다.

주요 오류는 기존 API 오류 형식을 따른다. 미로그인 401, 관리자/CSRF 거절 403, 다른 소유자·만료 업로드 404, 서식/참조 누락 400, 내용/해시 충돌 409, 입력 총량 초과 413, 업로드 예약량·개수 초과 429, 스키마 미적용·파일 저장 불가 503을 반환한다. 개별 파일 크기 등 잘못된 시작 입력은 400이다. 오류 응답에 DB 연결 문자열을 포함하지 않는다.

## 저장과 검증

- 일별 서식은 파일당 1~1,000행이며 여러 일별 파일을 함께 선택할 수 있다. 기존 운항 검증·버전·중복·이상치 규칙과 operations 저장을 재사용한다. 날짜·선박이 같은 동일 내용은 보존하며 다른 내용은 전체 DB 등록을 중단한다.
- 준비 CSV는 source_files/vessels/annual_reports/synthetic_noon/synthetic_voyages/quality_issues의 고정 헤더·타입·FK를 유지한다. 앱 선박을 대량 생성하지 않으며 동일 IMO의 유일한 기존 실제 앱 선박만 확인 후 연결한다. 다른 연결은 보존한다.
- DWT는 기존 후보 값·출처·5% 충돌 검증을 공유한다.
- AIS는 NavigationCatalog를 검증한 별도 JSON이다. 출처/시각을 유지하며 서버 지정 경로가 우선이면 그 사실을 표시한다. 기존 파일 교체에는 미리보기의 현재 해시와 명시 동의가 필요하다.

준비 CSV는 종류별 하나만 선택할 수 있다. 첫 적재는 연결할 출처·원본 선박·항차를 함께 선택하거나 준비 ZIP을 사용한다. 전처리 스크립트와 웹 적재는 `backend/tools/data_contract.py`와 `capacity_data.py`의 동일 서식·후보 검증을 공유한다. 원본 테이블의 고정 열·키·타입·외래 키를 유지하며 새 migration이나 별도 테이블은 만들지 않는다.

웹 DB 등록은 현재 앱과 해사 데이터가 같은 PostgreSQL DB에 있는 구성을 지원한다. `MARITIME_DATA_DATABASE_URL`이 앱 DB와 다르면 기존 관리자 적재 경로를 안내하고 웹 쓰기를 중단한다. 일별/정형 자료의 DB 검증·등록은 하나의 트랜잭션이며 미리보기에서는 롤백한다. 등록 시 계정 상태와 현재 DB를 재확인하고 감사 기록에 해시·종류별 건수·연결 건수를 남긴다.

관리형 참조 경로는 `HAEDAP_IMPORT_DIR/navigation/catalog.json`이며 기본 직접 실행 경로는 `backend/data/imports/navigation/catalog.json`, Docker는 `/data/imports/navigation/catalog.json`이다. 운영 Compose의 `maritime-imports` 볼륨에 보존한다. `MARITIME_PORT_REFERENCES_PATH`로 지정한 외부 경로가 우선하며 웹에서 그 경로의 다른 파일을 덮어쓰지 않는다. 기존과 같은 SHA256이면 재설치 없이 성공한다. 관리형 파일 교체는 이전 해시를 재검사하고 이전 JSON을 보존한 뒤 원자적으로 교체한다. DB 트랜잭션과 파일 설치는 별도 작업이므로 화면은 성공 결과를 각각 유지하고 참조 설치만 재시도할 수 있다.

임의 MRV 원시 서식은 필요한 준비 서식을 안내한다. 연간 보고를 하루 실적으로 바꾸거나 가상을 실제로 승격하지 않는다. 공식 CII·등급·입항 승인·원본의 법정 검증은 생성하지 않는다.
