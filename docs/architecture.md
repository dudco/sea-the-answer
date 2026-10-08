# 아키텍처

> 대상 버전: 1.3.2 · 최종 확인: 2026-10-08 (코드 대조)
> 이 문서는 **현재 구현**을 설명합니다. 앞으로 바꿀 계획은 [`plans/`](plans/), 바뀌지 않을 결정의 이유는 [`adr/`](adr/)에 있습니다.

## 1. 한눈에 보기

해답은 한 대의 PC에서 도는 **로컬 웹 애플리케이션**입니다. 프로세스는 두 개이고, 사용자는 하나의 주소(기본 `http://127.0.0.1:5173`)로만 접속합니다.

```mermaid
flowchart LR
  B[브라우저<br/>React UI] -->|HTTP :5173| G
  subgraph PC[실행 PC]
    R[npm start: scripts/run.mjs<br/>개발: 터미널 2개에서 직접 실행]
    G[backend/server.mjs<br/>게이트웨이 + API]
    N[Next.js<br/>127.0.0.1:임시포트]
    D[(SQLite<br/>backend/data/haedap.sqlite)]
    K[backups/*.json]
    R -. 실행·종료 .-> N
    R -. 실행·종료 .-> G
    G -->|/api/*| A[api.mjs → workspace / analysis / rag / tools]
    G -->|그 외 화면·리소스| N
    A --> D
    A --> K
  end
  A -. 선택: OPENAI_API_KEY 설정 시 .-> O[(외부 LLM API)]
```

- **일반 실행** `npm start` → `scripts/run.mjs`가 `next start`를 루프백 임시 포트로 먼저 띄우고, 준비되면 `backend/server.mjs`를 `HAEDAP_FRONTEND_ORIGIN`과 함께 띄웁니다. 둘 중 하나가 죽으면 둘 다 종료합니다. Windows의 `start.cmd` → `scripts/start.ps1` → (필요 시 `npm ci`, `npm run build`) → `scripts/run.mjs`.
- **개발 실행**은 래퍼 없이 두 프로세스를 각각 띄웁니다([ADR 0005](adr/0005-dev-mode-direct-processes.md)). `npm run dev:frontend` = `next dev frontend --webpack -H 127.0.0.1 -p 3000`, `npm run dev:backend` = `node --watch backend/server.mjs --frontend http://127.0.0.1:3000`. 접속 주소와 요청 흐름(게이트웨이 → Next.js)은 일반 실행과 같습니다.
- 백엔드가 Next.js 주소를 받는 방법: `--frontend <origin>` → 없으면 `HAEDAP_FRONTEND_ORIGIN`(`.env` 포함) → 둘 다 없으면 API만 동작. 주소는 `http://127.0.0.1:<port>`만 허용(`frontend-proxy.mjs`).
- `frontend/next.config.mjs`는 `next dev` 단계에서 `frontend/.next-dev`, 그 외에는 `frontend/.next`를 출력 폴더로 씁니다(`HAEDAP_NEXT_DIST`로 덮어쓰기 가능).
- 외부 네트워크는 선택적 LLM 호출에서만 사용합니다. 나머지는 모두 오프라인으로 동작합니다.

## 2. 요청 흐름

### 2.1 게이트웨이 (`backend/server.mjs`)

모든 요청은 먼저 게이트웨이를 지납니다.

1. **네트워크 정책** (`network.mjs`): `Host` 헤더가 이 서버의 주소·포트인지, 접속자 IP가 루프백(기본) 또는 연결된 IPv4 서브넷(`--lan`)인지 검사. 아니면 403.
2. **경로 분기**
   - `/api/*` → `api.mjs`가 직접 처리 (쿠키·CSRF·권한 검사가 같은 출처에서 유지됨)
   - 소스·설정 경로(`/backend`, `/frontend`, `/scripts`, `/data`, `/node_modules`, 점으로 시작하는 경로, `package.json`, `README.md`, `AGENTS.md` 등) → 404
   - 그 외 → `frontend-proxy.mjs`가 Next.js 루프백 프로세스로 전달 (WebSocket upgrade 포함, 개발 모드 HMR용)
3. 서버 시작 시 DB를 열고, 문서가 하나도 없으면 `backend/knowledge/seed.json`을 넣고, 1분마다 자동 백업 여부를 확인합니다.

### 2.2 화면 (`frontend/`)

- `src/app/` — App Router 페이지. `/`는 `/chat`으로 리다이렉트. 페이지: `/chat`, `/documents`, `/documents/[id]`, `/operations`, `/reports`, `/reports/[id]`, `/admin`.
- `src/workspace/provider.jsx` — `WorkspaceProvider`가 작업공간 상태를 소유하고 컴포넌트는 `useSyncExternalStore`로 구독.
- `src/workspace/controller.jsx` — 사용자 이벤트 처리, API 호출, 대화상자, 초안 보존.
- `src/lib/api.js` — 유일한 서버 호출 지점. `X-Haedap-Token`(CSRF), `X-Haedap-Identity`(현재 사용자 확인) 헤더를 붙임.
- `src/lib/pdf.js` — 브라우저 안의 PDF.js로 텍스트 추출(업로드 PDF는 외부로 보내지 않음). `src/lib/csv.js` — 운항 CSV 파싱.
- `src/lib/model.js` — 클라이언트 상태 모델, 미저장 초안의 `localStorage` 보관.
- PDF 원문 뷰어만 iframe을 쓰고, 나머지는 모두 JSX로 렌더링합니다.

### 2.3 통합 질문 (`POST /api/ask`)

```mermaid
sequenceDiagram
  participant UI as 브라우저
  participant API as api.mjs
  participant AN as analysis.integratedAnswer
  participant RAG as rag.answerQuestion
  participant DB as SQLite
  UI->>API: question, task, context{ship,from,to}, criterion
  API->>AN: 사용자·권한 확인 후 호출
  AN->>DB: allowedDocs(user) — 열람 가능한 적용 중 문서
  AN->>RAG: 질문 + 허용 문서 ID
  RAG->>DB: FTS5 MATCH + bm25 (최대 30 → 지지 검사 → 5)
  alt mode=llm 이고 모델 설정됨
    RAG->>RAG: 외부 LLM(JSON schema) → 인용 구절이 원문에 있는지 검사
  else
    RAG->>RAG: 상위 3개 원문 발췌
  end
  RAG->>DB: queries 기록
  AN->>DB: 운항 필요 시 summarize(ship, from, to)
  AN->>AN: criterion 있으면 단일 기준 수치 비교
  AN->>DB: queries 갱신 + query_owner
  AN-->>UI: statements, evidence, operations, compliance, ...
```

응답 형식은 [`specs/integrated-answer.md`](specs/integrated-answer.md)를 따릅니다.

## 3. 모듈 책임 (`backend/`)

| 파일 | 책임 | 의존 |
|---|---|---|
| `server.mjs` | 게이트웨이, 시작·종료, 시드, 자동 백업 타이머 | 아래 전부 |
| `network.mjs` | CLI 옵션(`--lan`, `--port`), LAN 인터페이스, 접속 허용 정책 | — |
| `frontend-proxy.mjs` | Next.js 루프백 프록시 (`http://127.0.0.1:<port>`만 허용) | — |
| `paths.mjs` | 프로젝트 루트, DB 경로 결정(신·구 경로 호환, 충돌 시 중단) | — |
| `api.mjs` | HTTP 라우팅, 세션·게스트 쿠키, CSRF, 본문 크기 제한, 오류 응답 | workspace, analysis, rag, tools |
| `workspace.mjs` | 스키마(작업공간 테이블), 인증, 권한, 문서·선박·운항 변경, 보고서, 감사 로그, 백업·복구 | db, knowledge |
| `db.mjs` | 스키마(문서·청크·FTS·보고서·로그), 문서 수집, 검색(`retrieve`), 보고서 저장 | knowledge |
| `knowledge.mjs` | 문서 검증, 청크 분할(최대 900자), 토큰화(단어 + 한글 바이그램 + 한영 용어 사전) | — |
| `rag.mjs` | 근거 기반 답변, 선택적 외부 LLM 호출과 인용 검증 | db, tools |
| `analysis.mjs` | 운항 요약, 기준 비교, 통합 답변, Noon/MRV 초안 생성 | workspace, rag |
| `tools.mjs` | 계산 도구(`calculate_emissions`, `voyage_time`)와 실행 기록 | db |
| `validation.mjs` | 입력 검증 도우미, `AppError` | — |

`scripts/`: `run.mjs`(일반 실행 시 두 프로세스 관리), `build.mjs`(Next 빌드), `start.ps1`·`start.cmd`(Windows), `setup-lan-firewall.ps1`, `ingest.mjs`(JSON 문서 수집), `check-runtime.cjs`(SQLite·FTS5 점검), `next-browser-smoke.mjs`(Playwright 업무 흐름 검증).

## 4. 보안 경계

모듈을 교체하더라도 아래 경계는 유지해야 합니다.

- **접속 범위**: 기본은 이 PC(루프백)만. `--lan`도 연결된 IPv4 서브넷과 서버 자신의 주소·포트 `Host`만 허용. 인터넷 공개 배포 구성이 아님(TLS 없음).
- **단일 출처**: API를 다른 포트로 노출하지 않음. Next.js는 `127.0.0.1`에서만 수신.
- **인증**: 관리자만 로그인(salt + scrypt, HttpOnly·SameSite=Strict 세션 쿠키, 12시간). 일반 사용자는 무작위 `haedap_guest` 쿠키로 작업공간만 구분(인증 수단 아님).
- **쓰기 보호**: 모든 POST는 JSON + `X-Haedap-Token` 필요. 원본 자료(문서·선박·운항) 변경은 서버에서 관리자 여부를 검사.
- **열람 범위**: 문서 `scope`(all/operator/admin)를 **검색 입력 단계부터** 적용하고, 원본 PDF·이전 버전·보고서 근거·질문 이력 재열람에도 다시 검사.
- **LLM 출력 검증**: 외부 모델은 근거 청크 ID와 원문 인용 구절을 반환해야 하며, 인용이 원문에 없으면 폐기하고 원문 발췌로 되돌림. 질문·근거는 지시문이 아닌 데이터로 취급하도록 지시.
- **근거 없는 수치 금지**: 공식 CII와 규정 적용 판정은 산출하지 않고 `unavailable` / `unknown`과 사유를 반환.

## 5. 교체 지점 (팀 모듈 연결)

| 바꾸려는 것 | 시작 파일 | 지켜야 할 계약 |
|---|---|---|
| 검색(벡터·하이브리드 RAG) | `db.mjs`의 `retrieve`, `knowledge.mjs`의 청크·토큰 | `allowedIds` 필터 유지, evidence 필드 형식 |
| 답변 생성(LLM 공급자) | `rag.mjs`의 `generateGrounded`, `modelConfigured` | statements의 `chunkId`·`quote` 인용 검증 |
| 의도 분류·Agent | `analysis.mjs`의 `integratedAnswer` | [`specs/integrated-answer.md`](specs/integrated-answer.md) 출력 형식 |
| 계산 Tool 추가 | `tools.mjs`의 `toolDefinitions`, `runTool` | 입력 검증, `version`·`assumptions` 반환, `tool_runs` 기록 |
| 보고서 서식 | `analysis.mjs`의 `generateReport` | 없는 값은 `[미입력 · 확인 필요]` |
| 화면 → 다른 API | `frontend/src/lib/api.js` | 같은 출처, CSRF·Identity 헤더 |

연결 순서와 담당은 [`plans/2026-10-08-team-module-integration.md`](plans/2026-10-08-team-module-integration.md)를 참고하세요.

## 6. 빌드·실행 산출물

| 경로 | 생성 시점 | Git |
|---|---|---|
| `node_modules/` | `npm ci` | 제외 |
| `frontend/.next/` | `npm run build` | 제외 |
| `frontend/.next-dev/` | `npm run dev:frontend` | 제외 |
| `backend/data/haedap.sqlite`(+ WAL) | 서버 첫 실행 | 제외 (`data/`) |
| `backend/data/backups/` | 수동·자동 백업 | 제외 |
| `.env` | 사용자가 직접 | 제외 |

## 7. 알려진 한계

- 문서·운항·보고서 목록을 매 요청 메모리로 읽는 캡스톤 데모 규모 설계. 대규모 운영에는 페이징·파일 저장소·TLS·로그 보존 정책이 필요.
- 검색은 어휘(키워드) 기반이라 의미가 같고 단어가 다른 질문, 교차 언어 질문에 약함.
- 질문 유형 분기는 단어 규칙 기반. 질문 속 날짜·선박명 자동 추출은 미구현.
