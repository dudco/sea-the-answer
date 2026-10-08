# 팀 모듈 연결 로드맵

- 상태: 초안
- 작성: 2026-10-08
- 담당: 단계별로 지정 (아래 표의 "담당" 칸을 팀 회의에서 채워 주세요)
- 관련: [`../architecture.md`](../architecture.md#5-교체-지점-팀-모듈-연결), [`../specs/integrated-answer.md`](../specs/integrated-answer.md), [`../specs/api.md`](../specs/api.md)

## 1. 배경과 목표

1.3.1은 화면·API·DB·권한·백업까지 동작하는 기반이지만, 해답의 핵심인 **해사 문서 RAG**와 **운항 데이터 Tool Calling LLM**은 단순한 버전으로 자리만 잡혀 있습니다. 이 계획은 팀의 전문 모듈을 기존 화면과 계약을 깨지 않고 붙이는 순서를 정합니다.

| 영역 | 현재 (1.3.1) | 목표 |
|---|---|---|
| 문서 검색 | SQLite FTS5 + BM25, 한영 용어 사전 | 벡터 + 키워드 하이브리드 RAG, 교차 언어 검색 |
| 답변 생성 | 원문 발췌, 선택적 OpenAI Responses API | 동국 AI CHAT API(개발) / Local LLM(테스트) 연결, 근거 인용 유지 |
| 질문 해석 | 단어 규칙, 선박·기간은 UI 선택 | 의도 분류 + 질문 속 선박·기간 추출, Tool Calling |
| 계산 | CO₂, 단순 DWT 집약도, 항해 시간 | 공식 CII 산식·보정·등급, 추가 Tool |
| 문서 형식 | 텍스트 PDF | DOCX, PPT, 일반 텍스트 추가 |
| 보고서 | 팀 검토용 Noon/MRV 초안 | 팀이 확정한 필수 항목·제출 서식 |

환경 전제(팀 결정): 일반 개발은 팀원 노트북 + 동국 AI CHAT API 크레딧, 테스트 환경은 AWS GPU 인스턴스의 Local LLM(Qwen 계열 4bit).

## 2. 범위

- 포함: 백엔드 교체 지점(`db.retrieve`, `rag.generateGrounded`, `analysis.integratedAnswer`, `tools.mjs`, 문서 수집)과 필요한 화면 수정
- 제외: 인터넷 공개 배포, TLS, 대규모 페이징 (별도 계획)

## 3. 단계

각 단계는 독립적으로 머지할 수 있게 나눴습니다. 순서는 의존 관계 기준이며 2·3·5단계는 병렬 진행이 가능합니다.

### 1단계 — LLM 공급자 추상화

- [ ] `rag.mjs`의 OpenAI 전용 호출을 공급자 인터페이스로 분리 (`OPENAI_*` 호환 유지)
- [ ] 동국 AI CHAT API 공급자 추가 — 엔드포인트·인증·모델명은 `.env`로 (`HAEDAP_LLM_PROVIDER` 등, 이름은 명세에서 확정)
- [ ] OpenAI 호환 Local LLM 엔드포인트(AWS) 공급자 추가
- [ ] 명세 작성: `specs/llm-provider.md` (입력·출력·타임아웃·실패 시 동작)
- [ ] ADR: 기본 공급자와 키 관리 방식
- 완료 조건: 모의 공급자 테스트 통과 + 실제 1개 공급자로 인용 검증을 통과한 답변 1건을 `changelog.md`에 날짜와 함께 기록

### 2단계 — 하이브리드 검색

- [ ] 임베딩 생성 위치 결정(로컬 모델 vs API) → ADR
- [ ] 청크 임베딩 저장 테이블 추가 → `data-model.md` 갱신, 백업 대상 여부 결정
- [ ] `retrieve`에 벡터 점수 + BM25 결합, `allowedIds` 필터 유지
- [ ] 평가 세트(질문–정답 청크) 작성과 Recall@5 측정 스크립트
- 완료 조건: 기존 검색 테스트 통과 + 평가 세트에서 FTS 대비 Recall 비교 결과 기록

### 3단계 — 문서 형식 확장

- [ ] DOCX, PPT(X), 일반 텍스트 추출 방식 결정(브라우저 vs 서버) → ADR
- [ ] 추출 결과를 기존 `sections[{page, heading, text}]` 형식으로 변환 (페이지 개념이 없는 형식의 `page` 규칙 정의)
- [ ] 문서 화면 업로드 허용 형식 확장, 원본 파일 저장(`document_files`) 형식 일반화
- 완료 조건: 형식별 샘플 1개씩 등록 → 검색·인용·원본 열기 확인

### 4단계 — 의도 분류와 Tool Calling

- [ ] 질문에서 작업 유형·선박·기간 추출 (UI 선택값이 있으면 우선)
- [ ] `toolDefinitions`를 LLM Tool 스키마로 노출하고 호출 결과를 `toolRuns`에 기록
- [ ] [`specs/integrated-answer.md`](../specs/integrated-answer.md) 출력 형식 유지 확인
- 완료 조건: 대표 질문 시나리오(규정만 / 운항만 / 통합 / 보고서)별 브라우저 검증 통과

### 5단계 — 공식 CII 계산

- [ ] 선종별 기준선·보정계수·연간 완전성 등 필요한 입력 정의 → `specs/cii.md`
- [ ] 계산 모듈 구현(Node 또는 Python Tool — 실행 방식 결정 → ADR)
- [ ] `cii.status:'available'` 반환 조건 명시, 조건 미달 시 기존처럼 `unavailable` + 사유
- 완료 조건: 공개 예제 값과 대조한 테스트 통과

### 6단계 — 보고서 서식 확정

- [ ] 팀이 Noon/MRV 필수 항목 확정 → 명세
- [ ] `generateReport` 갱신, 누락 항목 표시 규칙 유지
- 완료 조건: 확정 항목 체크리스트 기준 생성 결과 확인

## 4. 영향 받는 파일·문서

| 경로 | 단계 |
|---|---|
| `backend/rag.mjs`, `.env.example` | 1 |
| `backend/db.mjs`, `backend/knowledge.mjs`, `docs/data-model.md` | 2, 3 |
| `frontend/src/lib/pdf.js`(또는 새 추출 모듈), `frontend/src/views/forms.jsx` | 3 |
| `backend/analysis.mjs`, `backend/tools.mjs` | 4, 5, 6 |
| `docs/specs/*`, `docs/adr/*`, `docs/changelog.md`, `README.md` | 전 단계 |

## 5. 위험과 대응

| 위험 | 대응 |
|---|---|
| API 크레딧 소진 | 개발 중에는 모의 공급자·발췌 모드로 테스트, 실제 호출은 검증 시에만 |
| LLM이 근거 밖 내용 생성 | 기존 인용 검증(원문 포함 여부)을 모든 공급자에 동일 적용 |
| 검색 교체로 권한 누수 | `allowedIds` 필터를 검색 입력 단계에 유지, 기존 권한 테스트를 회귀로 사용 |
| 스키마 변경으로 기존 DB·백업 호환 깨짐 | `data-model.md` 8절 절차 준수, 이전 DB 회귀 테스트 추가 |

## 6. 열린 질문

- 동국 AI CHAT API의 엔드포인트 형식이 OpenAI 호환인지
- 임베딩 모델을 오프라인으로 돌릴지, API로 돌릴지
- Python 기반 팀 모듈을 쓸 경우 Node 서버와의 연결 방식(별도 프로세스 HTTP vs CLI)

## 7. 진행 기록

- 2026-10-08: 계획 초안 작성
