# 통합 답변 (`POST /api/ask`)

- 상태: 구현됨 (1.3.1)
- 최종 확인: 2026-11-06 (기존 답변 경로 유지, `question_intent`/`question_workflows` 자동 실행 추가·실제 API/DB/선택적 Qwen 검증)
- 관련: [`api.md`](api.md), [`../architecture.md`](../architecture.md#23-통합-질문-post-apiask), [`../plans/2026-10-08-team-module-integration.md`](../plans/2026-10-08-team-module-integration.md)

## 1. 목적

### 자연어 업무 실행 확장 (2026-11-06 구현됨)

자동 질문은 기존 항구 경로 다음에 폐쇄형 업무 계획을 검사한다. 운항 요약·MRV 참고 계산·두 종류의 결합·명시 선택 문서 답변을 기존 함수로 실행하며 범용 SQL/쓰기 도구는 제공하지 않는다. 명시 문장 조건이 UI 선택보다 우선한다. 모델은 서버가 허용한 action 하나만 제안한다. 선박명/IMO·연도·기간은 서버가 원문과 등록 자료로 해석하며 모델 출력으로 채우지 않는다. 기본 발췌 모드는 규칙만 사용하며 LLM 모드에서만 설정된 모델에 제한된 JSON 선택을 요청한다. 실패/상충/unknown/형식 오류는 규칙·되묻기로 처리한다. 선택 모델 `HAEDAP_PLANNER_MODEL`은 비어 있으면 기존 `OPENAI_MODEL`을 사용한다. 입력 4,096 UTF-8 byte·출력 64 token·18초 제한이며 원문 문서나 DB 행을 이 작업 선택 호출에 보내지 않는다.

`workflow` 응답은 `version`, 검증한 `scope`, `missing`, 선택 가능한 대상, `routing`, 실행 결과 행·비교를 보존한다. 선박 최대 2척·연도 3개·일별 기간 2개(각 366일 차이 이하)·총 도구 호출 4회다. 계산 불가/자료 없음 행을 유지하며 모델은 계산·CII/등급·선박 식별자·승인·인용을 생성하지 않는다. 자료 유형/단위·누락일·가상 여부·참고 한계를 표시한다. 공식 CII 요청은 참고값 동의/범위 안내를 거친다.

`context.previousQueryId`는 현재 표시한 소유자 workflow에만 연결한다. 소유자·선박 버전/IMO·MRV 매핑·문서 권한을 다시 확인하고 이전 숫자는 재사용하지 않는다. 독립 질문은 이전 조건을 이어받지 않는다. 짧은 연도/기간/선박 후속과 부족 입력 답변만 지정된 계획에 병합한다. 선택 문서는 `workflowInput.document_ids`, 부족한 선박/기간/연도는 동일 필드의 명시 입력으로 보완할 수 있으며 부모 응답이 없거나 타인의 응답이면 거부한다. 기존 문서 전용/절차·항구 질문과 기존 저장 이력은 호환 유지한다.

`workflowInput`은 `{ships?: string[], years?: int[], periods?: [{start,end}], document_ids?: string[], reference_ack?: boolean}`이며 기타 키·중복·잘못된 날짜를 거부한다. 날짜는 ISO 또는 명시 한국어 일/월/연도, 최근 N일·지난달/이번 달·지난주/이번 주·오늘/어제로 해석한다. 상대 날짜 기준은 KST이며 이번 달/주는 오늘까지다. 연도 없는 월은 검증한 부모의 연도가 하나일 때만 계승한다. 지원하지 않는 항차별/연료별/기관별 조건은 전체 합계로 대신 실행하지 않는다.

`workflow.scope`는 action·선박 snapshot(id/name/version/IMO)·years·periods·document_ids·document_question·reference_ack·mappings를 보존한다. 문서 선택 되묻기에서는 원래 질문을 유지하며 보완 양식의 안내 문장을 검색어로 사용하지 않는다. 상태는 `needs_input`·`completed`·`partial`·`insufficient_evidence`, `routing`은 규칙/모델 시도·대체 여부다. `results[]`는 kind/label/ship/year 또는 period/status/result이며 원래 도구의 출처·단위·차단 사유를 유지한다. `comparisons[]`는 같은 종류의 첫 결과 대비 차이·변화율이다. 0 기준 변화율, 자료 없음, 가상/실제 혼합은 비교 불가이며 인과·규정 준수 판단이 아니다. 버전/매핑 변경은 409, 권한 오류는 403, 자료원 장애는 503을 반환한다. 전체 상태가 완료여도 각 결과의 누락일·자료 한계를 확인해야 한다.

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
| `mode` | `extractive` · `llm` | `llm`은 모델이 설정된 경우에만 동작, 실패 시 발췌로 되돌림 |
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
