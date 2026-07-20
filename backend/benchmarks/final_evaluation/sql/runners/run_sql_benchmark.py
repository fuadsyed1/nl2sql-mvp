"""
Final NL-to-SQL benchmark runner (resumable, sequential).

    python -m benchmarks.final_evaluation.sql.runners.run_sql_benchmark \
        [--category having] [--database-id 46] [--limit 20]
        [--start-index 0] [--resume] [--output-prefix smoke]
        [--timeout 300] [--max-retries 1] [--smoke-per-category 2]

Sequential by design (MindRouter rate limits). Results are appended to a
JSONL file after EVERY case, so an interrupted run resumes with --resume
(completed case_ids are skipped). Reports are regenerated from the results
file at the end of every invocation.
"""

import argparse
import json
import os
import time
import urllib.error
import urllib.request

from benchmarks.final_evaluation.common import manifest as mf
from benchmarks.final_evaluation.common import scoring

BASE = os.path.join(os.path.dirname(__file__), "..", "..")
MAN_DIR = os.path.join(BASE, "sql", "manifests")
REF_DIR = os.path.join(BASE, "sql", "references")
RES_DIR = os.path.join(BASE, "sql", "results")
REP_DIR = os.path.join(BASE, "sql", "reports")
BASE_URL = os.environ.get("SPIDERSQL_URL", "http://127.0.0.1:8000")


def post_question(database_id, question, timeout):
    url = f"{BASE_URL}/database/{database_id}/execute_sql"
    payload = json.dumps({"question": question}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"},
        method="POST")
    started = time.time()
    timed_out = False
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        data = {"success": False,
                "_error": exc.read().decode("utf-8", errors="replace")}
    except Exception as exc:
        timed_out = "timed out" in str(exc).lower()
        data = {"success": False, "_error": repr(exc)}
    return data, round(time.time() - started, 2), timed_out


def load_benchmark(categories):
    cases, refs = [], {}
    for cat in categories:
        cases.extend(mf.read_jsonl(os.path.join(MAN_DIR, f"{cat}.jsonl")))
        for r in mf.read_jsonl(os.path.join(REF_DIR, f"{cat}_refs.jsonl")):
            refs[r["case_id"]] = r
    return cases, refs


def record_for(case, response, elapsed, timed_out, verdict, detail):
    execution = (response or {}).get("execution") or {}
    gen = (response or {}).get("generated_sql") or {}
    return {
        "case_id": case["case_id"], "category": case["category"],
        "difficulty": case["difficulty"],
        "database_id": case["database_id"], "question": case["question"],
        "success": bool((response or {}).get("success")),
        "generated_sql": gen.get("sql") if isinstance(gen, dict) else gen,
        "selected_candidate_source":
            (response or {}).get("selected_candidate_source"),
        "row_count": execution.get("row_count"),
        "expected_row_count": case.get("expected_row_count"),
        "verdict": verdict, "verdict_detail": detail,
        "controlled_failure": verdict == "controlled_failure",
        "fatal_reasons": ((response or {})
                          .get("selected_candidate_validation") or {}
                          ).get("fatal") or [],
        "candidate_fatal_reasons":
            (response or {}).get("candidate_fatal_reasons"),
        "warnings": (response or {}).get("warnings") or [],
        "repair_selected": bool((response or {}).get("repair_selected")),
        "repair_attempted": bool((response or {}).get("repair_attempted")),
        "latency_s": elapsed, "timed_out": timed_out,
        "error_type": (response or {}).get("error"),
    }


def write_reports(records, prefix):
    import collections
    import csv
    os.makedirs(REP_DIR, exist_ok=True)

    def _csv(name, header, rows):
        with open(os.path.join(REP_DIR, f"{prefix}_{name}.csv"), "w",
                  newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)

    flat_header = ["case_id", "category", "difficulty", "database_id",
                   "verdict", "success", "latency_s", "row_count",
                   "expected_row_count", "selected_candidate_source",
                   "repair_selected", "error_type"]
    _csv("results_flat", flat_header,
         [[r.get(k) for k in flat_header] for r in records])

    def _summary(key):
        agg = collections.defaultdict(lambda: collections.Counter())
        lat = collections.defaultdict(list)
        for r in records:
            agg[r[key]][r["verdict"]] += 1
            lat[r[key]].append(r["latency_s"])
        rows = []
        for k in sorted(agg, key=str):
            c = agg[k]
            total = sum(c.values())
            correct = c.get("correct", 0)
            rows.append([k, total, correct,
                         c.get("wrong_result", 0) + c.get("wrong_columns", 0),
                         c.get("controlled_failure", 0),
                         c.get("execution_error", 0), c.get("timeout", 0),
                         f"{correct / total:.3f}" if total else "0",
                         f"{sum(lat[k]) / len(lat[k]):.1f}" if lat[k] else "0"])
        return rows

    header = ["key", "total", "correct", "wrong", "controlled_failure",
              "error", "timeout", "strict_accuracy", "avg_latency_s"]
    _csv("category_summary", header, _summary("category"))
    _csv("difficulty_summary", header, _summary("difficulty"))
    _csv("database_summary", header, _summary("database_id"))

    err = collections.Counter(r["verdict"] for r in records)
    _csv("error_taxonomy", ["verdict", "count"], sorted(err.items()))
    lat_rows = [[r["case_id"], r["latency_s"]] for r in records]
    _csv("latency", ["case_id", "latency_s"], lat_rows)
    cf = [[r["case_id"], r["category"], "; ".join(r["fatal_reasons"])[:400]]
          for r in records if r["verdict"] == "controlled_failure"]
    _csv("controlled_failures", ["case_id", "category", "fatal_reasons"], cf)

    src = collections.defaultdict(lambda: collections.Counter())
    for r in records:
        src[r.get("selected_candidate_source") or "-"][r["verdict"]] += 1
    _csv("candidate_source_summary", ["source", "correct", "total"],
         [[s, c.get("correct", 0), sum(c.values())]
          for s, c in sorted(src.items())])

    total = len(records)
    correct = sum(1 for r in records if r["verdict"] == "correct")
    ctrl = sum(1 for r in records if r["verdict"] == "controlled_failure")
    lines = [
        "FINAL SQL BENCHMARK REPORT",
        f"cases run: {total}",
        f"correct: {correct}  ({correct / total:.1%})" if total else "",
        f"controlled failures: {ctrl}",
        f"safety accuracy ((correct+controlled)/all): "
        f"{(correct + ctrl) / total:.1%}" if total else "",
        "",
        "| Category | Total | Correct | Wrong | Controlled Failure | "
        "Error | Timeout | Strict Accuracy | Average Latency |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in _summary("category"):
        lines.append("| " + " | ".join(str(x) for x in row) + " |")
    with open(os.path.join(REP_DIR, f"{prefix}_report.txt"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(REP_DIR, f"{prefix}_results.json"), "w",
              encoding="utf-8") as f:
        json.dump(records, f, indent=1, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", action="append", default=None)
    ap.add_argument("--database-id", type=int, default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--start-index", type=int, default=0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--output-prefix", default="full")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--max-retries", type=int, default=1)
    ap.add_argument("--smoke-per-category", type=int, default=None,
                    help="run only the first N cases of each category")
    args = ap.parse_args()

    categories = args.category or list(mf.SQL_CATEGORIES)
    cases, refs = load_benchmark(categories)
    if args.database_id:
        cases = [c for c in cases if c["database_id"] == args.database_id]
    if args.smoke_per_category:
        import collections
        seen = collections.Counter()
        picked = []
        for c in cases:
            if seen[c["category"]] < args.smoke_per_category:
                picked.append(c)
                seen[c["category"]] += 1
        cases = picked
    cases = cases[args.start_index:]
    if args.limit:
        cases = cases[:args.limit]

    os.makedirs(RES_DIR, exist_ok=True)
    out_path = os.path.join(RES_DIR, f"{args.output_prefix}_results.jsonl")
    done = set()
    records = []
    if args.resume and os.path.exists(out_path):
        records = mf.read_jsonl(out_path)
        done = {r["case_id"] for r in records}
        print(f"resume: {len(done)} cases already completed")
    elif os.path.exists(out_path) and not args.resume:
        raise SystemExit(f"{out_path} exists; use --resume or a new "
                         f"--output-prefix (previous results are never "
                         f"overwritten)")

    with open(out_path, "a", encoding="utf-8") as out:
        for i, case in enumerate(cases):
            if case["case_id"] in done:
                continue
            response, elapsed, timed_out = None, 0.0, False
            for attempt in range(args.max_retries + 1):
                response, elapsed, timed_out = post_question(
                    case["database_id"], case["question"], args.timeout)
                if response.get("success") is not None and \
                        "_error" not in response:
                    break
                time.sleep(2 * (attempt + 1))
            verdict, detail = scoring.classify(
                case, response, refs.get(case["case_id"]),
                timeout_hit=timed_out,
                tolerance=case.get("numeric_tolerance",
                                   scoring.DEFAULT_TOLERANCE))
            rec = record_for(case, response, elapsed, timed_out, verdict,
                             detail)
            records.append(rec)
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            print(f"[{i + 1}/{len(cases)}] {case['case_id']}: {verdict} "
                  f"({elapsed}s)", flush=True)

    write_reports(records, args.output_prefix)
    print(f"done: {len(records)} results -> {out_path}")


if __name__ == "__main__":
    main()
