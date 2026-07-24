"""Final selector-ordering tests: a generic population/output tie-break must
never override a stronger semantic obligation (role provenance / either-or), and
an intersection must never beat a valid UNION for an either/or request.

Abstract schemas; no DB/test-id-specific production logic is exercised.
"""
from sqlglot import parse_one

from sql_candidates.candidate_types import SqlCandidate
from sql_candidates.candidate_selector import select_best
from sql_candidates.semantic_obligations import (
    ground_either_roles, role_either_satisfied)


def _c(src, lbl, score, sql, n, cols=("doctor_id",)):
    x = SqlCandidate(source=src, label=lbl, sql=sql,
                     execution={"executed": True, "columns": list(cols),
                                "rows": [[i] * len(cols) for i in range(n)],
                                "row_count": n})
    x.score = score
    x.validation = {"fatal": []}
    return x


# --------------------------------------------------------------------------- #
# t401 — role provenance must not be overridden by the population tie-break
# --------------------------------------------------------------------------- #
IDX401 = {"tables": {
    "doctors": [{"name": "doctor_id", "is_key": True}],
    "patients": [{"name": "patient_id", "is_key": True}, {"name": "primary_doctor_id"}],
    "appointments": [{"name": "appointment_id", "is_key": True}, {"name": "doctor_id"}]},
    "relationships": []}
CK401 = {"target_entity": "doctors", "output_columns": ["doctors.doctor_id"],
         "required_sql_shape": "plain_select"}
Q401 = ("List doctor identifiers that appear either as primary doctors or "
        "appointment doctors.")
ALL_DOCTORS = ("SELECT DISTINCT doctor_id FROM doctors "
               "UNION SELECT DISTINCT doctor_id FROM appointments")
ROLE_UNION = ("SELECT DISTINCT primary_doctor_id AS doctor_id FROM patients "
              "WHERE primary_doctor_id IS NOT NULL "
              "UNION SELECT DISTINCT doctor_id FROM appointments "
              "WHERE doctor_id IS NOT NULL")
ROLE_JOIN = ("SELECT DISTINCT primary_doctor_id AS doctor_id FROM patients "
             "WHERE primary_doctor_id IS NOT NULL "
             "UNION SELECT DISTINCT a.doctor_id FROM appointments a "
             "JOIN doctors d ON a.doctor_id=d.doctor_id")


def test_01_all_doctors_fails_role_obligation():
    g = ground_either_roles(Q401, CK401, IDX401)
    assert role_either_satisfied(parse_one(ALL_DOCTORS, read="sqlite"), g) is False


def test_02_role_grounded_passes_role_obligation():
    g = ground_either_roles(Q401, CK401, IDX401)
    assert role_either_satisfied(parse_one(ROLE_UNION, read="sqlite"), g) is True


def test_03_tie_break_cannot_replace_semantic_winner():
    # the role-grounded candidate uses a JOIN (1 restricting join); the wrong
    # all-doctors candidate has 0. The population tie-break must NOT switch to
    # the semantically-incomplete all-doctors candidate.
    sel, meta = select_best(
        [_c("llm_sql_direct", "all_doctors", 85, ALL_DOCTORS, 80),
         _c("llm_sql_direct_variant", "role_grounded", 85, ROLE_JOIN, 72)],
        checklist=CK401, idx=IDX401, question=Q401)
    assert sel.label == "role_grounded"
    assert meta.get("population_tie_break") is None
    # the semantically-incomplete all-doctors candidate must be excluded from
    # winning — either by the set-obligation filter (removed from the universe
    # before the tie-break) or, if it survived, by the tie-break skip guard.
    _rejected = set(
        (meta.get("set_obligation_filter") or {}).get("rejected_labels") or [])
    _skipped = set(
        (meta.get("population_tie_break_skipped") or {})
        .get("semantically_different_candidates") or [])
    assert "all_doctors" in (_rejected | _skipped)


def test_04_tie_break_still_works_among_equivalent():
    # two candidates with NO differing high-confidence obligation: the one with a
    # redundant restricting join loses to the clean one.
    idx = {"tables": {
        "p": [{"name": "pid", "is_key": True}],
        "s": [{"name": "sid", "is_key": True}, {"name": "pid"}, {"name": "aid"}],
        "i": [{"name": "iid", "is_key": True}],
        "aa": [{"name": "aaid", "is_key": True}, {"name": "sid"}]}, "relationships": []}
    clean = _c("llm_sql_direct", "clean", 100,
               "SELECT COUNT(DISTINCT p.pid) FROM p JOIN s ON p.pid=s.pid "
               "JOIN i ON s.aid=i.iid", 5, cols=("c",))
    redundant = _c("llm_sql_direct_variant", "redundant", 100,
                   "SELECT COUNT(DISTINCT p.pid) FROM p JOIN s ON p.pid=s.pid "
                   "JOIN i ON s.aid=i.iid JOIN aa ON s.sid=aa.sid", 3, cols=("c",))
    sel, meta = select_best([redundant, clean], checklist={"output_columns": ["pid"]},
                            idx=idx, question="count distinct p")
    assert sel.label == "clean"
    assert meta.get("selection_reason") == "population_preserving_tie_break"


def test_09_final_selection_metadata_consistent_t401():
    sel, meta = select_best(
        [_c("llm_sql_direct", "all_doctors", 85, ALL_DOCTORS, 80),
         _c("llm_sql_direct_variant", "role_grounded", 85, ROLE_JOIN, 72)],
        checklist=CK401, idx=IDX401, question=Q401)
    assert meta["selected_candidate_label"] == sel.label
    assert meta["selected_candidate_source"] == sel.source


# --------------------------------------------------------------------------- #
# t403 — an intersection must never beat a valid UNION for either/or
# --------------------------------------------------------------------------- #
IDX403 = {"tables": {
    "patients": [{"name": "patient_id", "is_key": True}, {"name": "first_name"}],
    "appointments": [{"name": "appointment_id", "is_key": True}, {"name": "patient_id"}],
    "billing_claims": [{"name": "claim_id", "is_key": True}, {"name": "patient_id"}]},
    "relationships": []}
CK403 = {"target_entity": "patients", "output_columns": ["patients.patient_id"],
         "required_sql_shape": "plain_select"}
Q403 = "List patient identifiers that appear either in appointments or billing claims."
INTERSECTION = ("SELECT DISTINCT a.patient_id, p.first_name FROM appointments a "
                "JOIN billing_claims b ON a.patient_id=b.patient_id "
                "JOIN patients p ON a.patient_id=p.patient_id")
UNION403 = ("SELECT patient_id FROM appointments "
            "UNION SELECT patient_id FROM billing_claims")


def test_05_intersection_fails_either_or():
    g = ground_either_roles(Q403, CK403, IDX403)
    assert role_either_satisfied(parse_one(INTERSECTION, read="sqlite"), g) is False


def test_06_union_passes_either_or():
    g = ground_either_roles(Q403, CK403, IDX403)
    assert role_either_satisfied(parse_one(UNION403, read="sqlite"), g) is True


def test_07_union_beats_intersection():
    # even when the intersection scores HIGHER, the UNION wins because it
    # satisfies the either/or obligation the intersection violates.
    sel, meta = select_best(
        [_c("llm_primary", "intersection", 90, INTERSECTION, 42, cols=("patient_id", "first_name")),
         _c("llm_sql_direct_variant", "union", 88, UNION403, 62, cols=("patient_id",))],
        checklist=CK403, idx=IDX403, question=Q403)
    assert sel.label == "union"


def test_08_unrequested_output_loses_equal_tie():
    # two VALID unions at equal score; the one projecting an unrequested column
    # loses the output tie-break (semantically equivalent -> tie-break applies).
    exact = _c("llm_sql_direct", "exact", 88, UNION403, 62, cols=("patient_id",))
    extra = _c("llm_sql_direct_variant", "extra", 88,
               "SELECT patient_id, first_name FROM appointments "
               "UNION SELECT patient_id, first_name FROM billing_claims", 62,
               cols=("patient_id", "first_name"))
    sel, meta = select_best([extra, exact], checklist=CK403, idx=IDX403, question=Q403)
    assert sel.label == "exact"


# --------------------------------------------------------------------------- #
# 10-12 regression: t51 / t142 / t96 obligations still discriminate
# --------------------------------------------------------------------------- #
def test_10_t51_subtraction_still_wins():
    from types import SimpleNamespace as NS
    from sql_candidates.semantic_obligations import compute_profile, is_eligible
    ck = {"output_columns": ["a", "b", "unused"], "required_sql_shape": "plain_select"}
    ct = NS(requirements=(NS(measure_components=(("t", "a"), ("t", "b")),
                            measure_operation="subtract", measure_aggregation="none",
                            comparison_operator=None, comparison_constant=None),))
    assert is_eligible(compute_profile("SELECT a,b,(a-b) AS unused FROM t", {"fatal": []}, ck, ct))
    assert not is_eligible(compute_profile("SELECT a,b FROM t", {"fatal": []}, ck, ct))


def test_11_t142_direct_role_still_discriminates():
    from sql_candidates.semantic_obligations import ground_direct_role, direct_role_join_present
    idx = {"tables": {
        "students": [{"name": "student_id", "is_key": True}, {"name": "advisor_instructor_id"}],
        "instructors": [{"name": "instructor_id", "is_key": True}]},
        "relationships": [{"from_table": "students", "from_column": "advisor_instructor_id",
                           "to_table": "instructors", "to_column": "instructor_id"}]}
    q = "How many programs have students advised by instructors?"
    g = ground_direct_role(q, idx)
    assert direct_role_join_present(parse_one(
        "SELECT 1 FROM students s JOIN instructors i ON s.advisor_instructor_id=i.instructor_id",
        read="sqlite"), g) is True


def test_12_t96_ratio_alignment_still_fatal():
    from sql_candidates.semantic_obligations import (
        question_bounded_subset_ratio, ratio_population_aligned)
    q = "For each patient, calculate abnormal lab tests as a percentage of completed lab tests."
    assert question_bounded_subset_ratio(q) is not None
    bad = ("SELECT patient_id, SUM(CASE WHEN abnormal_flag IN ('critical','high','low') "
           "THEN 1 ELSE 0 END)/NULLIF(COUNT(CASE WHEN test_status='completed' THEN 1 END),0) "
           "FROM lab_tests GROUP BY patient_id")
    assert ratio_population_aligned(parse_one(bad, read="sqlite")) is False


if __name__ == "__main__":   # pragma: no cover
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
