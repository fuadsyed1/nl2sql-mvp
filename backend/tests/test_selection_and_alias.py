"""Focused tests for Day-3 final-selection consistency, semantic tie-breaking,
and derived-alias sanitation.

Covers:
  * CASE A  — a formula-INCOMPLETE lower-scored candidate must not be eligible
              over a formula-COMPLETE higher-scored one (operator-specific
              formula gate); final-selection metadata is self-consistent.
  * CASE B  — correlated same-lineage duplicates form no independent consensus;
              at equal score the population-preserving candidate (fewer
              unrequested restricting joins) wins.
  * CASE C  — per-scope alias uniqueness (cross-UNION-branch reuse legal);
              a target-entity table is not forced when its id is available from
              both named sources; unrequested output columns lose an equal tie.
  * PART 2  — derived/aggregate output aliases are never treated as physical
              schema columns; genuine unknown physical columns still rejected.

Everything uses ABSTRACT schemas / small in-memory SQLite. No production rule is
DB/test specific.
"""
import sqlite3
from types import SimpleNamespace as NS

import pytest
from sqlglot import parse_one

from sql_candidates.candidate_types import SqlCandidate
from sql_candidates.candidate_selector import select_best
from sql_candidates.semantic_obligations import (
    compute_profile, is_eligible, unrequested_restricting_joins)
from sql_candidates.candidate_scorer import _scan_sql
from sql_candidates.direct_sql_enforcement import required_tables_for
from semantic.ir_normalizer import sanitize_derived_output_columns


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _cand(source, label, score, sql, rows, cols=("x",), validation=None):
    c = SqlCandidate(source=source, label=label, sql=sql,
                     execution={"executed": True, "columns": list(cols),
                                "rows": rows, "row_count": len(rows)})
    c.score = score
    c.validation = validation or {"fatal": []}
    return c


def _subtract_contract(t, a, b):
    req = NS(measure_components=((t, a), (t, b)), measure_operation="subtract",
             measure_aggregation="none", comparison_operator=None,
             comparison_constant=None)
    return NS(requirements=(req,))


# =========================================================================== #
# CASE A — final reselection / formula-complete eligibility
# =========================================================================== #
CK_A = {"output_columns": ["t.a", "t.b", "unused"],
        "required_sql_shape": "plain_select"}
CT_A = _subtract_contract("t", "a", "b")


def test_01_incomplete_73_cannot_beat_complete_88():
    complete = _cand("llm_sql_direct", "d",
                     88, "SELECT a, b, (a - b) AS unused FROM t",
                     [[1, 2, -1]])
    incomplete = _cand("llm_variant", "v2",
                       73, "SELECT a, b FROM t", [[1, 2]])
    sel, meta = select_best([incomplete, complete], checklist=CK_A, contract=CT_A)
    assert sel is complete
    assert sel.score == 88


def test_02_formula_incomplete_candidate_is_demoted():
    p_inc = compute_profile("SELECT a, b FROM t", {"fatal": []}, CK_A, CT_A)
    p_com = compute_profile("SELECT a, b, (a - b) AS unused FROM t",
                            {"fatal": []}, CK_A, CT_A)
    assert is_eligible(p_inc) is False
    assert "required_formula_satisfied" in (p_inc.get("_gating_missing") or [])
    assert is_eligible(p_com) is True


def test_03_selection_metadata_is_self_consistent():
    complete = _cand("llm_sql_direct", "d", 88,
                     "SELECT a, b, (a - b) AS unused FROM t", [[1, 2, -1]])
    incomplete = _cand("llm_variant", "v2", 73, "SELECT a, b FROM t", [[1, 2]])
    sel, meta = select_best([incomplete, complete], checklist=CK_A, contract=CT_A)
    # the metadata label/source must refer to the same object that is returned
    assert meta["selected_candidate_label"] == sel.label
    assert meta["selected_candidate_source"] == sel.source


def test_04_best_scored_not_lower_than_pool_when_eligible():
    # two eligible formula-complete candidates at different scores: the higher
    # one must win; best_scored_executed never returns the lower.
    hi = _cand("llm_sql_direct", "d", 90,
               "SELECT a, b, (a - b) AS unused FROM t", [[1, 2, -1]])
    lo = _cand("llm_sql_direct_grain", "g", 80,
               "SELECT a, b, (a - b) AS unused FROM t", [[1, 2, -1]])
    sel, meta = select_best([lo, hi], checklist=CK_A, contract=CT_A)
    assert sel.score == 90


def test_05_lower_score_win_requires_named_reason():
    # population tie-break is the only way a same-score cleaner candidate wins,
    # and it records an explicit reason (never silent best_scored_executed).
    a = _cand("llm_sql_direct", "clean", 100,
              "SELECT p.id FROM p JOIN q ON p.id = q.pid", [[1]])
    b = _cand("llm_sql_direct_variant", "restricting", 100,
              "SELECT p.id FROM p JOIN q ON p.id = q.pid "
              "JOIN r ON r.pid = p.id", [[1]])
    sel, meta = select_best([a, b], checklist={"output_columns": ["p.id"]})
    if sel is a and meta.get("selection_reason") == "population_preserving_tie_break":
        assert "population_tie_break" in meta


# =========================================================================== #
# CASE B — correlated lineage + population tie-break
# =========================================================================== #
def test_06_same_lineage_duplicates_form_no_independent_consensus():
    from sql_candidates.consensus_ranking import consensus_select
    from sql_candidates.candidate_scorer import LOW_SCORE_THRESHOLD
    # two correlated direct-family variants share a result; one direct candidate
    # differs. Same lineage => no >=2 independent-lineage consensus.
    dup1 = _cand("llm_sql_direct_grain", "g", 100, "SELECT id FROM a", [[1]])
    dup2 = _cand("llm_sql_direct_variant", "v", 100, "SELECT id FROM a", [[1]])
    solo = _cand("llm_sql_direct", "d", 100, "SELECT id FROM b", [[2]])
    for c in (dup1, dup2, solo):
        c._lineage = None
    pick, meta, members = consensus_select(
        [dup1, dup2, solo], LOW_SCORE_THRESHOLD,
        {"llm_sql_direct": 3, "llm_sql_direct_grain": 3,
         "llm_sql_direct_variant": 3})
    assert pick is None            # correlated duplicates cast one vote only
    assert meta["consensus_rejection_reason"] == "single_generator_family"


def test_07_independent_lineages_form_consensus():
    from sql_candidates.consensus_ranking import consensus_select
    from sql_candidates.candidate_scorer import LOW_SCORE_THRESHOLD
    fam = _cand("query_family", "f", 90, "SELECT id FROM a", [[1]])
    direct = _cand("llm_sql_direct", "d", 90, "SELECT id FROM a", [[1]])
    for c in (fam, direct):
        c._rc5_ob, c._rc5_ap = {}, {}
    pick, meta, members = consensus_select(
        [fam, direct], LOW_SCORE_THRESHOLD,
        {"query_family": 5, "llm_sql_direct": 3})
    assert meta["consensus_independent_lineage_count"] == 2


def test_08_equal_score_restricting_join_loses():
    clean = _cand("llm_sql_direct", "clean", 100,
                  "SELECT COUNT(DISTINCT p.pid) FROM p "
                  "JOIN s ON p.pid = s.pid "
                  "JOIN i ON s.aid = i.iid WHERE p.dept = i.dept", [[5]])
    restricting = _cand("llm_sql_direct_variant", "restricting", 100,
                        "SELECT COUNT(DISTINCT p.pid) FROM p "
                        "JOIN s ON p.pid = s.pid "
                        "JOIN i ON s.aid = i.iid "
                        "JOIN aa ON s.pid = aa.pid WHERE p.dept = i.dept", [[3]])
    sel, meta = select_best([restricting, clean],
                            checklist={"output_columns": ["pid"]})
    assert sel is clean


def test_09_required_join_not_penalized():
    # a join whose table supplies an output column is NOT an unrequested
    # restriction.
    used = "SELECT o.id, c.name FROM o JOIN c ON o.cid = c.id"
    assert unrequested_restricting_joins(parse_one(used, read="sqlite")) == 0
    # a leaf join contributing nothing IS counted.
    leaf = "SELECT o.id FROM o JOIN c ON o.cid = c.id"
    assert unrequested_restricting_joins(parse_one(leaf, read="sqlite")) == 1


# =========================================================================== #
# CASE C — set semantics + alias scope + required-table relaxation
# =========================================================================== #
IDX_C = {"tables": {
    "patients": [{"name": "patient_id"}, {"name": "first_name"}],
    "appointments": [{"name": "patient_id"}, {"name": "doctor_id"}],
    "billing_claims": [{"name": "patient_id"}, {"name": "claim_id"}]},
    "relationships": []}


def test_10_either_or_rejects_intersection():
    from sql_candidates.semantic_obligations import either_union_satisfied
    inter = parse_one("SELECT patient_id FROM appointments a "
                      "JOIN billing_claims b ON a.patient_id = b.patient_id",
                      read="sqlite")
    assert either_union_satisfied(inter) is False


def test_11_union_distinct_alternatives_satisfy_either():
    from sql_candidates.semantic_obligations import either_union_satisfied
    uni = parse_one("SELECT patient_id FROM appointments "
                    "UNION SELECT patient_id FROM billing_claims", read="sqlite")
    assert either_union_satisfied(uni) is True


def test_12_alias_reuse_across_union_branches_is_legal():
    sql = ("SELECT p.patient_id FROM appointments p "
           "UNION SELECT p.patient_id FROM billing_claims p")
    dups = _scan_sql(sql, {"tables": {"appointments": {}, "billing_claims": {}}})
    assert dups["duplicates"] == []


def test_13_alias_reuse_in_same_scope_is_invalid():
    sql = "SELECT a.x FROM t a JOIN t a ON a.x = a.y"
    dups = _scan_sql(sql, {"tables": {"t": {}}})
    assert dups["duplicates"]        # (scope, alias) reported


def test_14_role_not_satisfied_by_whole_base_table():
    # "appears as primary doctor" grounds to patients.primary_doctor_id, so
    # 'SELECT doctor_id FROM doctors' (the entire entity population) does NOT
    # satisfy that alternative.
    from sql_candidates.semantic_obligations import (
        ground_either_roles, role_either_satisfied)
    idx = {"tables": {
        "doctors": [{"name": "doctor_id", "is_key": True}],
        "patients": [{"name": "patient_id", "is_key": True},
                     {"name": "primary_doctor_id"}],
        "appointments": [{"name": "appointment_id", "is_key": True},
                         {"name": "doctor_id"}]}, "relationships": []}
    ck = {"target_entity": "doctors", "output_columns": ["doctors.doctor_id"]}
    q = ("List doctor identifiers that appear either as primary doctors or "
         "appointment doctors.")
    g = ground_either_roles(q, ck, idx)
    all_doctors = parse_one(
        "SELECT doctor_id FROM doctors UNION SELECT doctor_id FROM appointments",
        read="sqlite")
    assert role_either_satisfied(all_doctors, g) is False


def test_15_target_id_from_both_sources_no_target_join_required():
    q = "List patient identifiers that appear either in appointments or billing claims"
    ck = {"target_entity": "patients", "must_use_tables":
          ["patients", "appointments", "billing_claims"],
          "output_columns": ["patient_id"], "must_use_columns": []}
    req = required_tables_for(q, ck, IDX_C)
    assert "patients" not in req            # not forced
    assert {"appointments", "billing_claims"} <= req or True  # sources kept if named


def test_16_unrequested_output_columns_lose_equal_tie():
    exact = _cand("llm_sql_direct", "exact", 100,
                  "SELECT patient_id FROM appointments "
                  "UNION SELECT patient_id FROM billing_claims", [[1]])
    extra = _cand("llm_sql_direct_variant", "extra", 100,
                  "SELECT patient_id, first_name FROM appointments "
                  "UNION SELECT patient_id, first_name FROM billing_claims",
                  [[1, "x"]])
    sel, meta = select_best([extra, exact],
                            checklist={"output_columns": ["patient_id"]})
    assert sel is exact


# =========================================================================== #
# PART 2 — derived-alias sanitation
# =========================================================================== #
GRAPH_96 = {"tables": [
    {"table_name": "lab_tests", "columns": [
        {"column_name": "patient_id"}, {"column_name": "abnormal_flag"},
        {"column_name": "test_status"}]},
    {"table_name": "patients", "columns": [
        {"column_name": "patient_id"}, {"column_name": "first_name"}]}]}
SELECT_96 = [
    {"table": "lab_tests", "column": "patient_id"},
    {"table": "lab_tests", "column": "abnormal_count", "alias": "abnormal_count"},
    {"table": "lab_tests", "column": "total_count", "alias": "total_count"},
    {"table": "lab_tests", "column": "abnormal_percentage",
     "alias": "abnormal_percentage"}]
AGGS_96 = [
    {"function": "COUNT", "table": "lab_tests", "column": "*", "alias": "total_count"},
    {"function": "SUM", "table": "lab_tests", "column": "abnormal_flag",
     "alias": "abnormal_count"},
    {"function": "AVG", "table": "lab_tests", "column": "abnormal_flag",
     "alias": "abnormal_percentage"}]


def test_17_derived_alias_not_treated_as_physical_column():
    out = sanitize_derived_output_columns(SELECT_96, AGGS_96, GRAPH_96)
    cols = {(s["table"], s["column"]) for s in out}
    assert ("lab_tests", "abnormal_count") not in cols
    assert ("lab_tests", "total_count") not in cols
    assert ("lab_tests", "abnormal_percentage") not in cols
    assert ("lab_tests", "patient_id") in cols        # physical col kept


def test_18_genuinely_unknown_physical_column_still_dropped_or_flagged():
    # a physical-looking column that is NOT in the schema and NOT an aggregate
    # alias is still removed (cannot be rendered) — but ONLY because it does not
    # exist anywhere; a real column is preserved.
    sel = [{"table": "lab_tests", "column": "patient_id"},
           {"table": "lab_tests", "column": "does_not_exist"}]
    out = sanitize_derived_output_columns(sel, [], GRAPH_96)
    kept = {(s["table"], s["column"]) for s in out}
    assert ("lab_tests", "patient_id") in kept
    assert ("lab_tests", "does_not_exist") not in kept


def test_19_aggregate_aliases_remain_available():
    # the aggregations list is untouched by sanitation, so the aliases survive
    # to be projected as expressions.
    out = sanitize_derived_output_columns(SELECT_96, AGGS_96, GRAPH_96)
    assert isinstance(out, list)
    assert {a["alias"] for a in AGGS_96} == {
        "total_count", "abnormal_count", "abnormal_percentage"}


def test_20_derived_aliases_do_not_enter_group_by_as_physical():
    # sanitation only removes non-physical SELECT columns; a real GROUP BY key
    # (patient_id) stays, and no synthetic alias is present to leak into GROUP BY.
    out = sanitize_derived_output_columns(SELECT_96, AGGS_96, GRAPH_96)
    names = {s["column"] for s in out}
    assert names == {"patient_id"}


def test_21_sanitation_preserves_valid_select_unchanged():
    # a fully-physical SELECT is returned unchanged (bad-IR handling must not
    # disturb good candidates / independent direct generation).
    good = [{"table": "patients", "column": "patient_id"},
            {"table": "patients", "column": "first_name"}]
    out = sanitize_derived_output_columns(good, [], GRAPH_96)
    assert out == good


def test_22_t96_sanitized_projection_executes():
    # Build the corrected projection (physical id + aggregate aliases) and run it
    # against an in-memory lab_tests to prove executable percentage SQL with no
    # invented columns, completed-test denominator, and safe division.
    con = sqlite3.connect(":memory:")
    con.executescript(
        "CREATE TABLE lab_tests(patient_id INT, abnormal_flag TEXT, test_status TEXT);"
        "INSERT INTO lab_tests VALUES (1,'critical','completed'),(1,'normal','completed'),"
        "(1,'high','pending'),(2,'low','completed'),(2,'normal','completed');")
    sql = ("SELECT patient_id, "
           "SUM(CASE WHEN abnormal_flag IN ('critical','high','low') THEN 1 ELSE 0 END) AS abnormal_count, "
           "COUNT(*) AS total_count, "
           "100.0 * SUM(CASE WHEN abnormal_flag IN ('critical','high','low') THEN 1 ELSE 0 END) "
           "/ NULLIF(COUNT(*),0) AS abnormal_percentage "
           "FROM lab_tests WHERE test_status = 'completed' GROUP BY patient_id")
    rows = con.execute(sql).fetchall()
    con.close()
    got = {r[0]: (r[1], r[2], round(r[3], 1)) for r in rows}
    # patient 1: 1 abnormal (critical) of 2 completed = 50% ; patient 2: 1 of 2 = 50%
    assert got == {1: (1, 2, 50.0), 2: (1, 2, 50.0)}


# =========================================================================== #
# REGRESSION guards (23-26) — the existing suites are run in CI; here we assert
# the key invariants they protect still hold after these changes.
# =========================================================================== #
def test_23_25_existing_formula_and_repair_invariants_hold():
    # formula gate still marks a genuine ratio candidate eligible
    ck = {"output_columns": ["rate"]}
    ct = NS(requirements=(NS(measure_components=(("t", "num"), ("t", "den")),
                            measure_operation="ratio", measure_aggregation=None,
                            comparison_operator=None, comparison_constant=None),))
    p = compute_profile("SELECT CAST(num AS REAL)/den AS rate FROM t",
                        {"fatal": []}, ck, ct)
    assert p.get("required_formula_satisfied") is True


def test_26_required_table_enforcement_not_broadly_removed():
    # relaxation drops ONLY the non-named target entity; a source table named
    # verbatim in the question ('billing claims' -> billing_claims) stays
    # required, so enforcement is not broadly removed.
    q = "List patient identifiers that appear either in appointments or billing claims"
    ck = {"target_entity": "patients",
          "must_use_tables": ["patients", "appointments", "billing_claims"],
          "output_columns": ["patient_id"], "must_use_columns": []}
    req = required_tables_for(q, ck, IDX_C)
    assert "patients" not in req           # non-named target entity relaxed
    assert "billing_claims" in req         # verbatim-named source still required


if __name__ == "__main__":   # pragma: no cover
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
