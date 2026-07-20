"""
build_baseline_scores.py -> go_live_baseline_scores.json

Rebuilt with the semantic audits now obtained. Parses (never hardcodes):
  * NL-to-SQL execution success + SEMANTIC correctness per DB/category/difficulty
    (verdicts taken verbatim from the audit files: CSV for DB55-57, Markdown for
    DB54);
  * audit-vs-result execution cross-check (disagreement warnings);
  * containment designed-edge recovery from the authoritative case_summary, cross
    checked against the raw-trace derivation;
  * the 1737/1738 target reconciliation is flagged; the engineering target is
    1738 and the measured correct count is reported verbatim, never adjusted.
"""
import json
from collections import Counter, defaultdict
import day1_common as dc


def main():
    cfg = dc.load_config()
    ia = cfg["input_artifacts"]
    tgt = cfg["nl_to_sql_targets"]
    warnings, missing, sources = [], [], {}

    nl = {"by_database": {}, "totals": {}}
    sem = {"by_database": {}, "by_category": {}, "by_difficulty": {}, "totals": {}}
    g_exec = g_total = g_correct = 0
    cat_c = defaultdict(lambda: [0, 0]); dif_c = defaultdict(lambda: [0, 0])

    for db in ia["sql_result_files"]:
        rrel = ia["sql_result_files"][db]; rpath = dc.rp(rrel)
        info = ia["semantic_audit_files"].get(db)
        sources[f"sql_result_{db}"] = {"path": rrel, **dc.file_meta(rpath)}
        sources[f"semantic_audit_{db}"] = {"path": info["path"],
                                           **dc.file_meta(dc.rp(info["path"]))}
        rrecs = dc.parse_result_file(rpath)
        audit = dc.parse_semantic_audit(dc.rp(info["path"]), info.get("format"))
        vmap = dc.build_verdict_map(audit, rrecs)
        # execution
        ok = sum(1 for r in rrecs if r["status"] == "PASS")
        g_exec += ok; g_total += len(rrecs)
        nl["by_database"][db] = {"total_queries": len(rrecs),
                                 "execution_successes": ok,
                                 "execution_failures": len(rrecs) - ok}
        # semantic
        corr = sum(1 for v in vmap.values() if v["semantic_verdict"] == "CORRECT")
        inc = sum(1 for v in vmap.values() if v["semantic_verdict"] == "INCORRECT")
        g_correct += corr
        bycat = defaultdict(lambda: [0, 0]); bydif = defaultdict(lambda: [0, 0])
        # audit-vs-result execution cross-check (CSV audits carry status)
        mismatch = 0
        rstatus = {r["test_id"]: r["status"] for r in rrecs}
        for tid, v in vmap.items():
            good = v["semantic_verdict"] == "CORRECT"
            c = v.get("category"); d = v.get("difficulty")
            bycat[c][0] += 1; bycat[c][1] += int(good)
            bydif[d][0] += 1; bydif[d][1] += int(good)
            cat_c[c][0] += 1; cat_c[c][1] += int(good)
            dif_c[d][0] += 1; dif_c[d][1] += int(good)
            if v.get("execution_status") and rstatus.get(tid) and \
                    v["execution_status"] != rstatus[tid]:
                mismatch += 1
        if mismatch:
            warnings.append(f"db{db}: {mismatch} audit/result execution-status mismatches")
        sem["by_database"][db] = {
            "correct": corr, "incorrect": inc, "total": len(vmap),
            "accuracy": round(corr / len(vmap), 4) if vmap else None,
            "by_category": {k: {"total": t, "correct": g} for k, (t, g) in sorted(bycat.items())},
            "by_difficulty": {k: {"total": t, "correct": g} for k, (t, g) in sorted(bydif.items())},
            "audit_format": audit["format"],
        }
        if audit["header_totals"]:
            hd = audit["header_totals"]
            if hd.get("correct") is not None and hd["correct"] != corr:
                warnings.append(f"db{db}: markdown header correct {hd['correct']} "
                                f"!= derived {corr}")

    nl["totals"] = {
        "total_queries": g_total, "execution_successes": g_exec,
        "execution_failures": g_total - g_exec,
        "min_execution_target": cfg["nl_to_sql_targets"]["min_execution_successes"],
        "meets_execution_target": g_exec >= cfg["nl_to_sql_targets"]["min_execution_successes"],
    }
    sem["by_category"] = {k: {"total": t, "correct": g} for k, (t, g) in sorted(cat_c.items())}
    sem["by_difficulty"] = {k: {"total": t, "correct": g} for k, (t, g) in sorted(dif_c.items())}
    category_rollup = sum(g for _t, g in cat_c.values())
    sem["totals"] = {
        "status": "available",
        "correct": g_correct, "total": g_total,
        "incorrect": g_total - g_correct,
        "measured_accuracy": round(g_correct / g_total, 4) if g_total else None,
        "min_semantic_target": tgt["min_semantic_correct"],
        "meets_semantic_target": g_correct >= tgt["min_semantic_correct"],
        "gap_to_target": tgt["min_semantic_correct"] - g_correct,
        "category_rollup_correct": category_rollup,
        "target_reconciliation": tgt.get("target_reconciliation_note"),
    }
    if category_rollup != g_correct:
        warnings.append(f"semantic: category rollup {category_rollup} != "
                        f"db total {g_correct} (investigate audit category labels)")

    # containment from authoritative case_summary + cross-check
    csf = ia.get("containment_summary_files", {})
    cont = {"status": "unavailable"}
    cspath = dc.rp(csf.get("case_summary", "")) if csf.get("case_summary") else None
    if cspath and dc.file_meta(cspath)["exists"]:
        import csv as _csv
        des = defaultdict(int); rec = defaultdict(int)
        for r in _csv.DictReader(open(cspath, newline="", encoding="utf-8")):
            dbid = int(r["database_id"])
            des[dbid] += int(r["expected_edge_count"])
            rec[dbid] += int(r["expected_edges_passed_with_equivalence"])
        sources["containment_case_summary"] = {"path": csf["case_summary"],
                                               **dc.file_meta(cspath)}
        ctgt = cfg["containment_targets"]["designed_edges_by_db"]
        by_db, acc = {}, []
        for dbid in sorted(des):
            by_db[str(dbid)] = {"designed_edges": des[dbid], "recovered": rec[dbid],
                                "accuracy": round(rec[dbid] / des[dbid], 4),
                                "config_recovered_target": ctgt.get(str(dbid), {}).get("recovered_target")}
            acc.append(rec[dbid] / des[dbid])
        tot_d = sum(des.values()); tot_r = sum(rec.values())
        cont = {"status": "available", "source": "case_summary (authoritative)",
                "by_database": by_db, "weighted_recovered": tot_r,
                "weighted_total": tot_d,
                "weighted_accuracy": round(tot_r / tot_d, 4),
                "unweighted_db_average": round(sum(acc) / len(acc), 4),
                "weighted_recovered_target": cfg["containment_targets"]["weighted_recovered_target"],
                "meets_weighted_target": tot_r >= cfg["containment_targets"]["weighted_recovered_target"]}
        # cross-check raw JSON
        craw = dc.rp(ia["containment_results_file"])
        if dc.file_meta(craw)["exists"]:
            rr = defaultdict(int)
            for c in dc.parse_containment_file(craw):
                for a, b in c["designed_edges"]:
                    if dc.evaluate_designed_edge(c, a, b)[0]:
                        rr[c["database_id"]] += 1
            if sum(rr.values()) != tot_r:
                warnings.append(f"containment: raw-JSON recovered {sum(rr.values())} "
                                f"!= case_summary {tot_r}")
    else:
        missing.append(csf.get("case_summary", "containment_case_summary"))

    report = {
        "generated_at": dc.now_iso(),
        "config_schema_version": cfg["schema_version"],
        "nl_to_sql_execution": nl,
        "nl_to_sql_semantic_correct": sem,
        "containment": cont,
        "source_files": sources,
        "missing_artifacts": sorted(set(missing)),
        "warnings": warnings,
    }
    with open(dc.out("go_live_baseline_scores.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print("wrote go_live_baseline_scores.json")
    print("  execution:", g_exec, "/", g_total, "| semantic-correct:", g_correct,
          "/", g_total, "(target", tgt["min_semantic_correct"], ")")
    print("  containment recovered:", cont.get("weighted_recovered"), "/",
          cont.get("weighted_total"), "| warnings:", len(warnings),
          "| missing:", len(set(missing)))


if __name__ == "__main__":
    main()
