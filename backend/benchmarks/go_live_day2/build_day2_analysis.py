"""
build_day2_analysis.py  (Day 2 OFFLINE analysis; read-only over Day 1 outputs)

Produces:
  * day2_priority_cohorts.csv    - failures in the 4 priority patterns
  * day2_protected_controls.csv  - 32 deterministic protected-correct controls
  * day2_root_cause_sample.md    - <=24 balanced representative failures
Nothing is hardcoded (no embedded test IDs); everything is selected dynamically
from the frozen Day 1 artifacts.
"""
import os, sys, csv, json
from collections import defaultdict
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "go_live_day1"))
import day1_common as dc  # noqa: E402

D1 = os.path.join(os.path.dirname(__file__), os.pardir, "go_live_day1")
HERE = os.path.dirname(__file__)
TARGETS = ["wrong_filter_or_placement", "missing_metric_or_output",
           "aggregation_or_formula_error", "set_logic_error"]

# category -> protected-control theme (schema-independent, generic)
THEME = {
    "aggregation_derived": {"aggregation", "derived_metric", "distinct_count"},
    "filter_related": {"having", "subquery_cte"},
    "set_operations": {"set_operations"},
    "output_completeness": {"join", "multi_table_join", "group_by", "order_limit_topk"},
}


def _rows(name):
    return list(csv.DictReader(open(os.path.join(D1, name), newline="", encoding="utf-8")))


def priority_cohorts():
    reg = _rows("sql_failure_registry.csv")
    cols = ["database_id", "test_id", "category", "difficulty", "question",
            "selected_sql", "audit_reason", "failure_pattern", "selected_candidate"]
    out = []
    for r in reg:
        if r["semantic_failure_pattern"] not in TARGETS:
            continue
        out.append({"database_id": r["database_id"], "test_id": r["test_id"],
                    "category": r["category"], "difficulty": r["difficulty"],
                    "question": r["question"], "selected_sql": r["generated_sql"],
                    "audit_reason": r["audit_finding"],
                    "failure_pattern": r["semantic_failure_pattern"],
                    "selected_candidate": r["selected_source"]})
    out.sort(key=lambda r: (r["failure_pattern"], int(r["database_id"]), int(r["test_id"])))
    with open(os.path.join(HERE, "day2_priority_cohorts.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(out)
    return out


def protected_controls():
    cfg = dc.load_config(); ia = cfg["input_artifacts"]
    manifest = json.load(open(os.path.join(D1, "protected_regression_manifest.json")))
    correct_ids = {db: set(v["test_ids"]) for db, v in
                   manifest["protected_semantically_correct"]["by_database"].items()}
    # category per correct test id, per db, via verdict map
    theme_pool = defaultdict(list)   # theme -> [(db, tid, category, difficulty)]
    for db in ia["sql_result_files"]:
        info = ia["semantic_audit_files"][db]
        rrecs = dc.parse_result_file(dc.rp(ia["sql_result_files"][db]))
        vmap = dc.build_verdict_map(dc.parse_semantic_audit(dc.rp(info["path"]), info.get("format")), rrecs)
        for tid, v in vmap.items():
            if tid not in correct_ids.get(db, set()):
                continue
            for theme, cats in THEME.items():
                if (v.get("category") or "") in cats:
                    theme_pool[theme].append((db, tid, v.get("category"), v.get("difficulty")))
    # deterministic pick: 8 per theme, spread across the 4 databases
    cols = ["theme", "database_id", "test_id", "category", "difficulty"]
    picked = []
    for theme in THEME:
        pool = sorted(theme_pool[theme], key=lambda x: (int(x[0]), int(x[1])))
        by_db = defaultdict(list)
        for rec in pool:
            by_db[rec[0]].append(rec)
        chosen, i = [], 0
        dbs = sorted(by_db, key=int)
        while len(chosen) < 8 and any(by_db.values()):
            db = dbs[i % len(dbs)] if dbs else None
            if db and by_db[db]:
                chosen.append(by_db[db].pop(0))
            i += 1
            if i > 2000:
                break
        for db, tid, cat, dif in chosen[:8]:
            picked.append({"theme": theme, "database_id": db, "test_id": tid,
                           "category": cat, "difficulty": dif})
    with open(os.path.join(HERE, "day2_protected_controls.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(picked)
    return picked


def root_cause_sample(cohorts):
    # top-2 plausible alternatives per test from Day 1 manual-review CSV
    mr = defaultdict(list)
    for r in _rows("candidate_oracle_manual_review.csv"):
        mr[(r["database_id"], r["test_id"])].append(r)
    by_pat = defaultdict(list)
    for r in cohorts:
        by_pat[r["failure_pattern"]].append(r)
    lines = ["# Day 2 — Root-Cause Sample (<=24 representative failures)\n",
             "_Read-only analysis over frozen Day 1 artifacts. Balanced 6 per "
             "priority pattern, spread across databases and difficulties. Failure "
             "origin is inferred generically (not per-test)._\n"]
    for pat in TARGETS:
        rows = by_pat[pat]
        # balance across db + difficulty deterministically
        rows = sorted(rows, key=lambda r: (r["difficulty"], int(r["database_id"]), int(r["test_id"])))
        seen_db = defaultdict(int); pick = []
        for r in rows:
            if len(pick) >= 6:
                break
            if seen_db[r["database_id"]] < 2 or len(pick) >= len(set(r["database_id"] for r in rows)):
                pick.append(r); seen_db[r["database_id"]] += 1
        for r in pick[:6]:
            key = (r["database_id"], r["test_id"])
            alts = sorted(mr.get(key, []), key=lambda a: -(float(a["score"] or 0)))[:2]
            has_alt = len(mr.get(key, [])) > 0
            origin = ("selection/generation (a clean differing candidate existed)"
                      if has_alt else
                      "generation or contract-extraction (no clean alternative captured)")
            lines.append(f"## {pat} — DB{r['database_id']} test {r['test_id']} "
                         f"({r['category']}/{r['difficulty']})\n")
            lines.append(f"- **Question:** {r['question']}")
            lines.append(f"- **Audit reason:** {r['audit_reason']}")
            lines.append(f"- **Selected SQL:** `{(r['selected_sql'] or '')[:280]}`")
            lines.append(f"- **Likely origin:** {origin}")
            if alts:
                for i, a in enumerate(alts, 1):
                    lines.append(f"- **Plausible alt {i}** (score {a['score']}): "
                                 f"`{(a['candidate_sql'] or '')[:200]}`")
            lines.append("")
    open(os.path.join(HERE, "day2_root_cause_sample.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")


def main():
    coh = priority_cohorts()
    ctrl = protected_controls()
    root_cause_sample(coh)
    from collections import Counter
    print("day2_priority_cohorts.csv:", len(coh), "rows;",
          dict(Counter(r["failure_pattern"] for r in coh)))
    print("day2_protected_controls.csv:", len(ctrl), "rows;",
          dict(Counter(r["theme"] for r in ctrl)))
    print("day2_root_cause_sample.md written")


if __name__ == "__main__":
    main()
