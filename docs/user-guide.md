# 사용·운영 안내

> 대상 버전: 1.4.0 · 설치와 기본 실행은 [`../README.md`](../README.md)를 먼저 보세요.

## 1. 화면별 사용 방법

### 업무 스킬

**사용할 문서**에서 문서 왼쪽 체크박스를 눌러 선택합니다. 여러 문서를 하나씩 체크할 수 있고 다시 누르면 해제됩니다. 아래 선택 개수를 확인한 뒤 실행하세요. 최대 20개입니다.

별도 업무 스킬 메뉴 없이 기존 화면에서 기능을 펼쳐 실행합니다. 통합 질문의 **선택 문서로 질문하기**, 활성 문서 상세의 **이 문서로 질문·점검표 만들기**, 운항 정보의 **운항 실적·MRV 참고값 분석**, 보고서 목록의 **자료로 보고서 초안 만들기**를 사용합니다. 저장된 답변 아래 **이 응답의 근거·계산 점검**에서 해당 응답을 평가합니다. 모든 기본 기능은 LLM 없이 동작합니다. 이전 `/skills` 주소는 `/chat`으로 이동합니다.

| 스킬 | 필요한 입력 | 결과 |
|---|---|---|
| MRV 참고 분석 | 앱 선박·보고연도, 기존 명시 매핑 | 기존 Python Tool의 참고값·단위·출처·차단 사유 |
| 선택 문서 답변 | 질문·활성 문서(여러 개 가능) | 선택 개정본만 검색한 원문 근거·페이지 |
| 운항 실적 요약 | 앱 선박·기간 | 연료·계산 CO2·거리·보고일·샘플 표시 |
| 보고서 초안 | 앱 선박·기간·양식, 선택 문서(선택 사항) | 저장되지 않은 검토용 초안. 별도 버튼으로 새 보고서 저장 |
| 점검표 | 작업 목적·선택 문서 | 미확인 상태의 근거 있는 점검 항목 초안 |
| 질의평가 | 본인 질의 이력 | 인용·범위·계산 계약 검사. 의미적 정답성은 사람 검토 |

문서 답변·점검표·보고서의 문서 설명에는 **AI로 정리**를 선택할 수 있습니다. 기존 OpenAI 호환 설정을 사용하며 Ollama Qwen도 같은 방식으로 설정합니다. Docker에서 호스트 Ollama는 `LLM_API_BASE_URL=http://host.docker.internal:11434/v1`, `OPENAI_MODEL=qwen2.5:3b`, `LLM_RESPONSE_FORMAT=json_object` 예시를 참고하세요. 모델이 해당 PC에 설치·실행되어 있어야 합니다. 공급자별 키 격리는 기존 정책을 유지하며 Qwen을 위해 공급자 키를 복사하지 않습니다. 모델 응답 실패는 원문으로 되돌립니다. 입력에 답이 없다고 모델이 판단하면 근거 부족으로 반환할 수 있습니다.

현재 기능은 화면에서 사용자가 직접 실행합니다. 자연어에서 스킬을 자동 선택하거나 이전 대화의 선박·기간을 자동 기억하는 기능은 아닙니다. 현재 문서와 공통 선박·기간을 초기 입력으로 사용하며 최종 작업 범위는 실행 양식에서 확인합니다. 점검표는 완료·안전 승인을 의미하지 않고, MRV 초안은 공식 제출물이 아닙니다. 질의평가는 자동 정답률 산출이 아닙니다.

| 화면 | 할 수 있는 일 |
|---|---|
| 통합 질문 | 문서 질문, 선박·기간 지정, 운항 수치·추이·출처 확인, 근거 페이지 열기, 입력 기준 비교, 당시 답변 이력 열기, 보고서에 담기 |
| 문서 | 텍스트 PDF 등록, 추출 내용 검토, 메타데이터·열람 범위 설정, 개정 등록, 사용 중·이전·폐기 구분, 저장 원문 PDF 보기, 삭제 |
| 운항 정보 | 선박 등록·수정, 일별 기록 등록·수정·삭제, CSV 검증·일괄 등록, 지표별 차트, 여러 선박 비교, 배출량·집약도·시간 계산 |
| 보고서 | 여러 초안 저장·검색·다시 열기, DB 기록으로 Noon/MRV 검토 초안 생성, 편집·미리보기·Markdown 출력, JSON 가져오기, 검토 요청·승인 상태 표시 |
| 관리 | 계정·역할 관리, 변경 및 보고서 승인·반려, 질의·변경·오류·계산 로그, 전체 백업·복구·파일 보관·가져오기·자동 백업 설정 |

### 가장 빠른 체험 순서

모델 답변은 [README의 모델 서버 연결](../README.md#모델-서버-연결)에 따라 루트 `.env`를 설정합니다. OpenAI 호환 Chat Completions 서버를 선택할 수 있고 로컬 Ollama는 키 없이 활성화할 수 있습니다. 근거가 있는 질문에서 `generation=llm`과 인용을 확인하세요. 모델 실패 경고가 있으면 발췌 결과이므로 주소·인증·모델 ID·25초 응답 제한을 확인합니다. 동국의 실제 API 접속 정보와 Ollama 실접속 검증은 아직 남아 있습니다.

1. 일반 화면은 바로 사용할 수 있습니다. 가상 예시를 넣으려면 **관리자 로그인 → admin / 1234**로 로그인합니다.
2. **운항 정보 → 가상 예시로 둘러보기**를 누릅니다. 선박·기록이 없는 작업공간에서만 사용할 수 있습니다. 가상 선박 3척·2026-09-22~28의 21개 기록이 DB에 등록됩니다.
3. **통합 질문**에서 선박·기간을 확인하고 `선택한 선박의 연료 추이를 분석해줘`를 질문합니다.
4. 수치와 그래프를 확인하고 **보고서에 담기 → 저장**합니다.
5. **보고서 → 운항 기록으로 초안 만들기**에서 Noon과 MRV를 각각 생성합니다. 별도 항목으로 보관됩니다.
6. 초안의 누락 항목을 채우고 **검토 요청**합니다. 관리자는 **관리 → 승인 → 검토 내용 → 승인·반영**으로 확정합니다.
7. **관리 → 백업·복구**에서 백업을 만듭니다.

가상 예시는 자동으로 실제 자료와 섞어 넣지 않습니다. 새 작업공간에서 직접 기록을 넣는 경우 먼저 선박을 등록하세요.

### 문서 등록

- PDF는 최대 25MB, 1,000페이지를 지원합니다. 브라우저 안의 PDF.js로 추출하고 원본과 페이지 번호를 함께 저장합니다. 업로드 문서는 외부 서비스로 전송하지 않습니다.
- 문서 등록·개정·삭제는 관리자 전용입니다. 추출 진행·실패를 표시하고, 확인 체크 후 **저장**하면 승인 대기 없이 바로 반영됩니다. 실제 인덱싱이 성공해야 목록에 반영됩니다.
- 스캔 PDF의 OCR은 포함하지 않습니다. 텍스트 없는 페이지를 안내합니다. OCR 처리된 PDF를 사용하거나 페이지별 본문을 입력하세요.
- 본문의 `--- PAGE 7 ---`은 원본 PDF의 물리적인 7번째 페이지입니다. 인쇄된 쪽번호와 다를 수 있습니다.
- 문서명, 버전, 발행기관, 발행일, 개정일, 조항, 적용 조건, 열람 범위를 입력합니다. 표 구조와 조항의 자동 인식은 보장하지 않으므로 추출 내용을 원본과 대조합니다.
- 개정은 문서 상세의 **개정·정보 수정**으로 등록합니다. 이전 인용을 보존하고 새 버전을 검색에 사용합니다. 기존과 다른 원문이면 버전 이름도 바꾸세요.
- ‘사용 중’은 내부에서 지정한 적용 버전입니다. 외부 최신 규정 자동 확인 기능은 아닙니다.
- DOCX·PPT·일반 텍스트 파일 등록은 아직 지원하지 않습니다(계획: [`plans/2026-10-08-team-module-integration.md`](plans/2026-10-08-team-module-integration.md)).

DB가 비어 있으면 첫 요청 때 `backend/knowledge/seed.json`의 기본 문서가 자동 등록됩니다.

기본 문서는 IMO 공식 안내 요약 2건, 가상 예시 2건, 해사 기본 용어집, 그리고 원본 PDF가 함께 등록되는 원문 5건(해양환경관리법·선박안전법·해상교통안전법·선박직원법, USCG Navigation Rules Handbook)입니다. 원문은 `backend/knowledge/documents/`에 있으며 문서 화면의 "원문 PDF 열기"로 볼 수 있습니다. 한국 법령은 저작권법 제7조에 따라 보호 대상이 아니고 USCG 핸드북은 미국 정부 저작물이라 저장소에 함께 둡니다. IMO 협약 원문처럼 재배포가 허용되지 않은 문서는 넣지 않습니다.

seed는 **빈 DB에서만** 적용됩니다. 이미 쓰던 DB에 새 기본 문서를 반영하려면 `docker compose down -v`로 초기화하거나(모든 데이터 삭제) 관리자 화면에서 해당 PDF를 직접 등록합니다. 법령 개정 시 원본 PDF를 국가법령정보센터에서 "저장 → PDF"로 다시 받아 같은 이름으로 바꾼 뒤 `cd backend && uv run python ../scripts/build_seed_documents.py`를 실행하면 해당 항목이 다시 만들어집니다(poppler의 `pdftotext` 필요: macOS `brew install poppler`, Ubuntu `apt install poppler-utils`). 이전 Node 버전의 JSON 일괄 수집 명령(`npm run ingest`)은 제거되었으므로 문서는 화면(또는 같은 `/api/changes` API)으로 등록합니다.

## 2. 역할과 승인

| 사용 방식 | 권한 |
|---|---|
| 일반 사용자 · 로그인 없음 | 공개 문서 조회·질문, 운항 조회·분석·계산, 자기 브라우저의 보고서 작성·저장·검토 요청 |
| 관리자 · 로그인 필요 | 위 기능과 함께 제한 문서 열람, 문서·선박·기록 등록·수정·삭제 즉시 반영, 보고서 승인, 사용자 관리, 전체 로그·백업·복구 |

- 기본 관리자는 **`admin / 1234`**로 고정하며 사용자 관리 화면에서 수정하지 않습니다. 필요하면 별도의 관리자 계정(비밀번호 10자 이상)을 추가합니다. 기존 담당자·열람 계정 정보는 보존하지만 로그인은 관리자 계정에만 허용합니다.
- 문서 열람 범위는 `누구나 열람 / 담당자·관리자 / 관리자만`입니다. 로그인 없는 사용자는 `누구나 열람` 문서만 볼 수 있습니다. 관리자가 범위를 바꾸면 해당 문서의 이전 버전에도 적용됩니다.
- 문서와 운항 원본 자료는 관리자만 변경할 수 있고, 저장·등록·삭제는 승인 대기 없이 즉시 반영됩니다.
- 보고서는 관리자 작성분도 **검토 요청 → 승인** 단계를 거칩니다. 검토·승인된 보고서는 새 초안으로 복사해 수정합니다.
- 일반 사용자의 초안과 질문 이력은 브라우저의 무작위 식별 쿠키로 구분합니다. 쿠키를 삭제하거나 다른 브라우저·주소로 접속하면 다른 일반 사용자로 취급합니다. 같은 브라우저 프로필을 공유하는 사람은 같은 작업공간을 씁니다. 중요한 초안은 JSON으로 보관하세요.
- 관리자 세션은 12시간입니다. 서버 재시작·로그아웃·전체 복구 후에는 관리 기능만 다시 로그인합니다.

## 3. 운항 CSV

관리자로 로그인한 뒤 **운항 정보 → CSV 불러오기 → CSV 서식 받기**를 사용하세요. `ship` 열에는 화면에 안내된 선박 ID를 넣습니다.

- 필수 열: `ship,date,fuel,factor,distance,speed,fuelType`
- 선택 열: `position,voyage,draft,weather,engineHours,note`
- 단위: 연료 t, 거리 nm, 속력 kn, 흘수 m, 시간 h. 날짜 `YYYY-MM-DD`.
- CO₂ = 각 기록의 연료 × 입력 배출계수. 배출계수는 실제 연료에 맞게 확인하세요.
- 최대 1MB·1,000개 기록. 누락·숫자 범위·일자·중복을 행별로 표시합니다. 동일 선박·일자는 한 건만. 이전 기록보다 연료가 2배 이상이면 점검 사유가 필요합니다. 하나라도 실패하면 전체를 반영하지 않습니다.

필드 정의는 [`data-model.md`](data-model.md#3-운항)를 참고하세요.

## 4. 보고서와 기준 비교

- Noon 초안: 선택한 기간의 마지막 기록 하루. MRV 검토 초안: 선택 기간 전체.
- 선박·기간·항차·연료 종류·계수·수치·위치·흘수·기상·기관 운전시간 등을 표시하고, 없는 항목은 `[미입력 · 확인 필요]`로 표시합니다.
- 팀이 검토하는 기본 서식이며, 공식 Noon/MRV 제출 서식 충족을 인증하지 않습니다.
- 저장 충돌 시 내 편집 내용은 유지됩니다. 서버 내용을 확인하고 JSON으로 보관하거나 최신 버전을 확인한 후 대체 저장할 수 있습니다.
- 통합 답변의 **적용 기준 확인**은 근거 구절, 비교 지표, 조건과 기준값을 사용자가 직접 지정해 `입력 기준 충족 / 미충족 / 판단 불가`를 표시하는 기능입니다. 규정 적용 여부를 자동 판정하지 않습니다.

## 5. 외부 AI 답변 (선택)

기존 루트 `.env`를 보존하고 [README의 모델 서버 연결](../README.md#모델-서버-연결)에 따라 `LLM_API_BASE_URL`·`OPENAI_MODEL`을 설정합니다. OpenAI 호스트에는 `OPENAI_API_KEY`, 동국 도메인에는 `DONGUK_AI_CHAT_API_KEY`가 필요하며 로컬 Ollama는 키 없이 사용할 수 있습니다. 공급자 키는 해당 호스트에만 전송하며 다른 호환 서버에 자동으로 전달하지 않습니다. `LLM_RESPONSE_FORMAT`은 기본 `text`로 두고 지원이 확인된 경우에만 변경합니다.

이전 URL·출력 형식 변수 이름은 README의 전환 안내에 따라 바꾸고, Docker에서는 루트에서 `docker compose up -d --build backend frontend`로 컨테이너를 재생성합니다. 모델 설정이 유효하면 통합 질문에서 **AI 답변**을 선택할 수 있지만 실제 접속 성공을 보장하지는 않습니다. 근거가 있는 질문에서 `generation=llm`·유효 인용·모델 실패 경고 없음을 확인하세요. 키는 브라우저로 보내지 않으며 실패하면 원문 발췌로 돌아갑니다. 실제 동국·Ollama 호출은 아직 미검증입니다.

## 6. 백업과 복구

- **백업 만들기**: 문서·PDF·운항·보고서·계정 및 권한·질의·로그·승인·앱 설정을 JSON으로 DB 옆 `backups` 폴더에 보관합니다.
- **해사 데이터 사용 시**: 앱 JSON 백업은 MRV·합성 Noon·출처·품질 테이블이나 원본 파일을 포함하지 않습니다. PostgreSQL과 원본 파일을 별도로 백업하세요. 앱 복구 후 기존 선박 연결은 동일한 식별정보가 확인된 경우만 유지되고, 누락·불일치는 연결 해제 건수로 기록됩니다. 원본 해사 데이터는 남습니다.
- **파일 보관 / 가져오기**: 다른 저장장치에 보관할 파일을 내려받고, 100MB 이하의 전체 백업을 목록에 추가합니다(형식·체크섬 검증).
- **복구**: 선택한 시점으로 현재 데이터를 교체합니다. 복구 직전 자동 백업, 트랜잭션 복구, 검색 인덱스 재생성, 모든 세션 무효화를 수행합니다. 관리 기능은 `admin / 1234`로 다시 로그인합니다.
- **자동 백업**: 기본 하루 1회(UTC 날짜 기준, 서버 실행 중 1분마다 확인). 관리 화면에서 끌 수 있고 자동 삭제는 하지 않습니다.
- `.env`는 백업에 포함되지 않으니 별도로 보관합니다.
- 서버가 켜지지 않으면 정상 종료된 상태의 DB 폴더(기본 `backend/data`) 복사본을 복원할 수 있습니다. 실행 중인 DB를 임의로 교체하지 마세요.

해사 CSV 적재나 선박 연결 작업 중 복구를 요청하면 잠금을 최대 5초 기다린 뒤 BUSY 응답으로 거절할 수 있습니다. 앱 데이터·해사 연결은 변경하지 않으므로 진행 중인 작업이 끝난 다음 복구를 다시 요청하세요.

## 7. 같은 네트워크의 팀원이 접속하기 · 서버에 올리기

기본 실행은 이 PC에서만 접속됩니다(frontend 포트가 `127.0.0.1`에만 열림). 다른 PC에서 접속하게 하려면 최상위 `.env`에 아래 두 값을 넣고 `docker compose up -d`로 다시 시작합니다.

```dotenv
HAEDAP_BIND=0.0.0.0
HAEDAP_ALLOWED_HOSTS=192.168.0.10        # 팀원이 주소창에 입력할 이 PC의 IP 또는 서버 도메인(쉼표로 여러 개)
```

팀원은 `http://192.168.0.10:5173`으로 접속해 로그인 없이 기본 기능을 사용합니다. `HAEDAP_ALLOWED_HOSTS`에 없는 주소로 들어온 요청은 `HOST_DENIED`(403)로 거부합니다. **접속자 IP를 같은 서브넷으로 제한하지는 않으므로** 신뢰할 수 있는 네트워크에서만 켜고, 필요하면 OS 방화벽을 씁니다. Ubuntu는 `sudo ufw allow from 192.168.0.0/24 to any port 5173`, Windows는 인바운드 규칙의 원격 주소를 "로컬 서브넷"으로 제한합니다.

TLS(HTTPS)는 포함하지 않습니다. 인터넷에 공개하는 서버라면 Nginx·Caddy 같은 리버스 프록시를 앞에 두고, 그 도메인을 `HAEDAP_ALLOWED_HOSTS`에 넣으세요. PostgreSQL과 FastAPI는 어떤 경우에도 외부에 공개하지 않습니다(운영 compose는 두 포트를 열지 않음). 공유 서버에서는 `.env`의 `POSTGRES_PASSWORD`를 기본값에서 바꾸세요. **이미 만들어진 DB 볼륨의 비밀번호는 `.env`만 바꿔서는 바뀌지 않습니다** — 처음 시작하기 전에 정하거나, DB 안에서 `ALTER USER`로 바꿉니다.

## 8. 새 버전으로 바꾸기

데이터는 Docker 볼륨(`haedap_db-data`, `haedap_backups`)에 있으므로 코드만 바꾸고 다시 빌드하면 됩니다.

```bash
git pull
docker compose up --build -d
```

`docker compose down -v`는 **볼륨까지 지우므로** 데이터를 지우려는 경우에만 씁니다. 업그레이드 전에는 관리 → 백업·복구에서 백업을 만들고 내려받아 두세요.

새 버전에 DB 마이그레이션(`migrations/`의 새 파일)이 있으면 `docker compose up` 때 `migrate` 서비스가 자동으로 적용합니다. 적용 결과는 `docker compose logs migrate`, 현재 상태는 `docker compose run --rm migrate status`로 확인합니다. 마이그레이션이 실패하면 그 파일 전체가 롤백되고 backend는 시작하지 않습니다([데이터 모델 8절](data-model.md#8-스키마를-바꿀-때)).

이전 Node/SQLite 버전의 데이터(`backend/data/haedap.sqlite`)를 옮기는 도구는 제공하지 않습니다.

## 9. 문제 해결

| 증상 | 확인할 내용 |
|---|---|
| `docker compose` 명령이 없음 | Docker Desktop(Windows·macOS) 또는 Docker Engine + Compose 플러그인(Ubuntu) 설치 |
| 화면이 안 열림 | `docker compose ps`로 세 서비스가 `healthy`인지 확인. 아니면 `docker compose logs backend` |
| `DATA_SOURCE_UNAVAILABLE`, `SCHEMA_NOT_READY` | DB 연결·스키마 문제. `docker compose logs migrate`로 마이그레이션 결과 확인. compose 밖에서 만든 DB라면 `npx --yes dbmate@2.36.0 -d migrations up` 적용 여부 확인 |
| backend가 시작하지 않음 | `docker compose ps -a`에서 `migrate`가 실패(Exit ≠ 0)했는지 확인 → `docker compose logs migrate` |
| DB 비밀번호 인증 실패 | 볼륨을 만든 뒤 `POSTGRES_PASSWORD`를 바꾼 경우. 원래 값으로 되돌리거나 DB에서 `ALTER USER` |
| `HOST_DENIED` (403) | 접속한 주소를 `.env`의 `HAEDAP_ALLOWED_HOSTS`에 추가 후 `docker compose up -d` |
| 포트 사용 중 | `.env`의 `PORT`(공개 포트)를 바꿈. 개발 오버레이의 5432·8000이 겹치면 `POSTGRES_PORT`를 바꾸거나 해당 프로그램 종료 |
| 수정한 코드가 반영되지 않음 | 운영 compose는 이미지에 코드를 담으므로 `--build` 필요. 개발 오버레이에서 저장이 감지되지 않으면 `compose.dev.yaml`의 `WATCHPACK_POLLING` 주석 해제 |
| 의존성을 바꿨는데 반영되지 않음 | `docker compose … up --build` (의존성은 이미지에 설치됨) |
| 큰 PDF·백업 업로드가 끊김 | 101MB 이하인지 확인(`frontend/next.config.mjs`의 `proxyClientMaxBodySize`) |
| 관리자 로그인 실패 | `admin / 1234` 확인. 1분에 10번 넘게 틀리면 잠시 기다림 |
| backend 재시작 후 로그아웃됨 | 관리자 세션은 backend 메모리에 있어 정상 동작 |
| 등록·수정·삭제 버튼이 안 보임 | 관리자 로그인 여부 확인 |
| 문서가 안 보임 | 열람 범위·사용 중/이전/폐기 필터 확인 |
| 운항 화면이 비어 있음 | 선박·기록 등록 및 기간 확인. 가상 예시는 관리자 버튼으로 등록 |
| PDF 추출 실패 | 암호·손상·스캔 여부 확인. 텍스트 PDF 또는 페이지별 본문 입력 |
| 보고서 수정 불가 | 검토 중/승인 완료 상태는 복사 후 새 초안으로 작성 |
| 검토 대기 상태 | 관리자 계정으로 관리 → 승인에서 처리 |

## 10. 해사 데이터 Tool (선택)

역할4 도구입니다. 실행 중 조회·계산은 `backend/tools/`, 오프라인 자료 준비·적재는 `scripts/`, DDL은 루트 `migrations/`에 있습니다. 모두 backend uv 환경을 사용합니다. 계약은 [API 명세](specs/tools.md)와 [데이터 명세](specs/prepare-data.md), 테이블·ERD는 [데이터 모델](data-model.md#9-postgresql-해사-데이터-tool-선택)에 있습니다. 아래 명령은 별도 표시가 없으면 저장소 최상위에서 실행합니다.

### 설치와 실행

Python 의존성은 backend와 같은 `backend/pyproject.toml`·`uv.lock`으로 관리합니다. 전처리 스크립트에만 필요한 pandas·openpyxl은 `data` 그룹입니다.

```bash
uv sync --project backend --group data
```

**앱에 마운트(권장)**: 최상위 `.env`에 `MARITIME_DATA_API_TOKEN`(직접 생성한 32자 이상 토큰)을 넣고 `docker compose up --build -d`로 시작합니다. 기본 앱 init과 새 해사 마이그레이션이 같은 DB에 적용된 뒤 backend가 시작합니다. 토큰이 비어 있으면 해사 라우트가 만들어지지 않습니다. 개발 오버레이에서는 <http://127.0.0.1:8000/docs>에서 Authorize에 토큰을 넣고 시험할 수 있습니다. 일반 앱 health는 DB를 확인하지만 해사 CSV가 적재되었음을 보증하지 않습니다.

**별도 해사 DB를 선택하는 경우**: `MARITIME_DATA_DATABASE_URL`로 다른 DB를 지정할 수 있습니다. compose의 기본 migrate 서비스는 앱 DB만 대상으로 하므로 별도 DB에도 같은 `migrations/`의 기본 init과 해사 migration을 따로 적용해야 합니다. 그 DB의 `public.ships`가 연결 대상이며 앱 DB를 넘는 외래키·자동 선박 동기화는 지원하지 않습니다. 특별한 이유가 없으면 같은 `DATABASE_URL`을 사용하세요.

**독립 실행(역할4 도구 작업용)**: 최상위 `.env`에 `DATABASE_URL`과 `MARITIME_DATA_API_TOKEN`을 두고 환경파일을 명시해 실행합니다. 기존 `.env.local` 설정을 쓸 때는 아래 `--env-file`에 해당 파일을 지정합니다. 기존 파일을 무조건 덮어쓰지 마세요.

```bash
cd backend
uv run --env-file ../.env uvicorn tools.api:create_app --factory --host 127.0.0.1 --port 8001
```

`/api/health`의 `database_checked=false`는 프로세스만 확인했으며 DB를 검증하지 않았다는 뜻입니다. 실제 DB 조회는 토큰을 포함한 `/api/maritime-data/query`로 확인합니다. 503이면 PostgreSQL 실행·연결·스키마 적재 상태를 확인하세요. 원본·CSV·DB·비밀번호·토큰은 Git에 넣지 않습니다.

### 마이그레이션·전처리·적재·검증

자료 준비·적재는 호스트 PC의 Python·uv에서 실행합니다. Docker로 앱을 시작했다면 기본 DB 포트는 호스트에 열리지 않으므로 개발 오버레이의 루프백 DB 포트를 사용하세요(`docker compose -f compose.yaml -f compose.dev.yaml up -d db`). 최상위 `.env`에서 `DATABASE_URL` 예제의 주석을 해제하고 실제 `POSTGRES_USER`·비밀번호·DB·호스트 포트와 일치시킵니다. 기본 호스트는 `127.0.0.1:5432`이며 `POSTGRES_PORT`를 바꿨으면 그 포트를 사용합니다. 컨테이너 내부의 `db:5432` 주소를 호스트 도구에 사용하지 않습니다.

직접 PostgreSQL을 쓰는 경우에는 해당 DB의 호스트용 `DATABASE_URL`을 설정합니다. 이미 `docker compose up`으로 migration이 끝났으면 다시 적용할 필요가 없습니다. 아직 적용하지 않았거나 Docker 없이 준비한다면 저장소 최상위에서 다음 명령을 사용합니다. 기존 DB는 먼저 PostgreSQL 백업을 보관하세요. 아래 과정은 기존 데이터를 삭제하지 않습니다.

```powershell
npx --yes dbmate@2.36.0 -d migrations --no-dump-schema up
```

```powershell
uv run --locked --project backend --group data python -m scripts.prepare_maritime_data --source D:/Data --out data/maritime-data/new-run
uv run --locked --project backend python -m scripts.load_data --data-dir data/maritime-data/new-run
# 미리보기에서 입력 파일·건수를 확인한 뒤 적용
uv run --locked --project backend python -m scripts.load_data --data-dir data/maritime-data/new-run --apply
uv run --locked --project backend python -m scripts.describe_maritime_data
cd backend; uv run pytest; cd ..
uv run --locked --project backend --group data python -m scripts.test_prepare_maritime_data
```

이미 전처리한 CSV가 있으면 첫 명령을 생략합니다. loader는 backend의 psycopg를 사용하므로 별도 `psql.exe`가 필요 없습니다. 기본 실행은 파일·헤더·요약 건수를 확인하는 미리보기이며 DB에 연결하지 않습니다. `--apply`를 추가해야 DB에 연결하여 dbmate의 해사 migration 적용 이력(`20261013010000`)과 6개 대상 테이블을 확인하고 COPY합니다. 하나라도 비어 있지 않으면 중단하며 기존 레코드를 삭제·덮어쓰지 않습니다. 실패 시 단일 적재 트랜잭션을 롤백합니다. 설정은 루트 `.env`가 기본이고 환경변수가 우선하며 `--env-file`로 바꿀 수 있습니다. DB 주소는 `DATABASE_URL`을 사용합니다.

Windows 호환 래퍼는 `./scripts/load-maritime-data.ps1 -DataDir data/maritime-data/new-run`(미리보기), 같은 명령의 `-Apply`(실제 적재)입니다. uv가 PATH에 없으면 `-Uv 'uv 실행 파일 경로'`를 지정합니다. 이전 `-PgBin` 옵션은 없습니다. 버전별 과거 기대값을 확인하는 수동 SQL은 `scripts/verify_load.sql`이며 일반 loader는 입력 `summary.json`의 건수를 검증합니다.

필드 사전 생성기는 전처리 CSV의 `dictionary.json`만 생성합니다(기본 `output/maritime-data-contract/`, 변경은 `--out`). CSV 원본 필드 70개와 관리용 DB 컬럼 `vessels.ship_id`를 구분합니다. DDL·마이그레이션·설명·ERD는 덮어쓰지 않으며 스키마 변경은 새 dbmate migration으로만 관리합니다.

`MARITIME_DATA_TEST_DATABASE_URL`을 지정해야 기존 PostgreSQL 적재 데이터를 사용하는 읽기 전용 테스트가 실행됩니다. 미설정 시 이 테스트는 건너뛰며 단위 테스트 통과만으로 실 DB 검증을 주장하지 않습니다. API가 조회할 DB 사용자는 승인 뷰·출처 테이블에 필요한 읽기 권한만 갖도록 설정하는 것을 권장합니다. 도구의 READ ONLY 트랜잭션은 DB 사용자의 권한 자체를 바꾸지 않습니다.

### 이전 역할4 스키마·설정의 채택

기존 `role4` 또는 `maritime_data` 스키마가 하나만 있는 DB에는 새 해사 migration이 기대 구조를 검증하고 채택합니다. `role4`인 경우 이름을 `maritime_data`로 바꾸되 원본 행을 다시 적재하지 않습니다. 양쪽이 함께 있거나 구조가 맞지 않으면 migration 전체를 거절하므로 임의로 테이블을 삭제해서 통과시키지 마세요. 백업과 구조를 확인한 뒤 충돌 원인을 해결해야 합니다. 기존 데이터가 있는 테이블에는 CSV loader를 실행하지 않습니다. 데이터가 있는 해사 스키마의 rollback도 거절합니다.

이전 `role4/.env.local` 설정은 검토·백업 후 최상위 설정으로 옮깁니다. 원본 파일이나 비밀번호를 문서·Git에 복사하지 마세요. `scripts/migrate_maritime_data.py`는 이전 환경 호환용 보조 도구로만 남으며 새 설치·일반 업데이트 절차에서는 실행하지 않습니다. 표준 스키마 채택·변경은 위 dbmate 명령으로만 관리합니다. 스키마 채택은 공식 입력 검증을 의미하지 않습니다.

### 팀 앱 연결 시 참고

backend 코드는 `from tools import query, calculations, agent`로 공통 로직을 바로 호출할 수 있습니다(같은 프로세스). 기존 앱 선박과의 연결은 `vessels.ship_id`에 검토한 매핑만 지정합니다. 원본 키는 보존하고 앱 선박을 대량 자동 생성하거나 MRV를 일별 기록으로 변환하지 않습니다. 운항 화면의 MRV 분석은 일반 앱 권한·CSRF·감사 경계에서 명시 매핑과 정체성을 확인해 참고 계산을 실행합니다. 토큰을 브라우저로 보내지 않습니다. 통합 질문의 자동 MRV 호출은 후속 범위입니다. 현재 경계는 [아키텍처](architecture.md#8-해사-데이터-tool의-경계-선택), [업무 스킬](specs/workflow-skills.md)을 참고하세요.

### 기존 앱 선박에 명시적으로 연결하기

먼저 앱에 관리할 선박을 등록하고 실제 자료의 IMO가 같은지 확인합니다. 다음 예제의 `등록된-app-id`는 그 선박의 실제 `ships.id`로 바꿉니다. CLI는 저장소 루트 `.env`를 기본으로 읽고 환경변수가 우선합니다(`--env-file`로 변경 가능). 이 작업은 같은 DB의 `DATABASE_URL`만 사용하며 `MARITIME_DATA_DATABASE_URL`로 별도 DB를 지정해도 자동으로 옮기거나 동기화하지 않습니다.

```powershell
# 미리보기: DB를 변경하지 않음
uv run --locked --project backend python -m scripts.link_ship --vessel-id REAL:IMO:9074729 --ship-id '등록된-app-id'
# IMO·대상 선박을 검토한 뒤 같은 요청 적용
uv run --locked --project backend python -m scripts.link_ship --vessel-id REAL:IMO:9074729 --ship-id '등록된-app-id' --apply
```

실제 원본은 등록된 비샘플 앱 선박의 IMO가 같아야 합니다. 합성 선박은 `SYN:*` 원본과 `sample=true`인 앱 예시 선박에만 `--confirm-synthetic`을 추가하여 연결합니다. 다른 기존 연결의 덮어쓰기나 하나의 앱 선박에 여러 원본 선박 연결은 거절하며, 동일 연결의 재실행은 값을 바꾸지 않습니다. 연결되지 않은 외부 선박도 원본 MRV/Noon 조회에는 남습니다. 연결은 원본의 사실성·공식 CII 입력 검증을 대신하지 않습니다.

연결 후 운항 화면에서 실제 선박의 IMO·샘플 구분이나 합성 선박의 이름·선종·DWT·IMO·샘플 구분을 바꾸면 `MARITIME_SHIP_IDENTITY_CONFLICT`(409)로 거절합니다. 실제 선박은 같은 IMO를 유지하면 이름·DWT를 수정할 수 있습니다. 식별정보를 바꿔야 한다면 관리자가 연결을 수동 검토·해제한 뒤 수정하고, 새 식별정보를 확인해 다시 연결하세요. 앱이 원본 해사 자료나 기존 연결을 임의로 바꾸지는 않습니다.

### 원본 확보·공개 참조 자료·기존 데이터 버전

이 저장소에는 코드, 데이터 정의, SQL, API 계약만 포함합니다. 원본·전처리 CSV, PostgreSQL 데이터 디렉터리, 로그인 정보는 포함하지 않습니다. 공개 열람 가능과 재배포 허용은 다르므로 이용조건이 확인되지 않은 원본을 GitHub에 재게시하지 않았습니다.

#### 전처리 원본 6종

`scripts/prepare_maritime_data.py`는 아래 파일명을 기준으로 원본 폴더를 재귀 검색합니다. 팀 보유본 또는 출처에서 해당 버전을 확보해야 하며 최신 웹 다운로드가 동일 파일·동일 건수를 보장하지는 않습니다. 이번 분리는 자동 다운로드 기능을 새로 추가한 것이 아닙니다.

| ID | 원본 파일 | 용도 |
|---|---|---|
| DS-001 | `eu_mrv_vessel_annual_2018_2022.csv` | 실제 MRV 과거 보고기간 자료 |
| DS-002 | `해양수산부_선박_AIS_동적정보_20220101.csv` | 마스킹 AIS 참고자료, 선박 자동 연결 제외 |
| DS-003 | `UpdatedPub150.csv` | WPI 항구 참조 |
| DS-004 | `Smart-Maritime-Council-Standardised-Vessel-Dataset-SVD-for-Noon-Reports-and-Emissions-Reporting-V2-May-2025.xlsx` | SVD 컬럼 설계 참고 |
| DS-005 | `2025-v57-12092026-EU_MRV_Publication_of_information.xlsx` | 실제 MRV 보고 자료 |
| DS-006 | `synthetic_noon_daily_2025.csv` | 개발·검증용 합성 Noon |

실제 MRV 두 자료와 합성 Noon을 조회 대상으로 선정했고 AIS·항구·SVD는 참고 자료로만 보존합니다. 원본별 URL·SHA256은 전처리 출력 `source_files.csv`와 `summary.json`에 보존됩니다. 팀에서 데이터 전달 시 이 두 파일, CSV 6개 및 원본 추적에 필요한 `raw_records.jsonl`을 함께 전달하세요. 정확한 기존 버전의 재확보가 안 되면 새 자료를 기존 정답 건수에 맞추지 말고 새 데이터 버전으로 검증해야 합니다.

#### 공개 참조 자료

| 자료 | 보유 결과 및 제한 | 처리 코드 |
|---|---|---|
| GISIS EEDI | 11,244행, 익명·반올림, IMO 번호 없음 | `prepare_gisis_eedi.py` |
| IMO DCS 연차 보고서 | 2019~2024 공개 집계, 선박 단위 결합 불가 | `prepare_open_cii_references.py` |
| Wikidata / MarineVessels | MRV 25,240척 중 15,956척에 DWT 후보, 법정 검증값 아님 | `prepare_open_cii_references.py` |

GISIS 정규화는 `uv run --locked --project backend --group data python -m scripts.prepare_gisis_eedi INPUT.xlsx OUTPUT_DIR`로 실행합니다. 공개 CII 참조 처리 스크립트는 `data/maritime-data/2026-09-30-v2/reference/`의 수집 완료 파일을 입력으로 요구하며 자동 수집기가 아닙니다. 입력 구조: `reference/marine-vessels-2015/marine_vessels.csv`, `reference/wikidata-vessel-particulars/wikidata_ships_with_deadweight.csv`, `reference/imo-dcs-public-reports/`입니다. GISIS EEDI 원본 갱신일은 2025-12-02이며 익명 자료이므로 실제 MRV와 연결하지 않습니다. DWT 후보 출처 간 5% 초과 충돌은 검토 대상으로 남깁니다.

공식 CII 산정에 필요한 동일 선박·동일 연도의 검증된 연료별 사용량, 항해거리, 적용 선종·용량 및 보정 조건은 아직 충분히 확보되지 않았습니다. 공개 집계와 제원 후보를 공식 입력으로 자동 승격하지 않습니다.

### DWT 후보를 참고 지표에 연결하기 (선택)

기존 MRV 적재 후 추가 제원 migration을 적용하고 확보한 후보 CSV를 별도로 적재한다. 원본 파일은 저장소에 포함하지 않는다. 다음 명령은 저장소 루트에서 실행한다.

```powershell
# 먼저 기존 안내에 따라 호스트 DATABASE_URL과 migration을 준비한다.
npx --yes dbmate@2.36.0 -d migrations --no-dump-schema up
uv run --locked --project backend python -m scripts.load_capacity_candidates --csv D:/Data/vessel_capacity_candidates.csv
# 미리보기 행 수·DWT 보유·충돌·해시 확인 후 적용
uv run --locked --project backend python -m scripts.load_capacity_candidates --csv D:/Data/vessel_capacity_candidates.csv --apply
```

서버 Bearer 인증으로 `POST /api/maritime-data/reference-intensity`에 `{"scope":{"dataset":"real_annual","vessel_id":"REAL:IMO:9074729","year":2023},"accept_reference_limitations":true}`를 보낸다. 예시 ID·연도의 실제 레코드/후보가 없으면 blocked다. 성공은 `estimated`이며 `reference_dwt_intensity`와 CO₂·추정 거리·DWT·출처 스냅샷·한계 경고를 함께 확인한다. 공식 CII나 등급이 아니다. 기존 `/calculate`의 실제 MRV blocked 정책은 유지한다. 앱의 운항 정보 화면에서 참고값 분석 기능을 펼쳐 매핑된 선박·연도를 선택해 실행할 수 있다.

후보 DWT가 있어도 선종·양수 CO₂/거리·출처 일치·단일 승인 보고 조건을 만족해야 한다. 거리·DCS 범위·시점별 제원은 여전히 미검증이다. 참고값을 공식 등급으로 표시하거나 추정거리를 검증거리로 바꾸지 않는다. 참조 테이블이 비어 있지 않으면 적재를 거절한다. 앱 JSON 백업에는 참조 테이블이 없으므로 PostgreSQL/CSV를 따로 백업한다.

#### 기존 데이터 버전

2026-09-30 로컬 적재 기록: MRV 80,552행 중 조회 대상 79,032행, Partial 1,520행은 보존하되 기본 조회에서 제외. 합성 Noon 4,380행·238항차이며 거리 0인 기록 557행은 연료량을 보존합니다. 이 수치는 저장소에 데이터가 포함되거나 이번 작업에서 DB를 재검증했다는 의미가 아닙니다. 다른 데이터 버전에서는 `scripts/verify_load.sql`의 기대값을 검토하세요.
