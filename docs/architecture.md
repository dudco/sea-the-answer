# 아키텍처

## 관리자 운항 자료 가져오기 (2026-11-06)

기존 CSV 버튼의 `OperationImport`가 관리자 세션/CSRF로 파일을 나눠 전송한다. `api/operation_uploads.py`는 소유자·크기·TTL·순서·미리보기 해시를 관리한다. `tools/operation_import.py`는 알려진 CSV/준비 ZIP·JSON을 판별하고 기존 테이블의 고정 열·FK·출처·실제/가상 경계를 검증한다. 미리보기는 savepoint에서 실제 제약을 검사한 뒤 롤백하며 등록은 단일 DB 트랜잭션이다. 같은 키의 다른 행은 거절하고 같은 행은 보존한다. 임의 경로·DDL·실행 파일·SQL·LLM 도구는 공개하지 않는다.

순수 준비 필드 계약은 `tools/data_contract.py`, 후보 검증은 `tools/capacity_data.py`를 오프라인 scripts와 공유한다. 전처리·원시 파일 다운로드는 계속 scripts의 별도 작업이다. 런타임은 scripts나 pandas/openpyxl에 의존하지 않는다. 참조 JSON은 DB 등록과 별도 단계로 관리자 저장 위치에 원자 설치하고 이전 파일을 보존한다. 기본 참조 경로는 웹 관리 저장소이며 서버 지정 환경변수 경로가 우선한다. Docker는 `maritime-imports` 볼륨을 별도로 유지한다. [상세 계약](specs/operation-data-import.md).

## 자연어 업무 실행 (2026-11-06)

`routes/documents.ask`는 `question_router`를 통해 자료 현황 → 기존 항구/업무·대화 경로 → 명시 문서 설명 → 선택적 의미 분류 순으로 기존 기능에 연결한다. `dataset_intent`는 자료 이름·유무/출처 요청을 정의·계산·변경 요청과 구분하며, `dataset_status`는 실제 DB·참조 파일·현재 계정 문서에서 등록 현황을 읽는다. 규칙 경로가 놓친 AI 모드 질문에는 설정된 모델이 폐쇄형 action 하나만 제안한다(12초·32토큰 제한). 서버가 내부 route/dataset으로 변환한다. 실패·모호함·지원 밖 의도는 조건 확인으로 안내한다. 기존 원문 발췌의 일반 문서 질문은 유지한다.

`question_intent`는 날짜·작업 규칙을, `question_workflows`는 기존 `workflow_skills.operation_result`, `reference_intensity.calculate_reference`, 선택 문서 실행을 담당한다. 의미 분류 결과도 기존 실행기의 선박·날짜·매핑·권한 검증을 통과해야 하며 두 번의 모델 계획을 연달아 호출하지 않는다. 모델에 SQL·선박 ID·날짜·숫자 결과를 맡기는 범용 실행 경로는 없다.

현재 소유자의 지정 부모 응답만 후속 범위로 검증하고, 결과는 기존 queries/query_owner와 감사 기록에 저장한다. 매 요청 현재 도구를 다시 실행하며 반환 전 인증·선박 버전·매핑·문서 권한을 재확인한다. 브라우저의 기존 질문 화면은 `QuestionWorkflow`로 해석 범위·현재 필요한 후보·여러 도구 결과·산술 비교를 표시하고 새 질문 뒤 늦은 응답을 버린다. 운항 표·차트는 질문으로 확인한 한 선박·한 기간의 동일 DB 조회 결과를 집계와 표시 투영에 함께 사용한다. [입출력·제한](specs/integrated-answer.md#자연어-업무-실행-확장-2026-11-06-구현됨).

> 대상 버전: 1.4.0 · 최종 확인: 2026-11-04 (main 통합 코드 대조)

## 외부 AIS·선석 참조 API (2026-11-04 로컬 시범)

`scripts.prepare_navigation_references`의 명시적 오프라인 수집·준비 → 별도 JSON snapshot → 서버 전용 `MARITIME_PORT_REFERENCES_PATH` → `backend/tools/navigation_references.py` 순서다. 기존 해사 Bearer API와 일반 로그인 앱 어댑터가 같은 비교 함수를 사용한다. 요청 중 외부 네트워크를 조회하지 않으며 앱 원본 DB·MRV·DWT를 수정하지 않는다. 파일은 매 요청 크기·형식·식별자·시각을 재검사하며, Docker에서는 관리자가 읽기 전용 마운트를 설정한다. [계약과 실행법](specs/port-references.md).

1.1 수집본은 항구별 출처·용도 범위를 갖는다. Gothenburg 제목 블록과 Helsinki 크루즈 선석 표를 각각 명시적 UN/LOCODE/WPI에 연결하며, 선택 항구의 수집 시각으로 노후화를 판정한다. `scripts.navigation_bundle`은 관리자 PC에서 묶음 생성·검사·설치와 이전 파일 보존을 담당하고 DB/인터넷에 접속하지 않는다. 선택적 `compose.navigation.yaml`은 설치 디렉터리를 읽기 전용 마운트해 원자 교체된 파일을 다음 요청에서 읽게 한다. 앱 JSON 백업과 별도이며, 배포한다고 source의 시각·법적 신뢰가 갱신되지 않는다.

운항 화면의 `PortReferencePanel`은 기존 대상 선박을 사용해 `/api/operations/port-reference-screen`을 호출한다. 서버는 `api/maritime_context.py`의 공통 resolver로 앱 선박 ID→명시적 MRV 매핑→IMO를 확인한다. 이 resolver는 기존 MRV 계산 기능과 공유한다. 현재 계정·앱 선박 버전·연결은 결과 반환 전에 재확인하며 브라우저는 선택 변경 후 이전 응답을 버린다. 기존 공통 운항 조회 권한을 따르며, 선박별 ACL·LLM 라우팅은 추가하지 않는다. 날짜만 있는 앱 흘수 기록은 별도 참고로 표시하고 AIS나 현재 실측값으로 대체하지 않는다.

기존 통합 질문의 `/api/ask`는 `api/navigation_query.py`에서 자동 유형의 제한된 항구 비교 질문을 처리한다. 질문의 명시 IMO/앱 선박명 또는 기존 선택 선박을 확인한 뒤, 항구가 생략된 목록 질문은 제공 항구 전체를 비교한다. `api/navigation_service.py`를 상세 API와 공유하고 `NavigationAnswer`가 기존 답변 영역에 항구별 건수·숫자·출처·부족 항목을 표시한다. 질문에서 확인한 선박은 대기 중 선택이 바뀌지 않았을 때만 기존 문맥에 반영한다. 명시 문서 전용·규정/정의 설명과 다른 유형은 기존 `db.answer` 경로를 유지한다. 일반 RAG store·모델 호출 함수는 수정하지 않으며, 이 분기는 규칙과 도구로 실행되는 한정 경로다. 범용 LLM 의도 분류·실제 입항 허가 판정은 구현하지 않는다. 답변은 기존 소유자별 질문 이력에 저장한다.

`api/navigation_intent.py`는 이 경로의 공개 제한값 필터·상태 필터·항구별 정렬을 담당한다. 원본 비교 결과를 복사한 뒤 조건을 적용하며 소스 수치·판정 계산을 변경하지 않는다. 브라우저가 현재 표시한 답변의 `previousQueryId`를 보내면 짧은 후속 질문에만 사용한다. 서버는 기존 `queries`/`query_owner`에서 소유자를 확인하고 같은 선박 버전·IMO·현재 매핑을 재검증한다. 이력 숫자나 최신 질문을 암묵적으로 재사용하지 않고 현재 자료로 다시 계산한다. 지원 범위 밖의 명시 조건·실제 입항 불가 요청은 확인 상태로 반환한다.

`scripts.prepare_navigation_sources`는 별도 명시 수집/오프라인 확장 명령으로 노르웨이 공개 AIS·덴마크 Aalborg PDF를 기존 MRV/WPI 해시에 연결한다. PDF 추출 라이브러리는 준비 명령에서만 필요하며 서버 의존성에는 추가하지 않는다. 1.2 묶음도 기존 `navigation_bundle`로 검사·설치한다. 런타임의 `tools/navigation_readiness.py`는 검토된 원문 패턴의 예선/선저 여유/최신 측심 조건과 입항 전 추가 확인 항목을 반환한다. 선택적 가정값은 별도 `scenario`이고 실제 관측/측정/승인으로 저장·사용하지 않는다. 상세 화면과 질문 답변은 같은 `NavigationReadiness`/`OperationalChecks` 표시를 공유한다. 범용 LLM 도구 선택·동적 UKC 계산·실제 입항 허가는 추가하지 않는다.

> 이 문서는 **현재 구현**을 설명합니다. 앞으로 바꿀 계획은 [`plans/`](plans/), 바뀌지 않을 결정의 이유는 [`adr/`](adr/)에 있습니다.

### 과거 등록 제원·지역 관측 경계 (2026-11-05)

`scripts.prepare_navigation_quality`는 보존된 1.2를 기반으로 월 단위 노르웨이 등록 이력과 고정 SMHI 관측소의 원문·명세·좌표·기준면 증거를 별도 수집/검증한다. 명시 준비 작업에서만 네트워크를 사용한다. `backend/tools/navigation_context.py`는 일치하는 등록 후보의 길이/폭 참고값과 관측 품질/나이를 제공한다. 등록 흘수는 현재 흘수에 사용하지 않는다. `NavigationContext`/`HistoricalChecks`를 기존 질문·운항 상세 화면에서 공유하며 기존 AIS 판정·가정 입력·실제 입항 확인 상태는 바꾸지 않는다. Routeinfo 자료는 적용 항구/유효기간 검사 결과만 별도 보관하고 카탈로그/항로 추천에 연결하지 않는다.

### 공식 항만 지침의 명시 갱신

`scripts.prepare_port_guidance`는 고정 공식 HTML 수집 → main 본문/원문 해시 비교 → 조건·단위·적용 범위 검토 보고서 → 정확한 검토 SHA256을 지정한 새 1.4 준비 순서로 동작한다. 런타임 `tools/navigation_guidance.py`는 해당 항구·지정 선석의 참고 문서만 반환한다. 수집일/표시 개정일/명시 적용일을 구분하며 기존 비교·가정 조건·입항 상태에 자동 적용하지 않는다. 질문/운항 화면은 공통 `OfficialGuidance`를 사용한다. 출처 문서가 바뀌어도 일반 RAG·모델 라우팅·DB 원본을 갱신하지 않으며, 네트워크는 관리자 준비 단계에서만 사용한다.

## 현재 Python 문서 경로 (2026-10-13)

현재 실행 코드는 `backend/api/main.py`(FastAPI)와 `backend/api/store/`(PostgreSQL·업무 로직)이다. 전처리 모듈은 `api/` 패키지 안에 두어 backend 단독 실행과 Docker 운영 이미지에서 같은 경로로 사용한다.

문서 등록: `frontend/src/lib/pdf.js`가 브라우저에서 페이지별 텍스트를 추출 → `controller.jsx`에서 사용자가 검토한 본문을 sections로 변환 → `POST /api/changes` (`document.save`) → `api/store/documents.py`의 `DocumentStore.save_document` → `api/rag_preprocessing.py` → 기존 `documents`, `chunks`, `chunk_pages`, `document_files` 저장. 원본 PDF는 기존과 같이 base64로 보존하며 외부 추출 서비스에 보내지 않는다.

2026-10-18 문서 정보 수정 경로: `frontend/src/lib/document-save.js`가 정보 변경과 본문 개정을 구분한다. `document.save`의 `mode: "metadata"`는 같은 저장 모듈에서 현재 개정·정보 버전을 검사하고 `document_meta`만 갱신한다. 본문 개정은 새로 제공한 원문만 전송하고 기존 조회 청크를 원문으로 재사용하지 않는다. 신규 원문 전처리 결과가 0개면 저장을 거부한다. DB 스키마·검색 알고리즘·백업 구조는 유지한다.

전처리는 웹·DB 의존성이 없는 함수이고 문서 ID·제목은 저장 계층에서 기존 관계로 연결한다. 청킹 규칙과 변경 적용 범위는 [API 전처리 계약](specs/api.md#python-문서-전처리-계약-2026-10-13-확정), 검증과 새 구조 통합 기록은 [작업 기록](plans/2026-10-13-rag-preprocessing.md)에 있다. 현재 검색은 저장 계층이 권한·상태·종류·선택 문서 범위를 먼저 확정한 뒤 `api/rag_search.py`가 BM25와 로컬 E5 벡터 결과를 RRF로 결합한다. 한 검색 엔진만 준비되면 해당 결과를 사용하고 둘 다 불가하면 검색 불가를 알린다. 검색 후 반환 청크를 현재 PostgreSQL에서 다시 조회해 원문·권한 변경 결과를 제거한다. 저장 시에는 기존 문서·청크·개정 규칙을 유지하면서 자동 색인 작업을 같은 트랜잭션에 기록한다.

## 1. 한눈에 보기

### 질문창의 조건 보완과 AIS 자료 현황

웹의 `queryShipExplicit`/`queryPeriodExplicit`은 현재 브라우저에서 명시한 선택만 `/api/ask`로 전달한다. 기본 첫 선박·날짜를 질문 범위로 확정하지 않는다. `question_intent.slot_reply`는 등록 명칭·기간·연결 어미로 제한한 짧은 응답을 판별하고, `question_workflows`가 현재 소유자와 같은 대화의 부모 범위·문서 권한을 검증한다. `workflow.clarification`의 다음 질문을 주 안내로 쓰며 기존 선택 양식은 접힌 보조 입력이다.

`navigation_query`는 AIS 자료 보유·수집 현황 질문을 기존 문서 검색보다 먼저 처리한다. `navigation_service.load_snapshot`과 기존 `catalog_summary`를 재사용하고, `NavigationAnswer`가 수집본 건수·출처·노후화 및 요청 선박의 정확한 IMO 포함 여부를 표시한다. 모델이나 문서 유사도로 데이터 등록 여부를 추정하지 않는다. 관리자 반입과 실시간 수신은 별도이며 런타임 외부 수집·새 DB 테이블은 추가하지 않는다. [응답 계약](specs/integrated-answer.md#질문창-중심-조건-보완-2026-11-10-구현됨).

### 업무 스킬 실행

기존 질문·문서·운항·보고서 화면의 재사용 SkillsPanel → 일반 앱 API `/api/skills/run` → `api/workflow_skills.py`의 고정 handler로 실행한다. 지침은 Docker에 이미 복사되는 `knowledge/skills/<id>/SKILL.md`에 있다. 모델은 지침·원문에 기반한 설명에만 선택적으로 쓰며, 식별자·기간·SQL·권한·수치를 생성하지 않는다. 여섯 기능의 기본 실행에는 LLM이 필요 없다. 독립 업무 스킬 메뉴는 없으며 이전 /skills는 /chat으로 이동한다. 문서 상세는 현재 활성 문서, 운항·보고서는 공통 선박·기간, 응답 평가는 현재 답변 ID로 초기화한다. 패널을 펼칠 때만 카탈로그를 요청한다. [계약](specs/workflow-skills.md), [ADR 0015](adr/0015-optional-model-workflow-skills.md).

선택 문서 ID는 권한·활성 개정본을 먼저 확인하고 SQL 조회 조건으로 제한한다. MRV 실행은 앱 선박의 명시 매핑·IMO 정체성을 검증한 뒤 기존 Python Tool을 호출한다. 일반 앱 경계를 통해 호출하므로 서버 Bearer를 브라우저에 전달하지 않는다. 보고서 초안 생성은 payload만 반환하며 별도 버튼으로 저장한다. 실행 기록은 기존 queries/query_owner/audit에 보관하고 새 스키마는 만들지 않는다.

해답은 frontend·backend·PostgreSQL·rag-worker·Chroma와 시작 시 실행하는 마이그레이션으로 구성됩니다.
사용자는 **Next.js 주소 하나**(기본 `http://localhost:5173`)로만 접속합니다. Next.js가 화면을 그리고,
`/api/*`를 FastAPI로 넘깁니다([ADR 0006](adr/0006-nextjs-entry-rewrites-to-api.md), [ADR 0007](adr/0007-runtime-api-origin-via-proxy.md)).
백엔드와 내부 worker가 PostgreSQL에 접근합니다.

`frontend/`(npm)와 `backend/`(uv)는 독립 패키지이고 최상위 `compose.yaml`이 서비스를 함께 띄웁니다.
최상위 `e2e/`는 스택을 브라우저로 검증합니다([ADR 0009](adr/0009-split-packages-and-compose.md)).

```mermaid
flowchart LR
  B[브라우저<br/>React UI] -->|HTTP :5173| N
  subgraph C[docker compose · 프로젝트 haedap]
    N[frontend<br/>Next.js :5173<br/>유일하게 공개되는 포트]
    G[backend<br/>FastAPI :8000<br/>api.main:app]
    D[(db<br/>PostgreSQL 18<br/>볼륨 db-data)]
    M[migrate<br/>dbmate · migrations/<br/>시작 때 1회]
    K[/백업 파일<br/>볼륨 backups/]
    M -->|대기 중인 마이그레이션 적용| D
    N -->|/api/* proxy.js<br/>X-Forwarded-Host| G
    G --> D
    G --> K
    W[rag-worker · E5 CPU] --> D
    W --> V[(chroma · rag-vectors)]
    G --> V
  end
  G -. 선택: LLM_API_BASE_URL · OPENAI_MODEL 설정 .-> O[(OpenAI 호환 Chat Completions)]
  E[e2e<br/>Playwright] -. profile e2e .-> N
```

| 서비스 | 이미지(빌드 위치) | 포트 | 데이터 |
|---|---|---|---|
| `db` | `postgres:18-alpine` | 내부 5432 (개발 오버레이에서만 `127.0.0.1:5432` 공개) | 볼륨 `db-data` |
| `migrate` | `amacneil/dbmate:2.36.0` | 없음 | 최상위 `migrations/` 마운트. `up` 후 종료([ADR 0010](adr/0010-dbmate-migrations.md)) |
| `backend` | `backend/Dockerfile` (`prod`/`dev` 타깃) | 내부 8000 (개발 오버레이에서만 `127.0.0.1:8000` 공개) | 볼륨 `backups` → `/data/backups` |
| `chroma` | `backend/Dockerfile.chroma` (공식 Chroma 1.5.9 기반) | 내부 8000, 호스트 공개 없음 | 볼륨 `rag-vectors` → `/data/chroma` |
| `rag-worker` | backend와 같은 모델 포함 이미지 | 없음 | PG 작업 큐, 이미지 `/opt/models/e5-small` |
| `frontend` | `frontend/Dockerfile` (`prod`=standalone, `dev`=`next dev`) | `${HAEDAP_BIND:-127.0.0.1}:${PORT:-5173}` | 없음 |
| `e2e-*`, `e2e` | 같은 이미지·Dockerfile + `e2e/Dockerfile` | 공개 안 함 | DB·백업 모두 tmpfs (실행마다 빈 상태, `e2e-migrate`로 같은 마이그레이션 적용) |

- **운영 실행**: `docker compose up --build -d`. 시작 순서는 db(헬스체크 통과) → migrate(성공 종료) → backend(헬스체크 통과) → frontend입니다. 마이그레이션이 실패하면 backend가 시작하지 않습니다. backend 헬스체크는 `/api/health`를 호출하므로 DB 연결까지 확인합니다.
- **개발 실행**: `docker compose -f compose.yaml -f compose.dev.yaml up --build`. 소스를 컨테이너에 바인드 마운트하고 `uvicorn --reload`, `next dev`로 저장 즉시 반영합니다. Docker 없이 `backend/`에서 `uv run`, `frontend/`에서 `npm run dev`로 직접 실행하는 방법도 유지합니다([ADR 0005](adr/0005-dev-mode-direct-processes.md)).
- **API 주소**: `HAEDAP_API_ORIGIN`. compose에서는 `http://backend:8000`, 직접 실행에서는 기본 `http://127.0.0.1:8000`. `proxy.js`가 **요청마다** 이 값을 읽으므로 바꿔도 다시 빌드할 필요가 없습니다. 직접 실행할 때는 `next.config.mjs`가 이 값 하나만 최상위 `.env`에서 읽습니다.
- `next.config.mjs`는 `output: 'standalone'`으로 빌드하고, `next dev`는 `.next-dev`, 그 외에는 `.next`를 출력 폴더로 씁니다(`HAEDAP_NEXT_DIST`로 덮어쓰기 가능).
- 외부 네트워크는 선택적 LLM 호출에서만 사용합니다.

## 2. 요청 흐름

### 2.1 Next.js → FastAPI (`frontend/src/proxy.js`, `backend/api/web/handler.py`)

1. 브라우저 요청은 모두 Next.js가 받습니다. 화면·`/_next/*`·`frontend/public` 리소스는 Next.js가 직접 응답합니다.
2. `/api/:path*`는 `proxy.js`(Next.js 16의 `middleware` 후속, Node.js 런타임)가 `NextResponse.rewrite`로 `HAEDAP_API_ORIGIN/api/:path*`에 프록시합니다. 원래 `Host`는 `X-Forwarded-Host`에 들어갑니다. 쿠키·`Set-Cookie`는 그대로 오갑니다.
3. 프록시 설정(`experimental`): 요청 본문 최대 **101MB**(PDF 포함 문서 등록 38MB, 백업 가져오기 100MB), 응답 대기 **60초**.
4. FastAPI의 `/api/{path}` 하나가 모든 앱 API를 받습니다. 요청마다 PostgreSQL 연결을 열고(`Workspace`), 첫 요청에서 `bootstrap()`(명시적 초기 관리자 설정·기본 설정·`knowledge/seed.json` 문서 등록)을 한 번 실행합니다.
5. **Host·Origin 검사**(`validate_origin`): `X-Forwarded-Host`(없으면 `Host`)의 호스트 이름이 `localhost`, `127.0.0.1`, `HAEDAP_ALLOWED_HOSTS`에 있어야 하고, `Origin`이 있으면 같은 주소여야 합니다. 아니면 403.
6. 동시 요청 4개 제한, 백업 복구 중 다른 요청 차단(PostgreSQL advisory lock), 1분마다 자동 백업 여부 확인.
7. `MARITIME_DATA_API_TOKEN`이 설정되어 있으면 `/api/maritime-data/*` 라우터가 `/api/{path}`보다 먼저 등록됩니다(8절).

### 2.2 화면 (`frontend/`)

- `src/app/` — App Router 페이지. `/`는 `/chat`으로 리다이렉트. 페이지: `/chat`, `/documents`, `/documents/[id]`, `/operations`, `/reports`, `/reports/[id]`, `/admin`.
- `src/workspace/provider.jsx` — `WorkspaceProvider`가 작업공간 상태를 소유하고 컴포넌트는 `useSyncExternalStore`로 구독.
- `src/workspace/controller.jsx` — 사용자 이벤트 처리, API 호출, 대화상자, 초안 보존.
- `src/lib/api.js` — 유일한 서버 호출 지점. `X-Haedap-Token`(CSRF), `X-Haedap-Identity`(현재 사용자 확인) 헤더를 붙임.
- `src/lib/pdf.js` — 브라우저 안의 PDF.js로 텍스트 추출(업로드 PDF는 외부로 보내지 않음). `src/lib/csv.js` — 운항 CSV 파싱.
- `src/lib/model.js` — 클라이언트 상태 모델, 미저장 초안의 `localStorage` 보관.
- `src/lib/answer-presentation.js`, `src/components/answer-presentation.jsx` — 응답의 표·차트 구조와 자료 범위를 확인하고, 행별 원문 인용 버튼·축·단위·자료 표를 표시. 모델 문자열을 HTML로 실행하지 않으며 잘못된 표현은 안내와 기존 문장 응답으로 처리한다.

### 2.3 통합 질문 (`POST /api/ask`)

```mermaid
sequenceDiagram
  participant UI as 브라우저
  participant API as routes/documents.ask
  participant WS as Workspace.answer
  participant DB as PostgreSQL
  UI->>API: question, task, context{ship,from,to}, criterion, outputFormat
  API->>WS: 사용자·CSRF 확인 후 호출
  WS->>DB: search_candidates() — 권한·활성 개정·상태·종류·선택 문서 필터
  WS->>WS: BM25·로컬 E5 벡터 → RRF 상위 5 (준비 실패 시 BM25)
  WS->>DB: 후보 재조회 → 원문·권한 변경 결과 제거
  WS->>DB: 운항 필요 시 operation_summary(ship, from, to)
  WS->>WS: criterion 있으면 단일 기준 수치 비교
  WS->>WS: 실제 운항 전체 자료로 요청한 표·차트 구성
  WS->>WS: 완전 근거 단위의 입력 바이트·선행 처리 후 남은 시간 확인
  alt 문서 문장·표의 mode=llm 이고 설정·입력·남은 시간 예산 충족
    WS->>WS: 외부 LLM → 문장·요청 표의 구조와 정확한 원문 인용 검사
    opt 호출·검증 실패
      WS->>WS: 원문 발췌로 전환·사유 기록
    end
  else
    WS->>WS: 모델 호출 없이 기존 원문 발췌·자료 응답 유지
  end
  WS->>WS: 전체 운항 집계를 보존하고 답변 기록 미리보기는 최대 200건
  WS->>DB: queries + query_owner + audit 기록
  WS-->>UI: statements, evidence, operations, presentation, timings, ...
```

응답 형식은 [`specs/integrated-answer.md`](specs/integrated-answer.md)를 따릅니다.

표·차트의 자료/인용 검증과 표시 범위는 [`specs/answer-presentation.md`](specs/answer-presentation.md)를 따른다. LLM 사용자 메시지는 완전한 근거 단위로 8,192 UTF-8 바이트 안에 구성한다. 검색·운항 조회·계산을 생성 전에 완료하고, 답변 처리의 생성 설정+3초 예산에서 선행 처리 시간을 뺀 값과 생성 설정 중 작은 값을 모델 HTTP 제한으로 사용한다. 기본 생성 설정은 60초이며 연결은 최대 5초다. 남은 시간이 1초 미만이면 호출하지 않으며 HTTP 제한은 전체 처리의 강제 종료 시한이 아니다. 브라우저는 서버가 알린 질문 대기 시간(기본 95초)을 사용한다. 실제 운항 자료로 구성한 요청 표는 최대 50행, 요청 차트는 최대 100점이며, 전체 집계와 별도 운항 기록 미리보기 200건을 구분한다. 인증·조회·원본 데이터 경계는 유지한다.

## 3. 모듈 책임 (`backend/`)

| 경로 | 책임 |
|---|---|
| `api/main.py` | FastAPI 앱 생성, lifespan(자동 백업 루프), 해사 데이터 라우터 마운트, 오류 응답 형식 |
| `api/web/handler.py` | `/api/{path}` 진입점: 요청 슬롯, Content-Type·본문 크기, DB 세션, 인증·CSRF 후 `routes.dispatch` |
| `api/web/security.py` | Host·Origin 검사, 기존 게스트 식별자, 개인 계정 세션(메모리), CSRF 토큰, 로그인 시도 기록 |
| `api/web/concurrency.py` | 동시 요청 4개 제한, 복구 단독 실행(프로세스 카운터 + PostgreSQL advisory lock) |
| `api/web/backup_job.py` | 1분마다 확인하는 하루 1회 자동 백업 |
| `api/routes/` | 경로 표와 도메인별 핸들러: `system`(health·tools), `auth`, `documents`(문서·PDF·ask·search·history), `operations`, `changes`, `reports`, `admin`(users·logs·backups) |
| `api/store/` | `Workspace` = `base.Database`(연결·트랜잭션) + 도메인 mixin: `users`, `documents`(청크 900자·검색), `operations`, `changes`, `reports`, `answers`(통합 답변·선택적 LLM), `tools`, `backups` |
| `api/config.py`, `api/deps.py` | 환경 설정(DB 주소, 백업 경로, 허용 호스트), `Workspace` 열기와 최초 1회 초기화 |
| `api/llm.py` | 완전한 근거 단위의 입력 바이트 제한, 남은 HTTP 호출 시간 적용, Chat Completions 호출과 문장·요청 표의 JSON·원문 인용 검증. URL 호스트별 키 선택과 설정 판정은 `config.llm_settings()`를 health·답변이 공유 |
| `api/answer_presentation.py` | 표·차트 요청 해석, 문서 표의 행별 원문 인용 검증, 실제 운항 자료의 표·선/막대 차트 구성과 표시 한도. 모델·DB를 직접 호출하지 않음 |
| `api/rag_preprocessing.py` | 저장 전 페이지별 텍스트 정리·경계 기반 최대 900자 청킹. DB·웹 의존성 없음 |
| `api/rag_retrieval.py`, `api/rag_lexical.py` | PostgreSQL 허용 후보에 대한 OpenSearch/Nori 검색·준비 정보·진단. 전역 BM25 통계 사용 |
| `api/rag_vocabulary.py` | Nori 해사 사용자 단어, 한영 별칭, 제한적인 불용어. 검색용 사전이며 원문은 변경하지 않음 |
| `api/rag_lexical_jobs.py`, `api/rag_lexical_worker.py` | DB 변경 트리거의 독립 OpenSearch 작업 큐 처리·재시도·문서 세대 확인. Chroma 완료 상태와 독립 |
| `api/rag_search.py`, `api/rag_hybrid.py` | 준비된 두 엔진 후보의 RRF 결합, 한 엔진 대체 또는 명시적 503. 최종 PG 재확인은 store/documents.py |
| `api/rag_embeddings.py`, `api/rag_vector.py` | 고정 로컬 E5 모델 계약·입력 검증과 재구축 가능한 Chroma 색인. 검색 결과 본문은 현재 PostgreSQL 후보 행으로 구성 |
| `api/rag_jobs.py`, `api/rag_worker.py` | 문서 저장 트랜잭션의 자동 색인 작업 기록과 별도 worker의 획득·임베딩·세대 확인·완료 처리 |
| `api/errors.py`, `api/validation.py` | `ApiError`·`require`, 입력 검증·형식 도우미 |
| `knowledge/seed.json`, `knowledge/documents/`, `knowledge/sample-data.json` | 기본 문서와 그 원본 PDF(`file` 필드로 연결), "예시 데이터 넣기"용 가상 운항 기록 |
| `tools/` | 서비스 실행 중 사용하는 읽기 전용 해사 데이터 조회·계산·규칙 기반 조회 도우미(8절) |
| `tests/` | 앱과 해사 Tool pytest (`backend/`에서 `uv run pytest`) |

최상위 `scripts/`는 원본·공개 참조 자료 정규화, 전처리·품질 판정, 필드 사전 생성, CSV 적재 및 명시적 선박 연결을 담당합니다. backend uv 환경의 `data` 의존성 그룹을 사용하며 운영 이미지에는 포함하지 않습니다([ADR 0011 제안](adr/0011-tools-runtime-and-data-preparation.md)). 자료 준비는 서비스 시작이나 Tool 호출 때 자동 실행하지 않습니다.

DB 스키마는 backend가 아니라 최상위 `migrations/`(dbmate)가 소유합니다. backend는 테이블이 없으면 `SCHEMA_NOT_READY`(503)를 반환합니다.

개발자용 `scripts/debug_bm25.py`는 backend 기본 uv 의존성만 사용하는 읽기 전용 BM25 진단 도구다. `DocumentStore.search_candidates`의 기존 조회·권한·상태·kind 필터와 `rag_retrieval.query_tokens/chunk_tokens/retrieve`를 공유한다. 웹 API는 하이브리드 또는 준비된 한 엔진 결과를 score 없이 최대 5개 반환하며, 이 CLI는 BM25 점수·일치 토큰·미리보기를 출력한다. DB READ ONLY 트랜잭션에서 실행하며 초기화·저장·질문 이력·LLM 호출은 하지 않는다. 운영 이미지에는 스크립트를 포함하지 않고 실행할 때 읽기 전용 마운트한다. 기본 guest 또는 명시한 기존 활성 계정의 scope를 적용하며 DB 자격 증명을 가진 개발자 전용이다. [실행 방법](../README.md#bm25-개발자-디버그), [출력 계약](specs/api.md#개발자-진단-cli-계약-2026-10-15-확정).

개발자용 `scripts/evaluate_llm.py`는 기본 문서에서 고정 근거를 골라 한국어 생성만 비교한다. 기본 원문 발췌는 네트워크 없이 실행하고, 명시적 `--mode llm`만 기존 `api/llm.py`의 실제 모델 호출·원문 인용 검증을 사용한다. DB·검색·권한·이력 저장 경로를 호출하지 않으며 서비스 런타임에도 포함하지 않는다. 결과의 의미적 정답성은 사람 검토로 남긴다. [평가 계약](specs/llm-provider.md#7-한국어-생성고정-근거-평가-계약-2026-10-28-확정), [실행 방법](../README.md#한국어-답변-고정-근거-평가).

`frontend/tests/`는 CSV·PDF 유틸 단위 테스트(`npm test`), 최상위 `e2e/tests/`는 화면 → API → DB 전체 흐름 검증(Playwright)입니다.

## 4. 보안 경계

모듈을 교체하더라도 아래 경계는 유지해야 합니다.

- **접속 범위**: 공개되는 포트는 frontend 하나입니다. 기본 바인딩은 `127.0.0.1`(이 PC만). `HAEDAP_BIND=0.0.0.0`으로 LAN·서버 접속을 열고, 접속에 쓰는 호스트 이름·IP를 `HAEDAP_ALLOWED_HOSTS`에 넣습니다. TLS는 포함하지 않으므로 운영에는 앞단 HTTPS 리버스 프록시와 `HAEDAP_HTTPS=true`가 필요합니다. 외부 업무 접속은 조직의 VPN·추가 인증 정책을 함께 적용합니다.
- **내부 API·DB**: backend와 db는 compose 내부 네트워크에만 있고 운영 구성에서는 호스트에 공개하지 않습니다(개발 오버레이만 `127.0.0.1`로 공개). backend는 compose 네트워크 안에서만 접근되므로 로그인 시도 제한을 위해 `X-Forwarded-For`를 신뢰합니다(`--forwarded-allow-ips *`).
- **접속자 IP 범위**: 백엔드는 접속자 IP·서브넷을 검사하지 않습니다. 같은 서브넷으로 제한하려면 OS 방화벽을 씁니다(Ubuntu: `ufw allow from 192.168.0.0/24 to any port 5173`).
- **단일 출처**: 브라우저는 Next.js 주소 하나만 사용. Origin 검사는 실제 호스트(`X-Forwarded-Host`) 기준.
- **인증**: 선원·관리자·열람 계정의 서버 세션. 익명 업무 API 차단, 초기 비밀번호 교체, 30분 유휴·12시간 절대 만료, 계정 버전·활성 상태 재확인. HttpOnly·SameSite=Strict 및 HTTPS 운영 시 Secure 쿠키. 상세 계약은 [authentication.md](specs/authentication.md), 운영 조건은 [사용 안내 2절](user-guide.md#2-역할과-승인)을 따릅니다. backend 재시작 시 세션과 로그인 제한 기록이 초기화되는 단일 worker 구조입니다.
- **쓰기 보호**: 모든 POST는 JSON + `X-Haedap-Token` 필요. 원본 자료(문서·선박·운항) 변경은 서버에서 관리자 여부를 검사.
- **열람 범위**: 문서 `scope`(all/operator/admin)를 **검색 단계부터** 적용하고, 원본 PDF·보고서 근거·질문 이력 재열람에도 다시 검사.
- **LLM 인증키 격리**: `LLM_API_BASE_URL`을 파싱한 호스트가 `api.openai.com`이면 `OPENAI_API_KEY`, `dongguk.edu` 또는 하위 도메인이면 `DONGUK_AI_CHAT_API_KEY`만 선택. 해당 키가 없으면 모델 비활성. 로컬 Ollama·기타 호환 서버에는 두 키가 설정되어 있어도 인증 헤더를 보내지 않음. URL 경로·유사 도메인으로 키를 선택하지 않음([ADR 0013](adr/0013-provider-credential-isolation.md)).
- **LLM 출력 검증**: OpenAI 호환 `<LLM_API_BASE_URL>/chat/completions`에 권한 적용된 근거만 전달. JSON 출력 형식 강제는 `LLM_RESPONSE_FORMAT`의 선택 사항이고 앱의 JSON·인용 검증은 항상 적용. 정상 완료(`finish_reason=stop`)·최대 5개 문장·근거 ID·8자 이상 원문 인용을 검증하며 하나라도 틀리면 전체 폐기 후 발췌로 전환. health는 같은 설정 판정만 사용하며 모델 서버를 호출하지 않음([공급자 계약](specs/llm-provider.md)).
- **근거 없는 수치 금지**: 공식 CII와 규정 적용 판정은 산출하지 않고 `unavailable` / `unknown`과 사유를 반환.
- **비밀값**: `.env`(최상위)는 Git에서 제외. API 키는 backend 환경변수로만 전달하고 frontend 컨테이너에는 넣지 않습니다.

## 5. 교체 지점 (팀 모듈 연결)

| 바꾸려는 것 | 시작 위치 | 지켜야 할 계약 |
|---|---|---|
| 검색(벡터·하이브리드 RAG) | `api/store/documents.py`의 `search_candidates`·`search`, `api/rag_search.py`·`api/rag_hybrid.py`·`api/rag_vector.py` | 검색 전·후 현재 DB의 열람 범위·원문 확인, evidence 필드 형식, [벡터 검색 계약](specs/rag-vector.md) |
| 답변 생성(LLM 공급자) | `api/llm.py`, `api/config.py`, `api/store/answers.py`의 `mode=llm` 분기 | [공급자 계약](specs/llm-provider.md), 문장·표의 `chunkId`·`quote` 인용 검증, 입력 바이트·시간 예산 |
| 표·차트 표현 | `api/answer_presentation.py`, `frontend/src/components/answer-presentation.jsx` | [표현 계약](specs/answer-presentation.md), 원문 인용·실제 조회 수치·전체/표시 개수 구분 |
| 의도 분류·Agent | `api/store/answers.py`의 `answer` | [`specs/integrated-answer.md`](specs/integrated-answer.md) 출력 형식 |
| 계산 Tool 추가 | `api/store/tools.py`(`TOOL_DEFINITIONS`, 계산 메서드), `api/routes/system.py`(경로) | 입력 검증, `version`·`assumptions` 반환, `tool_runs` 기록 |
| 보고서 서식 | `api/store/reports.py`의 `generate_report` | 없는 값은 `[미입력 · 확인 필요]` |
| 새 서비스(로컬 LLM, 벡터 DB 등) | `compose.yaml`에 서비스 추가, backend 환경변수로 주소 전달 | 공개 포트는 frontend 하나 유지 |

연결 순서와 담당은 [`plans/2026-10-08-team-module-integration.md`](plans/2026-10-08-team-module-integration.md)를 참고하세요.

## 6. 빌드·실행 산출물

| 경로 | 생성 시점 | Git |
|---|---|---|
| `frontend/node_modules/`, `e2e/node_modules/` | `npm ci` (각 폴더) | 제외 |
| `backend/.venv/` | `uv sync` (`backend/`) | 제외 |
| `frontend/.next/`, `frontend/.next-dev/` | `npm run build`, `npm run dev` | 제외 |
| 볼륨 `haedap_db-data`, `haedap_backups` | `docker compose up` | — (`docker compose down -v`로 삭제됨) |
| 볼륨 `haedap_rag-vectors`, 이미지 `/opt/models/e5-small` | Chroma 실행·backend 이미지 빌드 | 파생 벡터 색인과 고정 로컬 모델. Git 원본 데이터가 아니며 PostgreSQL 자료로 색인 재구축 가능 |
| `backend/data/` | 직접 실행 시 백업(`data/backups/`) | 제외 |
| `e2e/test-results/`, `e2e/playwright-report/` | e2e 실행 | 제외 |
| `schema_migrations` 테이블 | dbmate (적용한 마이그레이션 버전) | — |
| `.env` | 사용자가 직접 | 제외 |

## 7. 알려진 한계

- 키워드 역인덱스는 OpenSearch가 영속 관리한다. 기존 벡터 내용 검증 때문에 초기 PG 전체 후보 읽기·해시 비용은 남으며 최종 재조회는 반환 ID로 제한한다.
- Nori 분석·전역 통계·사전·재색인·장애 정책은 [키워드 계약](specs/rag-lexical.md)을 따른다. 사전 밖 용어·다의어·영문 활용형과 부분 색인에 따른 순위 변화는 별도 평가가 필요하다.
- 관리자 세션은 backend 프로세스 메모리에 있어 backend를 여러 개 띄우면 공유되지 않음.
- 질문 유형 분기는 단어 규칙 기반. 질문 속 날짜·선박명 자동 추출은 미구현.

## 8. 해사 데이터 Tool의 경계 (선택)

공개 제원 후보는 추가 migration의 `capacity_candidates`에 원본과 별도 보존한다. 참고 전용 `/api/maritime-data/reference-intensity`는 승인 MRV 보고와 후보를 같은 읽기 전용 스냅샷에서 연결하며, 미검증 범위 수용 입력·출처·경고·차단 사유를 유지한다. 원본 CO₂·DWT·거리나 기존 calculate 계약은 변경하지 않고, 공식 CII·등급은 산출하지 않는다. 참조 CSV 적재는 `scripts/load_capacity_candidates.py`가 담당한다. 운항 화면의 MRV 업무는 일반 앱 권한 경계에서 명시 매핑을 검증하고 기존 Python 계산을 호출한다. 통합 질문 `/api/ask`의 자동 MRV 호출과 자연어 Tool 선택은 후속 범위다.

`backend/tools/`는 PostgreSQL `maritime_data` 스키마의 승인 View를 읽기 전용으로 조회·계산합니다. backend와 같은 uv 프로젝트이며, `MARITIME_DATA_API_TOKEN`(32자 이상)을 설정하면 같은 FastAPI 프로세스에 `/api/maritime-data/*`로 마운트됩니다. 설정하지 않으면 라우트가 없습니다. 기본은 앱의 `DATABASE_URL`이며 `MARITIME_DATA_DATABASE_URL`로 별도 DB를 선택할 수 있습니다. 별도 DB에도 기본 init과 해사 마이그레이션을 모두 적용해야 하며 선박 외래키는 그 DB 안의 `public.ships`만 참조합니다.

```mermaid
flowchart LR
  R[별도 원본·참조 자료] --> P[scripts<br/>오프라인 전처리·품질·출처 보존]
  M[migrations/<br/>dbmate · DDL만 적용] --> S[(PostgreSQL 앱 테이블<br/>public.ships / operations)]
  M --> DB[(같은 DB · maritime_data<br/>MRV / Noon / 출처 / 품질)]
  P -->|migration 선행·빈 테이블 CSV 적재| DB
  B[브라우저] --> N[Next.js :5173]
  N -->|/api/* proxy.js| G[FastAPI backend]
  G --> S
  DB -. vessels.ship_id<br/>검토한 명시적 연결 .-> S
  G -->|/api/maritime-data/*<br/>Bearer 토큰 필요| T[tools 라우터]
  T -->|승인 View 읽기 전용| DB
```

`vessels.ship_id`의 선택적 외래키로 기존 앱 `ships`를 재사용합니다. 연결은 준비 CLI의 명시적 매핑으로만 수행하고 외부 선박 전체를 자동 등록하지 않습니다. MRV는 보고기간 단위이므로 기존 일별 `operations`로 분해하지 않습니다. 원본 식별자와 REAL/SYN 구분, 출처·품질 정보를 그대로 유지합니다.

독립 Tool 라우트는 서버 전용 Bearer 토큰을 요구합니다. 기존 화면의 실행 패널은 이 토큰을 받지 않고 일반 앱의 `/api/skills/run`을 호출합니다. 서버가 앱 ID의 명시 매핑과 IMO 정체성을 확인한 뒤 계산 함수를 직접 실행하고 queries/query_owner/audit에 기록합니다. 접근 범위는 기존 앱의 로그인·역할 기반 운항 조회 정책을 따르며 사용자별 선박 ACL은 추가하지 않았습니다. 공식 CII 등급은 생성하지 않으며, 독립 Tool `/ask`의 실제 LLM 호출은 계속 비활성입니다.

`tools.api.create_app()`은 테스트·역할4 도구용 독립 앱으로 남아 있습니다. 마이그레이션은 앱과 해사 DDL을 소유하고 loader는 DDL을 실행하지 않습니다. 기존 단일 스키마 채택·rollback 제한과 앱 복구 시 선박 연결 정책은 [데이터 모델](data-model.md#9-postgresql-해사-데이터-tool-선택)에 정의합니다. 입출력은 [API 명세](specs/tools.md), 데이터 확보는 [운영 안내](user-guide.md#10-해사-데이터-tool-선택)를 참고하세요.
## 로컬 벡터/RRF 검색 경계

`store/documents.py.search_candidates()`가 PostgreSQL에서 권한·활성 개정·상태·종류·선택 문서 범위를 확정한 뒤
`rag_search.py`가 `rag_retrieval.py`(BM25)와 `rag_vector.py`(Chroma)의 후보를 `rag_hybrid.py`(RRF)로 결합한다.
`rag_readiness.py`는 문서 snapshot·모델·collection UUID에 연결된 완료 확인 정보를 일괄 조회한다.
BM25·벡터는 각각 준비된 허용 문서만 참여한다. 키워드 색인은 독립 outbox/lexical-worker가 동기화하며 검색은 복구하지 않는다.
검색 후에는 한 엔진 대체를 포함해 반환 ID만 PG에서 다시 조회하고 원문·권한 변경 결과를 제거한다.
청킹/개정 규칙은 유지하고 저장 끝에 작업 enqueue만 추가한다. `/search`와 `/ask`는 같은 검색 경로를 사용한다.

`rag_embeddings.py`는 고정 E5 모델 계약·명시적 준비·입력 길이 검증을 담당한다.
`scripts/rag_index.py`는 DB 읽기 전용 스냅샷 → 파생 벡터 색인, `scripts/debug_retrieval.py`는 같은 후보의 세 방식 비교다.
Chroma 서버는 Docker 내부 전용이며 자동 worker와 함께 기본 실행되고 `backend/Dockerfile.chroma`로 별도 빌드한다.
공식 Chroma 1.5.9에 기존 UID/GID 10001·저장 경로와 bash HTTP 헬스체크만 추가한다.
CPU PyTorch·E5 실행·Python 클라이언트는 backend/worker에 있다. 모델은 이미지 `/opt/models/e5-small`, 벡터는 named volume이다.
PostgreSQL만 원본이므로 Chroma 결과의 본문을 신뢰하지 않고 현재 후보 행으로 결과를 구성한다.
BM25는 OpenSearch/Nori 역인덱스를 사용한다. CLI에서 BM25만 실행하면 E5/Chroma를 로딩하지 않는다.
상세 실패·부분 색인·동기화 정책은 [검색 계약](specs/rag-vector.md), 로컬 벡터 선택 이유는 [ADR 0019](adr/0019-local-vector-retrieval.md), 자동 색인 결정은 [ADR 0021](adr/0021-durable-index-jobs.md)을 참고한다.

### 자동 색인 경계

`rag_jobs.enqueue`는 `save_document`와 같은 트랜잭션으로 작업을 기록한다.
정보만 수정하는 경로와 변경 없는 저장도 같은 작업을 요청한다. 원문·청크·PDF는 그대로 유지한다.
`rag_worker`는 전용 DB 세션에서 커밋된 작업을 획득하며 임베딩 동안 DB 트랜잭션을 열어두지 않는다.
세션 advisory lock은 중복 worker를 막고, generation/claim token은 오래된 완료를 막는다.
실패 정책·CLI 계약은 [rag-index-jobs](specs/rag-index-jobs.md)에 정의한다. 웹 응답은 색인을 기다리지 않는다.

```mermaid
flowchart LR
  Save[문서 저장] --> Tx[PG 트랜잭션: 문서·청크·작업]
  Tx --> Commit[커밋 후 HTTP 응답]
  Commit --> Worker[별도 rag-worker]
  Worker --> E5[이미지 내 E5 · CPU]
  E5 --> Chroma[Chroma upsert]
  Chroma --> Done[PG 작업 완료 · 세대 재확인]
```

worker는 모든 열람 범위의 활성 문서를 색인하는 서버 내부 작업자다. 검색의 사용자 권한 경계는 그대로 PG에서 확인한다.
복원 JSON에는 작업/벡터를 넣지 않으며 복원 후 명시적 enqueue로 재구축한다.

### 대화 및 화면 언어 (2026-11-09)

`store/conversations.py`는 기존 queries/query_owner의 소유권을 적용한 대화 목록·전체 조회·삭제를 맡는다. 통합 질문은 같은 대화에 답변을 추가하되 기존 생성/검색/계산 경로를 유지한다. UI는 `turns`와 현재 `conversationId`를 보관하며 답변 카드의 `data-answer-id`로 근거·보고서 액션을 연결한다. 새 질문/로고/사이드바 통합 질문 클릭은 새 대화를 시작하며 이전 대화는 이력에서 복원한다. 질문 전송 시 라우터의 상단 이동을 끄고, 질문·응답 DOM 반영 뒤 최하단으로 이동한다. 요청 순서 검사로 취소된 대화의 지연 스크롤을 막는다.

`UiLanguageContext`, `UiText`, `UiControl`은 중앙 사전 `ui-messages.json`의 메뉴·안내를 번역한다. 브라우저 설정 `haedap-ui-language`는 질문 API의 language와 별개다. 원문/질문/답변/보고서 본문은 번역 컴포넌트를 통과시키지 않고 입력값과 데이터 속성도 번역하지 않는다. 초기 SSR은 한국어이며 마운트 뒤 저장된 화면 언어를 읽는다.

### 2026-11-09 기본 문서 확장

`api/knowledge_update.py`는 기존 bootstrap 트랜잭션에서 기존 문서를 테스트용으로 표시하고, `knowledge/mepc-2026.json`의 10건과 원본 PDF를 등록한다. 원본은 준비 시 추출하며 런타임 PDF/OCR 의존성을 추가하지 않는다. settings 완료 키로 반복 실행을 방지한다. 원본 개정 ID·참조를 보존하고 변경된 활성 제목은 기존 색인 outbox에 다시 기록한다.
