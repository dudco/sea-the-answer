# 해답 — SEA THE ANSWER

현재 버전 **1.4.0** · 마지막 업데이트 **2026-10-08**

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
├─ frontend/            Next.js 16 App Router + React 19 화면 (JSX) — 사용자가 접속하는 공개 진입점
│  ├─ src/app/          페이지 라우트: /chat, /documents, /operations, /reports, /admin
│  ├─ src/views/        화면 JSX
│  ├─ src/workspace/    상태 Provider·컨트롤러(이벤트, API 호출)
│  ├─ src/lib/          API 클라이언트, CSV·PDF 처리, 상태 모델
│  ├─ src/styles/       CSS
│  ├─ public/           글꼴, PDF.js, Leaflet 등 오프라인 정적 리소스
│  └─ tests/
├─ backend/             Node.js HTTP API + SQLite
│  ├─ server.mjs        내부 API 서버(127.0.0.1:8000). Next.js가 /api/* 를 이리로 전달
│  ├─ api.mjs           라우팅·인증·CSRF
│  ├─ workspace.mjs     권한·CRUD·승인·보고서·백업
│  ├─ db.mjs, knowledge.mjs, rag.mjs   DB·문서 인덱싱·검색·답변
│  ├─ analysis.mjs, tools.mjs          운항 집계·통합 답변·계산 도구
│  ├─ knowledge/seed.json              최초 실행 시 넣는 기본 문서
│  ├─ data/             (실행 시 생성) SQLite DB와 backups/
│  └─ tests/
├─ scripts/             일반 실행(run.mjs)·Windows 실행기(start.cmd, start.ps1)·문서 수집·브라우저 검증
├─ docs/                설계·명세·계획·ADR 등 모든 프로젝트 문서
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

별도의 DB 서버, Python, Docker는 필요 없습니다. npm 패키지는 `next`, `react`, `react-dom`과 개발용 `playwright`뿐이며 `npm ci`가 자동 설치합니다.

## Windows에서 실행하기

### 1) Node.js 설치

1. <https://nodejs.org> 에서 **24 LTS Windows Installer(.msi)** 를 받아 기본 옵션으로 설치합니다.
2. 열려 있던 터미널을 모두 닫고 새로 연 뒤 확인합니다.

```bat
node --version
npm --version
```

`v24.`으로 시작하면 됩니다.

### 2) 가장 간단한 방법 — `scripts\start.cmd`

1. 프로젝트 폴더 안의 `scripts` 폴더를 엽니다.
2. **`start.cmd`를 더블클릭**합니다. 처음에는 패키지 설치와 Next.js 빌드를 자동으로 하므로 몇 분 걸립니다. 창을 닫지 마세요.
3. `SEA THE ANSWER (Next.js): http://127.0.0.1:5173` 이 보이면 브라우저에서 그 주소를 엽니다.
4. 끌 때는 창에서 `Ctrl+C`를 누르거나 창을 닫습니다.

옵션은 CMD 창에서 프로젝트 최상위 폴더로 이동한 뒤 붙여서 실행합니다. `start.cmd`가 하는 일은 [`docs/user-guide.md`](docs/user-guide.md#8-windows-실행기-startcmd--startps1)에 정리했습니다.

| 명령 | 하는 일 |
|---|---|
| `scripts\start.cmd -Port 5174` | 다른 포트로 실행 |
| `scripts\start.cmd -Lan` | 같은 네트워크의 팀원 접속 허용 |
| `scripts\start.cmd -Task build` | 다시 빌드만 |
| `scripts\start.cmd -Task test` | 테스트 |

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

`start.cmd`는 Windows 전용이므로 macOS에서는 터미널에서 실행합니다.

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
| `npm start` | 빌드된 화면(Next.js :5173) + 내부 API 서버(:8000) 실행, 이 PC에서만 접속 |
| `npm start -- --port 5174` | 다른 포트로 실행 |
| `npm run start:lan` | 같은 네트워크(연결된 IPv4 서브넷)의 기기 접속 허용 |
| `npm run dev:backend` + `npm run dev:frontend` | 개발 모드. 터미널 두 개에서 각각 실행 (아래 "개발 모드" 참고) |
| `npm run build` | 배포용 화면 빌드 (`frontend/.next`) |
| `npm test` | 백엔드·프런트엔드·실행기 단위/회귀 테스트 |
| `npx playwright install chromium` → `npm run test:browser` | 실제 브라우저 업무 흐름 검증 (임시 DB 사용) |
| `npm run ingest -- backend/knowledge/seed.json` | JSON 문서 일괄 수집 (운영자용) |
| `npm run check` | Node.js 런타임(SQLite·FTS5) 점검 |

꼭 기억할 점:

- 접속 주소는 **Next.js 주소 `http://127.0.0.1:5173`(또는 지정 포트)** 하나입니다. Next.js가 `/api/*` 요청을 내부 API 서버(`127.0.0.1:8000`)로 넘겨 줍니다. 8000 포트는 직접 열 필요가 없습니다.
- `node backend/server.mjs`만 실행하면 API만 켜지고 화면은 나오지 않습니다. 일반 실행은 `npm start`, 개발은 아래처럼 두 프로세스를 함께 띄우세요.
- DB는 기본적으로 `backend/data/haedap.sqlite`에 생성됩니다. 시작 로그의 `DB:` 줄에서 실제 경로를 확인할 수 있습니다.

## 개발 모드 (Windows·macOS 동일)

개발할 때는 백엔드와 프론트를 **각각 직접** 실행합니다. 빌드(`npm run build`)는 필요 없고, 터미널(또는 VS Code 터미널 탭)을 두 개 엽니다. 둘 다 프로젝트 최상위 폴더에서 실행합니다.

```bash
# 터미널 1 — 내부 API 서버(127.0.0.1:8000), 파일을 고치면 자동 재시작
npm run dev:backend

# 터미널 2 — Next.js 개발 서버(127.0.0.1:5173), 화면 수정이 바로 반영(HMR)
npm run dev:frontend
```

브라우저에서는 **`http://127.0.0.1:5173`** (Next.js)으로 접속합니다. 화면은 Next.js가 그리고, `/api/*`는 Next.js가 API 서버로 넘기므로 쿠키·CSRF·권한 검사가 운영과 똑같이 동작합니다.

| 프로세스 | 명령이 실제로 하는 일 | 포트 |
|---|---|---|
| 백엔드 | `node --watch backend/server.mjs` | 8000 (`HAEDAP_API_ORIGIN`의 포트, 이 PC 내부 전용) |
| 프론트 | `next dev frontend --webpack -H 127.0.0.1 -p 5173` | 5173 (사용자가 여는 주소) |

- 실행 순서는 상관없습니다. 백엔드가 아직 안 떴으면 화면의 API 호출이 실패하니, 백엔드를 켠 뒤 새로고침하세요.
- 개발 빌드 결과는 `frontend/.next-dev`에 따로 생겨서 `npm start`용 빌드(`frontend/.next`)를 덮어쓰지 않습니다.
- LAN 접속 테스트: `npm run dev:backend -- --lan` 과 `npm run dev:frontend -- -H 0.0.0.0`.
- 5173 포트를 바꾸려면 두 쪽을 같이: `npm run dev:frontend -- -p 5174`, `npm run dev:backend -- --public-port 5174` (또는 `.env`의 `PORT=5174`).
- 8000 포트가 이미 쓰이고 있으면 `.env`에 `HAEDAP_API_ORIGIN=http://127.0.0.1:8100` 처럼 지정합니다. 양쪽이 시작할 때 이 값을 함께 읽으므로 재시작만 하면 됩니다.
- Next.js 사용 통계 전송을 끄려면 한 번만 `npx next telemetry disable`.
- 종료는 각 터미널에서 `Ctrl+C`.

### 환경설정 (선택)

`.env.example`을 `.env`로 복사해 사용합니다. `.env`는 Git에 올리지 않습니다.

```bash
cp .env.example .env        # macOS
copy .env.example .env      # Windows CMD
```

| 변수 | 설명 |
|---|---|
| `PORT` | 사용자가 여는 Next.js 포트 (기본 5173). `--port`가 우선 |
| `HAEDAP_API_ORIGIN` | 내부 API 서버 주소 (기본 `http://127.0.0.1:8000`). API 서버와 Next.js가 **실행할 때** 함께 읽음 — 바꾸면 재시작만 하면 되고 다시 빌드할 필요 없음 |
| `HAEDAP_DB_PATH` | DB 파일 경로. 상대 경로는 프로젝트 최상위 기준 |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | 둘 다 설정하면 통합 질문에서 **AI 답변** 선택 가능. 키는 브라우저로 보내지 않음 |

## 처음 써 보기

1. 사이드바 **관리자 로그인** → `admin / 1234`
2. **운항 정보 → 가상 예시로 둘러보기** (가상 선박 3척, 7일치 기록 등록)
3. **통합 질문**에서 선박·기간을 고르고 `선택한 선박의 연료 추이를 분석해줘` 질문
4. **보고서에 담기 → 저장**, 또는 **보고서 → 운항 기록으로 초안 만들기**에서 Noon·MRV 초안 생성

화면별 자세한 사용법, 권한, CSV 형식, 백업·복구, 기존 데이터 이전, 문제 해결은 [`docs/user-guide.md`](docs/user-guide.md)에 있습니다.

## 문서

| 문서 | 내용 |
|---|---|
| [`docs/README.md`](docs/README.md) | 전체 문서 목록과 작성 규칙 |
| [`docs/architecture.md`](docs/architecture.md) | 시스템 구조, 요청 흐름, 모듈 경계, 보안 경계 |
| [`docs/data-model.md`](docs/data-model.md) | SQLite 테이블과 JSON 필드, 상태 값, 백업 형식 |
| [`docs/user-guide.md`](docs/user-guide.md) | 사용·운영 안내, 문제 해결 |
| [`docs/specs/`](docs/specs/) | API·통합 답변 등 구현 계약 |
| [`docs/plans/`](docs/plans/) | 작업 계획과 진행 상태 |
| [`docs/adr/`](docs/adr/) | 주요 설계 결정 기록 |
| [`docs/changelog.md`](docs/changelog.md) | 변경 이력과 검증 기록 |
| [`AGENTS.md`](AGENTS.md) | 사람·코딩 에이전트 공통 작업 지침 |

팀 보고서는 Notion에서 관리합니다: <https://app.notion.com/p/dudco/3dc1cb63e55380e98972eda1ce1040b5>
