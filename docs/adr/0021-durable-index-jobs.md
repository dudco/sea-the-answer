# 0021. PostgreSQL 작업 큐와 이미지에 포함한 E5 모델

- 상태: 채택
- 날짜: 2026-10-29
- 결정자: 문서 저장 후 자동 색인·모델 이미지 포함 사용자 요청
- 관련: [계약](../specs/rag-index-jobs.md), [이전 ADR](0020-dedicated-chroma-image.md)

## 배경

수동 색인은 문서 저장과 분리되어 누락되며 런타임 모델 볼륨 준비가 필요했다.
저장 응답 지연 없이 재시작·장애를 복구해야 한다.

## 결정

저장과 같은 트랜잭션의 PostgreSQL outbox 및 별도 Python worker를 사용한다.
세션 advisory lock과 세대/claim 조건부 갱신으로 중복 처리와 오래된 완료를 방지한다.
새 migration만 추가하며 Redis/Celery는 사용하지 않는다.
backend/worker 이미지 공통 모델 stage에 pinned E5를 다운로드·검증하고 /opt/models로 복사한다.
기존 rag-models 볼륨은 삭제하지 않고 마운트를 해제한다. Chroma 전용 이미지·벡터 볼륨은 유지한다.
0020의 나머지 검색·권한·CPU·길이·fallback·RRF 결정을 계승한다.

## 검토한 대안

| 대안 | 판단 |
|---|---|
| 저장 요청에서 동기 임베딩 | 응답 지연·Chroma 장애가 저장을 방해 |
| 메모리 BackgroundTasks | 프로세스 종료 시 작업 손실 |
| Redis/Celery | 현재 규모에서 추가 인프라 불필요 |
| PG 큐+별도 worker | 기존 DB로 지속성·원자적 작업 등록 확보 |

## 결과

이미지와 첫 빌드 시간이 증가하지만 실행 시 별도 모델 다운로드가 없다.
worker는 별도 모델 RAM과 PG 세션을 사용한다. 색인 완료는 비동기이며 미완료 검색은 BM25 fallback한다.
전체 기존 문서·모델 교체·복원 후 복구는 명시적 enqueue가 필요하다.
