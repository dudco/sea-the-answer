# 서버와 팀 모듈 연결 — 1.2.2

업데이트: 2026-09-30. 실행·업무 안내는 상위 `README.md`를 기준으로 합니다.

## 현재 구성

브라우저 ES 모듈 → `ui/api.js` → Node HTTP API → SQLite입니다. UI 메뉴는 통합 질문, 문서, 운항 정보, 보고서, 관리입니다. Next.js, PostgreSQL, ChromaDB, Python Tool, Local LLM으로 이전하는 작업은 포함하지 않습니다.

기존 테이블 `documents/chunks/chunks_fts/reports/tool_runs/queries`는 그대로 유지합니다. 새로 `users/document_meta/document_files/chunk_pages/ships/operations/report_meta/audit/query_owner/changes/settings`를 추가합니다. PDF 원본은 Base64 형태로 SQLite에 저장합니다. 향후 대용량 문서 환경에서는 별도 파일 저장소와 스트리밍 처리가 적합합니다.

`backend/workspace.mjs`는 사용자·변경·승인·보고서 메타데이터·백업을, `backend/analysis.mjs`는 운항 집계와 통합 응답을 담당합니다. 금융·법규 전문 계산 엔진은 아닙니다.

## 인증과 쓰기 보호

- `GET /api/health`: 연결 상태, 현재 관리자 또는 일반 사용자(`role:guest`), `authenticated`, `publicAccess:true`, CSRF 토큰. `setupRequired:false`. 일반 접근에도 공개 문서 수를 반환합니다.
- 시작 시 기본 관리자 `admin / 1234`를 자동 설정합니다. 기존 사용자 ID와 자료 소유권을 유지하는 일회성 이전이며 `settings.publicAccessV1`로 표시합니다. 기본 계정은 사용자 변경 API에서 고정합니다.
- `POST /api/auth/setup`: 사용하지 않으며 410을 반환합니다. 최초 계정 입력 과정이 없습니다.
- `POST /api/auth/login`, `/api/auth/logout`: 관리자만 로그인. HttpOnly, SameSite=Strict 세션 쿠키를 발급·폐기합니다. 비밀번호는 salt+scrypt로 저장합니다. 기본 관리자만 요청된 4자리 비밀번호를 사용하며 추가 관리자 비밀번호는 10자 이상입니다.
- 일반 사용자는 32바이트 난수 `haedap_guest` 쿠키로 구분합니다. DB 소유자 ID는 `guest_` + 쿠키 SHA-256이며 쿠키는 HttpOnly/SameSite=Strict, 최대 1년입니다. 관리자 로그인·로그아웃과 서버 재시작 후에도 같은 식별자를 유지합니다. 쿠키가 없으면 새 일반 사용자이며, 실제 사람의 인증 수단은 아닙니다.
- UI 요청의 `X-Haedap-Identity`가 현재 쿠키의 사용자와 다르면 401을 반환해 다른 탭·세션 만료로 바뀐 상태에서 이전 사용자의 내용이 저장되는 일을 막습니다. 권한 부여는 이 헤더가 아니라 서버의 사용자·역할 검사로 합니다.
- 세션 12시간, 로그인 실패 횟수 제한, 계정 버전 변경 시 기존 세션 무효화. 서버 재시작·전체 복구는 재로그인 필요.
- 모든 POST는 JSON과 `X-Haedap-Token`이 필요합니다. 같은 출처·Host·LAN 범위 검사도 유지합니다.
- `admin`: 승인·사용자·백업·전체 로그. `guest`: 공개 문서·운항 조회, 질문·계산, 자기 초안 작성·저장·검토 요청. 이전 `operator/viewer` 레코드는 보존하지만 이 계정의 로그인은 허용하지 않습니다.
- 제한 문서는 검색 입력 단계부터 제외합니다. 원본 PDF, 이전 버전, 보고서 근거, 질문 이력 재열람에도 문서 범위를 검사합니다.

## API

| 경로 | 동작 |
|---|---|
| GET `/api/documents` | 허용 문서 목록·메타데이터·페이지별 본문 |
| GET `/api/documents/:id/pdf` | 허용된 저장 원본 PDF |
| GET `/api/operations` | 저장 선박과 일별 운항 기록 |
| POST `/api/operations/validate` | 관리자 전용 CSV 행 검증. `{rows:[...]}` |
| POST `/api/operations/example` | 빈 작업공간에 명시적으로 가상 예시 등록, 관리자 전용 |
| POST `/api/changes` | 관리자 전용 `{kind,payload}` 변경 즉시 반영. 일반 사용자는 403 |
| GET `/api/changes` | 관리자 승인 목록 |
| POST `/api/changes/review` | `{id,decision:"approve" 또는 "reject",note}` |
| GET/POST `/api/users` | 관리자 계정 목록·생성·수정 |
| POST `/api/ask` | 근거+운항 데이터+기준 비교 통합 결과 |
| POST `/api/search` | 열람 범위가 적용된 검색 결과 |
| GET `/api/history` | 현재 사용자의 당시 질문·답변·근거 |
| GET `/api/logs` | 관리자 로그 최근 500건 |
| GET/POST `/api/reports` | 보고서 목록·저장. 새 초안은 새 UUID |
| GET `/api/reports/:id` | 개별 보고서 |
| GET/POST `/api/reports/current` | 이전 공용 초안 ID 호환 경로. 인증·권한 적용 |
| POST `/api/reports/generate` | `{template:"noon" 또는 "mrv",ship,from,to}` |
| POST `/api/reports/submit` | `{id,version}` 검토 요청 |
| POST `/api/tools/calculate_emissions` | `{fuel,factor,dwt,distance}` |
| POST `/api/tools/voyage_time` | `{start,end,before,after}` UTC 시간 계산 |
| GET/POST `/api/backups` | 전체 백업 목록 / 생성 |
| GET `/api/backups/:id` | 백업 파일 다운로드 |
| POST `/api/backups/import` | 전체 백업 JSON 형식·체크섬 검증 후 목록에 추가 |
| POST `/api/backups/restore` | `{id,confirm:"복구"}`. 복구 전 자동 보관·재로그인 |
| POST `/api/backups/settings` | `{autoBackup:"daily" 또는 "off"}` |

변경 `kind`: `document.save`, `document.delete`, `ship.save`, `operation.save`, `operation.import`, `operation.delete`.

문서·선박·운항 자료의 변경은 관리자만 가능하며 한 트랜잭션에서 즉시 반영합니다. 이력 호환을 위해 완료된 변경의 `status`는 `approved`로 기록하지만 별도의 승인 요청이나 대기는 없습니다. 일반 사용자의 직접 변경·CSV 검증 요청은 403이며 승인 대기 항목도 생성하지 않습니다. 문서·기록·보고서의 낡은 버전으로 변경하면 409입니다. CSV 여러 행은 하나의 트랜잭션으로 반영합니다. 일반 사용자의 질문·수치 계산·자기 초안 저장 및 보고서 검토 요청은 유지합니다. 보고서 검토 요청과 이전 버전에서 생성한 대기 항목은 기존 검토 API로 처리합니다.

## 문서 계약

문서 등록 payload:

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

새 문서는 `expectedId:""`, 개정 시 현재 revision ID와 `expectedMetaRevision`을 사용합니다. PDF를 포함하면 `file:{name,base64}`를 추가합니다. `kind`는 `onboard/official-summary/sample`, `scope`는 `all/operator/admin`, `status`는 `active/retired`입니다. 공식 안내 요약에는 HTTPS 원문 URL이 필요합니다.

권한 변경은 같은 논리 문서의 이전 버전에도 적용합니다. 문서 삭제는 검색·열람 제외로 처리하여 기록과 복구 가능성을 보존합니다. 페이지 번호 없는 기존 자료는 `페이지 미지정`으로 정직하게 표시합니다.

## 통합 답변을 팀 Agent로 교체할 때

UI의 입력 형태:

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

현재 `auto`는 단어 규칙 기반이며 UI에서 작업을 명시할 수 있습니다. 임의의 질문에서 선박·기간·규정을 해석하는 범용 Agent는 아닙니다. 팀의 의도 분류·RAG·Tool 호출 결과를 아래 형태로 맞추면 화면은 재사용할 수 있습니다.

- `question, language, generation, status, notice, warnings`
- `statements:[{text,chunkId,quote}]`
- `evidence:[{id,document_id,title,version,reference,heading,text,page,meta}]`
- `toolRuns:[]`
- `operations:{ship,from,to,rows,count,fuel,emission,distance,speed,intensity,sample,cii}`
- `compliance:{status:"met"|"unmet"|"unknown",label,actual,limit,rule,reason}`
- `reportSuggested:boolean`

CII 표시 계약은 `cii:{status:"available",value,unit,rating,year,method}` 또는 `cii:{status:"unavailable",reason}`입니다. 현재 기본 서버는 항상 공식 CII에 대해 `unavailable`을 반환합니다. **값이나 등급을 임의로 만들어 넣지 마세요.** 입력값·산식·선종·연도·검증된 기준을 전문 모듈에서 확보해야 합니다.

현재 기준 비교는 사용자가 직접 확인한 근거 구절과 수치를 비교합니다. `criterion`은 `documentId,chunkId,quote,metric,operator,limit,confirmed`를 받습니다. 원문 구절 포함 여부·문서 권한·현재 적용 버전을 확인합니다. 수치 기준의 규정상 의미·선박 적용 여부는 사용자의 검토를 전제로 하며 LLM이 자동 인증하지 않습니다.

브라우저의 입력·상태·결과 UI를 유지한 채 `backend/analysis.mjs`, `backend/rag.mjs`, `ui/api.js` 경계를 교체하면 됩니다. 인증과 인용 권한 검사를 우회하지 마세요.

## 백업과 한계

백업 JSON은 명시한 테이블과 원본 PDF를 포함하며 API 키는 포함하지 않습니다. SHA-256 체크섬으로 우발적 손상을 검사합니다. 서명된 외부 백업의 진위를 보장하는 기능은 아닙니다. 가져온 백업은 형식 v2만 허용합니다. 복구 시 FTS를 재구축하고 SQL 트랜잭션 실패는 되돌립니다. 이전 백업에도 기본 관리자 이전을 적용하고 관리자 세션을 해제합니다. 일반 식별 쿠키는 유지합니다. 자동 백업은 서버 실행 중 UTC 날짜 기준 하루 한 번입니다.

지금 규모의 캡스톤 데모에 맞춰 문서·운항·보고서 목록을 메모리에 읽습니다. 대규모 실운항 배포에는 페이징, 파일 저장소, TLS, 로그 보존 정책 등 별도 운영 설계가 필요합니다.
