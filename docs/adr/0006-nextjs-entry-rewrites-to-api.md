# 0006. Next.js를 공개 진입점으로 두고 `/api/*`는 rewrites로 내부 API 서버에 전달한다

- 상태: 채택 — 전달 수단(`next.config.mjs` rewrites, 빌드 때 주소 고정)은 [0007](0007-runtime-api-origin-via-proxy.md)로 대체
- 날짜: 2026-10-08
- 관련: [ADR 0002](0002-single-gateway-next-and-node-api.md)(대체), [ADR 0005](0005-dev-mode-direct-processes.md)(일부 대체), [`../architecture.md`](../architecture.md), [`../specs/api.md`](../specs/api.md)

## 배경

백엔드를 Python으로 옮길 예정입니다. ADR 0002 구조에서는 Node 백엔드가 공개 게이트웨이로서 Next.js 화면 프록시와 개발 모드 WebSocket(HMR) 중계까지 맡았기 때문에, 언어를 바꾸면 이 프록시 기능도 다시 구현해야 했습니다. 운영은 Docker로 올릴 계획이라 "공개 컨테이너 하나 + 내부 API 컨테이너" 구성이 자연스럽습니다.

## 결정

- 사용자는 Next.js 주소(기본 5173)로만 접속한다. Next.js가 화면을 제공하고 `/api/:path*`를 `next.config.mjs`의 `rewrites`로 `HAEDAP_API_ORIGIN`(기본 `http://127.0.0.1:8000`)에 전달한다.
- API 서버는 `127.0.0.1`에만 바인딩하고 화면을 제공하지 않는다(그 외 경로 404).
- Host·Origin 검사는 API 서버가 **실제 호스트**로 한다: 루프백 상대가 보낸 `X-Forwarded-Host`(Next.js가 원래 Host로 덮어씀), 없으면 `Host`. 프록시 경유는 공개 포트(`--public-port`), 직접 호출은 API 포트만 허용.
- `X-Forwarded-For`는 신뢰하지 않는다. LAN 모드의 **접속자 서브넷 검사는 제거**하고 OS 방화벽에 맡긴다.
- Next.js 프록시 한도를 본문 101MB, 대기 60초로 올린다(`experimental.proxyClientMaxBodySize`, `experimental.proxyTimeout`).
- Python 이전은 이 계약(경로·응답·Host 규칙, `specs/api.md`)을 그대로 구현하는 방식으로 한다.

## 검토한 대안

| 대안 | 채택하지 않은 이유 |
|---|---|
| ADR 0002 유지(API 서버가 게이트웨이) | Python으로 옮길 때 Next.js 프록시·HMR WebSocket 중계를 다시 구현해야 함 |
| 앞단에 Caddy/nginx | 개발 환경에도 별도 프로그램 설치가 필요. 운영 Docker 단계에서 다시 검토 가능 |
| `proxy.ts`(구 middleware)에서 접속자 IP 검사 | Next.js 16의 요청 객체가 접속자 IP를 제공하지 않아 신뢰할 수 있는 값이 없음 |

## 결과

- 좋아지는 점: API 서버가 순수 API만 담당해 언어 교체가 쉬움. 개발 모드 HMR이 Next.js에서 직접 처리됨. 운영 Docker 구성이 단순해짐.
- 감수하는 점:
  - rewrite 대상 주소가 `next build` 때 빌드 결과에 고정됨 → 주소를 바꾸면 다시 빌드(Docker에서는 빌드 인자로 지정).
  - LAN 모드에서 같은 서브넷 제한이 없어짐 → 신뢰할 수 있는 사설망에서만 사용, 필요하면 방화벽.
  - 요청 본문이 Next.js 메모리에 최대 101MB까지 버퍼링됨.
- 지켜야 할 규칙: API 서버를 `0.0.0.0`에 바인딩하지 않음. Docker로 옮길 때 컨테이너 간 통신에서 "루프백 상대" 조건을 어떻게 바꿀지(내부망 주소 허용 목록 등)를 후속 ADR로 정함.
