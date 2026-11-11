"""Seed evaluation against explicitly prepared OpenSearch; no app DB/API/LLM."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import csv
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import statistics
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from api.rag_preprocessing import preprocess_sections
from api.rag_retrieval import retrieve
from api.rag_lexical import LexicalIndex, LexicalUnavailable, fingerprint


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed_digest(seed):
    """Pin JSON content, independent of checkout line endings or formatting."""
    canonical = json.dumps(seed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalized(value):
    return " ".join(value.split())


def load_inputs(seed_path, cases_path):
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    dataset = json.loads(cases_path.read_text(encoding="utf-8"))
    if (dataset.get("version") != 1 or dataset.get("seed_hash_format") != "canonical-json-v1"
            or dataset.get("seed_sha256") != seed_digest(seed)):
        raise ValueError("평가셋 버전 또는 원문 해시 불일치: 원문과 라벨을 함께 검토하세요.")
    corpus = []
    for doc in sorted(seed, key=lambda item: item["id"]):
        for position, chunk in enumerate(preprocess_sections(doc["sections"]), 1):
            corpus.append({**chunk, "id": f"{doc['id']}:{position}",
                           "document_id": doc["id"], "title": doc["title"],
                           "reference": doc["reference"], "kind": doc["kind"],
                           "url": doc.get("url"), "source_file": doc.get("file")})
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("비어 있지 않은 cases 목록이 필요합니다.")
    seen = set()
    for case in cases:
        if not isinstance(case.get("id"), str) or not case["id"] or case["id"] in seen:
            raise ValueError("중복 또는 잘못된 질문 ID")
        seen.add(case["id"])
        if not isinstance(case.get("question"), str) or not case["question"].strip():
            raise ValueError(f"빈 질문: {case['id']}")
        if case.get("category") not in ("answerable", "unanswerable"):
            raise ValueError(f"잘못된 질문 유형: {case['id']}")
        anchors = case.get("evidence")
        if not isinstance(anchors, list) or bool(anchors) != (case["category"] == "answerable"):
            raise ValueError(f"질문 유형과 근거 라벨 불일치: {case['id']}")
        if not isinstance(case.get("expected_behavior"), str) or not case["expected_behavior"].strip():
            raise ValueError(f"기대 동작 누락: {case['id']}")
        anchor_keys = set()
        for anchor in anchors:
            quote = anchor.get("quote")
            if not isinstance(quote, str) or len(normalized(quote)) < 12:
                raise ValueError(f"근거 인용이 너무 짧음: {case['id']}")
            key = (anchor.get("document_id"), normalized(quote))
            if key in anchor_keys:
                raise ValueError(f"중복 근거 라벨: {case['id']}")
            anchor_keys.add(key)
            if not any(matches(row, anchor) for row in corpus):
                raise ValueError(f"원문 청크에서 인용을 찾을 수 없음: {case['id']}")
    return dataset, corpus


def matches(row, anchor):
    return (row["document_id"] == anchor["document_id"]
            and (not anchor.get("heading_contains")
                 or anchor["heading_contains"] in row.get("heading", ""))
            and normalized(anchor["quote"]) in normalized(row["text"]))


def score_results(case, rows):
    """Macro evidence-unit recall; multiple chunks matching one quote count once."""
    if case["category"] == "unanswerable":
        return {"hit": None, "recall": None, "reciprocal_rank": None,
                "empty_results": not rows, "status": "candidate_review" if rows else "empty_results"}
    anchors = case["evidence"]
    found = sum(any(matches(row, anchor) for row in rows) for anchor in anchors)
    rank = next((i for i, row in enumerate(rows, 1)
                 if any(matches(row, anchor) for anchor in anchors)), None)
    return {"hit": bool(found), "recall": found / len(anchors),
            "reciprocal_rank": 1 / rank if rank else 0.0, "empty_results": None,
            "status": "complete" if found == len(anchors) else "partial" if found else "miss"}


def percentile(values, fraction):
    values = sorted(values)
    offset = (len(values) - 1) * fraction
    low = int(offset)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (offset - low)


def evaluate(cases, corpus, *, top_k=5, repeats=3, retriever=retrieve, progress=None):
    if type(top_k) is not int or top_k < 1 or type(repeats) is not int or repeats < 1:
        raise ValueError("top_k와 repeats는 양의 정수여야 합니다.")
    start = perf_counter()
    retriever(cases[0]["question"], corpus, top_k=top_k)
    first_call_ms = (perf_counter() - start) * 1000
    results, timings = [], []
    for case in cases:
        durations, signatures = [], []
        for _ in range(repeats):
            start = perf_counter()
            rows = retriever(case["question"], corpus, top_k=top_k)
            durations.append((perf_counter() - start) * 1000)
            signatures.append([(row["id"], row["score"]) for row in rows])
        if any(signature != signatures[0] for signature in signatures[1:]):
            raise ValueError(f"반복 검색 결과 불일치: {case['id']}")
        timings.extend(durations)
        results.append({**case, **score_results(case, rows),
                        "latency_ms": {"median": statistics.median(durations), "runs": durations},
                        "results": [{key: row.get(key) for key in
                                     ("id", "document_id", "heading", "page", "score", "kind", "url", "source_file")}
                                    for row in rows]})
        if progress is not None:
            progress(case["id"], results[-1]["status"])
    positive = [r for r in results if r["category"] == "answerable"]
    negative = [r for r in results if r["category"] == "unanswerable"]
    mean = lambda group, field: statistics.mean(r[field] for r in group) if group else None
    return {"top_k": top_k, "repeats": repeats, "corpus_chunks": len(corpus),
            "case_count": len(cases), "answerable_count": len(positive), "unanswerable_count": len(negative),
            "metrics": {"hit_rate_at_k": mean(positive, "hit"), "recall_at_k": mean(positive, "recall"),
                        "mrr_at_k": mean(positive, "reciprocal_rank"),
                        "unanswerable_empty_rate": mean(negative, "empty_results")},
            "latency_ms": {"first_retrieval_call": first_call_ms,
                           "warm_p50": statistics.median(timings), "warm_p95": percentile(timings, .95)},
            "cases": results}


def markdown(report):
    metrics = report["metrics"]
    fmt = lambda value: "N/A" if value is None else f"{value:.4f}"
    lines = ["# 해사 문서 검색 평가 결과", "", f"실행: {report['created_at']}",
             f"문서 청크 {report['corpus_chunks']}개 · 질문 {report['case_count']}개 · k={report['top_k']} · 반복 {report['repeats']}회", "",
             f"- Hit@k: {fmt(metrics['hit_rate_at_k'])}", f"- Recall@k: {fmt(metrics['recall_at_k'])}",
             f"- MRR@k: {fmt(metrics['mrr_at_k'])}",
             f"- 답 없음 질문의 빈 검색 결과 비율: {fmt(metrics['unanswerable_empty_rate'])}",
             f"- 첫 검색 {report['latency_ms']['first_retrieval_call']:.1f} ms / 반복 p50 {report['latency_ms']['warm_p50']:.1f} ms / p95 {report['latency_ms']['warm_p95']:.1f} ms", "",
             "검색 함수만 측정했습니다. DB·권한·API·LLM·답변 정확성·실제 선박 적용성 검증이 아닙니다.",
             "답 없는 질문의 검색 후보 노출은 환각이나 잘못된 최종 답변을 의미하지 않습니다.", "",
             "| ID | 질문 | 유형 | 결과 | Recall@k | 중앙 시간(ms) |", "|---|---|---|---|---|---|"]
    escape = lambda value: str(value).replace("|", "\\|").replace("\n", " ")
    for row in report["cases"]:
        lines.append(f"| {row['id']} | {escape(row['question'])} | {row['category']} | {row['status']} | {fmt(row['recall'])} | {row['latency_ms']['median']:.1f} |")
    lines += ["", "## 실패·부분 검색·답 없음 후보의 수동 검토", ""]
    for row in report["cases"]:
        if row["status"] not in ("miss", "partial", "candidate_review"):
            continue
        lines += [f"### {row['id']}: {row['question']}", "", row["expected_behavior"], ""]
        for anchor in row["evidence"]:
            lines.append(f"- 정답 근거 `{anchor['document_id']}`: {anchor['quote']}")
        for item in row["results"]:
            lines.append(f"- 검색 후보 `{item['id']}`: {item['heading']} (p.{item['page']})")
        lines.append("")
    lines += ["## 재현 환경", "", "```json", json.dumps(report["provenance"], ensure_ascii=False, indent=2), "```", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, default=ROOT / "backend/knowledge/seed.json")
    parser.add_argument("--cases", type=Path, default=ROOT / "backend/knowledge/evaluation/maritime-questions.json")
    parser.add_argument("--output", type=Path, default=ROOT / "output/retrieval-evaluation")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--index", help="Previously prepared evaluation index")
    parser.add_argument("--prepare", action="store_true", help="Explicitly create a NEW haedap-lexical-eval-* index")
    args = parser.parse_args(argv)
    if args.top_k < 1 or args.repeats < 1:
        parser.error("top-k와 repeats는 양의 정수여야 합니다.")
    if args.prepare and (not args.index or not args.index.startswith("haedap-lexical-eval-")):
        parser.error("--prepare requires a new --index haedap-lexical-eval-...")
    files = {"seed": args.seed, "cases": args.cases, "runner": Path(__file__),
             "preprocessing": ROOT / "backend/api/rag_preprocessing.py",
             "retrieval": ROOT / "backend/api/rag_retrieval.py", "vocabulary": ROOT / "backend/api/rag_vocabulary.py"}
    index = None
    try:
        hashes = {name: digest(path) for name, path in files.items()}
        dataset, corpus = load_inputs(args.seed, args.cases)
        retriever = retrieve
        if args.index:
            index = LexicalIndex(index=args.index)
            if args.prepare:
                if index.request("GET", f"/{index.name}/_mapping", missing=True):
                    raise ValueError("Use a new evaluation index to avoid mixing corpus statistics")
                index.create()
                index.index(corpus)
                index.verify(corpus, publish=True)
            retriever = index.search
        report = evaluate(dataset["cases"], corpus, top_k=args.top_k, repeats=args.repeats,
                          retriever=retriever,
                          progress=lambda id, status: print(f"{id}: {status}", file=sys.stderr, flush=True))
        if hashes != {name: digest(path) for name, path in files.items()}:
            raise ValueError("측정 중 평가 입력 또는 코드가 변경되었습니다. 다시 실행하세요.")
    except (ValueError, KeyError, TypeError, OSError, LexicalUnavailable) as exc:
        parser.error(str(exc))
    finally:
        if index is not None:
            index.close()
    report["created_at"] = datetime.now(timezone.utc).isoformat()
    report["provenance"] = {"python": platform.python_version(), "platform": platform.platform(),
                            "packages": {name: version(name) for name in ("httpx",)},
                            "lexical_fingerprint": fingerprint(), "index": args.index or "haedap-lexical",
                            "sha256": hashes,
                            "scope": "seed snapshot against a pre-indexed isolated OpenSearch; no authentication/API/LLM; author-labelled pilot"}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "results.md").write_text(markdown(report), encoding="utf-8")
    with (args.output / "results.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["id", "question", "category", "status", "hit", "recall", "reciprocal_rank", "median_ms", "result_ids"])
        for row in report["cases"]:
            writer.writerow([row[key] for key in ("id", "question", "category", "status", "hit", "recall", "reciprocal_rank")]
                            + [row["latency_ms"]["median"], ";".join(r["id"] for r in row["results"])])
    print(json.dumps({"metrics": report["metrics"], "latency_ms": report["latency_ms"],
                      "report": str(args.output / "results.md")}, ensure_ascii=False, indent=2))
    return 0  # A measured miss is a result, not a broken evaluator.


if __name__ == "__main__":
    raise SystemExit(main())
