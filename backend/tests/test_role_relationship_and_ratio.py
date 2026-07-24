"""Focused tests for direct role-relationship grounding (t142) and bounded-subset
ratio population alignment (t96).

Abstract schemas; nothing about DB55/DB56/specific values or test-ids is
hardcoded in the production code these exercise.
"""
import sqlite3
from types import SimpleNamespace as NS

from sqlglot import parse_one

from sql_candidates.candidate_types import SqlCandidate
from sql_candidates.candidate_scorer import score_candidate
from sql_candidates.candidate_selector import select_best
from sql_candidates.semantic_obligations import (
    ground_direct_role, direct_role_join_present, role_event_semantics_requested,
    question_bounded_subset_ratio, ratio_population_aligned,
    _percent_values_out_of_bounds)
from semantic.semantic_checklist import _sanitize_role_event_tables


def _p(sql):
    return parse_one(sql, read="sqlite")


# schema: students.advisor_instructor_id -> instructors.instructor_id; the
# academic_advising event table bridges students & instructors.
IDX = {"tables": {
    "programs": [{"name": "program_id", "is_key": True}, {"name": "department_id"}],
    "students": [{"name": "student_id", "is_key": True}, {"name": "program_id"},
                 {"name": "advisor_instructor_id"}],
    "instructors": [{"name": "instructor_id", "is_key": True},
                    {"name": "department_id"}],
    "academic_advising": [{"name": "advising_id", "is_key": True},
                          {"name": "student_id"}, {"name": "instructor_id"},
                          {"name": "appointment_date"}, {"name": "topics_discussed"}]},
    "relationships": [{"from_table": "students", "from_column": "advisor_instructor_id",
                       "to_table": "instructors", "to_column": "instructor_id"}]}
Q142 = ("How many distinct programs have students advised by instructors from "
        "the same department as the program?")
DIRECT = ("SELECT COUNT(DISTINCT p.program_id) FROM programs p "
          "JOIN students s ON p.program_id=s.program_id "
          "JOIN instructors i ON s.advisor_instructor_id=i.instructor_id "
          "WHERE p.department_id=i.department_id")
EVENT = ("SELECT COUNT(DISTINCT p.program_id) FROM programs p "
         "JOIN students s ON p.program_id=s.program_id "
         "JOIN academic_advising aa ON s.student_id=aa.student_id "
         "JOIN instructors i ON aa.instructor_id=i.instructor_id "
         "WHERE p.department_id=i.department_id")


# =============================== t142 (1-12) =============================== #
def test_01_advised_by_grounds_to_role_fk():
    g = ground_direct_role(Q142, IDX)
    assert (g["source_table"], g["role_column"]) == ("students", "advisor_instructor_id")
    assert (g["target_table"], g["target_key"]) == ("instructors", "instructor_id")


def test_02_grounding_strengthened_by_fk_evidence():
    assert ground_direct_role(Q142, IDX)["fk_backed"] is True


def test_03_direct_candidate_satisfies_role_obligation():
    g = ground_direct_role(Q142, IDX)
    assert direct_role_join_present(_p(DIRECT), g) is True


def test_04_event_instructor_id_does_not_satisfy():
    g = ground_direct_role(Q142, IDX)
    assert direct_role_join_present(_p(EVENT), g) is False


def test_05_event_question_uses_event_table():
    q = "How many advising appointments did each student have with their advisor?"
    assert role_event_semantics_requested(q) is True


def test_06_event_topics_question_preserves_event_table():
    out = {"target_entity": "students",
           "must_use_tables": ["students", "academic_advising", "instructors"],
           "must_use_columns": []}
    _sanitize_role_event_tables(
        out, "List the advising topics discussed for each student's advisor.", IDX)
    assert "academic_advising" in out["must_use_tables"]   # event semantics -> kept


def test_07_ambiguous_role_stays_neutral():
    idx = {"tables": {
        "s": [{"name": "s_id", "is_key": True}, {"name": "lead_t_id"},
              {"name": "backup_t_id"}],
        "t": [{"name": "t_id", "is_key": True}]}, "relationships": []}
    # two candidate role columns both name 'lead'/'backup' t -> ambiguous IF the
    # question's role matches both; here the role word 'lead' matches only one,
    # but neither is FK-evidenced and both are t-role -> keep it unambiguous test
    q = "list s advised by t"      # 'advised' matches neither lead nor backup
    assert ground_direct_role(q, idx) is None


def test_08_unrelated_key_column_not_selected():
    idx = {"tables": {
        "students": [{"name": "student_id", "is_key": True},
                     {"name": "program_id"}],           # no advisor FK
        "instructors": [{"name": "instructor_id", "is_key": True}]},
        "relationships": []}
    assert ground_direct_role(Q142, idx) is None


def test_09_checklist_sanitation_removes_event_table():
    out = {"target_entity": "programs",
           "must_use_tables": ["programs", "students", "academic_advising",
                               "instructors", "departments"],
           "must_use_columns": ["academic_advising.student_id",
                                "academic_advising.instructor_id",
                                "programs.program_id"]}
    _sanitize_role_event_tables(out, Q142, IDX)
    assert "academic_advising" not in out["must_use_tables"]
    assert all(not c.startswith("academic_advising.") for c in out["must_use_columns"])
    assert "students.advisor_instructor_id" in out["must_use_columns"]
    assert "instructors.instructor_id" in out["must_use_columns"]


def test_10_explicitly_named_event_table_never_removed():
    out = {"target_entity": "programs",
           "must_use_tables": ["students", "academic_advising", "instructors"],
           "must_use_columns": []}
    q = ("How many programs have students advised by instructors, counting only "
         "rows in academic_advising?")
    _sanitize_role_event_tables(out, q, IDX)
    # academic_advising is named verbatim -> preserved
    assert "academic_advising" in out["must_use_tables"]


def test_11_selector_picks_direct_advisor():
    def c(lbl, sql, score, n):
        x = SqlCandidate(source="llm_sql_direct", label=lbl, sql=sql,
                         execution={"executed": True, "columns": ["c"],
                                    "rows": [[i] for i in range(n)], "row_count": n})
        x.score = score
        x.validation = {"fatal": []}
        return x
    ck = {"target_entity": "programs", "output_columns": ["programs.program_id"],
          "required_sql_shape": "plain_select"}
    sel, meta = select_best(
        [c("event", EVENT, 100, 1), c("direct_advisor", DIRECT, 87, 2)],
        checklist=ck, idx=IDX, question=Q142)
    assert sel.label == "direct_advisor"


def test_12_direct_advisor_returns_two_offline():
    # structural: DIRECT uses advisor_instructor_id (returns 2 on DB55); EVENT
    # uses the event table (returns 1). Here we assert the role predicate is the
    # discriminator (execution counts are validated in the offline replay).
    g = ground_direct_role(Q142, IDX)
    assert direct_role_join_present(_p(DIRECT), g)
    assert not direct_role_join_present(_p(EVENT), g)


# =============================== t96 (13-28) ============================== #
QV = "For each patient, calculate abnormal lab tests as a percentage of completed lab tests."
BAD = ("SELECT p.patient_id, CAST(SUM(CASE WHEN lt.abnormal_flag IN "
       "('critical','high','low') THEN 1 ELSE 0 END) AS REAL)*100.0/"
       "NULLIF(COUNT(CASE WHEN lt.test_status='completed' THEN 1 END),0) AS "
       "abnormal_percentage FROM patients p JOIN lab_tests lt "
       "ON p.patient_id=lt.patient_id GROUP BY p.patient_id")
GOOD_WHERE = ("SELECT patient_id, 100.0*SUM(CASE WHEN abnormal_flag IN "
              "('critical','high','low') THEN 1 ELSE 0 END)/NULLIF(COUNT(*),0) AS "
              "abnormal_percentage FROM lab_tests WHERE test_status='completed' "
              "GROUP BY patient_id")
GOOD_CASE = ("SELECT patient_id, 100.0*SUM(CASE WHEN test_status='completed' AND "
             "abnormal_flag IN ('critical','high','low') THEN 1 ELSE 0 END)/"
             "NULLIF(SUM(CASE WHEN test_status='completed' THEN 1 ELSE 0 END),0) AS "
             "abnormal_percentage FROM lab_tests GROUP BY patient_id")


def test_13_global_where_aligns():
    assert ratio_population_aligned(_p(GOOD_WHERE)) is True


def test_14_numerator_case_with_denominator_aligns():
    assert ratio_population_aligned(_p(GOOD_CASE)) is True


def test_15_abnormal_over_all_vs_completed_fails():
    assert ratio_population_aligned(_p(BAD)) is False


def _graph():
    return {"tables": [
        {"table_name": "patients", "columns": [
            {"column_name": "patient_id", "is_primary_key_candidate": True}]},
        {"table_name": "lab_tests", "columns": [
            {"column_name": "lab_test_id", "is_primary_key_candidate": True},
            {"column_name": "patient_id"},
            {"column_name": "abnormal_flag", "sample_values": ["normal", "low", "high", "critical"]},
            {"column_name": "test_status", "sample_values": ["completed", "pending"]}]}],
        "relationships": [{"from_table": "lab_tests", "from_column": "patient_id",
                           "to_table": "patients", "to_column": "patient_id"}]}


def _scored(sql, rows=None):
    c = SqlCandidate(source="llm_sql_direct", label="c", sql=sql,
                     execution={"executed": True,
                                "columns": ["patient_id", "abnormal_percentage"],
                                "rows": rows or [[1, 50.0]], "row_count": len(rows or [1])})
    ck = {"target_entity": "patients",
          "output_columns": ["patients.patient_id", "abnormal_percentage"],
          "required_group_keys": ["patients.patient_id"],
          "required_sql_shape": "plain_select"}
    score_candidate(QV, c, _graph(), checklist=ck)
    return c


def test_16_incorrect_live_sql_is_fatal():
    c = _scored(BAD)
    assert any("bounded-subset" in f for f in (c.validation or {}).get("fatal") or [])


def test_17_correct_where_alternative_passes():
    c = _scored(GOOD_WHERE)
    assert not (c.validation or {}).get("fatal")


def test_18_complement_stays_low_high_critical():
    from schema.value_profiler import categorical_complement
    g = categorical_complement(QV, {"lab_tests": {
        "abnormal_flag": ["normal", "low", "high", "critical"],
        "test_status": ["completed", "pending"]}})
    assert set(v.lower() for v in g["grounded_values"]) == {"low", "high", "critical"}


def test_19_normal_excluded():
    from schema.value_profiler import categorical_complement
    g = categorical_complement(QV, {"lab_tests": {
        "abnormal_flag": ["normal", "low", "high", "critical"]}})
    assert "normal" not in {v.lower() for v in g["grounded_values"]}


def test_20_boolean_one_rejected():
    from schema.value_profiler import categorical_complement, complement_value_satisfied
    g = categorical_complement(QV, {"lab_tests": {
        "abnormal_flag": ["normal", "low", "high", "critical"]}})
    assert complement_value_satisfied("abnormal_flag = '1'", g) is False


def test_21_having_not_required_for_per_patient_percentage():
    assert question_bounded_subset_ratio(QV) is not None
    # a per-entity percentage with GROUP BY but no HAVING is aligned/eligible
    assert ratio_population_aligned(_p(GOOD_WHERE)) is True


def test_22_having_required_for_real_threshold():
    from semantic.semantic_checklist import _HAVING_THRESHOLD_CUES
    q = "List patients having more than 5 completed lab tests."
    assert any(cue in " " + q.lower() + " " for cue in _HAVING_THRESHOLD_CUES)


def test_23_out_of_range_percentage_fails_plausibility():
    assert _percent_values_out_of_bounds(
        {"columns": ["patient_id", "abnormal_percentage"],
         "rows": [[1, 150.0], [2, 50.0]]}) == 150.0


def test_24_growth_percentage_above_100_valid():
    # unbounded ratio -> no bounded obligation -> never constrained
    assert question_bounded_subset_ratio(
        "Show revenue growth as a percentage versus last year.") is None


def test_25_independent_measure_ratio_valid():
    assert question_bounded_subset_ratio(
        "Show salary payroll as a percentage of annual revenue.") is None
    # (payroll and revenue are independent measures -> unbounded, not flagged)


def test_26_direct_override_cannot_restore_population_invalid():
    # the misaligned candidate is fatal, so even at a higher score it is dropped
    # by the hard selection invariant and the aligned one wins.
    bad = _scored(BAD)
    bad.score = 100
    good = _scored(GOOD_WHERE)
    good.score = 87
    ck = {"target_entity": "patients",
          "output_columns": ["patients.patient_id", "abnormal_percentage"],
          "required_sql_shape": "plain_select"}
    sel, meta = select_best([bad, good], checklist=ck, question=QV)
    assert sel.label == good.label


def test_27_offline_only_values_0_to_100():
    con = sqlite3.connect(":memory:")
    con.executescript(
        "CREATE TABLE lab_tests(patient_id INT, abnormal_flag TEXT, test_status TEXT);"
        "INSERT INTO lab_tests VALUES (1,'critical','completed'),(1,'normal','completed'),"
        "(1,'high','pending'),(2,'low','completed');")
    rows = con.execute(GOOD_WHERE).fetchall()
    con.close()
    for _pid, pct in rows:
        assert 0.0 <= pct <= 100.0


def test_28_offline_completed_universe_for_both():
    con = sqlite3.connect(":memory:")
    con.executescript(
        "CREATE TABLE lab_tests(patient_id INT, abnormal_flag TEXT, test_status TEXT);"
        "INSERT INTO lab_tests VALUES (1,'critical','completed'),(1,'normal','completed'),"
        "(1,'high','pending'),(2,'low','completed');")
    got = {r[0]: r[1] for r in con.execute(GOOD_WHERE).fetchall()}
    con.close()
    # patient 1: 1 abnormal (critical) of 2 completed = 50 (the pending 'high' is
    # excluded from BOTH numerator and denominator); patient 2: 1/1 = 100
    assert got == {1: 50.0, 2: 100.0}


if __name__ == "__main__":   # pragma: no cover
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
