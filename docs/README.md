# 해답 문서 안내

프로젝트의 모든 문서는 이 `docs/` 폴더에 모읍니다. 문서 위치·작성 규칙의 원본은 최상위 [`AGENTS.md`](../AGENTS.md)이며, 이 파일은 목록과 요약입니다.

## 어떤 문서를 먼저 볼까

| 하려는 일 | 읽을 문서 |
|---|---|
| 처음 실행 | [`../README.md`](../README.md) |
| 화면 사용·운영·문제 해결 | [`user-guide.md`](user-guide.md) |
| 코드 구조 파악, 모듈 교체 | [`architecture.md`](architecture.md) |
| DB·저장 형식 변경 | [`data-model.md`](data-model.md) |
| API 호출·응답 형식 구현 | [`specs/`](specs/) |
| 지금 진행 중인 작업 확인 | [`plans/`](plans/) |
| 설계가 왜 이런지 확인 | [`adr/`](adr/) |
| 무엇이 언제 바뀌었고 무엇을 검증했는지 | [`changelog.md`](changelog.md) |

## 전체 목록

### 기본 문서

- [`architecture.md`](architecture.md) — 실행 구조, 요청 흐름, 모듈 책임, 보안 경계, 교체 지점
- [`data-model.md`](data-model.md) — SQLite 테이블, JSON 필드, 상태 전이, 백업 형식
- [`user-guide.md`](user-guide.md) — 화면별 사용법, 역할·권한, CSV, 백업·복구, LAN, 데이터 이전, 문제 해결
- [`changelog.md`](changelog.md) — 변경 이력, 검증 기록

### specs — 구현 계약

| 문서 | 상태 |
|---|---|
| [`specs/api.md`](specs/api.md) — HTTP API, 인증·쓰기 보호, 문서 등록 payload | 구현됨 |
| [`specs/integrated-answer.md`](specs/integrated-answer.md) — `/api/ask` 입력·출력, CII·기준 비교 계약 | 구현됨 |

### plans — 작업 계획

| 문서 | 상태 |
|---|---|
| [`plans/2026-10-08-team-module-integration.md`](plans/2026-10-08-team-module-integration.md) — RAG·LLM·Tool 팀 모듈 연결 로드맵 | 초안 |

### adr — 설계 결정

| 번호 | 결정 | 상태 |
|---|---|---|
| [0001](adr/0001-docs-directory.md) | 문서를 최상위 `docs/`에 모으고 AGENTS.md를 공통 지침으로 사용 | 채택 |
| [0002](adr/0002-single-gateway-next-and-node-api.md) | Node API 게이트웨이 하나 뒤에 Next.js를 루프백으로 둠 | 대체됨(0006) |
| [0003](adr/0003-sqlite-fts5-local-storage.md) | 내장 SQLite + FTS5로 로컬 저장·검색 | 채택 |
| [0004](adr/0004-public-access-admin-only-writes.md) | 로그인 없는 일반 사용 + 관리자만 원본 자료 변경 | 채택 |
| [0005](adr/0005-dev-mode-direct-processes.md) | 개발 모드는 백엔드·프론트를 각각 직접 실행 | 채택 (일부 0006으로 대체) |
| [0006](adr/0006-nextjs-entry-rewrites-to-api.md) | Next.js를 공개 진입점으로, `/api/*`는 rewrites로 내부 API에 전달 | 채택 |

## 작성 규칙 요약

- 파일 이름은 영문 `kebab-case`. 템플릿은 각 폴더의 `_template.md`.
- plans: `YYYY-MM-DD-주제.md`, 상태 `초안 → 진행 중 → 완료/보류/취소`.
- specs: `주제.md`, 상태 `초안 → 확정 → 구현됨 → 폐기`. 코드가 바뀌면 같은 작업에서 갱신.
- adr: `NNNN-주제.md`, 상태 `제안 → 채택 → 대체됨/폐기`. 채택된 본문은 고치지 않고 새 ADR로 대체.
- 문서를 추가하거나 상태를 바꾸면 이 목록도 갱신합니다.
- 문서와 코드가 다르면 코드가 사실입니다. 발견하면 문서를 고칩니다.
