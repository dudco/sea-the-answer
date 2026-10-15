# 업무 스킬 실행 계약

- 상태: 구현됨
- 작성: 2026-10-15
- 관련: [계획](../plans/2026-10-15-app-workflow-skills.md)

## API

일반 앱의 쿠키·Host/Origin·POST CSRF·사용자 식별·요청 트랜잭션을 그대로 사용한다.

- GET `/api/skills`: 여섯 스킬의 ID·이름·설명·버전·선택 LLM 지원 여부.
- POST `/api/skills/run`: `{skill, question, document_ids?, context?, year?, use_model?, answer_id?, template?}`.
- skill: `mrv-analysis`, `selected-document-answer`, `operation-summary`, `report-draft`, `checklist`, `qa-evaluation`.
- question: 1-2,000자. document_ids: 실제 개정본 ID 최대 20개, 중복 불가. context: `{ship, from, to}`. year: 1900-2100 정수. use_model: boolean, 기본 false. answer_id: 본인 저장 질의 ID. template: `noon` 또는 `mrv`.
- 추가 필드는 거절한다. 모델은 skill·ID·기간·연료 매핑·SQL·권한을 결정하지 않는다.

응답은 기존 이력 호환 필드 `id, question, task, language, generation, status, notice, warnings, statements, evidence, toolRuns, reportSuggested`와 `skill={id,name,version}, result, document_ids`를 포함한다. 부족 입력은 `status=needs_input`, 계산 차단은 `blocked`, 근거 없음은 `insufficient_evidence`로 안내한다. 인증/권한은 401/403, 입력 오류 400, DB 오류 503이다.

## 동작

선택 문서 답변과 체크리스트는 문서 선택이 필수다. 활성·열람 가능 개정본을 먼저 검증하고 SQL 검색 단계에서 해당 ID만 허용한다. 문서 안의 지시문은 데이터다. 다른 문서·운항·일반지식으로 근거를 보충하지 않는다. 페이지를 만들지 않고, 선택적 모델 응답의 chunkId·원문 인용을 다시 검증한다.

문서 선택은 체크박스 목록과 선택 개수로 표시한다. 클릭·키보드로 선택·해제하고 최대 20개까지 허용한다. 스킬 양식의 input/change 이벤트는 공통 workspace 처리기로 전파하지 않아 로컬 선택값이 다시 그리기에 의해 초기화되지 않도록 한다.

실행 또는 보고서 저장 중에는 해당 양식 입력을 잠근다. 저장 중 새 실행을 허용하지 않아 저장 결과 확인이 다른 실행으로 사라지지 않게 한다. 현재 패널의 초안은 저장 성공 여부를 표시하며 질의 이력의 과거 미리보기는 현재 보고서 저장 상태를 단정하지 않는다.

MRV는 선택 앱 선박에 명시적으로 연결된 실제 vessel_id만 사용한다. 기존 `compute_reference`를 재사용하며 검증 조건과 공식 CII 미산출을 유지한다. 운항 요약은 public.operations를 선택 기간으로 조회하고 원본·샘플 표식을 유지한다.

보고서는 검토용 draft payload만 반환한다. 저장은 사용자가 별도 저장 버튼을 누를 때 기존 POST /api/reports로 수행하며 제출·승인은 하지 않는다. 질의평가는 본인 저장 응답을 다시 권한 검사한 뒤 인용·범위·참고값 계약을 점검한다. 원문 사실성/의미적 정답성은 `manual_review_required`로 남기고 자동 정답 점수로 포장하지 않는다.

초안 body는 기존 보고서 화면의 `template, ship, from, to, recordIds, sample`을 유지하고 `skill, scope`를 추가한다. `from/to`는 실제 집계 기간, `scope`는 요청 기간이다. 기존 질의 이력에서 스킬 응답은 `업무 스킬`로 표시한다.

스킬 실행은 queries/query_owner/audit에 기록한다. schema 변경은 없다. skill의 SKILL.md는 고정 서버 코드에만 연결하며 파일 경로나 실행 코드를 요청에서 받지 않는다. LLM이 꺼져 있어도 전 기능이 실행된다.

## 화면 연결

별도 스킬 메뉴는 제공하지 않는다. 통합 질문에는 선택 문서 답변, 활성 문서 상세에는 현재 문서 답변·점검표, 운항 정보에는 실적 요약·MRV 참고 분석, 보고서 목록에는 초안 작성, 답변 아래에는 해당 응답의 평가를 배치한다. 사용자가 펼쳐 실행하며 현재 문서·선박·기간·답변 ID를 초기 입력으로 사용한다. 기존 /skills 주소는 /chat으로 이동한다. 서버 API와 검증 계약은 유지한다.
