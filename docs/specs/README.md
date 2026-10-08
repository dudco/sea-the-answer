# specs — 구현 계약

다른 모듈·팀원·에이전트가 **기대고 구현하는 동작의 계약**을 적습니다. "무엇을 받고 무엇을 돌려주며 어떤 제약을 지켜야 하는가"가 핵심이고, 일정·담당은 [`../plans/`](../plans/)에 적습니다.

## 언제 쓰나

- 새 API 경로, Tool 입력·출력, 응답 JSON 형식을 만들거나 바꿀 때
- 팀 모듈(RAG, LLM, CII 계산 등)을 붙이기 전에 경계를 합의할 때
- 에이전트에게 구현을 맡길 때 — 명세가 곧 작업 지시서이자 완료 기준입니다

## 규칙

- 파일: `주제.md` (영문 kebab-case). 새 명세는 [`_template.md`](_template.md)를 복사합니다.
- 상태: `초안 → 확정 → 구현됨 → 폐기`. 확정 전에는 팀 합의가 필요하고, 구현됨 이후 코드가 바뀌면 같은 PR에서 명세를 갱신합니다.
- 필드는 표 또는 JSON 예시로, 오류는 HTTP 상태·코드와 함께 적습니다.
- 수용 기준(acceptance criteria)은 테스트로 옮길 수 있게 구체적으로 씁니다.

## 목록

| 문서 | 내용 | 상태 |
|---|---|---|
| [`api.md`](api.md) | HTTP API 전체, 인증·쓰기 보호, 문서 등록 payload | 구현됨 (1.3.1) |
| [`integrated-answer.md`](integrated-answer.md) | `POST /api/ask` 입력·출력, CII 표시, 기준 비교 | 구현됨 (1.3.1) |
| [`maritime-data-api.md`](maritime-data-api.md) | 독립 Python/PostgreSQL 조회·계산·조회 도우미 | 구현됨 (Tool 계약 v1) |
| [`maritime-data.md`](maritime-data.md) | 실제·합성 구분, 출처·품질·집계 적격성 | 구현됨 (데이터 계약 v1) |
