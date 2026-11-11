# 문서별 벡터 준비 상태와 부분 하이브리드 검색

- 상태: 완료
- 작성: Codex · 2026-11-05
- 담당: 문서/RAG
- 관련: [검색 계약](../specs/rag-vector.md), [ADR 0022](../adr/0022-document-vector-readiness.md)

## 배경과 범위

검색마다 전체 record를 검사하는 비용과 한 문서 미색인으로 전체 fallback하는 동작을 개선한다.
PG 원문·권한·작업 큐, BM25·RRF·모델·HTTP 계약은 유지한다. 실제 앱 데이터에는 쓰지 않는다.

## 단계와 완료 조건

- [x] 기존 큐·generation·내용 해시를 검토하고 준비 상태 계약 확정.
- [x] 문서 snapshot/collection UUID에 연결한 완료 확인 정보와 worker/CLI 공유 검증 구현.
- [x] 준비 문서만 벡터 참여, 전체 BM25 유지, 진단·검증/복구 CLI 구현.
- [x] 부분 실행·동시 변경·손상·필터 회귀 및 합성 corpus 비용 비교.
- [x] backend 전체·격리 Docker E2E 실행 및 결과 기록.

## 영향 파일

RAG 준비 상태 모듈, vector/search/jobs, 색인 CLI, 관련 테스트와 현재 명세·운영 안내.
API/문서 저장·DB 스키마 변경은 필요하지 않다.

## 위험과 대응

전체 스캔을 없애면 반환되지 않은 record 손상을 즉시 보장하여 탐지할 수 없다.
반환 record는 검사하고 전체 감사는 명시적 verify로 제공한다. 부분 corpus에 따른 RRF 순위 변화는 정확도 향상으로 보고하지 않는다.

## 진행 기록

- 2026-11-05: 기존 generation fencing과 immutable record ID를 재사용하는 설계 확정.
- 2026-11-09: CLI `--limit` 보완 포함 격리 PostgreSQL 전체 backend 861 passed / 4 skipped. 별도 해사 실데이터 DB 미설정 4건이며 실제 앱 DB를 연결하지 않았다. 같은 합성 1,000청크/10문서에서 준비 확인 metadata get 4회/1,000건 → 1회/10건, 86.73ms → 20.59ms(로컬 단회, 전체 검색 시간 아님).
- 2026-11-09: 이전에 검증한 동일 모델/잠긴 의존성 이미지 위에 현재 api를 COPY한 임시 빌드로 Docker E2E 19 passed. 실제 오프라인 E5/HTTP Chroma에서 worker 재시작·재시도·동시 실행·부분 hybrid·수동 완료 확인·부분 검색 범위를 확인했다. 새 기본 이미지의 모델 재다운로드 빌드는 장시간 대기로 중단했으므로 완료를 주장하지 않는다. 검증용 컨테이너·네트워크·합성 벡터 볼륨 정리 완료. 상세 명령/범위는 [변경 이력](../changelog.md)에 기록한다.
