# 0005. 개발 모드는 백엔드와 프론트를 각각 직접 실행한다

- 상태: 채택
- 날짜: 2026-10-08
- 관련: [ADR 0002](0002-single-gateway-next-and-node-api.md)(개발 모드의 실행 방식 부분을 대체), [`../architecture.md`](../architecture.md)

## 배경

1.3.1까지 `npm run dev`는 `scripts/run.mjs --dev`가 Next.js 개발 서버를 임시 포트로 띄우고, 준비를 기다린 뒤 백엔드를 띄우는 방식이었습니다. 한 명령으로 끝나지만 로그가 섞이고, 백엔드만 재시작하거나 한쪽만 디버깅하기 어려웠으며, 백엔드 코드를 고칠 때마다 전체를 다시 띄워야 했습니다.

## 결정

- 개발 모드에서는 래퍼 스크립트 없이 두 프로세스를 각각 실행한다.
  - `npm run dev:backend` = `node --watch backend/server.mjs --frontend http://127.0.0.1:3000`
  - `npm run dev:frontend` = `next dev frontend --webpack -H 127.0.0.1 -p 3000`
- 브라우저 접속은 개발 중에도 백엔드 게이트웨이(기본 5173)로 한다. ADR 0002의 단일 출처·보안 경계는 그대로 유지한다.
- 백엔드는 `--frontend <origin>` 옵션(없으면 `HAEDAP_FRONTEND_ORIGIN`)으로 Next.js 주소를 받는다.
- 개발/빌드 출력 폴더는 `next.config.mjs`가 Next의 단계(phase) 값으로 구분한다(환경변수 없이 Windows·macOS 공통).
- `npm start`(`scripts/run.mjs`)와 `start.cmd`는 빌드된 화면을 쓰는 일반 실행 전용으로 남긴다.
- 개발 환경은 Docker Compose를 기본으로 쓰지 않는다. Docker는 운영·테스트 배포용으로 따로 결정한다(후속 ADR).

## 검토한 대안

| 대안 | 채택하지 않은 이유 |
|---|---|
| 기존 `run.mjs --dev` 유지 | 로그 혼합, 한쪽만 재시작·디버깅 불가 |
| `concurrently` 등으로 한 명령에 두 프로세스 | 결국 래퍼이며 의존성이 하나 늘어남. 원하면 나중에 추가 가능 |
| 프론트(3000)로 접속하고 Next `rewrites`로 `/api` 전달 | 백엔드의 Host·출처·CSRF 검사가 프록시된 요청을 거부하거나 완화해야 해서 운영과 동작이 달라짐 |
| 개발도 Docker Compose | 설치물이 Node.js 하나뿐이라 이득이 적음. Windows·macOS의 바인드 마운트 파일 감시가 느리거나 누락되어 HMR·`--watch`가 불안정, Docker Desktop 설치 부담 |

## 결과

- 좋아지는 점: 백엔드 코드 수정 시 자동 재시작, 프로세스별 로그·디버깅, 실행 흐름이 단순.
- 감수하는 점: 터미널 두 개가 필요. 3000 포트를 바꾸면 양쪽 명령을 같이 바꿔야 함.
- 지켜야 할 규칙: 개발 중에도 3000 포트로 직접 접속하지 않음. Next.js는 `127.0.0.1`에서만 수신.
