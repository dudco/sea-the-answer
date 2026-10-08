# 변경 이력과 검증 기록

버전을 올리거나 검증을 수행하면 이 파일에 기록합니다. 검증은 **실제로 수행한 것만** 날짜·환경과 함께 적고, 수행하지 않은 범위는 따로 적습니다.

## 변경 이력

- **역할4 PR 구조 정리 / 2026-10-08** (기본 앱 버전 유지): 팀 main의 문서·소스 구조를 반영. Python 해사 Tool을 `backend/maritime_data/`로 옮기고 import·실행·적재 경로를 갱신. 역할4 API·데이터 계약은 `specs/`, PostgreSQL 테이블·ERD는 `data-model.md`, 설치·원본 확보·이전 안내는 `user-guide.md`에 통합. 생성기는 DDL·dictionary만 출력하도록 수정하여 설명 문서를 덮어쓰지 않음. 문서 목록·정리 계획·[ADR 0005 제안](adr/0005-maritime-data-tool-boundary.md) 추가. 조회·계산 로직·DB 스키마·기존 Node 앱 코드는 변경하지 않음.
- **문서 정리 / 2026-10-08** (코드 변경 없음, 버전 유지): 최상위 `docs/` 체계 도입 — `architecture.md`, `data-model.md`, `user-guide.md`, `changelog.md`, `specs/`, `plans/`, `adr/`. README를 소개·구조·설치·Windows/macOS 실행 중심으로 재작성하고 상세 내용을 docs로 이동. AGENTS.md를 문서 위치·작성 규칙 중심으로 갱신(이전의 "docs 폴더를 만들지 않는다" 규칙 폐기, [ADR 0001](adr/0001-docs-directory.md)).
- **1.3.1 / 2026-10-06**: 최상위 소스 폴더를 frontend/backend/scripts로 정리. Next.js와 Windows 실행·테스트 경로 수정. 레거시·중복 설명서 제거 및 README에 통합. 기본 DB 위치를 backend/data로 변경하고 옛 경로 호환·충돌 안내 추가. Windows npm 인수 전달을 명시하여 첫 실행 빌드 호출 보완.
- **1.3.0 / 2026-10-05**: Next.js App Router·React JSX로 UI 이전. 실제 페이지 URL·공통 Provider·컴포넌트·대화상자 적용. 기존 Node API·SQLite·권한 정책 유지. 하나의 시작 명령에서 API 게이트웨이와 Next.js 실행. 설치·빌드·개발·데이터 이전 안내 갱신.
- **1.2.2 / 2026-09-30**: SEA THE ANSWER 표기와 관리자 전용 문서·운항 변경, 즉시 반영.
- **1.2.1 / 2026-09-30**: 로그인 없는 일반 기능과 관리자 admin / 1234, 일반 사용자별 초안·이력 분리.
- **1.2.0 / 2026-09-30**: PDF/CSV, 다중 보고서, 통합 결과, 계정·권한·로그·백업·복구.

## 검증 기록

### 2026-10-08 — 역할4 PR 구조 정리

환경: Windows, Python 3.12.14, Node.js v24.16.0. 최신 팀 main `6608f6c`와 역할4 원격 head `cefd557`을 기존 작업용 체크아웃에서 로컬 병합하여 검증했습니다.

| 검증 | 결과 |
|---|---|
| `python -m pytest -q backend/maritime_data/tests` | **47개 통과, 실 PostgreSQL 대상 4개 건너뜀** |
| `python backend/maritime_data/scripts/test_prepare_maritime_data.py` | **3개 통과** |
| `npm test` | **33개 통과**, Windows CMD·PowerShell·LAN 실행 및 게이트웨이 응답 포함 |
| Windows 실행기에서 첫 실행 설치·Next.js 빌드 | 성공, `frontend/.next/BUILD_ID` 생성 및 세 실행 방식 확인 |
| 설명 생성기 `--out` 산출물 비교 | 기존 SQL·dictionary와 일치, 설명 Markdown을 생성하지 않음 |
| DB 필드·문서·경로 검사 | 6개 테이블의 필드 **70개** 대조, 로컬 문서 링크·앵커 확인, 이전 import·경로 제거 |
| 변경 경계·구문 검사 | 핵심 Python 조회·계산·전처리·마이그레이션 및 DB 스키마 보존, Node 코드·채택 ADR 0001~0004 보존, 적재 PowerShell 구문 및 `git diff --check` 통과 |

처음 `npm test` 실행은 이 PC의 Node 설치 두 개를 PowerShell 실행기가 하나의 경로 문자열로 읽어 Windows 실행기 1개가 실패했습니다. 별도 프로세스의 PATH에서 중복 설치 경로를 제외하고 `HAEDAP_NODE`를 공식 Node 실행 파일로 지정해 재실행한 결과 33개가 통과했습니다. 기존 팀 실행기 코드는 이 PR에서 수정하지 않았습니다. Python 테스트는 Starlette TestClient/httpx의 deprecation 경고 1개를 출력했습니다.

이번에 검증하지 않은 범위: 실제 PostgreSQL 조회·재적재·스키마 이름 변경(`MARITIME_DATA_TEST_DATABASE_URL` 미설정), 원본 데이터 전체의 재전처리, 팀 앱과 Python Tool의 연결·LLM·공식 CII 및 전체 브라우저 업무 흐름. 원격 푸시·PR 본문 변경·댓글은 수행하지 않았습니다.

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
