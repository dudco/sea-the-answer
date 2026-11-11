# 0022. 문서 snapshot별 Chroma 완료 확인 정보로 벡터 참여를 결정한다

- 상태: 채택
- 날짜: 2026-11-05
- 결정자: 문서/RAG 작업
- 관련: [계획](../plans/2026-11-05-vector-readiness.md), [계약](../specs/rag-vector.md), [기존 작업 큐](0021-durable-index-jobs.md)

## 배경

작업 done은 과거 실행 기록이며 현재 벡터 준비 증거가 아니다. 검색마다 모든 record를 조회하지 않으면서 미색인 문서를 BM25로 검색해야 한다.

## 결정

0021의 작업 큐·CPU 모델 이미지·권한·RRF 결정을 계승하고 준비 판정·fallback 정책을 대체한다. 별도 Chroma readiness collection에 문서 개정 ID·정렬한 전체 청크 내용 해시·모델 fingerprint·벡터 collection UUID를 묶은 완료 확인 정보를 저장한다. 검색용 ANN collection과 분리하며 원문은 넣지 않는다. 추가 PG migration은 만들지 않는다.

worker와 수동 CLI는 전체 문서 record 검증에 성공한 경우만 같은 함수를 통해 확인 정보를 기록한다. 부분 청크 실행은 문서 전체 완료가 아니다. 서로 다른 내용 snapshot은 서로 다른 키이므로 늦은 실행이 최신 snapshot을 덮어쓰지 않는다. worker는 최종 문서/작업 잠금과 generation/claim 확인도 유지한다.

검색은 현재 PG 허용 후보로 snapshot을 계산하고 문서별 정보를 묶어서 조회한다. 준비된 문서만 벡터 검색에 포함하고 BM25는 전체 후보를 유지한다. collection 삭제·재생성은 UUID로 구별한다. 반환 metadata/개수 불일치는 전체 fallback, 미준비 문서는 정상 부분 참여로 구별한다.

## 검토한 대안

| 대안 | 채택하지 않은 이유 |
|---|---|
| PG 준비 테이블 | 가능하지만 DB 마이그레이션과 요청/CLI 전달 변경이 필요하며 Chroma 세대 확인은 여전히 필요 |
| jobs.done 재사용 | 실제 snapshot·collection 교체를 증명하지 못함 |
| 전체 present 캐시 | 만료·무효화 외에 다시 전체 원격 검사가 필요 |

## 결과

검색 시 원격 metadata 확인량은 청크 수에서 문서 수로 줄지만 PG 조회·내용 해시·허용 ID 전달은 남는다. 임의 record 손상을 모두 검색 시 발견한다고 보장하지 않는다. 명시적 verify는 전체 검증과 손상 표시를, index/worker는 복구를 수행한다. PG와 Chroma의 원자성을 가정하지 않으며 준비 정보는 재생성 가능한 파생 자료다. 0021의 작업 큐 결정은 유지한다.
