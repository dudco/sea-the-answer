# 자동 색인 작업 계약

- 상태: 구현됨
- 작성: Codex · 2026-10-29
- 관련: [계획](../plans/2026-10-29-automatic-vector-indexing.md), [ADR](../adr/0021-durable-index-jobs.md)

## 1. 목적

저장 HTTP 응답에서 임베딩을 기다리지 않고 커밋된 문서를 복구 가능한 작업으로 색인한다.

## 2. 범위

등록·개정·동일 입력 저장과 `mode: metadata` 저장 모두 현재 모델 작업을 요청한다.
정보 수정은 원문·청크·PDF를 바꾸지 않으며, 상태 재활성화·누락 색인의 복구도 작업 큐로 처리한다.
변경 없는 정보 저장도 원문 변경 없이 작업만 요청한다. UI가 요청 자체를 생략한 경우에는 작업이 생성되지 않는다.
검색 모드와 독립적이다.
기존 문서 전체 스캔은 명시적 enqueue CLI에서만 수행한다. 원문/권한은 PostgreSQL이다.

## 3. 인터페이스

`enqueue(store, document_id)`는 호출자의 트랜잭션 안에서 실행하며 자체 commit하지 않는다.
`python -m api.rag_worker run`은 별도 프로세스다. `status`, `enqueue`, `retry`로 운영한다.
enqueue/retry는 기본 미리보기, 쓰려면 `--apply`; 문서 ID 필터와 limit를 제공한다.
API payload/응답 계약은 바뀌지 않는다. 오류는 허용 목록의 고정 코드만 기록한다.

## 4. 동작 규칙

- 문서 개정 ID+모델 fingerprint당 작업 하나. 요청마다 generation 증가, pending으로 재설정.
- worker는 현재 fingerprint 작업만 처리한다. 이전 모델 작업은 보존되며 새 모델 enqueue로 복구한다.
- 별도 PG 세션 advisory lock을 작업 처리 중 유지한다. 죽은 세션의 잠금은 DB가 해제하고 processing은 재획득 가능하다.
- pending/failed는 next_attempt_at 이후 실행. 실패는 최대 5회, 지수 backoff(최대 300초); CLI retry가 횟수를 초기화한다.
- 작업 세대·claim token이 모두 같은 경우만 완료/실패 갱신한다. 새 저장은 이전 실행의 완료를 무효화한다.
- 실행 전/완료 전 활성 개정·status 확인. 비활성/삭제는 cancelled. 권한은 색인 대상 제외 조건이 아니며 검색에서 항상 PG 권한을 적용한다.
- 벡터는 기존 VectorIndex.index와 immutable ID를 사용. CLI/worker 중복 실행은 같은 ID upsert로 수렴한다.
- 새 벡터 record의 embedding_input_hash로 실제 입력이 같은 개정의 임베딩 값도 재사용한다.
  title/reference/heading/text 변경은 재계산, scope/페이지/ID만 다른 경우에는 새 metadata record에 기존 값을 연결한다.
- Chroma에서 재사용한 ndarray와 새 임베딩 리스트는 upsert 직전에 모두 float 리스트로 통일한다.
  부분 완료 후 재시도에서도 배치 순서에 따라 입력 형식이 달라지지 않는다.
- Chroma 성공 후 PG 완료 기록 실패는 재처리로 복구한다. 오래된 벡터는 검색 후보에 포함되지 않는다.
- 백업 JSON에 작업을 포함하지 않는다. 복원 후 enqueue --apply로 재구축한다. 실제 앱 기존 자료를 자동 소급 색인하지 않는다.
- Docker 빌드에서 pinned 모델 다운로드/로컬 로딩 검증. 런타임은 /opt/models/e5-small, 다운로드 금지.

## 5. 수용 기준

- [x] commit/rollback·중복 worker·중단 복구·개정·삭제·실패 재시도 검증.
- [x] 기존 검색/답변 계약·필터 회귀.
- [x] 이미지 내 모델 오프라인 추론·격리 통합·E2E 검증.

## 6. 열린 질문

임베딩 중 프로세스가 멈추면 DB 세션이 살아 있는 동안 재획득하지 않는다. 운영자가 worker를 재시작해 복구한다.
근거: [PostgreSQL 세션 잠금](https://www.postgresql.org/docs/18/explicit-locking.html#ADVISORY-LOCKS)은
세션 종료 시 해제된다. 모델 다운로드는 [Hugging Face snapshot_download](https://huggingface.co/docs/huggingface_hub/en/guides/download)의 고정 revision/local_dir를 사용한다.
