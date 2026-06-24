#!/usr/bin/env python3
"""
run_petshop_benchmark.py — Phase 9, step 2.

Executes the PetShop benchmark questions against the live SpiderSQL pipeline
(POST /database/{id}/execute_sql), grades each result structurally, prints
per-question and category/overall summaries, and saves a timestamped JSON
result file under benchmarks/results/.

Standard library only (urllib for HTTP). It changes no application code.

Usage:
    python benchmarks/run_petshop_benchmark.py
    python benchmarks/run_petshop_benchmark.py --database-id 1
    python benchmarks/run_petshop_benchmark.py --base-url http://localhost:8000
"""

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BENCHMARK_FILE = SCRIPT_DIR / "benchmark_queries_petshop.json"
RESULTS_DIR = SCRIPT_DIR / "results"
FAILURE_CATEGORY = "failure/edge cases"


# ---------------------------------------------------------------------------
# HTTP (stdlib)
# ---------------------------------------------------------------------------
def post_execute_sql(base_url, database_id, question, timeout):
    """POST one question; return the parsed JSON response or an {_error} dict."""
    url = f"{base_url.rstrip('/')}/database/{database_id}/execute_sql"
    payload = json.dumps({"question": question}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
        return json.loads(body)
    except urllib.error.HTTPError as exc:
        return {"_error": f"HTTP {exc.code}: {exc.reason}"}
    except urllib.error.URLError as exc:
        return {"_error": f"connection error: {exc.reason}"}
    except (ValueError, TimeoutError) as exc:
        return {"_error": f"bad/empty response: {exc}"}
    except Exception as exc:  # never let one request abort the run
        return {"_error": f"unexpected: {exc}"}


# ---------------------------------------------------------------------------
# Grading (pure function — structural)
# ---------------------------------------------------------------------------
def _lower_set(values):
    return {str(v).strip().lower() for v in (values or [])}


def _flatten_rows(rows):
    parts = []
    for row in rows or []:
        cells = row if isinstance(row, list) else [row]
        parts.extend(str(c) for c in cells)
    return " ".join(parts)


def grade(item, response):
    """Return (passed: bool, reasons: list[str], details: dict)."""
    if isinstance(response, dict) and "_error" in response:
        return False, [f"request error: {response['_error']}"], {"request_error": response["_error"]}

    is_failure = item["category"] == FAILURE_CATEGORY

    validation = response.get("validation") or {}
    plan_raw = response.get("plan")          # may be None (e.g. validation failed)
    gsql_raw = response.get("generated_sql")  # may be None
    plan = plan_raw or {}
    gsql = gsql_raw or {}
    ir = response.get("ir") or {}
    execution = response.get("execution")     # may be None (meaningful)

    # --- failure / edge cases: the pipeline must DECLINE ---
    if is_failure:
        v_false = validation.get("valid") is False
        p_false = (plan_raw is not None) and (plan.get("resolved") is False)
        g_false = (gsql_raw is not None) and (gsql.get("generated") is False)
        declined = v_false or p_false or g_false
        exec_ok = (execution is None) or (execution.get("executed") is False)

        reasons = []
        if not declined:
            reasons.append("expected a decline (invalid IR / unresolved plan / no SQL), but pipeline produced output")
        if not exec_ok:
            reasons.append("execution should be null or executed=false for a failure case")

        details = {
            "mode": "failure_case",
            "validation_valid": validation.get("valid"),
            "plan_resolved": plan.get("resolved") if plan_raw is not None else None,
            "generated": gsql.get("generated") if gsql_raw is not None else None,
            "execution_executed": None if execution is None else execution.get("executed"),
            "declined": declined,
        }
        return (declined and exec_ok), reasons, details

    # --- non-failure: full structural checks ---
    valid = validation.get("valid") is True
    resolved = plan.get("resolved") is True
    generated = gsql.get("generated") is True
    executed = bool(execution) and execution.get("executed") is True

    tables_used = _lower_set(plan.get("tables_used")) | _lower_set(ir.get("tables"))
    exp_tables = _lower_set(item["expected_tables"])
    bridges = _lower_set(plan.get("bridge_tables"))
    exp_bridges = _lower_set(item["expected_bridge_tables"])

    sql = gsql.get("sql") or ""
    missing_sql = [s for s in item["expected_sql_contains"] if s not in sql]

    # Optional: expected_sql_any_of is a list of ALTERNATIVE fragment groups.
    # Each group is a list of substrings that must ALL appear; the check passes
    # if ANY one group matches. Absent -> no constraint (backward compatible).
    any_of = item.get("expected_sql_any_of")
    if any_of:
        any_of_ok = any(all(frag in sql for frag in group) for group in any_of)
    else:
        any_of_ok = True

    params = gsql.get("params")
    params_match = (params == item["expected_params"])

    flat = _flatten_rows((execution or {}).get("rows"))
    missing_results = [v for v in item["expected_result_contains"] if str(v) not in flat]

    checks = {
        "validation_valid": valid,
        "plan_resolved": resolved,
        "generated": generated,
        "executed": executed,
        "expected_tables_present": exp_tables.issubset(tables_used),
        "expected_bridge_present": exp_bridges.issubset(bridges),
        "sql_contains": len(missing_sql) == 0,
        "sql_any_of": any_of_ok,
        "params_match": params_match,
        "result_contains": len(missing_results) == 0,
    }
    passed = all(checks.values())

    reasons = []
    if not valid:
        reasons.append("validation.valid != true")
    if not resolved:
        reasons.append("plan.resolved != true")
    if not generated:
        reasons.append("generated_sql.generated != true")
    if not executed:
        reasons.append("execution.executed != true")
    if not checks["expected_tables_present"]:
        reasons.append(f"missing expected_tables {sorted(exp_tables - tables_used)}")
    if not checks["expected_bridge_present"]:
        reasons.append(f"missing expected_bridge_tables {sorted(exp_bridges - bridges)}")
    if missing_sql:
        reasons.append(f"sql missing fragments {missing_sql}")
    if not any_of_ok:
        reasons.append(f"sql matched none of the expected_sql_any_of alternatives")
    if not params_match:
        reasons.append(f"params {params} != expected {item['expected_params']}")
    if missing_results:
        reasons.append(f"results missing {missing_results}")

    details = {
        "mode": "normal_case",
        "checks": checks,
        "sql": sql,
        "params": params,
        "tables_used": sorted(tables_used),
        "bridge_tables": sorted(bridges),
    }
    return passed, reasons, details


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
def run(base_url, database_id, timeout):
    data = json.loads(BENCHMARK_FILE.read_text(encoding="utf-8"))
    items = data["queries"]

    per_question = []
    cat_passed = defaultdict(int)
    cat_total = defaultdict(int)
    total_latency_ms = 0.0

    print(f"Running {len(items)} PetShop benchmarks against "
          f"{base_url} (database_id={database_id})\n")

    for item in items:
        start = time.perf_counter()
        response = post_execute_sql(base_url, database_id, item["question"], timeout)
        latency_ms = (time.perf_counter() - start) * 1000.0
        total_latency_ms += latency_ms

        passed, reasons, details = grade(item, response)

        cat_total[item["category"]] += 1
        if passed:
            cat_passed[item["category"]] += 1

        status = "PASS" if passed else "FAIL"
        reason_text = "" if passed else "  -> " + "; ".join(reasons)
        print(f"[{status}] {item['id']:<13} {item['category']:<32} "
              f"{latency_ms:7.0f} ms{reason_text}")

        per_question.append({
            "id": item["id"],
            "category": item["category"],
            "question": item["question"],
            "latency_ms": round(latency_ms, 1),
            "passed": passed,
            "reasons": reasons,
            "grading": details,
            "response": response,
        })

    # --- summaries ---
    total = len(items)
    passed_count = sum(1 for q in per_question if q["passed"])
    failed_count = total - passed_count
    pass_rate = (passed_count / total * 100.0) if total else 0.0
    avg_latency_ms = (total_latency_ms / total) if total else 0.0

    print("\nCategory summary")
    print("-" * 50)
    for category in sorted(cat_total):
        p, t = cat_passed[category], cat_total[category]
        print(f"  {category:<34} {p}/{t}")

    print("\nOverall summary")
    print("-" * 50)
    print(f"  total        : {total}")
    print(f"  passed       : {passed_count}")
    print(f"  failed       : {failed_count}")
    print(f"  pass rate    : {pass_rate:.1f}%")
    print(f"  avg latency  : {avg_latency_ms:.0f} ms")

    result = {
        "benchmark": "petshop",
        "benchmark_version": data.get("version"),
        "timestamp": datetime.now().astimezone().isoformat(),
        "base_url": base_url,
        "database_id": database_id,
        "provider_env": os.environ.get("LLM_PROVIDER"),
        "model_env": os.environ.get("LLM_MODEL_NAME"),
        "summary": {
            "total": total,
            "passed": passed_count,
            "failed": failed_count,
            "pass_rate": round(pass_rate, 1),
            "avg_latency_ms": round(avg_latency_ms, 1),
        },
        "category_summary": {
            c: {"passed": cat_passed[c], "total": cat_total[c]} for c in sorted(cat_total)
        },
        "results": per_question,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"petshop_benchmark_{stamp}.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nResults saved to {out_path}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Run the PetShop SpiderSQL benchmark.")
    parser.add_argument("--database-id", type=int, default=1,
                        help="Database id of the uploaded PetShop database (default: 1).")
    parser.add_argument("--base-url", default="http://localhost:8000",
                        help="SpiderSQL backend base URL (default: http://localhost:8000).")
    parser.add_argument("--timeout", type=float, default=180.0,
                        help="Per-request timeout in seconds (default: 180).")
    args = parser.parse_args()
    run(args.base_url, args.database_id, args.timeout)


if __name__ == "__main__":
    main()