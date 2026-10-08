# 프로젝트 작업 지침

## README를 계속 업데이트하기

사용자는 누구나 README만 보고 실행·구현할 수 있도록 설명하고, 이후에도 이 파일을 계속 갱신해 달라고 요청했다. `README.md`를 프로젝트의 기본 안내서로 유지한다.

- 기능, 실행 방법, 의존성, 설정, 파일 구조, 문서 형식, DB, API 또는 테스트가 바뀌면 같은 작업에서 README의 관련 본문을 함께 수정한다.
- 처음 참여한 사람 기준으로 준비물 → 명령 실행 위치 → 복사 가능한 예제 → 기대 결과 → 문제 해결 순서로 설명한다. 전문 용어는 처음 등장할 때 풀어 쓴다.
- 실제 구현된 범위, 샘플 데이터, 선택적 설정, 미구현·미검증 범위를 구분한다. 모의 모델 응답 검증을 실제 외부 모델 호출 검증으로 기록하지 않는다.
- 마지막 업데이트 날짜와 변경 이력을 갱신한다. 변경 이력만 추가하고 본문을 오래된 상태로 두지 않는다.
- 테스트 결과는 실제 수행한 내용과 날짜로 기록한다. 문서만 바꾼 작업에서는 관련 없는 전체 테스트 대신 파일 경로·예제·설정을 현재 코드와 대조한다.
- 사용 설명서는 최상위의 기존 `README.md` 하나로 유지한다. 별도 README나 docs 폴더를 만들지 않고 설치, 실행, 문서 수집, 코드 구조, API, 검증 기록을 이 파일에 통합한다.
- 예제에 실제 API 키를 넣지 않는다. 기존 데이터나 설정을 덮어쓰는 절차는 영향을 명시하고 보존 방법을 함께 설명한다.

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
