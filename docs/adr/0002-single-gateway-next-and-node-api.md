# 0002. Node API 게이트웨이 하나 뒤에 Next.js를 루프백 프로세스로 둔다

- 상태: 채택 (1.3.0에서 도입, 2026-10-08 소급 기록)
- 날짜: 2026-10-05
- 관련: [`../architecture.md`](../architecture.md), [ADR 0004](0004-public-access-admin-only-writes.md)

## 배경

1.2.x의 화면을 Next.js App Router + React로 옮기면서, 이미 검증된 Node HTTP API(쿠키 세션, CSRF, Host·LAN 검사, 본문 크기 제한, 권한 검사)를 그대로 유지해야 했습니다.

## 결정

- 사용자가 접속하는 공개 포트는 `backend/server.mjs` 하나다. `/api/*`는 여기서 직접 처리하고, 나머지는 `127.0.0.1` 임시 포트의 Next.js 프로세스로 프록시한다.
- `scripts/run.mjs`가 두 프로세스를 함께 띄우고 함께 종료한다.
- API 로직은 Next.js Route Handler로 옮기지 않는다.

## 검토한 대안

| 대안 | 채택하지 않은 이유 |
|---|---|
| API를 Next.js Route Handler로 이전 | 보안 검사·DB 트랜잭션 코드를 다시 작성·검증해야 함 |
| 화면·API를 다른 포트로 분리(CORS) | 쿠키·CSRF·출처 검사가 복잡해지고 LAN 모드에서 공격면이 늘어남 |
| Next.js 커스텀 서버 | 버전 변경에 취약하고 Next 내부 동작에 결합됨 |

## 결과

- 좋아지는 점: 기존 API·보안 경계 유지, 화면은 Next.js 라우팅·빌드 사용.
- 감수하는 점: 프로세스 두 개, 시작 시 Next 준비 대기. `node backend/server.mjs`만 실행하면 화면이 없음.
- 지켜야 할 규칙: Next.js는 루프백에서만 수신. API를 다른 포트로 노출하지 않음. 접속 주소는 게이트웨이 주소.
