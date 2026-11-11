# 질문 분석을 LLM 도구 선택으로 전환

- 상태: 진행 중
- 작성: 윤영채 · 2026-11-12
- 담당: 윤영채
- 목표 일자: 미정
- 관련: [통합 답변 계약](../specs/integrated-answer.md), [ADR 0015](../adr/0015-optional-model-workflow-skills.md), [질문 표현 다양성 계획](2026-11-11-question-routing-coverage.md), [ADR 0024](../adr/0024-llm-tool-selection.md)

## 1. 배경과 목표

현재 `/api/ask`의 자동 질문(`task=auto`)은 `backend/api/question_router.py`의 `answer()`가 정규식 처리기를 차례로 시도해 작업을 정한다. 순서는 자료 현황 후속 질문 → 자료 현황(`dataset_intent.inventory_request`) → 항만 비교(`navigation_query.try_answer`) → 운항·MRV 워크플로(`question_intent.classify`) → 설명 요청(`explanation_request`)이다. 모든 처리기가 거절하고 `mode=llm`일 때만 `model_route()`가 action 하나를 JSON으로 고른다. 선박·기간 같은 인자는 각 처리기가 질문 원문에서 다시 정규식으로 뽑는다.

이 구조는 정규식이 모르는 표현을 놓치고, 모델은 규칙이 실패한 뒤에만 보조로 쓰인다. 목표는 다음과 같다.

- 문서 검색은 모든 질문에서 항상 실행해 답변 근거를 확보한다.
- 추가로 실행할 데이터 도구와 그 인자는 LLM이 네이티브 tool calling으로 고른다.
- 서버는 도구 이름 allowlist, 인자 스키마, 권한, 등록 선박·문서 대조로 검증한 뒤 기존 실행기를 호출한다.
- 기존 정규식 경로는 legacy로 코드에 남기되 기본 경로에서는 쓰지 않는다.

## 2. 결정 사항 (2026-11-12 합의)

| 항목 | 결정 |
|---|---|
| 기준 브랜치 | 최신 `main`(`5b09c09`)에서 `feature/llm-tool-selection` |
| 모델 권한 | 도구와 인자를 고른다. 서버가 검증한 값만 실행한다. SQL·식별자·수치·권한은 정하지 않는다. |
| 검색 | 모든 질문에서 문서 검색을 항상 실행한다(모델 선택 대상 아님). 모델은 추가 데이터 도구 0개 이상을 고른다. 라우팅 모델에는 검색 본문을 넣지 않는다. |
| 답변 방식 | 화면의 "원문 발췌/AI 답변" 선택과 `mode`를 제거한다. 모델 미설정이면 오류(`MODEL_NOT_CONFIGURED`)를 반환한다. 답변 생성 실패 시 검색 문단 표시는 안내 문구와 함께 유지한다. |
| 정규식 경로 | legacy로 남기고, 명시한 환경변수(예: `HAEDAP_QUESTION_ROUTER=legacy`)에서만 사용한다. 모델 호출 실패는 되묻기로 처리한다. |
| 후속 질문 | 자연어 후속 질문도 모델이 처리한다. 소유권을 확인한 이전 답변의 작업·범위 요약을 함께 전달한다. 되묻기 카드의 구조화 입력(`workflowInput`)은 기존 처리 유지. |
| 날짜 | 모델은 "지난달" 같은 원문 기간 표현만 넘기고, 기존 해석기(`question_intent.date_slots`)가 ISO 날짜로 바꾼다. |
| 도구 표시 | 이번에는 답변 완료 후 사용한 도구를 표시한다. 실시간 표시(스트리밍)는 후속 작업. |
| 도구 형식 | 이번에는 등록부 한곳에 모으기만 한다. 입출력 형식 통일(Convention)은 후속 작업. |

## 3. 현재 도구 목록 (2026-11-12, `5b09c09` 기준)

도구 역할을 하는 기능이 네 곳에 흩어져 있고, 인자 정의 방식도 서로 다르다. 한곳에서 전체를 보여 주는 등록부는 없다. `GET /api/tools`는 계산기 2개만 반환한다.

### 3.1 질문 경로가 쓰는 내부 실행기

`question_router.answer()`가 부르는 읽기 전용 실행기다. 대부분 질문 원문을 직접 받아 내부에서 인자를 정규식으로 추출하므로, 모델 도구로 쓰려면 구조화된 인자를 받는 진입점을 분리해야 한다.

| 후보 이름 | 현재 코드 | 받는 인자 | 하는 일 | 원문 의존 |
|---|---|---|---|---|
| `search_documents` | `store/documents.py` `DocumentStore.search(user, question, kind, document_ids)` | 질문(≤2000자), 범위 `all`·`imo`·`manual`, 문서 ID 목록 | 열람 권한 필터를 먼저 적용한 하이브리드 검색, 상위 5개 근거 | 질문을 검색어로 사용 (정상) |
| (답변 생성) | `store/answers.py` `AnswerStore.answer(user, payload)` | 질문, `mode`, `task`, `outputFormat`, `context`(선박·기간), `calculation` | 검색 → 인용 검증된 답변 생성 → 저장. 운항 키워드가 있으면 화면에서 고른 선박·기간으로 운항 요약 추가 | `needs_ops`를 정규식으로 판단 |
| `ask_selected_documents` | `question_workflows` `Scope(action=selected_document)` → `workflow_skills.selected_evidence` | 문서 ID ≤5(열람 권한), 문서 질문 | 지정 문서 안에서만 근거 검색·답변 | 문서 제목을 원문에서 매칭 |
| `summarize_operations` | `question_workflows.run_tools` `operations_summary` → `workflow_skills.operation_result` | 선박 ≤2(등록 선박 스냅숏), 기간 ≤2(ISO, ≤366일), 표·차트 표시 여부 | 일별 운항기록의 연료·CO₂·거리 합계, 2개 이상이면 산술 비교 | 선박·기간·표/차트를 원문에서 추출 |
| `calculate_mrv_reference` | `run_tools` `mrv_reference` → `tools.reference_intensity.calculate_reference` | 선박 ≤2, 연도 ≤3, `reference_ack`(사용자 확인 필수) | MRV 보고 CO₂·공개 DWT 후보로 참고 탄소집약도 계산. 공식 CII·등급 아님 | 선박·연도·동의 표현을 원문에서 추출 |
| `calculate_operations_and_mrv` | `run_tools` `combined` | 위 두 도구의 인자 합집합 | 운항 합계와 MRV 참고값을 함께 계산. 전체 조회 최대 4회 | 동일 |
| `compare_port_conditions` | `navigation_query.try_answer` → `navigation_service.compare_ship` + `select_results` | 앱 선박(실제 MRV 연결 필요), 항구 ID 목록, 선석 ID, 조건(길이·폭·흘수 m의 이상·이하, 정렬, 상태 필터) | 공개 선석 게시 조건과 선박 제원의 부분 비교. 입항 허가 판정 아님 | 선박·항구·조건을 원문에서 추출 (`parse_conditions`) |
| `get_dataset_status` | `dataset_status.answer(ctx, datasets)` | 자료 종류 `ais`·`mrv`·`dwt`·`noon`·`operations`·`documents`·`ports` | 서버에 등록된 자료의 유무·건수·출처·수집일 | 선박·기간 범위를 원문에서 추출 |
| `get_ais_catalog_status` | `navigation_query.catalog_status_answer(ctx, question)` | 선박(선택) | 연결된 AIS 수집본의 관측 수·선박 수, 특정 선박 관측 여부 | 선박 범위를 원문에서 추출 |

### 3.2 화면·앱 API에서 직접 쓰는 도구

로그인 세션과 역할 권한을 통과한다.

| 이름 | 경로 | 받는 인자 | 하는 일 | 부작용 |
|---|---|---|---|---|
| `calculate_emissions` | `POST /api/tools/calculate_emissions` (`store/tools.py`) | 연료 t(0~1e7), 배출계수(>0~10), DWT, 거리 nm | 배출량·단순 집약도 산술 | `tool_runs`에 실행 기록 저장 |
| `voyage_time` | `POST /api/tools/voyage_time` | 시작·종료 UTC ISO 시각, 시작·종료 UTC 오프셋(분, 15분 단위) | 경과 시간·선내 시각 계산 | `tool_runs`에 실행 기록 저장 |
| 업무 스킬 6종 | `GET /api/skills`, `POST /api/skills/run` (`workflow_skills.SkillRequest`) | 스킬 ID, 질문, 문서 ID ≤20, 선박·기간, 연도, `use_model`, 응답 ID, 보고서 양식 | `mrv-analysis`, `selected-document-answer`, `operation-summary`, `report-draft`(초안·저장 안 함), `checklist`, `qa-evaluation`(내 저장 응답 검사) | 실행 기록 |
| 선석 비교 화면 | `POST /api/operations/port-reference-screen` (`ScreenRequest`) | 선박, 항구 ID(`WPI:n`), 선석 ID, 가정 조건(`Scenario`) | 한 항구의 게시 조건 비교, 가정 조건 시험 | 없음 |
| 항구 카탈로그 | `GET /api/operations/port-references` | 없음 | 선석 참조 자료의 출처·제공 항구 | 없음 |
| 운항 목록 | `GET /api/operations` | 없음 | 등록 선박·운항기록 전체 | 없음 |

### 3.3 서버 전용 Tool API

`backend/tools/api.py`, `/api/maritime-data/*`. 서버 Bearer 토큰(`MARITIME_DATA_API_TOKEN`)으로만 인증하며 사용자별 권한을 검사하지 않는다. **모델 도구로 그대로 노출하지 않는다.**

| 경로 | 입력 | 하는 일 |
|---|---|---|
| `POST query` | `MaritimeDataQuery`: `real_annual`(연도 범위 ≤10년) 또는 `synthetic_noon`(기간 ≤366일), 선박·항차 ID, `limit` ≤200 | 승인 뷰 원자료 조회 |
| `GET factors` | 없음 | 고정 버전 배출계수 카탈로그 |
| `POST calculate` | `CalculationRequest`: 범위, 계수 버전, 연료 매핑 ≤2 | CO₂ 산술·입력 준비 상태 |
| `POST reference-intensity` | `ReferenceIntensityRequest` | MRV 참고 집약도 |
| `POST ask` | 질문, 고정 범위, `use_model` | 규칙 기반 조회 도우미. 모델 사용 시 `query_maritime_data` 하나를 빈 인자로 강제 호출 |
| `GET port-reference-catalog`, `POST port-reference-screen` | 위 3.2와 같음 | 선석 참조 |

### 3.4 모델 도구에서 제외

쓰기·관리·인증 기능은 모델이 고를 수 없다: 운항 자료 검증·예시·가져오기(`operations/validate`, `operations/example`, `operations/import/*`), 변경 요청·검토(`changes`), 보고서 저장·생성·제출(`reports/*`), 관리자(`users`, `backups`, `logs`), 인증(`auth/*`), 대화 삭제.

### 3.5 이번 작업의 모델 도구 (초안)

문서 검색은 항상 실행하므로 목록에 없다. 날짜는 원문 표현(`period_text`)으로 받아 기존 해석기가 바꾸고, 선박은 원문 표기(`ship_mentions`)로 받아 등록 선박 목록과 대조한다.

| 도구 | 인자 | 서버 검증 |
|---|---|---|
| `get_dataset_status` | `datasets`(enum, 1개 이상), `ship_mentions`, `period_text` | 자료 종류 allowlist, 선박 대조 |
| `get_ais_catalog_status` | `ship_mentions` | 선박 대조 |
| `summarize_operations` | `ship_mentions` ≤2, `period_text`, `display`(`text`·`table`·`chart`) | 기간 ≤366일, 최대 4회 조회 |
| `calculate_mrv_reference` | `ship_mentions` ≤2, `period_text`(보고연도) | 연도 ≤3, `reference_ack`는 사용자 확인으로만 설정 |
| `calculate_operations_and_mrv` | 위 두 도구 인자 | 동일 |
| `compare_port_conditions` | `ship_mention`, `port_mentions`, `berth_mention`, `filters`(치수·비교·m 값), `sort`, `status_filter` | 항구 카탈로그 대조, 수치 범위, 샘플 선박 거절 |
| `ask_selected_documents` | `document_mentions` | 열람 권한 문서 제목 대조 |
| `calculate_emissions` | `fuel_t`, `factor`, `dwt`, `distance_nm` | 기존 수치 범위 |
| `voyage_time` | `start`, `end`, `start_offset_min`, `end_offset_min` | 기존 형식·범위 |
| `request_clarification` | `missing`(enum) | — |
| `decline_request` | `reason`(enum: 실시간 위치·기상·예측·자료 변경·입항 승인·무관) | — |

업무 스킬의 `report-draft`·`checklist`·`qa-evaluation`은 생성형 산출물이라 이번 범위에서 제외하고, 형식 통일 작업 때 다시 검토한다.

## 4. 범위

- 포함: 도구 등록부, 모델 도구 선택·인자 검증, 처리기의 구조화 진입점, 라우터 전환(검색 항상 실행), 후속 질문 문맥 전달, `mode` 제거, 사용한 도구 표시, 실제 모델용 평가 질문 세트, 문서 갱신.
- 제외: 실시간 도구 진행 표시(SSE), 도구 입출력 형식 통일, 서버 전용 Tool API 노출, 쓰기 도구, 운영 배포.

## 5. 단계

### 1단계 — 도구 목록과 설계 문서

- [x] 코드 기준 도구 전체 목록 정리 (3절)
- [x] ADR 0024 초안(제안) 작성: ADR 0015의 "모델은 Tool·scope를 고르지 않는다"를 대체
- [x] `specs/integrated-answer.md`에 도구 스키마·검증·오류 코드·응답의 `routing.toolCalls` 추가
- 완료 조건: 문서 검토 후 명세 상태를 `확정`으로 변경

### 2단계 — 등록부와 도구 선택

- [x] `backend/api/tool_registry.py`: 이름·설명·Pydantic 인자·실행 함수·권한·읽기 전용 여부
- [x] 등록부에서 모델 `tools` 정의 생성, `GET /api/tools` 응답 확장 여부 결정
- [x] tool calling 요청·응답 검증(도구 이름 allowlist, 인자 스키마, 호출 수 제한)
- [x] 모의 모델 테스트 먼저 작성(TDD)
- 완료 조건: 모의 모델로 정상·잘못된 도구·잘못된 인자·시간 초과 테스트 통과

### 3단계 — 처리기 구조화 진입점

- [x] `question_workflows`: 선박·기간·연도를 직접 받는 실행 함수 분리
- [x] `navigation_query`: 선박·항구·조건을 직접 받는 실행 함수 분리
- [x] `dataset_status`·`catalog_status_answer`: 범위를 직접 받도록 분리
- [x] 기존 원문 파싱 경로(legacy)도 새 함수를 호출하도록 연결
- 완료 조건: 기존 테스트 회귀 없음

### 4단계 — 라우터 전환

- [x] 검색과 도구 선택 병렬 실행, 결과 결합
- [x] 후속 질문 문맥(이전 작업·범위 요약) 전달
- [x] `mode` 제거, 모델 미설정 오류, 모델 실패 되묻기
- [x] `HAEDAP_QUESTION_ROUTER=legacy` 전환
- 완료 조건: backend 전체 테스트 통과(환경 의존 제외)

### 5단계 — 화면

- [x] 답변 방식 선택 제거
- [x] 답변 카드에 사용한 도구 칩 표시
- 완료 조건: frontend 테스트·빌드 통과

### 6단계 — 평가와 기록

- [x] 실제 모델용 평가 질문 세트(기대 도구·인자)와 실행 스크립트
- [ ] 모델 서버의 `tools` 파라미터 지원 확인 후 실제 모델 평가 실행·기록
- [ ] Docker E2E 화면 검사 실행
- [ ] 명세·ADR 검토 후 `확정`·`채택`, ADR 0015 상태 변경
- [x] `architecture.md`, `user-guide.md`, `changelog.md` 갱신
- 완료 조건: 실제 모델 평가 결과를 실측값으로 기록(미실행이면 미검증으로 기록)

## 6. 영향 받는 파일·문서

| 경로 | 변경 |
|---|---|
| `backend/api/question_router.py` | 기본 경로를 도구 선택으로 전환, legacy 분리 |
| `backend/api/tool_registry.py` | 신규 |
| `backend/api/question_workflows.py`, `navigation_query.py`, `dataset_status.py` | 구조화 진입점 |
| `backend/api/store/answers.py` | `mode` 제거, 답변 생성 경로 |
| `frontend/src/views/views.jsx`, `workspace/controller.jsx` | 답변 방식 제거, 도구 표시 |
| `docs/adr/0024-*.md`, `docs/specs/integrated-answer.md` | 신규·갱신 |

## 7. 위험과 대응

| 위험 | 대응 |
|---|---|
| 작은 모델의 도구 선택 정확도 (기존 Qwen2.5 3B 분류 실측 5건 중 3건) | 평가 세트로 측정, 도구 설명·예시 조정. 검색은 항상 실행해 문서 근거는 유지 |
| 모델이 인자를 지어냄(없는 선박·문서) | 원문 표기를 등록 목록과 대조, 불일치 시 되묻기 |
| 문서 본문을 통한 지시 주입 | 라우팅 모델 입력에 검색 본문을 넣지 않음 |
| 응답 지연 증가 | 검색과 도구 선택 병렬 실행, 소요 시간 기록 |
| 모델 없는 환경에서 사용 불가 | 명확한 오류 안내, legacy 환경변수로 임시 전환 가능 |

## 8. 후속 작업

- 도구 형식 통일(Convention): 이름 규칙, Pydantic 입력 스키마, 공통 응답(`status`·`result`·`evidence`·`warnings`·`unavailable_reason`), 오류 코드.
- 실시간 도구 진행 표시(SSE).
- 생성형 스킬(`report-draft`, `checklist`)의 도구화 검토.

## 9. 진행 기록

- 2026-11-12: 워크트리 생성, backend 기준선 1,068 passed / 203 skipped / 4 failed(torch 미설치로 `test_document_save.py` 4건). 도구 목록 정리.
- 2026-11-12: 3차 평가(추론 끔) 10/25, 중간값 0.45초. 대부분 도구 없이 글로 답함 — 지시문의 "문서라고만 답하라" 출구로 쏠린 것으로 판단. `answer_from_documents` 제어 도구를 추가해 항상 도구 하나를 호출하게 하고, 글 응답·JSON 형태 호출을 평가 출력에 표시.
- 2026-11-12: 2차 평가(qwen3.6:35b, Ollama) 17/25. 남은 실패는 추론이 1024토큰을 소진(6건), 빈 선택 인자를 문자열 "None"으로 출력(1건), 선택 문서 미선택(1건). `HAEDAP_PLANNER_REASONING_EFFORT=none`(opt-in) 추가, "None" 문자열은 생략으로 처리, 선택 문서 도구 설명 보강.
- 2026-11-12: 서버 Qwen 1차 평가 11/25 일치, 14건 `MODEL_INCOMPLETE_OUTPUT`. 도구 선택 출력 한도를 400→1024로 늘리고(`HAEDAP_PLANNER_MAX_TOKENS`) 실패 시 종료 사유를 평가 결과에 표시.
- 2026-11-12: 명세 초안, 등록부·도구 선택·검증·처리기 구조화 진입점·라우터 전환·화면 변경·평가 스크립트 구현. 결정 보완: 질문당 데이터 도구 1개(운항+MRV는 결합 도구), 모델 경로에서 `mode`를 서버가 `llm`으로 고정, e2e 스택은 legacy 경로. 검증 수치는 [변경 이력](../changelog.md) 참고. 남은 일: 실제 모델 평가, Docker E2E, 명세·ADR 검토 후 확정.
