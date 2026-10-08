# 해답 — SEA THE ANSWER

현재 버전 **1.4.0** · 마지막 업데이트 **2026-10-09**

선내 문서 근거와 운항 기록을 함께 보여 주는 선박 업무 지원 앱입니다. 화면은 Next.js, `/api/*`는 Python FastAPI, 저장소는 PostgreSQL을 사용합니다. 문서 검색은 한국어·영어 단어의 일치도를 이용합니다. 답변은 기본적으로 근거 문장 발췌이며, 외부 모델은 선택 사항입니다. 벡터 검색, 공식 CII 산정, 규정 자동 판정은 아직 구현되지 않았습니다.

## 준비물

| 항목 | 용도 |
|---|---|
| Node.js 24 이상과 npm | Next.js 화면 빌드·실행 |
| Python 3.11 이상 | FastAPI 실행 |
| PostgreSQL 서버와 `psql` | 데이터 저장과 초기 스키마 적용 |
| 인터넷 | 최초 npm·Python 패키지 설치 |

모든 명령은 별도 언급이 없다면 **저장소 최상위 폴더**에서 실행합니다. Windows PowerShell에서 `npm`이 차단되면 `npm.cmd`를 사용하세요.

## 처음 설치하고 실행하기

1. PostgreSQL에 이 앱 전용 빈 데이터베이스와 사용자를 만듭니다. 아래 예시는 로컬 개발용입니다. 비밀번호는 직접 정하고 Git에 올리지 마세요.

   ```sql
   CREATE USER haedap_user WITH PASSWORD 'choose-your-own-password';
   CREATE DATABASE haedap OWNER haedap_user;
   ```

2. `.env.example`을 `.env`로 복사하고 `DATABASE_URL`의 사용자·비밀번호·호스트·DB 이름을 실제 값으로 바꿉니다. 비밀번호에 `@`, `:` 등의 문자가 있으면 URL 인코딩해야 합니다.

   ```powershell
   Copy-Item .env.example .env
   ```

3. **빈 DB에 한 번만** 스키마를 적용합니다. `psql`은 `.env`를 자동으로 읽지 않으므로 연결 문자열을 직접 넘깁니다. 기존 데이터가 있는 DB에는 적용하지 마세요.

   ```powershell
   psql 'postgresql://haedap_user:choose-your-own-password@127.0.0.1:5432/haedap' -f backend/pyapi/schema.sql
   ```

4. 의존성을 설치하고 앱을 실행합니다.

   ```powershell
   npm ci
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
   npm run build
   npm start
   ```

   macOS/Linux에서는 가상 환경 명령을 `python3 -m venv .venv`, `./.venv/bin/python -m pip install -r backend/requirements.txt`로 바꿉니다. Windows에서는 `scripts\start.cmd`가 Node·Python 패키지 설치와 화면 빌드를 확인하고 실행할 수 있습니다. PostgreSQL과 `.env`, 스키마는 먼저 준비해야 합니다.

5. 브라우저에서 `http://127.0.0.1:5173`을 엽니다. Next.js가 내부 FastAPI `127.0.0.1:8000`으로 `/api/*`를 전달합니다. `GET /api/health`의 `storage`가 `postgresql`이면 API가 DB에 연결된 것입니다. 최초 관리자 계정은 기존 앱과 같은 `admin / 1234`이므로 실제 사용 전에 비밀번호를 바꾸세요. DB가 비어 있으면 기본 문서가 등록됩니다.

## 기존 SQLite 데이터 옮기기

기존 DB 파일은 기본적으로 `backend/data/haedap.sqlite`입니다. 이전 중에는 서버를 중지하고 **원본 파일을 별도로 복사해 보관**하세요. 이전 대상은 스키마만 적용된 **빈 PostgreSQL DB**여야 합니다. 도구는 원본 SQLite를 읽기 전용으로 열고, `--apply`를 넣기 전에는 테이블별 행 수만 보여 줍니다. 데이터가 이미 있는 PostgreSQL 대상은 거부합니다. 이전에 실패하면 PostgreSQL 트랜잭션이 롤백됩니다.

```powershell
Copy-Item backend/data/haedap.sqlite backend/data/haedap.sqlite.before-postgres
.\.venv\Scripts\python.exe -m backend.pyapi.migrate_sqlite --sqlite backend/data/haedap.sqlite
.\.venv\Scripts\python.exe -m backend.pyapi.migrate_sqlite --sqlite backend/data/haedap.sqlite --apply
```

macOS/Linux는 위 Python 경로를 `./.venv/bin/python`으로 바꿉니다. `Copied:` 뒤의 건수를 확인한 다음 앱을 시작합니다. SQLite의 기존 사용자, 문서, 운항 기록, 보고서, 질의 이력, 변경 기록, 백업 설정을 테이블 단위로 복사합니다. 파일 시스템의 기존 백업 파일은 별도 보관해야 합니다.

## 개발과 API

개발 중에는 최상위 폴더에서 터미널 두 개를 엽니다. 두 명령 모두 `.env`를 읽습니다.

```powershell
npm run dev:backend
npm run dev:frontend
```

FastAPI는 `backend/pyapi/workspace_api.py`, PostgreSQL 동작은 `backend/pyapi/workspace_store.py`, 스키마는 `backend/pyapi/schema.sql`에 있습니다. 기존 화면이 호출하는 경로를 그대로 유지합니다.

| 경로 | 주요 기능 |
|---|---|
| `GET /api/health` | DB 연결·기능 상태와 CSRF 토큰 확인 |
| `POST /api/ask`, `/api/search` | 통합 답변과 문서 근거 검색 |
| `GET /api/documents`, `/api/operations`, `/api/reports` | 문서·운항·보고서 조회 |
| `POST /api/changes`, `/api/changes/review` | 관리자 변경과 승인 |
| `POST /api/tools/calculate_emissions`, `/api/tools/voyage_time` | 배출량·항해 시간 계산 |
| `/api/auth/*`, `/api/users`, `/api/history`, `/api/logs`, `/api/backups*` | 인증·사용자·이력·백업 |

브라우저 API 사용 예: 화면을 먼저 열고 `fetch('/api/health').then(r => r.json()).then(console.log)`을 개발자 콘솔에서 실행하면 상태 JSON을 볼 수 있습니다. 변경 요청은 health 응답의 `csrfToken`을 `x-haedap-token` 헤더에 넣습니다. 일반 조회·질문은 로그인 없이 가능하고 변경·관리 기능에는 관리자 로그인이 필요합니다.

`.env` 설정: `DATABASE_URL`은 필수입니다. `PORT`는 공개 화면 포트(기본 5173), `HAEDAP_API_ORIGIN`은 내부 API 주소(기본 `http://127.0.0.1:8000`), `HAEDAP_BACKUP_DIR`은 백업 저장 경로입니다. `OPENAI_API_KEY`와 `OPENAI_MODEL`을 모두 넣으면 근거 기반 모델 답변을 선택할 수 있습니다. 키는 서버에서만 사용합니다. 설정을 바꾼 뒤 두 프로세스를 다시 시작하세요.

문서 JSON 수집 명령 `npm run ingest -- backend/knowledge/seed.json`과 기존 Node 백엔드 파일은 저장소에 남아 있지만, 이 명령은 **레거시 SQLite 경로**를 사용합니다. 새 PostgreSQL 수집 경로는 아직 제공하지 않습니다. 문서 PDF/텍스트 등록은 화면 API를 사용하세요. `npm run check` 역시 기존 Node/SQLite 검사입니다.

## 검증과 문제 해결

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_fastapi_api.py -q
npm test
```

`npm test`는 기존 Node 테스트와 새 Python 테스트를 실행합니다. 2026-10-09에 Python API 테스트 4개와 Python 문법 검사를 통과했습니다. 이 환경에는 PostgreSQL 서버와 Node 실행 파일이 없어 실제 PostgreSQL 통합, `npm test`, 브라우저 흐름은 아직 검증하지 못했습니다. 외부 모델 호출도 검증하지 않았습니다.

화면에 연결 오류가 뜨면 PostgreSQL 실행 상태, `DATABASE_URL`, 스키마 적용, `npm run dev:backend` 로그를 순서대로 확인하세요. `DATA_SOURCE_UNAVAILABLE`은 DB 연결 또는 스키마 문제일 수 있습니다. 8000 포트가 이미 사용 중이면 `.env`의 `HAEDAP_API_ORIGIN`을 예를 들어 `http://127.0.0.1:8100`으로 바꾸고 재시작하세요. `npm start`는 먼저 `npm run build`로 만든 화면이 필요합니다. Python 패키지 오류는 위 `pip install -r backend/requirements.txt` 명령을 다시 실행하세요.

## 파일 구조와 변경 이력

`frontend/`는 Next.js 화면, `backend/pyapi/`는 현재 FastAPI·PostgreSQL 구현, `backend/tests/`는 API 테스트, `scripts/`는 실행 도구입니다. `backend/*.mjs`는 이전 Node/SQLite 구현을 보존한 파일입니다. API 계약·DB 구현을 바꾸면 이 README의 실행 예제와 검증 기록도 함께 갱신합니다.

- **2026-10-09:** 기존 `/api/*` 경로를 FastAPI로 옮기고 PostgreSQL 스키마, SQLite 일회성 이전 도구, Python API 테스트, 실행 명령을 추가했습니다. 실제 PostgreSQL 연결 검증은 남아 있습니다.
- **2026-10-08:** Next.js 공개 진입점과 Node/SQLite API 1.4.0.
