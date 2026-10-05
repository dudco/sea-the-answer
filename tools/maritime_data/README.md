# 해사 데이터 도구

최종 업데이트: 2026-10-05. 모든 명령은 저장소 루트에서 실행합니다.

| 위치 | 역할 |
|---|---|
| `query.py`, `calculations.py`, `agent.py` | 읽기 전용 조회, CO₂ 산술, 고정 조건 조회 도우미 |
| `api.py` | 별도 Bearer 토큰을 쓰는 FastAPI 어댑터 |
| `scripts/` | 전처리·적재·기존 스키마 이름 전환 |
| `schema/` | 실행용 DDL·적재 검증 SQL·기계용 데이터 사전 |
| `tests/` | 계약·인증·계산·마이그레이션 검증 |

## 준비와 실행

Python 3.12 또는 3.13과 PostgreSQL을 준비합니다. 통합 앱 개발 환경이 있으면 기존 `.venv`를 그대로 사용합니다. 도구만 사용할 때는 아래처럼 설치합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r tools/maritime_data/requirements.lock.txt
Copy-Item tools/maritime_data/.env.example .env.local
.\.venv\Scripts\python.exe -m uvicorn tools.maritime_data.api:create_app --factory --host 127.0.0.1 --port 8001
```

`.env.local`이 이미 있으면 복사 명령을 생략하고 필요한 키를 기존 파일에 추가합니다. `DATABASE_URL`은 PostgreSQL 연결 주소, `MARITIME_DATA_API_TOKEN`은 직접 생성한 32자 이상 토큰입니다. `/api/health`의 `database_checked=false`는 DB 연결을 검증하지 않았다는 뜻입니다. 인증을 포함한 명세는 http://127.0.0.1:8001/docs 에서 확인합니다.

## 전처리와 적재

```powershell
.\.venv\Scripts\python.exe tools/maritime_data/scripts/prepare_maritime_data.py --source D:/Data --out data/maritime-data/new-run
./tools/maritime_data/scripts/load-maritime-data.ps1 -DataDir data/maritime-data/new-run
.\.venv\Scripts\python.exe tools/maritime_data/scripts/describe_maritime_data.py
.\.venv\Scripts\python.exe -m pytest -q tools/maritime_data/tests
.\.venv\Scripts\python.exe tools/maritime_data/scripts/test_prepare_maritime_data.py
```

적재는 로컬 PostgreSQL만 지원하며 이미 스키마가 있으면 중단합니다. 새 데이터 버전은 검증 SQL의 기대 건수를 검토합니다. 503 오류는 DB 연결·스키마 적재 상태를 확인하세요. 테스트용 PostgreSQL은 `MARITIME_DATA_TEST_DATABASE_URL`로 지정하며 미설정 시 DB 테스트는 건너뜁니다.

이전 `role4/.env.local`을 사용한 환경은 필요한 설정을 저장소 루트 `.env.local`에 옮깁니다. 기존 `role4` 스키마·설정이 있는 환경은 서버를 중지하고 `python tools/maritime_data/scripts/migrate_maritime_data.py`로 미리 확인한 후 `--apply`로 이름을 변경합니다. 설정 충돌 시 중단하며 `.env.local.before-maritime-data` 백업을 남깁니다. 실제 데이터 폴더는 이동하지 않습니다.

## 앱 연동과 문서

`from tools.maritime_data import query, calculations, agent`로 공통 로직을 가져옵니다. 직접 호출하는 앱이 사용자 권한을 검사해야 합니다. 독립 API는 토큰 인증을 사용하며 통합 앱의 세션·감사는 해당 앱 어댑터가 담당합니다. 기존 Node UI와 자동으로 연결되지는 않습니다.

- [조회·계산 API 계약](../../docs/maritime-data/API.md)
- [테이블·단위·품질 계약](../../docs/maritime-data/DATA_CONTRACT.md)
- [원본 확보·참조 자료·데이터 버전](../../docs/maritime-data/DATA_ACCESS.md)

실제 MRV와 합성 Noon은 분리합니다. 공식 CII 등급·규정 적합성·실제 LLM 호출은 이 도구의 검증 완료 범위에 포함하지 않습니다.
