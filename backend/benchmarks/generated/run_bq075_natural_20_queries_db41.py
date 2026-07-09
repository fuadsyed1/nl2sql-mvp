"""
Run 20 natural-language bq075 benchmark questions against SpiderSQL database_id=41.

This runner intentionally contains ONLY natural-language questions.
It does not contain expected SQL, answer-key SQL, grading SQL, or hints.

Usage from backend folder while FastAPI is running:
    cd C:\\Projects\\nl2sql-mvp\\backend
    python benchmarks/generated/run_bq075_natural_20_queries_db41.py

Optional:
    python benchmarks/generated/run_bq075_natural_20_queries_db41.py --base-url http://127.0.0.1:8000 --database-id 41

Outputs:
    bq075_natural_20_results_db41_<timestamp>.json
    bq075_natural_20_results_db41_<timestamp>.md
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_DATABASE_ID = 41
DEFAULT_TIMEOUT_SECONDS = 180

# Natural-language only. No table names, no SQL, no expected answers.
QUERIES: List[str] = [
    "Which areas had higher agriculture, forestry, fishing, and hunting weekly wages in the first quarter of 1994 than in the first quarter of 1990, and how much did the wage increase?",
    "Which areas gained agriculture, forestry, fishing, and hunting establishments between the first quarter of 1990 and the first quarter of 1994?",
    "Which areas had the largest drop in agriculture, forestry, fishing, and hunting weekly wages between the second quarter of 1990 and the second quarter of 1994?",
    "Which areas increased their agriculture, forestry, fishing, and hunting establishment count every first quarter from 1990 through 1994?",
    "Which areas increased their agriculture, forestry, fishing, and hunting weekly wages every first quarter from 1990 through 1994?",
    "Which areas had more agriculture, forestry, fishing, and hunting establishments in the fourth quarter of 1991 than in the fourth quarter of 1990, but lower weekly wages?",
    "Which areas had above-average agriculture, forestry, fishing, and hunting weekly wages in the first quarter of 1990?",
    "Which areas had above-average agriculture, forestry, fishing, and hunting establishment counts but below-average weekly wages in the second quarter of 1990?",
    "Which areas had the ten highest agriculture, forestry, fishing, and hunting weekly wages in the third quarter of 1991?",
    "Which areas had the same agriculture, forestry, fishing, and hunting establishment count in the first quarter of 1990 and the first quarter of 1994, but different weekly wages?",
    "Which areas had agriculture, forestry, fishing, and hunting weekly wages increase while establishment counts decreased from the first quarter of 1990 to the first quarter of 1994?",
    "Which areas had the largest combined agriculture, forestry, fishing, and hunting establishment count across all four quarters of 1990?",
    "Which areas had their highest agriculture, forestry, fishing, and hunting weekly wage in the fourth quarter of 1990 compared with the other quarters of 1990?",
    "Which areas increased their agriculture, forestry, fishing, and hunting establishment count from quarter to quarter throughout 1990?",
    "Which areas had agriculture, forestry, fishing, and hunting weekly wages above 500 in the first quarter of 1991?",
    "Which areas had agriculture, forestry, fishing, and hunting weekly wages in the first quarter of 1994 that were more than double their first-quarter 1990 wages?",
    "Which areas moved from below-average agriculture, forestry, fishing, and hunting weekly wages in the first quarter of 1990 to above-average wages in the first quarter of 1994?",
    "Which areas had the largest increase in agriculture, forestry, fishing, and hunting establishments from the first quarter of 1990 to the first quarter of 1994?",
    "Which areas had above-average agriculture, forestry, fishing, and hunting establishment counts in both the first quarter of 1990 and the first quarter of 1994?",
    "Which areas had higher agriculture, forestry, fishing, and hunting weekly wages but fewer establishments in the first quarter of 1994 than in the first quarter of 1990?",
]


def post_json(url: str, payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_sql(response: Dict[str, Any]) -> str:
    generated = response.get("generated_sql") or {}
    if isinstance(generated, dict):
        return generated.get("sql") or ""
    direct_sql = response.get("sql")
    return direct_sql if isinstance(direct_sql, str) else ""


def extract_row_count(response: Dict[str, Any]) -> Any:
    execution = response.get("execution") or {}
    if isinstance(execution, dict):
        return execution.get("row_count")
    return None


def run_queries(base_url: str, database_id: int, timeout: int, delay: float) -> List[Dict[str, Any]]:
    endpoint = f"{base_url.rstrip('/')}/database/{database_id}/execute_sql"
    results: List[Dict[str, Any]] = []

    for index, question in enumerate(QUERIES, start=1):
        started = time.time()
        print(f"[{index:02d}/{len(QUERIES)}] {question}")
        try:
            response = post_json(endpoint, {"question": question}, timeout=timeout)
            elapsed = round(time.time() - started, 3)
            record = {
                "index": index,
                "question": question,
                "success": response.get("success"),
                "row_count": extract_row_count(response),
                "sql": extract_sql(response),
                "extraction_source": response.get("extraction_source"),
                "query_family": response.get("query_family"),
                "query_family_confidence": response.get("query_family_confidence"),
                "query_family_reason": response.get("query_family_reason"),
                "elapsed_seconds": elapsed,
                "response": response,
            }
            status = "OK" if record["success"] else "FAIL"
            print(
                f"    {status} rows={record['row_count']} "
                f"source={record['extraction_source']} family={record['query_family']} "
                f"time={elapsed}s"
            )
        except urllib.error.HTTPError as exc:
            elapsed = round(time.time() - started, 3)
            error_body = exc.read().decode("utf-8", errors="replace")
            record = {
                "index": index,
                "question": question,
                "success": False,
                "row_count": None,
                "sql": "",
                "extraction_source": None,
                "query_family": None,
                "query_family_confidence": None,
                "query_family_reason": None,
                "elapsed_seconds": elapsed,
                "error": f"HTTP {exc.code}: {error_body}",
            }
            print(f"    HTTP ERROR {exc.code}: {error_body[:300]}")
        except Exception as exc:
            elapsed = round(time.time() - started, 3)
            record = {
                "index": index,
                "question": question,
                "success": False,
                "row_count": None,
                "sql": "",
                "extraction_source": None,
                "query_family": None,
                "query_family_confidence": None,
                "query_family_reason": None,
                "elapsed_seconds": elapsed,
                "error": repr(exc),
            }
            print(f"    ERROR: {exc!r}")

        results.append(record)
        if delay > 0 and index < len(QUERIES):
            time.sleep(delay)

    return results


def write_outputs(results: List[Dict[str, Any]], database_id: int, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"bq075_natural_20_results_db{database_id}_{timestamp}.json"
    md_path = output_dir / f"bq075_natural_20_results_db{database_id}_{timestamp}.md"

    summary = {
        "database_id": database_id,
        "total": len(results),
        "success_count": sum(1 for r in results if r.get("success")),
        "failure_count": sum(1 for r in results if not r.get("success")),
        "query_family_count": sum(1 for r in results if r.get("extraction_source") == "query_family"),
        "llm_count": sum(1 for r in results if r.get("extraction_source") == "llm"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }

    json_path.write_text(
        json.dumps({"summary": summary, "results": results}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        f"# bq075 Natural 20 Query Results — database #{database_id}",
        "",
        "## Summary",
        "",
        f"- Total: {summary['total']}",
        f"- Success: {summary['success_count']}",
        f"- Failure: {summary['failure_count']}",
        f"- Query family path: {summary['query_family_count']}",
        f"- LLM path: {summary['llm_count']}",
        f"- Generated at: {summary['generated_at']}",
        "",
    ]

    for record in results:
        lines.extend(
            [
                f"## Q{record['index']}. {record['question']}",
                "",
                f"- Success: `{record.get('success')}`",
                f"- Row count: `{record.get('row_count')}`",
                f"- Extraction source: `{record.get('extraction_source')}`",
                f"- Query family: `{record.get('query_family')}`",
                f"- Confidence: `{record.get('query_family_confidence')}`",
                f"- Reason: `{record.get('query_family_reason')}`",
                f"- Time: `{record.get('elapsed_seconds')}s`",
                "",
                "```sql",
                record.get("sql") or "-- no sql generated",
                "```",
                "",
            ]
        )
        if record.get("error"):
            lines.extend(["Error:", "", "```text", str(record["error"]), "```", ""])

    md_path.write_text("\n".join(lines), encoding="utf-8")

    print("\nSaved:")
    print(f"  JSON: {json_path}")
    print(f"  Markdown: {md_path}")
    print("\nSummary:")
    print(json.dumps(summary, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 20 natural-language bq075 benchmark questions.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--database-id", type=int, default=DEFAULT_DATABASE_ID)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--delay", type=float, default=0.0, help="Optional delay between requests in seconds.")
    parser.add_argument("--output-dir", default=".")
    args = parser.parse_args()

    if len(QUERIES) != 20:
        print(f"Expected 20 queries, found {len(QUERIES)}", file=sys.stderr)
        return 2

    results = run_queries(args.base_url, args.database_id, args.timeout, args.delay)
    write_outputs(results, args.database_id, Path(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
