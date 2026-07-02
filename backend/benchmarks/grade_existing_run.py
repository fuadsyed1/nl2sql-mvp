"""
benchmarks/grade_existing_run.py

Re-grade an ALREADY SAVED debug-run JSON against the gold SQL — no server,
no LLM. Executes each stored generated SQL and the gold SQL directly on the
benchmark database and compares result sets.

Usage (from backend/):
    python -m benchmarks.grade_existing_run petfood_50_sql_debug_db28_<ts>.json
    python -m benchmarks.grade_existing_run spidersql_2db_40_sql_debug_<ts>.json
"""

import json
import sys
from collections import Counter

from benchmarks.gold_eval import grade

_BENCH_BY_DB = {28: "petfood_50", 29: "clinic_20", 30: "cyber_20"}


def _items(payload):
    """Normalize both runner formats -> list of
    (benchmark, index, question, sql, params, response)."""
    raw = payload.get("results", payload) if isinstance(payload, dict) else payload
    out = []
    counters = Counter()
    for item in raw:
        resp = item.get("response") or item.get("full_response") or {}
        db_id = item.get("database_id") or resp.get("database_id") or 28
        bench = _BENCH_BY_DB.get(db_id)
        if bench is None:
            continue
        counters[bench] += 1
        idx = item.get("query_number") or item.get("index") or counters[bench]
        params = ((resp.get("generated_sql") or {}).get("params")
                  if isinstance(resp.get("generated_sql"), dict) else None)
        out.append((bench, idx, item.get("question"), item.get("sql") or "",
                    params or [], resp))
    return out


def main(path):
    payload = json.loads(open(path, encoding="utf-8").read())
    graded = []
    for bench, idx, question, sql, params, resp in _items(payload):
        g = grade(bench, idx, question, sql, params)
        sel_val = resp.get("selected_candidate_validation") or {}
        graded.append({
            "benchmark": bench, "index": idx, "question": question,
            "match_level": g["match_level"], "semantic_ok": g["semantic_ok"],
            "both_empty": g["both_empty"], "gold_rows": g["gold_rows"],
            "gen_rows": g["gen_rows"], "gold_error": g["gold_error"],
            "gen_error": g["gen_error"], "note": g["note"],
            "source": resp.get("selected_candidate_source")
                      or resp.get("extraction_source"),
            "selection_reason": resp.get("selection_reason"),
            "warnings": resp.get("warnings") or [],
            "selected_fatal": sel_val.get("fatal") or [],
            "family": resp.get("query_family"),
            "guard": resp.get("family_guard_valid"),
        })

    ok = [g for g in graded if g["semantic_ok"]]
    print(f"\n=== {path} ===")
    print(f"graded: {len(graded)}  semantic_ok: {len(ok)} "
          f"({100.0*len(ok)/max(len(graded),1):.0f}%)")
    print("match levels:", dict(Counter(g["match_level"] for g in graded)))
    print("both_empty matches:",
          sum(1 for g in graded if g["semantic_ok"] and g["both_empty"]))
    print("by source:", dict(Counter(f"{g['source']}:{g['match_level']}"
                                     for g in graded)))
    fatal_won = [g for g in graded if g["selected_fatal"]]
    print(f"fatal candidate selected: {len(fatal_won)} -> "
          f"{[(g['benchmark'], g['index']) for g in fatal_won]}")
    print("\nWRONG (match_level=none):")
    for g in graded:
        if not g["semantic_ok"]:
            why = g["gen_error"] or f"gold_rows={g['gold_rows']} gen_rows={g['gen_rows']}"
            print(f"  {g['benchmark']} Q{g['index']:02d} [{g['source']}] {why}"
                  + (" FATAL-WON" if g["selected_fatal"] else ""))
    out_path = path.replace(".json", "_gold_graded.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(graded, fh, indent=2, ensure_ascii=False)
    print(f"\nsaved: {out_path}")
    return graded


if __name__ == "__main__":
    for p in sys.argv[1:]:
        main(p)
