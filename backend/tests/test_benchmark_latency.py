"""Latency benchmark checks; every model and API response is mocked, never a real call."""

import json

import httpx

from api import config
from scripts import benchmark_latency as bench

SETTINGS = config.LLMSettings("http://ollama.test:11434/v1", "qwen-mock", "", "json_schema")


def sse(*chunks):
    lines = [f"data: {json.dumps(c, ensure_ascii=False)}" for c in chunks] + ["data: [DONE]"]
    return httpx.Response(200, text="\n\n".join(lines) + "\n\n", headers={"content-type": "text/event-stream"})


def delta(**fields):
    return {"choices": [{"delta": fields, "finish_reason": None}]}


def test_app_requests_are_the_real_planner_and_answer_bodies():
    captured = bench.app_requests(SETTINGS)
    planner, answer = captured["planner"].body, captured["answer"].body
    assert captured["planner"].url == captured["answer"].url == "http://ollama.test:11434/v1/chat/completions"
    assert planner["model"] == "qwen-mock" and planner["stream"] is False
    assert "documents" in json.loads(planner["messages"][1]["content"])
    payload = json.loads(answer["messages"][1]["content"])
    assert len(payload["evidence"]) == 5  # production top-5, not the single labelled source
    assert answer["response_format"]["type"] == "json_schema"
    # The answer call carries no thinking control today; the benchmark variant adds it explicitly.
    assert "reasoning_effort" not in answer
    assert bench.variants(answer, ["no-think"])["no-think"]["reasoning_effort"] == "none"


def test_stream_separates_reasoning_field_from_answer():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return sse(delta(reasoning="생각"), delta(reasoning="중"), delta(content='{"a":'), delta(content="1}"),
                   {"choices": [], "usage": {"prompt_tokens": 900, "completion_tokens": 40}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    row = bench.measure_stream(client, "http://x/v1/chat/completions", {}, {"model": "m", "stream": False}, 5)
    assert seen[0]["stream"] is True and seen[0]["stream_options"] == {"include_usage": True}
    assert row["reasoning_chars"] == 3 and row["answer_chars"] == len('{"a":1}')
    assert row["thinking_s"] is not None and row["answer_s"] is not None
    assert row["prompt_tokens"] == 900 and row["completion_tokens"] == 40


def test_stream_detects_inline_think_tags_split_across_chunks():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: sse(
        delta(content="<thi"), delta(content="nk>abc</th"), delta(content="ink>{}"))))
    row = bench.measure_stream(client, "http://x", {}, {}, 5)
    assert row["reasoning_chars"] == len("<think>abc")
    assert row["answer_chars"] == 2 and row["thinking_s"] is not None


def test_stream_counts_tool_call_deltas_as_answer_without_thinking():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: sse(
        delta(tool_calls=[{"function": {"name": "list_vessels", "arguments": "{}"}}]))))
    row = bench.measure_stream(client, "http://x", {}, {}, 5)
    assert row["reasoning_chars"] == 0 and row["thinking_s"] is None and row["answer_chars"] > 0


def test_ollama_status_reports_cpu_offload():
    def handler(request):
        assert request.url.path == "/api/ps"
        return httpx.Response(200, json={"models": [{"name": "qwen3.6:35b", "size": 30e9, "size_vram": 24e9,
                                                     "context_length": 8192}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    [snap] = bench.ollama_status(client, "http://gpu.test:11434/v1")
    assert snap["gpu_ratio"] == 0.8 and snap["context_length"] == 8192
    assert bench.ollama_status(client, "https://api.openai.example/api") is None
    report = {"summary": [], "ollama_after": [snap]}
    assert any("CPU" in line for line in bench.model_findings(report))


def test_run_model_flags_thinking_and_compares_variant(monkeypatch):
    def handler(request):
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": []})
        body = json.loads(request.content)
        thinking = [] if body.get("reasoning_effort") == "none" else [delta(reasoning="x" * 500)]
        return sse(*thinking, delta(content="{}"), {"choices": [], "usage": {"completion_tokens": 10}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    report = bench.run_model(SETTINGS, repeats=2, names=["app", "no-think"], timeout=5, client=client,
                             log=lambda *_: None)
    assert len(report["runs"]) == 2 * 2 * 2 and not any("error" in r for r in report["runs"])
    by = {(s["stage"], s["variant"]): s for s in report["summary"]}
    assert by[("answer", "app")]["median_reasoning_chars"] == 500
    assert by[("answer", "no-think")]["median_reasoning_chars"] == 0
    assert any(line.startswith("answer: 현재 설정에서 추론") for line in report["findings"])


def test_percentile_is_nearest_rank():
    values = list(range(1, 21))
    assert bench.percentile(values, 95) == 19
    assert bench.percentile(values, 50) == 10
    assert bench.percentile([], 95) is None


def test_ask_breakdown_uses_recorded_server_timings():
    answer = {"generation": "llm", "status": "evidence_found", "warnings": [],
              "routing": {"method": "model_tools", "searchMs": 800, "planMs": 1500,
                          "toolCalls": [{"name": "search_documents", "durationMs": 800}]},
              "timings": {"generationMs": 9000}}
    row = bench.ask_breakdown(answer, 11.0)
    assert row["search_and_plan_s"] == 1.5 and row["generation_s"] == 9.0 and row["tool_s"] is None
    assert row["other_s"] == 0.5 and row["tools"] == ["search_documents"]


def test_run_api_logs_in_and_summarizes_against_kpi():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path, dict(request.headers)))
        if request.url.path == "/api/health":
            return httpx.Response(200, json={"csrfToken": "tok"})
        if request.url.path == "/api/auth/login":
            assert json.loads(request.content) == {"username": "crew", "password": "pw"}
            return httpx.Response(200, json={"user": {"id": "u1"}})
        return httpx.Response(200, json={"generation": "extractive", "warnings": ["MODEL_FAILED_EXTRACTIVE_FALLBACK"],
                                         "routing": {"planMs": 1000, "searchMs": 900}, "timings": {"generationMs": 60000}})

    client = httpx.Client(base_url="http://app.test", transport=httpx.MockTransport(handler))
    report = bench.run_api("http://app.test", "crew", "pw", ["q1", "q2"], repeats=1, timeout=5,
                           client=client, log=lambda *_: None)
    ask = [h for m, p, h in calls if p == "/api/ask"]
    assert len(ask) == 2 and all(h["x-haedap-token"] == "tok" and h["x-haedap-identity"] == "u1" for h in ask)
    assert report["summary"]["fallbacks"] == 2
    text = " ".join(report["findings"])
    assert "답변 생성" in text and "발췌 대체 2건" in text
    assert "pw" not in json.dumps(report)
