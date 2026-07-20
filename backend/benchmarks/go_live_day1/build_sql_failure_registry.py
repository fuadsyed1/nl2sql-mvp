"""
build_sql_failure_registry.py -> sql_failure_registry.csv (+ summary json)

Rebuilt from SEMANTIC verdicts (not execution status). One row per query the
audit marked INCORRECT -- i.e. EVERY executable-but-wrong SQL query PLUS the
controlled no-SQL failures. Controlled failures are additionally enriched with
the trace root-cause layer; executable-but-wrong rows get a best-effort semantic
failure pattern from the audit finding (unmatched -> needs_manual_review, never
force-labelled). Verdicts are taken verbatim from the audit files.
"""
import csv, json, re
import day1_common as dc

COLUMNS = [
    "database_id", "db_name", "test_id", "category", "difficulty", "question",
    "execution_status", "semantic_verdict", "failure_source",
    "semantic_failure_pattern", "controlled_root_cause_layer",
    "controlled_no_sql_stage", "num_candidates", "num_candidates_fatal",
    "num_candidates_executed", "selected_source", "repair_attempted",
    "repair_selected", "audit_finding", "generated_sql", "trace_matched",
    "needs_manual_review", "notes",
]


def _norm(q):
    return re.sub(r"\s+", " ", (q or "").strip()).lower()


def _is_controlled(v):
    st = (v.get("execution_status") or "").upper()
    sql = (v.get("sql") or "").upper()
    return st == "FAIL" or "NO SQL GENERATED" in sql or not v.get("sql")


def main():
    cfg = dc.load_config()
    ia = cfg["input_artifacts"]
    dbname = {str(d["database_id"]): d["name"] for d in cfg["databases"]}
    rows = []
    summary = {"by_database": {}, "by_failure_source": {},
               "by_semantic_failure_pattern": {},
               "by_controlled_root_cause_layer": {}, "needs_manual_review": 0}

    for db in ia["sql_result_files"]:
        info = ia["semantic_audit_files"].get(db)
        if not info:
            continue
        rrecs = dc.parse_result_file(dc.rp(ia["sql_result_files"][db]))
        audit = dc.parse_semantic_audit(dc.rp(info["path"]), info.get("format"))
        vmap = dc.build_verdict_map(audit, rrecs)
        # trace enrichment keyed by question
        trace_by_q = {}
        trel = ia["sql_trace_files"].get(db)
        if trel and dc.file_meta(dc.rp(trel))["exists"]:
            for rec in dc.parse_trace_file(dc.rp(trel)):
                trace_by_q[_norm(rec["question"])] = rec

        for tid, v in sorted(vmap.items()):
            if v["semantic_verdict"] != "INCORRECT":
                continue
            controlled = _is_controlled(v)
            src = "controlled_no_sql" if controlled else "executed_semantically_wrong"
            tr = trace_by_q.get(_norm(v["query"]))
            layer = ""; stage = ""; ncand = nfatal = nexec = None
            selected = ""; rep_att = rep_sel = None
            if tr:
                cands = tr["candidates"]
                ncand = len(cands)
                nfatal = sum(1 for c in cands if (c.get("fatal_count") or 0) > 0)
                nexec = sum(1 for c in cands if c.get("execution_success"))
                selected = tr.get("selected_label") or ""
                rm = tr.get("repair_meta") or {}
                rep_att = rm.get("repair_attempted"); rep_sel = rm.get("repair_selected")
                if controlled:
                    layer, _n = dc.classify_fatal_layer(tr["final_fatal_reasons"])
                    stage = tr.get("no_sql_stage") or ""
            if controlled:
                pattern, needs = "controlled_no_sql", False
            else:
                pattern, needs = dc.classify_semantic_failure(v.get("audit_note"))
            rows.append({
                "database_id": int(db), "db_name": dbname.get(db, ""),
                "test_id": tid, "category": v.get("category"),
                "difficulty": v.get("difficulty"), "question": v.get("query"),
                "execution_status": v.get("execution_status"),
                "semantic_verdict": "INCORRECT", "failure_source": src,
                "semantic_failure_pattern": pattern,
                "controlled_root_cause_layer": layer,
                "controlled_no_sql_stage": stage,
                "num_candidates": ncand, "num_candidates_fatal": nfatal,
                "num_candidates_executed": nexec, "selected_source": selected,
                "repair_attempted": rep_att, "repair_selected": rep_sel,
                "audit_finding": (v.get("audit_note") or "")[:300],
                "generated_sql": (v.get("sql") or "").replace("\n", " ")[:400],
                "trace_matched": tr is not None,
                "needs_manual_review": bool(needs),
                "notes": "" if tr else "no trace match by question",
            })
            d = summary["by_database"].setdefault(
                db, {"total": 0, "executed_semantically_wrong": 0,
                     "controlled_no_sql": 0})
            d["total"] += 1; d[src] += 1
            summary["by_failure_source"][src] = summary["by_failure_source"].get(src, 0) + 1
            summary["by_semantic_failure_pattern"][pattern] = \
                summary["by_semantic_failure_pattern"].get(pattern, 0) + 1
            if controlled and layer:
                summary["by_controlled_root_cause_layer"][layer] = \
                    summary["by_controlled_root_cause_layer"].get(layer, 0) + 1
            if needs:
                summary["needs_manual_review"] += 1

    rows.sort(key=lambda r: (r["database_id"], r["test_id"]))
    with open(dc.out("sql_failure_registry.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS); w.writeheader(); w.writerows(rows)
    summary["total_failures"] = len(rows)
    summary["generated_at"] = dc.now_iso()
    with open(dc.out("sql_failure_registry_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print("wrote sql_failure_registry.csv rows:", len(rows))
    print("  by_failure_source:", summary["by_failure_source"])
    print("  by_semantic_failure_pattern:", summary["by_semantic_failure_pattern"])
    print("  controlled root-cause layers:", summary["by_controlled_root_cause_layer"],
          "| needs_manual_review:", summary["needs_manual_review"])


if __name__ == "__main__":
    main()
