# 0001. 프로젝트 문서를 최상위 `docs/`에 모으고 `AGENTS.md`를 공통 작업 지침으로 쓴다

- 상태: 채택
- 날짜: 2026-10-08
- 관련: [`../../AGENTS.md`](../../AGENTS.md), [`../README.md`](../README.md)

## 배경

1.3.1까지는 "설명서는 README 하나, docs 폴더를 만들지 않는다"는 규칙이었습니다. README가 설치·사용법·API·DB·검증 기록·변경 이력을 모두 담아 40KB를 넘었고, 팀 모듈 연결을 앞두고 설계 결정·명세·작업 계획을 사람과 코딩 에이전트가 함께 참조할 자리가 필요해졌습니다.

## 결정

- 모든 프로젝트 문서는 저장소 최상위 `docs/`에 둔다. 하위 폴더(`frontend/docs` 등)에 문서 폴더를 만들지 않는다.
- `docs/` 안에 `architecture.md`, `data-model.md`, `user-guide.md`, `changelog.md`와 `specs/`, `plans/`, `adr/` 폴더를 둔다.
- 최상위 `README.md`는 소개·구조·설치·실행과 문서 안내만 담는다.
- 작업 지침은 `AGENTS.md` 하나로 관리하고, `CLAUDE.md`는 두지 않는다. Claude Code는 `CLAUDE.md`가 없으면 `AGENTS.md`를 읽는다.
- 하위 폴더에도 `AGENTS.md`·`CLAUDE.md`를 두지 않는다. `next dev`가 자동 생성하는 `frontend/AGENTS.md`·`frontend/CLAUDE.md`는 저장소에서 제거하고 `.gitignore`로 제외하며, 그 안내 내용은 최상위 `AGENTS.md` 6절에 한국어로 옮긴다.

## 검토한 대안

| 대안 | 채택하지 않은 이유 |
|---|---|
| README 하나 유지 | 문서가 계속 커지고, 계약·결정·계획이 섞여 갱신 누락이 생김 |
| GitHub Wiki / Notion에만 작성 | 코드와 같은 PR에서 갱신·리뷰할 수 없고 에이전트가 저장소에서 읽을 수 없음. Notion은 팀 보고서용으로 유지 |
| `CLAUDE.md`와 `AGENTS.md` 둘 다 유지 | 내용이 갈라질 위험. Claude Code는 `CLAUDE.md`가 있으면 `AGENTS.md`를 읽지 않으므로 둘을 따로 쓰면 다른 도구와 지침이 달라짐 |

## 결과

- 좋아지는 점: 변경 종류별로 고칠 문서가 정해져 있고, 에이전트가 같은 지침을 따름.
- 감수하는 점: 문서 수가 늘어 링크·목록 관리가 필요함.
- 지켜야 할 규칙: 문서 추가·상태 변경 시 `docs/README.md` 목록 갱신. 개인용 `CLAUDE.md`·`CLAUDE.local.md`를 만들면 Claude Code가 `AGENTS.md`를 읽지 않게 되므로 첫 줄에 `@AGENTS.md`를 넣는다. 오래된 Claude Code에서 `AGENTS.md`가 읽히지 않으면 같은 방식으로 불러온다.
