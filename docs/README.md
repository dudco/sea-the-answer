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
| 해사 데이터 Tool 호출·품질 규칙 | [`specs/tools.md`](specs/tools.md), [`specs/prepare-data.md`](specs/prepare-data.md) |
| 설계가 왜 이런지 확인 | [`adr/`](adr/) |
| 무엇이 언제 바뀌었고 무엇을 검증했는지 | [`changelog.md`](changelog.md) |

## 전체 목록

- [벡터 색인 복구·팀 브랜치 통합 검증](plans/2026-10-29-vector-index-repair-integration.md): 완료 (머지 커밋 대기).

- [등록 PDF 검색 평가 질문 10개](rag-evaluation-questions.json): 문서·물리 페이지·조항 후보 기준의 재사용 가능한 평가 자료.

- [자동 색인 계획](plans/2026-10-29-automatic-vector-indexing.md): 완료 · [작업 계약](specs/rag-index-jobs.md): 구현됨 · [ADR 0021](adr/0021-durable-index-jobs.md): 채택.

### 기본 문서

- [`architecture.md`](architecture.md) — 실행 구조, 요청 흐름, 모듈 책임, 보안 경계, 교체 지점
- [`data-model.md`](data-model.md) — PostgreSQL 앱 테이블 및 선택 해사 데이터 테이블·ERD, JSON 필드, 상태 전이, 백업 범위
- [`user-guide.md`](user-guide.md) — 화면별 사용법, 역할·권한, CSV, 백업·복구, LAN·서버, 버전 교체, 문제 해결
- [`changelog.md`](changelog.md) — 변경 이력, 검증 기록
- [`retrieval-evaluation.md`](retrieval-evaluation.md) — 실제 문서 스냅샷의 해사 질문 평가셋·검색 지표·실행 방법

### specs — 구현 계약

- [선원·관리자 인증](specs/authentication.md) — 구현됨
- [업무 스킬 실행 계약](specs/workflow-skills.md): 여섯 스킬, 선택 문서·매핑·권한·초안·평가 범위.

| 문서 | 상태 |
|---|---|
| [`specs/llm-provider.md`](specs/llm-provider.md) — Chat Completions 공통 설정·공급자 키 격리·인용 검증·한국어 평가 | 구현됨 (공급자별 실검증은 변경 이력 참고) |
| [`specs/api.md`](specs/api.md) — HTTP API, 인증·쓰기 보호, 문서 등록 payload | 구현됨 |
| [`specs/integrated-answer.md`](specs/integrated-answer.md) — `/api/ask` 입력·출력, CII·기준 비교 계약 | 구현됨 |
| [`specs/tools.md`](specs/tools.md) — 독립 PostgreSQL 조회·계산·조회 도우미 계약 | 구현됨 |
| [`specs/prepare-data.md`](specs/prepare-data.md) — 데이터 선택·출처·품질·집계 적격성 계약 | 구현됨 |

### plans — 작업 계획

- [웹 하이브리드 검색 통일](plans/2026-10-29-web-hybrid-search.md): 완료.

- [Chroma 서버 이미지 분리](plans/2026-10-29-chroma-image.md): 완료.

- [벡터·RRF 구현](plans/2026-10-27-vector-hybrid.md): 완료. [계약](specs/rag-vector.md) 구현됨, 현재 결정은 [ADR 0021](adr/0021-durable-index-jobs.md) (0019·0020 계승).

- [한국어 근거 답변과 실제 모델 검증](plans/2026-10-28-korean-llm-validation.md) — 완료 (Docker e2e·모델 연결 검증, 일반 한국어 품질은 후속)
- [해사 질문 검색 평가](plans/2026-10-28-maritime-retrieval-evaluation.md) — 초기 평가 완료
- [검색 토큰 재사용](plans/2026-10-28-search-token-reuse.md) — 로컬 구현·검증 완료

- [인증·Ollama·CI](plans/2026-10-21-crew-admin-auth.md) — 보류 (#14 관리자 병합 대기, 구현·검증 완료)
- [목차 청킹과 Kiwi BM25 개선](plans/2026-10-22-rag-chunking-kiwi.md): 완료.
- [앱 업무 스킬 구현](plans/2026-10-15-app-workflow-skills.md): 진행 상태와 실제 검증.

| 문서 | 상태 |
|---|---|
| [`plans/2026-10-15-bm25-debug.md`](plans/2026-10-15-bm25-debug.md) — 읽기 전용 BM25 디버그 CLI | 완료 |
| [`plans/2026-10-14-bm25-retrieval.md`](plans/2026-10-14-bm25-retrieval.md) — 권한 적용 후 한영 BM25 문서 검색 | 완료 |
| [`plans/2026-10-13-openai-compatible-chat.md`](plans/2026-10-13-openai-compatible-chat.md) — 모델 호출 전환·인증·공급자 실검증, CI 분리 | 보류 (#14 관리자 병합 대기) |
| [`plans/2026-10-13-rag-preprocessing.md`](plans/2026-10-13-rag-preprocessing.md) — Python 해사 문서 전처리·청킹 및 새 구조 통합 | 완료 |
| [`plans/2026-10-08-team-module-integration.md`](plans/2026-10-08-team-module-integration.md) — RAG·LLM·Tool 팀 모듈 연결 로드맵 | 초안 |
| [`plans/2026-10-08-tools-and-data-preparation-docs.md`](plans/2026-10-08-tools-and-data-preparation-docs.md) — 역할4 PR 문서·모듈 구조 정리 | 완료 |
| [`plans/2026-10-08-tools-pr-update.md`](plans/2026-10-08-tools-pr-update.md) — 역할4 PR 최신 main 반영 및 제출 | 완료 |
| [`plans/2026-10-13-tools-and-data-preparation-integration.md`](plans/2026-10-13-tools-and-data-preparation-integration.md) — 해사 runtime·준비 작업·마이그레이션·선박 연결 통합 | 완료 |
| [`plans/2026-10-13-mrv-reference-intensity.md`](plans/2026-10-13-mrv-reference-intensity.md) — 공개 DWT 후보 연결·MRV 참고 집약도 | 완료 (로컬·미제출) |

### adr — 설계 결정

- [0020 Chroma 전용 이미지](adr/0020-dedicated-chroma-image.md): 대체됨(0021). 전용 서버 분리는 유지.

- [0017 문서 분석 토큰의 제한된 메모리 재사용](adr/0017-bounded-chunk-token-reuse.md) — 제안·로컬 구현

- [0016 개인 계정과 서버의 업무 접근 통제](adr/0016-crew-admin-authentication.md) — 채택
- [0015 업무 스킬과 선택 LLM](adr/0015-optional-model-workflow-skills.md): 고정 실행기와 런타임 지침.

추가 제안: [0013 - 제원 후보 별도 보존·MRV 참고 집약도 API](adr/0013-mrv-reference-intensity.md). 팀 PR #11에서 사용하는 0012와 번호를 구분합니다.

| 번호 | 결정 | 상태 |
|---|---|---|
| [0001](adr/0001-docs-directory.md) | 문서를 최상위 `docs/`에 모으고 AGENTS.md를 공통 지침으로 사용 | 채택 |
| [0002](adr/0002-single-gateway-next-and-node-api.md) | Node API 게이트웨이 하나 뒤에 Next.js를 루프백으로 둠 | 대체됨(0006) |
| [0003](adr/0003-sqlite-fts5-local-storage.md) | 내장 SQLite + FTS5로 로컬 저장·검색 | 대체됨(0009) |
| [0004](adr/0004-public-access-admin-only-writes.md) | 로그인 없는 일반 사용 + 관리자만 원본 자료 변경 | 대체됨(0016) |
| [0005](adr/0005-dev-mode-direct-processes.md) | 개발 모드는 백엔드·프론트를 각각 직접 실행 | 채택 (일부 0006·0009로 대체) |
| [0006](adr/0006-nextjs-entry-rewrites-to-api.md) | Next.js를 공개 진입점으로, `/api/*`는 rewrites로 내부 API에 전달 | 채택 (일부 0007로 대체) |
| [0007](adr/0007-runtime-api-origin-via-proxy.md) | `/api/*` 전달 주소를 실행 시점에 결정(`proxy.js`) | 채택 |
| [0008](adr/0008-tools-query-and-calculation-boundary.md) | 해사 데이터 Tool의 독립 실행과 내부 API 연결 경계 | 제안 (실행 위치는 0009로 대체) |
| [0009](adr/0009-split-packages-and-compose.md) | frontend·backend 독립 패키지 + 최상위 docker compose + `e2e/` | 채택 (DB 초기화는 0010으로 대체) |
| [0010](adr/0010-dbmate-migrations.md) | DB 스키마를 최상위 `migrations/` SQL 파일 + dbmate로 관리 | 채택 |
| [0011](adr/0011-tools-runtime-and-data-preparation.md) | 해사 runtime·준비 작업 분리와 공통 마이그레이션·명시적 선박 연결 | 제안 |
| [0012](adr/0012-openai-compatible-chat-completions.md) | OpenAI 호환 Chat Completions 공통 호출과 로컬 인용 검증 | 대체됨(0013) |
| [0013](adr/0013-provider-credential-isolation.md) | 공통 LLM 설정과 URL 호스트에 따른 공급자별 인증키 격리 | 채택 |
| [0014](adr/0014-mindlogic-gateway-host.md) | 동국 AI Chat API 게이트웨이(Mindlogic) 호스트 계약 추가 | 제안 |

## 작성 규칙 요약

- 파일 이름은 영문 `kebab-case`. 템플릿은 각 폴더의 `_template.md`.
- plans: `YYYY-MM-DD-주제.md`, 상태 `초안 → 진행 중 → 완료/보류/취소`.
- specs: `주제.md`, 상태 `초안 → 확정 → 구현됨 → 폐기`. 코드가 바뀌면 같은 작업에서 갱신.
- adr: `NNNN-주제.md`, 상태 `제안 → 채택 → 대체됨/폐기`. 채택된 본문은 고치지 않고 새 ADR로 대체.
- 문서를 추가하거나 상태를 바꾸면 이 목록도 갱신합니다.
- 문서와 코드가 다르면 코드가 사실입니다. 발견하면 문서를 고칩니다.
