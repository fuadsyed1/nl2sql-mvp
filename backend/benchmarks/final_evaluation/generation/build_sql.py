"""
Build the final SQL benchmark: instantiate templates, execute every
reference read-only, write manifests + references + audit reports.

    python -m benchmarks.final_evaluation.generation.build_sql

Deterministic: rebuilding produces identical manifests (hashes included).
Fails loudly when any reference SQL fails or any protocol audit fails.
"""

import collections
import json
import os
import sys

from benchmarks.final_evaluation.common import manifest as mf
from benchmarks.final_evaluation.generation import (
    templates_db46, templates_lahman, templates_aw, genlib)

BASE = os.path.join(os.path.dirname(__file__), "..")
MAN_DIR = os.path.join(BASE, "sql", "manifests")
REF_DIR = os.path.join(BASE, "sql", "references")
REP_DIR = os.path.join(BASE, "sql", "reports")


def all_templates():
    return (templates_db46.TEMPLATES + templates_lahman.TEMPLATES
            + templates_aw.TEMPLATES)


def main():
    templates = all_templates()
    cases, failures = genlib.build_cases(templates, execute=True)
    if failures:
        print(f"REFERENCE FAILURES: {len(failures)}")
        for f in failures[:25]:
            print(f"  {f['template']}: {f['error']}\n    {f['sql'][:160]}")
        sys.exit(1)

    ok, audit = mf.audit_sql_cases(cases)
    os.makedirs(REP_DIR, exist_ok=True)
    with open(os.path.join(REP_DIR, "duplicate_audit.json"), "w",
              encoding="utf-8") as f:
        json.dump(audit, f, indent=2)
    if not ok:
        print("AUDIT PROBLEMS:")
        for p in audit["problems"]:
            print(" -", p)
        sys.exit(1)

    by_cat = collections.defaultdict(list)
    for c in cases:
        by_cat[c["category"]].append(c)
    for cat, cs in sorted(by_cat.items()):
        refs = [{"case_id": c["case_id"],
                 "columns": c["expected_columns"],
                 "rows": c.pop("_reference_rows"),
                 "ok": True} for c in cs]
        mf.write_jsonl(os.path.join(MAN_DIR, f"{cat}.jsonl"), cs)
        mf.write_jsonl(os.path.join(REF_DIR, f"{cat}_refs.jsonl"), refs)

    zero = sum(1 for c in cases if c["expected_row_count"] == 0)
    print(f"BUILD OK: {len(cases)} cases, "
          f"{len({c['semantic_template_id'] for c in cases})} templates, "
          f"{zero} zero-row references")
    for cat, cs in sorted(by_cat.items()):
        tpl = len({c['semantic_template_id'] for c in cs})
        d = collections.Counter(c['difficulty'] for c in cs)
        db = collections.Counter(c['database_id'] for c in cs)
        print(f"  {cat:18s} cases={len(cs)} templates={tpl} "
              f"E/M/H={d['easy']}/{d['medium']}/{d['hard']} db={dict(db)}")


if __name__ == "__main__":
    main()
