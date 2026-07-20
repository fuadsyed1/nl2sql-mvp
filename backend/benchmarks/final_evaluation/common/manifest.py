"""
final_evaluation/common/manifest.py

Manifest I/O + structural audits for both benchmark suites.

Manifests are JSONL (one case/group per line) so a partially written file is
still inspectable and diffs stay line-oriented. Audits enforce the frozen
protocol: exact counts, unique IDs, no duplicate questions or question/SQL
pairs, the 4-cases-per-semantic-template cap, the >=50-templates floor, the
60/80/60 difficulty split, and the zero-row ceiling.
"""

import collections
import hashlib
import json
import os

SQL_CATEGORIES = (
    "join", "multi_table_join", "group_by", "having", "subquery_cte",
    "set_operations", "order_limit_topk", "aggregation", "distinct_count",
    "derived_metric",
)
CONTAINMENT_CATEGORIES = (
    "simple_filter_chain", "conjunction_disjunction",
    "numeric_range_boundary", "join_refinement", "multi_table_refinement",
    "aggregate_having", "distinct_projection_key", "equivalence",
    "incomparable", "temporal", "derived_metric",
    "mixed_hierarchy_edge_cases",
)
CASES_PER_CATEGORY = 200
GROUPS_PER_CATEGORY = 20
DIFFICULTY_SPLIT = {"easy": 60, "medium": 80, "hard": 60}
MAX_CASES_PER_TEMPLATE = 4
MIN_TEMPLATES_PER_CATEGORY = 50
ZERO_ROW_CEILING = 0.10


def write_jsonl(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def audit_sql_cases(cases):
    """Full duplicate/count audit. Returns (ok, report_dict)."""
    problems = []
    by_cat = collections.defaultdict(list)
    for c in cases:
        by_cat[c["category"]].append(c)

    ids = [c["case_id"] for c in cases]
    dup_ids = [i for i, n in collections.Counter(ids).items() if n > 1]
    if dup_ids:
        problems.append(f"duplicate case ids: {dup_ids[:5]}")

    qs = [c["question"].strip().lower() for c in cases]
    dup_qs = [q for q, n in collections.Counter(qs).items() if n > 1]
    if dup_qs:
        problems.append(f"duplicate questions: {len(dup_qs)} "
                        f"(first: {dup_qs[0][:80]!r})")

    pairs = collections.Counter(
        (c["question"].strip().lower(), " ".join(c["reference_sql"].split()))
        for c in cases)
    dup_pairs = [p for p, n in pairs.items() if n > 1]
    if dup_pairs:
        problems.append(f"duplicate question/SQL pairs: {len(dup_pairs)}")

    if len(cases) != CASES_PER_CATEGORY * len(SQL_CATEGORIES):
        problems.append(f"total case count {len(cases)} != "
                        f"{CASES_PER_CATEGORY * len(SQL_CATEGORIES)}")

    cat_stats = {}
    for cat in SQL_CATEGORIES:
        cs = by_cat.get(cat, [])
        stats = {"cases": len(cs)}
        if len(cs) != CASES_PER_CATEGORY:
            problems.append(f"{cat}: {len(cs)} cases != {CASES_PER_CATEGORY}")
        tpl = collections.Counter(c["semantic_template_id"] for c in cs)
        stats["templates"] = len(tpl)
        if len(tpl) < MIN_TEMPLATES_PER_CATEGORY:
            problems.append(f"{cat}: only {len(tpl)} semantic templates "
                            f"(< {MIN_TEMPLATES_PER_CATEGORY})")
        over = {t: n for t, n in tpl.items() if n > MAX_CASES_PER_TEMPLATE}
        if over:
            problems.append(f"{cat}: templates over the "
                            f"{MAX_CASES_PER_TEMPLATE}-case cap: "
                            f"{list(over)[:3]}")
        diff = collections.Counter(c["difficulty"] for c in cs)
        stats["difficulty"] = dict(diff)
        for d, want in DIFFICULTY_SPLIT.items():
            if diff.get(d, 0) != want:
                problems.append(f"{cat}: difficulty {d} = {diff.get(d, 0)} "
                                f"!= {want}")
        stats["databases"] = dict(
            collections.Counter(c["database_id"] for c in cs))
        zero = sum(1 for c in cs if c.get("expected_row_count") == 0)
        stats["zero_row_cases"] = zero
        if zero > ZERO_ROW_CEILING * CASES_PER_CATEGORY:
            problems.append(f"{cat}: {zero} zero-row references exceed the "
                            f"{ZERO_ROW_CEILING:.0%} ceiling")
        cat_stats[cat] = stats

    return not problems, {"problems": problems, "categories": cat_stats,
                          "total_cases": len(cases)}


def audit_containment_groups(groups):
    problems = []
    by_cat = collections.defaultdict(list)
    for g in groups:
        by_cat[g["category"]].append(g)
    ids = [g["group_id"] for g in groups]
    dup = [i for i, n in collections.Counter(ids).items() if n > 1]
    if dup:
        problems.append(f"duplicate group ids: {dup[:5]}")
    if len(groups) != GROUPS_PER_CATEGORY * len(CONTAINMENT_CATEGORIES):
        problems.append(f"total groups {len(groups)} != "
                        f"{GROUPS_PER_CATEGORY * len(CONTAINMENT_CATEGORIES)}")
    stats = {}
    for cat in CONTAINMENT_CATEGORIES:
        gs = by_cat.get(cat, [])
        if len(gs) != GROUPS_PER_CATEGORY:
            problems.append(f"{cat}: {len(gs)} groups != "
                            f"{GROUPS_PER_CATEGORY}")
        sizes = collections.Counter(len(g["queries"]) for g in gs)
        for g in gs:
            if not 2 <= len(g["queries"]) <= 5:
                problems.append(f"{g['group_id']}: {len(g['queries'])} "
                                f"queries outside 2-5")
        stats[cat] = {"groups": len(gs), "sizes": dict(sizes)}
    return not problems, {"problems": problems, "categories": stats,
                          "total_groups": len(groups)}
