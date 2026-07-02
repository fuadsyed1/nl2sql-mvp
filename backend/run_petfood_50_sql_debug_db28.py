"""
Run all 50 petfood benchmark queries against SpiderSQL database_id=28,
printing ONLY the generated SQL plus compact debug metadata needed to diagnose failures.

Usage from backend folder while FastAPI is running:
    cd C:\Projects\nl2sql-mvp\backend
    python run_petfood_50_sql_debug_db28.py

Optional:
    python run_petfood_50_sql_debug_db28.py --base-url http://127.0.0.1:8000 --database-id 28

Outputs:
    petfood_50_sql_debug_db28_<timestamp>.json
    petfood_50_sql_debug_db28_<timestamp>.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_DATABASE_ID = 28
GOLD_BENCHMARK = "petfood_50"

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

QUERIES: List[str] = [
    "List all owners in Moscow, Idaho who have the lowest annual income among Moscow owners, and among those lowest-income owners return only the owner or owners with the largest number of pets.",
    "List all pet owners and their pets who do not live at the same address, using an outer join so owners without pets are still visible.",
    "List pets who never ate any food whose food type and flavor match a food type and flavor they actively love.",
    "List the brands and food names each pet could potentially eat if their owner has bought that food type for the pet's species and the pet has no allergy note for that flavor.",
    "List the highest priced food for each brand without using GROUP BY; use a correlated subquery or anti-join style condition.",
    "Find owners who bought food for a species they do not own, and list the mismatched food species beside the species of their pets.",
    "For every owner, list the pet that ate the lowest percentage of served food, but include owners whose pets have no feeding history.",
    "List pets whose owners bought a food brand that matches the pet's preferred brand, but the pet was never actually fed any food from that brand.",
    "Find food brands where every purchased food item from that brand was bought by owners outside Moscow, Idaho.",
    "List owners whose total spending is above the average spending of owners in their own city, without using GROUP BY in the outer query.",
    "Find pets that have at least two loved food profiles but were fed fewer than two distinct food brands.",
    "List foods that were purchased by an owner but are incompatible with every pet owned by that owner based on species_target.",
    "For each species, list the most expensive food that has been purchased at least once and has stock below the median stock for that species.",
    "List owners who live in the same city as a store where they bought food, but whose pets were fed that food in a different location than home.",
    "Find pets who have been fed only foods with allergen_flag = 'no', but have at least one liked profile with allergy_note not equal to 'none'.",
    "List pairs of pets owned by the same owner where both love the same flavor but have never been fed the same food_id.",
    "Find owners whose pets have consumed foods from more brands than the owner has directly purchased.",
    "List foods that are the cheapest within their food_type but are still more expensive than the average food purchased by Moscow owners.",
    "Find pets that love a brand but whose owner bought a different brand with the same food_type and flavor.",
    "List owners who bought the highest total quantity of food for each city, including ties.",
    "Find owners who have at least one pet with no matching active like record and at least one purchase of a food targeted to that pet's species.",
    "List pet-food pairs where the pet loves the food's flavor and food_type, the food matches species_target, and the owner has never bought that exact food.",
    "Find brands that have food for all species represented in the pets table.",
    "List owners whose pets were fed more total servings than the total quantity of food the owner purchased.",
    "Find pets whose favorite brand is the same as the most expensive brand their owner has purchased.",
    "List foods never purchased but still fed to at least one pet, with the pet and owner names.",
    "Find owners where every pet they own has been fed at least one food matching that pet's species.",
    "List pets whose owner bought food after the pet's adoption date, but the pet was fed before the owner's first purchase date.",
    "Find the second highest priced food within each brand without using LIMIT in a subquery.",
    "List cities where every owner has either no pets or has bought at least one food item.",
    "Find owners with pets at different addresses and whose highest single purchase total is below the average purchase total for their city.",
    "List foods that are loved by at least one pet by flavor/type but rejected in feeding history by another pet with notes = 'refused'.",
    "Find pets whose loved flavor appears in foods bought by their owner, but only in foods targeted to a different species.",
    "List owners who bought food from at least three brands and whose pets were fed food from fewer brands than that.",
    "Find foods whose price is higher than every other food with the same food_type and species_target.",
    "List pet owners whose pets' feeding history includes a food the owner never purchased.",
    "Find active liked profiles where no available food matches preferred_brand, food_type, flavor, and pet species.",
    "List owners whose pets have eaten all food_types that the owner has purchased.",
    "Find pets with no feeding history but whose owner has purchased at least one food compatible with the pet species.",
    "List the owner, pet, and food for cases where the pet ate less than 50 percent of a food that it should love by matching type and flavor.",
    "Find brands that are purchased by the lowest-income Moscow owners but are not purchased by any highest-income Moscow owners.",
    "List owners for whom the most expensive purchased food is incompatible with every pet they own.",
    "Find pet pairs from different owners who live at the same pet address and love the same preferred brand.",
    "List foods that could be recommended to a pet because the pet loves the type/flavor and another pet of the same species ate it above 90 percent.",
    "Find owners whose pets collectively love more distinct flavors than the number of distinct flavors the owner has purchased.",
    "List brands where the highest priced item was never purchased but a lower priced item from the same brand was purchased.",
    "Find owners who have pets but have never purchased a food matching any of their pets' species.",
    "List pets whose latest feeding was not vet approved and whose owner has purchased a vet-approved-compatible food type based on another feeding record.",
    "Find food types where the same owner both purchased the cheapest and the most expensive food of that type.",
    "List owners, pets, and loved food profiles where an outer join shows no matching purchased food by brand, food_type, and flavor.",
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


def sql_flags(sql: str) -> Dict[str, bool]:
    upper = sql.upper()
    return {
        "has_with_cte": "WITH " in upper,
        "has_not_exists": "NOT EXISTS" in upper,
        "has_left_join": "LEFT JOIN" in upper,
        "has_count_distinct": "COUNT(DISTINCT" in upper,
        "has_group_by": "GROUP BY" in upper,
        "has_having": "HAVING" in upper,
        "has_self_alias_hint": bool(re.search(r' AS "?[A-Za-z0-9_]+__(G|g)\d+"?', sql)),
        "has_null_filter": " IS NULL" in upper or " IS NOT NULL" in upper,
    }


def short_error(response: Dict[str, Any]) -> str:
    # Keep errors compact but useful. Different versions put error fields in different places.
    candidates = [
        response.get("error"),
        response.get("message"),
        response.get("detail"),
        (response.get("execution") or {}).get("error") if isinstance(response.get("execution"), dict) else None,
        (response.get("generated_sql") or {}).get("error") if isinstance(response.get("generated_sql"), dict) else None,
    ]
    for item in candidates:
        if item:
            return str(item)
    if response.get("success") is False:
        return "success=false but no explicit error field found"
    return ""


def run_queries(base_url: str, database_id: int, timeout: int, delay: float) -> List[Dict[str, Any]]:
    endpoint = f"{base_url.rstrip('/')}/database/{database_id}/execute_sql"
    results: List[Dict[str, Any]] = []

    for index, question in enumerate(QUERIES, start=1):
        started = time.time()
        print("=" * 100)
        print(f"Q{index:02d}")
        print(f"QUESTION: {question}")
        try:
            response = post_json(endpoint, {"question": question}, timeout=timeout)
            elapsed = round(time.time() - started, 3)
            sql = extract_sql(response)
            flags = sql_flags(sql)
            cand_meta = candidate_meta(response)
            rep_meta = repair_meta(response)
            params = ((response.get("generated_sql") or {}).get("params")
                      if isinstance(response.get("generated_sql"), dict) else None)
            gold = (gold_grade(GOLD_BENCHMARK, index, question, sql, params)
                    if gold_grade else None)
            record = {
                "index": index,
                "question": question,
                "success": response.get("success"),
                "row_count": extract_row_count(response),
                "extraction_source": response.get("extraction_source"),
                "query_family": response.get("query_family"),
                "query_family_confidence": response.get("query_family_confidence"),
                "query_family_reason": response.get("query_family_reason"),
                "elapsed_seconds": elapsed,
                "sql": sql,
                "sql_flags": flags,
                "error": short_error(response),
                "candidates": cand_meta,
                "repair": rep_meta,
                "gold": gold,
                "response": response,
            }

            status = "EXEC_OK" if response.get("success") else "EXEC_FAIL"
            print(
                f"STATUS: {status} | rows={record['row_count']} | "
                f"source={record['extraction_source']} | family={record['query_family']} | "
                f"conf={record['query_family_confidence']} | time={elapsed}s"
            )
            print(f"REASON: {record['query_family_reason']}")
            print("FLAGS:", json.dumps(flags, sort_keys=True))
            for line in format_candidates(cand_meta):
                print(line)
            print(format_repair(rep_meta))
            print(format_gold(gold))
            if record["error"]:
                print(f"ERROR: {record['error']}")
            print("SQL:")
            print(sql or "-- NO SQL GENERATED")
        except urllib.error.HTTPError as exc:
            elapsed = round(time.time() - started, 3)
            error_body = exc.read().decode("utf-8", errors="replace")
            record = {
                "index": index,
                "question": question,
                "success": False,
                "row_count": None,
                "extraction_source": None,
                "query_family": None,
                "query_family_confidence": None,
                "query_family_reason": None,
                "elapsed_seconds": elapsed,
                "sql": "",
                "sql_flags": {},
                "error": f"HTTP {exc.code}: {error_body}",
            }
            print(f"STATUS: HTTP_ERROR_{exc.code} | time={elapsed}s")
            print(f"ERROR: {error_body}")
            print("SQL:")
            print("-- NO SQL GENERATED")
        except Exception as exc:
            elapsed = round(time.time() - started, 3)
            record = {
                "index": index,
                "question": question,
                "success": False,
                "row_count": None,
                "extraction_source": None,
                "query_family": None,
                "query_family_confidence": None,
                "query_family_reason": None,
                "elapsed_seconds": elapsed,
                "sql": "",
                "sql_flags": {},
                "error": repr(exc),
            }
            print(f"STATUS: REQUEST_ERROR | time={elapsed}s")
            print(f"ERROR: {exc!r}")
            print("SQL:")
            print("-- NO SQL GENERATED")

        results.append(record)
        if delay > 0 and index < len(QUERIES):
            time.sleep(delay)

    return results


def write_outputs(results: List[Dict[str, Any]], database_id: int, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"petfood_50_sql_debug_db{database_id}_{timestamp}.json"
    md_path = output_dir / f"petfood_50_sql_debug_db{database_id}_{timestamp}.md"

    def _src(r):
        return (r.get("candidates") or {}).get("selected_candidate_source") \
            or r.get("extraction_source")

    source_breakdown: Dict[str, int] = {}
    for r in results:
        source_breakdown[str(_src(r))] = source_breakdown.get(str(_src(r)), 0) + 1
    fatal_won = [r["index"] for r in results
                 if any(c.get("fatal") for c in (r.get("candidates") or {}).get("candidates", [])
                        if c.get("label") == (r.get("response") or {}).get("selected_candidate_label"))]
    graded = [r for r in results if r.get("gold") and r["gold"].get("gold_found")]
    gold_ok = [r for r in graded if r["gold"].get("semantic_ok")]
    gold_strict = [r for r in graded if r["gold"].get("match_level") in ("strict", "column_order")]
    repairs = [r.get("repair") or {} for r in results]

    summary = {
        "repair_attempted_count": sum(1 for m in repairs if m.get("repair_attempted")),
        "repair_selected_count": sum(1 for m in repairs if m.get("repair_selected")),
        "repair_selected_queries": [r["index"] for r in results
                                    if (r.get("repair") or {}).get("repair_selected")],
        "database_id": database_id,
        "total": len(results),
        "exec_ok_count": sum(1 for r in results if r.get("success")),
        "exec_fail_count": sum(1 for r in results if not r.get("success")),
        "query_family_count": sum(1 for r in results if r.get("extraction_source") == "query_family"),
        "llm_count": sum(1 for r in results if r.get("extraction_source") == "llm"),
        "no_sql_count": sum(1 for r in results if not r.get("sql")),
        "gold_graded": len(graded),
        "gold_semantic_ok": len(gold_ok),
        "gold_strict_ok": len(gold_strict),
        "gold_wrong": [r["index"] for r in graded if not r["gold"].get("semantic_ok")],
        "selected_source_breakdown": source_breakdown,
        "fatal_candidate_won": fatal_won,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }

    json_path.write_text(
        json.dumps({"summary": summary, "results": results}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        f"# Petfood 50 SQL Debug — database #{database_id}",
        "",
        "This report is for SQL inspection, not semantic grading.",
        "",
        "## Summary",
        "",
        f"- Total: {summary['total']}",
        f"- Execution OK: {summary['exec_ok_count']}",
        f"- Execution fail: {summary['exec_fail_count']}",
        f"- Query family path: {summary['query_family_count']}",
        f"- LLM path: {summary['llm_count']}",
        f"- No SQL generated: {summary['no_sql_count']}",
        f"- Gold semantic OK: {summary['gold_semantic_ok']}/{summary['gold_graded']}"
        f" (strict {summary['gold_strict_ok']})",
        f"- Selected source breakdown: `{json.dumps(summary['selected_source_breakdown'])}`",
        f"- Fatal candidate won: {summary['fatal_candidate_won']}",
        f"- Gold wrong: {summary['gold_wrong']}",
        f"- Generated at: {summary['generated_at']}",
        "",
    ]

    for record in results:
        lines.extend([
            f"## Q{record['index']}",
            "",
            f"**Question:** {record['question']}",
            "",
            f"- Execution success: `{record.get('success')}`",
            f"- Row count: `{record.get('row_count')}`",
            f"- Source: `{record.get('extraction_source')}`",
            f"- Family: `{record.get('query_family')}`",
            f"- Confidence: `{record.get('query_family_confidence')}`",
            f"- Reason: {record.get('query_family_reason')}",
            f"- Time: `{record.get('elapsed_seconds')}s`",
            f"- Flags: `{json.dumps(record.get('sql_flags', {}), sort_keys=True)}`",
            f"- {format_gold(record.get('gold'))}",
            f"- {format_repair(record.get('repair'))}",
            "",
            "**Candidates:**",
            "```text",
            *format_candidates(record.get("candidates")
                               or {"selected_candidate_source": None,
                                   "selection_reason": None,
                                   "candidate_count": 0,
                                   "warnings": [], "candidates": []}),
            "```",
            "",
            "```sql",
            record.get("sql") or "-- NO SQL GENERATED",
            "```",
            "",
        ])
        if record.get("error"):
            lines.extend(["Error:", "", "```text", str(record["error"]), "```", ""])

    md_path.write_text("\n".join(lines), encoding="utf-8")

    print("\n" + "=" * 100)
    print("Saved:")
    print(f"  JSON: {json_path}")
    print(f"  Markdown: {md_path}")
    print("\nSummary:")
    print(json.dumps(summary, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all 50 petfood queries and print SQL/debug metadata only.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--database-id", type=int, default=DEFAULT_DATABASE_ID)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument("--output-dir", default=".")
    args = parser.parse_args()

    if len(QUERIES) != 50:
        print(f"Expected 50 queries, found {len(QUERIES)}", file=sys.stderr)
        return 2

    results = run_queries(args.base_url, args.database_id, args.timeout, args.delay)
    write_outputs(results, args.database_id, Path(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
