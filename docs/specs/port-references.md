# 선박 AIS·선석 조건 참조 API

- 상태: 구현됨 (서버 참조 API·로그인 상세 화면·기존 질문창, 로컬 시범)
- 작성: 역할4 · 2026-11-04
- 관련: [작업 계획](../plans/2026-11-04-port-reference-linkage.md), [기존 해사 API](tools.md)

## 목적과 경계

기존 MRV의 실제 IMO와 공개 AIS metadata를 연결하고, 항만청이 공개한 개별 선석의 명시적 최대 LOA·흘수 값과 대조한다. 결과는 자료 기반 사전 비교이며 입항 허가·안전 항해·선석 배정·화물 적합성·공식 CII 판정이 아니다. 기존 통합 질문의 제한된 항구 질의와 일반 로그인 운항 상세 화면에서 사용할 수 있다. 모델이 직접 도구를 선택하는 범용 라우팅은 별도다.

### 다중 항구·오프라인 묶음 계약

신규 `NAVIGATION-REFERENCES-1.1`은 항구별 `source_id`, 자료의 용도 범위 `reference_scope`를 갖고, 1.0 파일도 기본값을 적용해 계속 읽는다. Helsinki의 원문 표에 있는 `Maximum vessel draft`와 명시적인 `max vessel length`만 수치로 사용한다. `Berth length`, 수심, apron width는 허용 선박 길이·흘수·선폭으로 변환하지 않는다. `Date of last berth survey`는 원문에 보존하고 전체 자료 적용일/최신 검증일로 승격하지 않는다. 출처 누락·다른 항구 출처 혼합은 거절하며 노후화는 선택 항구의 수집본으로 평가한다.

호환성은 새 코드가 기존 1.0을 읽는 방향이다. 1.1 묶음을 반입할 때는 새 코드/이미지를 먼저 준비해야 한다. 원문 variants의 조건·위치와 게시 수치가 최종 참조 필드와 다르면 파일을 거절한다. AIS 흘수 255의 하한값은 별도 사유로 남기고 정확값 비교에 사용하지 않는다.

오프라인 관리자 CLI는 catalog·해시 manifest·출처 안내만 묶어 내보낸다. 검사/설치는 네트워크·계정·DB 접속 없이 수행하고 파일 크기·SHA256·모델·정해진 파일 이름을 검사한다. 기존 target을 교체하려면 예상 현재 해시가 일치해야 하며 기존 파일은 해시 이름으로 백업하고 새 파일을 원자 교체한다. 수집/생성 시각을 바꾸지 않으며, 오래된 묶음도 설치 후 API에서 계속 보류한다. 동시 설치 잠금·심볼릭 링크 거절·이전 파일 보존을 검증한다. 웹 업로드·임의 요청 경로·자동 인터넷 수집은 추가하지 않는다.

## 데이터 준비

`scripts.prepare_navigation_references`는 명시적 `fetch`에서만 정해진 공식 URL을 조회한다. 오프라인 `prepare`는 해시가 검증된 원문·manifest·기존 `vessels.csv`·WPI 입력으로 별도 catalog JSON을 생성한다. `MARITIME_PORT_REFERENCES_PATH`는 서버 관리자가 설정하는 파일 경로이며 요청 본문으로 파일·URL·SQL·검증 시각을 받지 않는다. 누락·잘못된 snapshot은 503이다. 런타임 인터넷 요청은 없다.

- Fintraffic / digitraffic.fi, CC BY 4.0. 가공 내역은 IMO 교집합·단위 변환·품질/시각 검사다. AIS 데이터는 선박 신고값이고, 공식 API 제공자의 이름이 실측·법정 검증을 의미하지 않는다. 제공 범위는 핀란드·주변 해역의 수신 범위이며 전 세계 보장 데이터가 아니다.
- metadata의 `timestamp`는 Unix 밀리초의 레코드 시각이다. 흘수 실측 시각으로 승격하지 않는다. `draught`는 1/10m, 0은 미제공, 255는 25.5m 이상이므로 정확값으로 사용하지 않는다. 항해 ETA의 연도를 추정하지 않는다. 안테나 A+B / C+D 합은 AIS 신고 길이·폭이며 법정 제원이 아니다. 일부 치수 0·최댓값은 보수적으로 보류한다.
- 정확 IMO·체크섬으로만 연결한다. 같은 IMO의 여러 MMSI나 같은 MMSI의 다른 IMO는 자동 선택하지 않는다. 기존 MRV 수치·DWT·과거 흘수는 수정하지 않는다.
- WPI↔항만청 자료는 명시한 UN/LOCODE와 유일 WPI ID를 함께 확인한다. 항구명 유사도 조인은 없다. 선석별 원문과 source hash·개정/수집 시각을 보존한다. 최대 선박 LOA와 물리적 부두 길이를 혼동하지 않는다.
- Helsinki는 FIHEL / WPI:28190에 연결된 크루즈 선석 8개가 대상이다. 원문에서 유일하게 선박 최대 길이를 명시한 LHD의 360m만 LOA로 사용하고 나머지 부두 길이는 조건 텍스트에 보존한다. 각 표의 최대 흘수와 조사 연도 2021도 구분한다. 크루즈 자료를 항구 전체·화물선용 조건으로 확대하지 않는다.
- 조건부 흘수·길이 범위·같은 선석의 상충 원문은 하나의 상한으로 평탄화하지 않는다. 출처의 풍속·예선·수위·밀도·다른 선석 점유 조건은 보존하며 이번 함수가 자동 충족 판정하지 않는다.

## API

아래 독립 Tool API는 기존 `/api/maritime-data/*`와 같은 서버 전용 Bearer 인증을 사용한다. 브라우저용 로그인 어댑터는 뒤의 별도 계약을 따른다.

- `GET /api/maritime-data/port-reference-catalog`: snapshot 식별·출처·제공 포트·선석 목록과 한계. 전체 선박 관측값은 반환하지 않는다.
- `POST /api/maritime-data/port-reference-screen`: `vessel_id` (`REAL:IMO:7자리`), `port_id` (`WPI:번호`), 선택적 `berth_id`를 받는다. 현재 PostgreSQL에서 REAL vessel 정체성을 검사한 뒤 snapshot을 사용한다. 자료 없는 선박은 데이터 부족 응답이며 다른 IMO로 대체하지 않는다. 모르는 port/berth는 404다.

결과는 `reference_only=true`, `admission=not_assessed`를 유지한다. 비교 상태는 `within_listed_reference`, `above_listed_reference`, `unavailable`이며 전체 상태는 `published_reference_exceeded`, `partial_reference_check`, `insufficient_data`다. 숫자는 Decimal 문자열이고 조건·부족 항목·원문 위치·출처·기준 시각을 함께 제공한다. 전체 상태가 부분 비교 통과여도 실제 입항 가능을 뜻하지 않는다.

노후화 정책은 소프트웨어의 보수적 기준이며 항만 규정이 아니다. AIS 레코드와 AIS 수집본은 24시간, 항만 snapshot 수집 후 30일을 넘으면 숫자를 현재 비교에 사용하지 않는다. 미래 시각·미확인 AIS 레코드 시각·동일 식별자의 복수 기록도 보류한다. 매 요청 서버 시각으로 재판정하며 수집일을 개정일로 바꾸지 않는다. 항만 원문의 개정일은 미확인이므로 경고와 확인 필요 항목에 남긴다. 전체 카탈로그의 생성 시각이 미래이거나 30일 초과인 경우도 보류한다.

## 실행 예시

저장소 최상위에서 기존 backend uv 환경을 사용한다. 추가 패키지·DB migration은 없다. 원본은 git 제외 경로에 별도 보관하고, 기존 전처리 파일·운영 DB를 덮어쓰지 않는다.

```bash
uv run --project backend python -m scripts.prepare_navigation_references fetch --raw-dir output/navigation-references/raw-new --include-helsinki
uv run --project backend python -m scripts.prepare_navigation_references prepare --raw-dir output/navigation-references/raw-new --vessels /path/to/vessels.csv --wpi /path/to/UpdatedPub150.csv --output output/navigation-references/catalog.json
```

`fetch`는 기존 원본 디렉터리가 있으면 덮어쓰지 않는다. `prepare`는 해시 고정 원본을 오프라인으로 처리한다. AIS 수집 실패·단위 계약 변경·유일하지 않은 SEGOT/WPI 연결은 새 결과 생성 전에 오류가 난다. 카탈로그를 다시 준비한다고 오래된 AIS 레코드가 새 관측값으로 바뀌지 않는다.

`--include-helsinki`를 생략하면 기존 Gothenburg 자료만 수집한다. 지정한 경우 Helsinki 수집 실패도 오류이며 요청한 항구를 조용히 제외하지 않는다. 준비 시 원문 표의 빈 두 번째 헤더 셀은 허용하되, 검토되지 않은 선석 번호·변경된 열/행 병합·조건 잘림은 오류로 처리한다.

직접 실행에서는 `MARITIME_PORT_REFERENCES_PATH`를 생성한 JSON의 절대경로로 설정하고 기존 API 서버를 실행한다. 이미 실행 중인 서버의 환경변수를 바꾸면 재시작해야 한다. 같은 경로의 JSON을 갱신하면 다음 요청부터 새 파일의 형식·크기·시각을 검증한다.

Docker는 `.env`에 호스트 파일 경로만 적는 것으로 파일이 전달되지 않는다. 설치 디렉터리의 절대경로를 `MARITIME_PORT_REFERENCES_DIR`에 지정하고 `docker compose -f compose.yaml -f compose.navigation.yaml up --build -d`로 실행한다. 기존 기본 Compose에는 이 파일을 자동 추가하지 않는다. 새 디렉터리를 자동 생성하지 않으며 폴더 전체를 읽기 전용으로 마운트해 원자적 파일 교체가 다음 요청에 반영되게 한다. 일반 앱 로그인 조회에는 서버 Bearer가 필요하지 않다. 독립 Tool API도 사용할 때만 `MARITIME_DATA_API_TOKEN`을 기존 안내에 따라 별도 설정한다.

```yaml
services:
  backend:
    environment:
      MARITIME_PORT_REFERENCES_PATH: /references/catalog.json
    volumes:
      - ./output/navigation-references:/references:ro
```

서버 측 Python 호출 예시다. 토큰을 브라우저 코드에 넣지 않는다. IMO 9240249는 2026-11-04 확보 snapshot의 실제 MRV 교집합에 포함됐다. 후속 수집본에 없거나 오래되면 자료 부족으로 응답하는 것이 정상이다.

```python
import os
import httpx

headers = {"Authorization": "Bearer " + os.environ["MARITIME_DATA_API_TOKEN"]}
result = httpx.post(
    "http://127.0.0.1:8001/api/maritime-data/port-reference-screen",
    headers=headers,
    json={"vessel_id": "REAL:IMO:9240249", "port_id": "WPI:24020",
          "berth_id": "WPI:24020:BERTH:510"},
    timeout=10,
)
result.raise_for_status()
print(result.json())
```

서버에는 해당 REAL vessel이 적재돼 있어야 한다. 앱 backend에 함께 마운트한 경우는 내부 API 주소·포트를 사용하며 위 8001은 독립 Tool 서버 예시다. Port/berth 조회는 서버 전용 카탈로그 API를 이용한다. 응답의 각 check에서 `status`, `reasons`, 신고 값과 게시 제한값을 확인하고 `conditions_evaluated=false`와 `required_before_admission`을 함께 읽어야 한다. 부분 비교 통과를 추천 항구 목록으로 변환하지 않는다.

## 참고 원문

- [Fintraffic API 안내](https://www.digitraffic.fi/en/marine-traffic/) · [공식 OpenAPI](https://meri.digitraffic.fi/swagger/openapi.json) · [이용조건](https://www.digitraffic.fi/en/terms-of-service/)
- [USCG AIS 치수·정적/항해 정보](https://www.navcen.uscg.gov/ais-class-a-reports)
- [Gothenburg Port Authority 선석 제원](https://www.portofgothenburg.com/maritime/berth-specifications/?epslanguage=en)
- [Port of Helsinki 크루즈 선석 제원](https://www.portofhelsinki.fi/en/professionals/information-for-port-users/instructions-for-cruise-ships/cruise-berth-details/)

## 일반 앱 어댑터·운항 상세 화면

일반 로그인 세션으로 `GET /api/operations/port-references`, `POST /api/operations/port-reference-screen`을 호출한다. POST 입력은 `ship`(앱 선박 ID), `port_id`, 선택적 `berth_id`다. 임의 `vessel_id`·파일·URL·SQL·검증 시각은 받지 않는다. 서버 Bearer를 브라우저로 전달하지 않고 기존 도구 함수를 직접 호출한다.

서버는 앱 선박 존재·예시 여부, maritime_data.vessels의 명시 ship_id 매핑과 IMO를 확인한다. 비교 후에도 현재 앱 선박 버전·매핑·로그인 계정을 다시 확인한다. 선박 수정·연결 변경·로그아웃/계정 비활성화가 발생하면 결과를 반환하지 않는다. 미연결/다중 매핑은 추가 연결 필요 상태다. 이 검사는 기존 MRV와 공통 resolver로 유지한다.

기존 운항 정보의 대상 선박 선택을 재사용한다. 선박/사용자/항구/선석이 바뀌면 이전 결과를 지우고 늦은 응답을 표시하지 않는다. 항구가 한 곳이면 자동 선택하고, 여러 곳이면 사용자가 지정한다. 패널을 펼칠 때만 카탈로그를 조회한다. 조회 시각·출처·수신 시각·미확인 조건과 현재 자료 부족 사유를 표시하며, 노후화된 자료를 새로 수집한 것처럼 표현하지 않는다.

상단 운항 기간 필터는 이 참조 비교에 적용하지 않는다. 참조 자료 수집·수신 시각과 매 요청의 서버 평가 시각을 사용하며, 화면에도 이 차이를 안내한다.

같은 선박의 최근 흘수 입력 기록은 별도 앱 기록으로 표시하고, 날짜만 있는 기록의 실측 시각은 미확인으로 둔다. 예시 기록·과거 입력을 AIS 또는 현재 실측 흘수로 자동 대체하지 않는다. 부분 참조 비교를 실제 입항 허가로 바꾸지 않는다.

이 어댑터는 기존 로그인·역할 기반 공통 운항 조회 권한을 따른다. 선박별 소유자 ACL을 새로 도입한 것은 아니다. 별도 Query/LLM 실행 이력 대신 기존 요청 감사 로그에 API 접근이 기록된다. 카탈로그는 원시 AIS 목록 없이 수집 시각·레코드 나이별 건수·생성 시각의 유효 여부를 반환한다. 시각 기준 이내 건수는 신원·제한 조건까지 모두 검증된 선박 수를 뜻하지 않는다.

운항 상세 패널의 다중 항구 비교에서는 명시적으로 항구를 선택한다. 응답의 `port_source_id`·`port_reference_scope`와 해당 항구의 출처만 반환하며, 다른 항구의 오래된 수집본이 선택 항구의 비교를 막지 않는다. 카탈로그에는 항구별 `retrieved_at`·`capture_issue`가 있다. 파일을 다시 읽을 때 이전 결과·선석 선택을 지우며, 항구가 그대로 존재하면 선택만 유지한다. 아래 통합 질문의 항구 목록 질의는 항구를 미리 선택할 필요가 없다.

참조 파일은 준비 도중 부분 JSON이 읽히지 않도록 같은 디렉터리의 임시 파일에서 원자적으로 교체한다. HTML의 선석 제목 아래 하위 제목·조건도 보존하며, 제한 조건이 크기 예산을 넘으면 잘라내지 않고 준비를 중단한다.

새 공개 JSON의 권한은 `0644`, 기존 파일 교체 시 권한은 기존 값을 유지한다. 관리자가 파일·상위 디렉터리 접근을 별도로 제한했다면 컨테이너 사용자에게 읽기·디렉터리 통과 권한을 허용해야 한다. 읽기 전용 마운트 자체가 호스트 파일 권한을 넓혀 주지는 않는다.

## 오프라인 반입·교체·복구

아래 명령은 저장소 최상위에서 실행한다. 네트워크가 되는 준비 PC에서 위 `fetch`·`prepare`를 끝내고 묶음을 만든다. `bundle-new`는 아직 없는 디렉터리를 지정한다.

```bash
uv run --project backend python -m scripts.navigation_bundle export --catalog output/navigation-references/catalog.json --output output/navigation-references/bundle-new
uv run --project backend python -m scripts.navigation_bundle inspect --bundle output/navigation-references/bundle-new
```

`catalog.json`, `manifest.json`, `SOURCES.txt` 세 파일을 **같은 폴더로** 승인된 저장장치/전달 경로를 통해 선내로 옮긴다. 이 묶음에는 계정·비밀번호·원본 연간 MRV 행·DB dump가 없다. 원본 수집 파일과 fetch manifest는 준비 PC에서 별도 보관한다. SHA256은 파일 변경을 검출하며 발행자 신뢰·법정 검증을 보증하는 서명은 아니다.

선내 설치 PC에도 현재 backend uv 환경과 코드가 준비돼 있어야 한다. 검사와 설치 명령은 네트워크·DB에 접속하지 않는다. 첫 설치 예시:

```bash
uv run --project backend python -m scripts.navigation_bundle inspect --bundle /path/to/transferred-bundle
uv run --project backend python -m scripts.navigation_bundle install --bundle /path/to/transferred-bundle --target output/navigation-installed/catalog.json
```

그 뒤 `.env`의 `MARITIME_PORT_REFERENCES_DIR`에 `output/navigation-installed`의 **절대경로**를 넣고 위 선택 Compose로 실행한다. Windows 경로는 `C:/.../navigation-installed`처럼 슬래시를 쓴다. 기존 실제 MRV 적재·앱 선박 명시 매핑은 여전히 별도로 필요하다. 복사된 catalog만으로 MRV DB가 만들어지지 않는다.

갱신 때는 현재 설치 파일의 SHA256을 확인해 아래 자리표시자에 넣는다. 출력되는 새 `catalog_sha256`은 다음 교체·복구 때 사용할 수 있다.

```bash
uv run --project backend python -m scripts.navigation_bundle install --bundle /path/to/new-bundle --target output/navigation-installed/catalog.json --expected-current-sha256 CURRENT_64_HEX_SHA256
```

다른 현재 파일·심볼릭 링크·동시 설치 잠금·손상된 묶음은 교체하지 않는다. 기존 내용은 `catalog.json.previous.<기존해시>.json`으로 보존한다. 복구는 이 백업을 `export`로 새 묶음 디렉터리에 넣고, 현재 설치 파일의 해시를 명시해 같은 `install` 명령으로 수행한다. 기존 백업·내보낸 디렉터리를 덮어쓰지 않는다. 잠금이 남으면 실행 중 설치자가 없는지 확인한 뒤 해당 잠금만 운영자가 정리한다.

갱신은 출항 전 또는 승인된 통신 가능 시점에 수행하고, 검사 시 현재의 노후화 결과와 실제 항만 공고를 확인한다. 재포장·설치·복구는 원래 관측/수집/생성 시각을 유지한다. 오래된 AIS 수집본을 반입해도 런타임의 24시간 보류는 그대로이며, 유효한 최신 선내 자료를 자동 생성하지 않는다.

## LLM 담당자에게 전달할 호출 경계

비교 API와 아래의 제한된 `/api/ask` 규칙 분기를 제공한다. 향후 모델이 직접 도구를 선택할 때에도 앱의 선택 선박 ID와 검토된 `port_id`/`berth_id`를 사용하고, 선박 제원·항구 ID·현재 흘수를 만들어 넣지 않는다. 명시 대상이 확인되지 않으면 다른 대상으로 대체하지 않으며, 선박 미연결은 `needs_mapping` 안내를 유지한다. `unavailable`·출처 시각·용도 범위·조건 미평가를 답변에도 보존하고 `admission=not_assessed`를 입항 허가로 바꾸지 않는다.

### 기존 질문창 연결 계약

`POST /api/ask`의 자동 유형에서 “우리 배가 입항 가능한 항구가 어디야?”, “IMO 8719188 선박이 헬싱키에 입항 가능해?” 같은 한/영 항구 참조 질의를 분기한다. 입항 단어만으로 분기하지 않으며 가능 여부·대상 항구 질문을 함께 확인한다. 명시한 문서 전용/다른 유형과 정의·규정·보고사항·제출 서류·일반 절차 질문은 기존 경로를 따른다. 범용 LLM 의도 분류나 대화 전체의 지시 대체를 구현한 것은 아니다.

질문의 유일한 IMO/앱 선박명을 우선하고, 없으면 기존 context.ship, 그것도 없으면 유일한 실제 앱 선박을 사용한다. 모호함·가상 선박·미연결·지원하지 않는 명시 항구/선석을 다른 대상으로 대체하지 않는다. 항구를 명시하지 않은 목록 질문은 현재 제공하는 항구 전체를 비교한다. 위치·거리/항로 추천이나 질문에 적은 가정 치수는 수집값으로 바꾸어 답하지 않고 지원 범위/필요 입력을 안내한다.

응답은 기존 answer 필수 필드와 `navigation`을 포함한다. 항구별 부분 수치 비교·초과·미확인 건수, 실제 상세 결과·source/hash/시점·추가 확인 사항을 저장하고 기존 queries/query_owner/audit에 기록한다. 외부 항만 source를 문서 evidence/document_id로 위장하지 않는다. 이력은 소유자 범위를 유지한다. `generation=tool`로 숫자·상태를 코드에서 정리하며 입항 허가·공식 안전 판정을 생성하지 않는다. 모델 미설정도 이 경로의 실행을 막지 않으며, LLM이 직접 해당 도구를 선택한 것으로 기록하지 않는다.

`navigation.status`는 `reference_only`, `needs_ship`, `needs_real_ship`, `needs_mapping`, `unsupported_port`, `unsupported_berth`, `needs_port`, `unsupported_scope`, `needs_verified_inputs`, `unavailable`과 아래 확장의 `no_reference_matches`, `unsupported_condition`, `needs_reference_scope`, `needs_previous_query`다. 상위 `status`는 항구 상세 결과 객체가 있으면 `reference_found`(0개 필터 결과 포함), 없으면 `needs_input`이다. 항구별 `ports`는 `port_id`, `name`, `berth_count`, 세 부분 비교 상태의 건수를 포함하고 `results`는 상세 API의 비교 결과 목록이다. `ship_options`·`port_options`는 확인용 공개 앱 항목이며 새로운 접근 권한을 부여하지 않는다. 비교 후 계정·매핑 변경은 오류/rollback 처리하며 저장된 당시 결과가 현재 자료의 유효성을 보장하지 않는다.

### 질문 조건·후속 질문 확장 (2026-11-05 구현됨)

- 공개 선석의 길이/폭/흘수 **제한값**에 대한 m 단위 이상·이하·초과·미만·동일 조건과 오름/내림 정렬을 지원한다. 미확인·조건부 값은 수치 필터에서 제외하고 제외 건수를 표시하며 정렬에서는 마지막에 둔다. 선박의 가정 치수를 실제 신고값으로 대체하지 않는다. 지원하지 않는 단위·모호한 조건·복합 의도는 `unsupported_condition`으로 안내하고 전체 결과로 조용히 대체하지 않는다.
- `공개 제한 초과만`, `자료 부족만`, `일부 공개 수치 이내만`은 각각 기존 부분 비교 상태 필터다. `입항 불가능한 선석만` 등 실제 불가 판정 요청은 `needs_reference_scope`로 안내하고, 공개 수치 초과 조회를 제안한다. 기본 목록의 부분 비교를 실제 입항 가능 선석으로 승격하지 않는다.
- 응답 `navigation.query`는 해석한 상태 필터·수치 필터·정렬과 한국어/영어 표시용 설명을 보존한다. `compared_berth_count`, `matched_berth_count`, `excluded_unknown_count`와 항구별 `available_berth_count`로 전체 비교와 표시 개수를 구분한다. 0건은 `no_reference_matches`이며 항구 미지원이나 입항 불가로 해석하지 않는다. 기존 JSON·자료의 숫자와 출처는 변경하지 않는다.
- 짧은 항구/선석 후속 질문은 `context.previousQueryId`로 지정한 기존 항구 답변을 사용한다. 클라이언트는 현재 표시된 항구 답변 ID만 보내며 새 질문/다른 선박 선택 후에는 연결하지 않는다. 서버는 UUID 형식, `query_owner.owner`, 항구 답변 여부와 같은 선박·버전·매핑을 확인한다. 불일치·유효하지 않은 이력은 내용 노출 없이 `needs_previous_query`로 안내한다. 사용자의 최신 질문을 암묵적으로 고르거나 클라이언트가 보낸 과거 결과를 신뢰하지 않는다.
- 이전 답변은 대상과 지원 조건을 연결하는 용도다. 이전 숫자·상태는 재사용하지 않고 현재 DB·카탈로그로 다시 비교한다. 항구를 바꾸는 후속 질문에서는 이전 선석을 해제한다. 일반 문서 질문과 문서 전용 작업은 후속 문맥이 있어도 기존 경로를 유지한다.

`query.filters`는 `kind=length|beam|draught`, `op=>=|<=|>|<|=`, 십진 문자열 `value_m`의 최대 3개 AND 조건이다. `query.sort`는 null 또는 `{kind, direction: asc|desc}` 하나이며 항구별로 안정 정렬한다. `query.status`는 null 또는 기존 선석 부분 비교 상태 3개 중 하나다. `description={ko,en}`은 적용 내용을 화면에 표시한다. 상태 필터를 먼저 적용하고, 남은 선석 중 수치 필터에 필요한 값이 하나라도 없으면 `excluded_unknown_count`에 선석당 한 번 센다. 수치·출처는 원래 값으로 보존한다. 예시:

```json
{"query":{"filters":[{"kind":"draught","op":">=","value_m":"8"}],"sort":null,"status":null,"description":{"ko":"공개 흘수 제한 8 m 이상","en":"Published draught limit at least 8 m"}},"selection":{"port_ids":["WPI:28190"],"berth_id":null},"compared_berth_count":8,"matched_berth_count":4,"excluded_unknown_count":0}
```

`그럼 헬싱키는?`, `그럼 LHD 선석은?`처럼 제한된 후속 표현과 조건 변경을 지원한다. 이전 상태/정렬/수치 조건은 각각 생략하면 이어받고, 새로 명시한 수치 조건 묶음은 이전 묶음을 대체한다. 항구 변경은 선석을 해제한다. 전체 질문을 다시 작성하면 이전 조건을 이어받지 않는다. 접속어 없는 임의의 생략문·범용 대화 의도를 해석하는 계약은 아니다. 기존 답변 JSON에 새 필드가 없으면 이력 화면은 열리지만 후속 조회는 새 전체 질문으로 시작한다.

### 다국가 수신자료·입항 검토 조건 확장 (2026-11-05)

상태: 구현됨(로컬 준비·API·화면 검증).

- snapshot 1.2는 기존 1.0/1.1 읽기를 유지하면서 노르웨이 Kystdatahuset의 익명 공개 GeoJSON(`ais_no`)·공식 OpenAPI(`schema_no`), 덴마크 Aalborg 2026 oil-terminal 안내서(`aalborg_berths`, DKAAL)를 추가한다. source ID·출처 시각·해시·원문 위치를 분리하고 한 파일로 출처를 덮어쓰지 않는다. source는 최대 7개다. 새 묶음도 8MiB 한도를 유지하며 기존 앱 DB/계정 백업과 분리한다.
- 노르웨이 `date_time_utc`는 위치 보고 시각이며 정적 제원/흘수 갱신·측정 시각으로 바꾸지 않는다. 공개 GeoJSON 명세에 단위가 명시되지 않은 치수는 `raw_reported_fields`에 원문 값만 보존하고 m 단위 계산 필드는 null로 둔다. `position_reported_at`과 수집 시각을 따로 제공한다. 자료를 많이 확보했다고 검증된 현재 입력이 확보된 것으로 보지 않는다. 같은 IMO의 복수 출처/MMSI는 후보를 보존하고 비교를 보류한다.
- Aalborg는 공식 2026 PDF p.7의 6개 oil-terminal quay만 연결한다. 허용 LOA와 부두 수심을 구분한다. 4122/4124의 단순 LOA만 사용하고 manifold 조건부 LOA는 보류한다. 모든 최대 흘수는 최신 측심·도선 제한의 각주가 있으므로 단순 상한으로 승격하지 않는다. 선저 여유 최소 0.1m도 회사 정책·최신 수심 확인을 대체하지 않는다.
- `results[].readiness`는 실제 입항 검토에 필요한 현재 실측 제원/흘수·전체 접근 경로·수위/기상·도선/예선·터미널/화물·최신 공고/승인을 개별 미확인 항목으로 반환한다. 확인된 항만 승인 자료가 없으므로 항상 `status=requires_review`, `admission=not_assessed`다.
- `berths[].operational_checks`는 검토된 원문 패턴의 풍속/LOA별 예선·UKC·최신 측심 확인을 구조화한다. 원문과 source locator를 함께 제공하고 미해석 조건이 남아 있음을 명시한다. 기존 `conditions_evaluated=false`와 신고값 비교를 유지한다. 원문 변경/모호함/중복은 자동 충족 판정하지 않는다.
- 독립 Tool 및 로그인 상세 API는 선택적 `scenario={wind_m_s,available_tugs,ukc_m}`를 받는다. 각각 0–100m/s, 정수 0–20척, 0–20m이며 누락은 unknown이다. 모든 제공값은 사용자 **가정 입력**이며 실제 기상 관측·측정·예선 확보 증빙으로 인증하지 않는다. 규칙 결과는 `needs_information`, `action_required`, `within_scenario`, `not_triggered_in_scenario`이고 실제 입항 가능/불가를 반환하지 않는다. viewer도 가정 비교를 할 수 있으나 선박·원본 데이터를 변경하지 않는다. 질문 경로는 별도 가정값 없이 현재 자료의 부족 항목·조건을 제공한다.
- AIS/항만 자료 확장은 명시 오프라인 fetch/prepare로만 수행한다. 한 source 실패·인증 필요·TLS 실패는 manifest에 보존한다. TLS 검증 해제, 인증 우회, 외부 서비스 메시지 전송, 대용량 전체 일자 AIS의 무제한 다운로드는 하지 않는다.

확장 준비는 저장소 최상위에서 수행한다. 기존 1.0/1.1 base의 MRV/WPI 해시가 현재 입력과 같아야 한다. PDF 추출용 `pypdf`는 오프라인 준비 명령에만 임시로 설치하며 서버 이미지·잠금 의존성은 바꾸지 않는다.

```bash
uv run --project backend python -m scripts.prepare_navigation_sources fetch --raw-dir output/navigation-extra/raw-new
uv run --project backend --with pypdf==6.10.0 python -m scripts.prepare_navigation_sources extend --base output/navigation-references/catalog.json --raw-dir output/navigation-extra/raw-new --vessels /path/to/vessels.csv --wpi /path/to/UpdatedPub150.csv --output output/navigation-extra/catalog-v12.json
uv run --project backend python -m scripts.navigation_bundle export --catalog output/navigation-extra/catalog-v12.json --output output/navigation-extra/bundle-v12
```

`fetch`는 새 디렉터리만 만들고 source별 16MiB·180초/읽기 timeout을 제한한다. `extend`는 새 출력 경로만 사용한다. 노르웨이 명세의 익명 공개 위치 보고 계약·NLOD 1.0 라이선스를 확인하며 원문 단위 추정을 하지 않는다. Aalborg PDF 7쪽의 헤더·선석 6개·숫자 열·각주가 검토된 2026 형식과 다르면 새 수치를 추정하지 않고 중단한다. PDF 표는 2026-11-05에 페이지 이미지와 추출 텍스트를 대조했다.

신규 코드를 먼저 배포한 다음 기존 `navigation_bundle inspect/install` 절차로 1.2를 설치한다. 이전 1.0/1.1 서버가 1.2를 읽는 호환성은 보장하지 않는다. 묶음 검사/설치에는 PDF 추출 도구·네트워크·DB가 필요하지 않으며 원래 수집 시각과 출처 해시를 유지한다. 조건이 바뀐 데이터는 운영 파일을 덮어써 맞추지 말고 parser/계약부터 검토한다.

출처: [Kystverket 공개 AIS 안내](https://www.kystverket.no/en/sea-transport-and-ports/ais/access-to-ais-data/), [Kystdatahuset 공식 OpenAPI](https://kystdatahuset.no/ws/swagger/v1/swagger.json), [Aalborg 2026 Oil Terminals 안내서](https://portofaalborg.dk/wp-content/uploads/2026/01/port-information-and-safety-regulations_january-2026-1.pdf). 노르웨이 API에 표시된 NLOD 1.0을 보존하고 다른 NLOD 버전으로 임의 변경하지 않는다. Aalborg 원문에 명시되지 않은 오픈 라이선스는 주장하지 않는다.

## 검증 범위

### 공식 항만 지침·변경 검토 확장 (2026-11-06 확정)

- snapshot 1.4는 1.0–1.3 읽기를 유지하고 `port_guidance`를 추가한다. 기존 source 12개·AIS·등록 제원·지역 관측·선석 수치/비교 상태는 변경하지 않는다. 공개 지침은 별도 문서 출처와 해시를 가진 최대 6개이며 고정 공식 URL/항구를 검증한다. 전체 8MiB 한도를 유지한다.
- 검토 대상은 Gothenburg의 Sjöfartsverket 최대 흘수·예선·풍속/시정/주야 지침과 Port Control 안내, Helsinki의 항만 규정·크루즈 Navigation & Safety 안내다. Aalborg는 기존 2026 Oil Terminals 범위를 유지한다. 공식 페이지를 새로 수집한 날짜를 규정 개정일/적용일이나 완전한 최신 공고 확인으로 바꾸지 않는다.
- 문서별 raw SHA256·정규화 main 본문 SHA256·URL·표시 개정일·명시 적용일·수집일을 보존한다. 항구/선종/수로·입출항/선석 등 원문의 적용 범위와 조건을 함께 제공한다. 접근 수로 흘수를 선석 흘수로, 지역 풍속을 원문 지정 지점 풍속으로, 입항 신고를 승인으로 대체하지 않는다.
- 상세/질문 결과 `official_guidance`는 해당 항구 문서와 조건·숫자·단위·근거 위치를 반환한다. 지정 선석이 있는 조건은 해당 선석에서만 표시하고 선종/경로 미확인 조건의 적용 여부는 `requires_review`다. 기존 자동 비교 수치·가정 조건·실제 입항 확인 상태를 바꾸지 않는다. 기존 문서 전용 RAG·권한·소유자 이력·LLM 라우팅 경계는 유지한다.
- 준비 CLI의 fetch는 고정 URL에만 크기/시간/TLS 제한을 적용하고 실패도 manifest에 보존한다. review는 원문/본문·메타데이터·기존 카탈로그 대비 신규/동일/변경을 구분한 보고서를 생성한다. prepare는 검토 보고서의 정확한 SHA256을 명시해야 하며 원문/manifest/기존 카탈로그/추출 결과가 바뀌면 중단한다. 변경된 내용을 운영 파일에 자동 덮어쓰지 않는다. 신규 출력·기존 묶음의 검사/보존 설치를 사용한다.
- 묶음은 지침의 출처/해시/수집 시각도 함께 안내한다. 운영 중 인터넷 호출·실시간 공고 구독·실측/승인자료 생성·새 migration은 포함하지 않는다. 새 지침이 최신 공고 전체를 포괄하거나 법적 적용이 검증됐다고 표시하지 않는다.

관리자는 저장소 최상위에서 보존된 1.3/1.4를 지정한다. 모든 출력은 새 경로를 사용한다. `review`는 이전/새 숫자와 본문 변경을 보여 주며 숫자·단위·적용 범위·개정일/적용일을 실제 원문과 대조한다. 동일 본문이라도 HTML 변경은 `raw_changed`로 표시한다. source 실패·추출 문구/조건 변경·동일 조건의 상충 값은 준비를 중단한다. 원문 조건이 바뀌면 parser/검토 계약도 재검토해야 하며 수치만 임의로 고치지 않는다.

```bash
uv run --project backend python -m scripts.prepare_port_guidance fetch --base /path/to/preserved-catalog.json --raw-dir output/port-guidance/raw-new
uv run --project backend python -m scripts.prepare_port_guidance review --base /path/to/preserved-catalog.json --raw-dir output/port-guidance/raw-new --output output/port-guidance/review-new.json
# review-new.json과 원문을 검토하고, 위 명령에서 출력된 정확한 review_sha256을 지정한다.
uv run --project backend python -m scripts.prepare_port_guidance prepare --base /path/to/preserved-catalog.json --raw-dir output/port-guidance/raw-new --review output/port-guidance/review-new.json --review-sha256 REVIEW_SHA256 --output output/port-guidance/catalog-new.json
uv run --project backend python -m scripts.navigation_bundle export --catalog output/port-guidance/catalog-new.json --output output/port-guidance/bundle-new
```

기존 `navigation_bundle inspect/install`로 확인·반입한다. 운영 파일이 있으면 `--expected-current-sha256`을 지정해 이전 파일을 보존한다. 서버에는 신규 1.4 읽기 코드를 먼저 배포한다. 옛 서버의 1.4 호환성은 보장하지 않는다. 지침의 raw/main 해시와 시각은 catalog·출처 안내에 보존되며 원문과 검토 보고서는 별도 아카이브로 전달해야 한다. 해시는 무결성 검사이고 배포자의 신뢰/법적 적용 확인을 대신하지 않는다.

### 등록 제원·지역 관측 참조 확장 (2026-11-05 확정)

- snapshot 1.3은 1.0–1.2 읽기를 유지하고 `static_references`, `static_reference_period`, `environment_observations`를 추가한다. source 최대 12개, 전체 8MiB는 유지한다. 과거 snapshot/원본 MRV/이전 미커밋 작업을 덮어쓰지 않는다.
- `norway_static`은 이미 노르웨이 GeoJSON과 MRV로 확인한 IMO/MMSI에 한해 월 단위 등록 이력을 조회한다. `schema_no_static`의 A/B/C/D metres·등록 유효기간·등록 흘수 의미를 확인한다. 등록 IMO가 현재 확인된 IMO와 다르거나 누락이면 식별 충돌로 보존하고 참고 비교를 보류한다. 현재 월 시작 이후 자료를 요구하거나 등록기간을 현재 실측/방송 시각으로 바꾸지 않는다.
- 길이/폭은 유효한 정수 offsets만 더해 `reference_length_m`, `reference_beam_m`에 보존한다. 등록 흘수 `registry_draught_m`는 원문 참조만 제공하고 현재 흘수 비교에는 쓰지 않는다. 요청 기간 끝 직전 기준으로 활성인 후보 전체를 검사하고, 식별자가 같고 해당 축 값이 전부 존재하며 일치할 때만 그 축의 참고 비교를 제공한다. 최신 레코드 임의 선택·불명확한 값 합치기는 하지 않는다. 원래 AIS 신고값 필드/기존 선석 상태는 변경하지 않는다.
- 상세/질문 결과의 `static_reference`와 선석별 `static_reference_checks`는 **과거 등록 제원 참고 비교**이며 현재 검증 제원·입항 승인으로 승격하지 않는다. 같은 source의 여러 등록 흘수 값이 있어도 현재 흘수는 생성하지 않는다.
- Gothenburg(WPI:24020)에만 검토한 SMHI Vinga A(71380)/Göteborg A(71420) 풍속, Göteborg-Tångudden(35120) 수위 관측을 연결한다. 고정 station metadata·공식 parameter·단위·관측 시각·원문 품질코드·좌표·출처 해시를 보존한다. 풍속은 시간당 제공되는 10분 평균(m/s), 수위는 parameter 13의 cm/RH2000이며 CSV의 기준면 문구를 대조한다.
- `environment`는 수집본의 지역 관측 문맥이다. 관측 품질 G/Y/O 등과 각 관측/수집 시각 기준 2시간의 앱 나이 상태를 분리한다. 최신 미검수/의심 관측을 이전 승인 값으로 바꿔 최신값처럼 표시하지 않는다. 임의 좌표·항구명 유사도 조인이나 다른 항구로 재사용하지 않는다.
- 지역 관측은 선석 현장 관측·예정 시각 예보·도선 제한 충족 증빙이 아니다. `scenario`로 자동 채우거나 UKC/입항 판정에 자동 투입하지 않는다. 현재 검증 흘수·실제 기상·서비스 배정·승인 확인 필요 상태를 유지한다. 자연어 LLM 라우팅을 추가하는 작업은 아니다.
- 네트워크는 명시 준비 CLI에서 고정 공공 URL에만 사용한다. source별 크기·시간 제한, TLS 정상 검증과 원문 SHA256을 유지한다. Windows에서 OpenSSL 체인이 확인되지 않으면 정상 시스템 신뢰 검증을 사용하는 제한된 대안을 허용하되 인증서 검사 생략/HTTP 강등은 하지 않는다. RTZ 항로는 공개 접근과 적용 범위부터 확인하며, 기존 항구와 검증된 연결이 없으면 별도 참조로 보관한다.

관리자는 저장소 최상위에서 보존된 1.2를 지정하고 새 경로로만 준비한다. source별 8MiB·읽기 20초·총 읽기 90초를 제한하며 Windows 인증서 체인 대안 프로세스는 100초 제한이다. 등록 API는 검토된 1–500 MMSI·10,000건 미만 응답·8,000자 URL 한도를 검사하고 포화 응답은 중단한다. station metadata/수위 CSV도 별도 원문·SHA256으로 보관한다. 결과는 기존 `navigation_bundle export/inspect/install`로 반입한다.

```bash
uv run --project backend python -m scripts.prepare_navigation_quality fetch --base /path/to/preserved-v12.json --raw-dir output/navigation-quality/raw-new
uv run --project backend python -m scripts.prepare_navigation_quality extend --base /path/to/preserved-v12.json --raw-dir output/navigation-quality/raw-new --output output/navigation-quality/catalog-v13.json
uv run --project backend python -m scripts.navigation_bundle export --catalog output/navigation-quality/catalog-v13.json --output output/navigation-quality/bundle-v13
uv run --project backend python -m scripts.prepare_navigation_quality route-audit --raw-dir output/navigation-quality/routes-new
```

`route-audit`는 공식 Routeinfo 전체 목록과 명시 LOCODE(SEGOT/FIHEL/DKAAL/NOBGO), 노르웨이 표본 RTZ 1개를 제한 수집하고 적용 기간·해시를 별도 보존한다. 현재 항구 카탈로그를 변경하지 않는다. 2026-11-05 응답은 689건 모두 적용 종료일이 지났고 현재 지원 세 항구의 목록은 각각 0건이므로 현재 항로/입항 근거로 연결하지 않았다. SMHI 품질/수위 기준면은 보존된 공식 관측 CSV의 설명을 대조했다. 확인하지 않은 오픈 라이선스는 주장하지 않는다.

특수값·단위·식별자 충돌·노후화·조건부/중복 선석·부두 길이 오해를 검사한다. 인증 실패·미설정 파일·잘못된 실제 선박·파라미터 바인딩·기존 API 계약을 검증한다. 실제 LLM과 실선 흘수 계측·항만 당국 승인 검증은 별도다.
