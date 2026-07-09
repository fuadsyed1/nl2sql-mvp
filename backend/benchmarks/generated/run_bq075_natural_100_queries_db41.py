"""
Run 100 natural-language bq075 benchmark questions against SpiderSQL database_id=41.

This runner intentionally contains ONLY natural-language questions.
It does NOT contain expected SQL or an answer key.

Usage from backend folder while FastAPI is running:
    cd C:\Projects\nl2sql-mvp\backend
    python benchmarks/generated/run_bq075_natural_100_queries_db41.py

Optional:
    python benchmarks/generated/run_bq075_natural_100_queries_db41.py --base-url http://127.0.0.1:8000 --database-id 41

Outputs:
    bq075_natural_100_results_db41_<timestamp>.json
    bq075_natural_100_results_db41_<timestamp>.md
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
DEFAULT_TIMEOUT = 240

QUERIES: List[str] = [
    'Which areas had higher agriculture, forestry, fishing, and hunting weekly wages in the first quarter of 1994 than in the first quarter of 1990, and how much did wages increase?',
    'Which areas gained agriculture, forestry, fishing, and hunting establishments between the first quarter of 1990 and the first quarter of 1994?',
    'Which areas had the single largest drop in agriculture, forestry, fishing, and hunting weekly wages between the second quarter of 1990 and the second quarter of 1994?',
    'Which areas had the same agriculture, forestry, fishing, and hunting establishment count in the third quarter of 1991 and the third quarter of 1993, but different weekly wages?',
    'Which areas had more agriculture, forestry, fishing, and hunting establishments in the fourth quarter of 1991 than in the fourth quarter of 1990, but lower weekly wages?',
    'Which areas had both higher agriculture, forestry, fishing, and hunting weekly wages and more establishments in the second quarter of 1992 than in the second quarter of 1991?',
    'Which areas had fewer agriculture, forestry, fishing, and hunting establishments but higher weekly wages in the third quarter of 1994 than in the third quarter of 1993?',
    'Which areas had agriculture, forestry, fishing, and hunting weekly wages in the fourth quarter of 1994 that were more than double their fourth-quarter 1990 wages?',
    'Which areas had the same agriculture, forestry, fishing, and hunting establishment count in the second quarter of 1992 and the second quarter of 1993, but a changed weekly wage?',
    'Which areas had both lower agriculture, forestry, fishing, and hunting weekly wages and fewer establishments in the first quarter of 1992 than in the first quarter of 1991?',
    'Which areas had above-average agriculture, forestry, fishing, and hunting weekly wages in the first quarter of 1990?',
    'Which areas had above-average agriculture, forestry, fishing, and hunting establishment counts but below-average weekly wages in the second quarter of 1990?',
    'Which areas had the ten highest agriculture, forestry, fishing, and hunting weekly wages in the third quarter of 1991?',
    'Which areas had the ten lowest agriculture, forestry, fishing, and hunting weekly wages in the fourth quarter of 1991?',
    'Which areas had above-average agriculture, forestry, fishing, and hunting establishment counts in the first quarter of 1992?',
    'Which areas had below-average agriculture, forestry, fishing, and hunting weekly wages but above-average establishment counts in the second quarter of 1992?',
    'Which areas had the five highest agriculture, forestry, fishing, and hunting establishment counts in the third quarter of 1992?',
    'Which areas had agriculture, forestry, fishing, and hunting weekly wages above 500 in the first quarter of 1991?',
    'Which areas had agriculture, forestry, fishing, and hunting weekly wages above 500 and at least 10 establishments in the fourth quarter of 1993?',
    'Which areas had agriculture, forestry, fishing, and hunting weekly wages below 300 in the second quarter of 1994?',
    'Which areas had the largest combined agriculture, forestry, fishing, and hunting establishment count across all four quarters of 1990?',
    'Which areas had their highest agriculture, forestry, fishing, and hunting weekly wage in the fourth quarter of 1990 compared with the other quarters of 1990?',
    'Which areas increased their agriculture, forestry, fishing, and hunting establishment count from quarter to quarter throughout 1990?',
    'Which areas increased their agriculture, forestry, fishing, and hunting weekly wages from quarter to quarter throughout 1990?',
    'Which areas decreased their agriculture, forestry, fishing, and hunting establishment count from quarter to quarter throughout 1990?',
    'Which areas had their highest agriculture, forestry, fishing, and hunting weekly wage in the second quarter of 1991 compared with the other quarters of 1991?',
    'Which areas had a 1991 total agriculture, forestry, fishing, and hunting establishment count above the average 1991 total across all areas?',
    'Which areas had a 1991 average agriculture, forestry, fishing, and hunting weekly wage above the overall 1991 average across all areas and quarters?',
    'Which areas had at least one 1991 quarter with agriculture, forestry, fishing, and hunting weekly wages below their own 1991 average?',
    'Which areas had their highest agriculture, forestry, fishing, and hunting establishment count in the third quarter of 1992 compared with the other quarters of 1992?',
    'Which areas had their lowest agriculture, forestry, fishing, and hunting weekly wage in the first quarter of 1992 compared with the other quarters of 1992?',
    'Which areas increased their agriculture, forestry, fishing, and hunting weekly wages from quarter to quarter throughout 1992?',
    'Which areas decreased their agriculture, forestry, fishing, and hunting establishment count from quarter to quarter throughout 1992?',
    'Which areas had more agriculture, forestry, fishing, and hunting establishments in the first half of 1993 than in the second half of 1993?',
    'Which areas had higher average agriculture, forestry, fishing, and hunting weekly wages in the second half of 1993 than in the first half of 1993?',
    'For each area, which quarter of 1994 had the highest agriculture, forestry, fishing, and hunting weekly wage?',
    'Which areas had higher agriculture, forestry, fishing, and hunting weekly wages in the fourth quarter of 1994 than in every earlier quarter of 1994?',
    'Which areas had fewer agriculture, forestry, fishing, and hunting establishments in the fourth quarter of 1994 than in every earlier quarter of 1994?',
    'Which areas had a higher total agriculture, forestry, fishing, and hunting establishment count in 1994 than in 1990?',
    'Which areas had a higher average agriculture, forestry, fishing, and hunting weekly wage in 1994 than in 1990?',
    'Which areas had agriculture, forestry, fishing, and hunting weekly wages rise every first quarter from 1990 through 1994?',
    'Which areas had agriculture, forestry, fishing, and hunting establishment counts rise every first quarter from 1990 through 1994?',
    'Which areas had agriculture, forestry, fishing, and hunting weekly wages fall every second quarter from 1990 through 1994?',
    'Which areas had agriculture, forestry, fishing, and hunting establishment counts rise every third quarter from 1990 through 1994?',
    'Which areas had their highest fourth-quarter agriculture, forestry, fishing, and hunting weekly wage in 1994 compared with the fourth quarters from 1990 through 1993?',
    'Which areas had their lowest first-quarter agriculture, forestry, fishing, and hunting establishment count in 1990 compared with the first quarters from 1991 through 1994?',
    'Which areas had agriculture, forestry, fishing, and hunting weekly wages in the second quarter of 1992 that were higher than both the second quarter of 1991 and the second quarter of 1993?',
    'Which areas had their highest third-quarter agriculture, forestry, fishing, and hunting establishment count in 1993 compared with the third quarters from 1990 through 1994?',
    'Which areas had agriculture, forestry, fishing, and hunting weekly wages dip in the fourth quarter of 1992 compared with both the fourth quarter of 1991 and the fourth quarter of 1993?',
    'Which areas had a second-quarter agriculture, forestry, fishing, and hunting establishment count in 1994 that was higher than every earlier second quarter from 1990 through 1993?',
    'Which areas had at least 25 percent growth in agriculture, forestry, fishing, and hunting weekly wages from the first quarter of 1990 to the first quarter of 1994?',
    'Which areas had at least 25 percent growth in agriculture, forestry, fishing, and hunting establishment counts from the first quarter of 1990 to the first quarter of 1994?',
    'Which areas had agriculture, forestry, fishing, and hunting establishment counts decline by at least half from the second quarter of 1990 to the second quarter of 1994?',
    'Which areas had agriculture, forestry, fishing, and hunting weekly wages increase by at least 100 from the third quarter of 1990 to the third quarter of 1994?',
    'Which areas had agriculture, forestry, fishing, and hunting establishment counts increase by at least 5 from the fourth quarter of 1990 to the fourth quarter of 1994?',
    'Which areas had first-quarter 1994 agriculture, forestry, fishing, and hunting weekly wages at least 25 percent higher than first-quarter 1990 wages?',
    'Which areas had first-quarter 1994 agriculture, forestry, fishing, and hunting establishment counts at least 25 percent lower than first-quarter 1990 counts?',
    'Which areas had agriculture, forestry, fishing, and hunting weekly wages in the fourth quarter of 1994 that were more than 100 higher than in the first quarter of 1994?',
    'Which areas had agriculture, forestry, fishing, and hunting establishment counts in the fourth quarter of 1994 that were at least 10 higher than in the first quarter of 1994?',
    'Which areas had agriculture, forestry, fishing, and hunting weekly wages in the second quarter of 1993 within 50 of their second-quarter 1990 wages?',
    'Which areas had above-average agriculture, forestry, fishing, and hunting weekly wages in both the first quarter of 1990 and the first quarter of 1994?',
    'Which areas moved from below-average agriculture, forestry, fishing, and hunting weekly wages in the first quarter of 1990 to above-average wages in the first quarter of 1994?',
    'Which areas moved from above-average agriculture, forestry, fishing, and hunting establishment counts in the first quarter of 1990 to below-average counts in the first quarter of 1994?',
    'Which areas had agriculture, forestry, fishing, and hunting weekly wages increase while establishment counts decreased from the first quarter of 1990 to the first quarter of 1994?',
    'Which areas had agriculture, forestry, fishing, and hunting establishment counts increase while weekly wages decreased from the first quarter of 1990 to the first quarter of 1994?',
    'Which areas had both agriculture, forestry, fishing, and hunting weekly wages and establishment counts increase from the first quarter of 1990 to the first quarter of 1994?',
    'Which areas had both agriculture, forestry, fishing, and hunting weekly wages and establishment counts decrease from the first quarter of 1990 to the first quarter of 1994?',
    'Which areas had the same agriculture, forestry, fishing, and hunting establishment count in the first quarter of 1990 and the first quarter of 1994, but different weekly wages?',
    'Which areas had the same agriculture, forestry, fishing, and hunting weekly wage in the first quarter of 1990 and the first quarter of 1994, but different establishment counts?',
    'Which areas had unchanged agriculture, forestry, fishing, and hunting weekly wages and unchanged establishment counts between the first quarter of 1990 and the first quarter of 1994?',
    'For each area, which quarter of 1990 had the highest agriculture, forestry, fishing, and hunting weekly wage?',
    'For each area, which quarter of 1990 had the lowest agriculture, forestry, fishing, and hunting establishment count?',
    'For each area, which year had the highest first-quarter agriculture, forestry, fishing, and hunting weekly wage from 1990 through 1994?',
    'For each area, which year had the lowest first-quarter agriculture, forestry, fishing, and hunting establishment count from 1990 through 1994?',
    'Which areas had agriculture, forestry, fishing, and hunting weekly wages in 1994 that were above the average of all their 1990 quarterly wages?',
    'Which areas had agriculture, forestry, fishing, and hunting establishment counts in the first quarter of 1994 above the average of their four 1990 quarterly establishment counts?',
    'Which areas had agriculture, forestry, fishing, and hunting weekly wages in every quarter of 1994 above 500?',
    'Which areas had agriculture, forestry, fishing, and hunting establishment counts in every quarter of 1994 above 10?',
    'Which areas had at least one quarter in 1994 with agriculture, forestry, fishing, and hunting weekly wages above 800?',
    'Which areas had at least one quarter in 1994 with agriculture, forestry, fishing, and hunting establishment counts below 5?',
    'Which areas had the largest spread between their highest and lowest agriculture, forestry, fishing, and hunting weekly wage in 1990?',
    'Which areas had the smallest spread between their highest and lowest agriculture, forestry, fishing, and hunting weekly wage in 1990?',
    'Which areas had the largest spread between their highest and lowest agriculture, forestry, fishing, and hunting establishment count in 1994?',
    'Which areas had the smallest spread between their highest and lowest agriculture, forestry, fishing, and hunting establishment count in 1994?',
    'Which areas had more total agriculture, forestry, fishing, and hunting establishments in 1992 than in both 1991 and 1993?',
    'Which areas had lower average agriculture, forestry, fishing, and hunting weekly wages in 1992 than in both 1991 and 1993?',
    'Which areas had agriculture, forestry, fishing, and hunting weekly wages that increased from 1990 to 1991 and again from 1991 to 1992 in the first quarter?',
    'Which areas had agriculture, forestry, fishing, and hunting establishment counts that decreased from 1992 to 1993 and again from 1993 to 1994 in the second quarter?',
    'Which areas had a larger agriculture, forestry, fishing, and hunting wage increase from 1990 Q1 to 1994 Q1 than from 1990 Q4 to 1994 Q4?',
    'Which areas had a larger agriculture, forestry, fishing, and hunting establishment increase from 1990 Q1 to 1994 Q1 than from 1990 Q4 to 1994 Q4?',
    'Which areas had their agriculture, forestry, fishing, and hunting weekly wages above the yearly average in every quarter of 1990?',
    'Which areas had their agriculture, forestry, fishing, and hunting establishment counts below the yearly average in every quarter of 1990?',
    'Which areas had agriculture, forestry, fishing, and hunting weekly wages above the quarter average in both the first quarter of 1991 and the first quarter of 1992?',
    'Which areas had agriculture, forestry, fishing, and hunting establishment counts below the quarter average in both the third quarter of 1993 and the third quarter of 1994?',
    'Which areas had a positive agriculture, forestry, fishing, and hunting wage increase from 1990 Q1 to 1994 Q1 but a negative establishment change over the same period?',
    'Which areas had a positive agriculture, forestry, fishing, and hunting establishment increase from 1990 Q1 to 1994 Q1 but a negative wage change over the same period?',
    'Which areas had agriculture, forestry, fishing, and hunting weekly wages in 1994 Q4 above the 1994 Q4 average and establishment counts below the 1994 Q4 average?',
    'Which areas had agriculture, forestry, fishing, and hunting establishment counts in 1994 Q4 above the 1994 Q4 average and weekly wages below the 1994 Q4 average?',
    'Which areas had the top 10 agriculture, forestry, fishing, and hunting wage increases from 1990 Q1 to 1994 Q1?',
    'Which areas had the top 10 agriculture, forestry, fishing, and hunting establishment increases from 1990 Q1 to 1994 Q1?',
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
        body = response.read().decode("utf-8")
        return json.loads(body)


def extract_sql(response: Dict[str, Any]) -> str:
    generated = response.get("generated_sql") or {}
    if isinstance(generated, dict):
        return generated.get("sql") or ""
    return ""


def extract_row_count(response: Dict[str, Any]) -> Any:
    execution = response.get("execution") or {}
    if isinstance(execution, dict):
        return execution.get("row_count")
    return None


def run_queries(base_url: str, database_id: int, timeout: int, delay: float) -> List[Dict[str, Any]]:
    endpoint = f"{base_url.rstrip('/')}/database/{database_id}/execute_sql"
    results: List[Dict[str, Any]] = []
    total = len(QUERIES)

    for index, question in enumerate(QUERIES, start=1):
        started = time.time()
        print(f"[{index:03d}/{total}] {question}")
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
                "selected_candidate_source": response.get("selected_candidate_source"),
                "selected_candidate_label": response.get("selected_candidate_label"),
                "selected_candidate_score": response.get("selected_candidate_score"),
                "low_confidence": response.get("low_confidence"),
                "elapsed_seconds": elapsed,
                "response": response,
            }
            status = "OK" if record["success"] else "FAIL"
            print(
                f"    {status} rows={record['row_count']} "
                f"source={record['extraction_source']} family={record['query_family']} "
                f"score={record['selected_candidate_score']} time={elapsed}s"
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
                "selected_candidate_source": None,
                "selected_candidate_label": None,
                "selected_candidate_score": None,
                "low_confidence": None,
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
                "selected_candidate_source": None,
                "selected_candidate_label": None,
                "selected_candidate_score": None,
                "low_confidence": None,
                "elapsed_seconds": elapsed,
                "error": repr(exc),
            }
            print(f"    ERROR: {exc!r}")

        results.append(record)
        if delay > 0 and index < total:
            time.sleep(delay)

    return results


def write_outputs(results: List[Dict[str, Any]], database_id: int, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"bq075_natural_100_results_db{database_id}_{timestamp}.json"
    md_path = output_dir / f"bq075_natural_100_results_db{database_id}_{timestamp}.md"

    summary = {
        "database_id": database_id,
        "total": len(results),
        "success_count": sum(1 for r in results if r.get("success")),
        "failure_count": sum(1 for r in results if not r.get("success")),
        "query_family_count": sum(1 for r in results if r.get("extraction_source") == "query_family"),
        "llm_count": sum(1 for r in results if r.get("extraction_source") == "llm"),
        "low_confidence_count": sum(1 for r in results if r.get("low_confidence")),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }

    json_path.write_text(
        json.dumps({"summary": summary, "results": results}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        f"# bq075 Natural 100 Query Results — database #{database_id}",
        "",
        "## Summary",
        "",
        f"- Total: {summary['total']}",
        f"- Success: {summary['success_count']}",
        f"- Failure: {summary['failure_count']}",
        f"- Query family path: {summary['query_family_count']}",
        f"- LLM path: {summary['llm_count']}",
        f"- Low confidence: {summary['low_confidence_count']}",
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
                f"- Selected source: `{record.get('selected_candidate_source')}`",
                f"- Selected label: `{record.get('selected_candidate_label')}`",
                f"- Selected score: `{record.get('selected_candidate_score')}`",
                f"- Low confidence: `{record.get('low_confidence')}`",
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
    parser = argparse.ArgumentParser(description="Run 100 natural-language bq075 benchmark queries.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--database-id", type=int, default=DEFAULT_DATABASE_ID)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--delay", type=float, default=0.0, help="Optional delay between requests in seconds.")
    parser.add_argument("--output-dir", default=".")
    args = parser.parse_args()

    if len(QUERIES) != 100:
        print(f"Expected 100 queries, found {len(QUERIES)}", file=sys.stderr)
        return 2

    results = run_queries(args.base_url, args.database_id, args.timeout, args.delay)
    write_outputs(results, args.database_id, Path(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
