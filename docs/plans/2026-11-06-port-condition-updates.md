# 공식 항만 조건 수집·변경 확인과 기존 비교 연결

- 상태: 완료 (로컬 자료 확보·구현·검증, 운영 배포/실제 적용 확인 제외)
- 작성: 역할4 · 2026-11-06
- 관련: [참조 계약](../specs/port-references.md), [등록 제원·관측 결과](2026-11-05-navigation-reference-quality.md)

## 목표·범위

현재 지원 항구의 공개 공식 운항 지침을 실제 확보해 비교 결과에 항구별 근거·확인할 조건을 연결한다. 원문/출처·페이지 표시 개정일·수집 시각을 구분하고, 재수집 시 내용 변경을 확인한 뒤 검토·반입할 수 있게 한다. 기존 시각/품질 검사와 일반 문서 RAG·LLM 라우팅·개인 DB·이전 미커밋 변경·원격 PR은 보존한다. 공개 지침만으로 실제 입항 승인이나 현재 실측값을 생성하지 않는다.

## 단계

- [x] 현재 지원 항구 공식 자료의 접근성·유효성·기존 수집본과 중복 확인.
- [x] 데이터/API 계약 확정, 고정 출처·검토 범위·변경 검사 명시.
- [x] 크기/시간/TLS 제한 수집·원문/해시·신규 출력·재수집 차이 보고 구현.
- [x] 확인된 조건과 근거를 기존 질문/운항 상세 결과에 연결.
- [x] 단위·API·Docker 화면·실제 MRV 연결 검증과 문서 갱신·임시 환경 정리.

## 완료 기준

실제 확보한 공식 조건을 항구에 맞게 표시하고, 다른 항구/선석·등록 제원/관측값·승인으로 확대하지 않는다. 변경된 원문을 검토 없이 기존 수치에 자동 적용하지 않고, 수집 실패·변경·페이지 시각/적용일 미확인을 드러낸다. MRV/기존 자료를 덮어쓰지 않고 운영 중 인터넷 호출 없이 새 묶음을 반입할 수 있어야 한다.

## 실제 확보·연결 결과

고정 공식 HTML **6개 문서·21개 조건**을 원문과 함께 확보했다. 기존 1.3의 AIS/등록/지역 관측/선석 데이터는 유지하고 1.4의 별도 `port_guidance`로 연결했다. 규정 전체나 모든 조건을 추출한 결과가 아니다.

| 항구·공식 출처 | 추출 범위 | 항목 |
|---|---|---:|
| Gothenburg · [Sjöfartsverket Maximum Draught](https://www.sjofartsverket.se/en/services/pilotage/pilot-area-gothenburg/standards--procedures/maximum-draught/) | 접근 수로 8곳의 MW 기준 최대 흘수·수로/선석 최소 UKC | 9 |
| Gothenburg · [Sjöfartsverket Tug Regulations](https://www.sjofartsverket.se/en/services/pilotage/pilot-area-gothenburg/standards--procedures/tug-regulations/) | 적재/특정 비가스프리 공선 유조선 호송 예선·사전 요청 | 2 |
| Gothenburg · [Sjöfartsverket Visibility Wind Darkness](https://www.sjofartsverket.se/en/services/pilotage/pilot-area-gothenburg/standards--procedures/visibility-wind-darkness/) | 230–290m 유조선·290m 이상 유조선·601번 자동차운반선의 일부 조건 | 3 |
| Gothenburg · [Port Control](https://www.portofgothenburg.com/maritime/port-control/) | 입항 사전 신고·실제 공사/운영 상태 확인 창구 안내 | 2 |
| Helsinki · [Harbour Regulations](https://www.portofhelsinki.fi/en/professionals/information-for-port-users/instructions/port-of-helsinki-harbour-regulations/) | 배정 위치/이동 허가·현재 수심·필요 예선/도선 지시 | 3 |
| Helsinki · [Cruise Navigation & Safety](https://www.portofhelsinki.fi/en/professionals/information-for-port-users/instructions-for-cruise-ships/navigation-safety/) | 크루즈 구역별 게시 흘수·도선 전장/입출항 통지 안내 | 2 |

- Sjöfartsverket 3개 페이지의 표시 개정일은 2021-01-30/31이다. 새 수집일을 최신 개정일로 바꾸지 않았다. Helsinki 일반 규정의 명시 적용일은 2023-02-07이고 다른 페이지에 표시되지 않은 날짜는 미확인이다. 모든 지침은 현재 적용 여부 확인 필요 상태다. Aalborg는 기존 2026 Oil Terminals를 유지하며 신규 문서 확보로 계산하지 않았다.
- 별도 재수집에서 6개 모두 정규화 본문은 같았고 3개는 raw HTML만 달라졌다. 세션/사이트 내부 HTML 변화와 본문 변경을 구분했다. 실제 기준값 변경은 관측되지 않았고 수치 변경/상충/적용 범위 변경 시나리오는 테스트로 검증했다.
- 준비 경로는 명시 fetch → 본문/원문·이전/새 숫자를 포함한 review → 정확한 review SHA256 지정 → 새 catalog/bundle → 검사/이전 파일 보존 설치다. 검토 보고서·원문·manifest·기존 catalog·추출 결과가 바뀌면 준비를 보류한다. TLS 검증·HTTPS/동일 origin redirect 제한을 유지한다. 운영 중 자동 인터넷 갱신이나 무검토 수치 덮어쓰기는 구현하지 않는다.
- 최종 `catalog-final-v14.json`/`installed/catalog.json`: **895,205 bytes**, SHA256 `059a09cddd15b51c5dc699d9f318db1b5ab1f2d61e52cecd89fefa9d9d11b128`. 검토 SHA256은 `17d18e6e977bb77da9058e03f9533cda398c42e295096121270bd594561020bc`다. 이전 1.3 및 준비 중간 파일을 보존했다. Git 제외 수집본/검토/묶음은 팀 배포 때 별도 전달해야 한다.

## 검증과 기록

- Docker 고정 의존성·임시 PostgreSQL에서 전체 backend **989 passed / 4 skipped**(적재 DB 선택 환경변수 미설정), 실제 데이터 적재 후 관련 **336 passed / 0 skipped**. frontend 단위 **26개**, production 빌드, 기본 Docker 화면 **23개**, 추가 실제 MRV 화면 **1개**가 통과했다. 범위는 겹치므로 합산하지 않는다.
- 실제 HTTP **46개**: 이전 질문/조건 26개·등록/관측 9개·공식 지침 11개. 새 “어떤 조건을 확인해야 해?” 질문/항구 후속 문맥·문서 전용 경계·601번 전용 조건 제외·공식 원문/숫자/날짜·미지원 항구를 단언했다. 입항 승인이나 LLM 호출 검증은 포함하지 않는다.
- 실제 IMO 8719188의 질문/운항 화면에서 Helsinki 규정 적용일·선석 배정/현 수심, Gothenburg 601번 입출항 16/18m/s와 510/519 수로 12.5m의 범위를 확인했다. 510번에서 601번 조건이 제거되고 다른 항구로 옮기면 이전 지침이 남지 않았다. 가정 풍속/UKC는 자동 입력되지 않았다. 모바일 가로 넘침/브라우저 오류가 없었다.
- 같은 서버 시각으로 1.3과 1.4를 비교해 세 항구의 기존 선석 checks·원문 조건·가정 규칙·등록값·지역 관측·미확인 상태가 동일함을 검증했다. backend 8개 runtime 파일의 SHA256과 로컬이 일치한다. MRV **80,552행** 전체 내용 MD5 `47f6876da973fe710a15e0d2491caa1e`를 유지했다. 개인 DB·기존 설치 파일·원격 PR은 변경하지 않았다.
- 초기 호스트 단위 검사 1건은 UTF-8 보고서를 기본 CP949로 읽는 테스트 코드 문제였다. 읽기 인코딩을 명시한 뒤 관련 57개와 최종 Docker 검사에서 통과했다. 런타임 검사나 적용 범위를 완화하지 않았다.
- 증거는 Git 제외 `output/port-conditions-20261106/`에 보존한다: `raw/`, `raw-recheck/`, `review-final.json`, `bundle-v14-reviewed/`, `prepared-summary.json`, `backend-tests.txt`, `loaded-related-tests.txt`, `docker-e2e.txt`, `actual-api.txt`, `guidance-api-responses.json`, `guidance-api-summary.json`, `actual-ui.txt`, `question-guidance.png`, `berth601-guidance-desktop.png`, `guidance-mobile.png`, `runtime-evidence.json`.
- 전용 Compose 프로젝트 `haedap-portguidance-20261106`의 컨테이너/네트워크를 `down`으로 정리했다. 다른 프로젝트·사용자 앱·볼륨은 삭제하지 않았다. 다음 단계는 팀 검토/PR·자료 묶음 전달/설치·팀 환경 재검증이며 이번에는 원격 제출하지 않았다.

## 남은 범위

실시간 항행 경보·공사 통제 공고·전체 접근 경로/최신 측심·입항 예정 시점 예보·실제 도선/예선 배정·실측 흘수·개별 항만 승인은 확보하지 않았다. 이번 결과는 공식 페이지에서 제공한 지침의 추가 참조와 변경 검토 절차다. 이를 최신 공고 전체 확인·현재 적용성 판정·자동 입항 승인으로 설명하지 않는다. 공식 문서 변경/접근 실패 시 재검토하고 인터넷 연결이 있는 관리자 환경에서 새 묶음으로 반입해야 한다.
