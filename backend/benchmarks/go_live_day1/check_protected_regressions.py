"""
check_protected_regressions.py

Day 1 validator for the semantic protected_regression_manifest.json. Does NOT
re-run the pipeline; validates the manifest is well-formed and self-consistent:
  * required structure present (semantic-correct + separate controlled section);
  * every id list is unique (no duplicates);
  * per-database counts equal id-list lengths; totals equal the sums;
  * protected-correct and controlled-failure id sets are DISJOINT per database
    (a controlled failure must never be protected as correct);
  * every referenced source file exists.
Exit 0 = pass, 1 = failure.
"""
import json, os, sys
import day1_common as dc

MANIFEST = dc.out("protected_regression_manifest.json")


def _check_id_section(section, label, problems):
    checks = 0
    total = 0
    for db, d in section.get("by_database", {}).items():
        ids = d.get("test_ids", [])
        checks += 2
        if len(ids) != len(set(ids)):
            problems.append(f"{label} db{db}: duplicate test_ids")
        if len(ids) != d.get("count"):
            problems.append(f"{label} db{db}: count {d.get('count')} != len {len(ids)}")
        total += d.get("count", 0)
    checks += 1
    if total != section.get("total"):
        problems.append(f"{label}: total {section.get('total')} != sum {total}")
    return checks


def validate(m):
    """Pure structural + self-consistency validation. Returns (problems, checks)."""
    problems, checks = [], 0
    for key in ("schema_version", "source_files", "protected_semantically_correct",
                "controlled_failures", "protected_containment_recovered_edges"):
        checks += 1
        if key not in m:
            problems.append(f"missing top-level key: {key}")

    checks += _check_id_section(m.get("protected_semantically_correct", {}),
                                "protected_correct", problems)
    checks += _check_id_section(m.get("controlled_failures", {}),
                                "controlled", problems)

    # disjointness: protected-correct vs controlled per database
    corr = m.get("protected_semantically_correct", {}).get("by_database", {})
    ctrl = m.get("controlled_failures", {}).get("by_database", {})
    for db in set(corr) | set(ctrl):
        checks += 1
        overlap = set(corr.get(db, {}).get("test_ids", [])) & \
            set(ctrl.get(db, {}).get("test_ids", []))
        if overlap:
            problems.append(f"db{db}: {len(overlap)} id(s) both protected-correct "
                            f"AND controlled: {sorted(overlap)[:5]}")

    # containment edges: unique tuples + counts + total
    ce = m.get("protected_containment_recovered_edges", {})
    ctotal = 0
    for db, d in ce.get("by_database", {}).items():
        edges = [tuple(e) for e in d.get("edges", [])]
        checks += 2
        if len(edges) != len(set(edges)):
            problems.append(f"containment db{db}: duplicate edges")
        if len(edges) != d.get("count"):
            problems.append(f"containment db{db}: edge count mismatch")
        ctotal += d.get("count", 0)
    checks += 1
    if ctotal != ce.get("total"):
        problems.append(f"containment: total {ce.get('total')} != sum {ctotal}")
    return problems, checks


def main():
    if not os.path.exists(MANIFEST):
        print("FAIL: manifest not found:", MANIFEST)
        return 1
    m = json.load(open(MANIFEST, encoding="utf-8"))
    problems, checks = validate(m)
    for name, meta in m.get("source_files", {}).items():
        checks += 1
        if not os.path.exists(dc.rp(meta.get("path", ""))):
            problems.append(f"source file missing: {name} -> {meta.get('path')}")
    if problems:
        print(f"FAIL: {len(problems)} problem(s) across {checks} checks")
        for p in problems:
            print("  -", p)
        return 1
    print(f"PASS: {checks} checks; protected-correct="
          f"{m['protected_semantically_correct'].get('total')}, controlled="
          f"{m['controlled_failures'].get('total')}, recovered-edges="
          f"{m['protected_containment_recovered_edges'].get('total')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
