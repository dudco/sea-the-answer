# 해답 — SEA THE ANSWER

현재 버전 **1.4.0** · 마지막 업데이트 **2026-10-15**

선내 문서 근거와 운항 기록을 함께 보여 주는 선박 업무 지원 앱입니다. 화면은 Next.js, `/api/*`는 Python FastAPI, 저장소는 PostgreSQL이며, 저장소 최상위에서 `docker compose` 하나로 셋을 함께 실행합니다.

| 화면 | 기능 |
|---|---|
| 통합 질문 | 문서 근거 + 선택한 선박·기간의 운항 수치·추이를 함께 답변, 근거 페이지·원문 PDF 열기, 입력 기준 비교, 보고서에 담기 |
| 업무 스킬 | MRV 참고 분석·선택 문서 답변·운항 요약·보고서 초안·점검표·내 응답 평가. 기본 동작은 LLM 불필요 |
| 문서 | 텍스트 PDF 등록·추출 검토, 메타데이터·열람 범위, 개정 버전 관리 |
| 운항 정보 | 선박·일별 기록 관리, CSV 일괄 등록, 지표 차트·선박 비교, 배출량·항해 시간 계산 |
| 보고서 | Noon / MRV 검토 초안 자동 생성, 편집·저장, 검토 요청 → 관리자 승인 |
| 관리 | 계정·역할, 승인, 질의·변경·오류 로그, 백업·복구 |

일반 기능은 로그인 없이 쓰고, 등록·수정·삭제·승인·백업은 관리자(기본 **`admin / 1234`**, 실제 사용 전에 변경)만 할 수 있습니다.

**현재 구현 범위**: 문서 검색은 질문 단어가 청크에 포함된 개수로 순위를 매기는 단순 키워드 검색이고, 답변은 기본적으로 원문 발췌입니다. 선택적 LLM은 OpenAI 호환 Chat Completions로 연결하며 주소·모델·키 설정으로 OpenAI·동국 AI Chat·로컬 Ollama를 전환할 수 있습니다. 공통 호출은 모의 HTTP로 검증했고, 동국의 실제 API 정보와 실제 Ollama 연결은 아직 미검증입니다. 벡터·하이브리드 RAG, 공식 CII 계산, 규정 적용 자동 판정, DOCX·PPT 등록은 아직 연결 전입니다. 범위와 연결 계획은 [`docs/plans/2026-10-08-team-module-integration.md`](docs/plans/2026-10-08-team-module-integration.md)를 보세요.

## 프로젝트 구조

`frontend/`와 `backend/`는 각자 패키지 매니저를 가진 독립 프로젝트입니다. 최상위에는 패키지 매니저가 없고, 실행·테스트를 묶는 compose 파일만 있습니다([ADR 0009](docs/adr/0009-split-packages-and-compose.md)).

```text
sea-the-answer/
├─ compose.yaml          db + migrate + backend + frontend (운영), profile "e2e" (테스트 스택)
├─ compose.dev.yaml      개발 오버레이: 소스 마운트, 핫 리로드, DB·API 포트를 127.0.0.1에 공개
├─ .env.example          설정 예시 → .env 로 복사
├─ frontend/             Next.js 16 + React 19 — 사용자가 접속하는 유일한 진입점   [npm]
│  ├─ package.json, package-lock.json, Dockerfile, next.config.mjs
│  ├─ src/app/           페이지 라우트: /chat, /documents, /operations, /reports, /admin
│  ├─ src/views/ src/workspace/ src/lib/ src/styles/
│  ├─ src/proxy.js       /api/* 를 backend로 전달 (HAEDAP_API_ORIGIN)
│  ├─ public/            글꼴, PDF.js, Leaflet 등 오프라인 정적 리소스
│  └─ tests/             단위 테스트 (npm test)
├─ backend/              FastAPI + PostgreSQL                                       [uv]
│  ├─ pyproject.toml, uv.lock, .python-version, Dockerfile
│  ├─ api/               FastAPI 앱 — main.py(진입점), web/(보안·동시성), routes/(도메인별 경로), store/(DB·업무 로직)
│  ├─ tools/ (선택) 해사 데이터 조회·계산 Tool (서비스 런타임)
│  ├─ knowledge/         seed.json(기본 문서), documents/(기본 문서 원본 PDF), sample-data.json(가상 운항 예시)
│  └─ tests/             pytest
├─ migrations/           DB 스키마 마이그레이션 (SQL, up/down)                        [dbmate]
├─ scripts/ 오프라인 자료 정규화·전처리·CSV 적재·선박 매핑 (backend uv 환경)
├─ e2e/                  Playwright 브라우저 테스트 (화면 → API → DB)                [npm]
├─ docs/                 설계·명세·계획·ADR 등 모든 프로젝트 문서
└─ AGENTS.md             사람·에이전트 공통 작업 지침
```

구조와 요청 흐름은 [`docs/architecture.md`](docs/architecture.md)에 있습니다.

## 실행하기 (Docker)

준비물: **Docker Desktop**(Windows·macOS) 또는 **Docker Engine + Compose 플러그인**(Ubuntu). 첫 빌드에는 인터넷이 필요합니다. 모든 명령은 **저장소 최상위**에서 실행합니다.

1. 설정 파일을 만듭니다. 기본값으로도 이 PC에서는 바로 동작합니다. 공유 서버라면 `POSTGRES_PASSWORD`를 **처음 시작하기 전에** 바꾸세요.

   ```bash
   cp .env.example .env            # Windows PowerShell: Copy-Item .env.example .env
   ```

2. 실행합니다. 처음에는 이미지 빌드로 몇 분 걸립니다. `migrate` 서비스가 DB 마이그레이션을 적용한 뒤 backend가 시작하고, DB가 비어 있으면 기본 문서와 관리자 계정이 만들어집니다.

   ```bash
   docker compose up --build -d
   ```

3. 브라우저에서 <http://localhost:5173>을 엽니다.

| 하려는 일 | 명령 |
|---|---|
| 상태 확인 (세 서비스가 `healthy`인지) | `docker compose ps` |
| 로그 보기 | `docker compose logs -f backend` (또는 `frontend`, `db`) |
| 중지 (데이터 유지) | `docker compose down` |
| 코드 변경 후 다시 띄우기 | `docker compose up --build -d` |
| **모든 데이터 삭제** 후 처음부터 | `docker compose down -v` |
| 마이그레이션 상태 보기 | `docker compose run --rm migrate status` |

데이터는 Docker 볼륨(`haedap_db-data`, 백업 파일은 `haedap_backups`)에 남습니다. 다른 PC·서버에서 접속하게 하려면 `.env`의 `HAEDAP_BIND`·`HAEDAP_ALLOWED_HOSTS`를 설정합니다([사용 안내 7절](docs/user-guide.md#7-같은-네트워크의-팀원이-접속하기--서버에-올리기)). 새 버전으로 바꾸는 방법은 [사용 안내 8절](docs/user-guide.md#8-새-버전으로-바꾸기)에 있습니다.

## 개발하기

### Docker로 (권장)

```bash
docker compose -f compose.yaml -f compose.dev.yaml up --build
```

`frontend/`와 `backend/` 소스가 컨테이너에 마운트되어 저장하면 바로 반영됩니다(`next dev`, `uvicorn --reload`). 화면은 <http://localhost:5173>, API 문서는 <http://127.0.0.1:8000/docs>, DB는 `127.0.0.1:5432`(사용자·비밀번호는 `.env`)로 열립니다. 의존성 파일(`package-lock.json`, `uv.lock`)을 바꾸면 `--build`로 이미지를 다시 만듭니다.

### Docker 없이

PostgreSQL을 직접 준비하거나 DB만 compose로 띄웁니다(`docker compose -f compose.yaml -f compose.dev.yaml up -d db`). 최상위 `.env`에 `DATABASE_URL=postgresql://haedap:<POSTGRES_PASSWORD>@127.0.0.1:5432/haedap?sslmode=disable`을 넣습니다. 이 값 하나를 dbmate와 backend가 함께 씁니다.

```bash
# 마이그레이션 적용 (최상위에서, Node.js 필요 — dbmate가 .env의 DATABASE_URL을 읽음)
npx --yes dbmate@2.36.0 -d migrations --no-dump-schema up

# 터미널 1 — backend (Python 3.13, uv 필요: https://docs.astral.sh/uv/)
cd backend
uv sync
uv run --env-file ../.env uvicorn api.main:app --reload

# 터미널 2 — frontend (Node.js 24 + npm)
cd frontend
npm ci
npm run dev
```

새 의존성은 해당 폴더에서만 추가합니다: `cd backend && uv add <패키지>`, `cd frontend && npm install <패키지>`.

### DB 스키마 바꾸기

스키마는 최상위 `migrations/`의 SQL 파일로 관리하고 [dbmate](https://github.com/amacneil/dbmate)로 적용합니다([ADR 0010](docs/adr/0010-dbmate-migrations.md)).

```bash
docker compose run --rm migrate new add_ship_flag    # migrations/<시각>_add_ship_flag.sql 생성
# 파일의 -- migrate:up / -- migrate:down 아래에 SQL 작성
docker compose run --rm migrate up                   # 적용 (docker compose up 때도 자동 적용)
docker compose run --rm migrate rollback             # 마지막 파일 되돌리기
```

이미 커밋된 마이그레이션 파일은 고치지 말고 항상 새 파일을 추가합니다. Docker 없이 하려면 `docker compose run --rm migrate` 대신 `npx --yes dbmate@2.36.0 -d migrations --no-dump-schema`를 씁니다. Linux에서 컨테이너로 만든 파일은 root 소유일 수 있으니 필요하면 `sudo chown`으로 바꾸세요.

## 테스트

| 범위 | 위치 | 명령 |
|---|---|---|
| backend 단위·API | `backend/` | `uv run pytest` |
| frontend 단위 | `frontend/` | `npm test` |
| e2e (화면 → API → DB 전체 흐름) | 최상위 | 아래 두 줄 |

```bash
docker compose --profile e2e up --build --force-recreate --exit-code-from e2e e2e   # 테스트 (종료 코드 = 결과)
docker compose --profile e2e down                                                      # 테스트 스택 정리
```

e2e는 앱과 분리된 테스트 스택(`e2e-db`·`e2e-migrate`·`e2e-backend`·`e2e-frontend`)을 띄웁니다. DB는 메모리(tmpfs)에 있어 앱 데이터에 영향이 없고, 호스트에 포트를 열지 않으므로 앱이 실행 중이어도 됩니다. 실패 시 스크린샷·trace는 `e2e/test-results/`, HTML 보고서는 `e2e/playwright-report/`에 생깁니다.

- **`--force-recreate`를 빼지 마세요.** 테스트가 끝나도 Compose는 `e2e` 컨테이너만 멈추고 의존 서비스(`e2e-db` 등)는 계속 실행합니다. 이 옵션이 있어야 다음 실행 때 컨테이너를 새로 만들어 빈 DB에서 시작합니다(없으면 이전 데이터가 남아 "예시 데이터 넣기" 단계에서 실패).
- 의존 서비스까지 자동으로 멈추는 Compose 옵션은 없어서, 끝나면 `down`으로 정리합니다. `--attach-dependencies`는 쓰지 마세요. `e2e-migrate`가 끝나는 순간 중단되어 **테스트를 돌리지 않고도 종료 코드 0**이 나옵니다(2026-10-13 확인).

Docker 없이 e2e를 돌리려면 **빈 DB로 띄운 스택**에 대고 `e2e/`에서 `npm ci`, `npx playwright install chromium`, `npx playwright test`를 실행합니다(주소는 `E2E_BASE_URL`, 기본 `http://127.0.0.1:5173`). 시나리오가 예시 데이터를 넣고 건수를 확인하므로 데이터가 있는 DB에서는 실패합니다.

## 설정 (`.env`)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | `haedap` / `haedap` / `haedap-local` | compose DB. 비밀번호는 DB 볼륨을 처음 만들 때만 적용됨 |
| `PORT` | `5173` | 화면 포트 |
| `HAEDAP_BIND` | `127.0.0.1` | `0.0.0.0`이면 LAN·서버 접속 허용 |
| `HAEDAP_ALLOWED_HOSTS` | (비움) | localhost 외에 접속에 쓰는 호스트 이름·IP(쉼표 구분) |
| `OPENAI_MODEL` | (비움) | 모델 서버의 정확한 모델 ID. 비우면 모델 답변 비활성 |
| `OPENAI_API_KEY` | (비움) | `api.openai.com`의 OpenAI 서버에만 전송. 해당 호스트에서 필수 |
| `DONGUK_AI_CHAT_API_KEY` | (비움) | `dongguk.edu`·하위 도메인 또는 동국 AI Chat 게이트웨이 `factchat-cloud.mindlogic.ai`에만 전송. 해당 호스트에서 필수 |
| `LLM_API_BASE_URL` | `https://api.openai.com/v1` | OpenAI 호환 API 접두 주소. `/chat/completions`는 앱에서 붙임. backend에만 전달 |
| `LLM_RESPONSE_FORMAT` | `text` | 기본은 JSON 출력 지시와 앱 내부 검증. 지원 서버·모델에서 `json_object` 또는 `json_schema` 선택 |
| `MARITIME_DATA_API_TOKEN`, `MARITIME_DATA_DATABASE_URL` | (비움) | 해사 데이터 Tool 라우트(`/api/maritime-data/*`) 활성화 |
| `DATABASE_URL`, `HAEDAP_API_ORIGIN` | — | Docker 없이 실행할 때만 사용 (`DATABASE_URL`은 dbmate도 사용) |

### 모델 서버 연결

준비물은 실행 중인 OpenAI 호환 Chat Completions 서버와 그 서버의 모델 ID입니다. 루트 `.env`의 기존 DB 설정을 보존하고 모델 항목만 수정하세요. Docker Desktop에서 PC의 Ollama를 사용할 때 예시는 다음과 같습니다. 모델 자리표시는 `ollama list`에서 확인한 실제 설치 모델 ID로 바꿉니다.

서버 재시작 전에 기존 설정의 `OPENAI_BASE_URL` → `LLM_API_BASE_URL`, `OPENAI_RESPONSE_FORMAT` → `LLM_RESPONSE_FORMAT`으로 이름을 바꿉니다. 이전 두 이름은 더 이상 읽지 않으므로 이전 URL만 남겨 두면 기본 OpenAI 주소가 선택됩니다. `OPENAI_MODEL`·`OPENAI_API_KEY`는 유지하며, 기존 OpenAI 키 변수에 동국 키를 넣었다면 `DONGUK_AI_CHAT_API_KEY`로 옮깁니다. 두 키가 함께 있어도 대상 호스트의 키만 선택하며 로컬 Ollama·기타 호환 서버에는 두 키를 모두 보내지 않습니다. 자세한 호스트 규칙은 [공급자 계약](docs/specs/llm-provider.md#서버-설정)에 있습니다.

```dotenv
LLM_API_BASE_URL=http://host.docker.internal:11434/v1
OPENAI_MODEL=replace-with-installed-model-id
OPENAI_API_KEY=
DONGUK_AI_CHAT_API_KEY=
LLM_RESPONSE_FORMAT=text
```

루트에서 `docker compose up -d --build backend frontend`로 코드와 환경변수를 반영합니다. 직접 실행하는 백엔드에서는 URL을 `http://127.0.0.1:11434/v1`로 바꾸고 재시작하세요. 컨테이너 안의 `localhost`는 컨테이너 자신입니다. 호스트의 Ollama 바인딩·방화벽 설정과 Linux 안내는 [공급자 계약](docs/specs/llm-provider.md#접속-위치별-기본-url)을 따릅니다.

예상 결과: `/api/health`의 `llmConfigured`가 true가 되고 모델 답변 모드를 사용할 수 있습니다. 실제 성공은 근거가 있는 질문에서 `generation=llm`, 유효 인용, 모델 실패 경고 없음까지 확인해야 합니다. 실패·잘린 응답·위조 인용은 `MODEL_FAILED_EXTRACTIVE_FALLBACK`과 원문 발췌로 전환됩니다. 설정이 잘못되면 `MODEL_NOT_CONFIGURED`입니다. 동국은 공식 API 주소·모델·인증 정보를 사용하며 웹 채팅 주소(`/dashboard/chat`)를 API 주소로 넣지 않습니다.

25초를 넘는 추론은 실패 전환되므로 로컬 모델을 미리 적재해 확인하세요. 기본 호환 요청은 공급자별 선택 필드를 생략하여 기존 2,200 출력 토큰 한도도 보내지 않습니다. 생성 한도는 모델 서버 설정에 따르며 앱은 최대 5개 답변 문장과 인용을 검증합니다. 상세 형식·제약은 [공급자 계약](docs/specs/llm-provider.md)에 있습니다.

CI 워크플로는 [별도 PR #14](https://github.com/dudco/sea-the-answer/pull/14)로 분리했습니다. 수행한 검증과 미검증 범위는 [변경 이력](docs/changelog.md)에 기록합니다.

## API

화면이 호출하는 경로는 모두 `/api/*`이며 Next.js가 backend로 전달합니다. 계약은 [`docs/specs/api.md`](docs/specs/api.md)에 있습니다.

| 경로 | 주요 기능 |
|---|---|
| `GET /api/health` | DB 연결·기능 상태와 CSRF 토큰 확인 |
| `POST /api/ask`, `/api/search` | 통합 답변과 문서 근거 검색 |
| `GET /api/documents`, `/api/operations`, `/api/reports` | 문서·운항·보고서 조회 |
| `POST /api/changes`, `/api/changes/review` | 관리자 변경과 승인 |
| `POST /api/tools/calculate_emissions`, `/api/tools/voyage_time` | 배출량·항해 시간 계산 |
| `/api/auth/*`, `/api/users`, `/api/history`, `/api/logs`, `/api/backups*` | 인증·사용자·이력·백업 |

변경 요청(POST)은 `GET /api/health` 응답의 `csrfToken`을 `X-Haedap-Token` 헤더에 넣어야 합니다.

## 해사 데이터 Tool (선택)

공개 DWT 후보를 별도로 연결해 MRV 보고 CO₂·추정 거리 기반 **참고 탄소집약도**를 제공한다. 참고값의 출처·시점/거리/DCS 범위 미검증과 계산 차단 사유를 함께 반환하며 공식 CII나 등급이 아니다. 참조 적재와 호출은 [사용 안내](docs/user-guide.md#dwt-후보를-참고-지표에-연결하기-선택), 계약은 [tools.md](docs/specs/tools.md)를 따른다. 이 기능은 서버 API이며 화면 자동 연결은 포함하지 않는다.

읽기 전용 조회·CO₂ 계산은 [`backend/tools/`](backend/tools/), 자료 정규화·전처리·적재는 [`scripts/`](scripts/)에 있습니다. backend와 같은 uv 환경을 사용하고, 해사 DDL도 루트 `migrations/`에서 앱 DDL과 함께 적용합니다. 기본은 앱과 같은 DB입니다. 기존 `ships`와의 연결은 검토한 명시적 매핑만 허용하며, 연간 MRV를 일별 `operations`로 바꾸거나 외부 선박을 대량 자동 등록하지 않습니다.

자료 준비 명령은 호스트 PC에서 실행하므로 Python·uv가 필요합니다. 먼저 [사용 안내의 DB 연결·migration 준비](docs/user-guide.md#마이그레이션전처리적재검증)를 따르세요. Docker DB를 쓸 때도 로컬 DB 포트와 호스트용 `DATABASE_URL`이 필요합니다.

```powershell
# 마이그레이션·호스트 DB 연결 준비 후, 저장소 최상위에서 실행합니다.
uv sync --project backend --group data
uv run --locked --project backend --group data python -m scripts.prepare_maritime_data --source D:/Data --out data/maritime-data/new-run
uv run --locked --project backend python -m scripts.load_data --data-dir data/maritime-data/new-run
# 미리보기에서 입력 파일·건수를 확인한 뒤 적용
uv run --locked --project backend python -m scripts.load_data --data-dir data/maritime-data/new-run --apply
```

적재기는 기본 미리보기에서는 DB에 연결하지 않으며 `--apply`에서만 migration 이력을 확인하고 이미 생성된 빈 해사 테이블에 CSV를 넣습니다. DDL은 실행하지 않습니다. `MARITIME_DATA_API_TOKEN`을 설정하면 같은 backend에 `/api/maritime-data/*`가 마운트됩니다(서버 전용 Bearer 토큰 필요, 화면 어댑터는 아직 없음). 별도 해사 DB를 선택한 경우에는 해당 DB에도 기본 init과 해사 마이그레이션이 필요합니다. 자세한 설정·검증·기존 스키마 채택 및 선박 연결은 [사용 안내 10절](docs/user-guide.md#10-해사-데이터-tool-선택), 호출 형식은 [API 명세](docs/specs/tools.md), 이번 변경 범위는 [ADR 0011 제안](docs/adr/0011-tools-runtime-and-data-preparation.md)을 보세요.

## 문서

| 문서 | 내용 |
|---|---|
| [`docs/README.md`](docs/README.md) | 전체 문서 목록과 작성 규칙 |
| [`docs/architecture.md`](docs/architecture.md) | 시스템 구조, 요청 흐름, 모듈 경계, 보안 경계 |
| [`docs/data-model.md`](docs/data-model.md) | PostgreSQL 테이블, 상태 값, 백업 형식 |
| [`docs/user-guide.md`](docs/user-guide.md) | 사용·운영 안내, 버전 교체, 문제 해결 |
| [`docs/specs/`](docs/specs/) | API·통합 답변 등 구현 계약 |
| [`docs/plans/`](docs/plans/) | 작업 계획과 진행 상태 |
| [`docs/adr/`](docs/adr/) | 주요 설계 결정 기록 |
| [`docs/changelog.md`](docs/changelog.md) | 변경 이력과 검증 기록 |
| [`AGENTS.md`](AGENTS.md) | 사람·코딩 에이전트 공통 작업 지침 |

팀 보고서는 Notion에서 관리합니다: <https://app.notion.com/p/dudco/3dc1cb63e55380e98972eda1ce1040b5>
