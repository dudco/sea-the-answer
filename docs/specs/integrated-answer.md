# 통합 답변 (`POST /api/ask`)

- 상태: 구현됨 (1.3.1)
- 최종 확인: 2026-10-08 (`backend/analysis.mjs`, `backend/rag.mjs` 대조)
- 관련: [`api.md`](api.md), [`../architecture.md`](../architecture.md#23-통합-질문-post-apiask), [`../plans/2026-10-08-team-module-integration.md`](../plans/2026-10-08-team-module-integration.md)

## 1. 목적

통합 질문 화면이 기대는 입력·출력 계약입니다. 팀의 의도 분류·RAG·Tool Calling·LLM 모듈로 내부 구현을 교체하더라도 **이 형식을 지키면 화면을 그대로 재사용**할 수 있습니다.

## 2. 요청

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
| `context` | `{ship, from, to}` | 운항 분석 대상. 질문에서 자동 추출하지 않음 |
| `criterion` | 아래 4절 또는 `null` | 사용자가 확인한 단일 기준 |
| `calculation` | `calculate_emissions` 입력 (선택) | 지정 시 `toolRuns`에 결과 추가 |

## 3. 응답

| 필드 | 설명 |
|---|---|
| `id` | `queries` 행 ID (이력 재열람) |
| `question`, `language` | |
| `task` | `documents` 또는 `integrated` |
| `generation` | `extractive` · `llm` |
| `status` | `evidence_found` · `insufficient_evidence` · `data_found` |
| `notice`, `warnings[]` | 안내 문구. 경고 코드: `MODEL_NOT_CONFIGURED`, `MODEL_FAILED_EXTRACTIVE_FALLBACK` |
| `statements[]` | `{text, chunkId, quote}` — 각 문장은 근거 청크와 원문 인용을 가져야 함 |
| `evidence[]` | `{id, document_id, title, version, reference, heading, text, page, meta, kind, url, …}` |
| `toolRuns[]` | 계산 도구 결과 (`id, name, version, …`) |
| `operations` | 운항 분석 시 `{ship, from, to, rows, count, fuel, emission, distance, speed, intensity, sample, cii}` |
| `operationNotice` | 운항 분석이 필요하지만 선박을 선택하지 않았을 때 |
| `compliance` | `{status:"met"|"unmet"|"unknown", label, actual, limit, rule, reason}` |
| `reportSuggested` | 보고서 작성 권유 여부 |

### 인용 규칙 (LLM 모드)

- 모델 출력은 JSON schema(`insufficient`, `statements[{text, chunkId, quote}]`, 최대 5개)로 강제합니다.
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

- 검색 입력 단계에서 `allowedDocs(user)`로 열람 범위를 적용할 것
- `statements`의 모든 문장이 `evidence`의 청크를 인용할 것
- `queries`·`query_owner`에 기록해 이력 재열람이 되게 할 것
- 근거 없는 CII 값·규정 판정을 만들지 말 것

## 6. 수용 기준

`backend/tests/`의 회귀 테스트로 확인되는 항목은 체크했습니다.

- [x] 제한 문서는 검색 단계에서 제외된다 (`workspace.test.mjs` — document access enforcement before search)
- [x] 설정된 LLM의 인용을 검증하고, 실패하면 명시적으로 발췌로 되돌린다 — 모의 응답 기준 (`backend.test.mjs`)
- [x] 근거가 없으면 답변 문장을 만들지 않는다 (`backend.test.mjs`)
- [x] 기준 비교가 met / unmet / unknown과 잘못된 근거 거부를 처리한다 (`workspace.test.mjs`)
- [ ] 운항 분석 응답의 CII가 항상 `unavailable`인지 전용 테스트 추가 필요
- [ ] 실제 외부 LLM 호출 검증
