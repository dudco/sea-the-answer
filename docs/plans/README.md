# plans — 작업 계획

- [2026-10-15 앱 업무 스킬](2026-10-15-app-workflow-skills.md): 여섯 기능과 선택 LLM의 구현·검증.

여러 단계·여러 사람이 걸리는 작업을 **시작하기 전에** 적고, 진행하면서 체크박스와 상태를 갱신합니다. 사람은 진행 상황을 확인하고, 에이전트는 다음에 할 일과 완료 조건을 여기서 읽습니다.

## 규칙

- 파일: `YYYY-MM-DD-주제.md` (작성일 기준, 영문 kebab-case). [`_template.md`](_template.md)를 복사합니다.
- 상태: `초안 → 진행 중 → 완료 / 보류 / 취소`. 끝난 계획도 지우지 않고 상태만 바꿉니다.
- 계획 안에서 인터페이스를 정해야 하면 [`../specs/`](../specs/)에 명세를 따로 쓰고 링크합니다. 되돌리기 어려운 선택은 [`../adr/`](../adr/)에 남깁니다.
- 단계마다 **완료 조건**을 적습니다(테스트 통과, 화면 확인, 문서 갱신 등).
- 에이전트가 단계를 끝내면 체크하고, 실제 결과·남은 문제를 "진행 기록"에 날짜와 함께 한 줄로 남깁니다.

## 목록

- [2026-10-29 웹 하이브리드 검색 통일](2026-10-29-web-hybrid-search.md): 완료.

- [2026-10-29 벡터 색인 복구·통합 검증](2026-10-29-vector-index-repair-integration.md): 완료 (머지 커밋 대기).

- [2026-10-29 Chroma 이미지 분리](2026-10-29-chroma-image.md): 완료.

- [2026-10-27 벡터·RRF](2026-10-27-vector-hybrid.md): 완료.

| 문서 | 내용 | 상태 |
|---|---|---|
| [`2026-10-28-korean-llm-validation.md`](2026-10-28-korean-llm-validation.md) | 한국어 평가·브라우저 회귀·Docker 및 실제 모델 연결 검증 | 완료 (일반 한국어 품질은 후속) |
| [`2026-10-28-search-token-reuse.md`](2026-10-28-search-token-reuse.md) | 내용별 토큰 재사용과 검색 순위·권한·속도 회귀 검증 | 완료·로컬 검증 |
| [`2026-10-28-maritime-retrieval-evaluation.md`](2026-10-28-maritime-retrieval-evaluation.md) | 원문 인용 기반 질문 평가와 BM25 지표·실패 분석 | 완료 |
| [`2026-10-22-rag-chunking-kiwi.md`](2026-10-22-rag-chunking-kiwi.md) | 목차·제목 청킹 및 Kiwi BM25 | 완료 |
| [`2026-10-21-crew-admin-auth.md`](2026-10-21-crew-admin-auth.md) | 인증 구현·Ollama 실검증·CI 성공, PR 제출 | 보류 (#14 관리자 병합 대기) |
| [`2026-10-15-bm25-debug.md`](2026-10-15-bm25-debug.md) | 읽기 전용 BM25 디버그 CLI | 완료 |
| [`2026-10-14-bm25-retrieval.md`](2026-10-14-bm25-retrieval.md) | 권한 적용 후 한영 BM25 문서 검색 | 완료 |
| [`2026-10-13-openai-compatible-chat.md`](2026-10-13-openai-compatible-chat.md) | 모델 호출 전환·인증·공급자 실검증, CI 분리 | 보류 (#14 관리자 병합 대기) |
| [`2026-10-13-rag-preprocessing.md`](2026-10-13-rag-preprocessing.md) | Python 해사 문서 전처리·청킹, 실제 PDF 검증 및 새 구조 통합 | 완료 |
| [`2026-10-08-team-module-integration.md`](2026-10-08-team-module-integration.md) | RAG·LLM·Tool·문서 형식 등 팀 모듈 연결 로드맵 | 초안 |
| [`2026-10-08-tools-and-data-preparation-docs.md`](2026-10-08-tools-and-data-preparation-docs.md) | 역할4 PR 문서·모듈 구조 정리 | 완료 |
| [`2026-10-08-tools-pr-update.md`](2026-10-08-tools-pr-update.md) | 역할4 PR 최신 main 반영 및 제출 | 완료 |
| [`2026-10-13-tools-and-data-preparation-integration.md`](2026-10-13-tools-and-data-preparation-integration.md) | 해사 runtime·준비 작업·마이그레이션·선박 연결 통합 | 완료 |
| [`2026-10-13-mrv-reference-intensity.md`](2026-10-13-mrv-reference-intensity.md) | 공개 제원 후보 연결·MRV 참고 집약도 | 완료 (로컬·미제출) |

- [자동 색인과 이미지 모델](2026-10-29-automatic-vector-indexing.md) — 완료
