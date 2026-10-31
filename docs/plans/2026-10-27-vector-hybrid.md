# 로컬 벡터 검색과 RRF

- 상태: 완료
- 작성: Codex · 2026-10-27
- 담당: 문서/RAG
- 관련: [명세](../specs/rag-vector.md), [ADR](../adr/0019-local-vector-retrieval.md)

## 1. 배경과 목표

기존 PostgreSQL 청크와 접근 제어를 재사용해 한영 벡터 검색과 순위 결합을 추가한다.
사용자 지시에 따라 dfb262f 기준으로 구현하며 9a14ff1 캐시 커밋은 가져오지 않는다.
사용자가 추가한 chromadb/sentence-transformers 의존성을 보존한다.

## 2. 범위

- 포함: CPU 임베딩, 명시적 모델 준비·증분 색인 CLI, Chroma, RRF, 검색 모드, 진단·검증.
- 제외: PDF 추출·청킹 변경, PostgreSQL 스키마/원본 변경, UI, 외부 임베딩 API, 브랜치 병합·커밋·푸시·실서비스 재시작.

## 3. 단계

- [x] 현재 구조·의존성·권한·공식 모델 문서 확인 및 설계 설명.
- [x] 모델·색인·RRF 독립 모듈 및 최소 API 연결.
- [x] 준비·색인·비교 CLI, Docker 영속화·CPU 의존성 검증.
- [x] 단위·실제 임베딩·소량 실제 DB·전체 backend·격리 E2E.
- [x] 실행/재색인/실패 정책·측정·한계 문서화.

## 4. 영향 받는 파일

api/rag_* 새 모듈, store/documents.py, routes/system.py, scripts/의 CLI,
backend 의존성·Dockerfile, compose 및 .env.example, 관련 테스트·문서.

## 5. 위험과 대응

색인과 DB는 원자적이지 않다. 내용/모델 fingerprint 확인, 권한 사전 필터와 DB 최종 재조회,
미색인 후보가 있으면 전체 BM25 fallback을 사용한다. 모델 준비는 명시적 다운로드만 허용한다.

## 6. 열린 질문

대규모 후보 조회 성능과 해사 전문 정확도는 작은 평가와 구분한다.

## 7. 진행 기록

- 2026-10-27: 구현 착수. 실제 데이터는 제한된 검증용 별도 색인에만 기록한다.
- 2026-10-27: 구현 완료. backend 438 passed/4 skipped, Docker E2E 1 passed,
  실제 DB 36개 청크·로컬 모델·Docker Chroma 재시작 검증. 수치/한계는 [변경 이력](../changelog.md).
  전체 색인·실서비스 전환·캐시 병합은 수행하지 않았다. 커밋·푸시·브랜치 변경 없음.
