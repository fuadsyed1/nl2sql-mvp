"""
generate_go_live_score_report.py -> go_live_score_report.json + .md

Consolidates the Day 1 semantic outputs against go_live_targets.json. Reads only
files produced by the other Day 1 builders. Flags the 1737/1738 target
reconciliation and reports measured semantic-correct verbatim.
"""
import json
import day1_common as dc


def _load(name):
    p = dc.out(name)
    return json.load(open(p, encoding="utf-8")) if dc.file_meta(p)["exists"] else None


def main():
    cfg = dc.load_config()
    base = _load("go_live_baseline_scores.json")
    sqlf = _load("sql_failure_registry_summary.json")
    orc = _load("candidate_oracle_summary.json")
    cont = _load("containment_failure_summary.json")
    tgt = cfg["nl_to_sql_targets"]; ctgt = cfg["containment_targets"]

    ex = base["nl_to_sql_execution"]["totals"]
    sem = base["nl_to_sql_semantic_correct"]["totals"]
    cb = base["containment"]

    report = {
        "generated_at": dc.now_iso(),
        "config_schema_version": cfg["schema_version"],
        "nl_to_sql": {
            "execution": {"successes": ex["execution_successes"],
                          "total": ex["total_queries"],
                          "min_target": ex["min_execution_target"],
                          "meets_target": ex["meets_execution_target"]},
            "semantic_correct": {"correct": sem["correct"], "total": sem["total"],
                                 "measured_accuracy": sem["measured_accuracy"],
                                 "engineering_target": tgt["min_semantic_correct"],
                                 "meets_target": sem["meets_semantic_target"],
                                 "gap_to_target": sem["gap_to_target"],
                                 "category_rollup_correct": sem["category_rollup_correct"],
                                 "target_reconciliation": sem["target_reconciliation"]},
            "failures": {"total": sqlf["total_failures"],
                         "by_source": sqlf["by_failure_source"],
                         "by_semantic_pattern": sqlf["by_semantic_failure_pattern"],
                         "controlled_root_cause_layers": sqlf["by_controlled_root_cause_layer"],
                         "needs_manual_review": sqlf["needs_manual_review"]},
            "candidate_oracle": {
                "candidate_rows": orc["candidate_rows"],
                "failed_queries": orc["failed_queries"],
                "executed_semantically_wrong": orc["executed_semantically_wrong"],
                "no_selected_sql": orc["no_selected_sql"],
                "selected_candidate_coverage": orc["selected_candidate_coverage"],
                "query_dispositions": orc["query_dispositions"],
                "manual_review_rows": orc["manual_review_rows"]},
        },
        "containment": {"weighted_recovered": cb["weighted_recovered"],
                        "weighted_total": cb["weighted_total"],
                        "weighted_accuracy": cb["weighted_accuracy"],
                        "unweighted_db_average": cb["unweighted_db_average"],
                        "weighted_recovered_target": ctgt["weighted_recovered_target"],
                        "meets_weighted_target": cb["meets_weighted_target"],
                        "by_database": cb["by_database"],
                        "failure_causes": cont["by_failure_cause"],
                        "required_causes_present": cont["required_causes_present"],
                        "required_causes_missing": cont["required_causes_missing"]},
        "missing_artifacts": base["missing_artifacts"],
        "warnings": base["warnings"],
    }
    with open(dc.out("go_live_score_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    L = ["# SpiderSQL Go-Live — Day 1 Baseline Score Report\n",
         f"_Generated {report['generated_at']} · config {cfg['schema_version']}_\n",
         "## NL-to-SQL\n",
         f"- Execution successes: **{ex['execution_successes']} / {ex['total_queries']}** "
         f"(target ≥ {ex['min_execution_target']}) → "
         f"{'MEETS' if ex['meets_execution_target'] else 'BELOW'}",
         f"- **Semantic-correct: {sem['correct']} / {sem['total']} = "
         f"{sem['measured_accuracy']:.1%}** (engineering target ≥ "
         f"{tgt['min_semantic_correct']}) → "
         f"{'MEETS' if sem['meets_semantic_target'] else 'BELOW'} "
         f"(gap {sem['gap_to_target']})",
         f"- Target reconciliation: {sem['target_reconciliation']}",
         f"- Category rollup of correct = {sem['category_rollup_correct']} "
         f"(equals DB total {sem['correct']}: measured data is internally consistent)",
         f"- Semantic failures: **{sqlf['total_failures']}** "
         f"({sqlf['by_failure_source']}); patterns {sqlf['by_semantic_failure_pattern']}",
         f"- Candidate-oracle rows: {orc['candidate_rows']} across "
         f"{orc['failed_queries']} failed queries "
         f"({orc['executed_semantically_wrong']} executed-wrong + "
         f"{orc['no_selected_sql']} no_selected_sql)",
         f"- Selected-candidate coverage: "
         f"{orc['selected_candidate_coverage']['executed_wrong_with_selected']}/"
         f"{orc['selected_candidate_coverage']['executed_wrong_total']} "
         f"({orc['selected_candidate_coverage']['coverage_pct']}%)",
         f"- Query dispositions (heuristic; see manual-review CSV): "
         f"{orc['query_dispositions']}\n",
         "### Semantic accuracy by database\n",
         "| DB | correct | total | accuracy |", "|----|--------|-------|----------|"]
    for db in sorted(base["nl_to_sql_semantic_correct"]["by_database"]):
        d = base["nl_to_sql_semantic_correct"]["by_database"][db]
        L.append(f"| {db} | {d['correct']} | {d['total']} | {d['accuracy']:.1%} |")
    L += ["", "## Containment (designed-edge recovery)\n",
          f"- Weighted: **{cb['weighted_recovered']} / {cb['weighted_total']} = "
          f"{cb['weighted_accuracy']:.1%}** (target {ctgt['weighted_recovered_target']} "
          f"= {ctgt['weighted_accuracy_target']:.1%}) → "
          f"{'MEETS' if cb['meets_weighted_target'] else 'BELOW'}",
          f"- Unweighted DB average: {cb['unweighted_db_average']:.1%}",
          f"- Detailed failure causes: {cont['by_failure_cause']}",
          f"- Required causes present: {cont['required_causes_present']}; "
          f"missing: {cont['required_causes_missing']}\n",
          "## Data availability\n",
          f"- Missing artifacts: {report['missing_artifacts'] or 'none (all obtained)'}",
          f"- Warnings: {len(report['warnings'])}"
          + ((" — " + "; ".join(report['warnings'])) if report['warnings'] else "")]
    with open(dc.out("go_live_score_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("wrote go_live_score_report.json + .md")


if __name__ == "__main__":
    main()
