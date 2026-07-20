"""
build_day2_targeted_selection.py

Deterministically selects the Day 2 targeted-verification set (<=64 live queries:
32 failure reruns = 8 per priority pattern, spread across DB/difficulty + 32
protected controls) and writes the before/after scaffold and honest status files.
NO live queries are executed here; the LLM backend (MindRouter) is unreachable in
this environment, so 'after' columns are left pending and recoveries are NOT
fabricated. Selection is dynamic (no embedded test IDs).
"""
import os, csv, json
from collections import defaultdict

HERE = os.path.dirname(__file__)
PATTERNS = ["aggregation_or_formula_error", "missing_metric_or_output",
            "wrong_filter_or_placement", "set_logic_error"]
BACKEND_UNREACHABLE = True  # verified: mindrouter DNS fails; :8000/:11434 refused


def _rows(name):
    return list(csv.DictReader(open(os.path.join(HERE, name), newline="", encoding="utf-8")))


def select_failures():
    coh = _rows("day2_priority_cohorts.csv")
    by_pat = defaultdict(list)
    for r in coh:
        by_pat[r["failure_pattern"]].append(r)
    picked = []
    for pat in PATTERNS:
        rows = sorted(by_pat[pat], key=lambda r: (r["difficulty"], int(r["database_id"]), int(r["test_id"])))
        by_db = defaultdict(list)
        for r in rows:
            by_db[r["database_id"]].append(r)
        dbs = sorted(by_db, key=int)
        chosen, i = [], 0
        while len(chosen) < 8 and any(by_db.values()):
            db = dbs[i % len(dbs)]
            if by_db[db]:
                chosen.append(by_db[db].pop(0))
            i += 1
            if i > 5000:
                break
        picked += chosen[:8]
    return picked


def main():
    failures = select_failures()
    controls = _rows("day2_protected_controls.csv")
    # enrich controls with question + correct SQL from the frozen audits (offline)
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "go_live_day1"))
    import day1_common as dc
    cfg = dc.load_config(); ia = cfg["input_artifacts"]
    vmaps = {}
    for db in ia["sql_result_files"]:
        info = ia["semantic_audit_files"][db]
        rrecs = dc.parse_result_file(dc.rp(ia["sql_result_files"][db]))
        vmaps[db] = dc.build_verdict_map(dc.parse_semantic_audit(dc.rp(info["path"]), info.get("format")), rrecs)
    for r in controls:
        v = vmaps.get(r["database_id"], {}).get(int(r["test_id"]), {})
        r["question"] = v.get("query", "")
        r["correct_sql"] = v.get("sql", "")

    ba_cols = ["kind", "group", "database_id", "test_id", "category", "difficulty",
               "question", "before_sql", "before_verdict", "audit_reason",
               "rerun_status", "after_sql", "after_verdict", "recovered"]
    ba = []
    for r in failures:
        ba.append({"kind": "failure_rerun", "group": r["failure_pattern"],
                   "database_id": r["database_id"], "test_id": r["test_id"],
                   "category": r["category"], "difficulty": r["difficulty"],
                   "question": r["question"], "before_sql": r["selected_sql"],
                   "before_verdict": "INCORRECT", "audit_reason": r["audit_reason"],
                   "rerun_status": "not_executed_backend_unreachable",
                   "after_sql": "", "after_verdict": "", "recovered": ""})
    for r in controls:
        ba.append({"kind": "protected_control", "group": r["theme"],
                   "database_id": r["database_id"], "test_id": r["test_id"],
                   "category": r["category"], "difficulty": r["difficulty"],
                   "question": r.get("question", ""), "before_sql": r.get("correct_sql", ""),
                   "before_verdict": "CORRECT",
                   "audit_reason": "", "rerun_status": "not_executed_backend_unreachable",
                   "after_sql": "", "after_verdict": "", "recovered": ""})
    with open(os.path.join(HERE, "day2_targeted_before_after.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ba_cols); w.writeheader(); w.writerows(ba)

    # honest placeholder result artifacts (0 rows, header only)
    with open(os.path.join(HERE, "day2_verified_recoveries.csv"), "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(["database_id", "test_id", "failure_pattern",
                                "before_sql", "after_sql", "verified_correct", "verifier_note"])
    with open(os.path.join(HERE, "day2_protected_regressions.csv"), "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(["database_id", "test_id", "theme",
                                "before_correct_sql", "after_sql", "regressed", "note"])
    status = ("Day 2 targeted live verification NOT executed.\n"
              "Reason: the LLM inference backend is unreachable from this environment "
              "(mindrouter.uidaho.edu does not resolve; localhost:8000 and localhost:11434 "
              "refuse connections). No new SQL could be generated, so recoveries and "
              "protected-control non-regression could not be measured. No results were "
              "fabricated. Re-run in an environment with MindRouter access using the same "
              "model (qwen/qwen3.5-122b) and server config as the frozen baseline.\n"
              f"Selected (deterministic): {len(failures)} failure reruns + "
              f"{len(controls)} protected controls = {len(failures)+len(controls)} queries "
              "(<= 64 cap).\n")
    open(os.path.join(HERE, "day2_targeted_results.txt"), "w", encoding="utf-8").write(status)
    open(os.path.join(HERE, "day2_targeted_trace.txt"), "w", encoding="utf-8").write(
        "No trace captured — live verification not executed (backend unreachable).\n")

    from collections import Counter
    print("failure reruns:", len(failures), dict(Counter(r["failure_pattern"] for r in failures)))
    print("controls:", len(controls), "| total selected:", len(failures)+len(controls))
    return failures, controls


if __name__ == "__main__":
    main()
