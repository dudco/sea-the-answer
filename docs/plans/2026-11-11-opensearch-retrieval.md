# OpenSearch 키워드 검색 전환

- 상태: 완료
- 작성: Codex · 2026-11-11
- 담당: 문서/RAG
- 관련: [명세](../specs/rag-lexical.md), [ADR 0023](../adr/0023-opensearch-lexical-index.md)

## 목표와 범위

Python의 요청별 Kiwi 분석·BM25 생성을 영속 OpenSearch/Nori 역인덱스로 대체한다. PostgreSQL 원본, Chroma/E5, Python RRF, UI·인용 계약은 유지한다. 실제 앱 데이터 변경·재시작·커밋·푸시는 제외한다.

## 단계

- [x] 기존 호출·권한·작업 트랜잭션과 Docker 구조 분석
- [x] 독립 검색 모듈, 분석 계약, 버전별 색인·진단 구현
- [x] 트랜잭션 outbox·worker·초기 색인/검증 CLI 구현
- [x] 검색 경로·Docker 연결, 사용하지 않는 의존성 정리
- [x] 단위·격리 통합·회귀·Docker E2E·합성 성능 검증
- [x] 현재 안내와 검증 기록 최소 갱신

## 영향과 위험

공통 변경은 Compose, 새 migration, 검색 결과 재확인 범위, 필요한 테스트/문서다. OpenSearch 장애는 문서 저장에 영향을 주지 않는다. 검색 시 전체 PG 후보 본문 읽기는 기존 벡터 입력 해시 검증 때문에 남는다. 전역 통계와 Nori 전환은 순위를 바꾸므로 기능·성능 검증을 정확도 개선으로 표현하지 않는다.
