# 문서 BM25 검색 연결

- 상태: 완료
- 작성: 2026-10-14
- 담당: 문서/RAG
- 관련: [검색 계약](../specs/api.md#문서-검색-bm25), [아키텍처](../architecture.md)

## 1. 배경과 목표

PostgreSQL에 저장된 청크의 단어 포함 개수 검색을 rank-bm25의 BM25Okapi로 교체한다. 저장·개정·청킹과 외부 evidence 형식은 유지한다.

## 2. 범위

- 포함: 독립 검색 모듈, 한영 토큰화·기존 동의어, 권한 적용 후 BM25, 단위·DB·E2E 회귀 검증.
- 제외: 임베딩, ChromaDB, 벡터·하이브리드 검색, RRF, DB 스키마·UI 변경.

## 3. 단계

- [x] 현재 저장·검색·API와 기존 테스트, 사용자가 추가한 의존성 확인.
- [x] 검색 계약 갱신 및 독립 모듈 연결. 완료 조건: 저장 코드 변경 없이 기존 필터와 응답 유지.
- [x] 한영 순위·빈 입력·소규모 corpus·권한·메타데이터 테스트. 완료 조건: 신규 및 기존 테스트 실행, 결과·제한 기록.
- [x] README·아키텍처·변경 이력 동기화. 완료 조건: 실행 방법과 한계 설명.

## 4. 영향 받는 파일·문서

| 경로 | 변경 이유 |
|---|---|
| `backend/api/rag_retrieval.py` (신규) | 토큰화·동의어·BM25 점수와 top-k 반환 |
| `backend/api/store/documents.py` | 기존 필터 통과 청크를 검색 모듈에 전달, 외부 evidence 형식 유지 |
| `backend/api/routes/system.py` | 실제 검색 방식 `bm25-ko-en` 표시 |
| `backend/tests/test_rag_retrieval.py` (신규) | DB 없는 검색·순위·권한 경계 단위 테스트 30개 |
| `backend/tests/test_rag_postgres.py` | 실 DB·HTTP 검색 순위·페이지·인용·필터 회귀 테스트 1개 추가 |
| `backend/tests/test_fastapi_api.py` | health의 검색 방식 표시 검증 |
| `README.md` | 현재 검색 방식·실행/테스트 방법 안내 |
| `docs/architecture.md` | 검색 모듈 책임·권한 경계·한계 설명 |
| `docs/data-model.md` | 기존 테이블 그대로 메모리 검색한다는 설명으로 정정 |
| `docs/specs/api.md` | BM25 입력·출력·토큰화·점수·health 계약 기록 |
| `docs/specs/integrated-answer.md` | 실제 검증된 제한 문서 검색 수용 기준 갱신 |
| `docs/changelog.md` | 구현 범위와 실제 검증 결과 기록 |
| `docs/plans/2026-10-14-bm25-retrieval.md` (신규) | 이 작업의 계획·완료 내역 |
| `docs/plans/2026-10-08-team-module-integration.md` | 과거 literal 설명과 현재 BM25 단계 구분 |
| `docs/README.md`, `docs/plans/README.md` | 신규 계획과 완료 상태 색인 |

`backend/pyproject.toml`, `backend/uv.lock`의 rank-bm25 추가는 사용자가 먼저 수행한 변경이며 그대로 보존했다. `.verification/bm25-db-tests.py`는 로컬 격리 DB 검증 보조 파일로 Git 제외다.

## 5. 위험과 대응

- 비공개 청크가 점수에 영향을 주지 않도록 corpus 구성 전 권한·상태·종류 필터 적용.
- 작은 corpus의 0/음수 점수는 일치 실패가 아님. 토큰 일치 여부로 결과를 선별하고 원래 점수순 정렬.
- 한글 2글자 토큰은 부분 일치를 지원하지만 오탐 가능. 형태소·의미 검색은 제공하지 않음.
- 매 요청 인덱스 재구성은 최신 권한·개정 반영에 단순하지만 대규모 자료에 비용이 큼.

## 6. 열린 질문

- 실제 해사 질문 평가 세트와 Recall@5 측정은 후속 작업.

## 7. 진행 기록

- 2026-10-14: 구현 범위·권한 경계·API 호환 계획 확인.
- 2026-10-14: 구현 완료. 격리 PostgreSQL 포함 backend 315 passed / 4 skipped(기존 적재 데이터셋 필요), frontend 4 passed, Docker Chromium E2E 1 passed. 테스트용 DB 서버·컨테이너 종료. 명령·한계는 [검증 기록](../changelog.md#2026-10-14--bm25-문서-검색)에 기록했다.
