# RAG / DB / Tool 구현

처음 실행하거나 구현 흐름을 따라가려면 [README](../README.md)를 먼저 보세요. README를 기본 실행·구현 안내서로 유지하며, 이 문서는 백엔드의 세부 동작과 제한 사항을 설명합니다.

현재 구현은 한 PC에서 실행하는 백엔드입니다. 기본 모드는 해당 PC에서 사용하며 LAN 모드에서는 같은 네트워크의 기기가 브라우저로 접속해 문서·DB를 공유합니다. 기본 실행에는 외부 API와 패키지 설치가 필요하지 않습니다. Node.js 22.13 이상에서 제공하는 SQLite를 사용하며, `start.cmd`는 호환되는 Node 또는 VS Code의 런타임을 찾습니다.

## 실행 및 검증

```powershell
.\start.cmd
# http://127.0.0.1:5173

# 다른 기기 접속은 위 로컬 서버를 종료한 뒤 실행
.\start-lan.cmd
# 실행 창의 LAN 주소로 접속

powershell -ExecutionPolicy Bypass -File .\start.ps1 -Task test
powershell -ExecutionPolicy Bypass -File .\start.ps1 -Task ingest -Document .\knowledge\seed.json
```

Node가 PATH에 있으면 `npm start`, `npm run start:lan`, `npm test`, `npm run ingest -- knowledge/seed.json`도 가능합니다. 포트 지정은 `node server.mjs --lan --port 5174` 또는 `start.ps1 -Lan -Port 5174`로 합니다. 실제 Chrome 검증은 `node scripts/browser-smoke.mjs`로 실행하며 `--lan`을 붙이면 LAN 주소로 점검합니다. 기본 Chrome 경로가 다르면 `CHROME_PATH` 환경변수를 설정하세요. 결과와 모바일 화면은 `.verification/backend-browser-*/`에 저장합니다. Windows 런처 로그는 `.verification/launcher-*/`에 저장합니다.

## 문서 수집 → 검색 → 답변

1. `knowledge/seed.json`의 초기 문서 4개를 빈 DB에 수집합니다. IMO 공식 웹 안내를 확인해 작성한 한국어 요약 2개와 명시적으로 표시한 가상 문서 2개입니다. 공식 규정 전문을 수집한 상태는 아닙니다.
2. 절·문장 경계로 본문을 최대 900자 청크로 나눕니다. 문서 ID·버전·확인일·출처 URL·조항·절 제목과 콘텐츠 해시를 보존합니다. 소수점은 분할하지 않습니다.
3. SQLite FTS5/BM25로 검색합니다. 한국어는 단어와 2글자 조각을 함께 색인하고, 작은 한·영 용어 사전을 적용합니다. **현재 검색은 어휘 기반이며 임베딩·벡터 검색은 구현하지 않았습니다.**
4. 기본 모드는 검색된 문단을 그대로 보여줍니다. 질문 전체를 해결한 생성 답변이라고 표시하지 않습니다. 근거가 없으면 답변을 보류합니다. 문서 필터는 검색 단계에 적용합니다.
5. 외부 모델을 설정하고 화면에서 선택하면 검색 문단을 근거로 답변을 생성합니다. 문장마다 존재하는 청크 ID와 해당 청크에 실제 존재하는 인용문을 검사합니다. 모델 오류·잘못된 인용·불완전한 출력에는 근거 문단으로 전환하고 전환 사실을 표시합니다.

인용의 존재 검사는 문장의 의미가 근거에 완전히 부합함을 보장하지 않습니다. 검색 적합성, 복합 질문, 선박별 적용 조건, 최신 개정 여부, 답변 정확도에 대한 별도 평가가 필요합니다. 모델이 질문을 근거로 답할 수 없다고 판단하면 답변을 보류합니다.

공식 수집 근거(2026-09-28 확인):

- [IMO 2020 · sulphur 안내](https://www.imo.org/en/mediacentre/hottopics/pages/sulphur-2020.aspx)
- [IMO · EEXI/CII FAQ](https://www.imo.org/en/mediacentre/hottopics/pages/eexi-cii-faq.aspx)

## 문서 추가와 개정

`knowledge/seed.json`과 같은 구조의 JSON 배열을 작성한 뒤 ingest 명령으로 등록합니다. 문서 종류는 `official-summary`, `onboard`, `sample` 중 하나입니다. 공식 안내 요약에는 HTTPS 원문 URL을 지정해야 합니다. 등록자가 출처와 본문 정확성을 확인해야 하며, 분류 이름만으로 진위를 검증하지는 않습니다.

```json
[
  {
    "id": "vessel-approved-manual",
    "title": "선내 승인 문서 제목",
    "kind": "onboard",
    "reference": "문서 번호 / 절 번호",
    "version": "1.0",
    "reviewedAt": "2026-09-28",
    "language": "ko",
    "sections": [
      { "heading": "절 제목", "text": "확인한 본문을 여기에 넣습니다." }
    ]
  }
]
```

같은 ID·같은 내용의 재수집은 중복을 만들지 않습니다. 같은 ID의 내용이 바뀌면 새 버전만 검색하며 이전 버전은 남겨 기존 보고서의 인용을 유지합니다. 수집은 트랜잭션 단위로 처리합니다. 서버 재시작은 기존 문서를 초기 시드로 되돌리지 않습니다. PDF/OCR, 웹 자동 크롤링, 자동 개정 감시는 다음 확장 범위입니다.

## DB와 보고서

기본 파일은 `data/haedap.sqlite`입니다. `documents`, `chunks`, `chunks_fts`, `reports`, `tool_runs`, `queries` 테이블을 사용합니다. 문서와 보고서뿐 아니라 질문, 검색 근거, 답변, 계산 입력·출력도 로컬 DB에 저장합니다. API 키는 DB·브라우저에 저장하지 않습니다.

보고서 화면에서 **초안 저장**을 누르면 현재 초안을 DB에 저장합니다. **DB 초안 불러오기**로 다시 열 수 있습니다. 기존 브라우저 초안을 자동 덮어쓰지 않습니다. 여러 창의 동시 편집은 버전 검사로 충돌을 알려주며, DB 초안을 다시 불러와 해결합니다. 서버 재시작 후에는 화면을 새로고침하세요. 샘플 모드에서는 기존 브라우저 저장 기능을 사용합니다.

이 단계는 현재 초안 1개를 위한 API입니다. LAN 접속 기기도 같은 초안을 공유하며 저장 버전으로 충돌을 감지합니다. 사용자 계정, 권한 구분, 다중 보고서 목록, 공개 인터넷 배포는 포함하지 않습니다. SQLite 파일을 백업할 때에는 서버를 종료한 뒤 파일을 복사하세요. 실행 중 파일 복사는 WAL 상태를 누락할 수 있습니다.

## 계산 Tool

| 이름 | 입력 | 결과 |
|---|---|---|
| `calculate_emissions` | 연료 t, 환산계수 tCO₂/t, DWT, 거리 nm | CO₂ t, 단순 집약도 gCO₂/(DWT·nm), 계산 버전·가정 |
| `voyage_time` | UTC 시작·종료, 시작·종료 선내 오프셋(분) | 실제 경과시간, 선내 시계 표시 차이, 반개구간 표기 |

계산은 모델에게 맡기지 않고 검증된 숫자 입력을 함수에 전달합니다. 문자열 숫자, 음수, 0인 분모, 무한대, 잘못된 날짜를 거부합니다. **공식 CII 등급은 산정하지 않습니다.** 배출량 화면의 초기 표시와 기본값 변경은 로컬 미리보기이며, 다시 계산하기를 누르면 서버 Tool을 실행하고 기록합니다. 배출량을 함께 요청하는 검색에는 현재 계산 화면의 입력값이 사용됩니다. 자연어 숫자 추출은 구현하지 않았습니다. 항해 시각 Tool은 API로 제공하며 기존 지도·시각 화면은 로컬 계산을 유지합니다.

## 선택적 외부 모델

`.env.example`을 `.env`로 복사하고 다음을 설정합니다. 모델 이름은 사용 가능한 Responses/Structured Outputs 지원 모델을 직접 지정합니다.

```dotenv
HAEDAP_DB_PATH=data/haedap.sqlite
OPENAI_API_KEY=발급받은_키
OPENAI_MODEL=사용할_모델_ID
```

서버를 재시작한 뒤 **실행 환경 설정 → 검색 근거로 AI 답변 생성**을 켭니다. 이때 질문과 검색 문단이 OpenAI에 전송됩니다. 기본 모드와 외부망 차단 모드에서는 전송하지 않습니다. [Responses API의 Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)를 사용하고 `store: false`로 요청합니다. 이번 환경에는 API 키가 없어 실제 외부 모델 호출은 하지 않았으며, API 요청 형식·정상 응답·실패·잘못된 인용 처리는 모의 응답으로 검증했습니다.

## API

| 메서드·경로 | 용도 |
|---|---|
| `GET /api/health` | DB·검색 상태, 모델 설정 여부, 요청 토큰 |
| `GET /api/documents` | 현재·이전 문서 버전과 청크 |
| `POST /api/search` | `{ "question": "...", "filter": "all" }`로 근거 검색 |
| `POST /api/ask` | 검색·선택적 생성·선택적 계산·질문 기록 |
| `GET /api/reports/current` | 현재 DB 초안 |
| `POST /api/reports/current` | `{ title, type, text, sources, version }` 저장 |
| `GET /api/tools` | 허용된 Tool 목록·입력 설명 |
| `POST /api/tools/calculate_emissions` | `{ fuel, factor, dwt, distance }` |
| `POST /api/tools/voyage_time` | `{ start, end, before, after }` |

POST 요청은 `Content-Type: application/json`과 health가 돌려주는 `X-Haedap-Token` 헤더가 필요합니다. 기본 서버는 `127.0.0.1`, `--lan` 서버는 `0.0.0.0`에 바인딩합니다. LAN 모드도 서버의 실제 IPv4 주소·포트, 연결된 서브넷의 접속자, 동일 출처 요청만 허용합니다. 네트워크가 바뀌면 서버를 재시작합니다. 요청 본문은 1MB, 동시 POST는 4개로 제한합니다. DB, 환경파일, 백엔드 소스는 정적 파일로 제공하지 않습니다. 요청 토큰은 사용자 인증을 대신하지 않습니다. 다른 기기 접속과 선택적 Windows 방화벽 설정은 README의 실행 안내를 따릅니다.

## 이번 검증과 남은 단계

2026-09-28 로컬/LAN 실행 변경 후 자동 테스트 15개, 로컬 주소와 실제 Wi-Fi 주소를 사용하는 Chrome 검증 각각 11개가 통과했습니다. 모두 이 PC에서 수행했으며, 독립된 다른 기기나 공용 Wi-Fi의 방화벽 통과 여부를 검증한 결과는 아닙니다.

자동 테스트는 수집 중복·개정 보존, 한국어/영어 검색과 필터, 미지원 질문, DB 재시작·저장 충돌, 계산 경계값, 날짜변경선, 모델 인용 검증·장애 전환, API 입력·출처 보호를 확인합니다. Chrome 검증은 검색 → 근거 열기 → 보고서 저장 → 새로고침·불러오기, 서버 계산, 근거 없음, 모바일 배치, 동적 문서 수집과 HTML 이스케이프를 확인합니다.

실제 선박 DB·AIS·기상 데이터, 승인 문서 전문, API 키를 사용하는 모델 품질 검증, 검색/답변 평가 데이터셋과 성능 측정은 아직 남아 있습니다. 현재 위치는 **RAG/DB/Tool의 로컬 MVP 구현 및 주요 UI 연결 완료**이며 운영용 통합·평가 완료는 아닙니다.


## 역할4 독립 PostgreSQL Tool (2026-09-30)

`role4/`는 별도 Python API입니다. 기존 Node.js/SQLite 서버의 `/api`와 자동 연결되지 않으며 기본 포트는 8000입니다. 역할4 테이블은 PostgreSQL의 `role4` 스키마에 분리됩니다. 기존 앱 DB를 이전하거나 변경하지 않습니다.

조회·계산 Tool은 Bearer 토큰이 필요합니다. 브라우저에 토큰을 노출하지 않고 팀 백엔드에서 권한 검사 후 호출하는 방식으로 연결하세요. 설치·적재·검증 명령은 [역할4 README](../role4/README.md), 식별자·결측·blocked 처리 및 미완료 통합 항목은 [연동 안내](../role4/INTEGRATION.md)에 있습니다.
