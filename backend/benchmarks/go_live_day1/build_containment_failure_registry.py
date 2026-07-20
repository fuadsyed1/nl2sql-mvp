"""
build_containment_failure_registry.py
    -> containment_failure_registry.csv + containment_failure_summary.json

Rebuilt from the AUTHORITATIVE containment artifacts now obtained:
  * spidersql_containment_failed_expected_edges.csv - one row per failed designed
    edge with the engine's own explanation;
  * spidersql_containment_case_summary.csv - per-case recovered counts.
Each failed edge is labelled with a detailed cause enum (base_entity_recovery,
canonical_key_failure, group_key_mismatch, distinct_groupby_normalization,
aggregate_normalization, sql_generation_failure, definite_wrong_relationship,
plus limit_orderby_normalization). The raw-trace derivation is used only as an
independent cross-check (warns on divergence); nothing is hardcoded.
"""
import csv, json
from collections import defaultdict
import day1_common as dc

COLUMNS = [
    "case_id", "database_id", "db_name", "difficulty", "case_name",
    "expected_subset", "expected_superset", "designed_relationship",
    "actual_relationship", "failure_cause", "failure_subtype",
    "needs_manual_review", "explanation", "subset_query", "superset_query",
]
REQUIRED_CAUSES = {"base_entity_recovery", "canonical_key_failure",
                   "group_key_mismatch", "distinct_groupby_normalization",
                   "aggregate_normalization", "sql_generation_failure",
                   "definite_wrong_relationship"}


def main():
    cfg = dc.load_config()
    ia = cfg["input_artifacts"]
    csf = ia["containment_summary_files"]
    dbname = {d["database_id"]: d["name"] for d in cfg["databases"]}

    fpath = dc.rp(csf["failed_expected_edges"])
    cpath = dc.rp(csf["case_summary"])
    warnings = []

    rows = []
    summary = {"by_database": {}, "by_failure_cause": {}, "by_failure_subtype": {},
               "failed_total": 0, "needs_manual_review": 0}
    with open(fpath, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            cause, sub = dc.classify_containment_cause(
                r["actual_relationship"], r["explanation"])
            needs = cause == "needs_manual_review"
            dbid = int(r["database_id"])
            rows.append({
                "case_id": int(r["case_id"]), "database_id": dbid,
                "db_name": dbname.get(dbid, r["database_name"]),
                "difficulty": r["difficulty"], "case_name": r["case_name"],
                "expected_subset": r["expected_subset"],
                "expected_superset": r["expected_superset"],
                "designed_relationship": "subset_contained_in_superset",
                "actual_relationship": r["actual_relationship"],
                "failure_cause": cause, "failure_subtype": sub or "",
                "needs_manual_review": needs,
                "explanation": r["explanation"][:300],
                "subset_query": r["subset_query"][:200],
                "superset_query": r["superset_query"][:200],
            })
            summary["failed_total"] += 1
            summary["by_database"].setdefault(dbid, {"failed": 0})["failed"] += 1
            summary["by_failure_cause"][cause] = summary["by_failure_cause"].get(cause, 0) + 1
            if sub:
                summary["by_failure_subtype"][sub] = summary["by_failure_subtype"].get(sub, 0) + 1
            if needs:
                summary["needs_manual_review"] += 1

    # recovered counts from case_summary (authoritative) + cross-check vs raw JSON
    designed = defaultdict(int); recovered = defaultdict(int)
    with open(cpath, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            dbid = int(r["database_id"])
            designed[dbid] += int(r["expected_edge_count"])
            recovered[dbid] += int(r["expected_edges_passed_with_equivalence"])
    for dbid in sorted(designed):
        d = summary["by_database"].setdefault(dbid, {"failed": 0})
        d["designed"] = designed[dbid]
        d["recovered"] = recovered[dbid]
        d["accuracy"] = round(recovered[dbid] / designed[dbid], 4)
        if designed[dbid] - recovered[dbid] != d["failed"]:
            warnings.append(f"db{dbid}: case_summary failures "
                            f"{designed[dbid]-recovered[dbid]} != registry rows {d['failed']}")

    # independent cross-check against the raw-JSON trace derivation
    craw = dc.rp(ia["containment_results_file"])
    if dc.file_meta(craw)["exists"]:
        rec_raw = defaultdict(int); des_raw = defaultdict(int)
        for c in dc.parse_containment_file(craw):
            for a, b in c["designed_edges"]:
                des_raw[c["database_id"]] += 1
                if dc.evaluate_designed_edge(c, a, b)[0]:
                    rec_raw[c["database_id"]] += 1
        for dbid in designed:
            if rec_raw[dbid] != recovered[dbid]:
                warnings.append(f"db{dbid}: raw-JSON recovered {rec_raw[dbid]} "
                                f"!= case_summary {recovered[dbid]}")

    summary["designed_total"] = sum(designed.values())
    summary["recovered_total"] = sum(recovered.values())
    summary["weighted_accuracy"] = round(
        summary["recovered_total"] / summary["designed_total"], 4)
    summary["required_causes_present"] = sorted(
        REQUIRED_CAUSES & set(summary["by_failure_cause"]))
    summary["required_causes_missing"] = sorted(
        REQUIRED_CAUSES - set(summary["by_failure_cause"]))
    summary["cross_check_warnings"] = warnings
    summary["generated_at"] = dc.now_iso()

    rows.sort(key=lambda r: (r["database_id"], r["case_id"],
                             r["expected_subset"], r["expected_superset"]))
    with open(dc.out("containment_failure_registry.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS); w.writeheader(); w.writerows(rows)
    with open(dc.out("containment_failure_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print("wrote containment_failure_registry.csv rows:", len(rows))
    print("  designed:", summary["designed_total"], "recovered:",
          summary["recovered_total"], "failed:", summary["failed_total"])
    print("  causes:", summary["by_failure_cause"])
    print("  required causes missing:", summary["required_causes_missing"],
          "| warnings:", len(warnings))


if __name__ == "__main__":
    main()
