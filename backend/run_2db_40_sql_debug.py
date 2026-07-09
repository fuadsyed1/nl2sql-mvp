#!/usr/bin/env python3
"""
SpiderSQL 2-database debug runner.

Databases:
- clinic_multiple_csv: database_id 29
- cybersecurity_incidents_schema: database_id 30

Run from backend folder while FastAPI backend is running:
    cd C:\\Projects\\nl2sql-mvp\\backend
    python run_2db_40_sql_debug.py

It prints SQL + metadata only, and saves JSON/Markdown results.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

BASE_URL = "http://127.0.0.1:8000"
TIMEOUT_SECONDS = 90
GOLD_BENCHMARKS = {29: "clinic_20", 30: "cyber_20"}

try:  # gold grading + candidate metadata (optional, never breaks the run)
    from benchmarks.gold_eval import grade as gold_grade
    from benchmarks.run_meta import (candidate_meta, format_candidates,
                                     format_gold, repair_meta, format_repair)
except Exception as _exc:  # pragma: no cover
    print(f"NOTE: gold grading unavailable ({_exc})")
    gold_grade = None

    def candidate_meta(response):
        return {"selected_candidate_source": response.get("selected_candidate_source"),
                "selection_reason": response.get("selection_reason"),
                "candidate_count": response.get("candidate_count"),
                "warnings": response.get("warnings") or [], "candidates": []}

    def format_candidates(meta):
        return [f"SELECTED: {meta['selected_candidate_source']}"]

    def format_gold(g):
        return "GOLD: (not graded)"

    def repair_meta(response):
        return {"repair_attempted": bool(response.get("repair_attempted"))}

    def format_repair(meta):
        return "REPAIR: (unavailable)"

DATABASES = [
    {
        "name": "clinic_multiple_csv",
        "database_id": 29,
        "queries": [
            "List patients whose latest appointment was cancelled but who have at least one unpaid invoice from an earlier appointment.",
            "Find doctors who treated patients from a different city and whose average invoice total is higher than the average invoice total for doctors in the same specialty.",
            "List patients who were prescribed a controlled substance but have no lab result marked high for the appointment where it was prescribed.",
            "Find visit types where the same doctor handled both the lowest base fee and the highest base fee appointment of that visit type.",
            "List medications that were prescribed to patients with chronic conditions but never prescribed during urgent visits.",
            "Find patients whose total unpaid invoice amount is greater than the total amount paid by insurance for their completed appointments.",
            "List doctors who have appointments with every insurance provider represented in the patients table.",
            "Find patients whose prescription days_supply is higher than every other prescription for the same medication class.",
            "List pairs of patients in the same city who saw the same doctor on different appointment dates.",
            "Find appointments where the patient city is different from the doctor clinic city and the invoice is unpaid.",
            "List medications where the most expensive medication in each class was never prescribed, but a cheaper medication from the same class was prescribed.",
            "Find patients who had a low lab result after receiving a prescription with refill allowed.",
            "List doctors whose patients had more distinct abnormal lab test names than the number of distinct medication classes they prescribed.",
            "Find patients who have appointments but have never received a prescription for any medication class marked controlled substance.",
            "List the highest total invoice patient for each city, including ties.",
            "Find patients whose latest lab result was high and whose doctor for that appointment has less than five years of experience.",
            "List appointments with no prescription but with at least one lab result and an unpaid invoice.",
            "Find doctors who have treated all visit types represented in the appointments table.",
            "List patients who were prescribed the same medication class by two different doctors.",
            "Find medication classes where patients with chronic conditions received more prescriptions than patients without chronic conditions.",
        ],
    },
    {
        "name": "cybersecurity_incidents_schema",
        "database_id": 30,
        "queries": [
            "List employees whose devices have unresolved critical alerts but who have no passed security training record.",
            "Find device types where the same employee owns both the most vulnerable and least vulnerable device of that type by vulnerability count.",
            "List devices with vulnerabilities that have an exploit available but no incident has been linked to any alert from that device.",
            "Find departments whose employees have devices affected by all severity levels represented in the vulnerabilities table.",
            "List employees whose average device risk score is above the average risk score of employees in their own department.",
            "Find vulnerabilities that appear on more distinct operating system families than the number of distinct departments with trained employees.",
            "List pairs of devices owned by different employees in the same office city that share the same CVE code.",
            "Find employees who opened incidents after their device's last patch date but before their latest unresolved alert time.",
            "List devices that have never had a false positive vulnerability record but have at least one unresolved alert.",
            "Find incident types where the highest impact incident was opened by an employee with no encrypted device.",
            "List employees whose manager has a lower risk score but whose devices have higher average CVSS score than the manager's devices.",
            "Find devices whose latest alert is unresolved and whose vulnerability with the highest CVSS score has not been remediated.",
            "List employees who have devices with all vulnerability severities but have not passed every security training course.",
            "Find office cities where every employee either has no device or has at least one encrypted device.",
            "List CVE codes where the highest CVSS occurrence was never remediated but a lower CVSS occurrence was remediated.",
            "Find employees whose devices triggered more distinct alert types than the number of distinct courses they passed.",
            "List incidents whose alerts come from devices owned by employees in a different office city than the employee who opened the incident.",
            "Find devices with no vulnerabilities but with at least one high severity alert.",
            "List employees where every device they own has been patched after all vulnerabilities on that device were detected.",
            "Find departments where the same manager supervises both the highest risk and lowest risk employee in that department.",
        ],
    },
]


def post_query(database_id: int, question: str) -> Dict[str, Any]:
    url = f"{BASE_URL}/database/{database_id}/execute_sql"
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
        "has_count_distinct": "COUNT(DISTINCT" in s,
        "has_group_by": "GROUP BY" in s,
        "has_having": "HAVING" in s,
        "has_null_filter": " IS NULL" in s or " IS NOT NULL" in s,
        "has_self_alias_hint": "__G" in s or " AS \"P1\"" in s or " AS \"P2\"" in s,
        "has_inner_join": "INNER JOIN" in s,
    }


def summarize_response(database_name: str, database_id: int, idx: int, question: str, response: Dict[str, Any]) -> Dict[str, Any]:
    sql = get_nested(response, ["generated_sql", "sql"], "") or ""
    execution = response.get("execution") if isinstance(response.get("execution"), dict) else {}
    error = response.get("error") or response.get("detail") or response.get("_http_error") or response.get("_exception")
    if not error and not response.get("success", False):
        error = get_nested(response, ["execution", "error"]) or get_nested(response, ["generated_sql", "error"]) or response.get("_error_body") or "success=false but no explicit error field found"
    status = "EXEC_OK" if response.get("success") else "EXEC_FAIL"
    if response.get("_http_status") and response.get("_http_status") >= 400:
        status = f"HTTP_ERROR_{response.get('_http_status')}"
    cand_meta = candidate_meta(response)
    bench = GOLD_BENCHMARKS.get(database_id)
    params = get_nested(response, ["generated_sql", "params"]) or []
    gold = (gold_grade(bench, idx, question, sql, params)
            if (gold_grade and bench) else None)
    return {
        "candidates": cand_meta,
        "repair": repair_meta(response),
        "gold": gold,
        "database_name": database_name,
        "database_id": database_id,
        "query_number": idx,
        "question": question,
        "status": status,
        "success": bool(response.get("success")),
        "row_count": execution.get("row_count"),
        "elapsed_seconds": response.get("_elapsed_seconds"),
        "extraction_source": response.get("extraction_source"),
        "query_family": response.get("query_family"),
        "query_family_confidence": response.get("query_family_confidence"),
        "query_family_reason": response.get("query_family_reason"),
        "family_guard_valid": response.get("family_guard_valid"),
        "family_guard_reasons": response.get("family_guard_reasons"),
        "sql": sql,
        "flags": sql_flags(sql),
        "error": error,
        "full_response": response,
    }


def print_result(item: Dict[str, Any]) -> None:
    print("=" * 100)
    print(f"{item['database_name']} | DB {item['database_id']} | Q{item['query_number']:02d}")
    print(f"QUESTION: {item['question']}")
    print(
        "STATUS: {status} | rows={rows} | source={source} | family={family} | conf={conf} | guard={guard} | time={time}s".format(
            status=item["status"],
            rows=item["row_count"],
            source=item["extraction_source"],
            family=item["query_family"],
            conf=item["query_family_confidence"],
            guard=item["family_guard_valid"],
            time=item["elapsed_seconds"],
        )
    )
    print(f"REASON: {item['query_family_reason']}")
    if item.get("family_guard_reasons"):
        print("GUARD_REASONS: " + json.dumps(item["family_guard_reasons"], ensure_ascii=False))
    print("FLAGS: " + json.dumps(item["flags"], sort_keys=True))
    for line in format_candidates(item.get("candidates") or candidate_meta({})):
        print(line)
    print(format_repair(item.get("repair")))
    print(format_gold(item.get("gold")))
    if item["error"]:
        print(f"ERROR: {item['error']}")
    print("SQL:")
    print(item["sql"] or "-- NO SQL GENERATED")


def write_outputs(results: List[Dict[str, Any]], timestamp: str) -> None:
    json_path = Path(f"spidersql_2db_40_sql_debug_{timestamp}.json")
    md_path = Path(f"spidersql_2db_40_sql_debug_{timestamp}.md")

    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# SpiderSQL 2-Database SQL Debug Results", ""]
    for item in results:
        lines.append(f"## {item['database_name']} DB {item['database_id']} Q{item['query_number']:02d}")
        lines.append("")
        lines.append(f"**Question:** {item['question']}")
        lines.append("")
        lines.append(
            f"**Status:** {item['status']} | rows={item['row_count']} | source={item['extraction_source']} | "
            f"family={item['query_family']} | conf={item['query_family_confidence']} | guard={item['family_guard_valid']} | "
            f"time={item['elapsed_seconds']}s"
        )
        lines.append("")
        if item.get("query_family_reason"):
            lines.append(f"**Reason:** {item['query_family_reason']}")
            lines.append("")
        if item.get("family_guard_reasons"):
            lines.append("**Guard reasons:**")
            for reason in item["family_guard_reasons"]:
                lines.append(f"- {reason}")
            lines.append("")
        lines.append("**Flags:**")
        lines.append("```json")
        lines.append(json.dumps(item["flags"], indent=2, sort_keys=True))
        lines.append("```")

        lines.append("")
        for line in format_candidates(item.get("candidates") or candidate_meta({})):
            lines.append(line)
        lines.append("")
        lines.append(format_repair(item.get("repair")))
        lines.append("")
        lines.append(format_gold(item.get("gold")))
        lines.append("")
        lines.append("**SQL:**")
        lines.append("```sql")
        lines.append(item.get("sql") or "-- NO SQL GENERATED")
        lines.append("```")
        lines.append("")
        if item.get("error"):
            lines.append("**Error:**")
            lines.append("```text")
            lines.append(str(item["error"]))
            lines.append("```")
            lines.append("")

    summary = build_summary(results)

    lines.append("## Summary")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(summary, indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    print("\n" + "=" * 100)
    print("Saved:")
    print(f"  JSON: {json_path}")
    print(f"  Markdown: {md_path}")
    print("\nSummary:")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def build_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    def is_semantic_ok(item: Dict[str, Any]) -> bool:
        gold = item.get("gold") or {}
        return bool(gold.get("semantic_ok"))

    def is_strict_ok(item: Dict[str, Any]) -> bool:
        gold = item.get("gold") or {}
        level = gold.get("match_level") or gold.get("level")
        return level in ("strict", "column_order")

    def repair_attempted(item: Dict[str, Any]) -> bool:
        repair = item.get("repair") or {}
        return bool(repair.get("repair_attempted"))

    def repair_selected(item: Dict[str, Any]) -> bool:
        repair = item.get("repair") or {}
        return bool(repair.get("repair_selected"))

    def selected_source(item: Dict[str, Any]) -> str:
        cand = item.get("candidates") or {}
        return cand.get("selected_candidate_source") or item.get("extraction_source") or "unknown"

    def fatal_won(item: Dict[str, Any]) -> bool:
        cand = item.get("candidates") or {}
        selected = cand.get("selected_candidate_source")
        for candidate in cand.get("candidates") or []:
            if candidate.get("source") == selected and candidate.get("fatal"):
                return True
        warnings = cand.get("warnings") or []
        return any("failed hard semantic checks" in str(w).lower() for w in warnings)

    selected_breakdown: Dict[str, int] = {}
    for item in results:
        src = selected_source(item)
        selected_breakdown[src] = selected_breakdown.get(src, 0) + 1

    gold_wrong = []
    fatal_candidate_won = []
    repair_selected_queries = []
    for item in results:
        ident = [item.get("database_name"), item.get("query_number")]
        if item.get("gold") is not None and not is_semantic_ok(item):
            gold_wrong.append(ident)
        if fatal_won(item):
            fatal_candidate_won.append(ident)
        if repair_selected(item):
            repair_selected_queries.append(ident)

    return {
        "repair_attempted_count": sum(1 for r in results if repair_attempted(r)),
        "repair_selected_count": sum(1 for r in results if repair_selected(r)),
        "repair_selected_queries": repair_selected_queries,
        "total": len(results),
        "exec_ok_count": sum(1 for r in results if r.get("success")),
        "exec_fail_count": sum(1 for r in results if not r.get("success")),
        "query_family_count": sum(1 for r in results if selected_source(r) == "query_family"),
        "llm_count": sum(1 for r in results if selected_source(r) != "query_family"),
        "no_sql_count": sum(1 for r in results if not r.get("sql")),
        "gold_graded": sum(1 for r in results if r.get("gold") is not None),
        "gold_semantic_ok": sum(1 for r in results if is_semantic_ok(r)),
        "gold_strict_ok": sum(1 for r in results if is_strict_ok(r)),
        "gold_wrong": gold_wrong,
        "selected_source_breakdown": selected_breakdown,
        "fatal_candidate_won": fatal_candidate_won,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def main() -> int:
    results: List[Dict[str, Any]] = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for db in DATABASES:
        database_name = db["name"]
        database_id = db["database_id"]
        queries = db["queries"]

        for idx, question in enumerate(queries, start=1):
            response = post_query(database_id, question)
            item = summarize_response(database_name, database_id, idx, question, response)
            results.append(item)
            print_result(item)

    write_outputs(results, timestamp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
