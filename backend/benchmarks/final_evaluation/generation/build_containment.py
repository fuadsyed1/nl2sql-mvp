"""
Build the final containment benchmark: instantiate the 240 groups, execute
every reference SQL read-only, COMPUTE the expected pairwise relations /
broadest / narrowest / equivalence classes / hierarchy from the normalized
result SETS on the frozen databases, and write manifests + references.

    python -m benchmarks.final_evaluation.generation.build_containment

This is data-dependent containment evaluation, not symbolic proof: expected
relations hold for the frozen database contents. Queries whose column counts
differ are expected to be 'unknown' (unsupported comparison keys).
"""

import collections
import json
import os
import sys

from benchmarks.final_evaluation.common import db as bdb
from benchmarks.final_evaluation.common import manifest as mf
from benchmarks.final_evaluation.common import scoring
from benchmarks.final_evaluation.generation.containment_groups import (
    build_all_groups)

BASE = os.path.join(os.path.dirname(__file__), "..")
MAN_DIR = os.path.join(BASE, "containment", "manifests")
REF_DIR = os.path.join(BASE, "containment", "references")
REP_DIR = os.path.join(BASE, "containment", "reports")


def relation_of(set_a, set_b, cols_a, cols_b):
    """Expected relation of A relative to B on normalized result sets."""
    if len(cols_a) != len(cols_b):
        return "unknown"
    if set_a == set_b:
        return "equivalent"
    if set_a < set_b:
        return "contained_in"
    if set_a > set_b:
        return "contains"
    return "incomparable"


def analyse_group(grp, results):
    """Fill expected_* fields from the per-query normalized sets."""
    qids = [q["query_id"] for q in grp["queries"]]
    sets = {qid: results[qid]["set"] for qid in qids}
    cols = {qid: results[qid]["columns"] for qid in qids}
    pairwise = []
    for i, a in enumerate(qids):
        for b in qids[i + 1:]:
            pairwise.append({"left": a, "right": b,
                             "relation": relation_of(sets[a], sets[b],
                                                     cols[a], cols[b])})
    grp["expected_pairwise"] = pairwise

    def rel(a, b):
        for p in pairwise:
            if p["left"] == a and p["right"] == b:
                return p["relation"]
            if p["left"] == b and p["right"] == a:
                r = p["relation"]
                return {"contains": "contained_in",
                        "contained_in": "contains"}.get(r, r)
        return "unknown"

    comparable = [q for q in qids
                  if not all(rel(q, o) == "unknown"
                             for o in qids if o != q)] or qids
    grp["expected_broadest"] = sorted(
        q for q in comparable
        if not any(rel(q, o) == "contained_in"
                   for o in qids if o != q))
    grp["expected_narrowest"] = sorted(
        q for q in comparable
        if not any(rel(q, o) == "contains" for o in qids if o != q))
    # equivalence classes with >= 2 members
    classes, seen = [], set()
    for q in qids:
        if q in seen:
            continue
        cls = [q] + [o for o in qids if o != q
                     and rel(q, o) == "equivalent"]
        if len(cls) > 1:
            classes.append(sorted(cls))
        seen.update(cls)
    grp["expected_equivalence_classes"] = classes
    edges = sorted(f"{p['right']} < {p['left']}" if p["relation"] ==
                   "contains" else f"{p['left']} < {p['right']}"
                   for p in pairwise
                   if p["relation"] in ("contains", "contained_in"))
    grp["expected_hierarchy"] = "; ".join(edges)
    grp["requires_counterexample"] = any(
        p["relation"] in ("contains", "contained_in", "incomparable")
        for p in pairwise)
    return grp


def main():
    groups = build_all_groups()
    failures, refs_by_group = [], {}
    for grp in groups:
        results = {}
        for q in grp["queries"]:
            r = bdb.execute_readonly(grp["database_id"],
                                     q["reference_sql"])
            if not r["ok"]:
                failures.append({"group": grp["group_id"],
                                 "query": q["query_id"],
                                 "error": r["error"],
                                 "sql": q["reference_sql"][:140]})
                continue
            norm = set(scoring.normalize_rows(r["rows"]))
            q["expected_row_count"] = r["row_count"]
            q["expected_result_hash"] = scoring.result_hash(
                r["rows"], "set_rows")
            results[q["query_id"]] = {
                "set": norm, "columns": r["columns"],
                "rows": r["rows"]}
        if len(results) != len(grp["queries"]):
            continue
        analyse_group(grp, results)
        refs_by_group[grp["group_id"]] = {
            "group_id": grp["group_id"],
            "queries": {qid: {"columns": v["columns"],
                              "rows": sorted(list(
                                  set(scoring.normalize_rows(v["rows"]))))}
                        for qid, v in results.items()}}
    if failures:
        print(f"REFERENCE FAILURES: {len(failures)}")
        for f in failures[:20]:
            print(f"  {f['group']}/{f['query']}: {f['error']}\n"
                  f"    {f['sql']}")
        sys.exit(1)

    ok, audit = mf.audit_containment_groups(groups)
    os.makedirs(REP_DIR, exist_ok=True)
    with open(os.path.join(REP_DIR, "group_audit.json"), "w",
              encoding="utf-8") as f:
        json.dump(audit, f, indent=2)
    if not ok:
        print("AUDIT PROBLEMS:")
        for p in audit["problems"]:
            print(" -", p)
        sys.exit(1)

    by_cat = collections.defaultdict(list)
    for grp in groups:
        by_cat[grp["category"]].append(grp)
    for cat, gs in sorted(by_cat.items()):
        mf.write_jsonl(os.path.join(MAN_DIR, f"{cat}.jsonl"), gs)
        mf.write_jsonl(os.path.join(REF_DIR, f"{cat}_refs.jsonl"),
                       [refs_by_group[grp["group_id"]] for grp in gs])
    sizes = collections.Counter(len(grp["queries"]) for grp in groups)
    print(f"BUILD OK: {len(groups)} groups; sizes={dict(sorted(sizes.items()))}")
    for cat, gs in sorted(by_cat.items()):
        d = collections.Counter(x["difficulty"] for x in gs)
        print(f"  {cat:28s} groups={len(gs)} "
              f"E/M/H={d.get('easy',0)}/{d.get('medium',0)}/{d.get('hard',0)}")


if __name__ == "__main__":
    main()
