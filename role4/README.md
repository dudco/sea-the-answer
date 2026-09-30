# Sea the Answer · 역할 4

최종 업데이트: **2026-09-30**

선박 운항 데이터의 **선정·전처리 → PostgreSQL 적재 → 읽기 전용 조회 → CO₂ 계산·입력 검증**을 담당하는 역할4 산출물입니다. 팀 저장소의 기존 앱과 독립된 `role4/` 폴더로 제공됩니다. 문서 검색, 보고서 작성, 사용자 관리 화면, 실제 LLM 연결은 포함하지 않습니다.

## 1. 완료 현황

| 구분 | 결과 |
|---|---|
| 실제 MRV 전처리·적재 | 80,552행, 기본 조회 79,032행 |
| Partial 보고 | 1,520행 보존, 기본 조회에서 제외 |
| Synthetic Noon | 개발·검증용 4,380행 / 238항차 |
| PostgreSQL | `role4` 스키마, 6개 테이블과 목적별 View |
| 조회 Tool | 실제/합성 분리, 기간·선박·항차 필터, 출처·품질·단위 반환 |
| 계산 Tool | Decimal CO₂ 산술, 개발용 기간 DWT 집약도, 부족 입력 명시 |
| 공개 참조 자료 | GISIS EEDI 11,244행, IMO DCS 2019~2024 집계, Wikidata·MarineVessels 제원 후보 |
| 상세 작업 설명 | 1~9단계 Markdown 및 PDF |

위 데이터 건수는 로컬에서 확보·적재·검증한 결과입니다. **GitHub에 원본 데이터나 DB가 포함되어 있다는 의미는 아닙니다.** 실제 MRV 보고값과 계산값은 구분하며, 공식 CII 수치·등급을 생성하지 않습니다. 익명 집계값과 미검증 DWT 후보는 법정 검증 입력을 대체하지 않습니다.

팀 연결 방법: [역할1·2·3 연동 안내](INTEGRATION.md).

## 2. 파일 구성

| 위치 | 내용 |
|---|---|
| `scripts/prepare_role4.py` | 원본 6종 전처리, CSV·출처·품질 이슈 출력 |
| `scripts/load-role4.ps1` | PostgreSQL 트랜잭션 적재 및 검증 |
| `scripts/prepare_gisis_eedi.py` | GISIS EEDI 참조 정규화 |
| `scripts/prepare_open_cii_references.py` | 공개 선박 제원 후보·DCS 참조 정리 |
| `service/role4.py` | 고정 SQL 및 바인딩 매개변수 기반 조회 |
| `service/role4_calculations.py` | CO₂·기간 지표·공식 입력 준비 상태 |
| `service/role4_agent.py` | 선택한 scope를 유지하는 조회 도우미 |
| `service/app.py` | 역할4 전용 FastAPI와 토큰 인증 |
| `service/tests/` | 입력·계산·인증·PostgreSQL 조회 검증 |
| `docs/role4/` | ERD, 데이터 정의, DDL, 계약, 검증 기록 |
| `docs/role4/stages/`, `docs/role4/pdf/` | 기존 작업의 단계별 설명 원문과 PDF |

## 3. 설치·설정

준비물: **Python 3.12 또는 3.13** (잠금 파일은 Windows/Python 3.12에서 검증), 실행 중인 PostgreSQL, 별도로 확보한 원본 또는 전처리 CSV. 아래 명령은 팀 저장소 루트에서 `cd role4`로 이동한 뒤 이 README가 있는 `role4/` 폴더에서 실행합니다. 이 저장소는 PostgreSQL 설치·기동이나 데이터를 자동 다운로드하지 않습니다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
Copy-Item .env.example .env.local
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

`.env.local`의 `DATABASE_URL`에 본인의 DB 주소·계정을 설정하고, 생성한 문자열을 `ROLE4_API_TOKEN`에 입력합니다. 기존 `.env.local`이 있으면 복사하지 말고 필요한 항목만 추가하세요. 예시의 포트 55432는 기존 로컬 환경 값이며, 다른 서버에서는 실제 포트를 사용합니다.

DB/사용자가 없으면 pgAdmin에서 별도 DB와 소유 계정을 먼저 생성하세요. 적재에는 스키마 생성 권한이 필요합니다. 팀 앱 운영 시에는 적재 후 `role4` 스키마 USAGE와 테이블 SELECT만 가진 별도 조회 계정 사용을 권장합니다. API는 public 앱 테이블을 생성하거나 수정하지 않습니다.

Linux에서는 `python3.12 -m venv .venv`, `.venv/bin/python`을 사용합니다. 아래 적재 PowerShell 스크립트는 Windows용이며 Linux 자동 적재는 검증하지 않았습니다.

## 4. 전처리 및 DB 적재

원본 파일 목록·출처·공개 범위는 [데이터 확보 안내](docs/role4/DATA_ACCESS.md)에 있습니다. 팀에서 제공받은 원본 6개가 있는 폴더를 지정합니다. 같은 이름의 파일이 여러 개 있으면 중단하며 결과 폴더는 새 경로여야 합니다.

```powershell
.\.venv\Scripts\python.exe scripts/prepare_role4.py --source 'D:/Data' --out data/role4/new-run
.\.venv\Scripts\python.exe scripts/test_prepare_role4.py
./scripts/load-role4.ps1 -DataDir data/role4/new-run
```

이미 전처리 CSV를 보유했다면 전처리를 건너뛰고 해당 폴더를 `-DataDir`에 지정합니다. 기본 폴더는 `data/role4/2026-09-30-v2`입니다. PostgreSQL 설치 위치가 다르면 `-PgBin 'D:/PostgreSQL/18/bin'`을 추가합니다.

적재 스크립트는 **로컬 DB만 지원**하고, `role4` 스키마가 이미 있으면 덮어쓰지 않습니다. CSV 누락·무결성 검증 실패 시 전체 트랜잭션을 롤백합니다. 현재 검증 SQL의 건수 기준은 위에 기재한 선정 데이터 버전용입니다. 새 버전 데이터는 기대값을 검토한 뒤 별도 DB에서 검증하세요.

6개 테이블: `source_files`, `vessels`, `synthetic_voyages`, `annual_reports`, `synthetic_noon`, `quality_issues`. 참조 자료는 별도 파일로 보관하고 운영 조회 View에 혼합하지 않습니다.

## 5. API 실행·사용

```powershell
.\.venv\Scripts\python.exe -m uvicorn service.app:create_app --factory --host 127.0.0.1 --port 8000
```

API 명세: http://127.0.0.1:8000/docs . `Authorize`에 본인의 토큰을 입력해 테스트합니다. `/api/health`는 프로세스 상태만 확인하며 DB 연결 성공을 의미하지 않습니다.

별도 PowerShell에서 토큰을 입력하고 조회합니다.

```powershell
$token = Read-Host 'ROLE4_API_TOKEN' -AsSecureString
$plainToken = [System.Net.NetworkCredential]::new('', $token).Password
$headers = @{ Authorization = "Bearer $plainToken" }
$body = @{ dataset = 'real_annual'; year_start = 2020; year_end = 2025; limit = 20 } | ConvertTo-Json
$result = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/role4/query' -Headers $headers -ContentType 'application/json' -Body $body
$result.rows | Format-Table reporting_year, vessel_id, fuel_t, co2_t
```

| API | 용도 |
|---|---|
| `POST /api/role4/query` | MRV 연도별 / 합성 Noon 날짜·항차별 조회 |
| `GET /api/role4/factors` | 고정 버전 계산계수·단위·출처 |
| `POST /api/role4/calculate` | CO₂ 산술·기간 지표·계산 불가 사유 |
| `POST /api/role4/ask` | 고정 scope의 규칙 기반 조회 도우미 |

모든 Tool은 **Bearer 토큰**이 필요합니다. 기존 통합 앱의 `/api/login`, 관리자 세션, CSRF, Next.js 화면은 이 배포판에서 제공하지 않습니다. 토큰 보유자는 역할4 데이터 전체를 조회할 수 있으므로 팀 앱에 연동할 때 사용자·선박별 권한 검사를 추가해야 합니다. 토큰은 브라우저 코드에 넣지 말고 서버에서 사용하세요. 기본 바인딩은 로컬이며 외부 서비스 배포 시 HTTPS 및 운영 인증 구성이 필요합니다.

조회는 최대 200행이며 `next_offset`으로 다음 페이지를 요청합니다. numeric은 정밀도를 유지하는 십진 문자열, 결측은 null입니다. PostgreSQL 읽기 전용·반복 읽기 트랜잭션과 SQL 문장당 5초 제한을 적용합니다. 성공한 조회·계산의 요약 이벤트는 `role4.audit` logger에 남기며 영구 감사 저장소는 포함하지 않습니다.

계산 요청 예시:

```powershell
$calculation = @{
  scope = @{ dataset = 'synthetic_noon'; vessel_id = 'SYN:SIM-BULK-01'; start = '2025-01-01'; end = '2025-12-31' }
  fuel_mappings = @(@{ fuel_label = 'VLSFO'; category = 'HFO'; evidence = 'Development assumption only; not certified fuel evidence' })
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/role4/calculate' -Headers $headers -ContentType 'application/json' -Body $calculation
```

위 연료 매핑은 **개발용 가정**입니다. 선정된 합성 데이터 기준 365행, CO₂ 13502.104704t, 기간 DWT 집약도 5.028268이 기대값이며 실제 선박의 공식 CII가 아닙니다. 필요한 입력이 없으면 `blocked`와 이유를 반환합니다. 도우미의 `use_model=true`도 이 배포판에서는 `LLM_NOT_CONFIGURED` 경고와 함께 규칙 경로로 처리됩니다.

## 6. 검증

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/test_prepare_role4.py
```

기본 테스트는 실제 DB가 필요 없으며 PostgreSQL 통합 테스트는 건너뜁니다. 선정 데이터를 이미 적재했다면 `ROLE4_TEST_DATABASE_URL`을 해당 DB URL로 설정하여 통합 테스트도 실행할 수 있습니다. 테스트는 기존 role4 데이터를 읽기만 하며 재적재하지 않습니다.

최신 배포 검증 결과는 [배포 검증 기록](docs/role4/RELEASE_VALIDATION.md)에 기록합니다. 과거 단계 문서의 전체 서비스 83개 테스트는 기존 통합 앱의 기록이며 현재 전용 배포판 테스트 개수와 다릅니다.

## 7. 상세 문서 및 단계별 PDF

- [데이터 계약·ERD](docs/role4/ROLE4_DATA_CONTRACT.md), [SQL 스키마](docs/role4/role4_schema.sql), [적재 결과](docs/role4/DB_LOAD_RESULT.md)
- [조회 계약](docs/role4/QUERY_TOOL.md), [계산 계약](docs/role4/CALCULATION_TOOL.md)
- [단계별 작업 설명](docs/role4/stages), [단계별 PDF 9종](docs/role4/pdf)

PDF와 단계별 문서는 **작업 당시의 구현 과정 기록**입니다. 특히 5·6단계의 통합 앱 로그인·화면·Agent 연결 설명은 과거 구성입니다. 현재 실행 방법은 이 README와 조회·계산 계약을 기준으로 확인하세요.

## 문제 해결

- 시작 시 설정 오류: `.env.local`의 DB URL과 32자 이상 API 토큰을 확인합니다.
- 401/403: Authorization 헤더 누락 또는 토큰 불일치입니다.
- 422: 입력 계약·기간·행 수 상한을 확인합니다.
- 503: PostgreSQL 기동·주소·권한·role4 적재 여부 및 조회 제한시간을 확인합니다.
- 전처리 원본 없음: 저장소에는 원본이 포함되지 않습니다. 데이터 확보 안내와 팀 보유본을 확인합니다.
- 공식 CII가 null: 버그가 아니라 검증된 연간 입력 부족 및 미구현 범위의 명시입니다.

## 변경 이력

- **2026-09-30:** 팀 저장소의 기존 코드를 유지하고 역할4 전용 코드·문서·PDF를 별도 폴더에 추가. 원래 조회·계산 로직을 유지하면서 독립 FastAPI와 토큰 인증, 실행 안내를 구성. 원본 데이터·로컬 DB·비밀번호는 제외. 팀 앱과 실제 연결은 후속 통합 범위이며, API 연결 계약은 아래 인수인계 문서를 참고.
