# HTTP API

- 상태: 구현됨 (1.4.0)
- 최종 확인: 2026-10-21 (`backend/api/` 대조)
- 관련: [`../architecture.md`](../architecture.md), [`../data-model.md`](../data-model.md), [`integrated-answer.md`](integrated-answer.md), [ADR 0016](../adr/0016-crew-admin-authentication.md)

## 1. 목적

화면(`frontend/src/lib/api.js`)과 팀 모듈이 사용하는 로컬 HTTP API의 계약입니다. 브라우저는 Next.js 공개 주소(`http://<host>:5173/api/...`)로 호출하고, Next.js가 `HAEDAP_API_ORIGIN`(기본 `http://127.0.0.1:8000`)으로 그대로 전달합니다. **API 구현을 Python 등으로 바꿔도 이 문서의 경로·형식·검사 규칙을 지키면 화면은 바뀌지 않습니다.**

### 전달 경로와 Host 규칙 (구현이 지켜야 할 것)

`GET /api/health`의 `llmConfigured`는 [모델 공급자 설정](llm-provider.md)이 유효한지 표시합니다. 로컬 호환 서버는 키 없이 활성화할 수 있고 health는 모델 서버를 호출하지 않습니다. true여도 서버 도달·인증·모델 적재 성공을 보장하지 않습니다. `POST /api/ask`의 기존 응답 필드·모델 실패 경고 코드는 유지합니다.

- API 서버(FastAPI)는 Next.js만 닿을 수 있는 곳에 둡니다. compose에서는 내부 네트워크의 `backend:8000`(호스트에 공개하지 않음), 직접 실행에서는 `127.0.0.1:8000`.
- 실제 호스트 = `X-Forwarded-Host`(Next.js 프록시가 설정) 또는 `Host`. 호스트 이름이 `127.0.0.1`·`localhost`·`HAEDAP_ALLOWED_HOSTS` 중 하나가 아니면 403 `HOST_DENIED`. 포트는 검사하지 않습니다.
- `Origin`이 있으면 `http://<실제 호스트>`(`HAEDAP_HTTPS=true`이면 `https://`)와 같아야 하고, `Sec-Fetch-Site`가 `cross-site`/`same-site`면 거부합니다(403 `ORIGIN_DENIED`).
- `X-Forwarded-For`는 로그인 시도 제한의 접속자 구분에만 씁니다(API가 내부 네트워크에만 있으므로 신뢰). 권한 판단에는 쓰지 않습니다.
- 앱 API는 `/api/{path}` 하나가 처리하고, 없는 경로는 404 `NOT_FOUND`. `MARITIME_DATA_API_TOKEN`이 있으면 `/api/maritime-data/*`가 먼저 매칭됩니다([해사 데이터 API](tools.md)).

## 2. 인증과 쓰기 보호

인증·계정 발급·비밀번호·세션·오류의 계약은 [authentication.md](authentication.md)에 정의합니다. `admin/operator/viewer` 개인 계정으로 로그인하며 업무 API는 익명 접근을 차단합니다. `health.publicAccess=false`; 초기 비밀번호 변경 전에는 업무를 사용할 수 없습니다.

- 모든 POST는 JSON + `X-Haedap-Token`(CSRF)이 필요합니다. 같은 출처·Host를 검사합니다.
- `X-Haedap-Identity`가 현재 세션 사용자와 다르면 401입니다. 서버가 저장된 역할로 권한을 결정합니다.
- 문서 범위는 검색 단계부터 원문 PDF·보고서 근거·질문 이력 재열람까지 검사합니다.
- 요청 크기: `/api/changes` 38MB, `/api/backups/import` 100MB, 그 외 POST 1MB. JSON이 아니면 415입니다.
- 기존 게스트 식별자와 소유 자료는 보존하지만 로그인 계정으로 자동 이전하지 않습니다.

## 3. 경로

| 메서드 · 경로 | 권한 | 동작 |
|---|---|---|
| GET `/api/health` | 모두 | 상태·사용자·CSRF 토큰 |
| GET `/api/skills` | 로그인 계정 | 고정 업무 스킬 목록 |
| POST `/api/skills/run` | 로그인 계정(본인 이력·문서 권한 검사) | [업무 스킬](workflow-skills.md). 입력 범위·매핑 검증 후 실행, 초안 저장은 별도 |
| POST `/api/auth/login` · `/api/auth/logout` | 모두 | 개인 계정 로그인·로그아웃 |
| POST `/api/auth/password` | 로그인 계정 | 본인 비밀번호 변경·세션 재발급 |
| GET `/api/documents` | 로그인 계정 | 허용 문서 목록·메타데이터·페이지별 본문 |
| GET `/api/documents/:id/pdf` | 로그인 계정(범위 검사) | 허용된 저장 원본 PDF |
| GET `/api/operations` | 로그인 계정 | 선박과 일별 운항 기록 |
| POST `/api/operations/validate` | 관리자 | CSV 행 검증 `{rows:[...]}` |
| POST `/api/operations/example` | 관리자 | 빈 작업공간에 가상 예시 등록 |
| POST `/api/changes` | 관리자 | `{kind, payload}` 변경 즉시 반영. 일반 사용자는 403 |
| GET `/api/changes` | 관리자 | 변경·승인 목록 (최근 200) |
| POST `/api/changes/review` | 관리자 | `{id, decision:"approve"|"reject", note}` |
| GET/POST `/api/users` | 관리자 | 계정 목록·생성·수정 |
| POST `/api/ask` | 로그인 계정 | 통합 답변 → [`integrated-answer.md`](integrated-answer.md) |
| POST `/api/search` | 로그인 계정 | 열람 범위가 적용된 검색 결과 |
| GET `/api/history` | 로그인 계정(본인) | 당시 질문·답변·근거 (최근 100) |
| GET `/api/logs` | 관리자 | 감사 로그 최근 500건 |
| GET/POST `/api/reports` | 조회: 로그인 계정 / 저장: 선원·관리자 | 보고서 목록·저장. 새 초안은 새 UUID |
| GET `/api/reports/:id` | 열람 권한 | 개별 보고서 |
| GET/POST `/api/reports/current` | 열람 권한 | 이전 공용 초안 ID 호환 경로 |
| POST `/api/reports/generate` | 선원·관리자 | `{template:"noon"|"mrv", ship, from, to}` |
| POST `/api/reports/submit` | 소유자·관리자 | `{id, version}` 검토 요청 |
| POST `/api/reports/delete` | 관리자 | `{id, version}` 저장된 보고서 삭제 |
| POST `/api/tools/calculate_emissions` | 로그인 계정 | `{fuel, factor, dwt, distance}` |
| POST `/api/tools/voyage_time` | 로그인 계정 | `{start, end, before, after}` UTC 시간 계산 |
| GET/POST `/api/backups` | 관리자 | 백업 목록 / 생성 |
| GET `/api/backups/:id` | 관리자 | 백업 파일 다운로드 |
| POST `/api/backups/import` | 관리자 | 백업 JSON 형식·체크섬 검증 후 목록에 추가 |
| POST `/api/backups/restore` | 관리자 | `{id, confirm:"복구"}`. 복구 전 자동 보관·재로그인 |
| POST `/api/backups/settings` | 관리자 | `{autoBackup:"daily"|"off"}` |

앱 JSON 백업·복구의 대상은 기존 앱 16개 테이블입니다. 해사 스키마 전체는 포함하지 않습니다. 같은 DB의 `maritime_data.vessels.ship_id`가 있으면 복구 직전 현재 연결을 보관하고, 앱 선박 교체 후 동일한 정체성이 확인되는 연결만 복원합니다. 실제 선박은 원본 7자리 IMO와 복구한 비샘플 앱 선박의 IMO가 같아야 하고, IMO가 없는 합성 선박은 이전 명시 연결의 이름·선종·DWT·IMO·sample 구분이 유지되어야 합니다. ID만 같고 식별정보가 달라진 선박은 연결하지 않습니다.

복구 응답은 `ok`, `safetyBackup`을 유지하며, 연결 컬럼이 있는 경우 `maritimeLinks={linkedBefore,restored,cleared,missingShips,identityMismatch}`를 추가합니다. 해제된 연결이 있으면 `warnings`도 반환하고 같은 건수를 감사 로그에 남깁니다. 이 응답은 현재 연결 보존 결과이며 과거 해사 데이터·연결을 복구하는 별도 백업을 대체하지 않습니다.

### 변경 `kind`

`document.save`, `document.delete`, `ship.save`, `operation.save`, `operation.import`, `operation.delete`.

- 관리자만 가능하며 한 트랜잭션에서 즉시 반영합니다. 이력 호환을 위해 `changes.status='approved'`로 기록하지만 승인 대기는 없습니다.
- 낡은 버전으로 변경하면 **409 `VERSION_CONFLICT`**. CSV 여러 행은 한 트랜잭션.
- `ship.save`에서 해사 원본과 연결된 선박의 정체성을 바꾸면 **409 `MARITIME_SHIP_IDENTITY_CONFLICT`**. 실제 선박은 원본과 동일한 IMO 및 비샘플 구분을 유지해야 하며 이름·DWT 변경은 허용합니다. 합성 선박은 기존 이름·선종·DWT·IMO·sample 구분을 유지해야 합니다. 필요한 식별정보 수정은 관리자가 연결을 수동 검토·해제한 뒤 수행하고 다시 연결합니다. 이 검사는 원본 데이터나 매핑을 자동 변경하지 않으며 연결이 없는 선박에는 기존 수정 규칙을 적용합니다.
- 보고서 검토 요청과 이전 버전의 대기 항목은 `POST /api/changes/review`로 처리합니다.

### 문서 검색 (BM25)

#### 개발자 진단 CLI 계약 (2026-10-15 확정)

`scripts/debug_bm25.py`는 HTTP API가 아닌 DB 접근 권한이 있는 개발자용 도구다. `query`, `--top-k`(기본 5), `--document-id`(개정 ID 완전 일치), `--document-title`(대소문자 무시 부분 일치), `--kind`(all/imo/manual), `--username`(활성 계정의 열람 범위 시뮬레이션), `--preview-chars`(기본 240, 0이면 본문 생략), `--json`을 받는다. 기본 사용자는 guest이며 문서 필터를 권한 검사 대신 사용하지 않는다. username 옵션은 웹 로그인 기능이 아니며 DB 자격 증명을 보유한 운영자만 사용한다.

DB의 READ ONLY 트랜잭션에서 기존 `DocumentStore.search_candidates`를 사용한다. 추가 문서 필터는 BM25 **이전**에 AND 조건으로 적용한다. 필터 후 corpus 크기·IDF가 달라지므로 필터 없는 UI 검색과 점수가 다를 수 있다. 같은 계정·kind·corpus·top-k이면 기존 `retrieve`의 순서·점수를 유지한다. 비활성 개정·상태 및 열람 불가 청크는 통계에서도 제외된다.

출력은 query 원문, 실제 확장 query_tokens, corpus_size, 역할·필터·top_k, results의 rank/chunk_id/document_id/title/page/heading/score/matched_tokens/preview다. score는 rank-bm25의 최종 합산 float이며 반올림·재계산하지 않는다. matched_tokens는 실제 질의 토큰과 **title/reference/heading/text 전체** 토큰의 교집합(질의 순서)이지 토큰별 기여도가 아니다. 작은 corpus의 0·음수 점수도 유지한다. 빈 질의/토큰/corpus/불일치는 빈 results, 잘못된 옵션·DB 오류·없는/비활성 계정은 비정상 종료한다. DB 오류의 접속 문자열·자격 증명은 출력하지 않는다. bootstrap·저장·마이그레이션·질의 이력·LLM 호출은 하지 않는다.

#### 기존 API 검색 계약

`POST /api/search`의 `{question, filter}` 및 `{evidence: [...]}`, `/api/ask`의 evidence 형식은 유지한다. 질문은 기존처럼 비어 있지 않은 최대 2,000자 문자열이며 `filter`는 `all|imo|manual`이다. `GET /api/health.retrieval`은 `hybrid-rrf` 정책을 반환한다.

- `DocumentStore.search`가 PostgreSQL에서 현재 개정(`active=true`) 청크를 읽고, 문서 상태·사용자 scope·종류 필터를 적용한 뒤에만 검색 모듈에 전달한다. 제한된 청크는 BM25 통계에도 포함하지 않는다.
- 업무 스킬의 선택 문서 검색은 `document_ids`의 활성·열람 권한을 검증하고 SQL에서 해당 ID로 후보를 제한한 뒤 같은 하이브리드 검색을 적용한다. 선택하지 않은 문서는 BM25 통계·벡터 후보에도 포함하지 않는다. CLI의 기본 전체 후보 조회도 공통 `search_candidates`를 사용한다.
- `api/rag_retrieval.py`의 `retrieve(query, chunks, top_k=5)`는 원본 청크 필드와 숫자 `score`를 가진 사본 목록을 반환한다. `DocumentStore`는 내부 점수만 제거하여 기존 API 응답을 유지한다. 문서 ID·제목·페이지·heading·본문은 변경하지 않는다.
- corpus는 `title`, `reference`, `heading`, `text`를 같은 비중으로 결합한다. Unicode NFKC 정규화·소문자화 후 한국어 구간을 Kiwi(`cong`)로 분석한다. 명사·수사·동사/형용사 어간·일반 부사·어근과 부정어 `않`을 남기고 조사·어미·접사 등을 제외한다. 인위적인 한글 2글자 분할은 하지 않는다. 영숫자와 소수·조항 번호(`0.50`, `901.1`, `5d`)는 정규식으로 보존한다. 원문·인용은 변경하지 않는다.
- `api/rag_vocabulary.py`에 Kiwi 사용자 단어(선급·평형수 등), 제한된 해사 한영 별칭(중량 갑판화물/heavy deck cargo 등), 불용어를 둔다. 질문과 corpus에 같은 토큰화·불용어 규칙을 적용한다. 부정어, 수치, 단위, 적용·기준·검사 같은 도메인 단어는 불용어에서 제외한다. 사전 별칭은 검색 보조이며 규제상 동등성을 보장하지 않는다.
- `경우`는 불용어로 제거하지 않으며 질문과 청크의 검색 토큰에 보존한다.
- 질의의 처음 30개 형태소/영숫자 토큰에 토큰 또는 연속 구 단위로 일치하는 별칭 그룹을 한 번 확장하고 중복을 제거한다. 부분 문자열 및 확장어를 다시 확장하는 연쇄 처리는 하지 않는다. corpus에는 별칭을 추가하지 않고 반복 토큰을 빈도 계산에 유지한다. 영문 stemming은 없으며 필요한 복수형은 사전에 명시한다.
- BM25Okapi 기본값(`k1=1.5`, `b=0.75`, `epsilon=0.25`)으로 계산한다. 일치 토큰이 없는 청크는 반환하지 않는다. 작은 corpus에서 0·음수 점수인 일치 청크도 반환하며 점수 내림차순, 동점은 입력 순서(DB의 문서 ID·청크 순서)를 유지한다. 점수는 확률이나 corpus 간 비교 가능한 신뢰도가 아니다.
- 검색 모듈은 빈 질의·빈 corpus·토큰 없는 corpus에 빈 목록을 반환한다. `top_k`는 양의 정수여야 한다. 외부 API의 기존 빈 질문 검증은 그대로 유지한다.
- 매 요청 허용 청크로 메모리 인덱스를 만들며 검색 변경에는 DB 재등록·재청킹이 필요 없다. Kiwi 분석기·고정 별칭과 내용 기반 문서 분석 토큰을 프로세스 내 재사용한다. 문서 토큰은 title/reference/heading/text 전체의 SHA-256을 키로 최대 2,048항목·계산 객체 크기 합 16MiB의 LRU에 보관하고 반환 시 목록을 복사한다. 원문 문자열·사용자 질의·권한·검색 결과·BM25 인덱스는 요청 간 캐시하지 않는다. 현재 DB 후보로 통계를 매번 다시 만들며 삭제·개정·권한·선택 범위 변경을 우회하지 않는다. 내용 변경·캐시 퇴출·프로세스 재시작 후 첫 분석 비용은 남는다. 어휘/분석 코드 변경 시 프로세스를 재시작한다. 토큰에도 민감한 단어가 남을 수 있고 크기 한도는 전체 RSS 상한이 아님은 [ADR 0017](../adr/0017-bounded-chunk-token-reuse.md)에 명시한다. 의미 검색·벡터 검색은 포함하지 않는다.

웹의 벡터/RRF 결합과 fallback은 별도 [계약](rag-vector.md)을 따른다. 위 토큰화·점수·캐시 설명은 BM25 구성 요소에 한정된다.

## 4. 문서 등록 payload (`document.save`)

```json
{
  "document": {
    "id": "manual-001",
    "title": "시험 매뉴얼",
    "kind": "onboard",
    "version": "1",
    "reviewedAt": "2026-09-30",
    "reference": "제1조",
    "language": "ko",
    "sections": [{"page": 7, "heading": "제1조", "text": "검토할 실제 원문을 입력합니다."}]
  },
  "expectedId": "",
  "meta": {
    "scope": "all",
    "status": "active",
    "issuer": "발행기관",
    "issuedAt": "2026-01-01",
    "revisedAt": "2026-09-01",
    "applicability": "적용 대상과 조건"
  }
}
```

| 필드 | 제약 |
|---|---|
| `document.id` | `^[a-z0-9][a-z0-9-]*$`, ≤80자 |
| `document.kind` | `onboard` · `official-summary` · `sample`. `official-summary`는 HTTPS `url` 필수 |
| `document.sections` | 1~1,500개, 절 본문 ≤20,000자, 전체 ≤2,000,000자, `page` 1~10,000 정수(선택) |
| `expectedId` | 새 문서는 `""`, 개정 시 현재 개정 ID. 다르면 409 |
| `expectedMetaRevision` | 개정·정보 수정 시 현재 `meta.revision`. 다르면 409 |
| `meta.scope` | `all` · `operator` · `admin` — 같은 논리 문서의 이전 개정본에도 적용 |
| `meta.status` | `active` · `retired` |
| `file` | 선택. `{name, base64}`, `%PDF-`로 시작, 25MB 이하 |

문서 삭제는 행을 지우지 않고 `status:'deleted'`로 검색·열람에서 제외합니다. 페이지 번호 없는 기존 자료는 `페이지 미지정`으로 표시합니다.

### 문서 정보만 수정 (2026-10-18 구현)

같은 `POST /api/changes`, `kind: "document.save"`에서 `payload.mode: "metadata"`를 사용한다. 관리자 권한·CSRF·변경 이력·트랜잭션은 기존 경로를 그대로 적용한다. 예시 payload:

```json
{
  "mode": "metadata",
  "document": {"id": "manual-001"},
  "expectedId": "manual-001-current-revision-id",
  "expectedMetaRevision": 1792281600000,
  "meta": {"issuer": "수정한 발행기관", "scope": "admin"}
}
```

- `expectedId`와 `expectedMetaRevision`은 편집을 시작할 때 조회한 실제 값으로 반드시 보낸다. 현재 개정 행을 잠근 뒤 두 값을 검사하며 불일치 시 409를 반환한다.
- `document`에는 논리 ID만 허용한다. `file`과 본문·제목·버전 등 추가 document 필드는 400으로 거부한다.
- `meta`는 `scope`, `status`, `issuer`(≤200자), `issuedAt`, `revisedAt`(빈 문자열 또는 유효한 YYYY-MM-DD), `applicability`(≤1,000자) 중 한 개 이상이다. 생략한 기존 정보와 확장 필드는 유지한다. `revision` 등 다른 키는 거부한다.
- `documents`의 ID·hash·확인일, `chunks`, `chunk_pages`, `document_files`는 수정하지 않는다. 전처리도 호출하지 않는다. 열람 범위는 기존처럼 이전 개정본에도 적용한다.
- 응답은 기존 `{id, status}`를 유지한다. 변경이 없으면 `unchanged`, 있으면 `updated`와 증가한 `meta.revision`을 다음 조회에서 확인한다.
- 정보만 수정하는 경우에도 같은 트랜잭션에서 파생 벡터 색인 작업을 요청한다. `unchanged`도 원문은 유지하면서 누락/모델 변경 색인 복구를 요청한다. 저장 실패 시 작업도 롤백된다. [자동 색인 계약](rag-index-jobs.md).
- `mode` 생략 또는 `content`는 기존 전체 문서 등록·개정 계약을 사용한다. 제목·버전·종류·조항·URL 변경은 이 경로이며 기존 개정 해시 규칙을 유지한다.

화면은 변경이 없으면 요청을 생략하고, 수정 화면에서 기본으로 정보만 수정한다. 본문·버전 개정은 새 PDF 추출 또는 원문 전체 입력이 필요하다. `GET /api/documents`의 `sections`는 검색 청크이며 편집용 원문으로 재전송하지 않는다. 별도 원문 저장소·원문 조회 API·기존 청크 재색인은 이번 변경에 포함하지 않는다.

### 화면의 페이지 본문 변환 (2026-10-18 보완)

- `frontend/src/lib/pdf.js`의 `textToSections`가 검토한 본문을 기존 `document.sections` 입력으로 변환한다. 첫 `--- PAGE n ---` 구분자 앞의 본문은 `page: null`로 보존하며 빈 본문은 제외한다. 표시된 페이지 번호와 입력 순서는 유지한다.
- 페이지별 본문이 19,000 UTF-16 코드 단위를 넘으면 문단→문장→줄→공백 경계를 우선한다. 한도 40% 이후의 경계를 우선하고, 없으면 앞쪽 공백까지 찾는다. 경계가 없는 긴 문자열은 한도 안에서 나누되 서로게이트 쌍과 CRLF는 쪼개지 않는다. 본문 양끝 공백 외에 일반적인 분할 경계의 공백·줄바꿈은 원래대로 남기며, 공백만 있는 조각은 제외한다.
- 이 분할은 기존 API 입력 길이 제한을 지키기 위한 것이다. 페이지를 서로 합치지 않으며 최종 검색 청크 생성은 아래 Python 전처리가 계속 담당한다. API 형식·백엔드·DB는 이 보완에서 변경하지 않는다. 이미 저장된 청크는 자동 변경하지 않는다.

### Python 문서 전처리 계약 (2026-10-13 확정)

현재 등록은 `POST /api/changes`의 `kind: "document.save"`이다. PDF.js가 만든 페이지별 `sections`와 선택적 `file`을 받고, `backend/api/store/documents.py`의 `DocumentStore.save_document`가 저장한다. raw PDF만 보내는 새 업로드 API는 추가하지 않는다.

`backend/api/rag_preprocessing.py`의 `preprocess_sections(sections, max_chars=900)`은 DB·웹 프레임워크에 의존하지 않고 `{page, heading, text}` 목록을 반환한다. 저장 시 기존 개정 ID와 순서로 청크 ID를 만들며 제목은 `documents`와 조인하여 반환한다.

- 페이지와 입력 절을 넘겨 본문을 합치지 않는다. 물리 페이지 번호 또는 기존 NULL을 유지한다.
- 줄바꿈/비분리 공백을 정리하되 조항 번호·숫자·기호와 표의 내부 공백·줄은 보존한다. OCR·수식 복원·단어 하이픈 결합은 하지 않는다.
- 명시적인 Part/Chapter/Section 머리말과 ABS 규정 꼬리말이 3개 이상 서로 다른 페이지 가장자리에서 반복될 때만 제거한다. 제거한 머리말 중 가장 구체적인 절 제목은 `heading`에 보존한다. 본문 중간의 같은 문구와 조항 제목은 보존한다.
- 번호 있는 짧은 조항 제목과 TABLE/FIGURE 제목은 별도 블록을 시작하고 `heading`에 반영한다. 긴 블록은 문단→문장→줄→공백 경계 순으로 최대 길이 안에서 나눈다. 표 블록은 문장보다 줄 경계를 우선한다. 경계가 없는 긴 문자열만 강제 분할한다.
- 2026-10-22: 점선+쪽번호 형태가 3개 이상이거나 명시적 CONTENTS/목차 표제와 점선 항목이 함께 있는 입력 절은 목차로 취급한다. 이어진 제목 줄·분리된 쪽번호를 항목 단위로 묶어 가능한 한 같은 청크에 넣고 본문 heading으로 승격하지 않는다. 900자를 넘는 단일 항목은 길이 제한을 우선한다. 점선 없는 목차·본문과 혼합된 목차 판별은 제한적이다.
- 본문에서 설명 없이 연속된 짧은 상위·하위 제목은 뒤 설명 블록에 함께 넣고 heading에 두 제목을 보존한다(누적 제목이 청크 한도의 40% 미만일 때). 페이지 끝에 제목만 있고 설명이 다음 페이지에 있거나 제목 자체가 매우 긴 경우에는 페이지·길이 제한을 우선하므로 짧은 청크가 남을 수 있다.
- 기존 문서 hash와 `unchanged` 판정을 유지한다. 이미 등록된 동일 문서/재활성화된 이전 개정본의 청크는 다시 쓰지 않는다. 변경된 청킹은 새 문서·새 내용의 개정부터 적용된다. 기존 청크를 바꾸는 재색인은 별도 작업이다.
- 새 개정본은 전처리를 한 번 수행하고, 결과가 0개면 400 `INVALID_INPUT`으로 거부한다. 이전 개정본의 활성 상태를 바꾸기 전에 검사한다. 기존 동일 해시·과거 개정본의 청크는 재검사·재생성하지 않는다.
- API 응답·PostgreSQL 테이블·열람 범위·인용 검증은 그대로 유지한다. 현재 검색은 위 BM25 계약을 따른다.

CLI 일괄 수집 명령은 제거되었습니다(Node 버전의 `npm run ingest`). 빈 DB의 첫 요청 때 `backend/knowledge/seed.json`(위 `document` 객체 배열)이 자동 등록됩니다.

## 5. 오류 형식

검증 실패는 `AppError(status, code, message)`로 던지고 다음 형식으로 응답합니다. 로그인한 사용자의 실패는 감사 로그(`category:'error'`)에도 남습니다.

```json
{"error": {"code": "VERSION_CONFLICT", "message": "운항 기록이 변경되었습니다. 다시 열어 주세요."}}
```

주요 코드: `LOGIN_FAILED`(401), `FORBIDDEN`(403), `NOT_FOUND`(404), `TOOL_NOT_FOUND`(404), `VERSION_CONFLICT`(409), `MARITIME_SHIP_IDENTITY_CONFLICT`(409), `SETUP_DISABLED`(410), `CONTENT_TYPE`(415), `ANOMALY`(운항 연료 급증 사유 누락). 메시지는 사용자에게 그대로 보여 줄 한국어 문장입니다.

해사 데이터 적재·연결 작업과 복구의 테이블 잠금이 충돌하면 최대 5초 대기 후 **409 BUSY**를 반환합니다. 복구 트랜잭션은 롤백되어 앱 데이터와 해사 연결을 변경하지 않으며, 작업이 끝난 후 복구를 다시 시도할 수 있습니다.

## 6. 한계

- 백업은 SHA-256 체크섬으로 우발적 손상만 검사하며, 서명 기반 진위 확인은 하지 않습니다. 가져오기는 형식 v2만 허용합니다.
- 목록 API는 페이징 없이 전체를 반환합니다(캡스톤 데모 규모).
## 웹 하이브리드 검색 (응답 필드 유지)

웹은 BM25·벡터 후보를 RRF로 결합한다. `/search`와 답변 흐름의 evidence 필드/최종 Top-5는 유지한다.
`health.retrieval`은 `hybrid-rrf` 정책이며 모델·색인의 준비 보증이 아니다.
준비 실패 시 BM25 fallback하며 안전한 서버 경고/개발자 CLI에 표시한다. 방식별 비교는 개발자 CLI에서 수행한다.
구체적인 준비·권한·색인 누락·RRF 동작은 [rag-vector.md](rag-vector.md)를 따른다.

### 보고서 삭제 (2026-10-18)

`POST /api/reports/delete`는 관리자만 호출한다. `{id: string, version: 양의 정수}`를 받고 `{ok: true, id}`를 반환한다. 모든 POST의 기존 CSRF·사용자 식별·복구 중 요청 차단을 적용한다.

- 보고서 행을 잠그고, 없으면 404 `NOT_FOUND`, 버전이 바뀌었으면 409 `VERSION_CONFLICT`로 거부한다.
- 작성 중·검토 중·승인됨 상태 모두 관리자가 삭제할 수 있다. `report_meta`와 `reports`의 해당 행을 같은 트랜잭션에서 삭제한다. DB 스키마 변경은 없다.
- 해당 보고서의 대기 중 검토 요청은 기존 `rejected` 상태와 ‘보고서 삭제로 검토 요청 종료’ 사유로 마감한다. 기존 승인·반려 이력과 근거 문서·운항 기록은 보존하며 감사 로그에 보고서 삭제를 남긴다.
- 검토 승인·반려도 같은 보고서 행을 먼저 잠그고 대기 상태를 다시 확인하여 삭제와 경합할 때 이미 종료된 요청을 처리하지 않는다.
- 화면은 삭제 성공 후 해당 보고서의 임시 초안을 비우고 목록으로 이동한다. 실패 시 편집 내용과 오류 안내를 유지한다.
