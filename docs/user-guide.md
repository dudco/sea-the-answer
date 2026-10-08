# 사용·운영 안내

> 대상 버전: 1.4.0 · 설치와 기본 실행은 [`../README.md`](../README.md)를 먼저 보세요.

## 1. 화면별 사용 방법

| 화면 | 할 수 있는 일 |
|---|---|
| 통합 질문 | 문서 질문, 선박·기간 지정, 운항 수치·추이·출처 확인, 근거 페이지 열기, 입력 기준 비교, 당시 답변 이력 열기, 보고서에 담기 |
| 문서 | 텍스트 PDF 등록, 추출 내용 검토, 메타데이터·열람 범위 설정, 개정 등록, 사용 중·이전·폐기 구분, 저장 원문 PDF 보기, 삭제 |
| 운항 정보 | 선박 등록·수정, 일별 기록 등록·수정·삭제, CSV 검증·일괄 등록, 지표별 차트, 여러 선박 비교, 배출량·집약도·시간 계산 |
| 보고서 | 여러 초안 저장·검색·다시 열기, DB 기록으로 Noon/MRV 검토 초안 생성, 편집·미리보기·Markdown 출력, JSON 가져오기, 검토 요청·승인 상태 표시 |
| 관리 | 계정·역할 관리, 변경 및 보고서 승인·반려, 질의·변경·오류·계산 로그, 전체 백업·복구·파일 보관·가져오기·자동 백업 설정 |

### 가장 빠른 체험 순서

1. 일반 화면은 바로 사용할 수 있습니다. 가상 예시를 넣으려면 **관리자 로그인 → admin / 1234**로 로그인합니다.
2. **운항 정보 → 가상 예시로 둘러보기**를 누릅니다. 선박·기록이 없는 작업공간에서만 사용할 수 있습니다. 가상 선박 3척·2026-09-22~28의 21개 기록이 DB에 등록됩니다.
3. **통합 질문**에서 선박·기간을 확인하고 `선택한 선박의 연료 추이를 분석해줘`를 질문합니다.
4. 수치와 그래프를 확인하고 **보고서에 담기 → 저장**합니다.
5. **보고서 → 운항 기록으로 초안 만들기**에서 Noon과 MRV를 각각 생성합니다. 별도 항목으로 보관됩니다.
6. 초안의 누락 항목을 채우고 **검토 요청**합니다. 관리자는 **관리 → 승인 → 검토 내용 → 승인·반영**으로 확정합니다.
7. **관리 → 백업·복구**에서 백업을 만듭니다.

가상 예시는 자동으로 실제 자료와 섞어 넣지 않습니다. 새 작업공간에서 직접 기록을 넣는 경우 먼저 선박을 등록하세요.

### 문서 등록

- PDF는 최대 25MB, 1,000페이지를 지원합니다. 브라우저 안의 PDF.js로 추출하고 원본과 페이지 번호를 함께 저장합니다. 업로드 문서는 외부 서비스로 전송하지 않습니다.
- 문서 등록·개정·삭제는 관리자 전용입니다. 추출 진행·실패를 표시하고, 확인 체크 후 **저장**하면 승인 대기 없이 바로 반영됩니다. 실제 인덱싱이 성공해야 목록에 반영됩니다.
- 스캔 PDF의 OCR은 포함하지 않습니다. 텍스트 없는 페이지를 안내합니다. OCR 처리된 PDF를 사용하거나 페이지별 본문을 입력하세요.
- 본문의 `--- PAGE 7 ---`은 원본 PDF의 물리적인 7번째 페이지입니다. 인쇄된 쪽번호와 다를 수 있습니다.
- 문서명, 버전, 발행기관, 발행일, 개정일, 조항, 적용 조건, 열람 범위를 입력합니다. 표 구조와 조항의 자동 인식은 보장하지 않으므로 추출 내용을 원본과 대조합니다.
- 개정은 문서 상세의 **개정·정보 수정**으로 등록합니다. 이전 인용을 보존하고 새 버전을 검색에 사용합니다. 기존과 다른 원문이면 버전 이름도 바꾸세요.
- ‘사용 중’은 내부에서 지정한 적용 버전입니다. 외부 최신 규정 자동 확인 기능은 아닙니다.
- DOCX·PPT·일반 텍스트 파일 등록은 아직 지원하지 않습니다(계획: [`plans/2026-10-08-team-module-integration.md`](plans/2026-10-08-team-module-integration.md)).

운영자는 JSON 문서 배열을 직접 수집할 수도 있습니다. 형식은 `backend/knowledge/seed.json`을 참고하세요.

```bash
npm run ingest -- backend/knowledge/seed.json
```

## 2. 역할과 승인

| 사용 방식 | 권한 |
|---|---|
| 일반 사용자 · 로그인 없음 | 공개 문서 조회·질문, 운항 조회·분석·계산, 자기 브라우저의 보고서 작성·저장·검토 요청 |
| 관리자 · 로그인 필요 | 위 기능과 함께 제한 문서 열람, 문서·선박·기록 등록·수정·삭제 즉시 반영, 보고서 승인, 사용자 관리, 전체 로그·백업·복구 |

- 기본 관리자는 **`admin / 1234`**로 고정하며 사용자 관리 화면에서 수정하지 않습니다. 필요하면 별도의 관리자 계정(비밀번호 10자 이상)을 추가합니다. 기존 담당자·열람 계정 정보는 보존하지만 로그인은 관리자 계정에만 허용합니다.
- 문서 열람 범위는 `누구나 열람 / 담당자·관리자 / 관리자만`입니다. 로그인 없는 사용자는 `누구나 열람` 문서만 볼 수 있습니다. 관리자가 범위를 바꾸면 해당 문서의 이전 버전에도 적용됩니다.
- 문서와 운항 원본 자료는 관리자만 변경할 수 있고, 저장·등록·삭제는 승인 대기 없이 즉시 반영됩니다.
- 보고서는 관리자 작성분도 **검토 요청 → 승인** 단계를 거칩니다. 검토·승인된 보고서는 새 초안으로 복사해 수정합니다.
- 일반 사용자의 초안과 질문 이력은 브라우저의 무작위 식별 쿠키로 구분합니다. 쿠키를 삭제하거나 다른 브라우저·주소로 접속하면 다른 일반 사용자로 취급합니다. 같은 브라우저 프로필을 공유하는 사람은 같은 작업공간을 씁니다. 중요한 초안은 JSON으로 보관하세요.
- 관리자 세션은 12시간입니다. 서버 재시작·로그아웃·전체 복구 후에는 관리 기능만 다시 로그인합니다.

## 3. 운항 CSV

관리자로 로그인한 뒤 **운항 정보 → CSV 불러오기 → CSV 서식 받기**를 사용하세요. `ship` 열에는 화면에 안내된 선박 ID를 넣습니다.

- 필수 열: `ship,date,fuel,factor,distance,speed,fuelType`
- 선택 열: `position,voyage,draft,weather,engineHours,note`
- 단위: 연료 t, 거리 nm, 속력 kn, 흘수 m, 시간 h. 날짜 `YYYY-MM-DD`.
- CO₂ = 각 기록의 연료 × 입력 배출계수. 배출계수는 실제 연료에 맞게 확인하세요.
- 최대 1MB·1,000개 기록. 누락·숫자 범위·일자·중복을 행별로 표시합니다. 동일 선박·일자는 한 건만. 이전 기록보다 연료가 2배 이상이면 점검 사유가 필요합니다. 하나라도 실패하면 전체를 반영하지 않습니다.

필드 정의는 [`data-model.md`](data-model.md#3-운항)를 참고하세요.

## 4. 보고서와 기준 비교

- Noon 초안: 선택한 기간의 마지막 기록 하루. MRV 검토 초안: 선택 기간 전체.
- 선박·기간·항차·연료 종류·계수·수치·위치·흘수·기상·기관 운전시간 등을 표시하고, 없는 항목은 `[미입력 · 확인 필요]`로 표시합니다.
- 팀이 검토하는 기본 서식이며, 공식 Noon/MRV 제출 서식 충족을 인증하지 않습니다.
- 저장 충돌 시 내 편집 내용은 유지됩니다. 서버 내용을 확인하고 JSON으로 보관하거나 최신 버전을 확인한 후 대체 저장할 수 있습니다.
- 통합 답변의 **적용 기준 확인**은 근거 구절, 비교 지표, 조건과 기준값을 사용자가 직접 지정해 `입력 기준 충족 / 미충족 / 판단 불가`를 표시하는 기능입니다. 규정 적용 여부를 자동 판정하지 않습니다.

## 5. 외부 AI 답변 (선택)

`.env.example`을 `.env`로 복사하고 `OPENAI_API_KEY`, `OPENAI_MODEL`을 설정한 후 서버를 재시작합니다. 두 값이 모두 있으면 통합 질문에서 **AI 답변**을 선택할 수 있습니다. API 키는 브라우저로 보내지 않고, 모델 실패 시 원문 근거 표시로 돌아갑니다. 실제 외부 모델 호출은 아직 검증하지 않았습니다.

## 6. 백업과 복구

- **백업 만들기**: 문서·PDF·운항·보고서·계정 및 권한·질의·로그·승인·앱 설정을 JSON으로 DB 옆 `backups` 폴더에 보관합니다.
- **파일 보관 / 가져오기**: 다른 저장장치에 보관할 파일을 내려받고, 100MB 이하의 전체 백업을 목록에 추가합니다(형식·체크섬 검증).
- **복구**: 선택한 시점으로 현재 데이터를 교체합니다. 복구 직전 자동 백업, 트랜잭션 복구, 검색 인덱스 재생성, 모든 세션 무효화를 수행합니다. 관리 기능은 `admin / 1234`로 다시 로그인합니다.
- **자동 백업**: 기본 하루 1회(UTC 날짜 기준, 서버 실행 중 1분마다 확인). 관리 화면에서 끌 수 있고 자동 삭제는 하지 않습니다.
- `.env`는 백업에 포함되지 않으니 별도로 보관합니다.
- 서버가 켜지지 않으면 정상 종료된 상태의 DB 폴더(기본 `backend/data`) 복사본을 복원할 수 있습니다. 실행 중인 DB를 임의로 교체하지 마세요.

## 7. 같은 네트워크의 팀원이 접속하기

`npm run start:lan` 또는 Windows CMD의 `scripts\start.cmd -Lan`으로 실행하고, 출력된 `LAN (...)` 주소를 같은 네트워크의 팀원에게 알려줍니다. 팀원은 로그인 없이 기본 기능을 사용합니다.

기본 실행은 이 PC에서만 접속됩니다. LAN 실행은 이 PC의 LAN 주소로 들어온 요청만 받고 임의 Host·다른 출처 요청은 거부하지만, **접속자 IP를 같은 서브넷으로 제한하지는 않습니다**(1.4.0부터). 신뢰할 수 있는 사설 네트워크에서만 켜고, 같은 서브넷으로 제한하려면 OS 방화벽을 쓰세요. Ubuntu는 `ufw`(예: `sudo ufw allow from 192.168.0.0/24 to any port 5173`), Windows는 인바운드 규칙의 원격 주소를 "로컬 서브넷"으로 제한하고, macOS는 처음 실행 시 뜨는 네트워크 연결 허용 창에서 허용합니다. 학교·공용 인터넷에 공개하는 배포 구성이 아닙니다.

## 8. Windows 실행기 (`start.cmd` / `start.ps1`)

Windows에서 더블클릭 한 번으로 설치·빌드·실행까지 하게 해 주는 편의 도구입니다. Ubuntu 서버·macOS에서는 쓰지 않고 `npm` 명령을 직접 실행합니다.

`scripts\start.cmd`는 프로젝트 최상위로 이동한 뒤, 실행 정책 제한 없이(`-ExecutionPolicy Bypass`) `scripts\start.ps1`을 호출하고 받은 옵션을 그대로 넘깁니다. 실패하면 창이 바로 닫히지 않도록 `pause`합니다(`HAEDAP_NO_PAUSE=1`이면 생략).

`scripts\start.ps1`이 하는 일:

1. **Node.js 찾기**: `-NodePath` 옵션 → `HAEDAP_NODE` 환경변수 → PATH의 `node` 순서. 없으면 Node.js 24 LTS 설치 안내 후 종료. 찾은 Node 폴더를 PATH 맨 앞에 넣어 `npm`도 같은 Node를 쓰게 함.
2. **런타임 점검**: `scripts/check-runtime.cjs`로 SQLite·FTS5 지원 확인, Node 주 버전이 24 이상인지 확인.
3. **패키지 설치**: `node_modules/next`가 없으면 `npm ci`.
4. **작업 실행** (`-Task`, 기본 `serve`)
   - `serve`: 빌드(`frontend/.next/BUILD_ID`)가 없으면 `npm run build` 후 `node scripts/run.mjs` 실행. `-Port`, `-Lan`을 `--port`, `--lan`으로 전달.
   - `build`: `npm run build` / `test`: `npm test` / `check`: 1~2단계만
   - `ingest`: `node scripts/ingest.mjs <-Document 경로>` (기본 `backend/knowledge/seed.json`)
5. Next.js 사용 통계 전송을 끔(`NEXT_TELEMETRY_DISABLED=1`).

## 9. 기존 프로젝트의 데이터를 유지하면서 새 버전으로 바꾸기

**기존 서버를 정상 종료한 후, 새 버전은 다른 폴더에 풀거나 클론하세요.**

1. 기존 실행 창에서 `Ctrl+C`로 서버를 종료합니다.
2. 새 버전을 별도 폴더에 준비합니다. 옛 폴더 위에 덮어쓰면 삭제 대상 레거시 파일이 남습니다.
3. 기존 최상위의 `data` 폴더(1.3.0 이하) 또는 `backend/data` 폴더 전체를 새 프로젝트의 **`backend/data`**로 복사합니다.
4. `.env`를 사용했다면 최상위로 복사합니다. 예전 설정이 `HAEDAP_DB_PATH=data/haedap.sqlite`라면 **`HAEDAP_DB_PATH=backend/data/haedap.sqlite`**로 바꿉니다.
5. `npm ci` → `npm run build` → `npm start` 순서로 실행합니다. 이전 `node_modules`, `.next`, `.next-dev`는 복사하지 않습니다.

DB 경로 선택 규칙:

- `.env`의 `HAEDAP_DB_PATH`가 우선합니다. 상대 경로의 기준은 항상 프로젝트 최상위이며 절대 경로도 됩니다.
- 설정이 없으면 `backend/data/haedap.sqlite`를 사용(없으면 생성)합니다.
- 설정이 없고 옛 `data/haedap.sqlite`만 있으면 그 파일을 계속 씁니다(자동 이동·삭제 없음).
- 양쪽에 모두 있으면 임의로 고르지 않고 시작을 멈춥니다. `.env`에 사용할 경로를 지정하세요.

1.2.2 이전 버전의 DB는 기존 `admin`의 사용자 ID·자료 소유권을 유지하면서 비밀번호를 `1234`, 역할을 관리자로 한 번 갱신합니다. 브라우저에만 남아 있던 미저장 초안은 이전 버전에서 JSON으로 내보낸 뒤 **보고서 → 초안 JSON 가져오기**로 옮길 수 있습니다.

## 10. 문제 해결

| 증상 | 확인할 내용 |
|---|---|
| node/npm 명령을 찾지 못함 | 공식 Node.js 24 LTS를 npm과 함께 설치하고 터미널을 새로 열기 |
| PowerShell에서 npm이 막힘 | `npm.cmd`로 실행하거나 CMD 창 사용 |
| SQLite/FTS5 오류 | `node scripts/check-runtime.cjs` 확인. VS Code 내장 런타임 등 대신 공식 Node.js 사용 |
| 패키지 설치 실패 | 인터넷·프록시를 확인하고 프로젝트 폴더에서 `npm ci` 재실행 |
| "먼저 npm run build를 실행해 주세요" | `npm run build` 실행 |
| API 연결 실패 | 백엔드(API 서버)가 켜져 있는지 확인. 개발 중이면 `npm run dev:backend`. 8000 포트를 바꿨다면 `.env`의 `HAEDAP_API_ORIGIN`을 고친 뒤 두 프로세스를 모두 재시작했는지 확인 |
| 포트 사용 중 | 기존 실행 창을 종료하거나 `npm start -- --port 5174` |
| 수정한 화면이 반영되지 않음 | 일반 실행이면 재빌드 후 재시작. 개발 중이면 `npm run dev:backend`와 `npm run dev:frontend`를 함께 실행 |
| 8000 포트로 열었더니 "API server only" | 화면은 Next.js 주소 `http://127.0.0.1:5173`으로 접속 |
| "API port 8000 is in use" | 다른 프로그램이 8000을 쓰는 중. `.env`에 `HAEDAP_API_ORIGIN=http://127.0.0.1:8100` 지정 후 두 프로세스 재시작 |
| 큰 PDF·백업 업로드가 끊김 | 101MB 이하인지 확인(`next.config.mjs`의 `proxyClientMaxBodySize`) |
| DB가 양쪽에 있다는 오류 | `.env`의 `HAEDAP_DB_PATH`로 사용할 DB 지정 |
| 관리자 로그인 실패 | `admin / 1234` 확인. 기존 서버 종료 후 새 폴더에서 실행 |
| 등록·수정·삭제 버튼이 안 보임 | 관리자 로그인 여부 확인 |
| 문서가 안 보임 | 열람 범위·사용 중/이전/폐기 필터 확인 |
| 운항 화면이 비어 있음 | 선박·기록 등록 및 기간 확인. 가상 예시는 관리자 버튼으로 등록 |
| PDF 추출 실패 | 암호·손상·스캔 여부 확인. 텍스트 PDF 또는 페이지별 본문 입력 |
| 보고서 수정 불가 | 검토 중/승인 완료 상태는 복사 후 새 초안으로 작성 |
| 검토 대기 상태 | 관리자 계정으로 관리 → 승인에서 처리 |

## 10. 해사 데이터 Tool (선택)

기본 Node/SQLite 앱과 별도로 실행되는 역할4 도구입니다. 코드는 `backend/maritime_data/`, 계약은 [API 명세](specs/maritime-data-api.md)와 [데이터 명세](specs/maritime-data.md), 테이블·ERD는 [데이터 모델](data-model.md#9-postgresql-해사-데이터-tool-선택)에 있습니다. 아래 명령은 저장소 루트에서 실행합니다.

### 설치와 실행

Python 3.12 또는 3.13, 별도 PostgreSQL 및 준비된 해사 데이터 스키마가 필요합니다. 기존 `.venv`가 있으면 재사용합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/maritime_data/requirements.lock.txt
if (-not (Test-Path -LiteralPath .env.local)) {
    Copy-Item backend/maritime_data/.env.example .env.local
}
```

루트 `.env.local`에 `DATABASE_URL`(PostgreSQL 연결 주소)과 `MARITIME_DATA_API_TOKEN`(직접 생성한 32자 이상 토큰)을 설정합니다. 기존 파일에는 필요한 키만 추가하고 덮어쓰지 않습니다. 기본 앱의 `.env`와는 별도 설정입니다. 원본·CSV·DB·비밀번호·토큰은 Git에 넣지 않습니다.

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.maritime_data.api:create_app --factory --host 127.0.0.1 --port 8001
```

개발용 API 명세는 <http://127.0.0.1:8001/docs>에서 열고 Authorize에 API 토큰을 입력합니다. `/api/health`의 `database_checked=false`는 프로세스만 확인했으며 DB를 검증하지 않았다는 뜻입니다. 실제 DB 조회는 토큰을 포함한 `/api/maritime-data/query`로 확인합니다. 503이면 PostgreSQL 실행·연결·스키마 적재 상태를 확인하세요. 이 도구는 독립 루프백 서비스이며 팀 화면에 자동 연결되지 않습니다.

### 전처리·적재·생성·검증

```powershell
.\.venv\Scripts\python.exe backend/maritime_data/scripts/prepare_maritime_data.py --source D:/Data --out data/maritime-data/new-run
./backend/maritime_data/scripts/load-maritime-data.ps1 -DataDir data/maritime-data/new-run
.\.venv\Scripts\python.exe backend/maritime_data/scripts/describe_maritime_data.py
.\.venv\Scripts\python.exe -m pytest -q backend/maritime_data/tests
.\.venv\Scripts\python.exe backend/maritime_data/scripts/test_prepare_maritime_data.py
```

이미 전처리한 CSV가 있으면 첫 명령을 생략합니다. 적재 스크립트는 Windows의 `psql.exe`를 사용하며 기본 PostgreSQL 경로가 다르면 `-PgBin`을 지정합니다. 로컬 DB만 지원하고 기존 `maritime_data` 스키마가 있으면 중단합니다. 실패 시 단일 적재 트랜잭션을 롤백합니다. 새 데이터 버전은 `schema/verify_load.sql`의 기대 건수를 먼저 검토합니다.

설명 생성기는 기본적으로 `schema/schema.sql`·`dictionary.json`만 다시 생성합니다. 다른 출력 폴더는 `--out`으로 지정합니다. 이전 `--docs` 옵션과 `DATA_CONTRACT.md` 자동 생성은 제거했으며, 설명·ERD는 최상위 docs에서 직접 관리합니다.

`MARITIME_DATA_TEST_DATABASE_URL`을 지정해야 기존 PostgreSQL 적재 데이터를 사용하는 읽기 전용 테스트가 실행됩니다. 미설정 시 이 테스트는 건너뛰며 단위 테스트 통과만으로 실 DB 검증을 주장하지 않습니다. API가 조회할 DB 사용자는 승인 뷰·출처 테이블에 필요한 읽기 권한만 갖도록 설정하는 것을 권장합니다. 도구의 READ ONLY 트랜잭션은 DB 사용자의 권한 자체를 바꾸지 않습니다.

### 이전 역할4 환경의 이름 전환

이전 `role4/.env.local`을 사용한 환경은 필요한 설정을 저장소 루트 `.env.local`로 옮깁니다. 기존 `role4` 스키마·설정이 있으면 Tool을 중지하고 아래 미리보기를 확인한 뒤 이름 전환이 필요한 경우에만 `--apply`를 사용합니다.

```powershell
.\.venv\Scripts\python.exe backend/maritime_data/scripts/migrate_maritime_data.py
# 미리보기 확인 후 적용이 필요한 경우에만:
.\.venv\Scripts\python.exe backend/maritime_data/scripts/migrate_maritime_data.py --apply
```

양쪽 스키마나 충돌하는 설정이 있으면 중단합니다. 변경된 설정은 `.env.local.before-maritime-data`에 백업하고 데이터 레코드·원본 폴더는 다시 쓰거나 이동하지 않습니다. DB 이름 전환은 SQLite와의 통합이나 공식 입력 검증을 의미하지 않습니다.

### 팀 앱 연결 시 참고

Python 호출자는 `from backend.maritime_data import query, calculations, agent`로 공통 로직을 사용할 수 있습니다. 내부 API(현재 Node)의 HTTP 어댑터·키 매핑·권한·감사 구현은 후속 작업입니다. 독립 API의 토큰은 서버에 보관하고 브라우저로 보내지 않습니다. 현재 구현 범위와 경계 제안은 [아키텍처](architecture.md#8-해사-데이터-tool의-경계-선택), [ADR 0008](adr/0008-maritime-data-tool-boundary.md)를 참고하세요.

### 원본 확보·공개 참조 자료·기존 데이터 버전

이 저장소에는 코드, 데이터 정의, SQL, API 계약만 포함합니다. 원본·전처리 CSV, PostgreSQL 데이터 디렉터리, 로그인 정보는 포함하지 않습니다. 공개 열람 가능과 재배포 허용은 다르므로 이용조건이 확인되지 않은 원본을 GitHub에 재게시하지 않았습니다.

#### 전처리 원본 6종

`backend/maritime_data/scripts/prepare_maritime_data.py`는 아래 파일명을 기준으로 원본 폴더를 재귀 검색합니다. 팀 보유본 또는 출처에서 해당 버전을 확보해야 하며 최신 웹 다운로드가 동일 파일·동일 건수를 보장하지는 않습니다.

| ID | 원본 파일 | 용도 |
|---|---|---|
| DS-001 | `eu_mrv_vessel_annual_2018_2022.csv` | 실제 MRV 과거 보고기간 자료 |
| DS-002 | `해양수산부_선박_AIS_동적정보_20220101.csv` | 마스킹 AIS 참고자료, 선박 자동 연결 제외 |
| DS-003 | `UpdatedPub150.csv` | WPI 항구 참조 |
| DS-004 | `Smart-Maritime-Council-Standardised-Vessel-Dataset-SVD-for-Noon-Reports-and-Emissions-Reporting-V2-May-2025.xlsx` | SVD 컬럼 설계 참고 |
| DS-005 | `2025-v57-12092026-EU_MRV_Publication_of_information.xlsx` | 실제 MRV 보고 자료 |
| DS-006 | `synthetic_noon_daily_2025.csv` | 개발·검증용 합성 Noon |

실제 MRV 두 자료와 합성 Noon을 조회 대상으로 선정했고 AIS·항구·SVD는 참고 자료로만 보존합니다. 원본별 URL·SHA256은 전처리 출력 `source_files.csv`와 `summary.json`에 보존됩니다. 팀에서 데이터 전달 시 이 두 파일, CSV 6개 및 원본 추적에 필요한 `raw_records.jsonl`을 함께 전달하세요. 정확한 기존 버전의 재확보가 안 되면 새 자료를 기존 정답 건수에 맞추지 말고 새 데이터 버전으로 검증해야 합니다.

#### 공개 참조 자료

| 자료 | 보유 결과 및 제한 | 처리 코드 |
|---|---|---|
| GISIS EEDI | 11,244행, 익명·반올림, IMO 번호 없음 | `prepare_gisis_eedi.py` |
| IMO DCS 연차 보고서 | 2019~2024 공개 집계, 선박 단위 결합 불가 | `prepare_open_cii_references.py` |
| Wikidata / MarineVessels | MRV 25,240척 중 15,956척에 DWT 후보, 법정 검증값 아님 | `prepare_open_cii_references.py` |

GISIS 정규화는 `python backend/maritime_data/scripts/prepare_gisis_eedi.py INPUT.xlsx OUTPUT_DIR`로 실행합니다. 공개 CII 참조 처리 스크립트는 `data/maritime-data/2026-09-30-v2/reference/`의 수집 완료 파일을 입력으로 요구하며 자동 수집기가 아닙니다. 입력 구조: `reference/marine-vessels-2015/marine_vessels.csv`, `reference/wikidata-vessel-particulars/wikidata_ships_with_deadweight.csv`, `reference/imo-dcs-public-reports/`입니다. GISIS EEDI 원본 갱신일은 2025-12-02이며 익명 자료이므로 실제 MRV와 연결하지 않습니다. DWT 후보 출처 간 5% 초과 충돌은 검토 대상으로 남깁니다.

공식 CII 산정에 필요한 동일 선박·동일 연도의 검증된 연료별 사용량, 항해거리, 적용 선종·용량 및 보정 조건은 아직 충분히 확보되지 않았습니다. 공개 집계와 제원 후보를 공식 입력으로 자동 승격하지 않습니다.

#### 기존 데이터 버전

2026-09-30 로컬 적재 기록: MRV 80,552행 중 조회 대상 79,032행, Partial 1,520행은 보존하되 기본 조회에서 제외. 합성 Noon 4,380행·238항차이며 거리 0인 기록 557행은 연료량을 보존합니다. 이 수치는 저장소에 데이터가 포함되거나 이번 작업에서 DB를 재검증했다는 의미가 아닙니다. 다른 데이터 버전에서는 `backend/maritime_data/schema/verify_load.sql`의 기대값을 검토하세요.
