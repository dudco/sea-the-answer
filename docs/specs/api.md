# HTTP API

- 상태: 구현됨 (1.4.0)
- 최종 확인: 2026-10-13 (`backend/api/` 대조)
- 관련: [`../architecture.md`](../architecture.md), [`../data-model.md`](../data-model.md), [`integrated-answer.md`](integrated-answer.md), [ADR 0004](../adr/0004-public-access-admin-only-writes.md)

## 1. 목적

화면(`frontend/src/lib/api.js`)과 팀 모듈이 사용하는 로컬 HTTP API의 계약입니다. 브라우저는 Next.js 공개 주소(`http://<host>:5173/api/...`)로 호출하고, Next.js가 `HAEDAP_API_ORIGIN`(기본 `http://127.0.0.1:8000`)으로 그대로 전달합니다. **API 구현을 Python 등으로 바꿔도 이 문서의 경로·형식·검사 규칙을 지키면 화면은 바뀌지 않습니다.**

### 전달 경로와 Host 규칙 (구현이 지켜야 할 것)

`GET /api/health`의 `llmConfigured`는 [모델 공급자 설정](llm-provider.md)이 유효한지 표시합니다. 로컬 호환 서버는 키 없이 활성화할 수 있고 health는 모델 서버를 호출하지 않습니다. true여도 서버 도달·인증·모델 적재 성공을 보장하지 않습니다. `POST /api/ask`의 기존 응답 필드·모델 실패 경고 코드는 유지합니다.

- API 서버(FastAPI)는 Next.js만 닿을 수 있는 곳에 둡니다. compose에서는 내부 네트워크의 `backend:8000`(호스트에 공개하지 않음), 직접 실행에서는 `127.0.0.1:8000`.
- 실제 호스트 = `X-Forwarded-Host`(Next.js 프록시가 설정) 또는 `Host`. 호스트 이름이 `127.0.0.1`·`localhost`·`HAEDAP_ALLOWED_HOSTS` 중 하나가 아니면 403 `HOST_DENIED`. 포트는 검사하지 않습니다.
- `Origin`이 있으면 `http://<실제 호스트>`와 같아야 하고, `Sec-Fetch-Site`가 `cross-site`/`same-site`면 거부합니다(403 `ORIGIN_DENIED`).
- `X-Forwarded-For`는 로그인 시도 제한의 접속자 구분에만 씁니다(API가 내부 네트워크에만 있으므로 신뢰). 권한 판단에는 쓰지 않습니다.
- 앱 API는 `/api/{path}` 하나가 처리하고, 없는 경로는 404 `NOT_FOUND`. `MARITIME_DATA_API_TOKEN`이 있으면 `/api/maritime-data/*`가 먼저 매칭됩니다([해사 데이터 API](tools.md)).

## 2. 인증과 쓰기 보호

- `GET /api/health`: 연결 상태, 현재 사용자(관리자 또는 `role:guest`), `authenticated`, `publicAccess:true`, CSRF 토큰, `setupRequired:false`, 공개 문서 수.
- 시작 시 기본 관리자 `admin / 1234`를 자동 설정합니다(일회성 이전, `settings.publicAccessV1`). 기본 계정은 사용자 변경 API에서 고정입니다.
- `POST /api/auth/setup`: 사용하지 않으며 **410**.
- `POST /api/auth/login`, `POST /api/auth/logout`: 관리자만 로그인. `haedap_session` 쿠키(HttpOnly, SameSite=Strict) 발급·폐기. 비밀번호는 salt + scrypt. 기본 관리자만 4자리 비밀번호, 추가 관리자는 10자 이상.
- 일반 사용자: 32바이트 난수 `haedap_guest` 쿠키(HttpOnly, SameSite=Strict, 최대 1년). DB 소유자 ID는 `guest_` + 쿠키 SHA-256. 인증 수단이 아니라 작업공간 구분용입니다.
- 요청 헤더 `X-Haedap-Identity`가 현재 쿠키의 사용자와 다르면 **401** — 다른 탭·세션 만료로 사용자가 바뀐 상태에서 이전 사용자의 내용이 저장되는 것을 막습니다. 권한 부여는 이 헤더가 아니라 서버의 역할 검사로 합니다.
- 세션 12시간, 로그인 실패 횟수 제한, 계정 `version` 변경 시 기존 세션 무효화. 서버 재시작·전체 복구 후 재로그인.
- **모든 POST**: `Content-Type: application/json` + `X-Haedap-Token`(CSRF) 필요. 같은 출처·Host 검사.
- 역할: `admin` — 승인·사용자·백업·전체 로그·원본 자료 변경. `guest` — 공개 문서·운항 조회, 질문·계산, 자기 초안 작성·저장·검토 요청. 이전 `operator`/`viewer` 레코드는 보존하지만 로그인 불가.
- 제한 문서는 검색 입력 단계부터 제외하고, 원본 PDF·이전 버전·보고서 근거·질문 이력 재열람에도 범위를 검사합니다.
- 본문 크기 제한: `/api/changes` 38MB(PDF 포함 문서 등록), `/api/backups/import` 100MB, 그 외 POST 1MB. JSON이 아니면 **415 `CONTENT_TYPE`**. Next.js 프록시 한도는 101MB, 응답 대기는 60초입니다.

## 3. 경로

| 메서드 · 경로 | 권한 | 동작 |
|---|---|---|
| GET `/api/health` | 모두 | 상태·사용자·CSRF 토큰 |
| POST `/api/auth/login` · `/api/auth/logout` | 모두 | 관리자 로그인·로그아웃 |
| GET `/api/documents` | 모두 | 허용 문서 목록·메타데이터·페이지별 본문 |
| GET `/api/documents/:id/pdf` | 모두(범위 검사) | 허용된 저장 원본 PDF |
| GET `/api/operations` | 모두 | 선박과 일별 운항 기록 |
| POST `/api/operations/validate` | 관리자 | CSV 행 검증 `{rows:[...]}` |
| POST `/api/operations/example` | 관리자 | 빈 작업공간에 가상 예시 등록 |
| POST `/api/changes` | 관리자 | `{kind, payload}` 변경 즉시 반영. 일반 사용자는 403 |
| GET `/api/changes` | 관리자 | 변경·승인 목록 (최근 200) |
| POST `/api/changes/review` | 관리자 | `{id, decision:"approve"|"reject", note}` |
| GET/POST `/api/users` | 관리자 | 계정 목록·생성·수정 |
| POST `/api/ask` | 모두 | 통합 답변 → [`integrated-answer.md`](integrated-answer.md) |
| POST `/api/search` | 모두 | 열람 범위가 적용된 검색 결과 |
| GET `/api/history` | 모두(본인) | 당시 질문·답변·근거 (최근 100) |
| GET `/api/logs` | 관리자 | 감사 로그 최근 500건 |
| GET/POST `/api/reports` | 모두 | 보고서 목록·저장. 새 초안은 새 UUID |
| GET `/api/reports/:id` | 열람 권한 | 개별 보고서 |
| GET/POST `/api/reports/current` | 열람 권한 | 이전 공용 초안 ID 호환 경로 |
| POST `/api/reports/generate` | 모두 | `{template:"noon"|"mrv", ship, from, to}` |
| POST `/api/reports/submit` | 소유자·관리자 | `{id, version}` 검토 요청 |
| POST `/api/tools/calculate_emissions` | 모두 | `{fuel, factor, dwt, distance}` |
| POST `/api/tools/voyage_time` | 모두 | `{start, end, before, after}` UTC 시간 계산 |
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

2026-10-14 확정: `POST /api/search`의 `{question, filter}` 및 `{evidence: [...]}`, `/api/ask`의 evidence 형식은 유지한다. 질문은 기존처럼 비어 있지 않은 최대 2,000자 문자열이며 `filter`는 `all|imo|manual`이다. `GET /api/health.retrieval`은 `bm25-ko-en`을 반환한다.

- `DocumentStore.search`가 PostgreSQL에서 현재 개정(`active=true`) 청크를 읽고, 문서 상태·사용자 scope·종류 필터를 적용한 뒤에만 검색 모듈에 전달한다. 제한된 청크는 BM25 통계에도 포함하지 않는다.
- `api/rag_retrieval.py`의 `retrieve(query, chunks, top_k=5)`는 원본 청크 필드와 숫자 `score`를 가진 사본 목록을 반환한다. `DocumentStore`는 내부 점수만 제거하여 기존 API 응답을 유지한다. 문서 ID·제목·페이지·heading·본문은 변경하지 않는다.
- corpus는 `title`, `reference`, `heading`, `text`를 같은 비중으로 결합한다. Unicode NFKC 정규화·소문자화 후 기존 정규식의 2자 이상 영숫자·한글 단어를 추출하고 한글 3자 이상 단어에는 겹치는 2글자 토큰을 추가한다. 원문은 정규화하지 않고 검색용 사본에만 적용한다.
- 질의의 서로 다른 기본 단어는 최대 30개이며 기존 한영 동의어를 확장한다. 단어와 확장어 모두 동일하게 토큰화하고 질의 토큰을 중복 제거한다. corpus의 반복 토큰은 BM25 빈도 계산을 위해 유지한다.
- BM25Okapi 기본값(`k1=1.5`, `b=0.75`, `epsilon=0.25`)으로 계산한다. 일치 토큰이 없는 청크는 반환하지 않는다. 작은 corpus에서 0·음수 점수인 일치 청크도 반환하며 점수 내림차순, 동점은 입력 순서(DB의 문서 ID·청크 순서)를 유지한다. 점수는 확률이나 corpus 간 비교 가능한 신뢰도가 아니다.
- 검색 모듈은 빈 질의·빈 corpus·토큰 없는 corpus에 빈 목록을 반환한다. `top_k`는 양의 정수여야 한다. 외부 API의 기존 빈 질문 검증은 그대로 유지한다.
- 매 요청 허용 청크로 메모리 인덱스를 만들며 DB 재등록·재청킹은 필요 없다. 형태소 분석·영문 stemming·의미 검색·벡터 검색은 포함하지 않는다.

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

### Python 문서 전처리 계약 (2026-10-13 확정)

현재 등록은 `POST /api/changes`의 `kind: "document.save"`이다. PDF.js가 만든 페이지별 `sections`와 선택적 `file`을 받고, `backend/api/store/documents.py`의 `DocumentStore.save_document`가 저장한다. raw PDF만 보내는 새 업로드 API는 추가하지 않는다.

`backend/api/rag_preprocessing.py`의 `preprocess_sections(sections, max_chars=900)`은 DB·웹 프레임워크에 의존하지 않고 `{page, heading, text}` 목록을 반환한다. 저장 시 기존 개정 ID와 순서로 청크 ID를 만들며 제목은 `documents`와 조인하여 반환한다.

- 페이지와 입력 절을 넘겨 본문을 합치지 않는다. 물리 페이지 번호 또는 기존 NULL을 유지한다.
- 줄바꿈/비분리 공백을 정리하되 조항 번호·숫자·기호와 표의 내부 공백·줄은 보존한다. OCR·수식 복원·단어 하이픈 결합은 하지 않는다.
- 명시적인 Part/Chapter/Section 머리말과 ABS 규정 꼬리말이 3개 이상 서로 다른 페이지 가장자리에서 반복될 때만 제거한다. 제거한 머리말 중 가장 구체적인 절 제목은 `heading`에 보존한다. 본문 중간의 같은 문구와 조항 제목은 보존한다.
- 번호 있는 짧은 조항 제목과 TABLE/FIGURE 제목은 별도 블록을 시작하고 `heading`에 반영한다. 긴 블록은 문단→문장→줄→공백 경계 순으로 최대 길이 안에서 나눈다. 표 블록은 문장보다 줄 경계를 우선한다. 경계가 없는 긴 문자열만 강제 분할한다.
- 기존 문서 hash와 `unchanged` 판정을 유지한다. 이미 등록된 동일 문서/재활성화된 이전 개정본의 청크는 다시 쓰지 않는다. 변경된 청킹은 새 문서·새 내용의 개정부터 적용된다. 기존 청크를 바꾸는 재색인은 별도 작업이다.
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
