# 선박 등록 제원·지역 환경 관측의 품질 검증과 연결

- 상태: 완료 (로컬 구현·자료 확보·검증, 실제 입항 승인/운영 배포 제외)
- 작성: 역할4 · 2026-11-05
- 관련: [다국가 자료 결과](2026-11-05-navigation-readiness-and-sources.md), [선석 참조 계약](../specs/port-references.md)

## 목표

1.2의 국가/식별자 범위 확장을 이어서 실제로 단위가 확인되는 등록 제원을 분리해 비교하고, 현재 지원 항구에 지역 풍속·수위 관측을 연결한다. 과거 등록값을 현재 실측으로, 지역 관측을 선석 현장·예보로, 참조 항로를 입항 허가로 바꾸지 않는다. 이전 미커밋 작업·개인 DB·원격 PR은 보존한다.

## 단계

- [x] 정적 기록 API·SMHI 풍속/수위의 실제 접근성과 단위·품질·시각 확인.
- [x] 1.3 데이터·API 계약 확정과 출처·관측 품질·과거 등록 기준 명시.
- [x] 원문·해시·요청 범위를 보존한 준비 코드와 재현 가능한 별도 snapshot 생성.
- [x] 등록 제원 참고 비교·지역 관측 표시를 기존 질문/상세 API·화면에 연결.
- [x] 노르웨이 참조 항로의 공개 접근·적용 범위를 확인하고, 검증된 공통 식별자가 없는 항구는 매핑 보류.
- [x] 단위·통합·실제 DB/API·Docker 화면 검증, 결과·한계·재현법 정리와 임시 환경 정리.

## 조사·범위

- 노르웨이 익명 `/api/ais/static-messages`는 레지스트리에서 AIS type 5/24를 근사 재구성한다. IMO는 AIS가 없으면 S&P로 보충될 수 있으므로 이 값을 새로운 선박 식별자 연결의 근거로 쓰지 않고, 이미 GeoJSON과 MRV로 확인된 IMO/MMSI와 일치하는 레코드만 사용한다. 요청 가능한 최신 기간은 현재 월 시작 전까지다. 2026-10월·499 MMSI 요청은 HTTP 200, 573개 레코드였다.
- dimensions A/B/C/D의 단위는 공식 OpenAPI에 metres로 명시돼 있다. `validFrom/validTo`는 등록 유효기간이며 실측/방송 시각이 아니다. 등록 흘수는 현재 항해 흘수와 달라 별도 보존한다.
- SMHI Vinga A/ Göteborg A의 풍속과 Göteborg-Tångudden의 수위 자료에 접근했다. 풍속은 시간당 제공되는 10분 평균, 수위는 cm 단위·품질코드가 있다. G/O 등 원문 품질을 유지하며, 최신 미검수 O를 더 오래된 G로 바꿔 최신값으로 표시하지 않는다.
- Python 환경의 SMHI 중간 인증서 확인 문제는 Windows의 정상 시스템 신뢰 검증으로 접근할 수 있었다. TLS 검증 해제는 하지 않았다. 준비 코드도 검증을 유지하고 고정 공공 URL만 요청한다.
- 운영 중 자동 인터넷 조회·실제 UKC/입항 승인·새 DB 테이블·LLM 라우팅·원격 push/PR 갱신은 이번 범위가 아니다.

## 확보·정규화 결과

- `output/navigation-quality-20261105/raw/manifest.json`에 보존된 1.2의 해시·2026-10-01~11-01 UTC 요청 기간·전체 499 MMSI 요청 URL·원문 SHA256·수집 시각을 보존했다. Windows 시스템 신뢰 검증 대안도 실제 성공했고 TLS 검증 생략은 하지 않았다.
- 등록 이력 573건을 보존했다. 499척 요청 중 길이 참고값 435척, 폭 참고값 433척을 제공할 수 있으며 식별 충돌 31척·치수 부족/충돌 26척·이력 미연결 5척은 해당 축 비교를 보류한다. 길이/폭 중 하나 이상 가능한 선박은 437척이다. 원래 노르웨이 단위 미확인 raw 치수와 등록 이력을 합쳐 현재 실측처럼 만들지 않았다.
- SMHI 풍속 2개·수위 1개 관측소를 Gothenburg에만 연결했다. 수위 최신 레코드의 음수 cm/RH2000·미검수 O를 유지했다. 관측/수집 노후화와 품질은 독립적이며 가정값에 자동 투입하지 않는다.
- `routes-audit/`의 공식 목록은 689건, Bergen 22건, 표본 RTZ는 18 waypoint였다. 응답 목록의 유효 종료일은 가장 늦은 것도 2026-08-05로 지났고 SEGOT/FIHEL/DKAAL 목록은 각각 0건이다. 카탈로그에 항로를 추가하지 않았다. 공개 접근 성공을 현재 항해 적합성 확보로 계산하지 않는다.
- 새 `catalog-v13.json`은 873,904 bytes이고 `bundle-v13/`, `installed/`는 별도 경로다. 이전 1.2·MRV/WPI 원문·기존 설치 파일을 덮어쓰지 않았다. 묶음 설치는 원문 수집 시각을 갱신하지 않는다. 해당 output은 Git 제외이며 실제 운용/배포 시 별도로 전달·반입해야 한다.

## 남은 실제 입력

공개 자료로 현재 입항 가능 여부를 확정할 수는 없다. 현재 선박 실측/신고 치수·흘수·수면 위 높이, 접근 항로 전체의 최신 측심/수심·동일 기준면의 조위·동적 UKC 정책, 입항 시각의 현장 기상/예보·수류, 화물/서비스 적합성·도선/예선 실제 배정·항만 공고/선석 승인이 추가로 필요하다. 지역 RH2000 수위를 기존 선석 수심에 바로 더하거나 등록 흘수를 현재 흘수로 쓰지 않는다. 실시간 자동 갱신은 출처별 약관·인증·장애·오프라인 유효성 정책을 정한 별도 작업이다.

## 최종 검증 (2026-11-05~06)

- 전체 backend: Docker의 고정 의존성·임시 PostgreSQL에서 **963 passed / 4 skipped**. 미설정된 적재 DB 검사는 실제 적재 후 두 DB 환경변수를 지정한 관련 검사 **310 passed / 0 skipped**로 확인했다. frontend 단위 **26개**, production 빌드, 기본 Docker 화면 **22개**, 추가 실제 MRV viewer 화면 **1개**가 통과했다. 검사 범위는 겹친다.
- 실제 HTTP 35개(기존 26·신규 9)는 단순 200 개수 대신 필터/후속/동일 의미·다른 항구/선박·등록 충돌·지역 관측·가정 입력의 의미를 단언했다. 등록값으로 기존 AIS null을 채우거나 실제 입항 상태를 바꾸지 않았고 지역 관측을 Helsinki/Aalborg에 사용하지 않았다.
- 노르웨이 IMO 9247053: 과거 길이 140m·폭 23m·등록 흘수 8.02m, GeoJSON raw 흘수 6.5를 구분했다. 실제 질문 답변과 운항 상세, 데스크톱/모바일 카드에서 확인했다. 모바일 가로 넘침/브라우저 오류는 없었다. 실제 등록 식별 충돌 선박도 별도 생성·매핑해 참고 비교 보류를 검증했다. 모두 격리된 시험용 앱/DB다.
- source·원문·준비/묶음: `raw/manifest.json`, `catalog-v13.summary.json`, `lineage-check.json`, `routes-audit/`. 실제 API: `responses.json`, `before-after.json`, `quality-api-responses.json`, `quality-api-summary.json`. 검사: `backend-tests.txt`, `docker-loaded-related-tests.txt`, `frontend-tests.txt`, `docker-e2e-resumed.txt`, `actual-ui.txt`. 화면: `question-context.png`, `registry-desktop.png`, `environment-desktop.png`, `environment-mobile.png`. 모두 `output/navigation-quality-20261105/` 아래 Git 제외 파일이다.
- `runtime-evidence.json`과 `final-runtime-check.txt`: backend 7개 소스 SHA256 일치, 1.3 SHA256 `3d54ec4169694b628812f2fb0b730b88db31ce0fc7f109ea7eb157f750eb50ef`, MRV 80,552행 MD5 `47f6876da973fe710a15e0d2491caa1e` 유지. 개인 DB·기존 1.2·미커밋 변경은 보존했다.
- 첫 빌드는 Docker 엔진 중단으로 재개했고, 호스트 Python의 sentence-transformers 누락으로 통합 fixture 3개가 실패한 중간 기록도 보존했다. Docker의 전체 의존성에서 최종 310/0을 확인했다. 코드/테스트를 느슨하게 바꿔 통과시키지 않았다.
- 전용 Compose 프로젝트 `haedap-portquality-20261105`의 컨테이너/네트워크를 `down`으로 정리했다. 기존 사용자 환경·다른 프로젝트·볼륨은 삭제하지 않았다. 원격 push/PR 갱신은 하지 않았다.
