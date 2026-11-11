"""Measure which tool the configured model picks for fixed questions (ADR 0024).

No database access and no tool execution: only the planner call is made.
Results are a technical match against expected tool names and argument
subsets, not a semantic grade. Mock-model test runs are not model accuracy.

Example (from the repository root, with LLM_* / OPENAI_MODEL set):
  cd backend && uv run python ../scripts/evaluate_tool_selection.py --output ../output/tool-eval.json
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend" if (ROOT / "backend/api").is_dir() else ROOT
sys.path.insert(0, str(BACKEND))

import httpx

from api import config, llm, tool_planner

DEFAULT_CASES = Path(__file__).resolve().parent / "fixtures/tool-selection-eval.json"
TODAY = "2026-11-12"
# Titles a crew account might be able to read; only titles are ever sent to the planner.
DOCUMENTS = ["선박 안전 문서", "MARPOL 부속서 VI 요약", "평형수 관리 지침", "IMO DCS·CII 안내"]


def load_cases(path: Path = DEFAULT_CASES) -> list[dict]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    ids = [c.get("id") for c in cases] if isinstance(cases, list) else []
    if not cases or len(set(ids)) != len(ids) or not all(isinstance(c.get("expected"), dict) for c in cases):
        raise ValueError("Invalid tool selection cases")
    return cases


def contains(actual, expected) -> bool:
    """Expected values are a subset: lists by membership, dicts by key, strings by containment."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(contains(actual.get(k), v) for k, v in expected.items())
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        return all(any(contains(a, e) for a in actual) for e in expected)
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.replace(" ", "") in actual.replace(" ", "")
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)) and not isinstance(expected, bool):
        return abs(actual - expected) < 1e-9
    return actual == expected


def score(case: dict, calls: list) -> dict:
    expected = case["expected"]
    names = [c.tool.name for c in calls]
    tool_ok = names == [] if not expected["tools"] else len(names) == 1 and names[0] in expected["tools"]
    args_ok = tool_ok and (not names or contains(calls[0].args.model_dump(mode="json"), expected.get("args", {})))
    return {"tools": names, "arguments": [c.args.model_dump(mode="json") for c in calls],
            "tool_match": tool_ok, "argument_match": args_ok}


def evaluate(cases: list[dict], *, settings: config.LLMSettings, client=None, fmt: str | None = None) -> dict:
    rows = []
    for case in cases:
        started = perf_counter()
        row = {"id": case["id"], "question": case["question"], "expected": case["expected"]}
        debug = {}
        try:
            calls = tool_planner.plan(case["question"], today=TODAY, summary=case.get("previous"),
                                      documents=case.get("documents", DOCUMENTS), settings=settings,
                                      client=client, debug=debug, fmt=fmt)
            row.update(score(case, calls), error=None, text_preview=debug.get("text_preview") or None)
        except tool_planner.PlanError as exc:
            row.update(tools=None, tool_match=False, argument_match=False, error=exc.code,
                       finish_reason=exc.detail if isinstance(exc.detail, str) else None)
        except httpx.HTTPError as exc:
            row.update(tools=None, tool_match=False, argument_match=False, error=llm.failure_details(exc)["code"])
        row["seconds"] = round(perf_counter() - started, 3)
        rows.append(row)
    total = len(rows)
    seconds = sorted(r["seconds"] for r in rows)
    return {"model": settings.model, "format": tool_planner.planner_format(fmt), "cases": total,
            "tool_match": sum(r["tool_match"] for r in rows), "argument_match": sum(r["argument_match"] for r in rows),
            "errors": sum(r["error"] is not None for r in rows),
            "median_seconds": seconds[total // 2] if total else None, "max_seconds": seconds[-1] if total else None,
            "rows": rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", action="append", dest="case_ids", default=[])
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, help="Create a new UTF-8 JSON file; never overwrite")
    parser.add_argument("--format", choices=("tools", "json"), help="Override HAEDAP_PLANNER_FORMAT")
    args = parser.parse_args(argv)
    settings = config.llm_settings()
    if settings is None:
        print("Model is not configured (OPENAI_MODEL / LLM_API_BASE_URL).", file=sys.stderr)
        return 2
    cases = [c for c in load_cases(args.cases) if not args.case_ids or c["id"] in args.case_ids]
    result = {"evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **evaluate(cases, settings=settings, fmt=args.format)}
    print(f"{result['model']} [{result['format']}, {args.cases.name}]: tool {result['tool_match']}/{result['cases']}, arguments {result['argument_match']}/{result['cases']}, "
          f"errors {result['errors']}, median {result['median_seconds']}s")
    for row in result["rows"]:
        if not row["argument_match"]:
            reason = f" (finish_reason={row['finish_reason']})" if row.get('finish_reason') else ''
            text = f" text={row['text_preview']!r}" if row.get('text_preview') else ''
            if row.get('tools') and row.get('tool_match'):
                text += f" arguments={json.dumps(row['arguments'][0], ensure_ascii=False)}"
            print(f"  - {row['id']}: got {row['tools']} {row.get('error') or ''}{reason}{text}")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
