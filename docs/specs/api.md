# HTTP API

- 상태: 구현됨 (1.3.1)
- 최종 확인: 2026-10-08
- 관련: [`../architecture.md`](../architecture.md), [`../data-model.md`](../data-model.md), [`integrated-answer.md`](integrated-answer.md), [ADR 0004](../adr/0004-public-access-admin-only-writes.md)

## 1. 목적

화면(`frontend/src/lib/api.js`)과 팀 모듈이 사용하는 로컬 Node HTTP API의 계약입니다. 모든 경로는 게이트웨이와 같은 출처(`http://<host>:<port>/api/...`)에서 제공됩니다.

## 2. 인증과 쓰기 보호

- `GET /api/health`: 연결 상태, 현재 사용자(관리자 또는 `role:guest`), `authenticated`, `publicAccess:true`, CSRF 토큰, `setupRequired:false`, 공개 문서 수.
- 시작 시 기본 관리자 `admin / 1234`를 자동 설정합니다(일회성 이전, `settings.publicAccessV1`). 기본 계정은 사용자 변경 API에서 고정입니다.
- `POST /api/auth/setup`: 사용하지 않으며 **410**.
- `POST /api/auth/login`, `POST /api/auth/logout`: 관리자만 로그인. `haedap_session` 쿠키(HttpOnly, SameSite=Strict) 발급·폐기. 비밀번호는 salt + scrypt. 기본 관리자만 4자리 비밀번호, 추가 관리자는 10자 이상.
- 일반 사용자: 32바이트 난수 `haedap_guest` 쿠키(HttpOnly, SameSite=Strict, 최대 1년). DB 소유자 ID는 `guest_` + 쿠키 SHA-256. 인증 수단이 아니라 작업공간 구분용입니다.
- 요청 헤더 `X-Haedap-Identity`가 현재 쿠키의 사용자와 다르면 **401** — 다른 탭·세션 만료로 사용자가 바뀐 상태에서 이전 사용자의 내용이 저장되는 것을 막습니다. 권한 부여는 이 헤더가 아니라 서버의 역할 검사로 합니다.
- 세션 12시간, 로그인 실패 횟수 제한, 계정 `version` 변경 시 기존 세션 무효화. 서버 재시작·전체 복구 후 재로그인.
- **모든 POST**: `Content-Type: application/json` + `X-Haedap-Token`(CSRF) 필요. 같은 출처·Host·LAN 범위 검사.
- 역할: `admin` — 승인·사용자·백업·전체 로그·원본 자료 변경. `guest` — 공개 문서·운항 조회, 질문·계산, 자기 초안 작성·저장·검토 요청. 이전 `operator`/`viewer` 레코드는 보존하지만 로그인 불가.
- 제한 문서는 검색 입력 단계부터 제외하고, 원본 PDF·이전 버전·보고서 근거·질문 이력 재열람에도 범위를 검사합니다.
- 본문 크기 제한: `/api/changes` 38MB(PDF 포함 문서 등록), `/api/backups/import` 100MB, 그 외 POST 1MB. JSON이 아니면 **415 `CONTENT_TYPE`**.

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

### 변경 `kind`

`document.save`, `document.delete`, `ship.save`, `operation.save`, `operation.import`, `operation.delete`.

- 관리자만 가능하며 한 트랜잭션에서 즉시 반영합니다. 이력 호환을 위해 `changes.status='approved'`로 기록하지만 승인 대기는 없습니다.
- 낡은 버전으로 변경하면 **409 `VERSION_CONFLICT`**. CSV 여러 행은 한 트랜잭션.
- 보고서 검토 요청과 이전 버전의 대기 항목은 `POST /api/changes/review`로 처리합니다.

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

CLI 수집(`npm run ingest -- <file>`)은 위 `document` 객체의 배열(1~100개)을 받습니다. 예시: `backend/knowledge/seed.json`.

## 5. 오류 형식

검증 실패는 `AppError(status, code, message)`로 던지고 다음 형식으로 응답합니다. 로그인한 사용자의 실패는 감사 로그(`category:'error'`)에도 남습니다.

```json
{"error": {"code": "VERSION_CONFLICT", "message": "운항 기록이 변경되었습니다. 다시 열어 주세요."}}
```

주요 코드: `LOGIN_FAILED`(401), `FORBIDDEN`(403), `NOT_FOUND`(404), `TOOL_NOT_FOUND`(404), `VERSION_CONFLICT`(409), `SETUP_DISABLED`(410), `CONTENT_TYPE`(415), `ANOMALY`(운항 연료 급증 사유 누락). 메시지는 사용자에게 그대로 보여 줄 한국어 문장입니다.

## 6. 한계

- 백업은 SHA-256 체크섬으로 우발적 손상만 검사하며, 서명 기반 진위 확인은 하지 않습니다. 가져오기는 형식 v2만 허용합니다.
- 목록 API는 페이징 없이 전체를 반환합니다(캡스톤 데모 규모).
