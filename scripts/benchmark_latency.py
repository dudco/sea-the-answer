"""질문 응답 지연을 구간별로 측정한다. 원인을 찾기 위한 진단 도구이며 품질 평가가 아니다.

model  DB·검색 없이, 앱이 실제로 보내는 요청 본문(도구 선택 · 답변 생성)을 그대로 만들어
       스트리밍으로 다시 보낸다. 첫 토큰까지 시간, 추론(thinking)에 쓴 시간, 본문 생성 시간,
       토큰 수·초당 토큰을 나눠 잰다. 같은 요청에 reasoning_effort="none"만 더한 변형과 비교한다.
       Ollama이면 /api/ps로 모델의 GPU 적재 비율·문맥 길이도 확인한다.
api    실행 중인 서버에 로그인해 /api/ask를 호출하고, 응답에 이미 기록된
       routing.searchMs·planMs·toolCalls·timings.generationMs를 모아 전체 시간과 비교한다.

실행 위치: 저장소 최상위
  uv run --project backend python scripts/benchmark_latency.py model --repeats 3
  HAEDAP_BENCH_PASSWORD=... uv run --project backend python scripts/benchmark_latency.py api \
      --base-url http://127.0.0.1:5173 --username <계정> --repeats 2

model은 환경변수의 LLM 설정(LLM_API_BASE_URL, OPENAI_MODEL 등)을 그대로 쓴다. 이 스크립트는 .env를
읽지 않으므로 호스트에서 실행할 때는 먼저 `set -a; . ./.env; set +a`로 불러오고, .env의 주소가 컨테이너
기준(host.docker.internal)이면 `LLM_API_BASE_URL=http://127.0.0.1:11434/v1`로 덮어쓴다.
api는 질문마다 일반 질문과 같이 질의 이력·감사 기록을 남긴다. 비밀번호는 인자로 받지 않는다.
"""

from __future__ import annotations

import argparse
from contextlib import nullcontext
from datetime import date, datetime, timezone
import getpass
import json
import os
from pathlib import Path
import statistics
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

import httpx

from api import config, llm, tool_planner  # noqa: E402
from scripts import evaluate_llm as fixed  # noqa: E402
from scripts import evaluate_llm_load as load  # noqa: E402

DEFAULT_CASE = "sulphur-limits"
DEFAULT_QUESTIONS = (
    "황산화물 배출 규제 설명해줘",
    "CII 등급 산정 기준을 알려줘",
    "선박 현등의 색상과 위치를 알려줘",
    "MEPC 84차 회의에서 결정된 주요 내용은?",
    "등록된 선박 목록 보여줘",
)
KPI_P95_SECONDS = 15.0
KPI_TOKENS_PER_SECOND = 20.0


# ---------------------------------------------------------------- 공통 통계

def percentile(values, q):
    """Nearest-rank percentile; None for an empty list."""
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    rank = max(1, -(-len(values) * q // 100))  # ceil without float error
    return values[int(rank) - 1]


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def fmt(value, unit="s", digits=2):
    return "-" if value is None else f"{value:.{digits}f}{unit}"


# ---------------------------------------------------------------- model 모드

class _Captured(Exception):
    pass


class _Capture:
    """Stands in for httpx so the app builds its real request body, which we then replay."""

    def __init__(self):
        self.url = self.body = None
        self.headers = {}

    def post(self, url, *, json=None, headers=None, **_):
        self.url, self.body, self.headers = url, json, dict(headers or {})
        raise _Captured


def capture(build):
    target = _Capture()
    try:
        build(target)
    except _Captured:
        return target
    raise RuntimeError("앱 코드가 모델 요청을 보내지 않았습니다.")


def app_requests(settings, case_id=DEFAULT_CASE):
    """Exact planner and grounded-answer request bodies the app would send for one fixed case."""
    case = next(c for c in fixed.load_cases() if c["id"] == case_id)
    # Production retrieval passes top-5 chunks; use five real seed sections, not one.
    evidence = load.build_matrix([case], ["five"])[0]["evidence"]
    titles = [doc["title"] for doc in json.loads(fixed.DEFAULT_SEED.read_text(encoding="utf-8"))]
    planner = capture(lambda c: tool_planner.plan(case["question"], today=date.today(), documents=titles,
                                                  settings=settings, client=c))
    answer = capture(lambda c: llm.grounded_response(case["question"], evidence, "ko", settings, client=c))
    return {"planner": planner, "answer": answer}


def variants(body, names):
    out = {}
    for name in names:
        if name == "app":
            out[name] = body
        elif name == "no-think":
            out[name] = {**body, "reasoning_effort": "none"}
        else:
            raise ValueError(name)
    return out


def measure_stream(client, url, headers, body, timeout):
    """Replay one request with streaming; split time into first token, thinking and answer."""
    body = {**body, "stream": True, "stream_options": {"include_usage": True}}
    started = perf_counter()
    first = think_first = answer_first = None
    reasoning_chars = answer_chars = 0
    content, in_think, usage, finish = "", None, None, None
    with client.stream("POST", url, json=body, headers=headers,
                       timeout=httpx.Timeout(timeout, connect=5)) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            chunk = json.loads(data)
            usage = chunk.get("usage") or usage
            now = perf_counter() - started
            for choice in chunk.get("choices") or []:
                finish = choice.get("finish_reason") or finish
                delta = choice.get("delta") or {}
                reasoning = delta.get("reasoning") or delta.get("reasoning_content") or ""
                text = delta.get("content") or ""
                calls = json.dumps(delta["tool_calls"]) if delta.get("tool_calls") else ""
                if reasoning or text or calls:
                    first = now if first is None else first
                if reasoning:
                    think_first = now if think_first is None else think_first
                    reasoning_chars += len(reasoning)
                if text:
                    # Some Qwen templates inline <think>…</think> in content instead of a reasoning field.
                    content += text
                    if in_think is None:
                        stripped = content.lstrip()
                        if stripped.startswith("<think>"):
                            in_think = True
                            think_first = now if think_first is None else think_first
                        elif len(stripped) >= 7 or not "<think>".startswith(stripped):
                            in_think = False
                    if in_think:
                        if "</think>" in content:
                            in_think = False
                            head, tail = content.split("</think>", 1)
                            reasoning_chars += len(head)
                            content = tail
                            if tail.strip():
                                answer_first = now if answer_first is None else answer_first
                                answer_chars += len(tail)
                    elif in_think is False:
                        answer_first = now if answer_first is None else answer_first
                        answer_chars += len(text)
                if calls:
                    answer_first = now if answer_first is None else answer_first
                    answer_chars += len(calls)
    total = perf_counter() - started
    completion = (usage or {}).get("completion_tokens")
    decode_window = total - first if first is not None else None
    return {
        "total_s": round(total, 3),
        "first_token_s": None if first is None else round(first, 3),
        "thinking_s": None if think_first is None else round((answer_first or total) - think_first, 3),
        "answer_s": None if answer_first is None else round(total - answer_first, 3),
        "prompt_tokens": (usage or {}).get("prompt_tokens"),
        "completion_tokens": completion,
        "reasoning_chars": reasoning_chars, "answer_chars": answer_chars,
        "tokens_per_s": round(completion / decode_window, 1) if completion and decode_window else None,
        "finish_reason": finish,
    }


def ollama_root(base_url):
    base = base_url.rstrip("/")
    return base[:-3] if base.endswith("/v1") else None


def ollama_status(client, base_url):
    """Loaded models from Ollama /api/ps; None when the server is not Ollama."""
    root = ollama_root(base_url)
    if not root:
        return None
    try:
        response = client.get(root + "/api/ps", timeout=5)
        response.raise_for_status()
        models = response.json().get("models", [])
    except (httpx.HTTPError, ValueError):
        return None
    return [{"name": m.get("name"), "size_gb": round(m.get("size", 0) / 1e9, 1),
             "vram_gb": round(m.get("size_vram", 0) / 1e9, 1),
             "gpu_ratio": round(m["size_vram"] / m["size"], 2) if m.get("size") else None,
             "context_length": m.get("context_length"), "expires_at": m.get("expires_at")}
            for m in models]


def run_model(settings, *, repeats, names, timeout, client=None, case_id=DEFAULT_CASE, log=print):
    requests = app_requests(settings, case_id)
    client = client or httpx.Client(follow_redirects=False)
    report = {"mode": "model", "model": settings.model, "planner_model": requests["planner"].body.get("model"),
              "base_url_host": httpx.URL(settings.base_url).host,
              "ollama_before": ollama_status(client, settings.base_url), "runs": []}
    for stage in ("planner", "answer"):
        captured = requests[stage]
        for name, body in variants(captured.body, names).items():
            for run in range(1, repeats + 1):
                try:
                    row = measure_stream(client, captured.url, captured.headers, body, timeout)
                except (httpx.HTTPError, ValueError) as exc:
                    row = {"error": type(exc).__name__ if not isinstance(exc, httpx.HTTPStatusError)
                           else f"HTTP {exc.response.status_code}"}
                row.update(stage=stage, variant=name, run=run)
                report["runs"].append(row)
                log(f"  {stage:<7} {name:<8} #{run}  total={fmt(row.get('total_s'))} "
                    f"first={fmt(row.get('first_token_s'))} think={fmt(row.get('thinking_s'))} "
                    f"tok={row.get('completion_tokens', '-')} {row.get('error', '')}")
    report["ollama_after"] = ollama_status(client, settings.base_url)
    report["summary"] = summarize_model(report["runs"])
    report["findings"] = model_findings(report)
    return report


def summarize_model(runs):
    groups = {}
    for row in runs:
        if "error" not in row:
            groups.setdefault((row["stage"], row["variant"]), []).append(row)
    summary = []
    for (stage, variant), rows in groups.items():
        warm = rows[1:] or rows  # first call may include model load
        summary.append({"stage": stage, "variant": variant, "runs": len(rows),
                        "first_call_total_s": rows[0]["total_s"],
                        **{f"median_{k}": median([r[k] for r in warm]) for k in
                           ("total_s", "first_token_s", "thinking_s", "answer_s",
                            "prompt_tokens", "completion_tokens", "reasoning_chars", "tokens_per_s")}})
    return summary


def model_findings(report):
    found = []
    by = {(s["stage"], s["variant"]): s for s in report["summary"]}
    for snap in report.get("ollama_after") or report.get("ollama_before") or []:
        if snap["gpu_ratio"] is not None and snap["gpu_ratio"] < 0.98:
            found.append(f"{snap['name']}: 모델의 {round((1 - snap['gpu_ratio']) * 100)}%가 CPU 메모리에 있습니다 "
                         "(GPU에 다 올라가지 않음). 생성 속도가 크게 떨어지는 주원인일 수 있습니다.")
    loaded = {m["name"] for m in report.get("ollama_after") or []}
    if len(loaded) > 1:
        found.append(f"모델 {len(loaded)}개가 동시에 적재되어 있습니다: {sorted(loaded)}. "
                     "도구 선택용 모델을 따로 쓰면 VRAM 경쟁·교체가 생길 수 있습니다.")
    for stage in ("planner", "answer"):
        app, off = by.get((stage, "app")), by.get((stage, "no-think"))
        if app and app["median_reasoning_chars"]:
            msg = (f"{stage}: 현재 설정에서 추론(thinking)을 생성합니다 "
                   f"(중앙값 {app['median_reasoning_chars']:.0f}자, {fmt(app['median_thinking_s'])}).")
            if off:
                msg += f" reasoning_effort=none이면 {fmt(app['median_total_s'])} → {fmt(off['median_total_s'])}."
            found.append(msg)
        for row in (app, off):
            if row and row["first_call_total_s"] and row["median_total_s"] \
                    and row["first_call_total_s"] > 2 * row["median_total_s"] + 3:
                found.append(f"{stage}/{row['variant']}: 첫 호출 {fmt(row['first_call_total_s'])}이 이후 중앙값 "
                             f"{fmt(row['median_total_s'])}보다 훨씬 깁니다 — 모델 적재(콜드 스타트) 의심.")
            if row and row["median_tokens_per_s"] and row["median_tokens_per_s"] < KPI_TOKENS_PER_SECOND:
                found.append(f"{stage}/{row['variant']}: 생성 속도 {row['median_tokens_per_s']} tok/s "
                             f"< 목표 {KPI_TOKENS_PER_SECOND:.0f} tok/s.")
    return found


# ---------------------------------------------------------------- api 모드

def ask_breakdown(answer, wall):
    """Stage times the server already records on /api/ask responses (ADR 0024 routing)."""
    routing = answer.get("routing") if isinstance(answer.get("routing"), dict) else {}
    timings = answer.get("timings") if isinstance(answer.get("timings"), dict) else {}
    calls = routing.get("toolCalls") if isinstance(routing.get("toolCalls"), list) else []
    tool_ms = sum(c.get("durationMs") or 0 for c in calls
                  if isinstance(c, dict) and c.get("name") != "search_documents")
    sec = lambda ms: None if ms is None else round(ms / 1000, 3)  # noqa: E731
    # planMs runs from before the document lookup until both search and tool selection finish.
    known = [sec(routing.get("planMs")), sec(timings.get("generationMs")), sec(tool_ms) if tool_ms else None]
    return {"wall_s": round(wall, 3), "search_s": sec(routing.get("searchMs")),
            "search_and_plan_s": sec(routing.get("planMs")), "tool_s": sec(tool_ms) if tool_ms else None,
            "generation_s": sec(timings.get("generationMs")),
            "other_s": round(wall - sum(v for v in known if v), 3),
            "route": routing.get("method"), "tools": [c.get("name") for c in calls if isinstance(c, dict)],
            "generation": answer.get("generation"), "status": answer.get("status"),
            "warnings": answer.get("warnings", []),
            "failure": (answer.get("generationFailure") or {}).get("code") or routing.get("error")}


def login(client, username, password):
    health = client.get("/api/health")
    health.raise_for_status()
    token = health.json()["csrfToken"]
    response = client.post("/api/auth/login", json={"username": username, "password": password},
                           headers={"X-Haedap-Token": token})
    if response.status_code != 200:
        raise SystemExit(f"로그인 실패: HTTP {response.status_code} {response.json().get('code', '')}")
    user = response.json()["user"]
    if user.get("must_change_password"):
        raise SystemExit("비밀번호 변경이 필요한 계정입니다. 화면에서 먼저 변경하세요.")
    return {"X-Haedap-Token": token, "X-Haedap-Identity": user["id"]}


def run_api(base_url, username, password, questions, *, repeats, timeout, client=None, log=print):
    client = client or httpx.Client(base_url=base_url, follow_redirects=False)
    headers = login(client, username, password)
    rows = []
    for run in range(1, repeats + 1):
        for question in questions:
            started = perf_counter()
            try:
                response = client.post("/api/ask", json={"question": question, "language": "auto"},
                                       headers=headers, timeout=timeout)
                wall = perf_counter() - started
                body = response.json()
                row = ask_breakdown(body, wall) if response.status_code == 200 else \
                    {"wall_s": round(wall, 3), "error": f"HTTP {response.status_code} {body.get('code', '')}"}
            except (httpx.HTTPError, ValueError) as exc:
                row = {"wall_s": round(perf_counter() - started, 3), "error": type(exc).__name__}
            row.update(question=question, run=run)
            rows.append(row)
            log(f"  #{run} {fmt(row['wall_s']):>8}  검색+선택={fmt(row.get('search_and_plan_s'))} "
                f"생성={fmt(row.get('generation_s'))} 도구={fmt(row.get('tool_s'))} "
                f"기타={fmt(row.get('other_s'))}  {row.get('generation') or row.get('error', '')}  {question[:30]}")
    walls = [r["wall_s"] for r in rows if "error" not in r]
    summary = {"requests": len(rows), "errors": sum("error" in r for r in rows),
               "p50_s": percentile(walls, 50), "p95_s": percentile(walls, 95), "kpi_p95_s": KPI_P95_SECONDS,
               **{f"median_{k}": median([r.get(k) for r in rows if "error" not in r]) for k in
                  ("search_s", "search_and_plan_s", "generation_s", "tool_s", "other_s")},
               "fallbacks": sum("MODEL_FAILED_EXTRACTIVE_FALLBACK" in r.get("warnings", []) for r in rows),
               "budget_exhausted": sum("MODEL_TIME_BUDGET_EXHAUSTED" in r.get("warnings", []) for r in rows)}
    return {"mode": "api", "base_url_host": httpx.URL(base_url).host, "runs": rows, "summary": summary,
            "findings": api_findings(summary)}


def api_findings(s):
    found = []
    if s["p95_s"] is not None:
        verdict = "충족" if s["p95_s"] <= KPI_P95_SECONDS else "미달"
        found.append(f"전체 응답 P95 {fmt(s['p95_s'])} (목표 ≤ {KPI_P95_SECONDS:.0f}s, {verdict}).")
    parts = {"검색+도구 선택(병렬)": s["median_search_and_plan_s"], "답변 생성": s["median_generation_s"],
             "데이터 도구": s["median_tool_s"], "기타(DB 기록·프록시·네트워크)": s["median_other_s"]}
    known = {k: v for k, v in parts.items() if v}
    if known:
        name = max(known, key=known.get)
        found.append(f"가장 큰 구간: {name} (중앙값 {fmt(known[name])}).")
    if s["median_search_s"] and s["median_search_and_plan_s"] and \
            s["median_search_s"] >= 0.8 * s["median_search_and_plan_s"]:
        found.append("검색이 병렬 구간의 대부분을 차지합니다 — 도구 선택보다 검색이 늦습니다.")
    if s["fallbacks"] or s["budget_exhausted"]:
        found.append(f"모델 실패로 원문 발췌 대체 {s['fallbacks']}건, 시간 예산 소진 {s['budget_exhausted']}건 — "
                     "응답이 빨라 보여도 실제로는 생성 시간 초과일 수 있습니다.")
    return found


# ---------------------------------------------------------------- 출력

def print_report(report):
    print("\n== 요약 ==")
    if report["mode"] == "model":
        for snap in report.get("ollama_after") or []:
            print(f"  [Ollama] {snap['name']}: {snap['size_gb']}GB 중 GPU {snap['vram_gb']}GB "
                  f"(비율 {snap['gpu_ratio']}), context={snap['context_length']}")
        print(f"  {'구간':<8}{'변형':<10}{'첫호출':>8}{'중앙값':>8}{'첫토큰':>8}{'추론':>8}{'본문':>8}"
              f"{'입력tok':>8}{'출력tok':>8}{'tok/s':>7}")
        for s in report["summary"]:
            print(f"  {s['stage']:<8}{s['variant']:<10}{fmt(s['first_call_total_s']):>8}"
                  f"{fmt(s['median_total_s']):>8}{fmt(s['median_first_token_s']):>8}"
                  f"{fmt(s['median_thinking_s']):>8}{fmt(s['median_answer_s']):>8}"
                  f"{fmt(s['median_prompt_tokens'], '', 0):>8}{fmt(s['median_completion_tokens'], '', 0):>8}"
                  f"{fmt(s['median_tokens_per_s'], '', 1):>7}")
    else:
        s = report["summary"]
        print(f"  요청 {s['requests']}건 (오류 {s['errors']}) · P50 {fmt(s['p50_s'])} · P95 {fmt(s['p95_s'])}")
        print(f"  중앙값: 검색 {fmt(s['median_search_s'])} · 검색+도구선택 {fmt(s['median_search_and_plan_s'])} · "
              f"생성 {fmt(s['median_generation_s'])} · 도구 {fmt(s['median_tool_s'])} · 기타 {fmt(s['median_other_s'])}")
    print("\n== 판단 근거 ==")
    for line in report["findings"] or ["자동으로 판단할 이상 신호는 없습니다. 위 표의 구간별 시간을 비교하세요."]:
        print("  - " + line)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)
    m = sub.add_parser("model", help="모델 호출만 측정 (DB·검색 없음)")
    m.add_argument("--repeats", type=int, default=3)
    m.add_argument("--variant", action="append", choices=("app", "no-think"),
                   help="기본: app과 no-think 둘 다")
    m.add_argument("--case", default=DEFAULT_CASE)
    m.add_argument("--timeout", type=float, default=180)
    a = sub.add_parser("api", help="실행 중인 서버의 /api/ask 전체 측정")
    a.add_argument("--base-url", default="http://127.0.0.1:5173")
    a.add_argument("--username", required=True)
    a.add_argument("--question", action="append", help="여러 번 지정 가능. 기본: 내장 5문항")
    a.add_argument("--questions-file", type=Path, help="한 줄에 질문 하나")
    a.add_argument("--repeats", type=int, default=2)
    a.add_argument("--timeout", type=float, default=180)
    for p in (m, a):
        p.add_argument("--output", type=Path, help="결과 JSON을 새 파일로 저장 (덮어쓰지 않음)")
    args = parser.parse_args(argv)
    if args.output is not None and args.output.exists():
        parser.error("출력 파일이 이미 있습니다.")
    started_at = datetime.now(timezone.utc).isoformat()
    if args.mode == "model":
        settings = config.llm_settings()
        if settings is None:
            parser.error("모델 설정이 없거나 잘못되었습니다 (.env의 LLM_API_BASE_URL·OPENAI_MODEL 확인).")
        print(f"모델 {settings.model} @ {httpx.URL(settings.base_url).host} — 구간별 {args.repeats}회")
        report = run_model(settings, repeats=args.repeats, names=args.variant or ["app", "no-think"],
                           timeout=args.timeout, case_id=args.case)
    else:
        questions = list(args.question or [])
        if args.questions_file:
            questions += [q.strip() for q in args.questions_file.read_text(encoding="utf-8").splitlines() if q.strip()]
        password = os.getenv("HAEDAP_BENCH_PASSWORD") or getpass.getpass("비밀번호: ")
        print(f"{args.base_url} /api/ask — 질문 {len(questions or DEFAULT_QUESTIONS)}개 × {args.repeats}회")
        report = run_api(args.base_url, args.username, password, questions or list(DEFAULT_QUESTIONS),
                         repeats=args.repeats, timeout=args.timeout)
    report["started_at"] = started_at
    print_report(report)
    with (args.output.open("x", encoding="utf-8") if args.output else nullcontext()) as stream:
        if stream:
            stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(f"\n저장: {args.output}")
    return 0


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    raise SystemExit(main())
