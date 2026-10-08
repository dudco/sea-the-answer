# 변경 이력과 검증 기록

버전을 올리거나 검증을 수행하면 이 파일에 기록합니다. 검증은 **실제로 수행한 것만** 날짜·환경과 함께 적고, 수행하지 않은 범위는 따로 적습니다.

## 변경 이력

- **1.4.0 정리 / 2026-10-08**: `/api/*` 전달을 `next.config.mjs`의 `rewrites`(빌드 때 주소 고정)에서 `frontend/src/proxy.js`(요청마다 결정)로 변경 — `.env`의 `HAEDAP_API_ORIGIN`을 바꾼 뒤 재시작만 하면 반영, 다시 빌드할 필요 없음([ADR 0007](adr/0007-runtime-api-origin-via-proxy.md)).
- **1.4.0 정리 / 2026-10-08**: `start.cmd`를 `scripts/start.cmd`로 이동(최상위에서 실행하도록 경로 보정). Ubuntu 서버 운영 기준으로 Windows 전용 `scripts/setup-lan-firewall.ps1` 제거(방화벽은 OS 설정으로 안내).
- **1.4.0 정리 / 2026-10-08**: 래퍼였던 `scripts/build.mjs` 제거(`npm run build`가 `next build frontend --webpack`을 직접 실행, 출력 폴더는 `next.config.mjs`가 결정), `test:browser`와 중복이던 `npm run test:ui` 제거.
- **1.4.0 / 2026-10-08**: Next.js를 공개 진입점으로 바꾸고 `/api/*`를 `rewrites`로 내부 API 서버에 전달([ADR 0006](adr/0006-nextjs-entry-rewrites-to-api.md)). API 서버는 `127.0.0.1:8000`(`HAEDAP_API_ORIGIN`)에만 바인딩하고 `X-Forwarded-Host` 기준으로 Host·Origin 검사, 공개 포트는 `--public-port`. `backend/frontend-proxy.mjs`와 `--frontend` 옵션 제거. 개발 모드 접속 주소를 5173(Next.js)으로 통일. 프록시 본문 한도 101MB·대기 60초로 상향. **LAN 모드의 접속자 서브넷 검사 제거**(Next.js가 실제 접속자 IP를 전달하지 않음 → OS 방화벽으로 제한).
- **1.3.2 / 2026-10-08**: 개발 모드를 래퍼 스크립트 대신 백엔드·프론트 직접 실행으로 변경([ADR 0005](adr/0005-dev-mode-direct-processes.md)). `npm run dev` → `npm run dev:backend`(`node --watch`, 자동 재시작) + `npm run dev:frontend`(`next dev`). 백엔드에 `--frontend <origin>` 옵션 추가(`HAEDAP_FRONTEND_ORIGIN`보다 우선, `.env`에서도 읽음). `next.config.mjs`가 개발/빌드 출력 폴더를 단계(phase)로 자동 구분. `scripts/run.mjs`와 `start.cmd`는 일반 실행 전용으로 정리(`--dev`, `-Task dev` 제거). 브라우저 검증의 개발 모드도 두 프로세스를 직접 띄우도록 변경.
- **문서 정리 / 2026-10-08** (코드 변경 없음, 버전 유지): 최상위 `docs/` 체계 도입 — `architecture.md`, `data-model.md`, `user-guide.md`, `changelog.md`, `specs/`, `plans/`, `adr/`. README를 소개·구조·설치·Windows/macOS 실행 중심으로 재작성하고 상세 내용을 docs로 이동. AGENTS.md를 문서 위치·작성 규칙 중심으로 갱신(이전의 "docs 폴더를 만들지 않는다" 규칙 폐기, [ADR 0001](adr/0001-docs-directory.md)).
- **1.3.1 / 2026-10-06**: 최상위 소스 폴더를 frontend/backend/scripts로 정리. Next.js와 Windows 실행·테스트 경로 수정. 레거시·중복 설명서 제거 및 README에 통합. 기본 DB 위치를 backend/data로 변경하고 옛 경로 호환·충돌 안내 추가. Windows npm 인수 전달을 명시하여 첫 실행 빌드 호출 보완.
- **1.3.0 / 2026-10-05**: Next.js App Router·React JSX로 UI 이전. 실제 페이지 URL·공통 Provider·컴포넌트·대화상자 적용. 기존 Node API·SQLite·권한 정책 유지. 하나의 시작 명령에서 API 게이트웨이와 Next.js 실행. 설치·빌드·개발·데이터 이전 안내 갱신.
- **1.2.2 / 2026-09-30**: SEA THE ANSWER 표기와 관리자 전용 문서·운항 변경, 즉시 반영.
- **1.2.1 / 2026-09-30**: 로그인 없는 일반 기능과 관리자 admin / 1234, 일반 사용자별 초안·이력 분리.
- **1.2.0 / 2026-09-30**: PDF/CSV, 다중 보고서, 통합 결과, 계정·권한·로그·백업·복구.

## 검증 기록

### 2026-10-08 — 1.4.0

환경: Linux, Node.js v24.21.0, Next.js 16.3.8, Playwright + Chromium(사전 설치본).

| 검증 | 결과 |
|---|---|
| `npm test` | **32개 통과, 실패 없음, Windows 전용 1개 건너뜀** (네트워크 정책 테스트를 프록시 경유/직접 호출로 재작성, HTTP 통합 테스트에 `X-Forwarded-Host` 경유 검사 추가) |
| `npm run build` | 성공 |
| `npm run test:browser` (일반 실행) | **17개 업무 흐름 통과** |
| `HAEDAP_TEST_DEV=1 npm run test:browser` (API 서버 + `next dev` 직접 실행) | **17개 업무 흐름 통과** |
| `npm start -- --lan` 수동 확인 | 60MB 요청 본문이 프록시를 거쳐 API까지 전달(앱 검증 응답 403 수신), LAN 주소로 화면·API 200, LAN 주소의 8000 포트는 연결 거부, 위조한 `X-Forwarded-For`는 무시 |

`proxy.js` 전환 후(같은 날): `npm test` 32개 통과, 빌드 성공, 브라우저 17개 흐름 일반·개발 모드 모두 통과. `HAEDAP_API_ORIGIN` 없이 빌드한 뒤 최상위 `.env`에만 다른 주소를 넣고 `next start` → 그 주소로 전달됨(재빌드 불필요) 확인.

Next.js 16.3.8 동작 확인(임시 에코 서버): rewrite 대상 주소는 `next build` 시점 값으로 고정, `X-Forwarded-Host`는 실제 Host로 덮어씀, `X-Forwarded-For`는 클라이언트 값을 그대로 전달, 기본 본문 한도 10MB 초과 시 프록시 실패.

검증하지 않은 범위: Windows·macOS 직접 실행, `start.cmd`, 다른 기기에서의 실제 LAN 접속.

### 2026-10-08 — 1.3.2

환경: Linux, Node.js v24.21.0, Next.js 16.3.8, Playwright + Chromium(사전 설치본).

| 검증 | 결과 |
|---|---|
| `npm test` | **33개 통과, 실패 없음, Windows 전용 1개 건너뜀** (`--frontend` 옵션 테스트 1개 추가) |
| `npm run build` | 성공 |
| `npm run test:browser` (일반 실행, `scripts/run.mjs`) | **17개 업무 흐름 통과** |
| `HAEDAP_TEST_DEV=1 npm run test:browser` (백엔드·`next dev` 직접 실행) | **17개 업무 흐름 통과** |
| `npm run dev:backend` → `npm run dev:frontend` 수동 실행 | 프론트 기동 전 안내 문구, 기동 후 `/chat` 200, 백엔드 파일 수정 시 자동 재시작, 개발 실행 후에도 `frontend/.next/BUILD_ID` 변경 없음 |

검증하지 않은 범위: Windows·macOS에서 두 명령 직접 실행, `start.cmd` 실제 실행.

### 2026-10-08 — 문서 정리

문서만 변경했으므로 테스트는 실행하지 않았습니다. 문서의 파일 경로, npm 스크립트(`package.json`), `start.ps1` 옵션, 테이블 정의(`backend/db.mjs`, `backend/workspace.mjs`), API 경로를 현재 코드와 대조했습니다. macOS 실행 절차는 같은 Node 명령을 쓰는 Linux 검증에 근거하며 macOS에서 직접 실행하지는 않았습니다.

### 2026-10-06 — 1.3.1

환경: Linux, Node.js v24.19.0, Next.js 16.3.8, React 19.2.7, Playwright와 Chromium 153.

| 검증 | 결과 |
|---|---|
| `npm run build` | `frontend/.next`에 배포용 빌드 성공 |
| `npm test` | **32개 통과, 실패 없음, Windows 전용 1개 건너뜀** |
| 일반 실행의 실제 브라우저 검증 | **17개 업무 흐름 통과**, 브라우저 예외·React 경고 없음 |
| 개발 실행의 실제 브라우저 검증 | **동일한 17개 흐름 통과**, 개발 빌드 경로 분리 확인 |
| DB 경로 호환 | 새 위치·옛 위치·사용자 지정 경로·양쪽 DB 존재 시 명시적 선택 검증 |

브라우저에서 공개 접근, 질문·검색·출처, 문서 상세 URL·새로고침, 일반 사용자의 변경 차단, 실패한 로그인 재시도, 관리자 로그인·로그아웃, 문서 등록·개정·삭제, 실제 PDF 추출·원문 저장, 선박·기록 등록·수정·삭제, 계산, CSV 검증·등록, 보고서 생성·저장·뒤로가기·검토 요청·승인, 백업·복구·세션 무효화, 모바일 메뉴를 확인했습니다. PDF는 테스트용 1페이지 텍스트 PDF의 원문 바이트까지 대조했습니다. 모든 업무 검증은 임시 DB·임시 포트로 진행했습니다.

검증하지 않은 범위:

- Windows에서 `start.cmd` 직접 실행(인수 전달·경로는 수정했으나 미실행)
- 다른 기기의 실제 LAN 접속, 휴대폰·Safari·Edge 전체 호환성, 모든 PDF 형식 (모바일은 Chromium 390px 기준)
- 실제 외부 LLM 호출 (모델 실패·인용 검사는 모의 응답 사용)
- 공식 CII 계산·규정 적용 자동 판정·검색 Recall·응답 시간 목표·번역 품질·공식 보고서 서식
