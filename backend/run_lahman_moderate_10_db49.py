"""
Moderate Lahman local-benchmark test runner.

This script runs 10 moderate natural-language questions against a loaded
Lahman Baseball database in SpiderSQL.

Default database_id is 49 because the current UI/backend run showed:
Database created: Lahman Baseball #49

Run from repo root or from this folder:

    python backend/benchmarks/local_lahman/run_lahman_moderate_10_db49.py

Optional:

    python backend/benchmarks/local_lahman/run_lahman_moderate_10_db49.py --db-id 49 --base-url http://127.0.0.1:8000

Outputs:

    backend/benchmarks/local_lahman/results/lahman_moderate_10_db49.json
    backend/benchmarks/local_lahman/results/lahman_moderate_10_db49.txt
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


QUERIES: list[str] = [
    "Show playerID, nameFirst, nameLast, birthYear from People limit 10.",

    "Count the number of rows in People.",

    "Find the top 10 rows from Batting by home runs. Show playerID, yearID, teamID, HR.",

    "Find batting rows where HR is greater than 50. Show playerID, yearID, teamID, HR and RBI.",

    "For each year in Batting, show the total number of home runs and total RBIs. Order by yearID.",

    "Find the top 10 players by total career home runs from Batting. Show playerID and total home runs.",

    "Join People and Batting using playerID. Show player names, yearID, teamID, and home runs for rows where HR is greater than 50.",

    "Join Teams and Batting using yearID, teamID, and lgID. For year 2001, show team name, playerID, and HR for batting rows with HR greater than 40.",

    "Join People and Pitching using playerID. Show player names, yearID, teamID, wins, losses, and strikeouts for pitching rows where strikeouts are greater than 250.",

    "Join Schools and CollegePlaying using schoolID. Show school name, playerID, and yearID for the first 20 college playing rows.",
]


def post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    """POST JSON using only Python standard library."""
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = {"success": False, "raw_text": raw}
            body["_http_status"] = response.status
            return body

    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"success": False, "raw_text": raw}
        body["_http_status"] = exc.code
        return body

    except Exception as exc:
        return {
            "success": False,
            "_http_status": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def extract_sql(response_json: dict[str, Any]) -> str:
    generated_sql = response_json.get("generated_sql")
    if isinstance(generated_sql, dict):
        return str(generated_sql.get("sql") or "")
    if isinstance(generated_sql, str):
        return generated_sql
    return ""


def extract_row_count(response_json: dict[str, Any]) -> Any:
    execution = response_json.get("execution")
    if isinstance(execution, dict):
        return execution.get("row_count")
    return None


def compact_json(obj: Any, max_chars: int = 4000) -> str:
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...<truncated>..."


def result_paths(script_dir: Path, db_id: int) -> tuple[Path, Path]:
    results_dir = script_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    return (
        results_dir / f"lahman_moderate_10_db{db_id}.json",
        results_dir / f"lahman_moderate_10_db{db_id}.txt",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 10 moderate Lahman NL-to-SQL benchmark queries.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--db-id", type=int, default=49)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--sleep", type=float, default=0.5)
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    json_path, txt_path = result_paths(script_dir, args.db_id)

    url = f"{args.base_url.rstrip('/')}/database/{args.db_id}/execute_sql"

    all_results: list[dict[str, Any]] = []
    text_lines: list[str] = []

    print("=" * 80)
    print("Lahman moderate 10-query benchmark")
    print(f"Database ID: {args.db_id}")
    print(f"Endpoint:    {url}")
    print(f"Timeout:     {args.timeout}s per query")
    print("=" * 80)

    for index, question in enumerate(QUERIES, start=1):
        print()
        print("-" * 80)
        print(f"QUERY {index:02d}")
        print(question)

        started = time.time()
        response_json = post_json(url, {"question": question}, timeout=args.timeout)
        elapsed = time.time() - started

        sql = extract_sql(response_json)
        row_count = extract_row_count(response_json)
        success = response_json.get("success")

        entry = {
            "query_number": index,
            "question": question,
            "elapsed_seconds": round(elapsed, 3),
            "success": success,
            "http_status": response_json.get("_http_status"),
            "row_count": row_count,
            "sql": sql,
            "response": response_json,
        }
        all_results.append(entry)

        print(f"success:         {success}")
        print(f"http_status:     {response_json.get('_http_status')}")
        print(f"row_count:       {row_count}")
        print(f"elapsed_seconds: {elapsed:.2f}")

        if sql:
            print("SQL:")
            print(sql)
        else:
            print("SQL: <no sql>")
            error = response_json.get("error")
            if error:
                print(f"error: {error}")

        text_lines.extend(
            [
                "=" * 80,
                f"QUERY {index:02d}",
                "",
                "NATURAL LANGUAGE:",
                question,
                "",
                f"SUCCESS: {success}",
                f"HTTP STATUS: {response_json.get('_http_status')}",
                f"ROW COUNT: {row_count}",
                f"ELAPSED SECONDS: {elapsed:.2f}",
                "",
                "SQL:",
                sql or "<no sql>",
                "",
                "RESPONSE PREVIEW:",
                compact_json(response_json, max_chars=5000),
                "",
            ]
        )

        time.sleep(args.sleep)

    json_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
    txt_path.write_text("\n".join(text_lines), encoding="utf-8")

    success_count = sum(1 for item in all_results if item.get("success") is True)
    timeout_or_request_failures = sum(
        1 for item in all_results
        if item.get("http_status") is None and item.get("success") is not True
    )

    print()
    print("=" * 80)
    print("DONE")
    print(f"Successful responses:       {success_count}/{len(QUERIES)}")
    print(f"Timeout/request failures:   {timeout_or_request_failures}/{len(QUERIES)}")
    print(f"JSON results saved to:      {json_path}")
    print(f"Text summary saved to:      {txt_path}")
    print("=" * 80)

    return 0 if success_count == len(QUERIES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
