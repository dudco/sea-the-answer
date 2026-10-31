# 자동 벡터 색인과 이미지 내 모델

- 상태: 완료
- 작성: Codex · 2026-10-29
- 담당: 문서/RAG
- 관련: [계약](../specs/rag-index-jobs.md), [ADR 0021](../adr/0021-durable-index-jobs.md)

## 1. 배경과 목표

문서 저장 트랜잭션에 지속성 작업을 기록하고 별도 worker로 커밋 후 색인한다.
고정 E5 파일은 backend/worker 이미지에 포함하고 검색 시 다운로드하지 않는다.

## 2. 범위

기존 Chroma 전용 이미지 변경을 보존한다. UI/API 응답·검색·청킹은 유지한다.
실제 앱 데이터 변경, 대량 색인, 서비스 재시작, 커밋·푸시는 제외한다.

## 3. 단계

- [x] 저장 경계·모델·Docker·관련 테스트 분석 및 설계 설명.
- [x] 작업 migration·enqueue·worker·진단 CLI 구현.
- [x] 모델 빌드 레이어·운영/개발 Docker 연결.
- [x] 단위·격리 DB/Chroma·실제 모델·전체 backend·E2E 검증.
- [x] 운영 안내·측정·한계 기록.

## 4. 영향 받는 파일·문서

RAG 작업 모듈, documents.py 최소 호출, 신규 migration, Docker, 테스트 및 관련 설계·운영 문서.

## 5. 위험과 대응

PG와 Chroma는 원자적이지 않다. 세대 조건부 완료, 세션 advisory lock, immutable 벡터 ID,
재시도와 현재 DB 후보 제한으로 처리한다. 모델 경로는 기존 볼륨 밖 /opt/models다.

## 6. 열린 질문

실제 대량 처리 성능은 이번 합성 소량 검증 범위 밖이다.

## 7. 진행 기록

- 2026-10-29: feature/rag-vector에서 기존 미커밋 Chroma 분리를 보존하며 시작.
- 2026-10-29: 456 passed/4 skipped, 실제 E5·격리 PG/Chroma 자동 색인·장애 복구·동시 worker,
  Docker 운영/개발 이미지의 네트워크 없는 추론 및 E2E 통과. 상세 기록은 [변경 이력](../changelog.md).
  실제 앱 적용·전체 실제 데이터 색인·커밋·푸시는 수행하지 않았다.
