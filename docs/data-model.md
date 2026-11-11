# 데이터 모델

## 자료 현황·질문 분기 JSON (2026-11-11)

새 테이블 없이 기존 `queries.response.dataStatus`에 서버에서 확인한 자료별 상태·건수·기간·출처와 범위를 저장한다. `routing`은 경로 종류와 규칙/모델/실패 사유만 기록한다. 문서 현황은 계정의 현재 열람 범위이며 후속 조회에서 저장된 숫자를 재사용하지 않는다. 데이터 원본·모델 출력 SQL·접속 문자열은 저장하지 않는다. [필드 계약](specs/integrated-answer.md#자료-현황과-의미-기반-경로-보완-2026-11-11-확정).

일반 답변의 `generationFailure`는 안전한 실패 코드/재시도 가능 여부만 보존하며 기존 경고를 유지한다. 관리자 오류 감사 기록에는 코드·호출 여부·생성 시간만 추가한다. 모델의 원시 오류 응답·추론 내용·접속 비밀은 저장하지 않는다. [공급자 계약](specs/llm-provider.md#qwen-호환성과-실패-원인-2026-11-11).

## 웹 운항 자료 등록 (2026-11-06)

새 영구 테이블·migration 없이 기존 operations와 maritime_data 원본/품질/후보 테이블을 사용한다. 행 충돌은 등록 전체를 롤백하고 동일 행은 변경하지 않는다. vessels의 기존 ship_id는 보존하며 명시 확인한 동일 IMO·유일 실제 앱 선박에만 새 연결을 허용한다. 임시 업로드 ID/소유자는 한 서버 프로세스에 귀속되고 파일은 제한된 임시 저장소에 둔다. 감사 기록에는 등록 해시·종류별 건수·연결 건수를 남긴다. AIS 참조는 별도 운영 볼륨의 JSON이며 DB/앱 JSON 백업에 합치지 않는다. [입출력 계약](specs/operation-data-import.md).

## 자연어 업무 실행 JSON (2026-11-06)

새 SQL 테이블이나 migration 없이 기존 `queries.response.workflow`에 검증 범위·되묻기·실행 결과·산술 비교·부모 응답 ID를 저장한다. `query_owner`로 후속/이력 열람을 제한한다. scope에는 선박 id/name/version/IMO, 연도/기간, MRV 매핑, 선택 문서 ID와 원래 질문, 운항 표·차트의 presentation_question을 보존하며 이력의 숫자를 다음 질문 답변으로 재사용하지 않는다. 출처 원본·MRV·선박/운항 기록은 조회만 한다. 정확한 필드와 상태는 [통합 답변 계약](specs/integrated-answer.md#자연어-업무-실행-확장-2026-11-06-구현됨)에 둔다. 기존 JSON 백업에 질문/소유자 자료가 포함되며 별도 백업 형식을 추가하지 않는다.

## 외부 선석 참조 snapshot (2026-11-04)

2026-11-10 확장도 새 migration 없이 기존 질문 JSON에 저장한다. `workflow.clarification`은 다음에 물을 조건/문장이고 `navigation.request_question`은 선박명 보완 전 원래 항구 조건이다. AIS 자료 현황은 `navigation.kind=catalog-status`와 기존 catalog summary, 선택적인 `ship_check`를 보존한다. 저장된 현황·이전 숫자를 새 조회에 사용하지 않으며 현재 파일/권한/식별자로 재확인한다. 실제 필드는 [통합 답변 계약](specs/integrated-answer.md)에 둔다.

새 DB 테이블을 만들지 않는다. 준비한 `catalog.json`은 실제 MRV IMO와 공개 AIS metadata의 교집합, 선석별 게시 제한·조건·중복 변형, 출처 SHA256·수집 시각을 보관하는 별도 읽기 전용 참조 파일이다. 형식·수량 단위·노후화 정책은 [선석 참조 계약](specs/port-references.md)에 정의한다. API는 현재 `maritime_data.vessels`의 REAL ID를 확인하지만 AIS 순간값을 연간 보고 값에 채우거나 기존 계정·운항·제원 테이블을 갱신하지 않는다. 이 외부 파일은 앱 JSON 백업에 포함되지 않으므로 원본·manifest·준비 절차와 함께 별도 보존/배포해야 한다. 복구 후에도 자료의 경과 시간은 요청 시 다시 검사한다.

> 대상: 기본 앱 1.4.0 + 선택 해사 데이터 Tool 계약 v1 · 최종 확인: 2026-10-15 (`migrations/`, `backend/api/store/`, `api/workflow_skills.py`, `scripts/` 대조)

참조 snapshot 1.1은 항구별 `source_id`·`reference_scope`를 추가하고 source variants의 조건/위치와 최종 제한값 일치를 검사한다. 오프라인 묶음은 catalog·SHA256 manifest·출처 안내로 구성하며 이전 catalog는 해시 이름의 별도 파일로 보존한다. 이 확장은 PostgreSQL 테이블·운항 JSON 필드·기존 MRV 행을 바꾸지 않고 앱 JSON 백업에도 포함되지 않는다. [필드·오프라인 계약](specs/port-references.md)을 따른다.

snapshot 1.2는 `ais_no`/`schema_no`(노르웨이 공개 위치 보고/명세), `aalborg_berths`(덴마크 Oil Terminals p.7)를 추가한다. 관측값의 선택적 `position_reported_at`·`raw_reported_fields`는 단위/정적 시각이 미확인인 원문 값이다. 기존 `reported_*_m`·`metadata_received_at`로 승격하지 않는다. 동일 IMO의 복수 source는 `observation_candidates`와 개수를 보존하고 단일 관측값 비교는 보류한다. 상세/질문 결과는 `readiness`의 7개 실제 확인 항목과 선석별 `operational_checks`를 추가한다. 가정 입력 `scenario`는 실제 계측·기상·예선 배정·승인 데이터 테이블을 생성하지 않으며 기존 선박/운항 필드를 바꾸지 않는다. 질문 이력은 당시 미확인 사유와 원문 출처를 JSON에 보존한다.

통합 질문에서 만든 항구 참조 답변은 기존 `queries.response` JSON의 `navigation`에 저장하고 `query_owner`로 사용자에게 연결한다. `generation=tool`, `task=navigation`, `reference_only=true`, `admission=not_assessed`와 선택 선박·매핑 문맥·항구별 건수·상세 수치·출처/시점·부족 사유를 보존한다. `evidence`·`statements`·`toolRuns`는 빈 배열이며 외부 항만 URL을 등록 문서 인용이나 CO₂ 실행 기록으로 만들지 않는다. Query 감사 기록과 소유자별 이력을 재사용하므로 추가 migration은 없다. 저장된 결과는 당시 수집본·비교 시점의 기록이며 현재 입항 허가로 갱신되는 값이 아니다.

2026-11-05 질문 조건 확장은 `navigation.query`(수치 필터·상태·항구별 정렬·표시 설명), `selection`(`port_ids`, `berth_id`), 비교/표시/수치 미확인 제외 건수를 추가한다. 항구별 `available_berth_count`는 필터 전 개수이고 기존 `berth_count`는 표시 개수다. 검증된 후속 질문만 `previous_query_id`를 저장한다. `no_reference_matches`, `unsupported_condition`, `needs_reference_scope`, `needs_previous_query`를 추가하며 과거 JSON에 이 필드가 없어도 화면 열람은 가능하다. 이전 숫자는 재사용하지 않고 같은 소유자·선박 버전·IMO·현재 매핑을 확인한 뒤 새로 비교한다. SQL 테이블 변경은 없다.
> 테이블·필드·상태 값을 바꾸면 같은 작업에서 이 문서를 고치고, 되돌리기 어려운 변경이면 ADR을 남깁니다.

> 문서 전처리 통합은 `migrations/`의 PostgreSQL 테이블/컬럼을 바꾸지 않는다. `chunks.document_id`로 문서 제목을, `chunk_pages.id`로 물리 페이지를 조회한다. 기존 `haedap-chunk-v1` 문서 해시와 청크 ID를 유지하고 기존 개정본의 청크는 재작성하지 않는다. 새 문서·새 내용 개정의 분할 규칙만 [전처리 계약](specs/api.md#python-문서-전처리-계약-2026-10-13-확정)에 따라 달라진다.

snapshot 1.3은 과거 등록 제원 `static_references`(현재 확인된 IMO/MMSI, 등록 IMO, 길이/폭/등록 흘수, 등록 유효기간, source locator/issue), 요청 기간 `static_reference_period`, 고정 지역 관측 `environment_observations`(station/parameter, 단위, 관측시각/품질, 좌표, 기준면·station metadata 해시)을 추가한다. `static_reference`/선석별 `static_reference_checks`는 길이/폭의 별도 과거 참고 비교다. 기존 AIS 신고값·기존 선석 상태는 유지한다. `environment`는 관측/수집 나이와 품질을 제공하지만 가정 입력·UKC·입항 판정에 자동 사용하지 않는다. 1.0–1.2 읽기와 기존 PostgreSQL 스키마/JSON 백업 범위를 유지한다. 상세 제약은 [참조 계약](specs/port-references.md#등록-제원지역-관측-참조-확장-2026-11-05-확정)에 정의한다.

참조 snapshot 1.4의 `port_guidance`는 최대 6개 고정 공식 문서와 `guidance_review_sha256`을 추가한다. 문서별 항구/URL·출처·raw/main 본문 SHA256·수집 시각·표시 개정일·명시 적용일, 조건별 한국어 요약/적용 범위·수치/단위·원문 발췌/정규화 본문 위치·지정 선석을 보존한다. 상세/질문 응답의 `official_guidance`는 항상 적용성 확인 필요이며 기존 자동 비교에 사용하지 않는다. 같은 항구의 다른 경로나 선종 조건을 현재 선박에 적용된 것으로 표시하지 않는다. 기존 sources 12개·AIS/등록/관측 자료·SQL 스키마·앱 백업 계약은 유지하며 지침은 별도 묶음으로 배포한다.

## 1. 저장소 개요


- **엔진**: PostgreSQL(compose 서비스 `db`, `postgres:18-alpine`). FastAPI가 요청마다 `psycopg`로 연결하고 요청 단위 트랜잭션으로 커밋·롤백합니다.
- **위치**: `DATABASE_URL`. compose에서는 `db` 컨테이너, 데이터는 볼륨 `haedap_db-data`.
- **스키마**: 최상위 [`migrations/`](../migrations/)의 SQL 파일이 원본이고, dbmate가 순서대로 적용합니다([ADR 0010](adr/0010-dbmate-migrations.md)). 적용 이력은 `schema_migrations` 테이블에 있습니다. compose의 `migrate` 서비스가 `docker compose up` 때마다 대기 중인 파일을 적용한 뒤 backend가 시작합니다. 현재 테이블 정의는 [`20261013000000_init.sql`](../migrations/20261013000000_init.sql) 이후 파일들을 차례로 적용한 결과입니다.
- **JSON `body` 컬럼**: 선박·운항·문서 메타 등은 필드를 `jsonb`로 저장합니다. 검색·정렬에 쓰는 값(`ship`, `date` 등)만 별도 컬럼으로 뺍니다.

```mermaid
erDiagram
  documents ||--o{ chunks : "document_id"
  chunks ||--o| chunk_pages : "id"
  documents ||--o| document_meta : "id"
  documents ||--o| document_files : "id"
  ships ||--o{ operations : "ship"
  reports ||--o| report_meta : "id"
  users ||--o{ report_meta : "owner"
  queries ||--o| query_owner : "id"
  users ||--o{ changes : "actor/reviewer"
```

(관계선은 논리적 관계입니다. 실제 외래키는 `migrations/`의 SQL을 보세요 — 예: `chunks.document_id → documents.id`, `operations.ship → ships.id`.)

## 2. 문서와 검색

### `documents` — 문서 개정본(revision) 단위

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | TEXT PK | 개정 ID = `{logical_id}-{hash 앞 16자}` |
| `logical_id` | TEXT | 논리 문서 ID (영문 소문자·숫자·하이픈). 같은 문서의 개정본이 공유 |
| `hash` | TEXT | 정규화한 문서 JSON의 SHA-256 (`haedap-chunk-v1` 접두). 같으면 `unchanged` |
| `title`, `reference`, `version` | TEXT | 제목, 출처 조항, 버전명 |
| `kind` | TEXT | `onboard` · `official-summary` · `sample` |
| `url` | TEXT NULL | HTTPS 원문 URL (`official-summary`는 필수) |
| `reviewed_at` | TEXT | 확인일 `YYYY-MM-DD` |
| `language` | TEXT | `ko` · `en` |
| `active` | INTEGER | 1 = 현재 개정본. `UNIQUE(logical_id) WHERE active=1`로 하나만 허용 |
| `imported_at` | TEXT | ISO 시각 |

### `chunks` / `chunk_pages`

| 테이블 | 컬럼 | 설명 |
|---|---|---|
| `chunks` | `id`(=`{revision}-{n}`), `document_id`, `position`, `heading`, `text` | 절을 900자씩 분할 |
| `chunk_pages` | `id`(청크 ID), `page` | PDF 물리 페이지 번호(없으면 NULL → "페이지 미지정") |

검색(`Workspace.search`): 현재 개정·문서 상태·열람 범위·종류 필터를 통과한 청크를 `api/rag_search.py`에 전달하고 BM25·준비된 문서의 벡터 결과를 RRF로 결합해 상위 5개를 반환합니다. BM25 역인덱스는 OpenSearch가 유지하며 PostgreSQL에는 검색 점수를 저장하지 않습니다. 벡터/준비 정보는 아래 파생 Chroma 구조에 저장합니다. 토큰화와 점수 규칙은 [검색 계약](specs/api.md#문서-검색-bm25), 결합·fallback은 [벡터 계약](specs/rag-vector.md)을 따릅니다.

### `rag_lexical_jobs` — OpenSearch 파생 색인 작업

`20261111000000_rag_lexical_jobs.sql`은 문서 ID PK, generation, pending/processing/done/failed 상태, attempts, claim_token, fingerprint, error_code, next_attempt_at, updated_at, source_txid를 추가한다. documents/document_meta/chunks/chunk_pages의 변경 트리거가 같은 트랜잭션에서 enqueue하고 같은 문서의 반복 변경은 트랜잭션별로 합친다. 물리 삭제 뒤에도 정리 작업이 남도록 문서 FK는 없다. 기존 문서를 migration에서 자동 enqueue하지 않는다.

전용 worker가 세션 advisory lock으로 문서별 중복 실행을 막고 원본·generation을 재확인한 뒤 완료한다. PostgreSQL done은 원격 저장소 건강 보증이 아니다. OpenSearch의 내용별 청크 record와 같은 색인의 문서 snapshot receipt가 검색 준비를 결정한다. 삭제·저장소 교체·누락 복구는 [키워드 계약](specs/rag-lexical.md)을 따른다.

### `document_meta` / `document_files`

| 테이블 | 내용 |
|---|---|
| `document_meta(id, body)` | 개정본별 메타 JSON: `{scope, status, issuer, issuedAt, revisedAt, applicability, revision}` |
| `document_files(id, name, base64)` | 개정본의 원본 PDF (Base64, 25MB 이하). 새 개정에 파일이 없으면 이전 개정의 PDF를 복사 |

- `scope`: `all`(로그인 사용자) · `operator`(담당자·관리자) · `admin`(관리자만). 바꾸면 같은 논리 문서의 **모든 개정본**에 적용.
- `status`: `active`(사용 중) · `retired`(폐기) · `deleted`(삭제 — 행은 남기고 검색·열람에서 제외).
- `revision`: 메타 수정 시각(ms). 낙관적 잠금 `expectedMetaRevision`에 사용.
- 메타가 없으면 기본값 `{scope:'all', status:'active', …, revision:0}`.

## 3. 운항

### `ships(id, body, version, seq)`

`seq`는 등록 순서(identity)입니다. 목록과 화면의 기본 선박 선택이 이 순서를 따릅니다(`ORDER BY seq, id`). API 응답에는 나오지 않습니다.

`body` 필드:

| 필드 | 타입 | 필수 | 비고 |
|---|---|---|---|
| `id` | string | 자동 | UUID |
| `name` | string | ✓ | ≤100자 |
| `type` | string | ✓ | 선종, ≤80자 |
| `dwt` | number | ✓ | 1 ~ 1e7 t |
| `imo`, `from`, `to` | string | | 선택 |
| `sample` | boolean | | 가상 예시 여부 |

### `operations(id, ship, date, body, version)` — `UNIQUE(ship, date)`

| 필드 | 단위 / 범위 | 필수 |
|---|---|---|
| `ship` | 등록된 선박 ID | ✓ |
| `date` | `YYYY-MM-DD` | ✓ |
| `fuel` | t, 0 ~ 1e7 | ✓ |
| `factor` | tCO₂/t 연료, 0 초과 ~ 10 | ✓ |
| `distance` | nm, 0 ~ 1e7 | ✓ |
| `speed` | kn, 0 ~ 100 | ✓ |
| `fuelType` | 문자열 | ✓ |
| `position`, `voyage`, `weather`, `note` | 문자열 | |
| `draft` | m, 0 ~ 40 또는 null | |
| `engineHours` | h, 0 ~ 24 또는 null | |
| `sample` | boolean | |

규칙: 같은 선박·일자는 한 건. 직전 기록보다 연료가 2배 이상이면 `note` 5자 이상 필요. CSV 일괄 등록은 1~1,000행, 한 행이라도 실패하면 전체 미반영.

파생 값(저장하지 않음, `analysis.summarize`): `emission = Σ fuel×factor`, `intensity = emission×1e6 / (dwt×distance)` gCO₂/(DWT·nm), `speed` = 평균. 공식 CII는 항상 `{status:'unavailable'}`.

## 4. 보고서

| 테이블 | 컬럼 | 설명 |
|---|---|---|
| `reports` | `id`, `title`(≤120), `type`, `text`(≤200,000), `sources`(문서 ID JSON 배열), `version`, `updated_at` | 본문 |
| `report_meta` | `id`, `owner`(사용자 ID 또는 `guest_…`), `status`, `body`(JSON) | 소유·상태 |

- `type`: `규정 검토` · `일일 운항` · `배출량 검토` · `종합 검토`
- `status` 전이: `draft` → (검토 요청) `review` → (승인) `approved` / (반려) `draft`. `review`·`approved`는 수정 불가 → 복사해 새 초안.
- `body`(≤50,000자 JSON): 생성 초안은 `{template:'noon'|'mrv', ship, from, to, recordIds:[{id,version}], sample}`, 승인 시 `approvedBy`, `approvedAt` 추가.
- 업무 스킬 초안도 위 공통 필드를 유지하며 `skill`과 요청 당시 `scope:{ship,from,to}`를 추가한다. Noon의 `from/to`는 실제 마지막 기록일이고 `scope`는 사용자가 요청한 전체 기간이다.
- 열람: 관리자, 소유자, 또는 `approved` — 단, `sources`의 모든 문서를 열람할 수 있어야 함.
- 관리자 삭제: 버전을 검사한 뒤 `report_meta`·`reports` 행을 같은 트랜잭션에서 삭제한다. 대기 검토 요청은 삭제 사유를 기록해 `rejected`로 종료하고 감사·검토 이력은 보존한다. 검토 처리와 삭제는 동일한 보고서 행 잠금을 사용한다.

## 5. 사용자·이력·운영

| 테이블 | 컬럼 | 설명 |
|---|---|---|
| `users` | `id`, `username`(UNIQUE), `name`, `role`, `password`(`salt:scrypt hex`), `active`, `version`, `must_change_password`(boolean, 기본 true) | `role`: `admin`(관리자) · `operator`(선원) · `viewer`(열람); 활성 계정만 로그인. 비밀번호 초기화 후 본인 변경 필수 |
| `queries` | `id`, `question`, `response`(통합 답변 JSON 전체), `created_at` | 질문 당시 답변 재열람용. 선택적 표·차트/입력·시간 통계와 운항 미리보기는 [표현 계약](specs/answer-presentation.md)을 따르며 이전 JSON에는 해당 필드가 없어도 된다. |
| `query_owner` | `id`, `owner` | 질문 소유자 |
| `tool_runs` | `id`, `tool`, `version`, `input`, `output`, `created_at` | 계산 도구 실행 기록 |
| `changes` | `id`, `at`, `actor`, `kind`, `payload`, `status`, `reviewer`, `reviewed_at`, `note` | 변경·승인 이력 |
| `audit` | `id`, `at`, `actor`(이름), `category`, `action`, `target`, `detail`(JSON) | 감사 로그 (관리 화면 최근 500건) |
| `settings` | `key`, `value` | 아래 키 참고 |

`changes.kind`: `document.save`, `document.delete`, `ship.save`, `operation.save`, `operation.import`, `operation.delete`, `report.approve`.
`changes.status`: 관리자 직접 변경은 즉시 `approved`로 기록. 보고서 검토 요청(및 이전 버전의 요청)은 `pending` → `approved` / `rejected`.

`settings` 키: `schema`(`'2'`), `autoBackup`(`daily`|`off`), `autoBackupDay`(마지막 자동 백업 UTC 날짜), `publicAccessV1`(이전 버전 잔존 키; 현재 인증 정책에 사용하지 않음).

## 6. 식별자와 동시성

- 대부분의 ID는 `randomUUID()`. 문서는 내용 해시 기반 개정 ID.
- **낙관적 잠금**: `ships`, `operations`, `reports`, `users`는 `version` 정수를 갖고, 요청의 `version`이 DB와 다르면 `409 VERSION_CONFLICT`. 저장 시 +1. 문서는 `expectedId`(현재 개정 ID)와 `expectedMetaRevision`으로 같은 검사를 합니다.
- 문서의 `document.save` / `mode: "metadata"`는 두 버전 값을 필수로 검사하고 기존 `document_meta.body`만 갱신합니다. 현재 개정 행 잠금 안에서 검사·저장을 수행하며, `body.revision`은 이전 값보다 증가합니다. 문서 개정 ID·확인일·청크·PDF는 유지하고 열람 범위는 이전 개정본에도 반영합니다. 테이블 추가나 백업 형식 변경은 없습니다.
- 변경은 PostgreSQL 트랜잭션 하나로 처리하며 충돌 제어가 필요한 기존 행은 `FOR UPDATE`로 잠급니다.
- 새 보고서·질문 소유자는 `users.id`입니다. 기존 `guest_` 식별자의 소유 자료는 보존하되 자동 이전하지 않습니다.
- `20261021000000_user_password_change.sql`이 기존 사용자에게 비밀번호 변경 요구를 추가합니다. 계정 변경은 행 잠금과 계정 관리용 advisory lock으로 직렬화합니다. 계정 버전 변경은 세션을 무효화합니다.

## 7. 백업 형식

`HAEDAP_BACKUP_DIR/{uuid}.json` (compose: 볼륨 `haedap_backups`의 `/data/backups`, 직접 실행 기본값: `backend/data/backups`). 각 테이블을 `SELECT *` 그대로 담으므로 `ships.seq` 같은 컬럼도 포함되며, 복구는 컬럼 이름을 지정해 넣습니다(그 컬럼이 없는 이전 백업은 기본값으로 채움).

```json
{
  "format": "haedap-workspace",
  "version": 2,
  "createdAt": "2026-10-08T00:00:00.000Z",
  "label": "수동 백업",
  "tables": { "documents": [], "chunks": [], "reports": [], "tool_runs": [], "queries": [],
              "users": [], "document_meta": [], "document_files": [], "chunk_pages": [],
              "ships": [], "operations": [], "report_meta": [], "audit": [], "query_owner": [],
              "changes": [], "settings": [] },
  "checksum": "checksum 필드를 뺀 나머지 JSON의 SHA-256 hex"
}
```

- 복구 조건: `format`·`version:2`·체크섬 일치, 16개 테이블 모두 존재, 활성 관리자 1명 이상. 복구 직전 자동 백업을 만들고 한 트랜잭션에서 전체 교체합니다.
- `.env`(API 키)는 포함하지 않습니다.
- `maritime_data`의 테이블·원본·CSV는 앱 JSON 백업에 포함하지 않습니다. 앱 복구는 외부 해사 레코드를 삭제하지 않으며, 복구 전 연결한 `vessels.ship_id`는 복구 후 동일한 선박 정체성이 확인되는 경우만 재연결합니다. 누락되거나 정체성이 다르면 NULL로 남기고 재연결·미연결 건수를 기록합니다. 전체 해사 데이터는 별도 PostgreSQL 백업이 필요합니다(9절).

## 8. 스키마를 바꿀 때

1. 새 마이그레이션 파일을 만듭니다(최상위에서): `docker compose run --rm migrate new add_ship_flag` → `migrations/<시각>_add_ship_flag.sql`.
2. `-- migrate:up`에 변경을, `-- migrate:down`에 되돌리는 SQL을 씁니다. **이미 커밋된 마이그레이션 파일은 고치지 않고** 항상 새 파일을 추가합니다.
3. 적용·확인: `docker compose up -d`(자동 적용) 또는 `docker compose run --rm migrate up`, 상태는 `docker compose run --rm migrate status`, 직전 파일 되돌리기는 `docker compose run --rm migrate rollback`.
4. 백업 대상 테이블이면 `BACKUP_TABLES`에 추가하고, 이전 백업 복구 시의 동작을 정합니다(백업 `version`을 올릴지 결정 → ADR).
5. 이 문서의 해당 절을 갱신하고, `backend/tests/`에 회귀 테스트를, 화면 흐름에 영향이 있으면 e2e를 실행합니다(e2e 스택도 같은 마이그레이션으로 DB를 만듭니다).

## 9. PostgreSQL 해사 데이터 Tool (선택)

앱과 같은 PostgreSQL DB 안의 `maritime_data` 스키마입니다. 루트 dbmate 마이그레이션이 구조를 만들고, 별도 전처리·CSV 적재를 거친 자료만 조회합니다. 아래 여섯 원본·출처·품질 테이블과 두 조회 View가 기본 저장 모델이며, 별도 제원 후보 참조 테이블 하나를 추가합니다. 기존 `public.ships`는 선택적 외래키로 재사용하며 보고기간 MRV·합성 Noon·출처·품질은 독립적으로 보존합니다. 실제/합성·단위 정책은 [데이터 명세](specs/prepare-data.md), 조회·계산 입력은 [API 명세](specs/tools.md)에 정의합니다.

DDL의 원본은 [`20261013010000_maritime_data.sql`](../migrations/20261013010000_maritime_data.sql)입니다. 데이터 필드 사전은 `backend/tools/data_contract.py`의 공유 `FIELDS`에서 생성하며 준비 스크립트도 같은 값을 사용합니다. 사전 생성은 DDL이나 migration을 변경하지 않습니다. SQL의 NOT NULL·CHECK·외래키는 아래 표의 필드 규칙에 추가 적용됩니다. 앱 테이블을 이 구조로 교체하거나 두 데이터를 자동 결합하지 않습니다([ADR 0011 제안](adr/0011-tools-runtime-and-data-preparation.md)).

### ERD

```mermaid
erDiagram
  public_ships o|--o{ vessels : explicit_ship_id
  source_files ||--o{ annual_reports : provenance
  source_files ||--o{ synthetic_noon : provenance
  source_files ||--o{ quality_issues : records
  vessels ||--o{ annual_reports : real
  vessels ||--o{ synthetic_voyages : synthetic
  vessels ||--o{ synthetic_noon : synthetic
  vessels ||--o| capacity_candidates : reference_only
  synthetic_voyages ||--o{ synthetic_noon : contains
```

`quality_issues.record_id`는 연간/일별 레코드 중 하나를 가리키는 논리 참조입니다. SQL의 외래키는 source_id에만 적용합니다. 원본 조회는 record_id 및 출처 키로 수행합니다.

### 컬럼 정의

#### source_files — 원본 파일·출처

| 컬럼 | PostgreSQL 타입 | 제약 | 의미·단위 |
|---|---|---|---|
| source_id | text | PK | Dataset ID + SHA256 |
| dataset_id | text | required | DS-001..006 |
| filename | text | required | Original basename |
| sha256 | text | required | Original byte checksum |
| source_url | text | nullable | Source recorded in assessment; not license approval |
| data_origin | text | required | REAL / SYNTHETIC / REFERENCE / SCHEMA |
| granularity | text | required | report / daily / position / port / schema |
| selection | text | required | Selected use for this preparation |
| row_count | integer | required | Count read from original |
| header_json | jsonb | required | Original ordered headers; duplicate XLSX names preserved |

#### vessels — 실제·합성 선박 식별

| 컬럼 | PostgreSQL 타입 | 제약 | 의미·단위 |
|---|---|---|---|
| vessel_id | text | PK | REAL:IMO:<number> or SYN:<source vessel ID> |
| data_origin | text | required | REAL or SYNTHETIC; never joined across origins |
| imo_number | text | nullable | Seven-digit source IMO; synthetic remains NULL |
| source_vessel_id | text | required | Original IMO or synthetic vessel ID |
| ship_id | text | nullable FK public.ships(id), ON DELETE SET NULL | Explicitly reviewed app ship link; source vessel ID remains unchanged |

#### annual_reports — 실제 MRV 보고기간 집계

| 컬럼 | PostgreSQL 타입 | 제약 | 의미·단위 |
|---|---|---|---|
| record_id | text | PK | Stable source/sheet/row hash |
| source_id | text | FK source_files | Source version |
| source_sheet | text | required | CSV or original XLSX sheet |
| source_row | integer | required | Original row number; CSV is logical record number |
| vessel_id | text | FK vessels | Real vessel only |
| vessel_name | text | nullable | Name at reporting time |
| ship_type | text | nullable | Source classification, unmodified |
| reporting_year | integer | required | Reporting year |
| report_type | text | required | FULL / PARTIAL / ARCHIVE_ANNUAL |
| period_label | text | required | Original reporting period |
| period_start | date | nullable | Reported partial bounds or nominal annual boundary; not observation date |
| period_end | date | nullable | Reported partial bounds or nominal annual boundary |
| fuel_t | numeric | nullable | Source total fuel, tonnes; no fuel split invented |
| co2_t | numeric | nullable | Reported CO2 tonnes; not CO2-equivalent |
| sea_hours | numeric | nullable | Reported sea hours, aliases checked for agreement |
| fuel_kg_per_nm | numeric | nullable | Reported distance intensity |
| distance_nm_estimate | numeric | nullable | fuel_t * 1000 / intensity; scope not verified |
| dwt_t | numeric | nullable | Source value only; missing stays NULL |
| fuel_type | text | nullable | Not provided in MRV inputs |
| quality_status | text | required | VALID / REVIEW / REJECT |
| aggregate_eligible | boolean | required | False for partial, duplicate keys, invalid core numbers |
| provenance_json | jsonb | required | Per-field original columns, missing reasons, distance method |

#### synthetic_noon — 개발용 합성 일별 기록

| 컬럼 | PostgreSQL 타입 | 제약 | 의미·단위 |
|---|---|---|---|
| record_id | text | PK | Stable source/row hash |
| source_id | text | FK source_files | Source version |
| source_row | integer | required | Original CSV logical row |
| vessel_id | text | FK vessels | Synthetic vessel only |
| voyage_id | text | FK synthetic_voyages | Synthetic voyage key |
| report_date | date | required | Noon reporting date; observation period may straddle years |
| period_start_utc | timestamptz | required | Original interval start UTC |
| observed_at_utc | timestamptz | required | Original interval end UTC |
| vessel_name | text | required | Fictional source name |
| ship_type | text | required | Fictional source type |
| dwt_t | numeric | required | Fictional DWT tonnes |
| operating_status | text | required | Source SEA/PORT classification |
| distance_nm | numeric | required | Fictional daily distance; zero in port allowed |
| fuel_t | numeric | required | Fictional daily fuel tonnes |
| fuel_type | text | required | Source fuel label; not an official factor mapping |
| speed_kn | numeric | required | Fictional speed |
| engine_hours | numeric | required | 0..24 hours |
| quality_status | text | required | VALID / REVIEW / REJECT |
| provenance_json | jsonb | required | Simulation flags/version/seed and original missing reasons |

#### synthetic_voyages — 개발용 합성 항차

| 컬럼 | PostgreSQL 타입 | 제약 | 의미·단위 |
|---|---|---|---|
| voyage_id | text | PK | SYN:<source voyage ID> |
| vessel_id | text | FK vessels | Synthetic vessel |
| departure_port_label | text | nullable | Source label; no unverified WPI match |
| arrival_port_label | text | nullable | Source label; no unverified WPI match |
| first_report_date | date | required | First included report date, NOT departure time |
| last_report_date | date | required | Last included report date, NOT arrival time |
| mapping_status | text | required | UNMAPPED_PORT_LABELS / CONFLICT |

#### quality_issues — 전처리 품질 이슈

| 컬럼 | PostgreSQL 타입 | 제약 | 의미·단위 |
|---|---|---|---|
| issue_id | integer | PK | Sequence within deterministic run |
| record_id | text | nullable | Logical reference to annual/noon row |
| source_id | text | FK source_files | Input source version |
| source_row | integer | required | Original record row |
| severity | text | required | INFO / REVIEW / REJECT |
| field | text | required | Affected field |
| code | text | required | Machine-readable issue code |
| detail | text | required | Evidence without replacing original value |

### 조회 View와 추가 제약

#### capacity_candidates - 별도 공개 제원 후보

추가 DDL 원본은 [`20261013020000_capacity_candidates.sql`](../migrations/20261013020000_capacity_candidates.sql)이다. 기존 여섯 운영·출처·품질 테이블과 두 View를 바꾸지 않고 참조 테이블 하나를 더한다.

| 컬럼 | 타입·제약 | 의미 |
|---|---|---|
| vessel_id / imo_number | PK·vessels FK / 7자리, REAL:IMO와 일치 | 이름 대신 원본 IMO로 연결 |
| candidate_dwt_t | nullable numeric, 양수·1천만 미만 | 원본 MRV DWT와 구분한 미검증 후보 t |
| capacity_status | 정해진 상태 5종 | 미확보·단일 출처·5% 이내 일치·5% 초과 충돌 |
| source_file_sha256 / source_filename / source_row | SHA256 / text / 2 이상 정수 | 실제 적재한 CSV 바이트와 논리 레코드 위치 |
| source_json | required JSONB object | 출처별 DWT·GT·URL·제원·제한 등 CSV 원문 필드 |
| loaded_at | timestamptz, 기본 now() | 적재 시각이며 선박 제원의 기준연도가 아님 |

CLI는 REAL 선박·IMO, 출처별 DWT·선택값·충돌 상태를 검증하고 빈 참조 테이블에만 적재한다. 원본 annual_reports.dwt_t·vessels·앱 ships는 수정하지 않는다. 데이터가 있으면 migration down을 거절한다. 앱 JSON 백업은 기존 16개 테이블로 유지하며 참조 테이블·CSV는 PostgreSQL 및 파일 백업으로 보관한다. 과거 보고연도 당시 제원 검증이나 공식 입력 승격은 제공하지 않는다. 새 참조 버전 교체는 별도 검토가 필요하다.

| 객체 | 정의·목적 |
|---|---|
| `real_annual_query` | `annual_reports` 중 `aggregate_eligible=true`만 노출 |
| `development_noon_query` | `synthetic_noon` 중 `quality_status='VALID'`만 노출 |
| 인덱스 | MRV `vessel_id/reporting_year`, Noon `vessel_id/report_date`, Noon `voyage_id` |

- 연간·일별 레코드의 품질 값은 VALID/REVIEW/REJECT로 제한하며 선박 ID 접두어를 검사합니다.
- MRV의 보고 유형은 FULL/PARTIAL/ARCHIVE_ANNUAL이며 집계 적격이면 VALID 및 비PARTIAL이어야 합니다. 기간 경계가 모두 있으면 종료 ≥ 시작입니다.
- Noon은 DWT > 0, 거리·연료·속도 ≥ 0, 기관 운전시간 0~24시간, 종료시각 > 시작시각 및 최대 24시간을 검사합니다.
- 해사 데이터 내부 외래키는 `ON DELETE RESTRICT`입니다. 원본·품질 레코드를 연쇄 삭제하지 않습니다. 앱 선박 연결인 `vessels.ship_id`만 `ON DELETE SET NULL`이며 앱 선박이 없어져도 원본 해사 레코드는 보존합니다.
- 선박 연결은 검토한 명시적 매핑만 허용합니다. 이름·IMO로 자동 조인하거나 원본 선박 전체를 `ships`에 생성하지 않습니다. MRV 보고기간 값을 앱 일별 `operations`로 분해하지 않습니다.
- 명시 매핑 CLI는 실제 원본과 같은 IMO의 비샘플 앱 선박만 연결합니다. 합성은 확인 옵션과 sample 앱 선박이 필요합니다. 서로 다른 기존 연결 덮어쓰기·앱 선박 중복 연결은 거절하고 동일 연결은 멱등 처리합니다. 명령과 설정 우선순위는 [운영 안내](user-guide.md#기존-앱-선박에-명시적으로-연결하기)에 있습니다.

### 버전·적재·백업 경계

`20261013000000_init.sql`은 그대로 유지하고 새 해사 마이그레이션을 그 뒤에 적용합니다. 기본 앱과 같은 `DATABASE_URL`을 사용합니다. `MARITIME_DATA_DATABASE_URL`로 별도 DB를 선택해도 그 DB에 기본 init과 해사 마이그레이션을 모두 적용해야 하며, 외래키는 그 DB의 `public.ships`만 참조합니다.

새 마이그레이션은 fresh DB에서는 빈 해사 테이블을 만듭니다. 이전 `role4` 또는 `maritime_data` 스키마가 하나만 있으면 기대 테이블·컬럼·구조를 검증한 뒤 채택하고, 양쪽이 함께 있거나 구조가 맞지 않으면 전체 변경을 거절합니다. 원본·운항 레코드는 재작성하지 않습니다. 해사 테이블에 데이터가 있으면 down을 거절하므로 일반 앱 rollback 명령으로 원본을 삭제하지 않습니다. 이름을 되돌려야 하는 기존 환경은 별도 보존·이전 계획이 필요합니다.

CSV loader는 DDL을 실행하지 않습니다. 마이그레이션이 적용되어 있고 6개 대상 테이블이 모두 빈 경우에만 한 트랜잭션 안에서 검증 후 적재합니다. 하나라도 데이터가 있으면 삭제·재적재하지 않고 거절합니다. CSV·원본·출처 해시는 별도 데이터 버전으로 보존합니다. 실행 절차와 이전 환경의 설정 전환은 [운영 안내](user-guide.md#10-해사-데이터-tool-선택)에 있습니다.

기본 앱의 JSON 백업에는 해사 테이블과 원본 파일이 포함되지 않습니다. 앱 복구는 현재 해사 선박 연결을 보관한 뒤 앱 선박을 교체하고, 동일한 정체성의 선박만 재연결합니다. 삭제·불일치 연결은 NULL로 두며 처리 건수를 복구 결과·감사에 남깁니다. 이 보존 절차는 과거 연결까지 복원하는 해사 백업을 대체하지 않습니다. 별도로 PostgreSQL 백업과 원본·전처리 산출물을 보관해야 합니다. 공개 제원·환경성능 참조 자료는 별도 데이터 폴더에 관리하며, 현재 위 여섯 운영 테이블에 자동 적재하거나 공식 CII 입력으로 사용하지 않습니다.
## 파생 벡터 색인과 작업 큐

선택적 Chroma collection은 PostgreSQL의 문서·청크·권한을 대체하지 않는다.
청크 ID/문서 ID/제목/페이지/heading/내용 해시/모델 계약 fingerprint와 정규화 벡터만 저장하고 본문은 중복 저장하지 않는다.
모델/입력 규칙별 collection, 내용별 immutable record ID를 사용한다. PostgreSQL 백업에는 벡터/모델 파일이 포함되지 않는다.
새 Chroma metadata의 `embedding_input_hash`는 모델 계약+실제 입력 해시다. 개정 ID/페이지만 달라져도
같은 입력의 벡터 값을 재사용하고 record의 문서·페이지는 현재 값으로 유지한다. 기존 metadata도 검색 호환성을 유지한다.
DB를 복원한 뒤 원본 청크에서 재색인할 수 있다. 상세 스키마와 일관성 계약은 [rag-vector](specs/rag-vector.md)를 따른다.

`haedap-ready-<fingerprint 앞 32자>`는 ANN 검색에 쓰지 않는 파생 확인 정보 collection이다.
키는 version·document_id(개정 ID)·정렬한 전체 청크 snapshot·fingerprint·벡터 collection UUID·청크 수의 해시다.
metadata는 이 필드와 state(`ready`/`invalid`)만 담고 본문은 저장하지 않는다. 고정 1차원 값은 Chroma 저장 형식용이다.
검색은 현재 PG snapshot과 정확히 맞는 ready만 사용한다. jobs.done과 독립적이며 PG 테이블 변경은 없다.

`20261029000000_rag_index_jobs.sql`은 원본 문서/청크 컬럼을 바꾸지 않고 작업 테이블을 추가한다.

| 컬럼 | 의미 |
|---|---|
| id | bigint identity PK |
| document_id | documents.id FK, 물리 삭제 시 CASCADE |
| fingerprint | 모델·입력 규칙·라이브러리 계약 해시, document_id와 UNIQUE |
| generation | enqueue마다 +1, 이전 작업의 완료 무효화 |
| state | pending / processing / done / failed / cancelled |
| attempts | 이번 세대의 실행 횟수, enqueue/retry 시 0 |
| claim_token | 실행별 UUID, 세대와 함께 조건부 완료에 사용 |
| error_code | 안전한 고정 코드; 본문/DSN/외부 예외 원문 저장 금지 |
| next_attempt_at / updated_at | 재시도 시각 / 상태 변경 시각 |

pending → processing → done, 실패는 failed(5회까지 재시도), 비활성·삭제 개정은 cancelled다.
processing 중 프로세스가 죽으면 PG 세션 잠금 해제 후 재획득한다. 새 저장은 pending으로 새 세대를 요청한다.
원본과 작업 생성은 하나의 트랜잭션, Chroma 저장과 작업 완료는 별도이며 실패 시 멱등 재처리한다.
앱 JSON 백업의 16개 테이블 계약은 유지한다. 작업은 복원 시 문서 물리 삭제와 함께 제거되므로
복원 후 enqueue가 필요하다. migration down은 큐만 삭제한다(진행 작업 상태가 소실되므로 worker 중지 후 적용).

## 대화 식별자 (2026-11-09)

`queries.response` JSON의 선택 필드 `conversationId`는 해당 대화의 첫 `queries.id`다. 첫 질문과 과거 질문에는 필드가 없어도 되며 `COALESCE(response->>'conversationId', id)`로 묶는다. `query_owner.owner` 조건을 항상 함께 적용한다. 첫 질문 행 잠금은 대화 추가·삭제의 동시 실행을 직렬화한다. 전체 대화 복원은 생성 시각, ID 순이다. 기존 queries/query_owner 백업에 JSON이 포함되므로 테이블·백업 형식·마이그레이션 변경은 없다. 과거 백업을 복원하면 그 백업에 포함된 삭제 전 대화도 복원될 수 있다.

## 2026-11-09 문서 묶음 업데이트

스키마 변경 없이 `settings`의 `knowledge-update:mepc-2026-11-09-v1` 키로 완료 여부와 변경·추가 건수를 JSON 문자열로 저장한다. 기존 bootstrap 초기화 잠금과 트랜잭션 안에서 기존 제목을 먼저 변경하고 MEPC 10건을 `save_document`로 등록한 뒤 완료 키를 기록한다. 백업에 settings가 포함되므로 복구 시에도 완료 여부가 보존된다. 삭제된 항목이나 기존 논리 ID가 있으면 재등록하지 않는다.

이번 기존 제목 변경은 표시 이름만 바꾸는 일회성 데이터 갱신이다. 기존 개정 ID와 원본 제출 해시(`hash`), 본문·청크·PDF·당시 답변 스냅샷을 보존한다. 따라서 변경 전 개정의 hash는 표시 이름 변경 전 제출 원문을 식별한다. 새로 등록하는 문서와 이후 본문 개정의 해시 계산은 기존 계약을 따른다. 활성 문서는 제목 변경에 맞춰 색인 작업을 다시 요청하며 현재 검색 결과는 새 제목을 사용한다.
