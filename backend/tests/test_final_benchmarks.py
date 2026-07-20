"""Part 10 — automated validation of the final-evaluation benchmark
infrastructure. Offline only: template counts, audits, scoring modes,
normalization, hashing, resume behavior, containment pair/hierarchy/
counterexample scoring, malformed entries, duplicate detection. The live
MindRouter model is never called.
"""

import json
import os

import pytest

from benchmarks.final_evaluation.common import manifest as mf
from benchmarks.final_evaluation.common import scoring
from benchmarks.final_evaluation.generation import genlib
from benchmarks.final_evaluation.generation.build_sql import all_templates
from benchmarks.final_evaluation.generation.containment_groups import (
    build_all_groups)
from benchmarks.final_evaluation.generation.build_containment import (
    analyse_group, relation_of)


# ---- manifest / template structure (no DB execution needed) -------------
def test_sql_template_and_case_counts():
    ts = all_templates()
    cases, failures = genlib.build_cases(ts, execute=False)
    assert failures == []
    assert len(cases) == 2000
    per_cat = {}
    for c in cases:
        per_cat.setdefault(c["category"], []).append(c)
    assert set(per_cat) == set(mf.SQL_CATEGORIES)
    for cat, cs in per_cat.items():
        assert len(cs) == 200, cat
        tpl = {c["semantic_template_id"] for c in cs}
        assert len(tpl) >= 50, cat
        diff = {}
        for c in cs:
            diff[c["difficulty"]] = diff.get(c["difficulty"], 0) + 1
        assert diff == {"easy": 60, "medium": 80, "hard": 60}, cat


def test_sql_cases_unique_ids_and_questions():
    cases, _ = genlib.build_cases(all_templates(), execute=False)
    ids = [c["case_id"] for c in cases]
    assert len(ids) == len(set(ids))
    qs = [c["question"].strip().lower() for c in cases]
    assert len(qs) == len(set(qs)), "duplicate questions found"


def test_audit_detects_duplicates_and_bad_counts():
    cases, _ = genlib.build_cases(all_templates(), execute=False)
    for c in cases:
        c.setdefault("expected_row_count", 1)
    ok, audit = mf.audit_sql_cases(cases)
    assert ok, audit["problems"]
    broken = [dict(c) for c in cases]
    broken[1]["case_id"] = broken[0]["case_id"]      # duplicate id
    broken[2]["question"] = broken[3]["question"]    # duplicate question
    ok2, audit2 = mf.audit_sql_cases(broken)
    assert not ok2
    assert any("duplicate case ids" in p for p in audit2["problems"])
    assert any("duplicate questions" in p for p in audit2["problems"])


def test_containment_group_counts():
    groups = build_all_groups()
    assert len(groups) == 240
    per_cat = {}
    for gp in groups:
        per_cat.setdefault(gp["category"], []).append(gp)
    assert set(per_cat) == set(mf.CONTAINMENT_CATEGORIES)
    for cat, gs in per_cat.items():
        assert len(gs) == 20, cat
        for gp in gs:
            assert 2 <= len(gp["queries"]) <= 5
    ids = [gp["group_id"] for gp in groups]
    assert len(ids) == len(set(ids))
    ok, audit = mf.audit_containment_groups(groups)
    assert ok, audit["problems"]


# ---- scoring modes / normalization --------------------------------------
def test_scalar_comparison_with_tolerance():
    eq, _ = scoring.compare_results("scalar", [[0.3]], [[0.30000001]])
    assert eq
    eq, _ = scoring.compare_results("scalar", [[0.3]], [[0.31]])
    assert not eq
    eq, _ = scoring.compare_results("scalar", [[42]], [["42.0"]])
    assert eq


def test_ordered_multiset_set_modes():
    a, b = [[1], [2], [2]], [[2], [1], [2]]
    assert not scoring.compare_results("ordered_rows", a, b)[0]
    assert scoring.compare_results("multiset_rows", a, b)[0]
    assert scoring.compare_results("set_rows", a, [[2], [1]])[0]
    assert not scoring.compare_results("multiset_rows", a, [[1], [2]])[0]


def test_null_normalization_and_hash_stability():
    assert scoring.normalize_value(None) == scoring.normalize_value(None)
    r1 = scoring.result_hash([[None, 1], [2, "x"]], "multiset_rows")
    r2 = scoring.result_hash([[2, "x"], [None, 1]], "multiset_rows")
    assert r1 == r2
    r3 = scoring.result_hash([[None, 1], [2, "x"]], "ordered_rows")
    r4 = scoring.result_hash([[2, "x"], [None, 1]], "ordered_rows")
    assert r3 != r4


def test_classify_verdicts():
    case = {"comparison_mode": "multiset_rows"}
    ref = {"ok": True, "columns": ["a"], "rows": [[1], [2]]}
    ok_resp = {"success": True,
               "execution": {"rows": [[2], [1]], "columns": ["x"]}}
    assert scoring.classify(case, ok_resp, ref)[0] == "correct"
    wrong = {"success": True,
             "execution": {"rows": [[9]], "columns": ["x"]}}
    assert scoring.classify(case, wrong, ref)[0] == "wrong_result"
    cols = {"success": True,
            "execution": {"rows": [[1, 2]], "columns": ["x", "y"]}}
    assert scoring.classify(case, cols, ref)[0] == "wrong_columns"
    ctrl = {"success": False, "error": "no_semantically_valid_sql"}
    assert scoring.classify(case, ctrl, ref)[0] == "controlled_failure"
    assert scoring.classify(case, None, ref)[0] == "execution_error"
    assert scoring.classify(case, ok_resp, ref,
                            timeout_hit=True)[0] == "timeout"
    assert scoring.classify(case, ok_resp,
                            {"ok": False})[0] == "invalid_reference"


# ---- containment expectation computation ---------------------------------
def test_relation_of():
    a, b = {(1,), (2,)}, {(1,), (2,), (3,)}
    assert relation_of(a, b, ["k"], ["k"]) == "contained_in"
    assert relation_of(b, a, ["k"], ["k"]) == "contains"
    assert relation_of(a, set(a), ["k"], ["k"]) == "equivalent"
    assert relation_of({(1,)}, {(2,)}, ["k"], ["k"]) == "incomparable"
    assert relation_of(a, b, ["k"], ["k", "j"]) == "unknown"


def test_analyse_group_hierarchy():
    grp = {"queries": [{"query_id": "Q1"}, {"query_id": "Q2"},
                       {"query_id": "Q3"}]}
    results = {
        "Q1": {"set": {(1,), (2,), (3,)}, "columns": ["k"]},
        "Q2": {"set": {(1,), (2,)}, "columns": ["k"]},
        "Q3": {"set": {(1,)}, "columns": ["k"]},
    }
    analyse_group(grp, results)
    rels = {(p["left"], p["right"]): p["relation"]
            for p in grp["expected_pairwise"]}
    assert rels[("Q1", "Q2")] == "contains"
    assert rels[("Q2", "Q3")] == "contains"
    assert grp["expected_broadest"] == ["Q1"]
    assert grp["expected_narrowest"] == ["Q3"]
    assert grp["expected_hierarchy"] == \
        "Q2 < Q1; Q3 < Q1; Q3 < Q2"
    assert grp["requires_counterexample"] is True


def test_analyse_group_equivalence_and_incomparable():
    grp = {"queries": [{"query_id": "Q1"}, {"query_id": "Q2"},
                       {"query_id": "Q3"}]}
    results = {
        "Q1": {"set": {(1,), (2,)}, "columns": ["k"]},
        "Q2": {"set": {(1,), (2,)}, "columns": ["k"]},
        "Q3": {"set": {(2,), (9,)}, "columns": ["k"]},
    }
    analyse_group(grp, results)
    assert grp["expected_equivalence_classes"] == [["Q1", "Q2"]]
    rels = {(p["left"], p["right"]): p["relation"]
            for p in grp["expected_pairwise"]}
    assert rels[("Q1", "Q3")] == "incomparable"
    assert sorted(grp["expected_broadest"]) == ["Q1", "Q2", "Q3"]


# ---- containment runner scoring (no HTTP) ---------------------------------
def _fake_group():
    grp = {"queries": [{"query_id": "Q1"}, {"query_id": "Q2"}],
           "expected_pairwise": [
               {"left": "Q1", "right": "Q2", "relation": "contains"}],
           "expected_broadest": ["Q1"], "expected_narrowest": ["Q2"],
           "expected_equivalence_classes": []}
    refs = {"queries": {"Q1": {"columns": ["k"],
                               "rows": [["1"], ["2"]]},
                        "Q2": {"columns": ["k"], "rows": [["1"]]}}}
    return grp, refs


def test_containment_pair_and_hierarchy_scoring():
    from benchmarks.final_evaluation.containment.runners import (
        run_containment_benchmark as rcb)
    grp, refs = _fake_group()
    response = {
        "query_results": [{"success": True, "sql": "S1"},
                          {"success": True, "sql": "S2"}],
        "pairwise_relationships": [
            {"query_a": 1, "query_b": 2,
             "relationship": "query_b_contained_in_query_a",
             "a_minus_b_rows": [["2"]], "b_minus_a_rows": []}],
        "analysis": {"main_queries": [{"index": 1}],
                     "equivalent_groups": []},
    }
    s = rcb.score_group(grp, refs, response)
    assert s["pairs_correct"] == 1 and s["pairs_total"] == 1
    assert s["broadest_correct"] and s["narrowest_correct"]
    assert s["hierarchy_correct"]
    assert s["counterexamples_checked"] == 1
    assert s["counterexamples_valid"] == 1
    # wrong relation -> pair and hierarchy fail
    response["pairwise_relationships"][0]["relationship"] = \
        "equivalent_on_current_database"
    s2 = rcb.score_group(grp, refs, response)
    assert s2["pairs_correct"] == 0 and not s2["hierarchy_correct"]


def test_counterexample_invalid_row_rejected():
    from benchmarks.final_evaluation.containment.runners import (
        run_containment_benchmark as rcb)
    grp, refs = _fake_group()
    response = {
        "query_results": [],
        "pairwise_relationships": [
            {"query_a": 1, "query_b": 2,
             "relationship": "query_b_contained_in_query_a",
             "a_minus_b_rows": [["1"]],  # in BOTH results -> invalid
             "b_minus_a_rows": []}],
        "analysis": {},
    }
    s = rcb.score_group(grp, refs, response)
    assert s["counterexamples_checked"] == 1
    assert s["counterexamples_valid"] == 0


# ---- resume / persistence -------------------------------------------------
def test_jsonl_roundtrip_and_resume_recovery(tmp_path):
    p = str(tmp_path / "r.jsonl")
    recs = [{"case_id": f"x_{i}", "verdict": "correct"} for i in range(4)]
    mf.write_jsonl(p, recs[:2])
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(recs[2]) + "\n")
        f.write('{"case_id": "x_3", "verdict"')  # torn write, no newline
    loaded = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                loaded.append(json.loads(line))
            except json.JSONDecodeError:
                continue                      # partial tail is recoverable
    assert [r["case_id"] for r in loaded] == ["x_0", "x_1", "x_2"]
    done = {r["case_id"] for r in loaded}
    remaining = [r for r in recs if r["case_id"] not in done]
    assert [r["case_id"] for r in remaining] == ["x_3"]


def test_malformed_manifest_entries_rejected():
    ok, audit = mf.audit_containment_groups([
        {"group_id": "g1", "category": "equivalence",
         "queries": [{"query_id": "Q1"}]},          # only 1 query
    ])
    assert not ok
    assert any("outside 2-5" in p for p in audit["problems"])


# ---- reference execution spot check (uses the real frozen DBs) ------------
@pytest.mark.skipif(
    not os.path.exists(os.path.join(
        os.path.dirname(__file__), "..", "uploads", "user_4", "databases",
        "db_46", "data.db")) and not os.environ.get(
            "FINAL_EVAL_BACKEND_DIR"),
    reason="benchmark databases not present")
def test_reference_execution_spot_check():
    from benchmarks.final_evaluation.common import db as bdb
    r = bdb.execute_readonly(46, "SELECT COUNT(*) FROM patients")
    assert r["ok"] and r["row_count"] == 1
    assert scoring.result_hash(r["rows"], "scalar")
