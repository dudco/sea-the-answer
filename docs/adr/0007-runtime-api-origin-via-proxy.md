# 0007. `/api/*` 전달 주소를 빌드가 아니라 실행 시점에 정한다 (`frontend/src/proxy.js`)

- 상태: 채택
- 날짜: 2026-10-08
- 관련: [ADR 0006](0006-nextjs-entry-rewrites-to-api.md)(전달 수단 부분을 대체), [`../architecture.md`](../architecture.md)

## 배경

ADR 0006은 `next.config.mjs`의 `rewrites`로 `/api/*`를 내부 API 서버에 넘겼습니다. 그런데 Next.js 16.3.8에서 확인해 보니 `rewrites`의 대상 주소는 `next build` 때 빌드 결과에 고정되어, `HAEDAP_API_ORIGIN`을 바꾸려면 다시 빌드해야 했습니다. Docker로 운영할 때도 같은 이미지를 환경(로컬·테스트 서버·운영)마다 다시 빌드해야 하는 문제가 됩니다.

## 결정

- `frontend/src/proxy.js`(Next.js 16에서 `middleware`가 이름을 바꾼 것, Node.js 런타임)에서 `matcher: '/api/:path*'` 요청을 `NextResponse.rewrite(new URL(경로, process.env.HAEDAP_API_ORIGIN))`로 넘긴다.
- `next.config.mjs`는 `next dev`/`next start`가 시작할 때마다 실행되므로, 여기서 최상위 `.env`의 `HAEDAP_API_ORIGIN` **하나만** 읽어 `process.env`에 채운다(그 밖의 비밀값은 Next.js에 넣지 않음).
- `next.config.mjs`의 `rewrites`는 제거한다. 프록시 한도(`proxyClientMaxBodySize` 101MB, `proxyTimeout` 60초)는 그대로 둔다.

## 확인한 동작 (2026-10-08, 임시 에코 서버)

주소 없이 빌드한 뒤 `next start` 때 준 주소로 전달됨, `X-Forwarded-Host`는 실제 Host, `Set-Cookie` 전달, 60MB 본문 전달, 45초 응답 정상 수신. `X-Forwarded-For`는 여전히 클라이언트 값이 그대로 전달되므로 신뢰하지 않는다(ADR 0006과 같음).

## 검토한 대안

| 대안 | 채택하지 않은 이유 |
|---|---|
| `rewrites` 유지 + 환경마다 빌드 | 이미지 재사용 불가, 주소를 바꿀 때마다 빌드 |
| Route Handler(`app/api/[...path]/route.js`)에서 `fetch`로 중계 | 본문 스트리밍·헤더·쿠키 전달을 직접 구현해야 하고 코드가 늘어남 |

## 결과

- 좋아지는 점: `.env`만 고치고 재시작하면 반영. Docker 이미지 하나를 여러 환경에 그대로 사용 가능.
- 감수하는 점: `/api/*` 요청마다 `proxy.js`가 한 번 실행됨(주소 계산뿐이라 비용은 작음).
- 지켜야 할 규칙: `proxy.js`에서 인증·권한 판단을 하지 않는다(검사는 API 서버가 담당). `matcher`를 `/api/` 밖으로 넓히지 않는다.
