#!/usr/bin/env python3
"""Shared runner for SpiderSQL natural-language execution benchmarks.

This runner intentionally does not compare generated SQL against a hard-coded
gold SQL string. A test passes when the backend returns success, produces SQL,
and does not report an execution failure.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT = 420


def _request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None,
    timeout: int,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw.strip() else {}
            if not isinstance(parsed, dict):
                parsed = {"data": parsed}
            parsed["_http_status"] = response.status
            return parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            parsed = {"raw_body": raw}
        if not isinstance(parsed, dict):
            parsed = {"data": parsed}
        parsed["_http_status"] = exc.code
        parsed["_request_error"] = f"HTTP {exc.code}"
        return parsed
    except Exception as exc:  # noqa: BLE001 - benchmark must record every failure
        return {
            "_http_status": None,
            "_request_error": f"{type(exc).__name__}: {exc}",
        }


def _get_json(url: str, timeout: int) -> dict[str, Any]:
    return _request_json("GET", url, None, timeout)


def _post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    return _request_json("POST", url, payload, timeout)


def _dig(mapping: Any, *path: str) -> Any:
    current = mapping
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def extract_generated_sql(response: dict[str, Any]) -> str:
    candidates = [
        _dig(response, "generated_sql", "sql"),
        _dig(response, "generated_sql", "query"),
        response.get("generated_sql"),
        response.get("sql"),
        response.get("selected_sql"),
        _dig(response, "result", "sql"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip().rstrip(";")
    return ""


def extract_row_count(response: dict[str, Any]) -> int | None:
    candidates = [
        _dig(response, "execution", "row_count"),
        response.get("row_count"),
        _dig(response, "result", "row_count"),
    ]
    for candidate in candidates:
        if isinstance(candidate, int):
            return candidate
    rows = _dig(response, "execution", "rows")
    if isinstance(rows, list):
        return len(rows)
    return None


def extract_columns(response: dict[str, Any]) -> list[str]:
    candidates = [
        _dig(response, "execution", "columns"),
        response.get("columns"),
        _dig(response, "result", "columns"),
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return [str(item) for item in candidate]
    return []


def execution_passed(response: dict[str, Any], generated_sql: str) -> tuple[bool, str]:
    if response.get("_request_error"):
        return False, str(response["_request_error"])
    if response.get("success") is not True:
        message = response.get("message") or response.get("error") or "response success was not true"
        return False, str(message)
    if not generated_sql:
        return False, "backend returned success but no generated SQL"

    execution = response.get("execution")
    if isinstance(execution, dict):
        if execution.get("success") is False:
            return False, str(execution.get("error") or execution.get("message") or "execution failed")
        for key in ("error", "exception"):
            if execution.get(key):
                return False, str(execution[key])

    return True, "query generated and executed successfully"


def _schema_snapshot(
    base_url: str,
    database_id: int,
    timeout: int,
) -> dict[str, Any]:
    base = base_url.rstrip("/")
    return {
        "database": _get_json(f"{base}/database/{database_id}", timeout),
        "schema": _get_json(f"{base}/database/{database_id}/schema", timeout),
        "relationships": _get_json(f"{base}/database/{database_id}/relationships", timeout),
    }


def _filter_tests(
    tests: list[dict[str, Any]],
    category: str | None,
    start: int | None,
    end: int | None,
) -> list[dict[str, Any]]:
    selected = list(tests)
    if category:
        selected = [test for test in selected if test["category"] == category]
    if start is not None:
        selected = [test for test in selected if int(test["ordinal"]) >= start]
    if end is not None:
        selected = [test for test in selected if int(test["ordinal"]) <= end]
    return selected


def _category_summary(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, dict[str, int]] = defaultdict(lambda: {"passed": 0, "failed": 0, "total": 0})
    for result in results:
        bucket = grouped[result["category"]]
        bucket["total"] += 1
        if result["passed"]:
            bucket["passed"] += 1
        else:
            bucket["failed"] += 1

    summary: dict[str, Any] = {}
    for category in sorted(grouped):
        bucket = grouped[category]
        total = bucket["total"]
        summary[category] = {
            **bucket,
            "pass_percent": round(100.0 * bucket["passed"] / total, 2) if total else 0.0,
        }
    return summary


def _safe_filename(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def _write_outputs(
    *,
    results: list[dict[str, Any]],
    snapshot: dict[str, Any],
    database_id: int,
    database_name: str,
    expected_tables: int,
    expected_relationships: int,
    suite_name: str,
    mode: str,
    base_url: str,
    started_at: str,
    output_dir: Path,
) -> dict[str, str]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _safe_filename(database_name)
    prefix = f"{slug}_{suite_name}_db{database_id}_{timestamp}"

    json_path = output_dir / f"{prefix}.json"
    txt_path = output_dir / f"{prefix}.txt"
    sql_path = output_dir / f"{prefix}.sql"
    csv_path = output_dir / f"{prefix}_summary.csv"

    passed = sum(1 for result in results if result["passed"])
    failed = len(results) - passed
    summary = {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "pass_percent": round(100.0 * passed / len(results), 2) if results else 0.0,
        "by_category": _category_summary(results),
    }

    document = {
        "benchmark": {
            "database_id": database_id,
            "database_name": database_name,
            "expected_tables": expected_tables,
            "expected_relationships": expected_relationships,
            "suite_name": suite_name,
            "mode": mode,
            "base_url": base_url,
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "scoring_rule": (
                "No hard SQL match. PASS means response.success=true, generated SQL is present, "
                "and the execution block does not report a failure."
            ),
        },
        "summary": summary,
        "database_snapshot": snapshot,
        "results": results,
    }
    json_path.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"SpiderSQL {suite_name}",
        f"Database: {database_name} #{database_id}",
        f"Mode: {mode}",
        f"Expected tables: {expected_tables}",
        f"Expected metadata relationships: {expected_relationships}",
        "Scoring: execution success only; no hard SQL string match.",
        "",
        f"PASS: {passed}/{len(results)}",
        f"FAIL: {failed}/{len(results)}",
        "",
        "CATEGORY SUMMARY",
        "-" * 100,
    ]
    for category, item in summary["by_category"].items():
        lines.append(
            f"{category:24s} PASS {item['passed']:2d}/{item['total']:2d} "
            f"({item['pass_percent']:6.2f}%)"
        )

    lines.extend(["", "TEST DETAILS", "=" * 100])
    for result in results:
        lines.extend(
            [
                f"{result['id']} [{result['category']}] {'PASS' if result['passed'] else 'FAIL'}",
                f"Question: {result['question']}",
                f"Reason: {result['reason']}",
                f"HTTP status: {result['http_status']}",
                f"Elapsed seconds: {result['elapsed_seconds']}",
                f"Row count: {result['row_count']}",
                f"Columns: {result['columns']}",
                "Generated SQL:",
                result["generated_sql"] or "(none)",
                "-" * 100,
            ]
        )
    txt_path.write_text("\n".join(lines), encoding="utf-8")

    sql_lines = [
        f"-- SpiderSQL generated SQL: {suite_name}",
        f"-- Database: {database_name} #{database_id}",
        "-- No SQL is hard-matched by the benchmark.",
        "",
    ]
    for result in results:
        sql_lines.append(
            f"-- {result['id']} | {result['category']} | "
            f"{'PASS' if result['passed'] else 'FAIL'}"
        )
        sql_lines.append(f"-- Question: {result['question']}")
        if result["generated_sql"]:
            sql_lines.append(result["generated_sql"].rstrip(";") + ";")
        else:
            sql_lines.append("-- No SQL generated.")
        sql_lines.append("")
    sql_path.write_text("\n".join(sql_lines), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["category", "passed", "failed", "total", "pass_percent"],
        )
        writer.writeheader()
        for category, item in summary["by_category"].items():
            writer.writerow({"category": category, **item})

    return {
        "json": str(json_path),
        "txt": str(txt_path),
        "sql": str(sql_path),
        "csv": str(csv_path),
    }


def run_query_cli(
    *,
    tests: list[dict[str, Any]],
    database_id: int,
    database_name: str,
    expected_tables: int,
    expected_relationships: int,
    suite_name: str,
    mode: str,
) -> int:
    parser = argparse.ArgumentParser(description=f"Run {suite_name}.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--db-id", type=int, default=database_id)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--only-category")
    parser.add_argument("--start", type=int)
    parser.add_argument("--end", type=int)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    selected = _filter_tests(tests, args.only_category, args.start, args.end)
    if args.limit is not None:
        selected = selected[: args.limit]
    if not selected:
        print("No tests selected.")
        return 2

    started_at = datetime.now().isoformat(timespec="seconds")
    base_url = args.base_url.rstrip("/")
    endpoint = f"{base_url}/database/{args.db_id}/execute_sql"
    output_dir = Path("benchmarks") / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 108)
    print(f"SpiderSQL {suite_name}")
    print(f"Database: {database_name} #{args.db_id}")
    print(f"Expected metadata: {expected_tables} tables, {expected_relationships} relationships")
    print(f"Endpoint: {endpoint}")
    print(f"Selected tests: {len(selected)}")
    print("Scoring: successful generation and execution only; no hard SQL match.")
    print("=" * 108)

    snapshot = _schema_snapshot(base_url, args.db_id, min(args.timeout, 120))
    results: list[dict[str, Any]] = []

    for index, test in enumerate(selected, start=1):
        started = time.perf_counter()
        response = _post_json(endpoint, {"question": test["question"]}, args.timeout)
        elapsed = round(time.perf_counter() - started, 3)
        generated_sql = extract_generated_sql(response)
        passed, reason = execution_passed(response, generated_sql)

        result = {
            "id": test["id"],
            "ordinal": test["ordinal"],
            "category": test["category"],
            "mode": mode,
            "question": test["question"],
            "passed": passed,
            "reason": reason,
            "http_status": response.get("_http_status"),
            "elapsed_seconds": elapsed,
            "generated_sql": generated_sql,
            "row_count": extract_row_count(response),
            "columns": extract_columns(response),
            "response": response,
        }
        results.append(result)

        status = "PASS" if passed else "FAIL"
        print(
            f"[{index:03d}/{len(selected):03d}] {status} "
            f"{test['id']} [{test['category']}] - {reason}",
            flush=True,
        )
        if args.sleep:
            time.sleep(args.sleep)

    paths = _write_outputs(
        results=results,
        snapshot=snapshot,
        database_id=args.db_id,
        database_name=database_name,
        expected_tables=expected_tables,
        expected_relationships=expected_relationships,
        suite_name=suite_name,
        mode=mode,
        base_url=base_url,
        started_at=started_at,
        output_dir=output_dir,
    )

    passed_count = sum(1 for result in results if result["passed"])
    print("=" * 108)
    print(f"DONE: PASS {passed_count}/{len(results)}")
    print(f"JSON: {paths['json']}")
    print(f"TXT:  {paths['txt']}")
    print(f"SQL:  {paths['sql']}")
    print(f"CSV:  {paths['csv']}")
    print("=" * 108)
    return 0 if passed_count == len(results) else 1
