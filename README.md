# 해답 — SEA THE ANSWER

현재 버전 **1.3.1** · 마지막 업데이트 **2026-10-08**

선원의 업무를 돕는 **선박 특화 LLM 시스템**입니다. 선내 매뉴얼·해사 규정 같은 문서를 근거로 질문에 답하고(RAG), 선박의 일별 운항 기록을 조회·분석·계산(Tool Calling)해서 두 결과를 하나의 답변과 보고서 초안으로 묶어 줍니다. 동국대학교 캡스톤 디자인2 팀 프로젝트입니다.

## 무엇을 할 수 있나

| 화면 | 기능 |
|---|---|
| 통합 질문 | 문서 근거 + 선택한 선박·기간의 운항 수치·추이를 함께 답변, 근거 페이지·원문 PDF 열기, 입력 기준 비교, 보고서에 담기 |
| 문서 | 텍스트 PDF 등록·추출 검토, 메타데이터·열람 범위, 개정 버전 관리 |
| 운항 정보 | 선박·일별 기록 관리, CSV 일괄 등록, 지표 차트·선박 비교, 배출량·항해 시간 계산 |
| 보고서 | Noon / MRV 검토 초안 자동 생성, 편집·저장, 검토 요청 → 관리자 승인 |
| 관리 | 계정·역할, 승인, 질의·변경·오류 로그, 백업·복구 |

일반 기능은 로그인 없이 쓰고, 등록·수정·삭제·승인·백업은 관리자(기본 **`admin / 1234`**)만 할 수 있습니다.

**현재 구현 범위**: 문서 검색은 SQLite FTS5(BM25) 키워드 검색, 답변은 기본적으로 원문 발췌이며, 외부 LLM은 `.env`로 켜는 선택 기능입니다. 벡터·하이브리드 RAG, Local LLM, 공식 CII 계산, 규정 적용 자동 판정, DOCX·PPT 등록은 아직 연결 전입니다. 자세한 범위와 연결 계획은 [`docs/plans/2026-10-08-team-module-integration.md`](docs/plans/2026-10-08-team-module-integration.md)를 보세요.

## 프로젝트 구조

```text
sea-the-answer/
├─ frontend/            Next.js 16 App Router + React 19 화면 (JSX)
│  ├─ src/app/          페이지 라우트: /chat, /documents, /operations, /reports, /admin
│  ├─ src/views/        화면 JSX
│  ├─ src/workspace/    상태 Provider·컨트롤러(이벤트, API 호출)
│  ├─ src/lib/          API 클라이언트, CSV·PDF 처리, 상태 모델
│  ├─ src/styles/       CSS
│  ├─ public/           글꼴, PDF.js, Leaflet 등 오프라인 정적 리소스
│  └─ tests/
├─ backend/             Node.js HTTP API + SQLite
│  ├─ server.mjs        단일 접속점(게이트웨이): /api는 직접 처리, 나머지는 Next.js로 전달
│  ├─ api.mjs           라우팅·인증·CSRF
│  ├─ workspace.mjs     권한·CRUD·승인·보고서·백업
│  ├─ db.mjs, knowledge.mjs, rag.mjs   DB·문서 인덱싱·검색·답변
│  ├─ analysis.mjs, tools.mjs          운항 집계·통합 답변·계산 도구
│  ├─ knowledge/seed.json              최초 실행 시 넣는 기본 문서
│  ├─ data/             (실행 시 생성) SQLite DB와 backups/
│  ├─ maritime_data/    (선택) Python 조회·계산 Tool + PostgreSQL 전처리·SQL·테스트
│  └─ tests/
├─ scripts/             실행(run.mjs)·빌드·Windows 실행기·문서 수집·브라우저 검증
├─ docs/                설계·명세·계획·ADR 등 모든 프로젝트 문서
├─ start.cmd            Windows 더블클릭 실행 진입점
├─ package.json         의존성과 npm 명령 (설치는 최상위에서 한 번)
├─ .env.example         환경설정 예시
└─ AGENTS.md            사람·에이전트 공통 작업 지침
```

구조와 요청 흐름은 [`docs/architecture.md`](docs/architecture.md)에 자세히 정리했습니다.

## 설치해야 하는 것

| 항목 | 버전 / 비고 |
|---|---|
| **Node.js** | **24 LTS 이상** (공식 배포판 권장, npm 포함). 내장 `node:sqlite`의 FTS5를 사용하므로 다른 런타임으로는 실행되지 않습니다 |
| 브라우저 | 최신 Chrome 또는 Edge (macOS는 Safari도 열리지만 검증 범위 밖) |
| 인터넷 | 최초 `npm ci`(패키지 설치) 때만 필요. 설치·빌드 후에는 오프라인 실행 |
| Git | 저장소를 클론할 때만 필요 (ZIP으로 받으면 불필요) |
| (선택) Playwright Chromium | 브라우저 자동 검증(`npm run test:browser`)을 돌릴 때만 |
| (선택) OpenAI 호환 API 키 | 통합 질문의 **AI 답변** 옵션을 쓸 때만 |

기본 앱에는 별도의 DB 서버, Python, Docker가 필요 없습니다. 선택 기능인 해사 데이터 Tool은 Python 3.12/3.13과 별도 PostgreSQL을 사용합니다. npm 패키지는 `next`, `react`, `react-dom`과 개발용 `playwright`뿐이며 `npm ci`가 자동 설치합니다.

## Windows에서 실행하기

### 1) Node.js 설치

1. <https://nodejs.org> 에서 **24 LTS Windows Installer(.msi)** 를 받아 기본 옵션으로 설치합니다.
2. 열려 있던 터미널을 모두 닫고 새로 연 뒤 확인합니다.

```bat
node --version
npm --version
```

`v24.`으로 시작하면 됩니다.

### 2) 가장 간단한 방법 — `start.cmd`

1. 프로젝트 폴더(`package.json`과 `start.cmd`가 있는 곳)를 엽니다.
2. **`start.cmd`를 더블클릭**합니다. 처음에는 패키지 설치와 Next.js 빌드를 자동으로 하므로 몇 분 걸립니다. 창을 닫지 마세요.
3. `SEA THE ANSWER (Next.js): http://127.0.0.1:5173` 이 보이면 브라우저에서 그 주소를 엽니다.
4. 끌 때는 창에서 `Ctrl+C`를 누르거나 창을 닫습니다.

옵션은 CMD 창에서 프로젝트 폴더로 이동한 뒤 붙여서 실행합니다.

| 명령 | 하는 일 |
|---|---|
| `start.cmd -Port 5174` | 다른 포트로 실행 |
| `start.cmd -Lan` | 같은 네트워크의 팀원 접속 허용 |
| `start.cmd -Task dev` | 개발 모드(수정 즉시 반영) |
| `start.cmd -Task build` | 다시 빌드만 |
| `start.cmd -Task test` | 테스트 |

### 3) 터미널에서 직접 실행

PowerShell 또는 CMD에서 프로젝트 폴더로 이동한 뒤:

```powershell
node scripts/check-runtime.cjs   # SQLite + FTS5 ready 가 나와야 함
npm ci                           # 최초 1회(또는 package-lock.json 변경 시)
npm run build                    # 최초 1회(또는 코드 변경 후)
npm start
```

PowerShell에서 `npm` 실행이 "스크립트를 실행할 수 없습니다"로 막히면 `npm` 대신 `npm.cmd`를 쓰거나 CMD 창에서 실행하세요.

## macOS에서 실행하기

### 1) Node.js 설치

다음 중 하나를 사용합니다.

- **공식 설치 파일(권장)**: <https://nodejs.org> 에서 24 LTS macOS Installer(.pkg)를 받아 설치
- **Homebrew**: `brew install node@24` 후 안내에 따라 PATH 추가
- **nvm**: `nvm install 24 && nvm use 24`

터미널(Terminal.app)을 새로 열고 확인합니다.

```bash
node --version   # v24.x
npm --version
```

### 2) 실행

macOS에는 `start.cmd`가 없으므로 터미널에서 실행합니다.

```bash
cd ~/경로/sea-the-answer
node scripts/check-runtime.cjs   # SQLite + FTS5 ready 확인
npm ci                           # 최초 1회
npm run build                    # 최초 1회(또는 코드 변경 후)
npm start
```

`SEA THE ANSWER (Next.js): http://127.0.0.1:5173` 이 나오면 브라우저에서 엽니다. 종료는 `Ctrl+C`입니다. LAN 접속을 켜면 macOS가 "들어오는 네트워크 연결 허용" 창을 띄울 수 있으니 **허용**을 누르세요.

## 공통 명령 (Windows·macOS 동일)

| 명령 | 하는 일 |
|---|---|
| `npm start` | 빌드된 화면 + API 서버 실행 (기본 5173 포트, 이 PC에서만 접속) |
| `npm start -- --port 5174` | 다른 포트로 실행 |
| `npm run start:lan` | 같은 네트워크(연결된 IPv4 서브넷)의 기기 접속 허용 |
| `npm run dev` | 개발 모드. 코드 수정이 바로 반영됨 (빌드 결과는 `frontend/.next-dev`) |
| `npm run build` | 배포용 화면 빌드 (`frontend/.next`) |
| `npm test` | 백엔드·프런트엔드·실행기 단위/회귀 테스트 |
| `npx playwright install chromium` → `npm run test:browser` | 실제 브라우저 업무 흐름 검증 (임시 DB 사용) |
| `npm run ingest -- backend/knowledge/seed.json` | JSON 문서 일괄 수집 (운영자용) |
| `npm run check` | Node.js 런타임(SQLite·FTS5) 점검 |

꼭 기억할 점:

- 접속 주소는 항상 마지막에 출력되는 **`SEA THE ANSWER` 주소(5173 또는 지정 포트)** 입니다. 로그 중간의 Next.js 임시 포트로 접속하면 API가 동작하지 않습니다.
- `node backend/server.mjs`만 실행하면 API만 켜지고 화면은 나오지 않습니다. `npm start` 또는 `npm run dev`를 사용하세요.
- DB는 기본적으로 `backend/data/haedap.sqlite`에 생성됩니다. 시작 로그의 `DB:` 줄에서 실제 경로를 확인할 수 있습니다.

### 환경설정 (선택)

`.env.example`을 `.env`로 복사해 사용합니다. `.env`는 Git에 올리지 않습니다.

```bash
cp .env.example .env        # macOS
copy .env.example .env      # Windows CMD
```

| 변수 | 설명 |
|---|---|
| `PORT` | 기본 포트 (기본 5173). `--port`가 우선 |
| `HAEDAP_DB_PATH` | DB 파일 경로. 상대 경로는 프로젝트 최상위 기준 |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | 둘 다 설정하면 통합 질문에서 **AI 답변** 선택 가능. 키는 브라우저로 보내지 않음 |

## 처음 써 보기

1. 사이드바 **관리자 로그인** → `admin / 1234`
2. **운항 정보 → 가상 예시로 둘러보기** (가상 선박 3척, 7일치 기록 등록)
3. **통합 질문**에서 선박·기간을 고르고 `선택한 선박의 연료 추이를 분석해줘` 질문
4. **보고서에 담기 → 저장**, 또는 **보고서 → 운항 기록으로 초안 만들기**에서 Noon·MRV 초안 생성

화면별 자세한 사용법, 권한, CSV 형식, 백업·복구, 기존 데이터 이전, 문제 해결은 [`docs/user-guide.md`](docs/user-guide.md)에 있습니다.

## 해사 데이터 Tool (선택)

역할4의 실제 MRV·합성 Noon 전처리, PostgreSQL 적재, 읽기 전용 조회 및 CO₂ 계산 도구는 [`backend/maritime_data/`](backend/maritime_data/)에 있습니다. 기본 Node/SQLite 앱과 별도로 실행하며, 현재 화면·게이트웨이가 이 도구를 자동 호출하지 않습니다. 원본 데이터·DB·비밀번호는 저장소에 포함하지 않습니다.

설치·실행·데이터 확보·기존 `role4` 환경의 이전은 [운영 안내](docs/user-guide.md#10-해사-데이터-tool-선택)를 따르세요. 호출 형식은 [해사 데이터 API 명세](docs/specs/maritime-data-api.md), 데이터 선택·품질 규칙은 [데이터 명세](docs/specs/maritime-data.md), 테이블·ERD는 [데이터 모델](docs/data-model.md#9-postgresql-해사-데이터-tool-선택)에 있습니다.

## 문서

| 문서 | 내용 |
|---|---|
| [`docs/README.md`](docs/README.md) | 전체 문서 목록과 작성 규칙 |
| [`docs/architecture.md`](docs/architecture.md) | 시스템 구조, 요청 흐름, 모듈 경계, 보안 경계 |
| [`docs/data-model.md`](docs/data-model.md) | SQLite 및 선택 PostgreSQL 테이블, 상태 값, 백업 범위 |
| [`docs/user-guide.md`](docs/user-guide.md) | 사용·운영 안내, 문제 해결 |
| [`docs/specs/`](docs/specs/) | API·통합 답변 등 구현 계약 |
| [`docs/plans/`](docs/plans/) | 작업 계획과 진행 상태 |
| [`docs/adr/`](docs/adr/) | 주요 설계 결정 기록 |
| [`docs/changelog.md`](docs/changelog.md) | 변경 이력과 검증 기록 |
| [`AGENTS.md`](AGENTS.md) | 사람·코딩 에이전트 공통 작업 지침 |

팀 보고서는 Notion에서 관리합니다: <https://app.notion.com/p/dudco/3dc1cb63e55380e98972eda1ce1040b5>
