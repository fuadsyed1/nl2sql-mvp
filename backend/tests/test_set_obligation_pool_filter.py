"""Set-obligation pool-filter tests.

For a high-confidence multi-source either/or request, once ANY candidate
satisfies the separable-UNION set obligation, every non-satisfying candidate
(intersection / non-separable) is removed from the entire selection universe
before consensus, RC5, the population tie-break, and all overrides. When NO
candidate satisfies, nothing is filtered (the deterministic fallback / normal
path handles coverage).

The centerpiece is the EXACT five-candidate live t403 pool reproduced together —
not an isolated two-candidate call.
"""
import sqlite3

from sql_candidates.candidate_types import SqlCandidate
from sql_candidates.candidate_selector import select_best


IDX = {"tables": {
    "patients": [{"name": "patient_id", "is_key": True}, {"name": "first_name"}],
    "appointments": [{"name": "appointment_id", "is_key": True}, {"name": "patient_id"}],
    "billing_claims": [{"name": "claim_id", "is_key": True}, {"name": "patient_id"}]},
    "relationships": []}
CK = {"target_entity": "patients", "output_columns": ["patients.patient_id"],
      "required_sql_shape": "plain_select",
      "must_use_tables": ["patients", "appointments", "billing_claims"]}
Q = "List patient identifiers that appear either in appointments or billing claims."

# The five live candidates (SQL shapes verbatim); execution rows supplied to
# mirror the live result (intersections 42, UNION 62).
FIVE = {
    "llm_primary": ("SELECT DISTINCT patients.patient_id, patients.first_name "
                    "FROM appointments INNER JOIN billing_claims "
                    "ON appointments.appointment_id=billing_claims.appointment_id "
                    "INNER JOIN patients ON appointments.patient_id=patients.patient_id", 42,
                    ("patient_id", "first_name")),
    "llm_variant_2": ("SELECT DISTINCT appointments.patient_id, billing_claims.patient_id "
                      "FROM appointments INNER JOIN billing_claims "
                      "ON appointments.patient_id=billing_claims.patient_id", 42,
                      ("patient_id", "patient_id")),
    "llm_sql_direct": ("SELECT DISTINCT p.patient_id FROM patients p "
                       "JOIN appointments a ON p.patient_id=a.patient_id "
                       "JOIN billing_claims b ON p.patient_id=b.patient_id", 42, ("patient_id",)),
    "llm_sql_direct_grain": ("SELECT DISTINCT p.patient_id FROM patients p "
                             "JOIN appointments a ON p.patient_id=a.patient_id "
                             "JOIN billing_claims b ON p.patient_id=b.patient_id", 42, ("patient_id",)),
    "llm_sql_direct_variant": ("SELECT DISTINCT p.patient_id FROM patients p "
                               "JOIN appointments a ON p.patient_id=a.patient_id "
                               "UNION SELECT DISTINCT p.patient_id FROM patients p "
                               "JOIN billing_claims b ON p.patient_id=b.patient_id", 62, ("patient_id",)),
}


def _c(lbl, sql, n, cols, score=84):
    x = SqlCandidate(source=lbl, label=lbl, sql=sql,
                     execution={"executed": True, "columns": list(cols),
                                "rows": [[i] * len(cols) for i in range(n)], "row_count": n})
    x.score = score
    x.validation = {"fatal": []}
    return x


def _pool():
    return [_c(l, s, n, cols) for l, (s, n, cols) in FIVE.items()]


def test_exact_live_pool_selects_union_62():
    sel, meta = select_best(_pool(), checklist=CK, idx=IDX, question=Q)
    assert sel.label == "llm_sql_direct_variant"
    assert sel.row_count == 62
    # final SQL / label / score / reason all reference the same candidate
    assert meta["selected_candidate_label"] == sel.label
    assert meta["selected_candidate_source"] == sel.source
    # no 42-row intersection can be returned
    assert sel.row_count != 42


def test_01_valid_union_filters_out_intersections():
    sel, meta = select_best(_pool(), checklist=CK, idx=IDX, question=Q)
    f = meta.get("set_obligation_filter")
    assert f and f["applicable"] is True
    assert f["pool_after"] == ["llm_sql_direct_variant"]
    assert set(f["rejected_labels"]) == {
        "llm_primary", "llm_variant_2", "llm_sql_direct", "llm_sql_direct_grain"}


def test_02_or_exists_equivalent_satisfies():
    exists = _c("exists",
                "SELECT DISTINCT p.patient_id FROM patients p WHERE "
                "EXISTS (SELECT 1 FROM appointments a WHERE a.patient_id=p.patient_id) "
                "OR EXISTS (SELECT 1 FROM billing_claims b WHERE b.patient_id=p.patient_id)",
                62, ("patient_id",), score=80)
    inter = _c("llm_primary", FIVE["llm_primary"][0], 42, ("patient_id", "first_name"), score=90)
    sel, meta = select_best([inter, exists], checklist=CK, idx=IDX, question=Q)
    assert sel.label == "exists"


def test_03_no_satisfier_keeps_pool_available():
    # only intersection candidates -> filter finds no satisfier -> pool unchanged
    # (NOT an immediate controlled failure; the fallback/normal path continues).
    pool = [_c(l, s, n, cols) for l, (s, n, cols) in FIVE.items()
            if l != "llm_sql_direct_variant"]
    sel, meta = select_best(pool, checklist=CK, idx=IDX, question=Q)
    assert sel is not None                      # still returns a candidate
    f = meta.get("set_obligation_filter") or {}
    assert f.get("filtered") is False           # nothing filtered
    assert "no candidate satisfies" in (f.get("note") or "")


def test_04_intersection_question_unaffected():
    # a genuine "in BOTH" question is not a multi-source either/or -> no filter,
    # the (correct) intersection candidate is free to win.
    q = "List patient identifiers that appear in both appointments and billing claims."
    inter = _c("intersection",
               "SELECT DISTINCT p.patient_id FROM patients p "
               "JOIN appointments a ON p.patient_id=a.patient_id "
               "JOIN billing_claims b ON p.patient_id=b.patient_id", 42, ("patient_id",), score=90)
    sel, meta = select_best([inter], checklist=CK, idx=IDX, question=q)
    assert sel.label == "intersection"
    assert meta.get("set_obligation_filter") is None


# ---- 5-8 regressions ---------------------------------------------------- #
def test_05_t401_role_grounded_still_wins():
    idx = {"tables": {
        "doctors": [{"name": "doctor_id", "is_key": True}],
        "patients": [{"name": "patient_id", "is_key": True}, {"name": "primary_doctor_id"}],
        "appointments": [{"name": "appointment_id", "is_key": True}, {"name": "doctor_id"}]},
        "relationships": []}
    ck = {"target_entity": "doctors", "output_columns": ["doctors.doctor_id"],
          "required_sql_shape": "plain_select"}
    q = ("List doctor identifiers that appear either as primary doctors or "
         "appointment doctors.")
    allc = _c("all_doctors",
              "SELECT DISTINCT doctor_id FROM doctors "
              "UNION SELECT DISTINCT doctor_id FROM appointments", 80, ("doctor_id",))
    role = _c("role_grounded",
              "SELECT DISTINCT primary_doctor_id AS doctor_id FROM patients "
              "WHERE primary_doctor_id IS NOT NULL "
              "UNION SELECT DISTINCT doctor_id FROM appointments "
              "WHERE doctor_id IS NOT NULL", 72, ("doctor_id",))
    sel, meta = select_best([allc, role], checklist=ck, idx=idx, question=q)
    assert sel.label == "role_grounded"


def test_06_08_non_either_questions_unfiltered():
    # a subtraction (t51) / ratio (t96) / count (t142) question is not an
    # either/or -> the set filter never applies.
    for q in ["Show each department with unused beds based on bed capacity minus current occupancy.",
              "For each patient, calculate abnormal lab tests as a percentage of completed lab tests.",
              "How many distinct programs have students advised by instructors?"]:
        c = _c("x", "SELECT 1 FROM t", 1, ("c",))
        _sel, meta = select_best([c], checklist={"output_columns": ["c"]},
                                 idx={"tables": {"t": [{"name": "c"}]}}, question=q)
        assert meta.get("set_obligation_filter") is None


if __name__ == "__main__":   # pragma: no cover
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
