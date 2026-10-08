# ADR 0008 — 해사 데이터 Tool의 독립 실행과 내부 API 연결 경계

- 상태: 제안
- 날짜: 2026-10-08
- 결정자: 팀 검토 예정 (역할4 제안)
- 관련: [ADR 0006](0006-nextjs-entry-rewrites-to-api.md), [ADR 0007](0007-runtime-api-origin-via-proxy.md), [ADR 0003](0003-sqlite-fts5-local-storage.md), [API 명세](../specs/maritime-data-api.md), [팀 연결 계획](../plans/2026-10-08-team-module-integration.md)

## 배경

기본 앱은 Next.js 공개 진입점과 내부 Node API/SQLite로 구성되며 역할4 조회·계산 Tool은 Python/PostgreSQL입니다. 현재 Tool은 루프백 8001에서 독립 실행됩니다. 이를 팀 앱에 연결할 방식과 책임 경계를 정해야 하며, 아직 연결 어댑터는 구현되지 않았습니다.

## 제안하는 결정

Python 소스·전처리·SQL·테스트는 `backend/maritime_data/`에 배치하고 별도 PostgreSQL을 유지합니다. 후속 팀 연결에서는 내부 API(현재 Node)가 서버 전용 Bearer 토큰으로 루프백 HTTP API를 호출하는 방식을 제안합니다. 브라우저는 기존 Next.js 공개 진입점만 사용하고, `/api/*`는 현재 `proxy.js`를 통해 내부 API로 전달합니다. 역할4 전용 API를 기존 앱 API 전체의 대체 서버로 지정하지 않습니다.

내부 API 어댑터가 앱 선박 키 매핑·접근 정책·CSRF·감사·오류 전달을 담당하고 Tool은 입력 검증·읽기 전용 조회·출처·단위·산술 재현성을 담당합니다. 원본 MRV·합성·참조 데이터를 분리하고 공식 CII 및 규정 적합성은 미검증 상태로 유지합니다.

## 대안

| 대안 | 검토 |
|---|---|
| Python CLI를 요청마다 호출 | 초기 연결은 단순하지만 프로세스·타임아웃·JSON 오류 처리와 재사용 비용 증가 |
| Python 로직을 Node로 재작성 | 언어 하나로 실행되지만 검증된 계약·Decimal·전처리를 다시 구현해야 함 |
| SQLite·PostgreSQL 통합 교체 | 앱 DB·백업·권한·기존 데이터 변경까지 범위가 넓어짐 |

## 결과와 남은 합의

현재 PR은 폴더·문서·독립 Tool만 정리합니다. ADR이 제안 상태인 동안 HTTP 방식이 팀의 확정 결정이 되거나 UI 연결이 완료된 것으로 해석하지 않습니다. 배포·서비스 시작 방식, 어댑터 시간 제한·오류 형식, 사용자별 권한·감사 및 선박 ID 매핑을 팀과 확정해야 합니다. 기존 채택 ADR의 본문은 변경하지 않습니다.

2026-10-08 제출 준비 시 팀 ADR 0005~0007과의 번호 중복을 해소하여, 기존 로컬 제안 0005를 0008로 이동했습니다.
