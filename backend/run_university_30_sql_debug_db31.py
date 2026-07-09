#!/usr/bin/env python3
"""
SpiderSQL University Research 30-question debug runner.

Database:
- university_research: database_id 31

Run from the backend folder while FastAPI backend is running:
    cd C:\\Projects\\nl2sql-mvp\\backend
    python run_university_30_sql_debug_db31.py

It sends 30 natural-language questions to:
    POST /database/31/execute_sql

It prints generated SQL + metadata and saves JSON/Markdown results.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

BASE_URL = "http://127.0.0.1:8000"
DATABASE_ID = 31
DATABASE_NAME = "university_research"
TIMEOUT_SECONDS = 120

QUESTIONS: List[str] = [
    "List active high-risk projects led by non-tenured faculty.",
    "Find departments where every faculty member has at least one project.",
    "List projects whose total approved expenses exceed their total awarded grant amount.",
    "Find faculty who advise PhD students but are not members of any active project.",
    "For each department, list the project with the highest total grant funding, including ties.",
    "Find projects with no publications but at least one federal grant.",
    "List students working on projects outside their own department.",
    "Find sponsors that fund projects in all colleges represented in the departments table.",
    "List equipment bought for projects whose lead faculty works in a different lab city than the department city.",
    "Find projects where every milestone is completed or late, with no pending milestones.",
    "Find faculty whose projects have more distinct student members than faculty members.",
    "List projects funded by industry sponsors but with no approved software expenses.",
    "Find students whose advisor leads a project that the student is also a member of.",
    "Find departments where the average impact score of publications is above the overall average publication impact score.",
    "List grants whose approved expenses are less than half of the awarded amount.",
    "Find project pairs in the same field that are led by faculty from different departments.",
    "List faculty who have open access publications but no equipment marked as shared on their led projects.",
    "Find active projects whose latest milestone is pending.",
    "Find departments whose students have participated in all project fields represented in projects.",
    "List projects that have critical risk level and at least one unapproved expense.",
    "List faculty who lead active projects but advise no PhD students.",
    "Find projects where total equipment cost is greater than total approved equipment expenses charged to the project.",
    "Find departments where every active project has at least one active grant.",
    "List students whose GPA is above the average GPA of students in their own department and who work on at least one high-risk project.",
    "Find projects where total student effort percent is greater than total faculty effort percent.",
    "Find grants whose latest expense is unapproved.",
    "List pairs of faculty in the same department who are members of the same project.",
    "Find projects with publications after the end date of at least one grant for that project.",
    "List sponsors whose total awarded amount is above the average total awarded amount per sponsor.",
    "Find equipment categories used by projects in every department.",
]

try:
    from benchmarks.run_meta import candidate_meta, format_candidates, repair_meta, format_repair
except Exception as exc:  # pragma: no cover
    print(f"NOTE: candidate metadata unavailable ({exc})")

    def candidate_meta(response: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "selected_candidate_source": response.get("selected_candidate_source"),
            "selection_reason": response.get("selection_reason"),
            "candidate_count": response.get("candidate_count"),
            "warnings": response.get("warnings") or [],
            "candidates": [],
        }

    def format_candidates(meta: Dict[str, Any]) -> List[str]:
        return [f"SELECTED: {meta.get('selected_candidate_source')} (reason={meta.get('selection_reason')})"]

    def repair_meta(response: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "repair_attempted": bool(response.get("repair_attempted")),
            "repair_selected": bool(response.get("repair_selected")),
        }

    def format_repair(meta: Dict[str, Any]) -> str:
        if not meta.get("repair_attempted"):
            return "REPAIR: not attempted"
        return f"REPAIR: attempted | selected={meta.get('repair_selected')}"


def post_query(question: str) -> Dict[str, Any]:
    url = f"{BASE_URL}/database/{DATABASE_ID}/execute_sql"
    payload = json.dumps({"question": question}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.time()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body)
            data["_http_status"] = response.status
            data["_elapsed_seconds"] = round(time.time() - start, 3)
            return data
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        return {
            "success": False,
            "_http_status": exc.code,
            "_elapsed_seconds": round(time.time() - start, 3),
            "_http_error": exc.reason,
            "_error_body": error_body,
        }
    except Exception as exc:
        return {
            "success": False,
            "_http_status": None,
            "_elapsed_seconds": round(time.time() - start, 3),
            "_exception": repr(exc),
        }


def get_nested(data: Dict[str, Any], path: List[str], default: Any = None) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def sql_flags(sql: str) -> Dict[str, bool]:
    s = (sql or "").upper()
    return {
        "has_with_cte": "WITH " in s,
        "has_not_exists": "NOT EXISTS" in s,
        "has_left_join": "LEFT JOIN" in s,
        "has_inner_join": "INNER JOIN" in s or " JOIN " in s,
        "has_count_distinct": "COUNT(DISTINCT" in s,
        "has_group_by": "GROUP BY" in s,
        "has_having": "HAVING" in s,
        "has_window": "ROW_NUMBER()" in s or "RANK()" in s or "DENSE_RANK()" in s or " OVER " in s,
        "has_null_filter": " IS NULL" in s or " IS NOT NULL" in s,
        "has_self_alias_hint": " P1" in s or " P2" in s or " F1" in s or " F2" in s or "__G" in s,
    }


def summarize_response(idx: int, question: str, response: Dict[str, Any]) -> Dict[str, Any]:
    sql = get_nested(response, ["generated_sql", "sql"], "") or ""
    execution = response.get("execution") if isinstance(response.get("execution"), dict) else {}
    error = response.get("error") or response.get("detail") or response.get("_http_error") or response.get("_exception")
    if not error and not response.get("success", False):
        error = (
            get_nested(response, ["execution", "error"])
            or get_nested(response, ["generated_sql", "error"])
            or response.get("_error_body")
            or "success=false but no explicit error field found"
        )
    status = "EXEC_OK" if response.get("success") else "EXEC_FAIL"
    if response.get("_http_status") and response.get("_http_status") >= 400:
        status = f"HTTP_ERROR_{response.get('_http_status')}"
    return {
        "database_name": DATABASE_NAME,
        "database_id": DATABASE_ID,
        "query_number": idx,
        "question": question,
        "status": status,
        "success": bool(response.get("success")),
        "row_count": execution.get("row_count"),
        "elapsed_seconds": response.get("_elapsed_seconds"),
        "extraction_source": response.get("extraction_source"),
        "selected_candidate_source": response.get("selected_candidate_source"),
        "selection_reason": response.get("selection_reason"),
        "query_family": response.get("query_family"),
        "query_family_confidence": response.get("query_family_confidence"),
        "query_family_reason": response.get("query_family_reason"),
        "family_guard_valid": response.get("family_guard_valid"),
        "family_guard_reasons": response.get("family_guard_reasons"),
        "repair": repair_meta(response),
        "candidates": candidate_meta(response),
        "warnings": response.get("warnings") or [],
        "sql": sql,
        "params": get_nested(response, ["generated_sql", "params"], []) or [],
        "flags": sql_flags(sql),
        "error": error,
        "full_response": response,
    }


def print_result(item: Dict[str, Any]) -> None:
    print("=" * 100)
    print(f"{item['database_name']} | DB {item['database_id']} | Q{item['query_number']:02d}")
    print(f"QUESTION: {item['question']}")
    print(
        "STATUS: {status} | rows={rows} | source={source} | selected={selected} | family={family} | conf={conf} | time={time}s".format(
            status=item["status"],
            rows=item["row_count"],
            source=item["extraction_source"],
            selected=item["selected_candidate_source"],
            family=item["query_family"],
            conf=item["query_family_confidence"],
            time=item["elapsed_seconds"],
        )
    )
    print(f"REASON: {item.get('query_family_reason')}")
    if item.get("family_guard_reasons"):
        print("GUARD_REASONS: " + json.dumps(item["family_guard_reasons"], ensure_ascii=False))
    print("FLAGS: " + json.dumps(item["flags"], sort_keys=True))
    for line in format_candidates(item.get("candidates") or {}):
        print(line)
    print(format_repair(item.get("repair") or {}))
    if item.get("warnings"):
        for warning in item["warnings"]:
            print(f"WARNING: {warning}")
    if item.get("error"):
        print(f"ERROR: {item['error']}")
    print("SQL:")
    print(item["sql"] or "-- NO SQL GENERATED")


def build_summary(results: List[Dict[str, Any]], timestamp: str) -> Dict[str, Any]:
    selected_sources = Counter(item.get("selected_candidate_source") or item.get("extraction_source") for item in results)
    family_count = sum(1 for item in results if item.get("selected_candidate_source") == "query_family")
    repair_attempted = [item for item in results if (item.get("repair") or {}).get("repair_attempted")]
    repair_selected = [item for item in results if (item.get("repair") or {}).get("repair_selected")]
    return {
        "database_name": DATABASE_NAME,
        "database_id": DATABASE_ID,
        "total": len(results),
        "exec_ok_count": sum(1 for item in results if item["status"] == "EXEC_OK"),
        "exec_fail_count": sum(1 for item in results if item["status"] != "EXEC_OK"),
        "query_family_count": family_count,
        "llm_count": len(results) - family_count,
        "no_sql_count": sum(1 for item in results if not item.get("sql")),
        "repair_attempted_count": len(repair_attempted),
        "repair_selected_count": len(repair_selected),
        "repair_selected_queries": [item["query_number"] for item in repair_selected],
        "selected_source_breakdown": dict(selected_sources),
        "generated_at": timestamp,
    }


def write_outputs(results: List[Dict[str, Any]], summary: Dict[str, Any], timestamp: str) -> None:
    json_path = Path(f"university_30_sql_debug_db31_{timestamp}.json")
    md_path = Path(f"university_30_sql_debug_db31_{timestamp}.md")

    json_path.write_text(json.dumps({"summary": summary, "results": results}, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# SpiderSQL University Research 30-Question Debug Results", ""]
    lines.append("## Summary")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(summary, indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")

    for item in results:
        lines.append(f"## Q{item['query_number']:02d}")
        lines.append("")
        lines.append(f"**Question:** {item['question']}")
        lines.append("")
        lines.append(
            f"**Status:** {item['status']} | rows={item['row_count']} | selected={item['selected_candidate_source']} | "
            f"family={item['query_family']} | conf={item['query_family_confidence']} | time={item['elapsed_seconds']}s"
        )
        lines.append("")
        if item.get("warnings"):
            lines.append("**Warnings:**")
            for warning in item["warnings"]:
                lines.append(f"- {warning}")
            lines.append("")
        if item.get("error"):
            lines.append(f"**Error:** {item['error']}")
            lines.append("")
        lines.append("**SQL:**")
        lines.append("```sql")
        lines.append(item.get("sql") or "-- NO SQL GENERATED")
        lines.append("```")
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n" + "=" * 100)
    print("Saved:")
    print(f"  JSON: {json_path}")
    print(f"  Markdown: {md_path}")


def main() -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results: List[Dict[str, Any]] = []
    for idx, question in enumerate(QUESTIONS, start=1):
        response = post_query(question)
        item = summarize_response(idx, question, response)
        results.append(item)
        print_result(item)

    summary = build_summary(results, timestamp)
    write_outputs(results, summary, timestamp)
    print("\nSummary:")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
