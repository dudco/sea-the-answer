# 0020. Chroma 서버를 공식 이미지 기반 전용 이미지로 분리

- 상태: 대체됨(0021)
- 날짜: 2026-10-29
- 결정자: 문서/RAG 사용자의 서버 이미지 분리 요청
- 관련: [계획](../plans/2026-10-29-chroma-image.md), [검색 계약](../specs/rag-vector.md), [이전 ADR 0019](0019-local-vector-retrieval.md)

## 배경

기존 Chroma 서비스는 임베딩용 PyTorch까지 설치한 약 2.81GB backend 이미지를 재사용했다.
사용자는 서버 이미지를 지금 분리하도록 요청했다. 데이터 경로와 비 root 실행은 유지해야 한다.

## 결정

`backend/Dockerfile.chroma`는 공식 `chromadb/chroma:1.5.9`를 기반으로 저장 디렉터리 소유권과
UID/GID 10001, 실행 명령과 HTTP 헬스체크만 추가한다. Python/PyTorch/앱 코드는 추가하지 않는다.
서버와 Python 클라이언트는 검증한 1.5.9를 사용한다. 볼륨 `rag-vectors`와 `/data/chroma` 경로,
내부 hostname `chroma:8000`, 선택적 profile `vector`는 유지한다. 호스트 포트는 열지 않는다.
공식 이미지에 Python/curl이 없어 bash 내장 TCP로 `/api/v2/heartbeat`의 HTTP 200을 검사한다.

ADR 0019의 나머지 결정인 PostgreSQL 원본, 로컬 E5 CPU 임베딩·길이 처리, 별도 모델/벡터 볼륨,
허용 후보 사전 필터·완전한 색인 확인·BM25 fallback·RRF와 수동 재색인은 그대로 이어받는다.
이 결정으로 검색 기본값이나 LLM 설정을 바꾸지 않는다.

## 검토한 대안

| 대안 | 장점 | 단점 / 채택하지 않은 이유 |
|---|---|---|
| backend 이미지 재사용 | 관리할 Dockerfile이 적음 | Chroma 서버에 임베딩/앱 의존성까지 포함 |
| 공식 이미지 직접 실행 | 가장 단순 | 기본 root 사용자와 /data 경로가 기존 UID/경로와 다름 |
| 공식 이미지에 최소 설정 추가 | 저장 형식·권한 유지, 서버 역할 분리 | 얇은 Dockerfile 하나 추가 |

## 결과

서버 전용 이미지에서 임베딩/앱 의존성을 제거한다. CPU PyTorch와 E5 추론은 계속 backend에 있으므로
backend 이미지 크기는 줄지 않는다. 이전에는 레이어를 공유했으므로 전체 디스크 절감량으로 해석하지 않는다.
이전 서버와 같은 UID와 볼륨 루트 경로를 유지하고 실제 데이터에 적용하기 전에 격리 볼륨으로
저장→새 서버 조회→추가 쓰기→컨테이너 재생성 후 보존을 검증한다. 별도 서버 버전 업그레이드는 다시 검증한다.

근거: [공식 Docker 안내](https://docs.trychroma.com/guides/deploy/docker),
해당 이미지 `chroma run --help`와 이미지 설정·실행 검증.
