#!/usr/bin/env python3
"""Shared runner for SpiderSQL natural-language containment benchmarks.

No hard SQL strings or hard containment verdicts are used for automated pass/fail.
A case passes when the batch endpoint succeeds and every input query returns SQL
without reporting query execution failure. The complete SQL and containment
response are preserved for manual or later semantic review.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT = 420


def _post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
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
    except Exception as exc:  # noqa: BLE001
        return {
            "_http_status": None,
            "_request_error": f"{type(exc).__name__}: {exc}",
        }


def _query_results(response: dict[str, Any]) -> list[dict[str, Any]]:
    value = response.get("query_results")
    return value if isinstance(value, list) else []


def _sql_from_query_result(item: dict[str, Any]) -> str:
    value = item.get("sql")
    if isinstance(value, str):
        return value.strip().rstrip(";")
    nested = item.get("generated_sql")
    if isinstance(nested, dict) and isinstance(nested.get("sql"), str):
        return nested["sql"].strip().rstrip(";")
    return ""


def _row_count(item: dict[str, Any]) -> int | None:
    value = item.get("row_count")
    if isinstance(value, int):
        return value
    execution = item.get("execution")
    if isinstance(execution, dict) and isinstance(execution.get("row_count"), int):
        return execution["row_count"]
    return None


def _case_passed(response: dict[str, Any], expected_query_count: int) -> tuple[bool, str]:
    if response.get("_request_error"):
        return False, str(response["_request_error"])
    if response.get("success") is not True:
        return False, str(response.get("message") or response.get("error") or "batch success was not true")

    results = _query_results(response)
    if len(results) != expected_query_count:
        return False, f"expected {expected_query_count} query results, received {len(results)}"

    for index, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            return False, f"query {index} result is not an object"
        if item.get("success") is False:
            return False, f"query {index} reported execution failure"
        if not _sql_from_query_result(item):
            return False, f"query {index} returned no generated SQL"

    return True, "all queries generated SQL and the containment endpoint completed"


def _filter_cases(
    cases: list[dict[str, Any]],
    only_mode: str,
    start: int | None,
    end: int | None,
) -> list[dict[str, Any]]:
    selected = list(cases)
    if only_mode != "all":
        selected = [case for case in selected if case["mode"] == only_mode]
    if start is not None:
        selected = [case for case in selected if int(case["id"]) >= start]
    if end is not None:
        selected = [case for case in selected if int(case["id"]) <= end]
    return selected


def _write_case_text(
    lines: list[str],
    case: dict[str, Any],
    response: dict[str, Any],
    elapsed: float,
    passed: bool,
    reason: str,
) -> None:
    lines.extend(
        [
            "=" * 108,
            f"CASE {case['id']:02d}: {case['name']}",
            f"MODE: {case['mode']}",
            f"CATEGORY: {case['category']}",
            f"STATUS: {'PASS' if passed else 'FAIL'}",
            f"REASON: {reason}",
            f"EXPECTED RELATIONSHIP NOTE: {case['expected_note']}",
            f"HTTP STATUS: {response.get('_http_status')}",
            f"ELAPSED SECONDS: {elapsed:.3f}",
            "",
            "INPUT QUERIES",
        ]
    )
    for index, query in enumerate(case["queries"], start=1):
        lines.append(f"Q{index}: {query}")

    lines.extend(["", "GENERATED SQL AND EXECUTION"])
    for index, item in enumerate(_query_results(response), start=1):
        sql = _sql_from_query_result(item)
        lines.extend(
            [
                f"Q{index}: success={item.get('success')} safe={item.get('safe')} "
                f"rows={_row_count(item)} empty={item.get('empty_result')}",
                f"columns={item.get('execution_columns') or item.get('columns')}",
                sql or "(no SQL)",
                "",
            ]
        )

    analysis = response.get("analysis")
    lines.extend(
        [
            "CONTAINMENT ANALYSIS",
            json.dumps(analysis, indent=2, ensure_ascii=False) if analysis is not None else "(none)",
            "",
            "PAIRWISE RESULTS",
            json.dumps(
                response.get("pairwise_results") or response.get("comparisons") or [],
                indent=2,
                ensure_ascii=False,
            ),
            "",
        ]
    )


def _safe_filename(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def run_containment_cli(
    *,
    cases: list[dict[str, Any]],
    database_id: int,
    database_name: str,
    expected_tables: int,
    expected_relationships: int,
    suite_name: str,
) -> int:
    parser = argparse.ArgumentParser(description=f"Run {suite_name}.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--db-id", type=int, default=database_id)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--sleep", type=float, default=0.3)
    parser.add_argument("--only-mode", choices=["all", "normal", "structured"], default="all")
    parser.add_argument("--start", type=int)
    parser.add_argument("--end", type=int)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    selected = _filter_cases(cases, args.only_mode, args.start, args.end)
    if args.limit is not None:
        selected = selected[: args.limit]
    if not selected:
        print("No containment cases selected.")
        return 2

    base_url = args.base_url.rstrip("/")
    endpoint = f"{base_url}/database/{args.db_id}/check_containment_batch"
    output_dir = Path("benchmarks") / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now().isoformat(timespec="seconds")

    print("=" * 108)
    print(f"SpiderSQL {suite_name}")
    print(f"Database: {database_name} #{args.db_id}")
    print(f"Expected metadata: {expected_tables} tables, {expected_relationships} relationships")
    print(f"Endpoint: {endpoint}")
    print(f"Selected cases: {len(selected)}")
    print("Automated scoring checks execution completion only; all SQL and verdicts are saved.")
    print("=" * 108)

    collected: list[dict[str, Any]] = []
    text_lines: list[str] = [
        f"SpiderSQL {suite_name}",
        f"Database: {database_name} #{args.db_id}",
        f"Expected tables: {expected_tables}",
        f"Expected metadata relationships: {expected_relationships}",
        "No hard SQL or hard verdict matching is used.",
        "",
    ]
    sql_lines: list[str] = [
        f"-- SpiderSQL containment generated SQL: {suite_name}",
        f"-- Database: {database_name} #{args.db_id}",
        "",
    ]

    for ordinal, case in enumerate(selected, start=1):
        started = time.perf_counter()
        response = _post_json(endpoint, {"queries": case["queries"]}, args.timeout)
        elapsed = round(time.perf_counter() - started, 3)
        passed, reason = _case_passed(response, len(case["queries"]))

        collected.append(
            {
                "case": case,
                "passed": passed,
                "reason": reason,
                "elapsed_seconds": elapsed,
                "http_status": response.get("_http_status"),
                "response": response,
            }
        )
        _write_case_text(text_lines, case, response, elapsed, passed, reason)

        sql_lines.append(
            f"-- CASE {case['id']:02d} | {case['mode']} | {case['category']} | "
            f"{'PASS' if passed else 'FAIL'}"
        )
        for query_index, (query, item) in enumerate(
            zip(case["queries"], _query_results(response), strict=False),
            start=1,
        ):
            sql_lines.append(f"-- Q{query_index}: {query}")
            sql = _sql_from_query_result(item)
            sql_lines.append(sql.rstrip(";") + ";" if sql else "-- No SQL generated.")
            sql_lines.append("")

        print(
            f"[{ordinal:02d}/{len(selected):02d}] {'PASS' if passed else 'FAIL'} "
            f"CASE {case['id']:02d} [{case['mode']} / {case['category']}] - {reason}",
            flush=True,
        )
        if args.sleep:
            time.sleep(args.sleep)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _safe_filename(database_name)
    prefix = f"{slug}_{suite_name}_db{args.db_id}_{timestamp}"
    json_path = output_dir / f"{prefix}.json"
    txt_path = output_dir / f"{prefix}.txt"
    sql_path = output_dir / f"{prefix}.sql"

    passed_count = sum(1 for item in collected if item["passed"])
    document = {
        "benchmark": {
            "database_id": args.db_id,
            "database_name": database_name,
            "expected_tables": expected_tables,
            "expected_relationships": expected_relationships,
            "suite_name": suite_name,
            "base_url": base_url,
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "scoring_rule": (
                "No hard SQL or verdict match. PASS means the batch endpoint completed and each "
                "input query returned SQL without reporting execution failure."
            ),
        },
        "summary": {
            "total_cases": len(collected),
            "passed_cases": passed_count,
            "failed_cases": len(collected) - passed_count,
            "normal_cases": sum(1 for item in collected if item["case"]["mode"] == "normal"),
            "structured_cases": sum(1 for item in collected if item["case"]["mode"] == "structured"),
        },
        "results": collected,
    }
    json_path.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")

    text_lines.extend(
        [
            "=" * 108,
            "FINAL SUMMARY",
            f"PASS: {passed_count}/{len(collected)}",
            f"FAIL: {len(collected) - passed_count}/{len(collected)}",
        ]
    )
    txt_path.write_text("\n".join(text_lines), encoding="utf-8")
    sql_path.write_text("\n".join(sql_lines), encoding="utf-8")

    print("=" * 108)
    print(f"DONE: PASS {passed_count}/{len(collected)}")
    print(f"JSON: {json_path}")
    print(f"TXT:  {txt_path}")
    print(f"SQL:  {sql_path}")
    print("=" * 108)
    return 0 if passed_count == len(collected) else 1
