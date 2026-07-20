"""
build_protected_regression_manifest.py -> protected_regression_manifest.json

Generated DYNAMICALLY from the parsed audits (never a typed ID list). It now
protects ONLY the semantically-correct queries (verdict == CORRECT), NOT every
execution-success query. Controlled failures are kept in a SEPARATE protected
section (they must stay controlled, not silently become wrong-but-executed
answers). Recovered containment designed-edges are protected in their own
section. Day 2 changes must not regress any protected item.
"""
import json
import day1_common as dc


def main():
    cfg = dc.load_config()
    ia = cfg["input_artifacts"]
    dbname = {str(d["database_id"]): d["name"] for d in cfg["databases"]}
    sources = {}

    correct_by_db, controlled_by_db = {}, {}
    correct_total = controlled_total = 0
    for db in ia["sql_result_files"]:
        info = ia["semantic_audit_files"].get(db)
        rrel = ia["sql_result_files"][db]
        sources[f"sql_result_{db}"] = {"path": rrel, **dc.file_meta(dc.rp(rrel))}
        sources[f"semantic_audit_{db}"] = {"path": info["path"],
                                           **dc.file_meta(dc.rp(info["path"]))}
        rrecs = dc.parse_result_file(dc.rp(rrel))
        audit = dc.parse_semantic_audit(dc.rp(info["path"]), info.get("format"))
        vmap = dc.build_verdict_map(audit, rrecs)
        correct_ids, controlled_ids = [], []
        for tid, v in vmap.items():
            st = (v.get("execution_status") or "").upper()
            sql = (v.get("sql") or "").upper()
            is_controlled = st == "FAIL" or "NO SQL GENERATED" in sql or not v.get("sql")
            if v["semantic_verdict"] == "CORRECT":
                correct_ids.append(tid)
            elif is_controlled:
                controlled_ids.append(tid)
        correct_ids.sort(); controlled_ids.sort()
        correct_by_db[db] = {"db_name": dbname.get(db, ""),
                             "count": len(correct_ids), "test_ids": correct_ids}
        controlled_by_db[db] = {"db_name": dbname.get(db, ""),
                                "count": len(controlled_ids), "test_ids": controlled_ids}
        correct_total += len(correct_ids)
        controlled_total += len(controlled_ids)

    # recovered containment designed-edges (from raw JSON derivation)
    cpath = dc.rp(ia["containment_results_file"])
    sources["containment_results"] = {"path": ia["containment_results_file"],
                                      **dc.file_meta(cpath)}
    cont_by_db, cont_total = {}, 0
    if dc.file_meta(cpath)["exists"]:
        by = {}
        for c in dc.parse_containment_file(cpath):
            for a, b in c["designed_edges"]:
                if dc.evaluate_designed_edge(c, a, b)[0]:
                    by.setdefault(str(c["database_id"]), []).append([c["case_id"], a, b])
        for dbid, edges in by.items():
            edges.sort()
            cont_by_db[dbid] = {"count": len(edges), "edges": edges}
            cont_total += len(edges)

    manifest = {
        "schema_version": "day1.protected.v2",
        "generated_at": dc.now_iso(),
        "generation": "dynamic (parsed from semantic audits; no manual IDs)",
        "protection_policy": ("Protect ONLY semantically-correct queries. Execution "
                              "success is NOT sufficient. Controlled failures are "
                              "tracked separately and must remain controlled."),
        "source_files": sources,
        "protected_semantically_correct": {
            "by_database": correct_by_db, "total": correct_total},
        "controlled_failures": {
            "by_database": controlled_by_db, "total": controlled_total},
        "protected_containment_recovered_edges": {
            "by_database": cont_by_db, "total": cont_total},
    }
    with open(dc.out("protected_regression_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print("wrote protected_regression_manifest.json")
    print("  protected semantically-correct:", correct_total,
          "| controlled (separate):", controlled_total,
          "| recovered edges:", cont_total)


if __name__ == "__main__":
    main()
