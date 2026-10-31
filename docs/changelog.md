# 변경 이력과 검증 기록

버전을 올리거나 검증을 수행하면 이 파일에 기록합니다. 검증은 **실제로 수행한 것만** 날짜·환경과 함께 적고, 수행하지 않은 범위는 따로 적습니다.

## 변경 이력

### 2026-10-29 — 웹 하이브리드 검색 통일

- 웹 검색·답변은 BM25·벡터 후보의 RRF Top-5를 사용한다. CLI의 세 방식 비교와 BM25 fallback은 유지하며,
  health는 `hybrid-rrf` 정책을 표시한다. fallback 후에도 현재 DB의 권한·내용을 재확인한다.
- `uv run --locked --project backend pytest backend/tests/test_rag_vector.py backend/tests/test_debug_bm25.py -q --tb=short`: **58 통과**.
- `uv run --locked --project backend python .verification/bm25-db-tests.py`: 임시 PostgreSQL 17에서
  backend 전체 `python -m pytest -q -rs --tb=short`, **591 통과·4 건너뜀(105.95초)**.
  건너뛴 기존 해사 실데이터 테스트 4건은 `MARITIME_DATA_TEST_DATABASE_URL` 미설정이다.
  실제 임시 Chroma·모의 임베딩으로 환경변수 없음/기존 값 잔존, API hybrid 호출·개정·권한·인용·fallback을 검증했다.
- `docker compose -p haedap-web-hybrid-check --profile e2e up --build --force-recreate --exit-code-from e2e e2e`:
  **8 통과(1.2분)**. 이 스택은 벡터 색인이 없어 BM25 fallback으로 화면을 검증한다. 같은 프로젝트 `down` 및 임시 DB 종료 완료.
  개발 Compose `config --quiet`와 `git diff --check` 통과. 실제 E5 검색 품질·실제 앱 데이터 평가는 수행하지 않았다.
  개인 `.env`·실제 앱·PDF·벡터 색인은 변경하지 않았다. [계획](plans/2026-10-29-web-hybrid-search.md).

### 2026-10-29 — 경우 토큰 유지·일회성 RAG 보고서 정리

- 요청에 따라 `경우`를 불용어에서 제거했다. Kiwi가 추출한 해당 토큰을 질문·청크 양쪽에 유지한다.
  조사/어미 제거·나머지 불용어·동의어·권한 필터·벡터/RRF 규칙은 유지한다.
  단어가 같은 청크가 추가로 검색될 수 있으며 정확도가 항상 향상된다는 뜻은 아니다.
- 일회성 PDF 검색 평가 보고서, 초기 검색 기준선 보고서, 캐시 개선 결과 보고서 총 3개를 삭제하고
  README·계획·사용법·변경 이력의 참조를 정리했다. 평가 질문·실행 도구·사용법과
  설계/명세/완료 계획 및 이 문서의 기존 검증 요약은 보존했다. 삭제 파일은 Git 이력에서 복구할 수 있다.
- 적용하려면 backend 코드를 반영하고 프로세스를 재생성해 기존 메모리 토큰 캐시를 비워야 한다.
  PostgreSQL 청크나 Chroma 임베딩은 바뀌지 않아 재청킹·재임베딩은 필요하지 않다.
- 관련 BM25/캐시/디버그 테스트: `uv run --locked --project backend pytest backend/tests/test_rag_retrieval.py backend/tests/test_debug_bm25.py backend/tests/test_retrieval_token_cache.py -q --tb=short` **81 통과**.
- 전체 backend: `uv run --locked --project backend python .verification/bm25-db-tests.py`에서
  임시 PostgreSQL 17로 `python -m pytest -q -rs --tb=short` 실행, **579 통과·4 건너뜀(180.31초)**.
  건너뛴 4건은 기존 해사 실데이터용 `MARITIME_DATA_TEST_DATABASE_URL` 미설정이다. 임시 DB 종료 완료.
- `docker compose -p haedap-stopword-check --profile e2e up --build --force-recreate --exit-code-from e2e e2e`:
  이미지 빌드 및 브라우저 E2E **8 통과(1.8분)**, 종료 코드 0. 같은 프로젝트 `down` 정리 완료.
  삭제한 파일의 남은 Markdown 링크와 `git diff --check`를 확인했다. 실제 앱·PDF·DB·색인은 변경하지 않았다.

### 2026-10-29 — 혼합 벡터 색인 수정·팀 main/CI 통합

- `upstream/main` e388a2a와 `cxo/feature/ci-verification` cfa7fb5의 변경을 통합했다.
  두 원격 부모를 가진 미완료 머지 상태로 유지하며 커밋·푸시는 하지 않았다.
  실제 3-way 병합 결과를 기준으로 README·문서·테스트 fixture 충돌을 양쪽 내용을 보존해 해결했다.
  CI의 `.github/workflows/verify.yaml`은 원격과 동일하다. 프런트·인증·LLM·BM25 캐시 코드는 main과 동일하게 유지했다.
- Chroma에서 읽은 ndarray와 E5가 만든 list가 같은 upsert 배치에 들어가면 첫 항목에 따라 실패하던
  문제를 모든 벡터의 float 리스트 변환으로 수정했다. 임베딩 값·모델 fingerprint·record ID는 유지하므로
  완료된 벡터는 재사용하고 실패 작업 retry로 나머지를 처리할 수 있다.
- main의 `mode: metadata` 저장에도 같은 트랜잭션의 enqueue를 연결했다. 원문/청크/PDF와 응답은 유지하며
  재활성화·색인 누락·변경 없는 저장도 작업을 요청한다. UI가 변경 없는 요청을 생략하면 enqueue도 없다.
  인증 및 색인 migration을 모두 적용하는 fixture, 로그인 필수 벡터 API 검증을 반영했다.
- 팀 ADR 0016/0017과의 번호 중복을 피하려고 이 브랜치의 RAG ADR 0016/0017/0018을
  0019/0020/0021로 재번호화했다. 결정 본문은 보존하고 번호·참조만 정리했다.
  기존 평가 JSON/보고서는 stash 백업과 blob 해시가 동일함을 확인했다.

검증 및 적용 범위:

- 수정 전 혼합 배치 회귀: **1 실패·1 통과**로 오류 재현. 수정 후 `uv run --locked --project backend pytest backend/tests/test_rag_vector.py -q --tb=short`: **25 통과**.
- frontend `npm.cmd test`: **20 통과**. Docker Next.js production 빌드 성공.
- `docker compose -p haedap-rag-merge-check --profile e2e up --build --force-recreate --exit-code-from e2e e2e`:
  **8 통과(1.0분)**, 종료 코드 0. 같은 프로젝트의 `down`으로 테스트 컨테이너·네트워크 정리 완료.
- 해당 새 backend 이미지에서 `docker run --rm --network none ... python /app/check_mixed.py`:
  실제 고정 E5 CPU·임시 Chroma로 재사용+신규 혼합 배치 저장, 재실행 중복 없음(3개 record),
  vector/hybrid가 fallback 없이 기대 문서·페이지 반환. 외부 다운로드·앱 DB 없이 검증했다.
- 첫 backend 전체 검증은 **575 통과·2 실패·4 건너뜀**이었다. 두 실패는 main의 로그인 필수 정책에
  맞지 않는 기존 벡터 API 테스트였으며 선원 로그인과 익명 401·scope 제외 검증으로 보정했다.
- 최종 `uv run --locked --project backend python .verification/bm25-db-tests.py`:
  Windows/Python 3.13/임시 PostgreSQL 17의 `python -m pytest -q -rs --tb=short` **578 통과·4 건너뜀(137.08초)**.
  네 건은 `MARITIME_DATA_TEST_DATABASE_URL`이 필요한 기존 해사 데이터셋 계산 2·조회 2이며
  RAG/인증/메타데이터 저장/작업 큐/캐시/벡터 API 테스트는 실행했다. 임시 DB는 종료했다.
  운영·개발·E2E `docker compose ... config -q` 모두 통과. GitHub Actions 서버에서의 실행은 미검증이다.
- 실제 앱 재빌드/재시작·작업 retry·기존 PDF 대량 색인·질의 이력 저장은 수행하지 않았다.
  실제 데이터의 전체 색인 완료 및 질문 10개 벡터 정확도 재평가는 배포·retry 이후 별도 확인이 필요하다.

### 2026-10-14 — CI 워크플로 분리 (cxo 브랜치에서 가져온 기록)

PR #11 검토에 따라 `.github/workflows/verify.yaml`을 CI PR #14로 분리했다.
해당 브랜치의 기존 기록: 2026-10-14 커밋 8112816의 fork Actions에서 backend 151 통과·4 건너뜀,
frontend 4개·Next.js 빌드, Compose 구성 3종과 Docker E2E 1개 통과.
이는 당시 원격 브랜치의 검증 기록이며 이번 통합 결과는 위 2026-10-29 항목을 따른다.

### 2026-10-29 — 등록 PDF 질문 10개 검색 평가 (코드 수정 없음)

- 실제 등록 PDF 3개와 로컬 원본 일치 확인 후 질문 세트·평가 보고서를 추가했다.
  guest 허용 7문서 5,485청크, 질문 10개 × BM25/vector/hybrid, 문서 필터 10개·영어 대조 6개를 읽기 전용 실행했다.
- 기대 조항 후보 Hit@1 5/10, Hit@5 8/10, MRR@5 0.62. 전체 BM25 평균 8.110초, DB snapshot 조회 0.202초.
  PDF 물리 페이지/조항 후보 검색 평가이며 법규 해석·LLM 답변 정답률·전문가 확정 정답 세트는 아니다.
- 실제 PDF 색인 작업은 모두 5회 실패했고 1,686/5,485청크만 현재 Chroma에 있었다.
  vector/hybrid 각각 10/10회 `index_incomplete_or_stale`로 BM25 fallback하여 독립 정확도는 평가할 수 없었다.
- 재사용 ndarray·신규 list 혼합 배치의 Chroma 입력 검증 ValueError를 세 실제 누락 배치에서 재현했다.
  메모리에서 list로 통일하면 로컬 검증이 통과했다. 제품 코드 수정·Chroma 저장·작업 retry는 하지 않았다.
- Q08(SOx scrubber 제출자료)은 한국어 79위/영어 대조 2위, Q10(BWMS 승인)은 53위/1위였다.
  목차 상위 노출, 반복 머리말/꼬리말 heading과 반복 토큰화 비용도 기록했다.
- 실행: `uv run --locked --project backend python .verification/run-registered-eval.py`.
  메타데이터 전용 로컬 결과는 `.verification/registered-rag-evaluation.json`이며 원문 본문은 저장하지 않았다.
  PDF 메타데이터 확인은 임시 pypdf/pypdfium2 환경을 사용했고 pyproject/uv.lock은 변경하지 않았다.
  실제 DB·원본 PDF·질의 이력·.env·서비스 상태·브랜치 변경 및 커밋/푸시 없음.
  문서/평가 자료만 추가했으므로 관련 없는 전체 단위 테스트/E2E는 다시 실행하지 않았다.
  상세 기준·한계·질문은 평가 보고서(보고서 정리로 삭제, 요약은 변경 이력에 보존) 참고.

### 2026-10-29 — 저장 후 자동 색인·이미지 내 E5 (1.4.0 유지)

- 신규 `rag_index_jobs` migration으로 문서 저장과 같은 트랜잭션에 작업을 기록한다.
  `documents.py`는 import와 enqueue 호출만 추가했다. 별도 `rag_worker`가 커밋된 작업만 처리하며
  generation/claim token과 PG 세션 advisory lock으로 중복 worker·중단 복구·오래된 완료를 처리한다.
  실패는 최대 5회 자동 재시도하며 상태·안전한 오류 코드·enqueue/retry CLI를 제공한다.
- 기존 `VectorIndex.index`를 수동 CLI/worker가 공유한다. 새 record의 실제 입력 해시로 개정/페이지/ID만 다른
  청크의 임베딩 값을 재사용하며 title/reference/heading/text 변경은 재계산한다. 이전 metadata 형식도 검색 호환된다.
  검색 권한·활성·상태·kind·선택 문서·최종 DB 확인과 BM25 fallback/RRF 계약은 유지했다.
- backend/worker 이미지의 모델 stage에서 pinned E5를 다운로드·검증하고 `/opt/models/e5-small`로 포함한다.
  CPU 의존성과 고정 revision/384차원/정규화/긴 입력 규칙을 유지했고 새 의존성은 추가하지 않았다.
  운영/개발 이미지가 모델 레이어를 공유하며 앱 코드 변경 후 재빌드에서 모델 단계 `CACHED`를 확인했다.
  기존 `rag-models` 볼륨은 마운트만 해제하고 삭제하지 않는다. Chroma 전용 이미지는 유지했다.
- Docker inspect 보고값: 이전 모델 없는 backend 2,802,092,996바이트(약 2.80GB),
  모델 포함 backend 약 3.58GB, 전용 Chroma 826,147,540바이트(약 826MB).
  이미지 내 모델 파일 합계 492,803,681바이트(약 493MB), 다운로드·검증 단계 95.2초(의존성 레이어 캐시 사용).
  이미지 보고 크기는 전체 PC 추가 디스크 점유와 다르며 backend/worker 레이어는 공유된다.

검증 (2026-10-29, 실제 앱 데이터 사용 없음):

- `uv run --locked --project backend python .verification/bm25-db-tests.py`: 임시 PostgreSQL 17 클러스터에서
  backend의 `python -m pytest -q -rs --tb=short` 실행. 최종 **456 passed, 4 skipped, 122.89초**.
  네 건은 기존 해사 데이터셋의 `MARITIME_DATA_TEST_DATABASE_URL` 미설정(계산 2·조회 2)이며,
  RAG PostgreSQL/작업 큐 테스트는 실행했다. 중간 신규 FK 정리 테스트의 삭제 순서를 기존 FK에 맞춰 고쳤다.
- DB 없는 `test_rag_vector.py`: **23 passed, 6.74초**. 실제 임시 Chroma+모의 encoder로
  입력 재사용·새 메타데이터·legacy 호환·순위·권한·fallback·CLI 회귀를 검증했다.
- 운영 이미지 `docker run --rm --network none ...`: 실제 baked E5로 384차원·정규화·CPU(`torch.version.cuda is None`) 확인.
  개발 이미지도 `./backend:/app:ro` 마운트와 network none에서 같은 모델 추론 통과.
- `docker compose -p haedap-auto-index-check --profile e2e run --rm --no-deps
  -e HAEDAP_CHROMA_HOST=chroma -v ./backend/tests:/app/verification:ro -v ./migrations:/migrations:ro
  e2e-backend python -m verification.verify_auto_index`: 격리 e2e-db의 임시 schema와 Chroma HTTP 서버,
  합성 문서 3개 청크에서 커밋 전 작업 비가시성→실제 worker→색인→벡터/하이브리드 정답 p.1 확인.
  실제 HTTP 연결 실패 후 PG 원문 유지·retry 복구, 동일 입력 재시작·중복 방지,
  두 별도 worker 프로세스의 개정 처리·삭제 후 후보 제외도 통과했다. 실제 모델 검증이며 모의 응답이 아니다.
- Docker E2E: `docker compose -p haedap-auto-index-check --profile e2e up --build --force-recreate --exit-code-from e2e e2e`,
  문서·운항·보고서·승인·백업 시나리오 통과. 종료 후 같은 격리 프로젝트 `down`으로 정리.
- 실제 앱 컨테이너는 기존 상태(backend/frontend 7일, db 11일 실행)를 유지했다.
  실제 PDF·앱 DB·질의 이력·.env 변경, 실제 데이터 전체 색인, 커밋·푸시·브랜치 머지 없음.

한계: 대량 실제 문서 처리량/최대 RAM/검색 정확도는 이번 소량 합성 검증으로 보장하지 않는다.
PG 세션이 살아 있는 정지 worker는 재시작이 필요하며 네트워크 단절 감지 지연이 있을 수 있다.
오래된 Chroma record/모델 collection은 자동 삭제하지 않는다. 기존 문서·모델 변경·JSON 복원 후에는 명시적 enqueue가 필요하다.
기존 형식 record는 입력 해시가 없어 개정 간 벡터 재사용 대상이 아니지만 현재 검색은 유지된다.

### 2026-10-29 — Chroma 서버 전용 이미지 분리 (1.4.0 유지)

- `compose.yaml`의 Chroma 서비스를 backend 이미지 재사용에서 `backend/Dockerfile.chroma`로 변경했다.
  공식 `chromadb/chroma:1.5.9` 위에 기존 UID/GID 10001, `/data/chroma`와 HTTP 헬스체크만 추가했다.
  공식 이미지에 Python/curl이 없으므로 bash 내장 TCP로 heartbeat의 HTTP 200을 검사한다.
  Python/임베딩/PyTorch·E5·BM25·RRF 코드는 기존 backend에 유지하며 검색 기본값도 bm25로 유지했다.
- 이미지 inspect 기준 기존 서버용 backend 이미지 2,808,942,616바이트(약 2.81GB), 새 서버 이미지
  826,147,542바이트(약 826MB). backend 이미지 축소나 전체 PC 디스크 절감량을 뜻하지 않는다.
  기존에는 이미지 레이어를 공유했고 이전 이미지·테스트 이미지는 삭제하지 않았다.
- 기존 `rag-vectors` 볼륨명·마운트 루트 경로·내부 hostname/port·외부 포트 미공개를 유지했다.
  현재 앱 컨테이너·PostgreSQL·사용자 PDF·`.env`는 변경하지 않았고 실제 서비스 전환/커밋/푸시는 하지 않았다.
  [ADR 0017](adr/0020-dedicated-chroma-image.md)이 0016의 서버 이미지 선택을 대체하고 나머지 검색 결정을 계승한다.

검증(2026-10-29, Windows Docker Desktop / Linux 컨테이너):

- `docker compose -p haedap-chroma-split-check --profile vector build chroma`: 성공.
  공식 멀티 아키텍처 이미지 manifest/`run --help` 확인 후 실제 amd64에서 실행 검증했다(arm64 실행 미검증).
- 격리 테스트 볼륨에 **이전 backend 기반 이미지**의 PersistentClient 1.5.9로 합성 벡터 2개 저장 →
  새 서버가 HTTP로 2개 조회·검색 → 추가 벡터 1개 쓰기 → 컨테이너 강제 재생성 후 3개 보존 확인.
  새로 생성한 빈 볼륨과 이전 형식 볼륨 모두 UID/GID 10001로 쓰기 가능, SQLite 파일 소유권 유지.
  허용 ID 제한 검색·RRF·미색인 BM25 fallback 통과. 실제 앱 DB는 사용하지 않았다.
- 같은 전용 서버에 준비된 로컬 E5 모델로 공개 합성 청크 3개를 실제 임베딩·색인했다.
  vector/hybrid 검색, 긴 문서 구간 임베딩·단위 벡터, 긴 질문 거부 확인. 모델 다운로드 없이 offline 실행.
  이는 실제 모델 검증이며 위의 3차원 합성 encoder 호환성 테스트와 구분한다.
- `uv run --locked --project backend pytest backend/tests/test_rag_vector.py backend/tests/test_rag_retrieval.py backend/tests/test_debug_bm25.py -q --tb=short`:
  **91 passed (18.50초)**. 이 작업에서 Python 검색 코드/API를 수정하지 않았다.
- `docker compose -p haedap-chroma-split-check --profile e2e up --build --force-recreate --exit-code-from e2e e2e`:
  **1 passed (48.9초)**, 화면 시나리오 38.0초. 이후 같은 격리 프로젝트의 `--profile vector --profile e2e down`으로 정리했다.
  호환성·모델 테스트는 별도 합성 데이터로 수행했으며 실제 앱 전체 문서의 검색 품질 재평가는 수행하지 않았다.

### 2026-10-27 — 선택적 로컬 벡터 검색과 RRF (1.4.0 유지)

- `feature/rag-vector`의 dfb262f 기준. 사용자의 후속 지시에 따라 BM25 토큰 캐시 커밋 9a14ff1은 병합하지 않았다.
  기존 BM25/청킹/저장/개정/프론트엔드는 유지하고 독립 임베딩·Chroma·RRF·모드 모듈을 추가했다.
  사용자 설치 chromadb 1.5.9/sentence-transformers 6.2.0을 보존하고 Docker용 CPU PyTorch 2.14.1을 지정했다.
  기본 모드는 bm25, 허용 후보의 전체 색인 검증 실패 시 경고와 함께 BM25 fallback한다.
- 실제 모델: 공식 multilingual-e5-small revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`, CPU, 384차원.
  로컬 파일 약 492.8MB, `query:`/`passage:` 입력과 정규화, 512토큰 초과 문서의 무손실 문자 분할→평균/재정규화.
  모델 다운로드 첫 시도는 네트워크 연결 재설정으로 실패했고, 단일 다운로드 worker 및 `HF_HUB_DISABLE_XET=1` 재시도로 성공했다.
  실제 추론은 HF/Transformers offline 설정에서도 성공했다. 외부 임베딩 API 호출은 없다.
- 새 CLI: 명시적 prepare, 기본 dry-run/제한/배치/재실행 index, 동일 corpus의 세 검색 방식 비교.
  PostgreSQL 읽기 전용, Chroma만 쓰기. 기존 앱의 문서·청크·질의 이력, PDF와 `.env`는 변경하지 않았다.

검증(2026-10-27, Windows Python 3.13 / Docker Linux CPU):

- `uv run --locked --project backend pytest backend/tests/test_rag_vector.py backend/tests/test_rag_retrieval.py backend/tests/test_debug_bm25.py -q --tb=short`: 최종 91 passed (5.56초).
- 전체 backend는 `.verification/bm25-db-tests.py`가 만든 임시 PostgreSQL cluster에서 `python -m pytest -q -rs --tb=short` 실행.
  이 helper는 `.env`를 읽지 않고 테스트 연결만 주입하며 종료 시 PostgreSQL을 중단한다.
  최종 **438 passed, 4 skipped (97.74초)**. 4개는 `MARITIME_DATA_TEST_DATABASE_URL`로 별도 실제 해사 데이터셋을 제공해야 하는
  기존 `test_tools_calculations.py` 2개/`test_tools_query.py` 2개다. 앱 DB 기반 RAG 테스트는 건너뛰지 않았다.
  추가 API 테스트 작성 중 삭제 함수에 dict를 전달한 fixture 오류 2건은 문서 ID 인자로 수정 후 전체 재검증했다.
  신규 API 테스트는 실제 PostgreSQL/Chroma와 **모의 임베딩**을 사용하며 `/search`, `/ask` 인용, 권한·종류·선택·개정·삭제를 검증한다.
- `docker compose -p haedap-rag-vector-check --profile e2e up --build --force-recreate --exit-code-from e2e e2e`:
  **1 passed**, 전체 시나리오 36.6초(Playwright 전체 47.3초). 실제 앱과 별도 DB/네트워크 사용.
- 같은 격리 프로젝트의 Chroma HTTP 서버에 **실제 로컬 모델**로 공개 합성 청크 3개를 색인했다.
  vector/hybrid 검색, 512토큰 초과 입력 처리·384차원 단위 벡터, 긴 query 거부를 확인했다.
  Chroma 재시작 후 새 클라이언트에서도 3개 모두 재사용(indexed=0)·검색 성공. app UID로 모델 읽기·Chroma volume 쓰기 확인.
  검증 종료 후 `docker compose -p haedap-rag-vector-check --profile vector --profile e2e down`으로 테스트 서비스만 정리했다.

실제 등록 DB 소량 검증:

- 공개 허용 후보 5,485개 중 **36개만**, Part 5D 물리 페이지 17–19·KR 2025 물리 페이지 20–22·IMO 요약 2종(총 문서 4개).
  DB READ ONLY 조회 후 호스트 메모리에서 처리하고 `.verification/`의 격리 Chroma에만 색인했다. 본문은 출력하지 않았다.
  총 36개 생성 후 같은 입력 재실행은 새 생성 0개/재사용 36개.
- 동일 질문과 후보로 비교한 결과(작은 부분 corpus이며 전체 검색 정확도 아님):

| 질문 | BM25 1위 | 벡터 1위 | RRF 결과 |
|---|---|---|---|
| 선급이 자동으로 정지되는 경우는? | KR p.21 | KR p.21 (다른 청크) | KR p.21 1위 |
| Part 5D heavy deck cargo 강화 적용 기준 | p.17 용어 정의 | p.18 §3 강화 조항 | p.17 적용 범위 1위, p.18 §3 2위 |
| 연료 황 함유량 기준 | IMO 황 함유량 요약 | 같은 요약 | 같은 요약 1위 (원래 page=null) |

- 두 실행에서 읽기 전용 DB+컨테이너 전달 약 2.05–2.10초, 모델 첫 import/로드 16.42–22.54초,
  36개 색인 2.87–6.11초. 로드 이후 벡터 질의 0.017–0.070초, hybrid 0.10–0.20초.
  첫 BM25/Kiwi 초기화 포함 3.16–4.38초, 이후 소량 corpus BM25 약 0.10–0.14초.
  별도 테스트 병행 중의 소규모 측정이며 API 전체 응답 시간/전체 5,485개 검색 시간/최대 RAM 측정은 아니다.
- 남은 한계: 전체 corpus 색인·성능·정답률 평가 미수행, 실제 웹앱 모드 전환 미수행(임의 재시작 금지).
  하이브리드가 항상 벡터보다 정확한 것은 아니며, BM25 캐시 미포함으로 큰 corpus의 BM25 비용은 남는다.
  권한 후보 전수 metadata 확인·최종 DB 재조회 비용, 긴 청크 평균의 의미 희석, 수동 재색인/오래된 벡터 정리도 남는다.
  라이브러리/모델이 바뀌면 새 fingerprint collection으로 전체 재색인이 필요하다.
- **PR #20 최신 main 충돌 해결 / 2026-10-29**: `origin/main`의 `7c0ba46`(PR #19)을 한국어 LLM 검증 브랜치에 병합했다. `docs/README.md`·`docs/plans/README.md`·변경 이력의 충돌 3곳에서 한국어 평가·Docker 기록과 검색 토큰 재사용·해사 검색 평가 기록을 모두 보존했다. LLM·보고서 코드는 기존 PR과, 검색 런타임·검색 평가 도구는 최신 main과 동일함을 확인했다.
  - Windows·Python 3.13.16·격리 PostgreSQL 18.6에서 병합 후 backend/scripts 전체 **533 통과·4 건너뜀(200.87초)**. 건너뛴 4건은 별도 해사 데이터셋이 필요한 기존 테스트이며 기존 Starlette/httpx 경고 1건이 남는다. 검증 실행기의 Windows 기동 대기·한글 경로 읽기 문제는 테스트 시작 전 중단으로 구분하고, 실행기 보정 후 새 DB에서 위 결과를 확인했다. 임시 DB와 이번에 시작한 PostgreSQL은 정리했다.
  - Next.js 16.3.8 Docker production 빌드와 Compose e2e **8건 통과(1.8분)**: 실제 브라우저→API→PostgreSQL 업무 흐름 1건과 모의 API UI 회귀 7건. Compose 실행·정리 모두 종료 코드 0이며 이번 재검증에서 실제 모델은 호출하지 않았다. 화면 소스가 기존 PR과 같아 frontend 단위 테스트 20건은 앞선 결과를 유지한다. `npm ci`는 기존 잠금 의존성에서 critical 1건 경고를 출력했으며 의존성 변경 없이 별도 점검 대상으로 기록한다.
  - 로컬 검증 결과는 `.verification/backend_20261028_d02c6eac/`와 `.verification/docker-e2e-20261029-74e239a7/`에 보존했다. 문서 링크와 충돌 표시·공백 검사를 수행했으며 모델·로그·개인 설정은 PR에 포함하지 않는다.

- **재부팅 후 로컬 Docker 엔진 검증 / 2026-10-29** (1.4.0 유지): 사용자 재부팅 완료 후 WSL 상태가 기본 버전 2로 정상 응답하고 재부팅 대기가 해소됨을 확인했다. Docker의 새 가상 디스크 포맷·VM 초기화에 약 2분이 걸려 첫 45초 확인은 시간 초과였으며, 이후 실제 Docker Server **29.9.2 / Linux amd64 / WSL2 kernel 6.18.54.1** 응답과 `docker compose ... config --quiet` 통과를 확인했다. 재부팅 전 `Virtual Machine Platform not enabled` 오류와 구분한다. 엔진의 실제 Server 응답을 확인했으며 CLI 버전만으로 성공 처리하지 않았다.
  - **보고서 초기화 경합 수정**: 첫 Docker e2e는 UI 6건 통과·실제 workspace 1건 실패였다. trace를 확인해 선원 재로그인 후 운항 조회 완료 전에 Noon을 눌러 `보고서 대상 선박을 선택해 주세요`로 종료되고 생성 POST가 없음을 확인했다. `report-view.jsx`의 Noon/MRV 버튼을 `state.ready`·`state.connecting`에 따라 비활성화하도록 수정했다. 로그인 후 운항 응답을 보류하고 실제 logout toast의 만료 render를 clock으로 재현해, 초기화 중 두 버튼 잠금·조회 완료 후 활성화·정확한 선박으로 초안 생성을 검사하는 회귀를 추가했다. 대기 시간은 늘리지 않았다.
  - **최종 frontend·Docker 검증**: Node 24.21.0의 `npm test` **20 통과**, 수정 후 Next.js 16.3.8 Docker production 빌드 성공. 새 임시 DB의 Compose e2e **8 통과(1.7분)**: 실제 브라우저→API→PostgreSQL 업무 흐름 1건과 모의 API UI/지연 응답 회귀 7건이다. 격리 프로젝트 `haedap-korean-e2e-20261029`의 실행·`down` 정리 모두 종료 코드 0이며, 앱 DB·개인 `.env`는 변경하지 않았다. e2e에서는 실제 모델을 비활성화했다. 최초 Node 실행의 샌드박스 `spawn EPERM`은 승인 환경의 성공 재실행과 구분한다.
  - **컨테이너→호스트 실제 모델 검증**: 같은 backend 이미지에서 `http://host.docker.internal:11434/v1`의 Ollama 0.40.6·기존 `qwen2.5:3b`·`json_schema`를 호출했다. 모델 목록 HTTP 200·설치 모델 확인·가상 한국어 단문 생성·원문 인용 검증을 **19.28초**에 통과했다. 별도 모델 최초 적재는 12.19초였으며 앱 응답 시간과 합치지 않는다. 호스트 바인딩은 `127.0.0.1:11434`였고, 컨테이너의 `llm.py` SHA-256이 현재 소스와 일치했다. 이 검사는 직접 transport·인용 검사이며 인증 API·DB·브라우저 전체 모델 흐름이나 일반 한국어 품질 합격으로 확대하지 않는다.
  - **기록·정리**: 첫 실패 로그는 `.verification/docker-e2e-20261029-b09cbcaa/`, 최종 성공·정리 로그는 `.verification/docker-e2e-20261029-9499f1c6/`, 실제 모델 결과는 `.verification/container-llm-20261029-f64912e2/`에 보존했다. 기본 `e2e/` 보고서는 재실행 결과로 갱신된다. 설치 완료된 임시 Docker 설치 파일과 이 작업의 앱 복사본만 정리했고 모델·원본·검증 기록은 보존했다. Docker Desktop과 호스트 Ollama 검증 서버는 실행 상태다.

- **한국어 근거 답변·평가 도구 / 2026-10-28** (1.4.0 유지): 요청 언어의 `text`와 원문 그대로의 `quote`를 분리하고, 다른 언어의 근거도 활용하며 답변을 짧게 작성하도록 프롬프트를 보완했다. JSON·근거 ID·8자 이상 원문 인용·단일 요청·25초 제한·오류 시 전체 발췌 전환은 유지한다. `scripts/evaluate_llm.py`와 기본 문서 기준 한국어 사례 16개를 추가했다. 기본 발췌는 네트워크 없이 실행하고 `--mode llm`만 실제 모델을 호출한다. 코드·평가 입력 해시와 시간·오류 유형·인용·한글 여부를 기록하며 의미적 정답성은 사람 검토로 남긴다. 출력 경로를 호출 전에 확보하고 기존 결과를 덮어쓰지 않는다.
  - Windows·Python 3.13.16·PostgreSQL 18.6의 새 검증 DB에서 `uv run --locked --offline --no-sync pytest` **504 통과·4 건너뜀(272.77초)**. 제외 4개는 별도 해사 데이터셋이 필요한 기존 테스트다. 검증 중 추가한 출력 사전 검사·입력 해시 테스트와 최종 프롬프트까지 포함한 집중 실행은 **138 통과(12.67초)**. 실제 검색/BM25→모의 모델 HTTP 권한 회귀, 익명·초기 비밀번호·회수 세션 요청 0회, 번역한 원문 인용의 전체 폐기를 확인했다. 이 집중 테스트는 실제 모델 품질 검증이 아니다. 기존 Starlette/httpx 경고 1건이 남아 있다.
  - 최초 샌드박스 실행은 Windows 임시 폴더 `PermissionError`로 일부 setup을 수행하지 못했고, 승인 환경에서 재실행한 위 성공 결과와 구분한다. 실제 앱 DB·`.env`는 변경하지 않고 별도 검증 클러스터의 data 경로를 확인한 뒤 임시 DB를 만들고 삭제했다.
  - PR #18이 2026-10-22 `91a1cc6`으로 병합된 사실을 확인해 후속 계획을 바로잡았다. CI #14는 README 충돌을 확인하고 현재 문서를 보존하는 workflow-only 패치의 `git apply --check`를 통과했다. 패치·검토 메모는 `.verification/ci-pr14-20261028/`에 보존했다. 실제 브랜치 갱신·push·관리자 병합·새 원격 CI 실행은 수행하지 않았다.
  - Docker e2e 명령은 실제 시도했으나 Docker 미설치로 `CommandNotFoundException`이었다. 따라서 Compose e2e·Docker → 호스트 Ollama 연결은 이번 변경에서 미검증이다. 실제 모델 비교·브라우저 결과는 아래 후속 기록에 구분한다.
  - **실제 모델 1차 측정**: Ollama 0.40.6·`qwen2.5:3b` Q4_K_M·CPU·`json_schema`·기존 25초 제한으로 고정 근거 16문항을 실행했다. 원래 프롬프트는 답변 1/근거 부족 2/요청 또는 검증 실패 13, 중간 수정 프롬프트는 0/3/13이었다. 두 실행 중 pytest 등 CPU 작업이 함께 진행돼 성능 전후 비교 기준으로 사용하지 않는다. 오류 대부분은 약 25초 종료와 Ollama 요청 취소를 관측했다. 오류를 발췌 성공이나 의미적 오답으로 바꾸어 집계하지 않았다. 원본 결과는 `.verification/korean-llm-{baseline,candidate}-20261028.json`에 보존했다.
  - **별도 진단**: 운영 제한을 변경하지 않고 한 사례만 진단용 90초 제한으로 호출했으며 실제로는 **20.70초**에 끝났다. 원문 인용 검증을 통과했지만 답변에서 ECA 안/밖 조건이 잘못 반복되는 의미 오류를 발견했다. 따라서 유효 인용·정상 완료만으로 한국어 품질 합격을 주장하지 않는다. 진단은 앱의 실제 25초 제한 성공 검사와 별도이며 `.verification/diagnose-model-20261028.json`에 보존했다. 최종 프롬프트에는 숫자·단위·조건을 원문대로 유지하라는 지시도 추가했다.
  - **부하 제거 후 동일 6문항 순차 비교**: 입력 해시 `cdad591c…f4cddb8`로 같은 질문·근거·순서를 확인했다. 원래 프롬프트는 답변 2/근거 부족 2/오류 2(시간 초과 1, 검증 실패 1), 답변·인용 분리 지시는 1/2/3(시간 초과 2, 검증 실패 1), 별도 한국어 우선 실험은 0/2/4(시간 초과 4)였다. 원래 프롬프트의 답변 2건 중 1건은 한국어 요청에 영어를 그대로 반환했다. 수정 지시의 황 한도 사례는 한국어·안/밖 조건·원문 인용을 확인했지만 전체 품질 개선은 입증하지 못했다. 기본 샘플링의 단일 실행 관찰이며 자동 정답률로 해석하지 않는다. 한국어 우선 실험은 서비스에 채택하지 않았다.
  - **temperature 0 실험**: 기존 3B 가중치를 재사용한 임시 프리셋으로 4문항을 별도 실행해 답변 1/근거 부족 1/응답 검증 실패 2였다. 운영 모델·공통 요청 옵션은 바꾸지 않았다. 실험 결과를 기본 설정으로 권장하지 않는다. 결과·코드 해시·오류 종류·입력 일치 확인은 `.verification/korean-llm-comparison-20261028.json`과 각 원본 JSON에 보존했다. 의미적 품질은 사람 검토 대기다.
  - **실제 모델 브라우저 2건 통과**: Chrome → Next production standalone → 인증 FastAPI → 새 PostgreSQL DB → 실제 Ollama `qwen2.5:3b/json_schema`. 가상 단문 `청해쿼츠는 출항 전 장비 점검 절차입니다`에 대한 한국어 생성·원문 인용·원문 모달·관리자/폐기 문서 제외·근거 없는 질문을 확인했다(성공 단계 41.51초, 모델 HTTP 호출 약 13.40초). 없는 모델로 백엔드를 재시작한 단계도 원문 발췌·실패 경고·유효 인용을 확인해 통과했다(14.74초). 실제 모델/DB/API를 모의 처리하지 않았다. 두 단계는 최소 연결 검사이며 16문항 전체 품질 합격을 뜻하지 않는다. 앱 서버·임시 DB는 정리했고 결과 JSON·스크린샷은 `.verification/live_20261028_86db9538/`에 있다. 성공 실행에는 trace를 보존하지 않았다. 화면 소스는 변경하지 않아 frontend 테스트·빌드는 재실행하지 않았고 기존 production 빌드를 사용했다.
  - **Docker·WSL 설치 완료, 재부팅 후 실행 검증 대기**: 사용자가 이 PC에 직접 설치·실행하도록 지시했다. Windows 10 Enterprise 22H2(19045.6456)·RAM 16GiB·하드웨어 가상화·SLAT를 확인했다. 관리자 권한으로 WSL 및 VirtualMachinePlatform을 Disabled→Enabled로 바꾸고 WSL 설치 종료 코드 0을 확인했다. WSL 3.0.3.0·kernel 6.18.54.1을 확인했으며 OS는 재부팅 후 적용을 명시했다. Docker 공식 설치 파일의 유효한 Docker Inc 서명과 SHA-256을 기록하고 **Docker Desktop 4.97.0 사용자 설치 종료 코드 0**·실행 파일을 확인했다. Docker CLI 29.9.2·Compose 5.6.1·Desktop CLI 4.97.0을 확인했다.
  - **설치와 엔진 실행 결과 구분**: 실제 `docker desktop start --timeout 45`는 시작 대기 후 실패했다. backend 로그는 `Virtual Machine Platform not enabled`로 `starting→stopping→stopped`를 기록하고, `wsl --status`는 `WSL_E_WSL_OPTIONAL_COMPONENT_REQUIRED`를 반환했다. `docker info`도 HTTP 500이었고 Server 정보가 없어 엔진 성공으로 집계하지 않는다(이 명령은 종료 코드가 0이라 출력까지 확인했다). 자동 재부팅하지 않았으며 사용자 승인/재부팅 후 Compose e2e·컨테이너→호스트 Ollama를 이어간다. 설치 서명·해시·종료 코드·선별 엔진 오류는 `.verification/docker-*-20261028.json`에 보존했다. 임시 앱/DB·검증 PostgreSQL·temperature 0 프리셋은 정리했다. [검증 재현 절차](plans/2026-10-28-korean-llm-validation.md#docker-검증-재현-순서)를 계획에 남겼다.

- **문서 토큰 재사용으로 반복 검색 지연 개선 / 2026-10-28**: 프로파일의 청크 분석 병목(4.525초 중 4.475초)을 확인하고 `rag_retrieval.py`에 내용 기반·최대 2,048항목·계산 크기 16MiB LRU를 추가했다. 캐시 값은 분석 토큰만이며 원문·질의·결과·권한·BM25 인덱스는 저장하지 않는다. 현재 DB 후보의 권한·활성 개정·선택 범위를 매번 확인하고 인덱스를 새로 만든다. 분석 코드·어휘 배포 시 재시작하며 토큰 메모리 보관의 한계는 ADR에 기록했다.
  - PR 제출 준비에서 평가셋의 원문 해시를 정규 JSON 내용 기반으로 보완했다. Git LF와 Windows CRLF·들여쓰기 차이는 허용하고 내용 변경은 거부한다. 파일 바이트 해시는 실행 provenance에 따로 보존한다. 관련 **122 통과(5.27초)**, 질문·근거·검색 런타임 변경 없음.
  - PR 전 최신 main·열린 #14와 중복 점검: 새 검색 구현을 복제하지 않았고 기존 진단 CLI·응답 점검 스킬과 평가 목적이 다름을 확인했다. #14는 CI·공통 문서만 변경한다. 선택하지 않은 문서가 warm cache에서 결과·점수에 섞이지 않는 테스트를 보강하여 관련 **120 통과(7.63초)**. 런타임 코드는 이 재점검에서 변경하지 않았다. README 날짜 변경 제거, 공통 문서 병합 조정 가능성은 비교 결과에 기록했다.
  - 같은 문서 955청크·질문 20개·k=5·질문별 1회에서 결과 순서·float 점수·메타데이터가 모두 기준선과 일치했다. Hit@5/Recall@5 1.0·MRR@5 0.96875 유지. warm p50 **7.009초 → 0.057초**, p95 **7.664초 → 0.078초**. 첫 검색은 **9.300초**이며 전체 API·LLM 지연이나 선내 장비 성능 보증은 아니다.
  - Windows·Python 3.13.7·잠금 의존성·격리 PostgreSQL 18에서 backend/scripts 전체 **496 통과·4 건너뜀(247.87초)**. 선택 해사 데이터셋 등 환경이 필요한 기존 4개 건너뜀과 Starlette/httpx 경고 1건은 유지한다. 관련 표적 테스트는 119 통과이며 전체 결과에 중복 합산하지 않는다.
  - 별도 Compose 운영 빌드·마이그레이션·Chromium **7 통과(2.2분)**, 종료 코드 0: 실제 DB 전체 업무 흐름 1개와 모의 API UI 6개를 구분한다. 실제 외부/로컬 LLM 호출은 하지 않았다. 임시 DB·검증 컨테이너 정리, 개인 DB·기존 체험 앱 변경 없음. 로컬 구현이며 PR·push 없음. 비교·재현 결과(보고서 정리로 삭제, 요약은 변경 이력에 보존), [ADR 0017 제안](adr/0017-bounded-chunk-token-reuse.md).

- **해사 질문 평가셋·검색 기준선 / 2026-10-28**: 기본 문서 스냅샷을 대상으로 `scripts/evaluate_retrieval.py`와 질문–원문 인용 라벨 20건을 추가했다. 운영 전처리·BM25 함수를 그대로 사용하고 JSON·CSV·Markdown으로 지표·검색 후보·시간·해시를 기록한다. 실제 앱·DB·API·검색 알고리즘은 변경하지 않았다.
  - Windows 11·Python 3.13.7·Intel Core i5-1335U, `uv sync --frozen` 환경에서 관련 pytest **110 통과**. International 조건을 명확히 한 후 평가 도구 테스트 **15 재통과**(중복 합산 안 함).
  - 문서 10개·955청크, 답 있는 질문 16개 Hit@5/Recall@5 **1.0**, MRR@5 **0.96875**, 근거 1위 **15/16**. 답 없는 질문 4개 모두 후보 노출: 최종 답변 오류·환각으로 판정하지 않고 수동 검토 대상으로 분리했다.
  - 최종 실행은 질문별 **1회** 측정: 첫 검색 **12.965초**, 이후 질문 분포 p50 **7.009초**, p95 **7.664초**. HTTP·DB·LLM 지연·실제 선내 장비 성능은 검증하지 않았다. 작성자 초기 평가셋이며 독립 전문가·미공개 질문 평가와 전체 backend/Docker 검증은 이번 범위가 아니다. [사용법](retrieval-evaluation.md), 결과·한계·재현 해시(보고서 정리로 삭제, 요약은 변경 이력에 보존).

- **PR #18 최신 main 충돌 해결 / 2026-10-22**: `origin/main`의 `826563e`(PR #17)를 개인 계정 인증 브랜치에 병합했다. API 명세·변경 이력·로그인 화면의 충돌 3곳을 해결하고 BM25/Kiwi·업무 스킬·문서 정보 수정/본문 개정·관리자 보고서 삭제와 개인 계정·비밀번호 변경·소유권 검사를 함께 유지했다. 자동 병합된 문서의 이전 단어 포함 검색 설명을 제거해 현재 BM25 계약과 맞췄다. 새 API/UI 테스트는 익명 401·선원/열람자 403·관리자 허용으로 구분했다.
  - Windows·Python 3.13.16·PostgreSQL 18.6의 새 임시 DB에서 backend **472 통과·4 건너뜀(222.35초)**. 별도 해사 데이터셋을 요구하는 4개와 기존 Starlette/httpx 경고 1건은 유지한다. 첫 실행은 신규 문서 테스트의 두 번째 개정에 생성용 빈 `expectedId`가 남아 **471 통과·1 실패·4 건너뜀**이었고, 실제 첫 개정 ID를 넣어 전체 재실행을 통과했다. 버전 잠금·오래된 정보 409 검사는 변경하지 않았다.
  - Node 24.21.0에서 frontend **20 통과**, Next.js 16.3.8 production 빌드 성공. 실제 Chrome → Next standalone → FastAPI → PostgreSQL 전체 업무 시나리오 **1 통과(약 1.6분)**: 개인 로그인·비밀번호 변경·권한, 검색·PDF·문서 정보 수정/개정, 보고서 승인·관리자 삭제·충돌·검토 대기 종료, 백업 복구 후 재로그인과 업무 스킬을 확인했다. 첫 브라우저 실행은 검색 응답 전 15초 요소 검사에서 실패해 실제 `/api/ask` 응답 완료·성공을 확인한 뒤 화면을 검사하도록 수정하고 새 DB에서 통과했다. 앱의 요청 중단 제한은 바꾸지 않았다.
  - 실제 빌드 화면의 **모의 API UI 6건 통과**도 별도로 확인했다. 개인 계정 표시·브랜드·탐색, 질문 초기화·늦은 응답 무시, 삭제 취소/충돌/성공과 모바일 화면 검증이며 실제 DB 검증으로 집계하지 않는다. 검증 스크립트의 Windows 한글 경로 읽기도 보정했다. 임시 DB·서버는 정리했고 실제 앱 DB·`.env`는 사용하거나 변경하지 않았다. Docker 미설치로 Compose 컨테이너 e2e와 실제 외부 모델 호출은 이번 검증에 포함하지 않았다.

- **최신 main 병합·검증 / 2026-10-22**: `origin/main`의 `ba93cf7`(PR #15, BM25·Kiwi·목차 청킹)을 개인 계정 인증 브랜치에 병합했다. 문서 4개의 충돌에서 인증·Ollama·CI 기록과 새 검색·전처리 설명을 함께 보존했다. 새 BM25 API 회귀 테스트는 기존 접근 정책에 맞춰 일반 선원 계정으로 로그인하며 관리자 문서·폐기 문서 제외 검증을 유지한다. Windows·Python 3.13.16·PostgreSQL 18.6의 새 임시 DB에서 backend 전체 **441 통과·4 건너뜀(217.54초)**. 건너뛴 4개는 별도 해사 데이터셋 설정이 필요한 기존 테스트이고 Starlette/httpx 사용 중단 경고 1건이 남아 있다. 테스트 DB와 이 작업에서 시작한 검증 서버를 정리했다. `git diff --check`와 변경 문서의 로컬 파일 링크를 확인했다. 화면 소스는 바뀌지 않아 frontend 테스트·빌드는 재실행하지 않았으며, 실제 외부 모델 호출도 수행하지 않았다. Docker 실행 파일이 없어 지정된 Compose e2e 명령은 실행하지 못했다. 새 검증 클러스터 초기화는 Windows 제한 토큰·한글 인코딩 오류로 실패해 기존 검증용 PostgreSQL에 별도 DB를 만들어 확인했으며, 실제 앱 DB·`.env`는 사용하거나 변경하지 않았다.

- **UI 표시·탐색 정리와 관리자 보고서 삭제 / 2026-10-18** (1.4.0 유지): 일반 사용자 표시에서 식별자 숨김, 화면의 HAEDAP 문구를 SEA THE ANSWER로 통일, 사이드바 로고를 통합 질문 이동 버튼으로 변경. 문서·운항 기록·보고서 삭제에 공통 붉은 테두리 스타일을 적용했다. 통합 질문 메뉴를 누르면 새 질문 화면으로 초기화하고 질문 이력은 유지하며 이전 요청의 늦은 응답을 무시한다.
  - 저장된 보고서 상세에 관리자 전용 삭제 버튼 추가. 확인·버전 충돌 안내·임시 초안 정리·목록 이동을 연결했다. 삭제 중 중복 삭제·저장을 차단한다.
  - 백엔드 실행 코드 변경은 `api/routes/reports.py`, `api/store/reports.py`, `api/store/changes.py` 3개 파일이다. 기존 POST 보안 검사 안에서 관리자 삭제를 수행하고, 대기 검토를 종료하며 감사 로그를 기록한다. 검토 승인·반려와 삭제의 동시 처리는 보고서 행 잠금으로 순서를 맞춘다. DB 스키마·청킹·RAG·LLM·Tool 코드는 변경하지 않았다.
  - 검증: 2026-10-18 Linux / Node 24.19.0 / Python 3.13.16. `frontend/npm test` **20 통과**, `npm run build` **성공**, `backend/uv run --locked pytest` **271 통과·67 건너뜀**(PostgreSQL 필요). 보고서 삭제 권한·버전·검토 경합·API 보안 회귀 테스트 13건을 포함한다.
  - 실제 Next.js 빌드에 Playwright로 접속한 **모의 API UI 시나리오 6건 통과**: 일반 사용자 표시·브랜드·권한, 질문 초기화·이력 재열람, 늦은 답변 무시, 삭제 버튼 색·크기, 보고서 삭제 취소·충돌·성공·임시 보관 정리·새로고침, 모바일 화면·키보드 로고 이동. 모의 API 테스트는 실제 DB/LLM 연동 검증이 아니다.
  - Docker 실행 파일이 없는 환경이어서 Docker/PostgreSQL 전체 e2e는 미수행. 기존 `e2e/tests/workspace.spec.js`에 실제 관리자 보고서 삭제·일반 사용자 거부·검토 대기 종료·충돌 검증 단계를 추가했으며 팀 Docker 환경에서 실행할 수 있다.

- **프론트엔드 본문 보존·긴 입력 분할 보완 / 2026-10-18** (1.4.0 유지): 앞선 재청킹 방지 수정에 이어 `frontend/src/lib/pdf.js`에서 첫 페이지 구분자 앞의 본문을 `page: null`로 보존한다. 19,000자 입력 분할은 문단·문장·줄·공백 경계를 우선하고, 경계가 없는 긴 문자열만 강제 분할하며 서로게이트 쌍·CRLF를 보존한다. 페이지 간 본문을 합치지 않으며 이전 재청킹 방지 기능을 유지한다. 입력 변환 규칙은 [API 명세](specs/api.md#화면의-페이지-본문-변환-2026-10-18-보완)에 기록했다.
  - 이번 추가 변경은 프론트엔드 실행 코드 1개와 회귀 테스트·문서뿐이다. 이전 전달본 대비 `backend/`와 `migrations/`의 모든 파일이 동일함을 바이트 비교로 확인했다. 최종 Python 청킹·검색·LLM·DB는 추가로 변경하지 않았다. 이미 저장된 본문 누락이나 청크는 자동 복구하지 않는다.
  - 검증: 2026-10-18 Linux / Node 24.19.0에서 `frontend/npm test` **20 통과**(새 회귀 테스트 10건 포함), `npm run build` **성공**. 실제 빌드 화면의 Playwright 검증 **8개 시나리오 통과**: 앞선 정보 수정·충돌·PDF 추출 흐름과 함께, 본문 개정 시 머리말 보존·페이지 번호·긴 단어 경계·전체 본문 전달을 확인했다.
  - 화면 검증의 API 응답은 모의 처리했다. Docker가 없는 실행 환경이므로 실제 PostgreSQL·Docker 통합 e2e는 수행하지 않았다.

- **정보 수정 시 불필요한 재청킹 방지 / 2026-10-18** (1.4.0 유지): 수정 화면을 기본 **정보만 수정**과 **본문·버전 개정**으로 구분했다. 변경이 없으면 요청을 생략하고, 정보 수정은 `document.save`의 `mode: "metadata"`로 문서 ID·현재 버전·허용된 정보만 보낸다. 기존 청크를 편집용 원문으로 재사용하지 않으며 본문 개정에는 PDF 재추출 또는 원문 전체 입력을 요구한다. PDF 추출 중 중복 선택을 막고 추출 실패 시 이전 본문이 남지 않도록 했다. 정보 수정 이력도 본문 없이 표시한다.
  - 백엔드 기능 변경은 `backend/api/store/documents.py` 한 파일: 메타데이터 전용 분기, 현재 개정 행 잠금·충돌 검사, 기존 문서·청크·페이지·PDF 유지, 전처리 결과 0개 거부. DB 스키마·마이그레이션·백업·청킹 알고리즘·검색·LLM·Tool 코드는 변경하지 않았다.
  - 검증: Linux / Python 3.13.16 / Node 24.19.0에서 `frontend/npm test` **10 통과**, `npm run build` **성공**; `backend/uv run --locked pytest` **258 통과·67 건너뜀**(실제 PostgreSQL 필요), 새 저장 경계 회귀 테스트 16건 포함.
  - 실제 빌드 화면을 Playwright로 확인: 변경 없는 저장 요청 0건, 정보 저장 payload, 충돌 시 입력 유지, 새 원문 필수 개정, 변경 이력 열람, 실제 PDF.js 추출, 추출 실패 후 정보 수정, 수정 방식 전환·모바일 가로 넘침 없음 등 8개 시나리오 통과. 이 화면 검증은 **API 응답을 모의 처리**했으며 실제 DB 연동 검증은 아니다.
  - `docker compose --profile e2e ...`는 실행 환경에 Docker가 없어 실행하지 못했다. 실제 DB용 테스트 2건과 기존 전체 e2e 흐름의 재청킹 회귀 검증을 추가했으며 팀 Docker 환경에서 실행해야 한다. 원문 영구 보관·OCR·청킹 품질 개선·기존 청크 복구·제목/버전 개정 시 청크 재사용은 이번 범위 밖이다.

- **목차 청킹·Kiwi BM25 / 2026-10-22** (1.4.0 유지): 목차 항목의 줄바꿈 제목·쪽번호를 묶고 목차 heading 승격을 억제한다. 연속된 짧은 상위·하위 제목은 설명과 함께 청킹한다. 한글 bigram을 Kiwi 형태소 분석으로 교체하고 `api/rag_vocabulary.py`에 해사 사용자 사전·한영 별칭·제한적 불용어를 분리했다. 질의와 corpus가 같은 토큰화를 사용하며 조사·어미를 제외하고 부정어·숫자·단위를 보존한다. 사용자 설치 Kiwi 의존성을 그대로 사용한다. 저장/hash/개정/권한/API/UI는 변경하지 않았고 기존 DB 재청킹·벡터·RRF는 수행하지 않았다. [계획](plans/2026-10-22-rag-chunking-kiwi.md).

- **최신 main 병합·검증 / 2026-10-21**: `origin/main`의 `0257175`를 개인 계정 인증 브랜치에 병합했다. 문서 4개의 충돌에서 인증·Ollama 기록과 업무 스킬 설명을 함께 보존하고, 업무 스킬의 로그인 요건을 API·구조 문서에 반영했다. 스킬 통합 테스트는 로그인한 별도 계정으로 실행하며 익명 접근 차단을 확인하고, 브라우저 테스트는 계정 전환 전 사용자의 미저장 초안 상태에 의존하지 않도록 했다. Windows·Python 3.13.16·PostgreSQL 18.6의 새 임시 DB에서 backend **363 통과·4 건너뜀(162.13초)**, Node 24.21.0에서 frontend **4 통과**와 Next.js 16.3.8 production 빌드 성공. 실제 Chrome → Next standalone → FastAPI → PostgreSQL 통합 시나리오 **1 통과(57.5초)**. 임시 DB·서버는 검증 후 정리했다. 실제 외부 모델은 호출하지 않았고 Docker 미설치로 Compose e2e는 실행하지 못했다. 기존 Starlette httpx 사용 중단 경고 1건이 남아 있다.

- **Ollama 실제 연동 / 2026-10-21**: Windows·CPU·16GB RAM, Ollama **0.40.6**, 공식 `qwen2.5:3b` Q4_K_M, `http://127.0.0.1:11434/v1`, `json_schema`. 실행 파일과 모델의 공식 SHA-256을 확인했다. 실제 모델을 미리 적재한 뒤 `grounded_statements` 호출은 **14.97초**, 선원 로그인한 FastAPI TestClient → 실제 PostgreSQL 검색 → 실제 Ollama HTTP 호출은 **9.91초**에 영문 `generation=llm`, 원문과 일치하는 인용, 실패 경고 없음을 확인했다. 가상 절차 문서 1건을 사용했고 외부 호출·DB를 모의 처리하지 않았다. 존재하지 않는 모델은 Ollama 오류 후 `MODEL_FAILED_EXTRACTIVE_FALLBACK`·유효 발췌로 전환됐다.
  - **품질 한계**: 영어 질문의 한국어 출력 요청(9.12초)과 한국어 원문·질문(4.50초)은 `insufficient_evidence`·빈 statements를 반환했다. 이를 한국어 답변 성공으로 집계하지 않는다. `qwen2.5:1.5b`에서는 정상 인용 사례 외에 불일치 JSON·변형 인용·빈 답변도 관찰했으며, temperature 0 프리셋으로도 해결되지 않았다. 한국어 품질 개선과 기존 검색 순위 문제는 후속 과제다. 이 검증은 모델 전체 품질 평가가 아니며, Docker → 호스트 Ollama 연결·Ollama를 켠 브라우저 흐름은 미검증이다. 별도의 전체 브라우저/Compose 검증에서는 모델을 껐다.
  - **로컬 산출물**: 재현 스크립트·실제 응답 JSON·공식 실행 파일·모델은 Git에서 제외된 `.verification/`에 보관했다. 기존 운영 `.env`·DB를 변경하지 않고 별도 검증 DB와 루프백 포트를 사용했다. 일반 설치·실행 절차는 [사용 안내](user-guide.md#로컬-ollama-실행)에 있다.
- **최종 코드 재검증 / 2026-10-21**: 프롬프트 보완까지 포함한 `8d67a50`에 #14 워크플로를 결합한 `7ba0680`의 [CI 39486841355](https://github.com/cxo-ca/sea-the-answer/actions/runs/39486841355)에서 backend **329 통과·4 건너뜀(24.20초)**, frontend 테스트·빌드, Compose e2e **1 통과(28.4초)** 및 종료 코드 0 확인. CI #14 자체 최신 커밋 `cfa7fb5`도 [39483905479](https://github.com/cxo-ca/sea-the-answer/actions/runs/39483905479)에서 세 작업 모두 성공했다.
- **로컬 모델 응답 지시 보완 / 2026-10-21**: 실제 Ollama에서 작은 모델이 근거 부족 예시를 반복하거나 인용문을 바꾸는 응답을 확인해, 근거가 충분한 JSON 예시와 원문 대소문자·문구를 그대로 복사하는 지시를 추가했다. 질문·문서 안의 지시를 따르지 않는 경계와 서버의 JSON·인용 거부 규칙은 유지한다. 공급자 HTTP·API 회귀 **104 통과(4.51초)**. 이 수정만으로 모든 모델의 출력 품질을 보장하지 않는다.
- **원격 CI 통합 검증 / 2026-10-21**: [GitHub Actions 39482809765](https://github.com/cxo-ca/sea-the-answer/actions/runs/39482809765)에서 인증 구현 `a1d2d93` + PR #14 워크플로(`cce3c71`) 검증 성공. Linux·PostgreSQL 18 backend **329 통과·4 건너뜀(24.65초)**, frontend 테스트·빌드 성공, 운영·개발·e2e Compose 설정 검사 및 격리된 DB를 사용하는 **Compose e2e 1 통과(27.2초)**, 종료 시 `down` 정리 성공. 실제 모델은 이 CI에서 호출하지 않았다. #14 README 날짜 충돌은 `cfa7fb5`로 제거했다. upstream 병합은 `cxo-ca`에 쓰기 권한이 없어 관리자 처리 대기다.
- **개인 계정 인증 / 2026-10-21** (1.4.0 유지, [ADR 0016](adr/0016-crew-admin-authentication.md)): 일반 선원·열람·관리자 개인 계정 로그인, 관리자 계정 발급·회수, 최초·초기화 비밀번호 변경, 익명 업무 API 차단, 계정 버전 기반 세션 회수, 30분 유휴·12시간 절대 만료와 로그인 시도 제한을 구현했다. 내장 관리자 비밀번호를 제거하고 빈 DB의 명시적 초기 관리자 설정으로 전환했다. 기존 계정·보고서를 보존하며 새 마이그레이션에서 기존 계정도 비밀번호 변경을 요구한다. 권한·접속 로그, 운영 절차·인증 명세를 갱신했다. 실제 규정의 적용 범위와 프로젝트 정책을 ADR에 구분했다.
- **인증·화면 검증 / 2026-10-21**: Windows, Python 3.13.16, PostgreSQL 18.6의 별도 DB에서 backend 전체 **329 통과·4 건너뜀**, 최종 인증 집중 **26 통과**. Node 24.21.0에서 frontend **4 통과**, Next.js 16.3.8 production 빌드 성공. 실제 Chrome → Next standalone → FastAPI → PostgreSQL 통합 시나리오 **1 통과(56.9초)**: 익명 차단, 초기 관리자·선원 비밀번호 변경, 계정 발급, 권한 제한, 문서·PDF·운항·보고서·승인, 백업 복구 후 재로그인, 모바일 탐색. 백업 생성 완료를 기다리도록 테스트를 보완했다. 이 PC에는 Docker가 없어 로컬 결과를 Compose 실행 결과로 표기하지 않는다. Starlette의 기존 httpx 사용 중단 경고 1건은 남아 있다.


- **RAG 브랜치 최신 팀 main 통합 / 2026-10-21**: 로컬 `main`을 `upstream/main`의 `0257175`로 fast-forward하고 `feature/rag-bm25`에 병합했다. 문서 검색·변경 이력 충돌을 해결해 팀의 선택 문서 ID 검증·SQL 범위 제한과 기존 BM25·디버그 CLI를 함께 보존했다. 선택하지 않은 문서는 BM25 통계에 포함하지 않는다. 기본 용어집 확충에 영향을 받던 합성 순위 테스트는 롤백 전용 테스트 스키마 안에서 corpus를 격리했다. 사용자 Kiwi 의존성 변경은 별도 미커밋 변경으로 보존하며 실제 앱 DB·`.env`·사용자 PDF는 수정하지 않는다.

- **BM25 개발자 진단 / 2026-10-15** (1.4.0 유지): `scripts/debug_bm25.py`에서 기존 PostgreSQL 청크를 읽어 질의 토큰·Top-K·전체 점수·일치 토큰·출처·미리보기를 출력한다. 문서 ID/제목·kind·활성 사용자 범위·JSON 옵션을 지원한다. 기존 토큰 함수와 후보 조회를 공유하고 DB는 READ ONLY로 연결한다. 랭킹·API 응답·저장·청킹·UI·스키마·의존성 변경 없음. 토큰별 기여도와 검색 품질 개선은 제외했다. [계획](plans/2026-10-15-bm25-debug.md), [실행](../README.md#bm25-개발자-디버그).

- **BM25 문서 검색 / 2026-10-14** (1.4.0 유지): `api/rag_retrieval.py`에 한영 단어·한글 2글자 토큰·기존 동의어와 rank-bm25 BM25Okapi 검색을 분리했다. 저장 계층의 권한·현재 개정·문서 상태·종류 필터 이후 제목·출처·heading·본문으로 상위 5개를 선택한다. 내부 점수는 외부 evidence에 추가하지 않고 기존 응답·페이지·원문 인용을 유지한다. health의 retrieval은 `bm25-ko-en`. 사용자 추가 의존성을 사용하며 저장·개정·전처리·스키마·UI는 변경하지 않았다. 임베딩·ChromaDB·벡터·하이브리드·RRF는 범위 밖이다. [작업 계획](plans/2026-10-14-bm25-retrieval.md).
- **선택 상자 값이 바뀌지 않던 문제 수정 / 2026-10-15**: 화면 공통 `onInput` 처리에서 바로 다시 그리면서, `change` 이벤트가 값을 저장하기 전에 React가 선택 상자를 이전 값으로 되돌렸다. 질문 화면의 답변 방식·언어·작업 유형·검색 범위와 운항·문서 화면의 `data-field` 선택·날짜 입력이 영향을 받았다. `data-field` 요소는 `input`에서 다시 그리지 않도록 `frontend/src/workspace/controller.jsx` 수정. 검증: 2026-10-15 브라우저에서 실제 사용자 순서(input → change)로 재현 확인, `npm test` 4 통과. 수정 후 화면 재확인은 frontend 재빌드 뒤 진행 예정.
- **기본 문서 확충 / 2026-10-15** (버전 유지): 원본 PDF와 함께 등록되는 기본 문서 5건(해양환경관리법 법률 제21416호, 선박안전법 제19134호, 해상교통안전법 제19573호, 선박직원법 제21053호 — 2026-10-15 국가법령정보센터에서 받은 본문 PDF; USCG Navigation Rules and Regulations Handbook 2024-08-12 수정판)과 법령 정의 조항·COLREG Rule 3 기반 `해사 기본 용어집`을 `seed.json`에 추가. 법령은 조문 단위, 핸드북은 페이지 단위 절이며 원문 페이지 번호를 보존한다. `seed.json` 항목의 `file` 필드가 `knowledge/` 아래 PDF를 가리키면 `bootstrap()`이 원본을 함께 저장한다(`knowledge/` 밖 경로는 거부). 재생성 스크립트 `scripts/build_seed_documents.py` 추가. 검증: 2026-10-15 `uv run pytest` 242 통과·65 건너뜀(PostgreSQL 필요), 신규 `test_seed_documents.py` 9건 포함. 실제 PostgreSQL 적재와 화면 확인은 미수행. 알려진 한계: 키워드 검색이 조사가 붙은 단어(예: "조종불능선이")를 찾지 못하고 흔한 단어와 핵심 단어를 같은 점수로 세어, 문서가 늘면서 일부 질문의 근거 순위가 나빠진다.
- **AI 답변 실패 배너 오표시 수정 / 2026-10-14**: 통합 질문 화면이 경고 코드가 하나라도 있으면 "AI 답변을 생성하지 못해…" 배너를 띄워, 모델 답변이 성공(`generation=llm`)해도 `OPERATIONS_CONTEXT_REQUIRED`만으로 실패처럼 보였다. `MODEL_FAILED_EXTRACTIVE_FALLBACK`·`MODEL_NOT_CONFIGURED`일 때만 표시하도록 `frontend/src/views/views.jsx`를 수정. 검증: 2026-10-14 `npm test` 4 통과. 같은 날 동국 AI Chat 게이트웨이(`gpt-6-luna`)로 backend 컨테이너에서 `grounded_statements` 실호출 성공(200, 유효 인용, 4.3초), 웹 화면에서 "연료 황 함유량 기준은?" 질문이 AI 초안으로 표시됨을 확인.
- **동국 AI Chat 게이트웨이 호스트 / 2026-10-14** (버전 유지, [ADR 0014 제안](adr/0014-mindlogic-gateway-host.md)): 확인된 API 기본 주소 `https://factchat-cloud.mindlogic.ai/v1/gateway`의 정확한 호스트에 `DONGUK_AI_CHAT_API_KEY`를 보내고, 이 호스트에서는 문서 표기대로 `/chat/completions/`로 호출한다. 다른 `*.mindlogic.ai`·유사 도메인에는 키를 보내지 않는다. 검증: 2026-10-14 로컬 작업 폴더의 `backend/`에서 (Linux, Python 3.13) `uv run pytest` 233 통과·65 건너뜀(PostgreSQL 필요 테스트). 실제 게이트웨이 호출·e2e는 미수행.

- **후속 작업 우선순위 기록 / 2026-10-15** (문서만 변경, 버전 유지): 사용자가 지정한 [후속 계획](plans/2026-10-13-openai-compatible-chat.md)에 일반 선원·관리자 인증 우선, 로컬 Ollama 실제 연동 검증·운영 문서 보완, CI PR #14의 추후 병합을 기록했다. 검색·문서 정보 질문·접근 정책 등 사용자 보고 문제를 보존했으며 이번 작업에서 재검증한 결과로 표현하지 않는다.

### 2026-10-15 - 선택적 LLM을 사용하는 앱 업무 스킬

- 실행·저장 상태 보완: 처리 중 양식을 잠그고 저장 중 새 실행을 차단한다. 보고서 저장 성공 문구와 과거 이력 미리보기의 상태 안내를 구분했다. 지연 요청을 포함한 Docker 전체 19단계 통과(49.3초), frontend 4 passed·production build 성공.

- 문서 선택 오류: 스킬 양식의 input/change가 공통 화면 처리기에 전파되지 않도록 분리하고, 문서 선택을 체크박스·선택 개수 표시로 변경했다. 실제 인앱 브라우저 클릭·입력 후 선택 유지·선택 문서 조회 확인. frontend 4 passed, production build, Docker 전체 19단계 재검증 통과(36.7초).

- 화면 배치 변경: 독립 스킬 메뉴를 제거하고 통합 질문·문서 상세·운항 정보·보고서 목록·답변 아래에 각각 연결했다. /skills는 /chat으로 이동한다. 화면별 재사용 실행 패널이 현재 자료를 초기 선택하고 펼칠 때만 카탈로그를 요청한다. frontend 4 passed·production build·기존 화면 기반 Docker 전체 19단계 통과(35.5초).

- PR #16 재점검: 스킬 보고서에 공통 template·ship·from·to 메타데이터를 유지하고, 저장 후 공통 보고서 목록을 갱신하며, 이력에서 업무 스킬 배지를 표시한다. backend 272 passed / 69 skipped, 실제 PostgreSQL 관련 36 passed, frontend 4 passed, 확장 Docker 전체 19단계 통과(28.8초).

- 최초 독립 화면에서 시작한 MRV 참고 분석·선택 문서 답변·운항 요약·보고서 초안·점검표·내 응답 평가를 선택 실행한다. 런타임 `knowledge/skills/*/SKILL.md` 6개와 고정 서버 실행기를 추가했다. 기본 동작은 LLM 불필요, 선택 문서 표현만 기존 OpenAI 호환/Qwen에 연결한다.
- `/api/skills/run`은 일반 앱 인증·CSRF·사용자 식별·트랜잭션·감사를 재사용한다. 문서 ID 범위를 SQL에서 제한하고 활성/열람권한·인용을 검증한다. MRV는 앱 선박의 명시 매핑·IMO를 확인해 기존 Python Tool을 실행한다. 토큰을 브라우저에 노출하지 않는다. 기존 공개 운항 접근 정책을 유지하며 사용자별 선박 ACL은 추가하지 않았다.
- 보고서는 payload만 생성하고 별도 저장 버튼에서 새 draft로 저장한다. 평가는 본인 저장 응답에 한하며 인용·범위·계산 일관성을 검사하고 의미적 정답성은 사람 검토로 남긴다. migration·원본·기존 Tool API 계약은 변경하지 않았다.
- 검증: 스킬 형식 6개, backend 253 passed / 68 skipped, 실 PostgreSQL 임시 스키마의 관련 회귀 35 passed, frontend 4 passed·production build, 격리 Docker e2e 19단계 통과. 앞선 실패는 새 선택란 접근성 라벨을 보완하고 테스트 스택을 비운 뒤 해결했다. 별도 Docker 체험 DB에서 여섯 스킬 HTTP와 실제 MRV/DWT 표본 8.013878 화면 표시·모바일 폭·브라우저 오류 없음을 확인했다.
- 실제 Qwen 2.5 3B 요청은 성공하고 검증된 JSON·근거 부족 응답을 반환했다. 표현 품질·전체 정답률을 통과한 것으로 해석하지 않는다. 모델 없이 여섯 기능을 사용할 수 있다. 자연어 자동 라우팅·지속 대화 기억·공식 CII·점검 승인 기능은 포함하지 않았다.
- 팀 최신 main 통합 후 검증: backend **272 passed / 68 skipped**, 실 PostgreSQL 관련 **35 passed**, frontend **4 passed**, production build와 Docker 전체 **19단계 통과**. 팀의 기본 문서·게이트웨이·선택 입력 수정도 보존했다.
- 최초 구현 후 팀 main 024f3b376713의 게이트웨이·기본 문서·입력 보존 수정을 유지해 다시 통합했다. 작업은 해당 main 기반 `codex/qwen-workflow-skills`의 로컬 변경이다. 최초 검증 시 원격 푸시·PR은 하지 않았으며 이후 사용자 요청으로 PR #16에 제출했다. 체험용 DB는 기존 개인 role4 DB와 분리했다.

- **PR #11 검토 반영 / 2026-10-14** (1.4.0 유지, [ADR 0013](adr/0013-provider-credential-isolation.md)): URL·출력 형식 설정을 `LLM_API_BASE_URL`·`LLM_RESPONSE_FORMAT`으로 변경. `OPENAI_MODEL`·`OPENAI_API_KEY`는 유지하고 `DONGUK_AI_CHAT_API_KEY`를 분리했다. URL 호스트에 맞는 공급자 키만 선택하며 로컬 Ollama·기타 호환 서버에는 두 키가 있어도 인증 헤더를 보내지 않는다. CI 워크플로는 기능 변경에서 제거해 별도 PR로 분리한다. 최신 `main`의 RAG 전처리·문서 변경을 함께 보존했다. 기존 `.env`는 재시작 전 이름 변경이 필요하며 자동 수정하지 않는다. 실제 동국·Ollama 접속은 미검증.

- **최초 PR #11의 OpenAI 호환 Chat Completions / 2026-10-13** (버전 유지, [ADR 0012](adr/0012-openai-compatible-chat-completions.md)): #8 머지본 `196ad73`에서 `api/llm.py`로 모델 통신·JSON·인용 검증 분리. 당시 `OPENAI_BASE_URL`·`OPENAI_RESPONSE_FORMAT` 추가, 기존 키·모델 이름 유지. 키 없는 로컬 호환 서버 활성화와 health·답변 설정 판정 통일, 실패·잘림·위조 인용은 기존 발췌 경고로 전환. `.env.example`·Compose·README·공급자 계약 갱신. 당시 PR에 검증 워크플로를 연결했으며 2026-10-14 검토에서 별도 PR로 분리. 동국·Ollama 실접속은 미검증.
- **문서 전처리 / 2026-10-13**: Python 전처리 모듈과 페이지·조항·문장 경계 청킹을 구현. 최신 main 통합에서는 모듈을 `backend/api/rag_preprocessing.py`로 옮기고 `api/store/documents.py`에 연결했다. API·테이블·개정 해시·기존 청크를 유지하며 검증 도구도 backend/pytest·e2e 패키지로 재배치했다. [구현·실행·머지 안내](plans/2026-10-13-rag-preprocessing.md).

- **추가 팀 피드백 반영 / 2026-10-13**: 중복된 `maritime_data` 코드 하위 폴더를 제거해 런타임을 `backend/tools/`, 사전 자료 준비를 `scripts/` 바로 아래로 이동했다. import·모듈 실행 명령·저장소 기준 기본 경로를 함께 수정했다. 명세는 `tools.md`(호출·조회·계산)와 `prepare-data.md`(사전 수집·전처리·적재)로 구분하고 관련 ADR·계획 파일명과 색인을 갱신했다. DB 스키마·API URL·응답 계약은 유지한다.

- **역할4 피드백 반영 / 2026-10-13** (버전 유지, [ADR 0011 제안](adr/0011-tools-runtime-and-data-preparation.md)): 실행 Tool을 backend/tools, 준비·적재 스크립트를 최상위 scripts로 분리. 새 dbmate migration으로 해사 DDL을 통합하고 기존 public.ships와 명시적으로 연결한다. MRV·합성 Noon·출처·품질 모델과 API 계약은 유지한다. 기존 데이터 채택·비어 있지 않은 대상 재적재/rollback 거절, 앱 복구 시 연결 보존/해제 기록, 연결된 선박 식별정보 변경 보호를 추가했다.

- **backend 코드 구조 정리 / 2026-10-13** (동작 변경 없음): `backend/pyapi/`를 `backend/api/`로 바꾸고 두 파일에 몰려 있던 코드를 나눔 — `main.py`(앱), `web/`(보안·동시성·진입점·자동 백업), `routes/`(도메인별 경로 표), `store/`(`Workspace`를 도메인 mixin으로 분리), `config`·`deps`·`errors`·`validation`. ASGI 경로는 `api.main:app`. 경로 30개·접두 경로 3개와 `Workspace` 메서드 47개가 이전과 같음을 대조했고, `uv run pytest`(57 통과)와 e2e로 확인.
- **DB 마이그레이션 도입 / 2026-10-13** (버전 유지, [ADR 0010](adr/0010-dbmate-migrations.md)): 앱 스키마를 최상위 `migrations/`의 SQL 파일(dbmate, up/down)로 관리. `backend/pyapi/schema.sql`을 첫 마이그레이션 `20261013000000_init.sql`로 옮기고 삭제. compose에 일회성 `migrate`·`e2e-migrate` 서비스(`amacneil/dbmate:2.36.0`)를 추가해 backend보다 먼저 적용하고, db 컨테이너의 initdb 스크립트 마운트 제거.
- **패키지 분리·docker compose·e2e / 2026-10-13** (버전 유지, [ADR 0009](adr/0009-split-packages-and-compose.md)): `package.json`·lockfile을 `frontend/`로 옮기고(Playwright 제거), `backend/`를 자체 uv 프로젝트로 정리(Python 3.12~3.13, `pyapi`·`maritime_data`를 `backend/`에서 바로 import). 최상위에 `compose.yaml`(db·backend·frontend, profile `e2e`), `compose.dev.yaml`(소스 마운트·핫 리로드), 서비스별 `Dockerfile`(prod·dev 타깃), 최상위 `e2e/`(Playwright Test, 기존 `scripts/next-browser-smoke.mjs` 시나리오 14단계 이식) 추가. 쓰이지 않던 Node/SQLite 백엔드(`backend/*.mjs`와 테스트)와 `scripts/` 전체(실행기·Windows 실행기·SQLite 점검·JSON 수집) 제거, 예시 운항 데이터를 `backend/knowledge/sample-data.json`으로 변환. SQLite → PostgreSQL 이전 도구 `pyapi/migrate_sqlite.py` 제거(만든 PostgreSQL DB가 없고, 로컬 SQLite에도 테스트 흔적만 있어 옮길 데이터 없음). `maritime_data`의 별도 `pyproject.toml`·requirements를 backend로 통합하고 `MARITIME_DATA_API_TOKEN`이 있으면 `/api/maritime-data/*`를 같은 앱에 마운트. Next.js는 `output: 'standalone'`.
- **버그 수정 / 2026-10-13** (e2e로 발견): ① 선박 목록이 `ORDER BY id`라 UUID로 등록한 선박이 임의 위치에 끼어 화면의 기본 선박이 바뀌던 문제 — `ships.seq`(identity, 등록 순서) 추가. ② LAN·서버 IP로 `http://` 접속 시 `crypto.randomUUID`가 없어 문서 등록이 실패하던 문제 — `frontend/src/lib/id.js`에서 `getRandomValues` 대체 경로 사용.
- **FastAPI 이전 / 2026-10-09~10** (PR #7): 기존 `/api/*`를 FastAPI·PostgreSQL로 이전, SQLite 일회성 이전 도구, uv 잠금 파일 추가. (이 항목은 2026-10-13에 소급 기록)
- **역할4 PR 최신 main 반영 / 2026-10-08**: 팀 PR #5(main `18831cb`, 기본 앱 1.4.0)를 병합하고 역할4 문서 충돌 해결. Next.js 공개 진입점(5173)·내부 API(8000)·선택 Python Tool(8001)의 경계에 맞춰 문서를 갱신. 팀의 채택 ADR 0005~0007을 보존하고 역할4 연결 제안은 [ADR 0008](adr/0008-tools-query-and-calculation-boundary.md)로 이동. 역할4 핵심 로직·DB 정의와 최신 팀 Node/Next.js 코드는 그대로 유지.
- **역할4 PR 구조 정리 / 2026-10-08** (기본 앱 버전 유지): 팀 main의 문서·소스 구조를 반영. Python 해사 Tool을 `backend/maritime_data/`로 옮기고 import·실행·적재 경로를 갱신. 역할4 API·데이터 계약은 `specs/`, PostgreSQL 테이블·ERD는 `data-model.md`, 설치·원본 확보·이전 안내는 `user-guide.md`에 통합. 생성기는 DDL·dictionary만 출력하도록 수정하여 설명 문서를 덮어쓰지 않음. 문서 목록·정리 계획·[ADR 0008 제안](adr/0008-tools-query-and-calculation-boundary.md) 추가. 조회·계산 로직·DB 스키마·기존 Node 앱 코드는 변경하지 않음.

- **1.4.0 정리 / 2026-10-08**: `/api/*` 전달을 `next.config.mjs`의 `rewrites`(빌드 때 주소 고정)에서 `frontend/src/proxy.js`(요청마다 결정)로 변경 — `.env`의 `HAEDAP_API_ORIGIN`을 바꾼 뒤 재시작만 하면 반영, 다시 빌드할 필요 없음([ADR 0007](adr/0007-runtime-api-origin-via-proxy.md)).
- **1.4.0 정리 / 2026-10-08**: `start.cmd`를 `scripts/start.cmd`로 이동(최상위에서 실행하도록 경로 보정). Ubuntu 서버 운영 기준으로 Windows 전용 `scripts/setup-lan-firewall.ps1` 제거(방화벽은 OS 설정으로 안내).
- **1.4.0 정리 / 2026-10-08**: 래퍼였던 `scripts/build.mjs` 제거(`npm run build`가 `next build frontend --webpack`을 직접 실행, 출력 폴더는 `next.config.mjs`가 결정), `test:browser`와 중복이던 `npm run test:ui` 제거.
- **1.4.0 / 2026-10-08**: Next.js를 공개 진입점으로 바꾸고 `/api/*`를 `rewrites`로 내부 API 서버에 전달([ADR 0006](adr/0006-nextjs-entry-rewrites-to-api.md)). API 서버는 `127.0.0.1:8000`(`HAEDAP_API_ORIGIN`)에만 바인딩하고 `X-Forwarded-Host` 기준으로 Host·Origin 검사, 공개 포트는 `--public-port`. `backend/frontend-proxy.mjs`와 `--frontend` 옵션 제거. 개발 모드 접속 주소를 5173(Next.js)으로 통일. 프록시 본문 한도 101MB·대기 60초로 상향. **LAN 모드의 접속자 서브넷 검사 제거**(Next.js가 실제 접속자 IP를 전달하지 않음 → OS 방화벽으로 제한).
- **1.3.2 / 2026-10-08**: 개발 모드를 래퍼 스크립트 대신 백엔드·프론트 직접 실행으로 변경([ADR 0005](adr/0005-dev-mode-direct-processes.md)). `npm run dev` → `npm run dev:backend`(`node --watch`, 자동 재시작) + `npm run dev:frontend`(`next dev`). 백엔드에 `--frontend <origin>` 옵션 추가(`HAEDAP_FRONTEND_ORIGIN`보다 우선, `.env`에서도 읽음). `next.config.mjs`가 개발/빌드 출력 폴더를 단계(phase)로 자동 구분. `scripts/run.mjs`와 `start.cmd`는 일반 실행 전용으로 정리(`--dev`, `-Task dev` 제거). 브라우저 검증의 개발 모드도 두 프로세스를 직접 띄우도록 변경.
- **문서 정리 / 2026-10-08** (코드 변경 없음, 버전 유지): 최상위 `docs/` 체계 도입 — `architecture.md`, `data-model.md`, `user-guide.md`, `changelog.md`, `specs/`, `plans/`, `adr/`. README를 소개·구조·설치·Windows/macOS 실행 중심으로 재작성하고 상세 내용을 docs로 이동. AGENTS.md를 문서 위치·작성 규칙 중심으로 갱신(이전의 "docs 폴더를 만들지 않는다" 규칙 폐기, [ADR 0001](adr/0001-docs-directory.md)).
- **1.3.1 / 2026-10-06**: 최상위 소스 폴더를 frontend/backend/scripts로 정리. Next.js와 Windows 실행·테스트 경로 수정. 레거시·중복 설명서 제거 및 README에 통합. 기본 DB 위치를 backend/data로 변경하고 옛 경로 호환·충돌 안내 추가. Windows npm 인수 전달을 명시하여 첫 실행 빌드 호출 보완.
- **1.3.0 / 2026-10-05**: Next.js App Router·React JSX로 UI 이전. 실제 페이지 URL·공통 Provider·컴포넌트·대화상자 적용. 기존 Node API·SQLite·권한 정책 유지. 하나의 시작 명령에서 API 게이트웨이와 Next.js 실행. 설치·빌드·개발·데이터 이전 안내 갱신.
- **1.2.2 / 2026-09-30**: SEA THE ANSWER 표기와 관리자 전용 문서·운항 변경, 즉시 반영.
- **1.2.1 / 2026-09-30**: 로그인 없는 일반 기능과 관리자 admin / 1234, 일반 사용자별 초안·이력 분리.
- **1.2.0 / 2026-09-30**: PDF/CSV, 다중 보고서, 통합 결과, 계정·권한·로그·백업·복구.

## 검증 기록

### 2026-10-15 — 후속 작업 메모 문서 확인

사용자의 최신 우선순위를 계획에 반영하고 기존 인증 설명·API 계약과 대조했다. 변경 문서의 로컬 파일 링크와 `git diff --check`를 확인했다. 실행 코드 변경이 없어 단위·브라우저 테스트를 실행하지 않았으며, 로그인 구현·실제 Ollama 호출·CI PR 병합도 수행하지 않았다.
### 2026-10-22 — 목차 청킹·Kiwi 검증

- Windows Python 3.13, Kiwi 0.24.0, 별도 임시 PostgreSQL 17에서 `backend/` 기준 `uv run python ../.verification/bm25-db-tests.py` 실행: **415 passed / 4 skipped**, 90.10초. helper는 `.env` 없이 임시 서버/테스트 DB에서 `python -m pytest -q -rs --tb=short`를 실행하고 종료했다. skip 4개는 기존 해사 데이터셋을 요구하는 `MARITIME_DATA_TEST_DATABASE_URL` 미설정이며 이번 검색·청킹 테스트는 모두 실행했다. 기존 Starlette/httpx 경고 1개.
- DB 없는 표적 테스트: `uv run pytest tests/test_rag_preprocessing.py tests/test_rag_retrieval.py tests/test_debug_bm25.py -q` → **95 passed**, 2.66초. 합성 목차·연속 제목·본문 문자 보존·길이/페이지·한국어 형태소·한영 용어·부정어·숫자·불용어·기존 권한/CLI 계약을 검증했다.
- 기존 로컬 PDF.js 추출 검토 자료를 사용해 Part 5D의 1~10쪽을 HEAD의 이전 전처리와 비교했다(새 PDF 추출/실제 앱 DB 저장 아님). 공백을 제외한 본문 문자가 동일하고 900자·물리 페이지 제한을 지킨다. 3쪽 목차 25개, 8쪽 목차 34개 항목이 분리되지 않고 base heading을 유지한다. 8쪽 5→4청크, 9쪽 8→6청크이며 9쪽 제목만 있는 청크는 2→0개. 원문 파일/본문은 Git에 추가하지 않았다.
- 목차 판별은 규칙 기반이므로 점선 없는 목차, 본문과 혼합된 목차에는 제한이 있다. 한 항목이 900자를 넘거나 제목과 설명이 서로 다른 페이지에 있으면 길이·페이지 보존을 우선한다. 표 열 구조·로마숫자 꼬리말 개선은 이번 범위 밖이다. 전체 실제 질의에 대한 Recall@5 향상을 측정한 것은 아니다.
- Docker 운영 이미지에서 Kiwi 설치와 frontend production 빌드 성공. 첫 E2E는 문서 저장·검색 등 기능 단계를 통과했지만 최종 브라우저 경고 검사에서 운항 등록 후 `GET /api/health`의 429 한 건으로 실패했다. 기존 비차단 동시 요청 4개 제한에 해당하며 해당 경로·제한은 수정하지 않았다. 재실행 과정에서 `--force-recreate`만으로 의존 DB가 재생성되지 않는 것을 확인해 그 실행을 중단하고 테스트 프로젝트 전체를 `down`한 뒤 다시 실행했다.
- 새 테스트 스택의 최종 E2E **1 passed (30.0초)**, 429 재현 없음. 루트에서 `docker compose -p haedap-rag-kiwi-check --profile e2e up --build --force-recreate --exit-code-from e2e e2e` 실행 후 같은 프로젝트의 `down`으로 정리했다. 실제 앱·DB는 재시작하거나 수정하지 않았으며 커밋·푸시는 하지 않았다. `git diff --check` 통과.

### 2026-10-21 — 최신 main과 BM25 통합

- `backend/`에서 `uv run pytest tests/test_rag_retrieval.py tests/test_debug_bm25.py tests/test_workflow_skills.py -q`: **91 passed / 4 skipped**. 선택 ID 형식·권한 검증과 SQL 필터를 점수 계산 전에 적용하는 회귀 테스트 8개를 추가했다.
- `uv run python ../.verification/bm25-db-tests.py`로 임시 PostgreSQL 17에서 전체 `python -m pytest -q -rs --tb=short` 검증: **399 passed / 4 skipped**, 기존 Starlette/httpx 경고 1개. 최초 실행은 새 기본 용어집의 실제 단어 일치로 합성 문서 전용 결과를 가정한 테스트 1개가 실패했다. 해당 테스트의 롤백 전용 스키마에서 기본 문서를 비활성화해 corpus를 격리한 후 전체 재실행을 통과했다. 4개는 별도 `MARITIME_DATA_TEST_DATABASE_URL`이 필요한 기존 데이터셋 테스트다. 임시 서버 종료, 보조 파일·로그 Git 제외.
- `frontend/`에서 `npm.cmd test`: **4 passed**. Docker의 frontend `npm run build` 성공.
- `docker compose -p haedap-rag-main-merge-check --profile e2e up --build --force-recreate --exit-code-from e2e e2e`: **Chromium E2E 1 passed**, 종료 코드 0. 기존 문서·검색·원문·운항·보고서·관리·백업 및 팀 업무 스킬 흐름 검증. 같은 프로젝트의 `--profile e2e down`으로 정리했으며 실제 앱 스택은 재시작하지 않았다.
- 충돌 마커·미해결 파일 없음, `git diff --check` 통과. 실제 외부 LLM 호출·검색 정확도 개선·새 데이터셋의 내용 검증은 이번 병합 검증 범위 밖이다.

### 2026-10-15 — BM25 개발자 진단

- Windows, Python 3.13, rank-bm25 0.2.2. 신규 진단 테스트 23개. `backend/`에서 `uv run pytest tests/test_debug_bm25.py tests/test_rag_retrieval.py -q`: **53 passed**. 루트의 `uv run --project backend pytest backend/tests/test_debug_bm25.py backend/tests/test_rag_retrieval.py -q`와 CLI `--help`도 확인했다.
- `backend/`에서 `uv run python ../.verification/bm25-db-tests.py`로 격리된 PostgreSQL 17 클러스터를 열어 `python -m pytest -q -rs --tb=short` 수행: **338 passed / 4 skipped**, 기존 Starlette/httpx 경고 1개. 4개는 `MARITIME_DATA_TEST_DATABASE_URL`이 필요한 기존 데이터셋 테스트다. 임시 서버는 종료했다. 보조 스크립트·로그는 Git 제외이며 실제 앱 DB를 테스트용으로 사용하지 않았다.
- `docker compose build backend` 후 README의 일회성 CLI 명령(`--top-k 3 --preview-chars 0 --json`)을 실제 등록 DB에서 실행했다. 공개 검색 후보 **5,689개 청크**를 확인했고, 세 질의(한국어 선급정지 / 영어 heavy deck cargo / 혼합 Part 5D)에 대해 진단의 순위·점수가 기존 `retrieve` 및 `DocumentStore.search` 순위와 일치했다. 문서 ID+제목 필터의 corpus 1,376개, 없는 ID의 빈 결과, 기존 활성 관리자 계정 범위도 확인했다. `SHOW transaction_read_only=on` 확인. 본문·접속 문자열·비밀값은 출력/기록하지 않았으며 실 DB에는 쓰지 않았다.
- `docker compose -p haedap-bm25-debug-check --profile e2e up --build --force-recreate --exit-code-from e2e e2e`: **Chromium E2E 1 passed**, 종료 코드 0. backend·frontend 운영 이미지 빌드 및 기존 문서/검색/운항/보고서/관리/백업 흐름 통과. 이후 같은 프로젝트의 `docker compose ... --profile e2e down`으로 테스트 컨테이너·네트워크를 정리했다. 기존 `haedap` 웹앱은 재시작하지 않았다.
- UI 소스를 바꾸지 않아 frontend 단위 테스트는 별도로 재실행하지 않았다. 검색 정확도 개선, 토큰별 점수 기여도, 대규모 성능, 실제 외부 LLM 호출은 검증 범위 밖이다. `git diff --check` 통과.

### 2026-10-14 — BM25 문서 검색

- Windows, Python 3.13, rank-bm25 0.2.2. 사용자의 `.env`·실제 PDF·앱 DB는 변경하지 않았다.
- `backend/`에서 `uv run pytest -q`: DB 설정 없는 초기 실행은 253 passed / 65 skipped. 이후 실 DB 검색 회귀 테스트 1개를 추가했다.
- 격리된 loopback PostgreSQL 17 클러스터의 `HAEDAP_TEST_DATABASE_URL`을 설정하고 `python -m pytest -q -rs --tb=short`: **315 passed / 4 skipped**, 기존 Starlette/httpx 사용 중단 경고 1개. 4개는 적재된 해사 데이터셋용 `MARITIME_DATA_TEST_DATABASE_URL`이 없어 건너뛰었다. 임시 서버는 종료했다. 로컬 보조 실행 명령: `backend/`에서 `uv run python ../.verification/bm25-db-tests.py` (보조 파일·로그는 Git 제외).
- 신규 검색 단위 테스트 30개: 한영 순위·길이/빈도 반영, 동의어·한글 조사 대응, Unicode 정규화, 메타데이터 보존, 빈 입력, 0/음수 점수, top-k·동점, 권한/상태/종류 필터를 점수 계산 전 적용하는지 확인.
- 실 DB에서 합성 문서 저장 → `/api/search` 한영 순위·문서명·페이지·heading → `/api/ask` 원문 인용 → 범위/상태 변경 즉시 제외를 검증했다. 기존 개정·중복·롤백 테스트도 통과했다.
- `frontend/`에서 `npm.cmd test`: **4 passed**.
- 루트에서 `docker compose -p haedap-bm25-check --profile e2e up --build --force-recreate --exit-code-from e2e e2e`: **Chromium E2E 1 passed**, 종료 코드 0 (문서·검색·원문·운항·보고서·관리·백업 전체 시나리오). backend는 새 의존성으로 운영 이미지 빌드, frontend 운영 이미지는 변경 없는 기존 빌드 캐시를 사용했다. 기존 앱과 다른 Compose 프로젝트명으로 실행하고 `docker compose -p haedap-bm25-check --profile e2e down`으로 테스트 스택을 정리했다.
- 실제 해사 질문 평가 세트의 Recall@5, 대규모 자료 성능, 실제 외부 LLM 호출은 이번 검증에 포함하지 않았다.

### 2026-10-14 — PR #11 검토 반영 (Windows)

환경: 최신 `main`의 #10 머지본 `76620c7` 반영, Python 3.13.16·uv. 테스트에는 실제 모델 키를 사용하지 않았다.

| 검증 | 실제 결과 |
|---|---|
| 모델 전용 모의 HTTP·API pytest | 94 통과. 두 공급자 키가 함께 있을 때 대상별 Bearer 헤더, Ollama 무인증, 키 누락·유사 도메인·URL 경로의 키 격리, 새 설정 이름·health·발췌 전환 검증 |
| `backend/`에서 `uv run --locked --offline pytest -q --basetemp ../.verification/pytest-llm-review-20261014` | 189 통과, 실 PostgreSQL·데이터셋이 필요한 60 건너뜀. 기존 Starlette TestClient/httpx 사용 중단 경고 1건. 최초 실행의 Windows 임시 폴더 권한 오류는 전용 검증 폴더 재실행으로 해소 |
| 문서·기능 변경 범위 | 최종 로컬 링크 171개·JSON 예제 2개와 `git diff --check` 통과. 최신 main 대비 CI 워크플로·frontend·e2e·migrations·의존성 변경 없음 |
| 로컬 Compose e2e·정리 명령 | `docker compose --profile e2e up --build --force-recreate --exit-code-from e2e e2e` 및 `down`을 시도했으나 Docker 실행 파일이 없어 실행 불가 |
| 실제 OpenAI·동국 AI Chat·Ollama 호출 | 수행하지 않음. 공급자 공식 접속 정보·실행 모델 환경에 대한 검증은 후속 항목 |

제출: 검토 반영 기능은 [PR #13](https://github.com/dudco/sea-the-answer/pull/13), CI 워크플로는 [PR #14](https://github.com/dudco/sea-the-answer/pull/14)로 분리했다. PR #13은 최신 main 기준으로 CI 파일을 포함하지 않는다.

같은 날 [기능 검증 Actions](https://github.com/cxo-ca/sea-the-answer/actions/runs/38518450553)가 성공했다. 검증 커밋 `2eeaffc`는 기능 커밋 `e72f1ce`에 별도 CI 워크플로만 추가한 것으로, 모델 코드·Compose·설정 예제는 동일하다. Linux / Python 3.13.16 / PostgreSQL 18에서 백엔드 **245 통과·실 데이터셋 4 건너뜀**, 프런트 **4개 통과·Next.js 16.3.8 빌드 성공**, 운영·개발·e2e Compose 검사 3종과 Docker Chromium e2e **1개 통과**를 확인했다. e2e 종료 코드 0, 테스트 컨테이너·네트워크 제거도 확인했다. 기존 Starlette/httpx 경고 1건이 있으며 실제 외부 모델 호출은 검증하지 않았다. 이후 제출 링크·결과 기록 변경은 문서에만 해당한다.

별도 [CI 전용 Actions](https://github.com/cxo-ca/sea-the-answer/actions/runs/38518455486)도 커밋 `8112816`에서 성공했다. LLM 변경을 포함하지 않은 최신 main에 CI만 추가해 백엔드 **151 통과·실 데이터셋 4 건너뜀**, 프런트 테스트·빌드, Compose 3종, Docker e2e와 정리를 확인했다.

### 2026-10-13 — 최초 PR #11의 Chat Completions 구현 (Windows)

환경: #8 머지 커밋 `196ad73`, Python 3.13.16·uv 0.13.0·Node.js 24.21.0. 실행 도구는 프로젝트의 무시된 `.verification/`에 준비했고 backend 잠금 파일의 dev·data 의존성과 frontend `npm ci`를 설치했다. 개인 `.env`·DB·마이그레이션·패키지 잠금 파일은 수정하지 않았다.

| 검증 | 실제 결과 |
|---|---|
| 모델 전용 pytest | 70 통과. 모의 HTTP로 OpenAI·사용자 지정 경로·키 없는 로컬 주소, JSON 옵션, 언어·인용·실패 전환·health와 실제 답변 오케스트레이션 검증 |
| 전체 backend pytest (`--basetemp`는 프로젝트 내부 검증 폴더) | 147 통과, 실 PostgreSQL 연결·데이터셋이 필요한 58 건너뜀. Starlette TestClient/httpx 사용 중단 경고 1건 |
| frontend `npm test` | 4 통과 |
| frontend `npm run build` | Next.js 16.3.8 standalone 빌드 성공 |
| 로컬 Docker Compose·e2e | Docker 실행 파일·데몬이 없어 실행하지 못함. PR 워크플로에 검증 연결 |
| 실제 OpenAI·동국 AI Chat·Ollama 호출 | 수행하지 않음. 동국 웹 링크는 API 주소가 아니며 실제 API 정보·실행 모델 환경 미확보 |

같은 날 최초 PR #11의 Linux GitHub Actions에서 커밋 `7d7f956`의 [검증 실행](https://github.com/cxo-ca/sea-the-answer/actions/runs/38408707402)이 성공했다. 백엔드 201 통과·실 해사 데이터셋 4 건너뜀(임시 PostgreSQL 18로 로컬에서 건너뛴 통합 테스트 포함), 프런트 단위 테스트·빌드 성공, 운영·개발·e2e Compose 구문 검사 성공, Docker의 격리된 DB→dbmate→FastAPI→Next.js→브라우저 14단계 흐름 1개 테스트 통과·정리 성공. 이는 2026-10-14 검토 반영 전 변경의 검증 기록이며 현재 변경 검증을 대신하지 않는다. 실제 모델 키·주소는 e2e에 전달하지 않았으므로 실제 공급자 연결 검증은 여전히 미검증이다.

제출: 원본 저장소 직접 푸시 권한이 없어 본인 fork의 `feature/openai-compatible-chat`에서 [PR #11](https://github.com/dudco/sea-the-answer/pull/11)을 제출했다. 원본 PR의 Actions는 실행이 관찰되지 않아 활성화된 fork의 동일 워크플로로 검증했다. 개인 Git 전역 설정·원본 main·PR 병합은 변경하지 않았다. 준비 문서는 stash `c1c56bd`에도 보존했다.

최초 모델 테스트의 메모리 DB 대역이 최신 advisory lock 질의를 처리하지 못해 실패했으며 대역을 보완한 뒤 70개가 통과했다. 전체 테스트는 샌드박스 임시 폴더 접근, 프런트 테스트는 자식 프로세스 실행 제한으로 실패한 뒤 승인된 실행으로 재검증했다. 이 환경 오류를 제품 코드 변경으로 우회하지 않았다.

### 2026-10-13 — RAG 최신 main 통합 검증

기준 `upstream/main` `196ad73` + RAG `9d6b4c2`. Windows / Node.js 24.21.0 / Python 3.13.15 / PostgreSQL 17.11 / Playwright 1.62.1. 삭제/수정 2개와 내용 2개, 총 4개 파일의 충돌을 해결했다. 전처리 로직은 내용 변경 없이 `backend/api/rag_preprocessing.py`로 이동했고 `DocumentStore.save_document`에 연결했다. 팀의 frontend·tools·마이그레이션·의존성 잠금 파일은 그대로 유지한다.

| 검증 | 결과 |
|---|---|
| backend 전체 pytest (격리 PostgreSQL 포함) | **151 passed, 4 skipped**, 기존 Starlette/httpx 경고 1개. 건너뛴 4개는 별도 해사 원본 데이터셋을 요구하는 조회 테스트 |
| 기본 `uv run --locked pytest -q` (DB 테스트 변수 없음) | 95 passed, 60 skipped. DB 회귀는 위 격리 서버에서 별도로 활성화 |
| frontend `npm test`, `npm run build` | **4 passed**, production standalone 빌드 성공 |
| 실제 PDF 검증 | Part 5D 물리 20/21/22쪽 → 21청크, Part 6 물리 23/30/31쪽 → 13청크. 새 API의 저장·검색 문서명/페이지·원본 PDF 반환 통과, 임시 스키마 롤백 |
| 기존 브라우저 e2e | 독립 포트의 FastAPI + production standalone + 빈 PostgreSQL에서 전체 시나리오 통과. `e2e/test-results/.last-run.json`: `passed`, 실패 목록 없음 |
| Git 검사 | 충돌 표시 제거, `git diff --check` 통과. 머지 변경은 스테이징하고 커밋·푸시는 하지 않음 |

기존 `.env` 계정으로 전체 DB 회귀를 켠 첫 시도는 임시 데이터베이스 생성 권한 부족으로 54개 setup 오류(97 passed, 4 skipped)가 났다. 계정 권한을 변경하지 않고 별도의 임시 PostgreSQL 클러스터로 전환해 위 결과를 얻었다. RAG 전용 2개 DB 테스트는 기존 계정에서도 임시 스키마 롤백 방식으로 통과했다.

Docker 실행 파일이 없어 지정된 compose e2e 명령은 실행하지 못했다. 대신 실제 두 migration의 up SQL을 빈 검증 DB에 적용하고 Dockerfile과 같은 standalone/static/public 배치로 브라우저 테스트를 수행했다. Docker 이미지 빌드·컨테이너 실행과 dbmate CLI 자체는 이번 검증 범위 밖이다. 브라우저 설치 완료 전 첫 e2e 시도는 실행 파일 미존재로 실패했고, 설치 후 통과했다. 마지막 로컬 실행기는 통과한 Playwright 결과를 터미널에 출력할 때 Windows CP949 인코딩 오류가 났으나, Playwright가 남긴 성공 결과와 실패 목록 없음은 별도로 확인했다. 테스트 서버는 모두 종료했고 로그·검증용 DB 파일은 Git 제외 `.verification/`에 보존했다. 사용자 DB의 기존 문서·설정, `.env`, PDF 원본은 보존했으며 외부 LLM은 호출하지 않았다.

### 2026-10-13 — Python 문서 전처리

Windows / Node.js 24.21.0 / Python 3.13.15 / PostgreSQL 17 / 설치된 Edge headless.

| 검증 | 결과 |
|---|---|
| Python 기존 API + 전처리 | 27개 통과 |
| 실제 PostgreSQL API 회귀 | 2개 통과: 페이지·제목·인용, 중복/개정/이전 청크 보존, 권한, 삭제, 실패 롤백 |
| 실제 PDF | Part 5D 물리 20/21/22쪽(21청크), Part 6 물리 23/30/31쪽(13청크)의 API 저장·검색·원본 PDF 반환 통과. 검증 스키마 롤백 |
| `npm test` | Node 33개 중 32개 통과, 기존 Windows launcher 테스트의 `taskkill /T /F` 종료 코드 128로 실패. 이 단계의 실패 때문에 npm의 후속 Python 단계는 실행되지 않음 |
| `node scripts/run-python-tests.mjs` | 별도 실행: 27개 통과, 실 DB 환경변수 미설정 2개 skip |

FastAPI TestClient의 기존 httpx 관련 사용 중단 경고 1개가 발생한다. UI 코드는 변경하지 않아 build/기존 브라우저 smoke는 수행하지 않았다. 실제 PDF 추출은 Playwright에서 현재 `frontend/src/lib/pdf.js` 함수를 실행했고 저장/검색은 FastAPI TestClient + 실제 PostgreSQL로 확인했다. UI 화면 클릭을 포함한 전체 업로드 테스트와 전체 검색 정확도 평가는 별도이다. 기존 README/설계 문서 일부에 Node/SQLite 설명이 남아 있어 현재 Python 경로와의 차이를 아키텍처·데이터 모델 상단에 명시했다.

### 2026-10-13 - PR #9 최종 점검

- 최신 PR #8 기준과 PR #9의 import·이미지 경로·DB/API 계약·기존 데이터 보존 경계를 대조했다. 커밋된 migration 및 잠금 파일은 변경하지 않았다.
- 해사 적재의 테이블 잠금과 복구가 충돌하면 기존 복구 요청이 오래 대기할 수 있음을 실제 PostgreSQL에서 재현했다. 복구의 lock_timeout을 5초로 제한하고 409 BUSY로 응답하도록 수정했다.
- 회귀 테스트는 충돌 시 복구가 제때 거절되고 앱 선박·해사 연결·성공 감사 기록이 변경되지 않음을 확인한다.
- 보완 후 backend 전체 **135 passed, skipped 0**(기존 Starlette 경고 1개), 관련 API·복구·매핑 **50 passed**, 깨끗한 Chromium의 production standalone e2e **16단계 통과**. dbmate와 실제 6개 CSV의 임시 DB 적재·데이터가 있는 rollback 거절도 다시 확인했다.
- frontend 소스·의존성은 변경하지 않았으므로 앞선 단위 4개 및 production 빌드 검증을 유지한다. Docker 컨테이너 실행과 실제 개인 DB 이전은 미검증·미수행 범위로 유지한다.

### 2026-10-13 - 역할4 Tool·준비 작업·공통 DB 통합 (Windows)

- 기준: 팀 PR #8 refactor/split-packages의 f0610d0. 기존 main 및 개인 작업 디렉터리와 분리한 worktree에서 검증했다.
- 환경: Windows, Node.js 24.16.0, Python 3.12.14, PostgreSQL 18, dbmate 2.36.0, backend/frontend/e2e의 기존 잠금 파일. 잠금 파일과 이미 커밋된 init migration은 변경하지 않았다.
- backend 전체 pytest: **134 passed**, 실 DB 생략 **0**. Starlette/httpx 사용 중단 경고 1개는 기존 의존성에서 발생한다.
- 실제 PostgreSQL 회귀: 새/기존 maritime_data/기존 role4 채택, 충돌·컬럼/제약 불일치 거절 및 원복, 데이터가 있는 down 거절, 빈 스키마 down/up, 명시적 선박 연결·식별 변경 거절, 앱 백업·복구 호환·중간 실패 rollback, CSV 헤더·건수·출처 검증·재적재 거절을 포함한다.
- dbmate 실 실행: up → status → up(변화 없음) → rollback(빈 스키마) → up 통과. 데이터가 있는 별도 DB에서 rollback이 실패하고 migration 이력 및 데이터가 보존됨을 확인했다.
- 보유 처리본은 읽기만 하고 임시 DB에 적재했다: source_files 6, vessels 25,252, annual_reports 80,552, synthetic_noon 4,380, synthetic_voyages 238, quality_issues 26,249. 실제 연간 조회 View는 79,032행, 앱 ships 자동 생성은 0행이다.
- frontend: 단위 테스트 **4 passed**, npm run build 성공. 실제 Next standalone → FastAPI → PostgreSQL 및 마운트된 해사 factors 경로 확인.
- e2e: Playwright 1.62.1의 깨끗한 Chromium Headless Shell에서 **1개 시나리오·16단계 통과**, 종료 코드 0. 테스트별 DB·API/화면 포트·백업 디렉터리를 분리하고 소유 프로세스를 종료했다.
- 기존 설치 Chrome 실행은 외부 요청의 ERR_CERT_AUTHORITY_INVALID 경고로 최종 검사가 실패했다. 이후 테스트 전용 Chromium에서 경고 검사를 유지한 채 통과했으며 인증서 검사를 끄지 않았다. 재실행 준비 중에는 이전 테스트의 백업 폴더가 재사용돼 복구/생성 요청이 겹친 것을 확인하고, 테스트마다 폴더를 분리했다.
- CLI help·사전 JSON 생성·PowerShell 구문 분석·git diff --check 통과.
- 미검증: Docker 실행 파일이 없어 compose 이미지 빌드·컨테이너 e2e는 실행하지 않았다. 대신 동일 migration/실제 DB와 production standalone을 별도 프로세스로 실행했다. 실제 개인 DB의 이전, 외부 LLM, 공식 CII, 사용자별 화면 어댑터는 수행·완료 범위가 아니다.

### 2026-10-13 — Docker로 e2e 실행 (macOS, Apple Silicon, PostgreSQL 18.6 이미지)

| 검증 | 결과 |
|---|---|
| `docker compose --profile e2e up --build --exit-code-from e2e e2e` | 이미지 빌드부터 e2e-db → e2e-migrate(마이그레이션 적용) → e2e-backend → e2e-frontend → e2e 순서로 실행, 14단계 1개 테스트 통과, 종료 코드 0 |
| 테스트 종료 후 상태 | `e2e` 컨테이너만 멈추고 e2e-db·e2e-backend·e2e-frontend는 계속 실행됨 → 다시 실행하면 이전 데이터가 남은 DB를 씀 |
| `--force-recreate --attach-dependencies` 추가 | e2e-migrate가 정상 종료하는 순간 중단되어 테스트가 시작되지 않았고 e2e 컨테이너는 `Exited (0)`, 의존 서비스는 여전히 실행 중 → 사용하지 않음 |
| `--force-recreate` | 컨테이너를 새로 만들어 DB 초기화와 마이그레이션이 처음부터 다시 적용됨을 로그로 확인 → 표준 명령에 포함하고 종료 후 `down`으로 정리 |

### 2026-10-13 — dbmate 마이그레이션

환경: 위 기록과 같은 Linux 작업 공간, dbmate 2.36.0(npm), PostgreSQL 16. Docker 데몬이 없어 `amacneil/dbmate` 이미지로 실행하는 `migrate` 서비스 자체는 실행하지 못했습니다.

| 검증 | 결과 |
|---|---|
| `docker compose config -q` (운영, 운영+개발, `--profile e2e`) | 3개 통과. backend → `migrate`(`service_completed_successfully`) 의존 확인 |
| 빈 DB에 `dbmate up` → `status` → 다시 `up` → `rollback` → `up` | 적용 1건, 재실행은 변화 없음, rollback 후 앱 테이블 0개(`schema_migrations`만 남음), 재적용 정상 |
| 일부러 실패하는 마이그레이션 | 종료 코드 2, 그 파일의 테이블 생성까지 롤백, 이력에 기록 안 됨 |
| `postgresql://…?sslmode=disable` 하나를 dbmate·psycopg가 공유 | 둘 다 연결 성공 |
| `backend/`: `uv run pytest` | 57 통과, 4 건너뜀 |
| dbmate로 만든 DB에서 e2e (`127.0.0.1`, `e2e-frontend` 두 조건) | 둘 다 14단계 통과 |

### 2026-10-13 — 패키지 분리·docker compose·e2e

환경: Linux 클라우드 작업 공간(Python 3.13, uv, Node.js 22, PostgreSQL 16, Playwright 번들 Chromium). **Docker 데몬이 없어 이미지 빌드와 `docker compose up`은 실행하지 못했습니다.** 대신 compose와 같은 구성을 프로세스로 띄워 검증했습니다: 빈 DB에 `schema.sql` 적용 → `uvicorn pyapi.workspace_api:app --proxy-headers` → `next build` 산출물을 `frontend/Dockerfile`의 prod 단계와 같은 배치(standalone + static + public)로 `node server.js` 실행 → `e2e/`에서 Playwright.

| 검증 | 결과 |
|---|---|
| `docker compose config -q` (운영, 운영+개발 오버레이, `--profile e2e`) | 3개 모두 통과 |
| `backend/`: `uv lock`, `uv sync --locked`, `uv run pytest` | 58 통과, 4 건너뜀(`MARITIME_DATA_TEST_DATABASE_URL` 필요한 실 DB 테스트) |
| `frontend/`: `npm ci`, `npm test`, `npm run build` | 단위 4개 통과, 빌드 성공(standalone) |
| e2e, `E2E_BASE_URL=http://127.0.0.1:5173` | 14단계 1개 테스트 통과(약 20초) |
| e2e, compose와 같은 조건 `http://e2e-frontend:5173` + `HAEDAP_ALLOWED_HOSTS=e2e-frontend` | 통과 (수정 전에는 `crypto.randomUUID` 오류로 실패) |
| 스키마 미적용 DB | `/api/health` 503 `SCHEMA_NOT_READY` |
| 허용되지 않은 Host로 프록시 경유 요청 | 403 |

미검증: Docker 이미지 빌드·실행(특히 `postgres:18-alpine`의 초기화 스크립트, `mcr.microsoft.com/playwright:v1.62.1-noble` 이미지, macOS·Windows 바인드 마운트 핫 리로드), Node.js 24에서의 실행(engines 기준), 외부 LLM 호출.

### 2026-10-08 — 역할4 PR 최신 main 반영

환경: Windows, Python 3.12.14, Node.js v24.16.0, 기본 앱 1.4.0 및 Next.js 16.3.8. 로컬 정리 커밋 `fef7e20`에 최신 팀 main `18831cb`를 반영한 결과입니다.

| 검증 | 결과 |
|---|---|
| `npm run build` | 최신 `proxy.js`를 포함한 배포용 빌드 성공 |
| `npm test` | **33개 통과**, Windows CMD·PowerShell·LAN 실행 및 Next.js 경유 API 확인 |
| `python -m pytest -q backend/maritime_data/tests` | **47개 통과, 실 DB 4개 건너뜀** |
| 전처리 테스트 | **3개 통과** |
| 문서·코드 경계 | DB 필드 70개·DDL·dictionary 일치, 로컬 링크·앵커 확인, 팀 채택 ADR 0001~0007과 Node/Next.js 코드 및 역할4 핵심 로직 보존 |
| 파일 검사 | 병합 충돌·이전 역할4 ADR 경로 제거, `git diff --check` 통과 |

Node 테스트는 이 PC의 중복 Node PATH를 제외하고 `HAEDAP_NODE`를 공식 Node 실행 파일로 지정한 별도 프로세스에서 실행했습니다. Python은 동일한 Starlette TestClient/httpx deprecation 경고 1개를 출력했습니다. 실 PostgreSQL·원본 전체 재전처리·팀 Python 어댑터·LLM·공식 CII 및 전체 브라우저 업무 흐름은 이번 검증에 포함하지 않았습니다. DB·원본·개인 설정은 변경하지 않았습니다.

제출 결과: 같은 날 `feature/operation-db` 일반 푸시와 [기존 PR #3](https://github.com/dudco/sea-the-answer/pull/3)의 본문 갱신을 완료했습니다. 새 PR 생성·강제 푸시·PR 병합은 수행하지 않았습니다.

### 2026-10-08 — 역할4 PR 구조 정리

환경: Windows, Python 3.12.14, Node.js v24.16.0. 최신 팀 main `6608f6c`와 역할4 원격 head `cefd557`을 기존 작업용 체크아웃에서 로컬 병합하여 검증했습니다.

| 검증 | 결과 |
|---|---|
| `python -m pytest -q backend/maritime_data/tests` | **47개 통과, 실 PostgreSQL 대상 4개 건너뜀** |
| `python backend/maritime_data/scripts/test_prepare_maritime_data.py` | **3개 통과** |
| `npm test` | **33개 통과**, Windows CMD·PowerShell·LAN 실행 및 게이트웨이 응답 포함 |
| Windows 실행기에서 첫 실행 설치·Next.js 빌드 | 성공, `frontend/.next/BUILD_ID` 생성 및 세 실행 방식 확인 |
| 설명 생성기 `--out` 산출물 비교 | 기존 SQL·dictionary와 일치, 설명 Markdown을 생성하지 않음 |
| DB 필드·문서·경로 검사 | 6개 테이블의 필드 **70개** 대조, 로컬 문서 링크·앵커 확인, 이전 import·경로 제거 |
| 변경 경계·구문 검사 | 핵심 Python 조회·계산·전처리·마이그레이션 및 DB 스키마 보존, Node 코드·채택 ADR 0001~0004 보존, 적재 PowerShell 구문 및 `git diff --check` 통과 |

처음 `npm test` 실행은 이 PC의 Node 설치 두 개를 PowerShell 실행기가 하나의 경로 문자열로 읽어 Windows 실행기 1개가 실패했습니다. 별도 프로세스의 PATH에서 중복 설치 경로를 제외하고 `HAEDAP_NODE`를 공식 Node 실행 파일로 지정해 재실행한 결과 33개가 통과했습니다. 기존 팀 실행기 코드는 이 PR에서 수정하지 않았습니다. Python 테스트는 Starlette TestClient/httpx의 deprecation 경고 1개를 출력했습니다.

이번에 검증하지 않은 범위: 실제 PostgreSQL 조회·재적재·스키마 이름 변경(`MARITIME_DATA_TEST_DATABASE_URL` 미설정), 원본 데이터 전체의 재전처리, 팀 앱과 Python Tool의 연결·LLM·공식 CII 및 전체 브라우저 업무 흐름. 원격 푸시·PR 본문 변경·댓글은 수행하지 않았습니다.


### 2026-10-08 — 1.4.0

환경: Linux, Node.js v24.21.0, Next.js 16.3.8, Playwright + Chromium(사전 설치본).

| 검증 | 결과 |
|---|---|
| `npm test` | **32개 통과, 실패 없음, Windows 전용 1개 건너뜀** (네트워크 정책 테스트를 프록시 경유/직접 호출로 재작성, HTTP 통합 테스트에 `X-Forwarded-Host` 경유 검사 추가) |
| `npm run build` | 성공 |
| `npm run test:browser` (일반 실행) | **17개 업무 흐름 통과** |
| `HAEDAP_TEST_DEV=1 npm run test:browser` (API 서버 + `next dev` 직접 실행) | **17개 업무 흐름 통과** |
| `npm start -- --lan` 수동 확인 | 60MB 요청 본문이 프록시를 거쳐 API까지 전달(앱 검증 응답 403 수신), LAN 주소로 화면·API 200, LAN 주소의 8000 포트는 연결 거부, 위조한 `X-Forwarded-For`는 무시 |

`proxy.js` 전환 후(같은 날): `npm test` 32개 통과, 빌드 성공, 브라우저 17개 흐름 일반·개발 모드 모두 통과. `HAEDAP_API_ORIGIN` 없이 빌드한 뒤 최상위 `.env`에만 다른 주소를 넣고 `next start` → 그 주소로 전달됨(재빌드 불필요) 확인.

Next.js 16.3.8 동작 확인(임시 에코 서버): rewrite 대상 주소는 `next build` 시점 값으로 고정, `X-Forwarded-Host`는 실제 Host로 덮어씀, `X-Forwarded-For`는 클라이언트 값을 그대로 전달, 기본 본문 한도 10MB 초과 시 프록시 실패.

검증하지 않은 범위: Windows·macOS 직접 실행, `start.cmd`, 다른 기기에서의 실제 LAN 접속.

### 2026-10-08 — 1.3.2

환경: Linux, Node.js v24.21.0, Next.js 16.3.8, Playwright + Chromium(사전 설치본).

| 검증 | 결과 |
|---|---|
| `npm test` | **33개 통과, 실패 없음, Windows 전용 1개 건너뜀** (`--frontend` 옵션 테스트 1개 추가) |
| `npm run build` | 성공 |
| `npm run test:browser` (일반 실행, `scripts/run.mjs`) | **17개 업무 흐름 통과** |
| `HAEDAP_TEST_DEV=1 npm run test:browser` (백엔드·`next dev` 직접 실행) | **17개 업무 흐름 통과** |
| `npm run dev:backend` → `npm run dev:frontend` 수동 실행 | 프론트 기동 전 안내 문구, 기동 후 `/chat` 200, 백엔드 파일 수정 시 자동 재시작, 개발 실행 후에도 `frontend/.next/BUILD_ID` 변경 없음 |

검증하지 않은 범위: Windows·macOS에서 두 명령 직접 실행, `start.cmd` 실제 실행.

### 2026-10-08 — 문서 정리

문서만 변경했으므로 테스트는 실행하지 않았습니다. 문서의 파일 경로, npm 스크립트(`package.json`), `start.ps1` 옵션, 테이블 정의(`backend/db.mjs`, `backend/workspace.mjs`), API 경로를 현재 코드와 대조했습니다. macOS 실행 절차는 같은 Node 명령을 쓰는 Linux 검증에 근거하며 macOS에서 직접 실행하지는 않았습니다.

### 2026-10-06 — 1.3.1

환경: Linux, Node.js v24.19.0, Next.js 16.3.8, React 19.2.7, Playwright와 Chromium 153.

| 검증 | 결과 |
|---|---|
| `npm run build` | `frontend/.next`에 배포용 빌드 성공 |
| `npm test` | **32개 통과, 실패 없음, Windows 전용 1개 건너뜀** |
| 일반 실행의 실제 브라우저 검증 | **17개 업무 흐름 통과**, 브라우저 예외·React 경고 없음 |
| 개발 실행의 실제 브라우저 검증 | **동일한 17개 흐름 통과**, 개발 빌드 경로 분리 확인 |
| DB 경로 호환 | 새 위치·옛 위치·사용자 지정 경로·양쪽 DB 존재 시 명시적 선택 검증 |

브라우저에서 공개 접근, 질문·검색·출처, 문서 상세 URL·새로고침, 일반 사용자의 변경 차단, 실패한 로그인 재시도, 관리자 로그인·로그아웃, 문서 등록·개정·삭제, 실제 PDF 추출·원문 저장, 선박·기록 등록·수정·삭제, 계산, CSV 검증·등록, 보고서 생성·저장·뒤로가기·검토 요청·승인, 백업·복구·세션 무효화, 모바일 메뉴를 확인했습니다. PDF는 테스트용 1페이지 텍스트 PDF의 원문 바이트까지 대조했습니다. 모든 업무 검증은 임시 DB·임시 포트로 진행했습니다.

검증하지 않은 범위:

- Windows에서 `start.cmd` 직접 실행(인수 전달·경로는 수정했으나 미실행)
- 다른 기기의 실제 LAN 접속, 휴대폰·Safari·Edge 전체 호환성, 모든 PDF 형식 (모바일은 Chromium 390px 기준)
- 실제 외부 LLM 호출 (모델 실패·인용 검사는 모의 응답 사용)
- 공식 CII 계산·규정 적용 자동 판정·검색 Recall·응답 시간 목표·번역 품질·공식 보고서 서식

## 2026-10-13 추가 폴더·문서 피드백 검증

- Windows / Python 3.12.14 / PostgreSQL 18: 변경된 모듈 경로로 전체 backend **135개 통과, 생략 0개**. 기존 Starlette/httpx 경고 1개. 테스트 파일명 정리 후 135개 수집도 재확인했다.
- 격리된 테스트 DB에서 dbmate up/status/재실행/빈 스키마 rollback/up과 실제 처리본 적재 확인: MRV 80,552행, Noon 4,380행, 실제 연간 View 79,032행, 앱 선박 자동 생성 0행. 데이터가 있는 rollback은 거절했다. 개인 DB와 원본은 변경하지 않았다.
- `scripts.load_data`, `scripts.link_ship`의 CLI help, 새 경로의 필드 사전 생성, PowerShell 구문, 문서 내부 파일 링크, diff 공백 검증 통과.
- 이번 추가 변경에서는 frontend·브라우저 e2e·Docker 실행을 재검증하지 않았다. 기존 검증 기록은 위 항목의 당시 결과다.

## 2026-10-13 - MRV 제원 후보 연결 및 참고 지표 검증 (Windows)

- **MRV 참고 탄소집약도 / 2026-10-13 (로컬·미제출)**: 공개 DWT 후보를 별도 capacity_candidates에 보존하는 추가 migration·미리보기/빈 테이블 적재 CLI와 서버 Bearer 전용 reference-intensity API를 추가했다. 단일 승인 MRV의 보고 CO₂·추정 거리·출처 충돌 없는 후보 DWT로 참고값을 계산하고, 공식 CII·등급은 계속 null이다. 기존 calculate 응답·기존 migration·원본·앱 테이블은 유지한다. 지원 선종은 Bulk carrier/Container ship/Oil tanker다.

- 기준 main 196ad73108db, 로컬 codex/mrv-reference-intensity. 원격 푸시·PR 갱신·개인 DB 변경 없이 수행했다.
- 전체 backend **170 passed, skipped 0**. 기존 Starlette/httpx 경고 1개. 단위·입력·인증·출처 충돌/결측/0·범위·숫자 정밀도·원본 불변·실 DB 회귀 포함.
- dbmate 실제 실행: fresh up/status/reup, 빈 참조 migration down/up 통과. 참조 데이터 적재 후 down은 거절되고 전체 transaction이 보존됐다.
- 기존 보유 CSV를 읽기만 하여 임시 DB에 source_files 6, vessels 25,252, MRV 80,552, Noon 4,380, voyages 238, quality_issues 26,249행 적재했다.
- 별도 후보 CSV 25,240행 적재: DWT 후보 15,956척, 출처 간 5% 초과 충돌 137척을 상태로 보존. 파일 SHA256 f5b951b51992a70e8ce11a739a513fa1fbfafdcd5c84d90282ef74eaf256c01f.
- 지원 3선종에서 단일 승인 보고·양수 CO₂/추정거리/DWT·제원 충돌 제외 조건을 만족하는 참고 산술 범위는 **28,131보고 / 8,934척**. 이는 공식 CII 산정 가능 범위·독립 검증된 입력 수가 아니다.
- 실제 HTTP API 표본: REAL:IMO:7422881 / 2018, 보고 CO₂ 19545.24t, 후보 DWT 38997.0t, 추정거리 62541.32231404958677685950413nm → 참고값 8.013878 gCO₂/(DWT t·nm), status=estimated, 공식 등급 null. 기존 calculate는 동일 표본에서 blocked를 유지했다.
- annual_reports·vessels·synthetic_noon 전체 행의 정렬 JSON 지문과 건수가 참조 적재/조회 전후 동일했다. 후보 CSV 해시 불변. 임시 DB는 검증 종료 후 삭제했다.
- CLI help·문서 링크·diff 공백 확인 통과. 기존 커밋된 migration·의존성 잠금 파일은 변경하지 않았다.
- 이번 변경은 서버 API 범위다. frontend·화면/LLM 어댑터·브라우저 e2e·Docker 실행·실제 개인 DB 적용은 미수행이며 기존 결과를 새 성공 기록으로 대체하지 않았다.

## 2026-10-14 - MRV 참고 지표 PR 직전 전체 호환 점검

- 기준 upstream/main 196ad73108db를 다시 fetch해 변경이 없음을 확인했다. 작업 브랜치는 codex/mrv-reference-intensity이며 원격에 푸시하지 않았다.
- 팀 PR #11이 ADR 0012를 사용하므로 역할4 제안은 ADR 0013으로 번호·링크를 변경했다. 문서 삽입 위치를 조정한 뒤 PR #10(a6c29e4f)·#11(737c6314) 각각과 git merge-tree 충돌 0을 확인했다.
- 두 팀 PR 자체를 합칠 때 docs/README·architecture·changelog·plans/README의 기존 문서 충돌 4곳이 있다. 이 팀 간 문서는 임시 코드 테스트 사본에서만 양쪽 내용을 보존했으며 팀 브랜치·실제 작업 브랜치에 병합하지 않았다.
- 최종 자체 backend **174 passed, skipped 0**. 출처 5% 경계, SQL/비밀 오류 비노출, 참조 적재 중간 실패 전체 rollback, main 앱에서 새 경로 마운트 검증을 추가했다.
- 임시 사본의 역할4 + PR #10 + PR #11 코드 조합에서 **264 passed, skipped 0**. 같은 실자료 임시 DB와 새 migration을 사용했다. 두 실행 모두 기존 Starlette/httpx 경고 1개.
- frontend 단위 **4 passed**, production standalone build 성공. 실제 Next → FastAPI → PostgreSQL에서 기존 Chromium **1개 시나리오·16단계 통과**. Next 프록시를 통한 새 Bearer API 호출과 빈 데이터의 명시 blocked 응답도 통과했다.
- 실자료 참조 적재·원본 지문 불변·기존 calculate blocked 보존·참조 데이터 존재 시 down 거절을 재확인했다. 지원 선종/계산 범위는 앞선 검증과 같은 28,131보고·8,934척이다.
- 기존 migration 2개와 backend/frontend/e2e 잠금 파일 불변, 문서 링크·diff 공백 확인 통과. 개인 DB/원본 CSV 변경 없음. 소유 임시 DB와 서버/브라우저 프로세스 정리.
- Docker 실행 파일이 없어 컨테이너 e2e는 실행하지 않았다. 실제 production 프로세스 e2e로 확인했으며 컨테이너 이미지 검증 성공으로 기록하지 않는다. 외부 LLM 실호출·화면 자동 연결·공식 CII·실제 개인 DB 적용은 제외한다.
