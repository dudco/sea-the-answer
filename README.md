# 해,답 · 선원 업무 지원

규정 문서를 검색하고 근거를 확인한 뒤, 운항 수치를 계산하고 보고서 초안을 저장하는 웹 앱입니다.

**이 README가 프로젝트의 기본 실행·구현 안내서입니다.** 처음 참여한 사람도 순서대로 따라 할 수 있도록 유지합니다. 앞으로 기능·설정·실행 방법이 바뀌면 해당 설명과 맨 아래 변경 이력을 함께 업데이트합니다.

마지막 업데이트: **2026-10-05**

## 목차

- [1. 현재 구현 상태](#1-현재-구현-상태)
- [2. 처음 실행하기](#2-처음-실행하기)
- [3. 화면에서 기능 확인하기](#3-화면에서-기능-확인하기)
- [4. 구조와 파일 역할](#4-구조와-파일-역할)
- [5. 검색할 문서 추가하기](#5-검색할-문서-추가하기)
- [6. AI 답변 생성 연결하기](#6-ai-답변-생성-연결하기)
- [7. DB 저장과 백업](#7-db-저장과-백업)
- [8. 기능 구현·수정 순서](#8-기능-구현수정-순서)
- [9. API 직접 호출하기](#9-api-직접-호출하기)
- [10. 테스트하기](#10-테스트하기)
- [11. 문제 해결](#11-문제-해결)
- [12. 다음 작업과 문서 관리](#12-다음-작업과-문서-관리)
- [13. 변경 이력](#13-변경-이력)

## 해사 데이터 · PostgreSQL 조회·계산 도구

코드·전처리·SQL·테스트는 **[tools/maritime_data/](tools/maritime_data/README.md)** 에 있습니다. 문서는 [API 계약](docs/maritime-data/API.md), [데이터 계약](docs/maritime-data/DATA_CONTRACT.md), [원본 확보](docs/maritime-data/DATA_ACCESS.md) 3개로 정리했습니다. 원본·CSV·DB·비밀번호는 Git에 포함하지 않습니다. 기존 Node UI는 이 API를 자동 호출하지 않습니다.

Python 3.12/3.13과 PostgreSQL을 준비하고 아래 명령을 **저장소 루트**에서 실행합니다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r tools/maritime_data/requirements.lock.txt
Copy-Item tools/maritime_data/.env.example .env.local
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
# .env.local에 DATABASE_URL과 생성한 MARITIME_DATA_API_TOKEN을 설정
.\.venv\Scripts\python.exe -m uvicorn tools.maritime_data.api:create_app --factory --host 127.0.0.1 --port 8001
```

기존 `.env.local`은 복사로 덮어쓰지 않고 필요한 키만 추가합니다. 명세는 http://127.0.0.1:8001/docs 에서 확인합니다. 모든 도구 요청은 Bearer 토큰을 사용합니다. 503 오류는 PostgreSQL 연결·적재 상태를 확인하세요. 공식 CII 등급은 반환하지 않습니다.

```powershell
.\.venv\Scripts\python.exe tools/maritime_data/scripts/prepare_maritime_data.py --source D:/Data --out data/maritime-data/new-run
./tools/maritime_data/scripts/load-maritime-data.ps1 -DataDir data/maritime-data/new-run
.\.venv\Scripts\python.exe -m pytest -q tools/maritime_data/tests
.\.venv\Scripts\python.exe tools/maritime_data/scripts/test_prepare_maritime_data.py
```

이미 전처리한 CSV는 첫 명령을 생략합니다. 적재는 로컬 DB만 지원하고 기존 스키마가 있으면 중단하며 실패 시 롤백합니다. 새 데이터는 검증 SQL의 기대 건수를 검토하세요. `MARITIME_DATA_TEST_DATABASE_URL`이 있어야 실제 DB 테스트가 실행됩니다. 기존 스키마·설정 이름의 전환은 [도구 안내](tools/maritime_data/README.md)를 따르며, 직접 앱에 연결할 때는 호출하는 백엔드가 사용자 권한을 검사합니다.

## 1. 현재 구현 상태

진행 순서는 **설계 → UI 프로토타입 → RAG/DB/Tool → 통합 → 평가**입니다. 현재는 **RAG/DB/Tool의 로컬 MVP와 주요 화면 연결까지 구현한 상태**입니다. MVP는 핵심 흐름을 확인할 수 있는 첫 구현을 뜻합니다.

| 단계 | 현재 상태 | 남은 내용 |
|---|---|---|
| 설계 | 화면과 주요 사용 흐름 구체화 | 실제 데이터·운영 환경의 상세 설계 |
| UI 프로토타입 | 대시보드, 지도, 검색, 계산, 보고서, 모바일 화면 구현 | 사용자 피드백 반영 |
| RAG/DB/Tool | 문서 수집·검색, SQLite 저장, 계산 API 구현 | 문서 확충, 실제 모델 호출 검증, 검색 고도화 |
| 통합 | 검색·근거·보고서·계산 연결, 같은 네트워크용 LAN 실행 | 실제 선박 DB·AIS·기상 연결 |
| 평가 | 기능 테스트와 브라우저 동작 확인 | 검색 정확도·AI 답변 품질·성능 평가 |

현재 검색은 **키워드 기반**이며 임베딩·벡터 검색은 아직 없습니다. 기본 상태에서는 **검색된 문단을 그대로 표시**합니다. 외부 모델 연동 코드는 있지만 실제 호출은 아직 검증하지 않았습니다. 운항 수치는 가상 데이터이며 공식 CII 등급은 산정하지 않습니다.

## 2. 처음 실행하기

### 준비물

| 준비물 | 설명 |
|---|---|
| 프로젝트 폴더 전체 | 화면 파일뿐 아니라 `backend/`, `knowledge/`, 서버 파일도 함께 받아야 합니다. |
| 서버를 실행할 PC | Windows는 실행 파일을 제공하며, macOS/Linux는 Node 명령으로 실행합니다. |
| 접속할 기기의 웹 브라우저 | 서버 PC뿐 아니라 같은 네트워크의 PC·휴대폰·태블릿에서도 사용할 수 있습니다. 접속만 하는 기기에는 Node나 프로젝트 설치가 필요 없습니다. |
| Node.js 22.13 이상 또는 호환되는 VS Code | 실행 도구가 `node:sqlite`를 사용할 수 있는 런타임을 찾습니다. |
| API 키·인터넷 | 외부 AI 사용 시 필요합니다. 지도 배경·공식 원문 링크도 인터넷을 사용합니다. |

기본 검색·DB·계산에는 외부 API 키가 필요하지 않습니다. 현재 외부 npm 패키지를 사용하지 않아 **`npm install`과 별도 DB 설치도 필요하지 않습니다.**

### 가장 쉬운 실행 방법: 더블클릭

1. 프로젝트 폴더에서 **`start.cmd`를 더블클릭**합니다.
2. 실행 창에 `HAEDAP: http://127.0.0.1:5173`이 나오면 창을 열어 둡니다.
3. 브라우저에서 **http://127.0.0.1:5173**을 엽니다.
4. 화면 위에 **문서 검색 연결됨**이 표시되면 준비가 끝났습니다.
5. 종료하려면 실행 창에서 **Ctrl+C**를 누릅니다.

다른 기기에서도 접속하려면 `start.cmd` 대신 **`start-lan.cmd`를 더블클릭**합니다. 두 실행 파일은 같은 서버·DB를 사용하며 접속 허용 범위만 다릅니다. 한 번에 필요한 실행 파일 하나만 켜세요.

첫 실행 시 `data/haedap.sqlite` 파일과 초기 문서 4개가 자동 생성됩니다. 기존 DB가 있으면 내용을 유지합니다. `index.html`을 더블클릭하는 대신 서버 주소로 접속하세요.

### 터미널에서 실행하기: Windows

이 문서의 명령은 모두 **프로젝트 폴더를 연 PowerShell 터미널**에서 실행합니다. VS Code에서 프로젝트 폴더를 연 뒤 **터미널 → 새 터미널**을 선택하세요. `Get-Location`으로 현재 폴더를 확인할 수 있습니다.

```powershell
.\start.cmd
```

이 명령은 더블클릭과 동일한 실행 경로입니다. **현재 PC에는 `node`·`npm` 명령이 없어도 VS Code 런타임을 자동으로 찾아 실행하도록 조정했습니다.**

같은 네트워크의 다른 기기에도 열려면 다음을 실행합니다.

```powershell
.\start-lan.cmd
```

PowerShell 스크립트를 직접 호출해도 같은 방식으로 동작합니다.

```powershell
# 이 PC에서만 사용
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1

# 같은 네트워크의 다른 기기에서도 사용
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1 -Lan
```

기본 포트가 사용 중이면 다른 번호로 실행합니다. 이 경우 접속 주소도 `http://127.0.0.1:5174`로 바뀝니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -Port 5174
```

LAN 모드의 포트도 `powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1 -Lan -Port 5174`로 지정합니다. 포트 우선순위는 실행 시 지정값 → `PORT` 환경변수 또는 `.env` 값 → 기본 `5173`입니다.

실행 환경만 확인하려면 아래 명령을 사용합니다. 실제로 선택한 실행 파일, `SQLite ready`, Node 버전이 표시됩니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1 -Task check
```

Node나 VS Code를 별도 경로에 설치했다면 `-NodePath '실제 실행 파일 경로'`를 지정하거나 `HAEDAP_NODE` 환경변수에 경로를 넣습니다. 호환되지 않는 런타임은 건너뛰고 다음 설치 위치를 확인합니다.

### Node가 설치된 PC 또는 macOS/Linux에서 실행하기

터미널에서 프로젝트 폴더로 이동한 뒤 실행합니다. 아래 명령은 Node가 PATH에 등록된 환경에서 사용합니다. Windows에서 `node`를 찾을 수 없으면 위의 `start.cmd` 방식을 사용하세요.

```powershell
node --version
npm start
```

LAN 모드와 포트 변경도 가능합니다.

```sh
# 같은 네트워크에 공유
npm run start:lan

# 포트까지 지정
node server.mjs --lan --port 5174
```

Windows 실행 도구는 이 PC에서 검증했습니다. macOS/Linux용 Node 명령은 공통 서버 코드를 사용하지만 해당 운영체제 실기기 검증은 아직 하지 않았습니다.

### 다른 기기에서 접속하기

1. 서버 PC와 사용할 기기를 같은 공유기·신뢰하는 네트워크에 연결합니다. PC가 유선이고 휴대폰이 Wi-Fi여도 같은 네트워크면 가능합니다.
2. 서버 PC에서 **`start-lan.cmd`** 또는 `start.ps1 -Lan`으로 실행합니다.
3. 실행 창의 `LAN (Wi-Fi): http://...:5173` 같은 줄을 찾습니다.
4. 다른 기기의 브라우저에 **그 LAN 주소를 그대로 입력**합니다. `127.0.0.1`, `localhost`, `0.0.0.0`은 다른 기기에서 입력할 접속 주소가 아닙니다.
5. 화면의 **문서 검색 연결됨**을 확인하고 검색·계산을 사용합니다. 서버 PC의 실행 창은 열어 둡니다.

출력 예시입니다. `192.168.0.20`은 예시이므로 실제 실행 창에 표시된 주소를 사용하세요.

```text
HAEDAP: http://127.0.0.1:5173
Mode: LAN
LAN (Wi-Fi): http://192.168.0.20:5173
```

네트워크 주소가 여러 개면 접속할 기기와 같은 Wi-Fi/이더넷 쪽 주소를 선택합니다. Wi-Fi를 바꿨거나 IP 주소가 바뀌면 서버를 재시작해 새 주소를 확인합니다. LAN 모드는 실행 PC의 IPv4 주소와 연결된 서브넷만 허용하며 IPv6·공개 인터넷 배포는 이번 범위에 포함하지 않습니다.

**접속 기기들은 서버 PC의 문서·현재 보고서 초안 1개를 함께 사용합니다.** 기기별 독립 계정은 없고 동시 편집은 저장 버전 충돌로 확인합니다. 서버를 끄거나 PC가 절전 상태가 되면 접속이 끊깁니다.

### 다른 기기에서 연결되지 않을 때: Windows 방화벽

서버 PC에서 LAN 주소가 열리는데 다른 기기에서 열리지 않으면 방화벽과 공유기의 기기 간 통신 차단 여부를 확인합니다. Windows 방화벽 허용이 필요할 때는 **신뢰하는 개인/도메인 네트워크에서** 관리자 PowerShell을 열고 프로젝트 폴더로 이동해 다음을 실행합니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup-lan-firewall.ps1 -Port 5173
```

이 도구는 지정 TCP 포트를 **개인/도메인 프로필 + 로컬 서브넷**에만 허용합니다. 같은 이름의 규칙이 있으면 기존 설정을 유지하고 표시합니다. 서버 포트를 바꿨으면 방화벽 설정도 같은 번호를 사용합니다. 실행 도구가 방화벽을 자동으로 변경하지는 않습니다.

현재 네트워크 종류를 확인하는 명령입니다.

```powershell
Get-NetConnectionProfile | Select-Object Name, NetworkCategory
```

`Public`이면 위 규칙은 해당 네트워크를 열지 않습니다. 가정·사무실 등 직접 신뢰할 수 있는 네트워크에서 사용하세요. 학교·공공 Wi-Fi는 기기 간 통신 자체를 차단할 수 있습니다. **2026-09-28 현재 이 PC의 Wi-Fi는 `Public`으로 확인했으며 공용 네트워크 방화벽 설정은 변경하지 않았습니다.** 실제 다른 기기에서의 접속은 별도 확인이 필요합니다.

추가한 규칙을 제거하려면 관리자 PowerShell에서 실행합니다.

```powershell
Remove-NetFirewallRule -Name 'Haedap-LAN-TCP-5173'
```

방화벽 설정 범위는 [Microsoft의 New-NetFirewallRule 문서](https://learn.microsoft.com/en-us/powershell/module/netsecurity/new-netfirewallrule)를 참고하세요.

### 다른 PC에서 서버 자체를 실행하려면

프로젝트 폴더와 Node.js 22.13 이상 또는 호환 VS Code가 필요합니다. Windows에서는 `start.cmd`, macOS/Linux에서는 `npm start`로 실행합니다. 새 환경에 `data/`가 없으면 초기 문서로 새 DB가 만들어집니다. 기존 DB까지 옮기려면 [DB 저장과 백업](#7-db-저장과-백업)을 따릅니다. `.env`의 API 키는 새 서버에서 별도로 설정하고, 단순히 브라우저로 접속할 기기에는 프로젝트나 키를 복사하지 않습니다.

## 3. 화면에서 기능 확인하기

| 순서 | 할 일 | 정상 동작 |
|---|---|---|
| 1 | **규정 검색**에서 `연료 황 함유량` 검색 | 관련 문단과 출처 표시 |
| 2 | 인용 번호 또는 **근거 문서** 선택 | 저장 문서의 내용·버전·출처 확인 |
| 3 | **보고서에 담기** 선택 | 내용과 근거가 초안에 추가됨 |
| 4 | 제목·내용 확인 후 **초안 저장** 선택 | DB 저장 안내 표시 |
| 5 | **DB 초안 불러오기** 선택 | 저장한 초안이 열림. 기존 편집 내용이 있으면 교체 확인 표시 |
| 6 | **CII · 배출량**에서 수치 변경 후 **다시 계산하기** 선택 | 서버 계산 결과와 실행 기록 저장 |
| 7 | `초콜릿 케이크 레시피` 검색 | 근거가 충분하지 않다는 안내 표시 |

계산 예시: 연료 `100`, 계수 `3`, DWT `1000`, 거리 `100`이면 **CO₂ 300 t**, **단순 집약도 3000 gCO₂/(DWT·nm)**입니다. 초기 표시값은 로컬 미리보기이며, 다시 계산하기를 누르면 서버 Tool을 호출합니다.

**실행 환경 설정**의 `문서 검색 + DB + 계산 도구`는 실제 백엔드를 사용합니다. 샘플 모드는 기존 준비된 응답·오류 상황을 체험하며 보고서를 브라우저에 저장합니다. 두 모드는 검색 동작과 저장 위치가 다릅니다.

## 4. 구조와 파일 역할

| 용어 | 이 프로젝트에서의 의미 |
|---|---|
| UI / 프런트엔드 | 브라우저 화면과 버튼 동작 |
| 백엔드 | 검색·저장·계산 요청을 처리하는 서버 |
| DB / SQLite | 문서와 보고서 등을 파일에 지속적으로 저장하는 장치 |
| 청크 | 긴 문서를 검색하기 좋은 크기로 나눈 문단 |
| RAG | 관련 문서를 검색한 뒤 그 근거를 모델에 제공해 답변하게 하는 방식 |
| LLM | 근거를 읽고 자연어 답변을 작성하는 AI 모델 |
| Tool | 정해진 입력을 검증하고 계산하는 함수 |
| API | 화면이나 다른 프로그램이 서버 기능을 호출하는 통로 |

```text
문서 JSON → 수집 명령 → 형식 검사·문단 분할 → SQLite에 저장·검색 색인 생성

화면에서 질문 → /api/ask → 관련 문단 검색
                           ├─ 기본: 검색 문단 표시
                           └─ 선택: 외부 모델 답변 생성 → 인용 확인 → 표시
                                      ↓
                              보고서에 담기 → DB 저장

계산 화면 → /api/tools/calculate_emissions → 입력 검사 → 계산 → 실행 기록 저장
```

| 파일 | 역할 |
|---|---|
| [index.html](index.html) | 화면 시작점과 스크립트 로딩 |
| [app.js](app.js) | 메뉴, 검색·보고서 화면, 기존 샘플 모드 |
| [backend-ui.js](backend-ui.js) | 실제 API 호출, 근거 표시, DB 저장·불러오기 |
| [style.css](style.css) | 기본 화면 스타일 |
| [operations.js](operations.js), [operations.css](operations.css) | 지도·항해 시각·사용 환경 화면 |
| [server.mjs](server.mjs) | 서버 시작, 빈 DB 초기화, API와 화면 파일 제공 |
| [backend/api.mjs](backend/api.mjs) | API 경로와 요청 검사 |
| [backend/network.mjs](backend/network.mjs) | 로컬/LAN 실행 옵션, 접속 주소·서브넷 검사 |
| [backend/knowledge.mjs](backend/knowledge.mjs) | 문서 형식 검사, 문단 분할, 검색어 처리 |
| [backend/db.mjs](backend/db.mjs) | DB 테이블, 문서 수집·검색, 보고서·실행 기록 저장 |
| [backend/rag.mjs](backend/rag.mjs) | 검색과 모델 생성 연결, 인용 검사, 실패 처리 |
| [backend/tools.mjs](backend/tools.mjs) | 배출량·항해 시각 계산 |
| [backend/validation.mjs](backend/validation.mjs) | 공통 입력 검사와 오류 형식 |
| [knowledge/seed.json](knowledge/seed.json) | 초기 문서 4개 |
| [scripts/ingest.mjs](scripts/ingest.mjs) | 문서를 수집하는 명령 |
| [tests/backend.test.mjs](tests/backend.test.mjs), [tests/server.test.mjs](tests/server.test.mjs) | 백엔드·HTTP 테스트 |
| [tests/network.test.mjs](tests/network.test.mjs), [tests/launcher.test.mjs](tests/launcher.test.mjs) | 네트워크 허용 범위와 CMD·PowerShell·LAN 실행 검증 |
| [scripts/browser-smoke.mjs](scripts/browser-smoke.mjs) | 실제 Chrome 검증 |
| [.env.example](.env.example) | 선택적 서버 설정 예시 |
| [start.ps1](start.ps1), [start.cmd](start.cmd), [start-lan.cmd](start-lan.cmd) | Windows 로컬·LAN 실행·테스트·수집 도구 |
| [setup-lan-firewall.ps1](setup-lan-firewall.ps1) | 선택적 개인/도메인 네트워크 방화벽 설정 |

`fonts/`와 `vendor/leaflet/`에는 글꼴과 지도 라이브러리가 있습니다. `styles.css`는 이전 파일이며 현재 화면에서는 사용하지 않습니다. `.backup/`, `.replica/`, `.verification/`는 작업·검증 자료로, 새로 받은 프로젝트에는 없을 수 있습니다.

## 5. 검색할 문서 추가하기

현재 수집기는 **JSON 문서 배열**을 받습니다. PDF나 URL에서 본문을 자동 추출하는 기능은 아직 없습니다. 확인한 본문을 아래 형식으로 작성하세요.

### 1단계: 문서 파일 만들기

`knowledge/my-documents.json` 파일을 만들고 다음 내용을 UTF-8로 저장합니다. 검색 연습용 가상 문서 예시입니다.

```json
[
  {
    "id": "sample-contact-guide",
    "title": "교육용 연락처 확인 안내 (가상)",
    "kind": "sample",
    "reference": "TRAINING-CONTACT-01 · 1절",
    "version": "1.0",
    "reviewedAt": "2026-09-28",
    "language": "ko",
    "sections": [
      {
        "heading": "교육용 연락처 확인",
        "text": "교육용 연락처는 담당자가 제공한 목록에서 확인합니다. 이 내용은 검색 연습을 위한 가상 문서이며 실제 비상 연락 절차가 아닙니다."
      }
    ]
  }
]
```

| 항목 | 작성 방법 |
|---|---|
| `id` | 고정 문서 이름. 영문 소문자·숫자·하이픈만 사용하고 개정 시에도 유지 |
| `title` | 화면에 보일 문서 제목 |
| `kind` | 공식 안내 요약 `official-summary`, 선내 문서 `onboard`, 가상 자료 `sample` |
| `reference` | 문서 번호·규정 조항 등 사람이 확인할 출처 위치 |
| `version` | 작성·개정 버전 |
| `reviewedAt` | 실제 확인일. `YYYY-MM-DD` 형식 |
| `language` | 한국어 `ko`, 영어 `en` |
| `url` | 원문 HTTPS 주소. `official-summary`에서는 필수, 나머지에서는 선택 |
| `sections` | 절 제목 `heading`과 본문 `text`의 목록 |

분류 이름만으로 공식성이 검증되지는 않습니다. 등록자가 원문과 요약의 정확성을 확인해야 합니다.

### 2단계: DB에 등록하기

서버를 켜 둔 경우 별도 터미널에서 실행합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -Task ingest -Document .\knowledge\my-documents.json
```

결과의 `created`는 새 문서 등록, `updated`는 같은 ID의 새 버전 등록, `unchanged`는 내용이 같아 기존 문서를 유지했다는 뜻입니다.

### 3단계: 검색 확인하기

앱에서 `교육용 연락처`를 검색합니다. 새 문서와 근거가 표시되면 완료입니다. 화면 위 문서 개수 표시까지 갱신하려면 새로고침합니다.

개정할 때는 같은 `id`를 유지하고 본문·`version`·`reviewedAt`을 수정해 재수집합니다. 새 버전만 검색하고 이전 버전은 기존 보고서 인용을 위해 보존합니다.

**파일 수정만으로 기존 DB는 바뀌지 않습니다.** `knowledge/seed.json`을 수정했을 때도 수집 명령을 다시 실행합니다. 초기 문서는 빈 DB에만 자동 등록됩니다.

## 6. AI 답변 생성 연결하기

설정하지 않아도 문서 검색·DB 저장·계산은 동작합니다.

1. `.env.example`을 복사해 **`.env`**라는 이름으로 저장합니다. 이미 `.env`가 있으면 덮어쓰지 말고 내용을 수정합니다. `.env.txt`가 되지 않도록 확인하세요.
2. 아래 값을 채웁니다. 모델에는 사용할 수 있는 Responses API·Structured Outputs 지원 모델의 실제 ID를 넣습니다.

```dotenv
HAEDAP_DB_PATH=data/haedap.sqlite
OPENAI_API_KEY=발급받은_실제_API_키
OPENAI_MODEL=사용할_실제_모델_ID
```

3. 서버를 종료했다가 다시 실행하고 브라우저를 새로고침합니다.
4. **실행 환경 설정 → 검색 근거로 AI 답변 생성**을 켭니다. 실행 방식은 `문서 검색 + DB + 계산 도구`로 둡니다.
5. 질문을 검색하고 AI 초안 또는 실패 시 근거 문단 전환 안내를 확인합니다.

AI 옵션을 켜면 질문과 검색 문단이 외부 모델로 전송됩니다. 키는 서버에서만 사용하고 `.env`는 Git 저장 대상에서 제외합니다. 호출 실패·잘못된 인용이 감지되면 검색 문단으로 전환합니다. 인용문의 존재 검사와 답변 전체의 정확성 평가는 별개입니다.

현재 모델 검증은 모의 응답으로 진행했습니다. 실제 호출·비용·답변 품질은 추가 확인이 필요합니다. 요청 형식은 [OpenAI Structured Outputs 문서](https://developers.openai.com/api/docs/guides/structured-outputs)를 참고하세요.

## 7. DB 저장과 백업

기본 저장 위치는 **`data/haedap.sqlite`**입니다. SQLite는 별도 DB 서버 대신 파일에 데이터를 저장합니다.

| 내용 | 테이블 |
|---|---|
| 문서와 개정 이력 | `documents` |
| 분할한 문단과 검색 색인 | `chunks`, `chunks_fts` |
| 보고서 초안 | `reports` |
| Tool 입력·출력·계산 버전 | `tool_runs` |
| 질문·검색 근거·응답 | `queries` |

현재 UI는 **현재 초안 1개**를 저장·불러옵니다. 계정·권한 관리나 보고서 목록은 아직 없습니다. 여러 창의 편집은 버전 충돌로 감지하며, DB 초안을 다시 불러와 해결합니다. 기존 브라우저 초안을 DB 내용으로 자동 덮어쓰지 않습니다.

백업은 서버를 Ctrl+C로 종료한 뒤 `data/` 폴더를 별도 위치에 복사합니다. `.env`에서 DB 경로를 바꿨다면 그 위치를 백업합니다. 실행 중에는 `-wal`, `-shm` 보조 파일을 사용할 수 있으므로 **실행 중인 DB 파일 하나만 복사하지 마세요.** 복원도 서버를 종료한 뒤 진행하며 현재 데이터를 먼저 별도로 보관합니다.

화면의 **초안 백업 (.json)**은 현재 보고서만 내보내는 기능으로 전체 DB 백업과 다릅니다. `data/`는 Git 저장 대상에서 제외되므로 코드만 복사하면 기존 DB는 함께 이동하지 않습니다.

## 8. 기능 구현·수정 순서

### 검색 기능 수정

1. `backend/knowledge.mjs`의 `validateDocument`, `prepareDocument`, `tokens`에서 문서 형식·분할·검색어 처리를 확인합니다.
2. `backend/db.mjs`의 `importDocuments`, `retrieve`에서 수집·검색을 확인합니다.
3. 현재 검색은 SQLite FTS5/BM25에 단어·한국어 2글자 조각·한영 용어 사전을 적용합니다. 의미 기반 검색을 추가하려면 임베딩 생성·저장·검색을 별도로 구현합니다.
4. 검색어 처리나 청크 구조를 바꾸면 기존 색인도 갱신합니다. 현재는 분할 버전 문자열을 올리고 문서를 재수집해 새 리비전을 만드는 방식을 사용할 수 있습니다. 이전 인용은 보존합니다.
5. 한영 질문·관련 없는 질문·문서 필터를 테스트합니다.

### 새 계산 Tool 추가

1. `backend/tools.mjs`에 계산 함수를 추가합니다. 입력 단위·허용 범위를 검증하고 결과 단위·계산 버전·가정을 반환합니다.
2. 같은 파일의 `toolDefinitions`와 `runTool`의 허용 함수 목록에 등록합니다. 반환값의 `version`은 실행 기록 저장에 필요합니다.
3. 등록한 Tool은 `POST /api/tools/도구이름`으로 호출할 수 있습니다.
4. 화면에서 사용하려면 `backend-ui.js`에 API 호출을 추가하고 `app.js`의 버튼·폼과 연결합니다.
5. 정상값과 해당 계산의 경계 조건을 테스트합니다.

기존 `calculate_emissions`는 배출량·단순 집약도를, `voyage_time`은 UTC 경과시간·선내 시계 표시 차이를 계산합니다. 시각 Tool은 API로 제공되며 기존 지도·시각 화면은 로컬 계산을 유지합니다. 자연어에서 계산 숫자를 추출하는 기능은 없습니다.

### DB·API·화면 연결 수정

1. 저장 기능은 `backend/db.mjs`, 요청 경로는 `backend/api.mjs`에서 수정합니다.
2. 기존 DB를 고려합니다. `CREATE TABLE IF NOT EXISTS`만 바꿔서는 이미 생성된 테이블이 변경되지 않습니다. 스키마 변경에는 기존 데이터를 보존하는 마이그레이션을 추가해야 합니다.
3. SQL에 입력값을 직접 문자열로 붙이지 않고 매개변수를 바인딩합니다. 기존 버전 충돌 검사를 유지합니다.
4. `backend-ui.js`에서 API를 호출하고 `app.js`에 로딩·성공·오류·근거 없음 상태를 연결합니다.
5. 서버 코드 수정 뒤에는 서버를 재시작합니다. 자동 재시작 기능은 없습니다. 화면 코드 수정 후에는 브라우저를 새로고침합니다.

### AI 답변 처리 수정

`backend/rag.mjs`의 `answerQuestion`이 검색·선택적 계산·답변 생성·기록을 묶습니다. `generateGrounded`는 모델 호출과 청크 ID·인용문 검사를 담당합니다. 설정 누락, 호출 실패, 근거 부족을 구분하는 흐름을 유지하세요.

수정 후에는 관련 테스트와 README를 함께 갱신합니다. 추가 구현 설명은 [백엔드 상세 문서](docs/BACKEND.md)를 참고하세요.

## 9. API 직접 호출하기

서버를 켜 둔 뒤 **별도의 PowerShell 터미널**에 순서대로 입력합니다. 다른 포트로 실행했다면 `$base`를 바꿉니다.

```powershell
# 1. 서버 상태 확인과 요청 토큰 받기
$base = 'http://127.0.0.1:5173'
$health = Invoke-RestMethod -Uri "$base/api/health"
$health
$headers = @{ 'X-Haedap-Token' = $health.csrfToken }

# 2. 문서 검색
$askBody = @{ question = '연료 황 함유량'; mode = 'extractive' } | ConvertTo-Json
Invoke-RestMethod -Uri "$base/api/ask" -Method Post -Headers $headers -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($askBody))

# 3. 배출량 계산
$toolBody = @{ fuel = 100; factor = 3; dwt = 1000; distance = 100 } | ConvertTo-Json
Invoke-RestMethod -Uri "$base/api/tools/calculate_emissions" -Method Post -Headers $headers -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($toolBody))
```

첫 응답의 `ok`가 `True`이면 연결된 상태입니다. 검색 응답의 `evidence`는 근거 문단, `statements`는 표시 내용입니다. 계산의 `result.emission`은 `300`입니다. 서버를 재시작했다면 첫 단계에서 토큰을 다시 받습니다.

| 메서드·경로 | 용도 | 주요 입력 |
|---|---|---|
| `GET /api/health` | 연결 상태·모델 설정 여부·토큰 | 없음 |
| `GET /api/documents` | 문서 버전과 청크 | 없음 |
| `POST /api/search` | 근거만 검색 | `question`, `filter`: `all` / `imo` / `manual` |
| `POST /api/ask` | 검색·선택적 생성·계산 | `question`, `filter`, `mode`: `extractive` / `llm`, `language`: `ko` / `en`, 선택적 `calculation` |
| `GET /api/reports/current` | 초안 불러오기 | 없음 |
| `POST /api/reports/current` | 초안 저장 | `title`, `type`, `text`, `sources`, `version` |
| `GET /api/tools` | Tool 목록 | 없음 |
| `POST /api/tools/calculate_emissions` | 배출량 계산 | `fuel`, `factor`, `dwt`, `distance` |
| `POST /api/tools/voyage_time` | 시각 계산 | `start`, `end`, `before`, `after` |

`sources`는 문서 ID 배열입니다. 새 보고서의 `version`은 `0`, 이후에는 불러온 최신 버전을 전달합니다. `type`은 `규정 검토`, `일일 운항`, `배출량 검토`, `종합 검토` 중 하나입니다. `calculation`은 배출량 Tool과 같은 입력 객체입니다. 시각 Tool에는 `2026-09-18T00:00:00Z` 형식의 UTC 시각과 분 단위 선내 오프셋을 전달합니다.

기본 실행은 **이 PC 전용**, `--lan` 실행은 **같은 네트워크의 기기용**입니다. LAN 주소로 API를 호출할 때는 위 예제의 `$base`도 실행 창의 주소로 바꿉니다. POST에는 JSON과 요청 토큰이 필요하고 요청 크기는 1MB로 제한됩니다. LAN에서도 동일 출처 검사와 비공개 파일 차단을 유지합니다. 요청 토큰은 로그인 기능이 아니며 사용자별 권한·공개 인터넷 배포는 별도 구현 범위입니다.

## 10. 테스트하기

### 백엔드·HTTP 테스트

Node가 PATH에 없어도 실행 도구로 테스트할 수 있습니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -Task test
```

Node가 인식된다면 `npm test`도 가능합니다. 테스트는 실제 사용 DB와 별도의 DB를 사용하며 문서 개정, 검색, 저장 충돌, 재시작 후 유지, 계산 경계값, 모델 인용·실패 처리, API 요청 검사를 확인합니다. 네트워크·포트 검사와 CMD·PowerShell·LAN 실행 검사도 포함합니다. Windows 런처 검증의 실행 로그와 결과는 `.verification/launcher-*/`에 보관합니다.

**2026-09-28 확인 결과: 15개 통과, 실패 0개.** CMD·PowerShell에서 서버 시작 및 이 PC의 실제 LAN 주소를 통한 API 호출까지 확인했습니다. 독립된 휴대폰·다른 PC에서의 연결은 아직 직접 검증하지 않았습니다. Windows 런처 테스트는 다른 운영체제에서는 건너뜁니다.

### 실제 Chrome 검증

Chrome이 설치돼 있고 Node가 인식된다면 다음을 실행합니다.

```powershell
node scripts/browser-smoke.mjs
```

실제 LAN 주소로 화면·API 연결을 확인하려면 `node scripts/browser-smoke.mjs --lan`을 사용합니다. 이 검증도 같은 PC의 브라우저에서 실행하므로 다른 기기의 방화벽 통과 여부를 대신 확인하지는 않습니다.

Node 대신 현재 사용자 경로에 설치된 VS Code를 사용하는 경우입니다. 다른 곳에 설치했다면 실행 파일 경로를 바꿉니다.

```powershell
$env:ELECTRON_RUN_AS_NODE = '1'
& "$env:LOCALAPPDATA\Programs\Microsoft VS Code\Code.exe" scripts/browser-smoke.mjs | Out-Host
```

기본 Chrome 경로는 `C:/Program Files/Google/Chrome/Application/chrome.exe`입니다. 다르면 실행 전에 `$env:CHROME_PATH`에 실제 경로를 지정합니다.

별도의 테스트 서버·DB와 숨김 브라우저로 검색 → 근거 보기 → 보고서 저장·불러오기, 계산, 새 문서 반영, 모바일 화면을 확인합니다. 결과는 `.verification/backend-browser-*/results.json`, 화면은 같은 폴더의 `report-mobile.png`에 저장됩니다.

**2026-09-28 확인 결과: 로컬 주소와 실제 Wi-Fi 주소 각각 11개 점검 통과, JavaScript 예외 없음.** 같은 PC의 Chrome에서 두 접속 경로를 확인한 결과입니다. 독립된 다른 기기 연결, 실제 모델의 답변 정확도·운항 적합성 평가 결과는 아닙니다.

## 11. 문제 해결

| 증상 | 확인·해결 방법 |
|---|---|
| `node`·`npm`을 찾을 수 없음 | `start.cmd`나 `start.ps1`을 사용합니다. 호환 런타임이 없으면 Node.js 22.13 이상이 필요합니다. |
| `node:sqlite`를 찾을 수 없음 | 선택된 런타임의 버전과 SQLite 지원 여부를 확인합니다. |
| `Port 5173 is in use` | 기존 실행 창을 확인하거나 `-Port 5174`로 실행하고 접속 주소도 변경합니다. |
| 백엔드 연결 실패 | 서버 실행 여부와 주소를 확인합니다. HTML 파일 직접 열기는 사용하지 않습니다. |
| 이 PC에서는 열리지만 다른 기기는 실패 | `start-lan.cmd` 실행 여부, 실행 창의 LAN 주소, 같은 네트워크 연결, 방화벽 프로필·포트, 공유기의 기기 격리를 순서대로 확인합니다. |
| LAN 실행 후 주소가 표시되지 않음 | Wi-Fi/유선 IPv4 연결을 확인하고 서버를 재시작합니다. |
| LAN에서 403 응답 | 실행 창에 표시된 IP·포트로 접속합니다. 네트워크 변경 후에는 서버를 재시작합니다. |
| 재시작 후 요청 토큰 오류 | 화면을 새로고침하거나 `/api/health`에서 토큰을 다시 받습니다. |
| 문서 수정이 반영되지 않음 | 수정 후 ingest 명령을 실행했는지, 서버와 수집 명령이 같은 DB 경로를 사용하는지 확인합니다. |
| 수집 시 JSON 오류 | 큰따옴표·쉼표·최상위 배열·필수 항목·UTF-8 저장을 확인합니다. JSON에는 주석을 넣지 않습니다. |
| 검색 근거가 없음 | 등록 본문과 필터를 확인하고 핵심 용어로 검색합니다. 현재는 의미 기반 검색이 아닙니다. |
| AI 옵션 비활성화 | 키와 모델 ID를 모두 설정한 뒤 서버 재시작·화면 새로고침을 합니다. |
| AI 대신 근거 문단 표시 | 기본 모드이거나 모델 실패 후 전환입니다. 설정·연결·모델 사용 권한을 확인합니다. |
| 보고서 버전 충돌 | 필요한 편집 내용을 먼저 파일로 보관하고 DB 초안을 불러와 변경 내용을 반영합니다. |
| 샘플 모드 초안이 DB에 없음 | 샘플 모드는 브라우저 저장입니다. 실제 문서 검색 모드에서 저장합니다. |
| 지도 배경만 나오지 않음 | 인터넷·지도 스위치·저사양 모드를 확인합니다. 지도와 로컬 검색은 별개입니다. |
| 코드 수정이 반영되지 않음 | 서버 코드는 서버 재시작, 화면 코드는 브라우저 새로고침이 필요합니다. |

## 12. 다음 작업과 문서 관리

다음 작업은 승인 문서 확충·개정 관리, 실제 모델 연결과 품질 평가, 검색 평가용 질문·정답 근거 작성, 실제 선박 DB·AIS·기상 통합입니다. 필요에 따라 벡터 검색, PDF/OCR, 계정·권한, 다중 보고서, 배포·복구 체계를 추가합니다.

**앞으로 작업이 끝날 때마다 이 README를 함께 업데이트합니다.** 변경 이력뿐 아니라 사용자가 따라 할 본문도 수정합니다.

| 바뀐 내용 | 함께 수정할 항목 |
|---|---|
| 기능·완료 범위 | 현재 구현 상태, 화면 확인, 다음 작업 |
| 설치·실행·설정 | 처음 실행하기, AI 설정, 문제 해결 |
| 파일·API | 구조, 구현 방법, API 예제 |
| 문서 형식·DB | 문서 추가, 백업, 기존 데이터 이전 절차 |
| 테스트 | 실행 명령, 날짜, 실제 결과·미검증 범위 |
| 모든 변경 | 마지막 업데이트 날짜와 변경 이력 |

지속적인 작업 지침은 [AGENTS.md](AGENTS.md)에 남겨 두었습니다. 상세 문서를 추가해도 처음 실행하고 기본 기능을 수정하는 데 필요한 절차는 README에 유지합니다. 코드와 문서가 다르면 실제 구현을 확인해 갱신합니다.

## 13. 변경 이력

| 날짜 | 변경 내용 | 검증·남은 사항 |
|---|---|---|
| 2026-10-05 | 해사 데이터 도구를 tools/maritime_data로 정리하고 상세 문서를 3개로 통합 | Python 계약·인증·계산·전처리 검증. 실제 DB·팀 UI 연결은 후속 범위 |
| 2026-09-28 | 런타임 자동 탐색 보강, 로컬·LAN 실행 파일과 서버 옵션, 접속 주소 출력, 연결 서브넷 검사, 선택적 방화벽 설정 및 다른 기기 실행 안내 추가 | 자동 테스트 15개, 로컬·LAN 브라우저 각 11개 통과. 독립된 다른 기기 연결·공용 Wi-Fi 통과는 미검증 |
| 2026-09-28 | README를 실행·사용·수집·설정·DB·구현·API·테스트·문제 해결 안내로 확장. 지속 업데이트 지침 추가 | 경로·예제와 현재 코드 대조. 문서 정리로 외부 모델 검증이 추가된 것은 아님 |
| 2026-09-28 | SQLite DB, 문서 수집·검색, 선택적 모델 생성, 계산 Tool, 주요 UI 연결 구현 | 백엔드 10개·브라우저 11개 통과. 실제 모델·운항 데이터·품질 평가는 남음 |
| 2026-09-21 | 원본 데모의 화면·자산을 로컬 복제하고 실행 도구 구성 | 이후 백엔드 연결을 위해 화면 코드 수정 |

초기 화면 원본: [해,답 데모](https://haedap-maritime-demo.gptjipiti1014.chatgpt.site). 공식 안내 요약의 출처와 세부 구현 범위는 [백엔드 상세 문서](docs/BACKEND.md)에 정리돼 있습니다.
