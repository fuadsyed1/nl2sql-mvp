"""Focused tests for role-to-column grounding (either/or) and categorical
complement value grounding.

All schemas are abstract / small; nothing about DB56, doctors, patients, lab
tests, or specific values is hardcoded in the production code these exercise.
"""
from types import SimpleNamespace as NS

import sqlite3
from sqlglot import parse_one

from sql_candidates.candidate_types import SqlCandidate
from sql_candidates.candidate_selector import select_best
from sql_candidates.semantic_obligations import (
    ground_either_roles, role_either_satisfied)
from schema.value_profiler import (
    categorical_complement, complement_value_satisfied)


# schema: entity `doctors`; role source columns patients.primary_doctor_id and
# appointments.doctor_id.
IDX = {"tables": {
    "doctors": [{"name": "doctor_id", "is_key": True}, {"name": "name"}],
    "patients": [{"name": "patient_id", "is_key": True},
                 {"name": "primary_doctor_id"}, {"name": "assigned_nurse_id"}],
    "appointments": [{"name": "appointment_id", "is_key": True},
                     {"name": "doctor_id"}, {"name": "patient_id"}]},
    "relationships": [{"from_table": "patients", "from_column": "primary_doctor_id",
                       "to_table": "doctors", "to_column": "doctor_id"}]}
CK = {"target_entity": "doctors", "output_columns": ["doctors.doctor_id"]}
Q = ("List doctor identifiers that appear either as primary doctors or "
     "appointment doctors.")


def _p(sql):
    return parse_one(sql, read="sqlite")


def _ground():
    return ground_either_roles(Q, CK, IDX)


# =========================== ROLE GROUNDING (1-13) ========================= #
def test_01_primary_doctors_grounds_to_role_column():
    g = _ground()
    a = next(x for x in g if x["phrase"].startswith("primary"))
    assert (a["table"], a["column"]) == ("patients", "primary_doctor_id")
    assert a["provenance"] == "role_qualified_column"


def test_02_appointment_doctors_grounds_to_source_doctor_id():
    g = _ground()
    b = next(x for x in g if x["phrase"].startswith("appointment"))
    assert (b["table"], b["column"]) == ("appointments", "doctor_id")


def test_03_all_doctors_does_not_satisfy_primary_role():
    g = _ground()
    sql = _p("SELECT doctor_id FROM doctors UNION SELECT doctor_id FROM appointments")
    assert role_either_satisfied(sql, g) is False


def test_04_union_of_role_columns_satisfies():
    g = _ground()
    sql = _p("SELECT primary_doctor_id AS doctor_id FROM patients "
             "WHERE primary_doctor_id IS NOT NULL "
             "UNION SELECT doctor_id FROM appointments WHERE doctor_id IS NOT NULL")
    assert role_either_satisfied(sql, g) is True


def test_05_exists_or_equivalent_satisfies():
    g = _ground()
    sql = _p("SELECT DISTINCT d.doctor_id FROM doctors d "
             "WHERE EXISTS (SELECT 1 FROM patients p WHERE p.primary_doctor_id=d.doctor_id) "
             "OR EXISTS (SELECT 1 FROM appointments a WHERE a.doctor_id=d.doctor_id)")
    assert role_either_satisfied(sql, g) is True


def test_06_inner_join_intersection_does_not_satisfy():
    g = _ground()
    sql = _p("SELECT DISTINCT d.doctor_id FROM doctors d "
             "JOIN appointments a ON d.doctor_id=a.doctor_id "
             "JOIN patients p ON d.doctor_id=p.primary_doctor_id")
    assert role_either_satisfied(sql, g) is False


def test_07_two_branches_same_source_do_not_satisfy_both():
    g = _ground()
    sql = _p("SELECT doctor_id FROM appointments "
             "UNION SELECT doctor_id FROM appointments")
    assert role_either_satisfied(sql, g) is False


def test_08_unambiguous_only_no_grounding_stays_neutral():
    # entity with no role-qualified column and no role-named source -> None
    idx = {"tables": {"t": [{"name": "t_id", "is_key": True}],
                      "x": [{"name": "x_id", "is_key": True}]}, "relationships": []}
    ck = {"target_entity": "t", "output_columns": ["t.t_id"]}
    q = "List t identifiers that appear either as red t or blue t."
    assert ground_either_roles(q, ck, idx) is None


def test_09_role_qualified_non_key_text_not_an_identifier_source():
    # a role-qualified TEXT column (not key-like) must not be picked as an id
    # source; grounding should fall through / stay neutral for that phrase.
    idx = {"tables": {
        "doctors": [{"name": "doctor_id", "is_key": True}],
        "notes": [{"name": "note_id", "is_key": True},
                  {"name": "primary_doctor_comment"}]},   # text, not *_id
        "relationships": []}
    ck = {"target_entity": "doctors", "output_columns": ["doctors.doctor_id"]}
    q = "List doctor identifiers that appear either as primary doctors or lead doctors."
    g = ground_either_roles(q, ck, idx)
    # primary_doctor_comment is not key-like -> not grounded -> whole obl neutral
    assert g is None


def test_10_fk_relationship_backed_role_column():
    g = _ground()
    a = next(x for x in g if x["phrase"].startswith("primary"))
    # the grounded role column is the FK to the target entity id
    assert (a["table"], a["column"]) == ("patients", "primary_doctor_id")


def test_11_plain_list_all_doctors_from_base_table_valid():
    # a non-either "list all doctors" imposes no role obligation.
    from sql_candidates.semantic_obligations import question_either_union_obligation
    assert question_either_union_obligation("List all doctors") in (False, None)


def test_12_selector_picks_role_grounded_over_all_doctors():
    def c(src, lbl, sql, rows):
        x = SqlCandidate(source=src, label=lbl, sql=sql,
                         execution={"executed": True, "columns": ["doctor_id"],
                                    "rows": rows, "row_count": len(rows)})
        x.score = 85
        x.validation = {"fatal": []}
        return x
    wrong = c("llm_sql_direct", "all_doctors",
              "SELECT DISTINCT doctor_id FROM doctors "
              "UNION SELECT DISTINCT doctor_id FROM appointments",
              [[i] for i in range(80)])
    right = c("llm_sql_direct_variant", "role_grounded",
              "SELECT DISTINCT d.doctor_id FROM doctors d WHERE "
              "EXISTS (SELECT 1 FROM patients p WHERE p.primary_doctor_id=d.doctor_id) "
              "OR EXISTS (SELECT 1 FROM appointments a WHERE a.doctor_id=d.doctor_id)",
              [[i] for i in range(72)])
    ck = dict(CK, required_sql_shape="plain_select",
              must_use_tables=["doctors", "appointments"])
    sel, meta = select_best([wrong, right], checklist=ck, idx=IDX, question=Q)
    assert sel.label == "role_grounded"       # 72-row role-grounded result wins


def test_13_t401_style_role_grounding_passes():
    # the former xfail scenario now grounds and discriminates correctly.
    g = _ground()
    assert g is not None and len(g) == 2


# ====================== CATEGORICAL VALUE GROUNDING (14-24) ================= #
PROF = {"lab_tests": {"abnormal_flag": ["normal", "low", "high", "critical"],
                      "test_status": ["completed", "pending", "cancelled"]}}
QV = "For each patient, calculate abnormal lab tests as a percentage of completed lab tests."


def test_14_abnormal_maps_to_complement_set():
    g = categorical_complement(QV, PROF)
    assert g["column"] == "abnormal_flag"
    assert set(v.lower() for v in g["grounded_values"]) == {"low", "high", "critical"}


def test_15_base_value_normal_excluded():
    g = categorical_complement(QV, PROF)
    assert "normal" not in {v.lower() for v in g["grounded_values"]}
    assert g["base"] == "normal"


def test_16_no_unseen_value_invented():
    g = categorical_complement(QV, PROF)
    assert set(g["grounded_values"]) <= set(PROF["lab_tests"]["abnormal_flag"])


def test_17_text_status_not_defaulted_to_boolean():
    g = categorical_complement(QV, PROF)
    assert complement_value_satisfied("abnormal_flag = '1'", g) is False


def test_18_single_category_incomplete():
    g = categorical_complement(QV, PROF)
    assert complement_value_satisfied(
        "SUM(CASE WHEN abnormal_flag='high' THEN 1 ELSE 0 END)", g) is False


def test_19_full_complement_in_set_satisfies():
    g = categorical_complement(QV, PROF)
    assert complement_value_satisfied(
        "abnormal_flag IN ('critical','high','low')", g) is True


def test_20_completed_denominator_grounded_independently():
    # 'completed' is a normal stored value of a DIFFERENT column; it must not be
    # mistaken for the abnormal complement.
    g = categorical_complement(QV, PROF)
    assert g["column"] == "abnormal_flag"
    assert "completed" not in {v.lower() for v in g["grounded_values"]}


def test_21_percentage_nullif_execution():
    con = sqlite3.connect(":memory:")
    con.executescript(
        "CREATE TABLE lab_tests(patient_id INT, abnormal_flag TEXT, test_status TEXT);"
        "INSERT INTO lab_tests VALUES (1,'critical','completed'),(1,'normal','completed'),"
        "(2,'low','completed'),(2,'high','pending');")
    sql = ("SELECT patient_id, 100.0*SUM(CASE WHEN abnormal_flag IN "
           "('critical','high','low') THEN 1 ELSE 0 END)/NULLIF(COUNT(*),0) AS pct "
           "FROM lab_tests WHERE test_status='completed' GROUP BY patient_id")
    got = {r[0]: round(r[1], 1) for r in con.execute(sql).fetchall()}
    con.close()
    assert got == {1: 50.0, 2: 100.0}     # p1: 1/2 completed abnormal; p2: 1/1


def test_22_incomplete_profile_stays_neutral():
    assert categorical_complement(QV, {"lab_tests": {"abnormal_flag": ["normal"]}}) is None


def test_23_binary_column_direct_grounding():
    g = categorical_complement(QV, {"lab_tests": {"abnormal_flag": ["normal", "abnormal"]}})
    assert g["mode"] == "direct"
    assert [v.lower() for v in g["grounded_values"]] == ["abnormal"]


def test_24_t96_offline_executes_full_complement():
    con = sqlite3.connect(":memory:")
    con.executescript(
        "CREATE TABLE lab_tests(patient_id INT, abnormal_flag TEXT, test_status TEXT);"
        "INSERT INTO lab_tests VALUES (1,'critical','completed'),(1,'low','completed'),"
        "(1,'normal','completed'),(2,'high','completed');")
    g = categorical_complement(QV, PROF)
    vals = ",".join(f"'{v}'" for v in g["grounded_values"])
    sql = (f"SELECT patient_id, SUM(CASE WHEN abnormal_flag IN ({vals}) THEN 1 ELSE 0 END) "
           f"AS abnormal_count, COUNT(*) AS total_count, "
           f"100.0*SUM(CASE WHEN abnormal_flag IN ({vals}) THEN 1 ELSE 0 END)"
           f"/NULLIF(COUNT(*),0) AS abnormal_percentage "
           f"FROM lab_tests WHERE test_status='completed' GROUP BY patient_id")
    rows = con.execute(sql).fetchall()
    con.close()
    assert complement_value_satisfied(sql, g) is True
    got = {r[0]: (r[1], r[2]) for r in rows}
    assert got == {1: (2, 3), 2: (1, 1)}   # p1: 2 abnormal of 3; p2: 1 of 1


# ============================ REGRESSION (25-30) =========================== #
def test_25_existing_set_operation_still_grounds_by_table():
    # a table-source either/or (no role qualifiers) still grounds via tables and
    # a UNION of the two sources satisfies it.
    idx = {"tables": {
        "patients": [{"name": "patient_id", "is_key": True}],
        "appointments": [{"name": "patient_id"}],
        "billing_claims": [{"name": "patient_id"}]}, "relationships": []}
    ck = {"target_entity": "patients", "output_columns": ["patients.patient_id"]}
    q = "List patient identifiers that appear either in appointments or billing claims"
    g = ground_either_roles(q, ck, idx)
    # both alternatives ground to (source, patient_id)
    assert g is not None
    sql = _p("SELECT patient_id FROM appointments "
             "UNION SELECT patient_id FROM billing_claims")
    assert role_either_satisfied(sql, g) is True


def test_26_role_grounding_neutral_on_non_either_question():
    assert ground_either_roles("How many doctors are there?", CK, IDX) is None


def test_27_complement_neutral_without_concept():
    assert categorical_complement("list completed lab tests", PROF) is None


def test_28_complement_no_false_substring_match():
    # 'abnormal' must not spuriously match a single-letter status like wing 'B'
    prof = {"departments": {"wing": ["A", "B", "C", "D"]},
            "lab_tests": {"abnormal_flag": ["normal", "low", "high", "critical"]}}
    g = categorical_complement(QV, prof)
    assert g["column"] == "abnormal_flag"


def test_29_role_columns_are_key_like_only():
    g = _ground()
    for a in g:
        col = a["column"]
        assert col.endswith("_id") or col.endswith("_key") or col == "id"


def test_30_both_alternatives_required_else_neutral():
    # if only ONE alternative grounds, the whole obligation is neutral (None).
    idx = {"tables": {
        "doctors": [{"name": "doctor_id", "is_key": True}],
        "appointments": [{"name": "doctor_id"}]}, "relationships": []}
    ck = {"target_entity": "doctors", "output_columns": ["doctors.doctor_id"]}
    q = "List doctor identifiers that appear either as primary doctors or appointment doctors."
    # no primary_doctor_id column anywhere -> primary role ungrounded -> None
    assert ground_either_roles(q, ck, idx) is None


if __name__ == "__main__":   # pragma: no cover
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
