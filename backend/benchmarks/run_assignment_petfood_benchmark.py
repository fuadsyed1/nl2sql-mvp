#!/usr/bin/env python3

import argparse
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).resolve().parent
BENCHMARK_FILE = SCRIPT_DIR / "benchmark_queries_assignment_petfood.json"
RESULTS_DIR = SCRIPT_DIR / "results"


def post_execute_sql(base_url, database_id, question, timeout):
    url = f"{base_url.rstrip('/')}/database/{database_id}/execute_sql"
    payload = json.dumps({"question": question}).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"_error": f"HTTP {exc.code}: {exc.reason}"}
    except urllib.error.URLError as exc:
        return {"_error": f"connection error: {exc.reason}"}
    except Exception as exc:
        return {"_error": f"unexpected error: {exc}"}


def lower_set(values):
    return {str(v).lower() for v in (values or [])}


def flatten_rows(rows):
    text = []
    for row in rows or []:
        if isinstance(row, list):
            text.extend(str(cell) for cell in row)
        else:
            text.append(str(row))
    return " ".join(text)


def grade(item, response):
    if "_error" in response:
        return False, [response["_error"]], {}

    validation = response.get("validation") or {}
    plan = response.get("plan") or {}
    generated_sql = response.get("generated_sql") or {}
    execution = response.get("execution") or {}
    ir = response.get("ir") or {}

    sql = generated_sql.get("sql") or ""
    sql_lower = sql.lower()

    expected_sql = item.get("expected_sql_contains", [])
    missing_sql = [
        frag for frag in expected_sql
        if str(frag).lower() not in sql_lower
    ]

    params = generated_sql.get("params") or []
    expected_params = item.get("expected_params") or []

    tables_used = lower_set(plan.get("tables_used")) | lower_set(ir.get("tables"))
    expected_tables = lower_set(item.get("expected_tables"))

    bridge_tables = lower_set(plan.get("bridge_tables"))
    expected_bridge_tables = lower_set(item.get("expected_bridge_tables"))

    result_text = flatten_rows(execution.get("rows"))
    missing_results = [
        value for value in item.get("expected_result_contains", [])
        if str(value) not in result_text
    ]

    checks = {
        "validation_valid": validation.get("valid") is True,
        "plan_resolved": plan.get("resolved") is True,
        "generated": generated_sql.get("generated") is True,
        "executed": execution.get("executed") is True,
        "expected_tables_present": expected_tables.issubset(tables_used),
        "expected_bridge_tables_present": expected_bridge_tables.issubset(bridge_tables),
        "sql_contains": len(missing_sql) == 0,
        "params_match": params == expected_params,
        "result_contains": len(missing_results) == 0,
    }

    reasons = []

    if not checks["validation_valid"]:
        reasons.append("validation.valid != true")
    if not checks["plan_resolved"]:
        reasons.append("plan.resolved != true")
    if not checks["generated"]:
        reasons.append("generated_sql.generated != true")
    if not checks["executed"]:
        reasons.append("execution.executed != true")
    if not checks["expected_tables_present"]:
        reasons.append(f"missing expected_tables {sorted(expected_tables - tables_used)}")
    if not checks["expected_bridge_tables_present"]:
        reasons.append(f"missing expected_bridge_tables {sorted(expected_bridge_tables - bridge_tables)}")
    if missing_sql:
        reasons.append(f"sql missing fragments {missing_sql}")
    if not checks["params_match"]:
        reasons.append(f"params {params} != expected {expected_params}")
    if missing_results:
        reasons.append(f"results missing {missing_results}")

    grading = {
        "checks": checks,
        "sql": sql,
        "params": params,
        "tables_used": sorted(tables_used),
        "bridge_tables": sorted(bridge_tables),
    }

    return all(checks.values()), reasons, grading


def run(base_url, database_id, timeout):
    benchmark = json.loads(BENCHMARK_FILE.read_text(encoding="utf-8"))
    items = benchmark["queries"]

    print(
        f"Running {len(items)} Assignment Pet Food benchmarks "
        f"against {base_url} database_id={database_id}\n"
    )

    results = []
    passed_count = 0
    total_latency = 0.0

    for item in items:
        start = time.perf_counter()
        response = post_execute_sql(base_url, database_id, item["question"], timeout)
        latency_ms = (time.perf_counter() - start) * 1000.0
        total_latency += latency_ms

        passed, reasons, grading = grade(item, response)

        if passed:
            passed_count += 1

        status = "PASS" if passed else "FAIL"
        reason_text = "" if passed else " -> " + "; ".join(reasons)

        print(
            f"[{status}] {item['id']:<28} "
            f"{item['category']:<24} {latency_ms:7.0f} ms{reason_text}"
        )

        results.append({
            "id": item["id"],
            "category": item["category"],
            "question": item["question"],
            "latency_ms": round(latency_ms, 1),
            "passed": passed,
            "reasons": reasons,
            "grading": grading,
            "response": response,
        })

    total = len(items)
    failed_count = total - passed_count
    pass_rate = (passed_count / total * 100.0) if total else 0.0

    print("\nOverall summary")
    print("-" * 50)
    print(f"  total       : {total}")
    print(f"  passed      : {passed_count}")
    print(f"  failed      : {failed_count}")
    print(f"  pass rate   : {pass_rate:.1f}%")
    print(f"  avg latency : {total_latency / total:.0f} ms")

    output = {
        "benchmark": benchmark.get("benchmark"),
        "benchmark_version": benchmark.get("version"),
        "timestamp": datetime.now().astimezone().isoformat(),
        "base_url": base_url,
        "database_id": database_id,
        "summary": {
            "total": total,
            "passed": passed_count,
            "failed": failed_count,
            "pass_rate": round(pass_rate, 1),
            "avg_latency_ms": round(total_latency / total, 1),
        },
        "results": results,
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"assignment_petfood_benchmark_{stamp}.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    print(f"\nResults saved to {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-id", type=int, default=2)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=180.0)

    args = parser.parse_args()
    run(args.base_url, args.database_id, args.timeout)


if __name__ == "__main__":
    main()