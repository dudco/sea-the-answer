# 0015. 업무 스킬은 고정 서버 실행기로 처리하고 LLM은 선택적으로 사용

- 상태: 채택
- 날짜: 2026-10-15
- 관련: [계약](../specs/workflow-skills.md)

## 결정

여섯 기능을 일반 앱의 보안 경계 안에서 실행한다. 런타임 지침은 `backend/knowledge/skills/<id>/SKILL.md`에 두고 기존 Docker knowledge 복사에 포함한다. 이는 프로젝트 설계 문서가 아니라 앱이 읽는 지식 리소스다. 설계·명세·사용법은 docs에 유지한다.

스킬 카탈로그와 서버 handler는 allowlist다. 모델은 임의 Tool·SQL·scope를 실행하지 않는다. 문서 표현 개선 시에만 선택한 스킬 지침과 권한을 통과한 근거를 기존 OpenAI 호환 LLM에 전달한다. 모델 실패는 원문 발췌로 되돌린다.

기존 `/api/ask`와 Tool API 계약을 유지하고 `/api/skills/*`를 추가한다. 모델이 없는 환경에서도 재현 가능한 동작과 보안 검증을 우선한다. Claude Code의 자동 스킬 탐색과 앱의 실행 기능은 구분한다.
