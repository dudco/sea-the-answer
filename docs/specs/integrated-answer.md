# 통합 답변 (`POST /api/ask`)

- 상태: 구현됨 (1.3.1)
- 최종 확인: 2026-11-10 (대화형 조건·AIS 현황·질문 표현 보완, 실제 로컬 Qwen 연결·제한된 생성 확인; 전반적 생성 품질은 미달, 검증 기록 참조)
- 관련: [`api.md`](api.md), [`../architecture.md`](../architecture.md#23-통합-질문-post-apiask), [`../plans/2026-10-08-team-module-integration.md`](../plans/2026-10-08-team-module-integration.md)

## 1. 목적

### LLM 도구 선택 (2026-11-12 초안)

[ADR 0024](../adr/0024-llm-tool-selection.md)·[계획](../plans/2026-11-12-llm-tool-selection.md)의 구현 계약이다. 확정 전까지 아래 다른 절과 충돌하면 이 절이 우선하는 초안이며, 구현 후 다른 절을 함께 고친다.

**흐름.** `task=auto` 질문은 다음 순서로 처리한다.

1. 입력 검증. `workflowInput`(되묻기 카드의 구조화 응답)은 기존 업무 경로로 처리한다.
2. 서버 환경변수 `HAEDAP_QUESTION_ROUTER=legacy`이면 기존 규칙 경로를 그대로 쓴다. 기본값은 `model`.
3. 모델이 설정되지 않았으면 `503 MODEL_NOT_CONFIGURED`를 반환한다.
4. 문서 검색(`DocumentStore.search`, 열람 권한 필터 선적용)과 도구 선택 모델 호출을 병렬로 실행한다. 도구 선택 입력은 질문, 오늘 날짜, 소유권을 확인한 이전 답변의 요약(작업 종류·선박 이름·기간·되묻기 항목), 사용자가 열람할 수 있는 문서 제목(최대 50개, 각 100자)뿐이며 검색 본문은 넣지 않는다. 모델이 tool_calls 대신 글로 낸 호출은 `<tool_call>` JSON, `{"name"|"function", "arguments"}` JSON, `도구이름(키=리터럴)` 형식만 읽으며 리터럴 외 표현은 거절한다. 도구 이름 없이 인자만 낸 응답은 추측하지 않고 문서 답변으로 처리한다.
5. 모델은 항상 도구를 하나 호출하며, 문서만으로 답할 질문은 `answer_from_documents`를 고른다. 데이터 도구 호출이 0개이면 검색 근거로 문서 답변을 생성한다(기존 인용 검증). 1개이면 서버가 인자를 검증해 해당 실행기를 호출하고, 검색 근거를 `relatedEvidence`로 함께 반환한다. 2개 이상이면 되묻기로 처리한다(이번 범위는 질문당 데이터 도구 1개, 운항+MRV는 결합 도구 1개로 처리).
6. 모델 호출 실패·시간 초과·등록되지 않은 도구·인자 검증 실패는 `needs_input` 되묻기(`warnings: ["MODEL_ROUTING_UNAVAILABLE"]`)로 응답한다. 규칙 경로로 자동 대체하지 않는다.

**도구.** 정의는 `backend/api/tool_registry.py` 한곳에서 만들며 `GET /api/tools`의 `assistantTools`로도 제공한다. 모든 인자 객체는 추가 필드를 거절한다.

| 도구 | 인자 | 서버 검증·변환 | 실행기 |
|---|---|---|---|
| `get_dataset_status` | `datasets`: `ais`·`mrv`·`dwt`·`noon`·`operations`·`documents`·`ports` 1~7개(중복 불가), `ship_mentions` ≤1, `period_text` ≤100자 | 자료 종류 allowlist, 선박 대조, 기간 해석 | `dataset_status` |
| `get_ais_catalog_status` | `ship_mentions` ≤1 | 선박 대조 | `navigation_query.catalog_status_answer` |
| `summarize_operations` | `ship_mentions` ≤2, `period_text` ≤100자, `display`: `text`·`table`·`chart` | 기간 ≤2개·각 366일 이하, 표·차트는 1척·1기간 | `question_workflows` |
| `calculate_mrv_reference` | `ship_mentions` ≤2, `period_text`(보고연도), `accept_reference`(bool) | 연도 ≤3, `accept_reference`는 직전 소유 답변이 참고값 동의를 물었을 때만 반영 | `question_workflows` |
| `calculate_operations_and_mrv` | 위 두 도구의 인자 | 동일, 총 조회 ≤4회 | `question_workflows` |
| `compare_port_conditions` | `ship_mention`, `port_mentions` ≤5, `berth_mention`, `filters` ≤3(`dimension`: `length`·`beam`·`draught`, `op`: `>=`·`<=`·`>`·`<`·`=`, `value_m` 0 초과 ≤1000), `sort`(`dimension`, `direction`: `asc`·`desc`), `status_filter` | 항구 카탈로그 이름 대조, 실제 MRV 연결 선박만 | `navigation_query` |
| `ask_selected_documents` | `document_mentions` ≤5 | 열람 가능한 문서 제목 대조 | `question_workflows` |
| `calculate_emissions` | `fuel_t`, `factor`, `dwt`, `distance_nm` | 기존 수치 범위 | `ToolStore.calculate_emissions` |
| `voyage_time` | `start`, `end`(UTC ISO), `start_offset_min`, `end_offset_min` | 기존 형식·범위 | `ToolStore.voyage_time` |
| `answer_from_documents` | 없음 | 데이터 도구 0개로 처리(검색은 이미 실행) | 문서 답변 생성 |
| `request_clarification` | `missing`: `task`·`ships`·`periods`·`years`·`documents`·`ports` | — | 되묻기 저장 |
| `decline_request` | `reason`: `realtime_position`·`weather`·`forecast`·`data_change`·`entry_approval`·`off_topic` | — | 지원 불가 안내 저장 |

**모델이 낸 값의 처리.** 선박·문서·항구 표기는 질문 원문 또는 이전 답변 요약에 실제로 나온 문자열이어야 하며, 서버가 등록 목록·열람 권한·카탈로그와 대조해 식별자로 바꾼다. 일치하지 않으면 후보를 보여 주는 되묻기로 응답한다. 기간 표현은 `question_intent.date_slots`가 해석하며 실패하면 기간 되묻기로 응답한다. 모델은 SQL·식별자·수치 결과·답변 문장을 만들지 않는다.

**응답 추가 필드.** `routing`은 `{method: "model_tools", toolCalls: [{name, arguments, status, durationMs}], searchMs, planMs}`이다. `arguments`는 서버가 검증·변환한 값만 담고 모델 원시 응답은 저장하지 않는다. `relatedEvidence[]`는 데이터 도구 응답에 붙는 검색 근거이며 `evidence[]`와 같은 형식·권한 검사를 따른다.

**요청 변경.** `mode`는 더 이상 쓰지 않는다. 보내도 무시하며 답변 생성은 항상 모델을 사용한다. 생성 실패 시 검색 문단 표시(`MODEL_FAILED_EXTRACTIVE_FALLBACK`)는 유지한다.

### 자료 현황과 의미 기반 경로 보완 (2026-11-11 확정)

자동 질문은 MRV·AIS·DWT·Synthetic Noon·일별 운항·열람 가능 문서의 등록 여부/건수/출처 요청을 조회·계산/문서 설명과 구분한다. 현황은 현재 서버 자료에서 읽고, 빈 자료와 읽기 실패를 구분한다. 전체 등록 건수와 계산 적격 건수는 별개다. 선박·연도 조건을 적용할 수 없으면 전체 수치를 해당 조건의 결과로 대신 제공하지 않는다. 문서 현황은 현재 계정의 열람 범위만 센다.

기존 규칙과 대화 조건을 우선 재사용한다. 그 경로가 처리하지 못한 AI 모드 질문에는 폐쇄형 의미 분류를 사용할 수 있다. 모델은 문서·선택 문서·운항 요약·MRV 참고 계산·결합·항만 비교·자료별 현황·되묻기·지원 밖 중 **action 하나만** 출력한다(최대 32토큰·12초·질문 4,096바이트). 서버가 이를 내부 route/dataset으로 바꾼다. 모델의 자기 평가 점수를 신뢰도 수치로 사용하지 않는다. 식별자·날짜·SQL·계산값을 모델에서 받지 않으며 기존 실행 검증을 유지한다. 분류 실패/모호함과 지원 밖 요청은 안내하고 명시한 문서 전용 모드는 유지한다. 일반 LLM 생성 실패를 도구 현황 실패나 데이터 부재로 해석하지 않는다.

자료 현황 응답은 기존 answer 필드를 유지하고 `dataStatus`에 `datasets`(자료별 상태·건수·기간·출처·주의사항), `scope`, `assessed_at`을 추가한다. `routing`은 규칙/모델/대화 경로와 제한된 사유만 기록하며 내부 URL·키·원시 오류는 반환하지 않는다. 기존 AIS `navigation.kind=catalog-status` 계약도 유지한다.

### 필요한 순간에만 후보 제시 (2026-11-10 구현됨)

통합 질문에는 선박·기간을 미리 선택하는 양식이나 업무 조건 보완 양식을 표시하지 않는다. 현재 마지막 답변의 `workflow.clarification.field`에 해당하는 선박/문서 후보 또는 참고값 확인 버튼만 표시하며, 날짜·연도는 질문창에 답한다. 이전 답변의 후보는 실행할 수 없다. 후보 클릭은 기존 `workflowInput`의 ID와 현재 답변 ID를 사용하며 서버가 소유자·대화·권한·버전을 다시 검증한다. 여러 대상을 동시에 지정하려면 이름/제목을 문장으로 답한다. 관리자 자료 등록 및 다른 화면의 업무 양식은 이 변경 범위가 아니다.

`workflow.options.ships`는 `id/name/imo/type/sample/version`, `documents`는 `id/title/version/reference`를 제공한다. 같은 이름/제목으로 모호해진 경우 일치 후보를 우선하고, 선박 100개·문서 50개 한도와 열람 범위를 유지한다. 화면은 처음 8개를 제시하고 더 보기로 다음 후보를 펼칠 수 있다. 현재 확인하지 않은 항목과 이미 충족한 조건의 전체 목록을 상시 제시하지 않는다. 참고값 확인을 거절하면 `clarification=null`로 추가 선택을 닫고 이후의 단순한 “네”는 동의로 처리하지 않는다.

자동 질문의 HTTP context는 현재 대화의 검증된 답변 범위에서만 이어받는다. 운항 관리 화면의 선택값을 보이지 않는 기본값으로 사용하지 않는다. 운영 기록 표/차트도 질문의 선박·기간을 기존 조건 해석기로 확인하며, 부족하면 같은 되묻기를 사용한다. `workflow.scope.presentation_question`(기본 빈 문자열, 최대 2,000자)은 실제 사용자가 요청한 운항 표/차트 문장을 조건 보완 동안 보존한다. 한 선박·한 기간만 투영하고 기존 `presentation`/`operations` 계약과 한도를 재사용한다. 문서 표·공식 CII 등급 차트는 기존 경로와 제한을 유지한다.

### 화면의 실제 AI 호출 선택 (2026-11-10 구현됨)

로그인한 사용자의 health에서 `llmConfigured=true`이면 통합 질문의 기본 요청 모드는 `llm`이다. `답변 방식`에서 명시적으로 원문 발췌를 고르면 현재 계정 세션의 재연결에도 그 선택을 보존한다. 미설정 시에는 원문 발췌만 사용하며 계정 변경/로그아웃 뒤 선택을 초기화한다. 설정 유무와 실제 생성 성공은 구분하고, 최종 `generation`과 fallback 경고 표시를 유지한다. 자료 현황·계산 도구는 기존 고정 경로를 따르며 AI 기본 선택을 생성 성공으로 표시하지 않는다.

### 질문창 중심 조건 보완 (2026-11-10 구현됨)

추가 표현 계약: `AIS 있어?`·`실시간 AIS 데이터야?`·`AIS 정보 최신이야?`도 수집본 현황으로 확인한다. 명시 기간과 지표의 명사구(`2025년 1월 연료 사용량`, `올해 항해거리는?`)는 조건 확인/조회 경로를 사용한다. 계산식·배출계수 설명은 문서 경로이며 원인·예측 요청을 합계로 대신 답하지 않는다. 모호한 미래 표현은 과거 UI 범위로 대체하지 않는다. `그 문서에서…`는 같은 대화의 검증한 선택 문서 ID만 이어받고 새 질문으로 다시 검색한다. 부모 권한이 유효하지 않으면 문서를 다시 지정해야 한다.

자동 질문에서 `context.ship/from/to`를 생략하면 해당 조건은 미지정이다. 웹은 초기 화면이 자동 선택한 첫 선박·기본 날짜를 보내지 않는다. 현재 대화에서 검증한 선박/기간만 보낸다. 운항 관리 화면의 선택값은 질문의 숨은 조건으로 사용하지 않는다. 기존 API 호출자가 명시한 context는 호환 유지한다.

`AIS 데이터 있어?`·`AIS 자료 등록됐어?`·`AIS 출처/수집 현황`은 일반 문서 검색보다 먼저 실제 참조 catalog를 확인한다. 응답 `navigation.kind=catalog-status`, `navigation.catalog`은 기존 catalog summary 계약을 재사용하며 건수·고유 선박·출처·수집일·노후화 기준을 반환한다. 빈 관측 목록과 연결/형식 확인 불가는 별도 상태다. 특정 선박 질문은 현재 등록된 정확한 IMO의 포함 여부만 확인하며, 다른 선박으로 대신 확인하거나 실시간 위치/입항 허가로 표현하지 않는다. 정의·절차 질문은 원래 문서 경로를 유지한다. 이 경로는 AIS snapshot 현황이며 MRV DB의 적재 여부를 대변하지 않는다.

`workflow.clarification`은 미충족 조건 중 다음 하나의 `field`, `question`을 제공한다. 선박 → MRV 연도 → 참고값 확인 → 일별 기간 → 문서 순서로 묻는다. 사용자는 질문창에서 등록 선박명/IMO, 날짜/상대 기간, 열람 가능한 문서의 고유한 제목, 명시적인 참고값 요청으로 답할 수 있다. `네` 같은 짧은 동의는 현재 묻는 항목이 참고값 확인일 때만 유효하다. 부정 표현은 동의로 처리하지 않는다. 원래 선택 문서 질문을 보존하며 제목이 중복되면 구분을 요청한다. 화면의 조건 보완 양식은 제거하고 현재 후보 버튼의 ID 답변에 기존 `workflowInput` 계약을 사용한다.

완료 후에도 `2월은?`, `별빛호는?`처럼 등록 명칭·날짜와 연결 어미로만 이루어진 짧은 후속은 현재 부모 범위로 재조회한다. 다른 주제·정의·절차 질문은 원래 검색 경로로 보낸다. `conversationId`가 있으면 부모도 같은 대화에 속해야 한다. 항구 질문에서 선박이 부족한 경우에도 선박명만 답해 원래 항구·조건을 이어갈 수 있다. 선박 등록/실제 매핑/자료 갱신은 질문 경로에서 수행하지 않는다.

### 자연어 업무 실행 확장 (2026-11-06 구현됨)

자동 질문은 기존 항구 경로 다음에 폐쇄형 업무 계획을 검사한다. 운항 요약·MRV 참고 계산·두 종류의 결합·명시 선택 문서 답변을 기존 함수로 실행하며 범용 SQL/쓰기 도구는 제공하지 않는다. 명시 문장 조건이 UI 선택보다 우선한다. 모델은 서버가 허용한 action 하나만 제안한다. 선박명/IMO·연도·기간은 서버가 원문과 등록 자료로 해석하며 모델 출력으로 채우지 않는다. 기본 발췌 모드는 규칙만 사용하며 LLM 모드에서만 설정된 모델에 제한된 JSON 선택을 요청한다. 실패/상충/unknown/형식 오류는 규칙·되묻기로 처리한다. 선택 모델 `HAEDAP_PLANNER_MODEL`은 비어 있으면 기존 `OPENAI_MODEL`을 사용한다. 입력 4,096 UTF-8 byte·출력 64 token·18초 제한이며 원문 문서나 DB 행을 이 작업 선택 호출에 보내지 않는다.

`workflow` 응답은 `version`, 검증한 `scope`, `missing`, 선택 가능한 대상, `routing`, 실행 결과 행·비교를 보존한다. 선박 최대 2척·연도 3개·일별 기간 2개(각 366일 차이 이하)·총 도구 호출 4회다. 계산 불가/자료 없음 행을 유지하며 모델은 계산·CII/등급·선박 식별자·승인·인용을 생성하지 않는다. 자료 유형/단위·누락일·가상 여부·참고 한계를 표시한다. 공식 CII 요청은 참고값 동의/범위 안내를 거친다.

`context.previousQueryId`는 현재 표시한 소유자 workflow에만 연결한다. 소유자·선박 버전/IMO·MRV 매핑·문서 권한을 다시 확인하고 이전 숫자는 재사용하지 않는다. 독립 질문은 이전 조건을 이어받지 않는다. 짧은 연도/기간/선박 후속과 부족 입력 답변만 지정된 계획에 병합한다. 선택 문서는 `workflowInput.document_ids`, 부족한 선박/기간/연도는 동일 필드의 명시 입력으로 보완할 수 있으며 부모 응답이 없거나 타인의 응답이면 거부한다. 기존 문서 전용/절차·항구 질문과 기존 저장 이력은 호환 유지한다.

`workflowInput`은 `{ships?: string[], years?: int[], periods?: [{start,end}], document_ids?: string[], reference_ack?: boolean}`이며 기타 키·중복·잘못된 날짜를 거부한다. 날짜는 ISO 또는 명시 한국어 일/월/연도, 최근 N일·지난달/이번 달·지난주/이번 주·오늘/어제로 해석한다. 상대 날짜 기준은 KST이며 이번 달/주는 오늘까지다. 연도 없는 월은 검증한 부모의 연도가 하나일 때만 계승한다. 지원하지 않는 항차별/연료별/기관별 조건은 전체 합계로 대신 실행하지 않는다.

`workflow.scope`는 action·선박 snapshot(id/name/version/IMO)·years·periods·document_ids·document_question·presentation_question·reference_ack·mappings를 보존한다. 문서 선택 되묻기에서는 원래 질문을 유지하며 후보 선택의 표시 문장을 원래 문서 질문 대신 검색하지 않는다. 상태는 `needs_input`·`completed`·`partial`·`insufficient_evidence`, `routing`은 규칙/모델 시도·대체 여부다. `results[]`는 kind/label/ship/year 또는 period/status/result이며 원래 도구의 출처·단위·차단 사유를 유지한다. `comparisons[]`는 같은 종류의 첫 결과 대비 차이·변화율이다. 0 기준 변화율, 자료 없음, 가상/실제 혼합은 비교 불가이며 인과·규정 준수 판단이 아니다. 버전/매핑 변경은 409, 권한 오류는 403, 자료원 장애는 503을 반환한다. 전체 상태가 완료여도 각 결과의 누락일·자료 한계를 확인해야 한다.

통합 질문 화면이 기대는 입력·출력 계약입니다. 팀의 의도 분류·RAG·Tool Calling·LLM 모듈로 내부 구현을 교체하더라도 **이 형식을 지키면 화면을 그대로 재사용**할 수 있습니다.

## 2. 요청

표·차트 요청의 `outputFormat`, 응답 `presentation`·`presentationNotice`·`generationStats`·`timings`, 운항 기록 미리보기는 [표현·입력량 추가 계약](answer-presentation.md)을 따른다. 기존 필드와 인용·권한 경계는 유지한다.

```json
{
  "question": "선택 선박의 운항 현황과 관련 규정을 확인해줘",
  "task": "integrated",
  "language": "auto",
  "mode": "extractive",
  "filter": "all",
  "context": {"ship": "등록된 선박 ID", "from": "2026-09-01", "to": "2026-09-30"},
  "criterion": null
}
```

| 필드 | 값 | 설명 |
|---|---|---|
| `question` | 문자열 ≤2,000자 | 필수 |
| `task` | `auto` · `documents` · `operations` · `integrated` · `report` | `auto`는 단어 규칙으로 운항 분석 필요 여부를 판단 |
| `language` | `auto` · `ko` · `en` | `auto`는 한글 포함 여부로 결정 |
| `mode` | `extractive` · `llm` | 2026-11-12 초안부터 자동 질문에서 무시(위 LLM 도구 선택 절). 생성 실패 시 발췌 표시는 유지 |
| `filter` | `all` · `imo` · `manual` | `imo` = `official-summary`, `manual` = 그 외 |
| `context` | `{ship, from, to, previousQueryId?}` | 기존 경로의 운항 범위. auto workflow에서는 검증한 자연어 조건을 우선하고 현재 소유자 답변에만 후속 연결 |
| `workflowInput` | 위 보완 계약 | auto workflow 되묻기용. 현재 부모 답변 필요 |
| `criterion` | 아래 4절 또는 `null` | 사용자가 확인한 단일 기준 |
| `calculation` | `calculate_emissions` 입력 (선택) | 지정 시 `toolRuns`에 결과 추가 |

## 3. 응답

| 필드 | 설명 |
|---|---|
| `id` | `queries` 행 ID (이력 재열람) |
| `question`, `language` | |
| `task` | `documents` · `integrated` · `navigation` · `workflow` |
| `generation` | `extractive` · `llm` · `tool` · `workflow` |
| `status` | 기존 `evidence_found` · `insufficient_evidence` · `data_found`와 위 확장 상태 |
| `workflow` | 자연어 업무 실행 시에만 위 검증 범위·되묻기·결과·비교 계약 |
| `notice`, `warnings[]` | 안내 문구. 경고 코드: `MODEL_NOT_CONFIGURED`, `MODEL_FAILED_EXTRACTIVE_FALLBACK` |
| `statements[]` | `{text, chunkId, quote}` — 각 문장은 근거 청크와 원문 인용을 가져야 함 |
| `evidence[]` | `{id, document_id, title, version, reference, heading, text, page, meta, kind, url, …}` |
| `toolRuns[]` | 계산 도구 결과 (`id, name, version, …`) |
| `operations` | 운항 분석 시 `{ship, from, to, rows, count, fuel, emission, distance, speed, intensity, sample, cii}` |
| `operationNotice` | 운항 분석이 필요하지만 선박을 선택하지 않았을 때 |
| `compliance` | `{status:"met"|"unmet"|"unknown", label, actual, limit, rule, reason}` |
| `reportSuggested` | 보고서 작성 권유 여부 |

### 인용 규칙 (LLM 모드)

- 모델은 OpenAI 호환 Chat Completions로 호출합니다. JSON 출력 강제는 공급자 지원에 따라 선택하며 앱은 항상 `insufficient`와 `statements[{text, chunkId, quote}]`(최대 5개)의 타입·원문 인용을 검증합니다. 설정·호출 계약은 [`llm-provider.md`](llm-provider.md)를 따릅니다.
- 각 `quote`는 8자 이상이며 해당 `chunkId` 원문에 **그대로 포함**되어야 합니다. 하나라도 어기면 전체를 폐기하고 발췌 모드로 되돌립니다.
- 질문과 근거는 데이터로만 취급하며, 근거로 답할 수 없으면 `insufficient:true`.

### CII 표시 계약

```json
{"status": "available", "value": 0, "unit": "", "rating": "A", "year": 2026, "method": ""}
{"status": "unavailable", "reason": "산출에 필요한 조건 설명"}
```

현재 서버는 항상 `unavailable`을 반환합니다. **값이나 등급을 임의로 만들어 넣지 마세요.** 입력값·산식·선종·연도·검증된 기준을 전문 모듈에서 확보한 경우에만 `available`을 반환합니다.

## 4. 기준 비교 (`criterion`)

```json
{"documentId": "…", "chunkId": "…", "quote": "원문 구절", "metric": "fuel", "operator": "lte", "limit": 100, "confirmed": true}
```

검증 순서: `confirmed === true` → 현재 열람 가능한 적용 중 문서 → 청크가 그 문서에 속하고 `quote`(8자 이상)가 원문에 포함 → `metric` ∈ `fuel|emission|intensity|speed` → `operator` ∈ `lte|gte` → `limit` 0~1e12.
결과는 사용자가 입력한 **단일 기준의 수치 비교**이며 전체 규정 준수나 공식 CII 판정이 아닙니다. 데이터가 없으면 `unknown`.

## 5. 교체 시 지켜야 할 것

- 검색 입력 단계에서 `allowed_document_ids(user)`로 열람 범위를 적용할 것
- `statements`의 모든 문장이 `evidence`의 청크를 인용할 것
- `queries`·`query_owner`에 기록해 이력 재열람이 되게 할 것
- 근거 없는 CII 값·규정 판정을 만들지 말 것

## 6. 수용 기준

`backend/tests/`의 회귀 테스트로 확인되는 항목은 체크했습니다.

- [x] 제한 문서 검색·BM25 순위·페이지와 원문 인용의 실 DB 회귀 검증 (`test_rag_postgres.py`, 2026-10-14)
- [x] 설정된 LLM의 인용을 검증하고 실패하면 발췌로 되돌린다 — 모의 HTTP와 실제 답변 오케스트레이션 기준 (`test_llm_provider.py`)
- [x] 근거가 없으면 모델을 호출하지 않고 답변 문장을 만들지 않는다 (`test_llm_provider.py`)
- [ ] 기준 비교의 met / unmet / unknown과 잘못된 근거 거부 전용 회귀 검증 — 이전 Node 테스트는 #8에서 제거됨; 이번 전환은 기준 비교를 변경하지 않음
- [ ] 운항 분석 응답의 CII가 항상 `unavailable`인지 전용 테스트 추가 필요
- [ ] 실제 외부 LLM 호출 검증

## 대화 저장·조회·삭제 (2026-11-09, 구현됨)

- `POST /api/ask`에 선택 `conversationId`를 추가한다. 미지정 시 기존과 같이 새 질문을 저장하며 그 응답의 `id`가 새 대화 ID다. 지정 시 본인이 소유한 대화의 첫 질문을 확인하고 행 잠금을 획득한 뒤 같은 대화에 저장한다. 후속 답변에는 `conversationId`가 포함된다.
- `GET /api/conversations`: 본인 소유 최근 100개 대화의 `{history: [{id, question, at, count}]}`. `question`은 첫 질문, `at`은 마지막 질문 시각. 질문 수에는 100개 제한을 적용하지 않는다.
- `GET /api/conversations/{id}`: `{id, turns: [{id, question, at, answer, unavailable}]}`. 생성 시각과 ID 순으로 모든 질문을 반환하고 각 답변의 근거 열람 권한을 재검사한다. 권한을 잃은 답변만 `answer:null`로 숨긴다.
- `POST /api/conversations/delete` 입력 `{id}`: 본인 대화의 모든 `queries`와 `query_owner` 행을 삭제한다. `{deleted:id, count}` 반환. 삭제 후 재조회·추가는 404. POST의 기존 로그인·CSRF·identity 검증을 그대로 적용한다.
- 타인의 대화 ID와 없는 ID는 모두 404로 처리한다. 삭제와 후속 저장은 대화 첫 행 잠금으로 직렬화한다. 이미 작성한 보고서나 등록 문서는 삭제하지 않는다. 삭제 감사 로그와 과거 백업은 유지한다.
- 기존 `/api/history` 계약은 호환 유지한다. 대화 식별자가 없는 기존 질문/스킬 실행은 각 1개 질문 대화로 표시한다.
- 새 대화/로고 클릭은 화면을 비우고 이후 첫 질문부터 새 대화로 저장한다. 화면 전환으로 진행 중 응답을 떠나더라도 서버 완료 기록은 이력에 남을 수 있다.
- UI 기본값은 `task:auto`, `language:auto`, `mode:extractive`를 유지한다. 화면 언어 `ko/en`은 API 질문 필드와 독립적이다. 전문 LLM 다중 대화 메모리를 추가하지 않고 기존 제한적 후속 질문 처리만 유지한다.
