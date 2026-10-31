# 0019. PostgreSQL 원본과 분리한 로컬 E5·Chroma 검색

- 상태: 대체됨(0020)
- 날짜: 2026-10-27
- 결정자: 문서/RAG 요청에 따른 구현
- 관련: [명세](../specs/rag-vector.md), [계획](../plans/2026-10-27-vector-hybrid.md)

## 배경

사용자는 기존 저장/API 변경을 최소화하면서 외부 본문 전송 없이 벡터·RRF 검색을 요청했다.

## 결정

PostgreSQL만 문서·개정·권한의 원본으로 유지한다. Chroma는 삭제 후 재구축 가능한 파생 색인이다.
Docker는 같은 backend 이미지의 Chroma 서버를 내부 profile `vector`로 실행하고 영구 볼륨을 사용한다.
로컬 단일 프로세스 검증은 PersistentClient도 지원하되 서버와 같은 파일을 직접 공유하지 않는다.
고정 revision의 `intfloat/multilingual-e5-small`, CPU, 384차원 정규화 벡터를 사용한다.
512토큰 초과는 임베딩 전용 구간으로 분할 후 평균·정규화한다. DB 청크는 변경하지 않는다.
검색 후보는 DB에서 먼저 권한 필터링하고 색인 누락/오래됨이 있으면 BM25로 명시적 fallback한다.
RRF는 기본 k=60, 각 검색 후보 30개, 최종 5개로 시작한다. 품질 최적값이라는 뜻은 아니다.

## 검토한 대안

| 대안 | 판단 |
|---|---|
| 외부 임베딩 API | 본문 외부 전송 제외 요구 때문에 채택하지 않음 |
| pgvector | PostgreSQL 확장·스키마 변경을 피하고 요청한 Chroma 사용 |
| 더 큰 E5/BGE 모델 | CPU 개발환경의 비용을 줄이기 위해 small부터 평가 |
| 자동 동기 저장 | 기존 저장 트랜잭션을 확대하지 않고 명시적 재색인 CLI 사용 |

## 결과

모델 다운로드는 별도 준비 단계이고 검색은 로컬 파일만 읽는다. 모델/입력 규칙 변경은 별도 collection으로
분리한다. 재시작 시 모델은 다시 로드되지만 파일/벡터는 유지된다. DB와 Chroma 동시 변경의 완전한
트랜잭션이나 대량 색인의 무중단 전환은 보장하지 않는다. 동기화 전에도 권한은 DB가 결정한다.

근거: [공식 모델 카드](https://huggingface.co/intfloat/multilingual-e5-small),
[Chroma API](https://docs.trychroma.com/reference/python/collection).
