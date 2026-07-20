#!/usr/bin/env python3
"""
Run 100 natural-language queries against SpiderSQL database 46.

What it does:
- Sends each question to POST /database/46/execute_sql
- Prints PASS when SpiderSQL reports a successful SQL execution
- Prints FAIL otherwise
- Saves the question, generated SQL, status, row count, warnings, and error
  to a timestamped TXT file after every query

Example:
    python run_db46_100_queries.py

Optional:
    python run_db46_100_queries.py --base-url http://127.0.0.1:8000
    python run_db46_100_queries.py --timeout 240 --delay 0.5
    python run_db46_100_queries.py --output db46_100_results.txt
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DATABASE_ID = 46

QUERIES: list[str] = [
    # Easy: retrieval, filters, sorting, simple counts
    "Show all patients.",
    "List patient IDs and patient names.",
    "Show all doctors.",
    "List all appointments.",
    "Show all invoices.",
    "List all lab results.",
    "Find patients from Idaho.",
    "Find patients whose insurance provider is BlueCross.",
    "Find completed appointments.",
    "Find appointments that are checkups.",
    "Find unpaid invoices.",
    "Find partially paid invoices.",
    "Find invoices with a total amount greater than 450.",
    "Find lab results marked critical.",
    "Find lab results marked high.",
    "Find lab results marked low.",
    "List appointments ordered by appointment date from newest to oldest.",
    "Show the 10 most expensive invoices.",
    "Show the 10 most recent lab results.",
    "Count all patients.",

    # Easy-medium: joins and basic aggregation
    "Count all appointments.",
    "Count all invoices.",
    "Count all lab results.",
    "Show each appointment with its patient name.",
    "Show each appointment with the doctor's specialty.",
    "Show every invoice with the patient ID and patient name.",
    "Show every lab result with the patient ID and patient name.",
    "List patients who have at least one appointment.",
    "List patients who have at least one completed appointment.",
    "List patients who have at least one checkup appointment.",
    "List patients who have at least one unpaid invoice.",
    "List patients who have at least one critical lab result.",
    "Count appointments for each patient.",
    "Count appointments for each doctor.",
    "Count lab results for each patient.",
    "Count invoices for each patient.",
    "Calculate the total invoiced amount for each patient.",
    "Calculate the average invoice amount for each patient.",
    "Calculate the maximum invoice amount for each patient.",
    "Calculate the minimum invoice amount for each patient.",

    # Medium: GROUP BY, HAVING, DISTINCT, top-k
    "Count patients by state.",
    "Count patients by insurance provider.",
    "Count appointments by status.",
    "Count appointments by visit type.",
    "Count doctors by specialty.",
    "Count lab results by result flag.",
    "Count lab results by test name.",
    "Show the total invoiced amount by insurance provider.",
    "Show the average invoice amount by insurance provider.",
    "Show the total outstanding balance by patient, where outstanding balance is total amount minus insurance paid.",
    "Find patients with more than 3 appointments.",
    "Find doctors who handled more than 5 appointments.",
    "Find patients with more than 2 completed appointments.",
    "Find patients with more than one distinct type of lab test.",
    "Find patients with more than one abnormal lab test type, where abnormal means high, low, or critical.",
    "Find insurance providers with more than 2 patients.",
    "Find visit types with more than 5 appointments.",
    "Show the 5 patients with the highest total invoiced amount.",
    "Show the 5 doctors with the most appointments.",
    "Show the 5 lab test names with the highest average test value.",

    # Medium-hard: comparisons, subqueries, set-style questions
    "Find patients whose total invoiced amount is above the average patient total.",
    "Find patients whose average invoice amount is above the overall average invoice amount.",
    "Find invoices whose total amount is above the average invoice amount.",
    "Find lab results whose test value is above the average value for the same test name.",
    "Find doctors whose appointment count is above the average doctor appointment count.",
    "Find insurance providers whose total invoiced amount is above the average provider total.",
    "Find patients who have appointments but no invoices.",
    "Find patients who have invoices but no lab results.",
    "Find patients who have both a completed appointment and an unpaid invoice.",
    "Find patients who have a critical lab result or an unpaid invoice.",
    "Find patients who had both a checkup and a follow-up appointment.",
    "Find patients who were seen by doctors from more than one specialty.",
    "Find patients who have appointments with every status that appears in the appointments table.",
    "Find doctors who have never handled a completed appointment.",
    "Find patients whose total invoice amount is greater than every individual invoice amount for patients from Idaho.",
    "Find the patient or patients with the highest total invoiced amount.",
    "Find the doctor or doctors with the highest number of appointments.",
    "Find the most common appointment visit type.",
    "Find the insurance provider with the highest total outstanding balance.",
    "Find the lab test name with the highest average test value.",

    # Hard: multi-condition, temporal, nested aggregation, grain-sensitive
    "Find patients from Idaho who had at least one completed checkup appointment.",
    "Find patients from Idaho who had at least one completed checkup appointment with an invoice total greater than 450.",
    "Find patients who had a completed appointment and whose total invoiced amount is greater than 1000.",
    "Find patients whose latest appointment was completed.",
    "Find patients whose earliest appointment was a checkup.",
    "Find each patient's most recent appointment date.",
    "Find patients whose most recent appointment was completed and whose lifetime invoiced amount is above the average for patients with the same insurance provider.",
    "Find patients whose total invoiced amount is above the average total for patients with the same insurance provider.",
    "Find patients who were seen by doctors from more than one specialty and whose total invoiced amount is above the average total for patients with the same insurance provider.",
    "Find patients whose unpaid or partially paid balance is higher than the average outstanding balance for patients with the same insurance provider.",
    "Find patients with abnormal results in more than one type of lab test and an outstanding balance above the average patient outstanding balance.",
    "Find lab results whose value is above the average for the same test and whose patient has spent more than the average patient.",
    "Find patients who have at least two completed appointments and at least one critical lab result.",
    "Find doctors who treated patients from more than one state and handled more appointments than the average doctor.",
    "Find patients whose number of distinct lab test types is above the average number of distinct test types per patient.",
    "Find patients whose total outstanding balance is positive and whose average invoice amount is above the overall patient average.",
    "For each insurance provider, find the patient with the highest total invoiced amount.",
    "For each doctor specialty, find the doctor with the most appointments.",
    "Find patients whose total invoiced amount is above their insurance provider average and who also have more than one distinct appointment visit type.",
    "Find patients whose most recent appointment was completed, who have abnormal lab results in more than one test type, and whose outstanding balance is above the average patient outstanding balance.",
]

assert len(QUERIES) == 100, f"Expected 100 queries, found {len(QUERIES)}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run 100 natural-language queries against SpiderSQL DB46."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="SpiderSQL backend base URL.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=240.0,
        help="Timeout in seconds for each request.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.25,
        help="Delay in seconds between requests.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="TXT output path. Default: timestamped file in the current directory.",
    )
    return parser.parse_args()


def post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
            return json.loads(text)
    except HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(error_text)
            if isinstance(parsed, dict):
                parsed.setdefault("_http_status", exc.code)
                return parsed
        except json.JSONDecodeError:
            pass
        return {"success": False, "error": f"HTTP {exc.code}", "message": error_text}
    except URLError as exc:
        return {"success": False, "error": "connection_error", "message": str(exc.reason)}
    except TimeoutError:
        return {"success": False, "error": "timeout", "message": f"Request exceeded {timeout} seconds."}
    except json.JSONDecodeError as exc:
        return {"success": False, "error": "invalid_json_response", "message": str(exc)}
    except Exception as exc:
        return {"success": False, "error": type(exc).__name__, "message": str(exc)}


def extract_sql(result: dict[str, Any]) -> str:
    generated = result.get("generated_sql")
    if isinstance(generated, dict):
        sql = generated.get("sql")
        if isinstance(sql, str) and sql.strip():
            return sql.strip()
    elif isinstance(generated, str) and generated.strip():
        return generated.strip()

    rejected = result.get("debug_rejected_sql")
    if isinstance(rejected, dict):
        sql = rejected.get("sql")
        if isinstance(sql, str) and sql.strip():
            return sql.strip()
    elif isinstance(rejected, str) and rejected.strip():
        return rejected.strip()

    return "-- NO SQL RETURNED"


def execution_succeeded(result: dict[str, Any]) -> bool:
    if result.get("success") is not True:
        return False
    execution = result.get("execution")
    return isinstance(execution, dict) and execution.get("executed") is True and not execution.get("error")


def format_warnings(result: dict[str, Any]) -> str:
    warnings = result.get("warnings", [])
    if not warnings:
        return "None"
    if isinstance(warnings, list):
        return "\n".join(f"- {item}" for item in warnings)
    return str(warnings)


def write_result(output_file, index: int, question: str, status: str, elapsed: float, result: dict[str, Any]) -> None:
    execution = result.get("execution")
    if not isinstance(execution, dict):
        execution = {}

    error = result.get("error") or execution.get("error") or result.get("message") or ""

    output_file.write("=" * 100 + "\n")
    output_file.write(f"QUERY {index:03d}\n")
    output_file.write(f"STATUS: {status}\n")
    output_file.write(f"ELAPSED: {elapsed:.2f} seconds\n")
    output_file.write(f"QUESTION: {question}\n")
    output_file.write(f"SELECTED CANDIDATE: {result.get('selected_candidate_source', '')}\n")
    output_file.write(f"ROW COUNT: {execution.get('row_count')}\n")
    output_file.write(f"ERROR: {error}\n")
    output_file.write("\nSQL:\n")
    output_file.write(extract_sql(result) + "\n")
    output_file.write("\nWARNINGS:\n")
    output_file.write(format_warnings(result) + "\n\n")
    output_file.flush()


def main() -> int:
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(args.output or f"db46_100_query_results_{timestamp}.txt").resolve()
    endpoint = f"{args.base_url.rstrip('/')}/database/{DATABASE_ID}/execute_sql"

    passed = 0
    failed = 0
    started = time.perf_counter()

    print(f"SpiderSQL endpoint: {endpoint}")
    print(f"Results file: {output_path}")
    print(f"Queries: {len(QUERIES)}")
    print("-" * 80)

    with output_path.open("w", encoding="utf-8") as output_file:
        output_file.write("SpiderSQL DB46 — 100 Natural-Language Query Test\n")
        output_file.write(f"Started: {datetime.now().isoformat(timespec='seconds')}\n")
        output_file.write(f"Endpoint: {endpoint}\n")
        output_file.write(f"Total queries: {len(QUERIES)}\n\n")
        output_file.flush()

        for index, question in enumerate(QUERIES, start=1):
            query_started = time.perf_counter()
            result = post_json(endpoint, {"question": question}, timeout=args.timeout)
            elapsed = time.perf_counter() - query_started

            if execution_succeeded(result):
                status = "PASS"
                passed += 1
            else:
                status = "FAIL"
                failed += 1

            print(f"[{index:03d}/100] {status} ({elapsed:.2f}s) — {question}", flush=True)
            write_result(output_file, index, question, status, elapsed, result)

            if args.delay > 0 and index < len(QUERIES):
                time.sleep(args.delay)

        total_elapsed = time.perf_counter() - started
        output_file.write("\n" + "=" * 100 + "\nFINAL SUMMARY\n")
        output_file.write(f"PASS: {passed}\n")
        output_file.write(f"FAIL: {failed}\n")
        output_file.write(f"TOTAL: {len(QUERIES)}\n")
        output_file.write(f"EXECUTION SUCCESS RATE: {passed / len(QUERIES) * 100:.2f}%\n")
        output_file.write(f"TOTAL ELAPSED: {total_elapsed:.2f} seconds\n")
        output_file.flush()

    print("-" * 80)
    print(f"PASS: {passed}")
    print(f"FAIL: {failed}")
    print(f"TOTAL: {len(QUERIES)}")
    print(f"Execution success rate: {passed / len(QUERIES) * 100:.2f}%")
    print(f"Saved: {output_path}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
