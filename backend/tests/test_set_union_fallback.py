"""Focused tests for the deterministic SET-UNION candidate fallback.

Abstract schemas + a small in-memory DB; nothing about DB56 / specific tables /
columns / test-ids is hardcoded in the production code exercised here.
"""
import sqlite3

from sqlglot import parse_one

from sql_candidates.set_fallback import synthesize_set_union
from sql_candidates.semantic_obligations import role_either_satisfied, ground_either_roles
from sql_candidates.candidate_types import SqlCandidate
from sql_candidates.candidate_selector import select_best


IDX = {"tables": {
    "patients": [{"name": "patient_id", "is_key": True}, {"name": "first_name"}],
    "appointments": [{"name": "appointment_id", "is_key": True}, {"name": "patient_id"}],
    "billing_claims": [{"name": "claim_id", "is_key": True}, {"name": "patient_id"}]},
    "relationships": []}
CK = {"target_entity": "patients", "output_columns": ["patients.patient_id"],
      "required_sql_shape": "plain_select"}
Q = "List patient identifiers that appear either in appointments or billing claims."
INTER = ("SELECT DISTINCT a.patient_id, p.first_name FROM appointments a "
         "JOIN billing_claims b ON a.patient_id=b.patient_id "
         "JOIN patients p ON a.patient_id=p.patient_id")


def test_01_generates_union_when_all_intersections():
    sql, meta = synthesize_set_union(Q, CK, IDX, [INTER])
    assert sql is not None
    tree = parse_one(sql, read="sqlite")
    g = ground_either_roles(Q, CK, IDX)
    assert role_either_satisfied(tree, g) is True
    assert {a["table"] for a in meta["alternatives"]} == {"appointments", "billing_claims"}


def test_02_union_returns_62_and_wins():
    con = sqlite3.connect(":memory:")
    con.executescript(
        "CREATE TABLE appointments(appointment_id INT, patient_id INT);"
        "CREATE TABLE billing_claims(claim_id INT, patient_id INT);"
        "CREATE TABLE patients(patient_id INT, first_name TEXT);"
        # patients 1..40 in appointments; 30..61 in billing -> union = 1..61 = 61
        + "".join(f"INSERT INTO appointments VALUES ({i},{i});" for i in range(1, 41))
        + "".join(f"INSERT INTO billing_claims VALUES ({i},{i});" for i in range(30, 62)))
    sql, _ = synthesize_set_union(Q, CK, IDX, [INTER])
    n_union = len(con.execute(sql).fetchall())
    n_inter = len(con.execute(
        "SELECT DISTINCT a.patient_id FROM appointments a "
        "JOIN billing_claims b ON a.patient_id=b.patient_id").fetchall())
    con.close()
    assert n_union > n_inter          # union (61) strictly covers more than intersection (11)

    def c(lbl, s, n):
        x = SqlCandidate(source="llm_sql_direct" if "union" in lbl else "llm_primary",
                         label=lbl, sql=s,
                         execution={"executed": True, "columns": ["patient_id"],
                                    "rows": [[i] for i in range(n)], "row_count": n})
        x.score = 90 if lbl == "intersection" else 67
        x.validation = {"fatal": []}
        return x
    sel, meta = select_best(
        [c("intersection", INTER, n_inter), c("deterministic_set_union", sql, n_union)],
        checklist=CK, idx=IDX, question=Q)
    assert sel.label == "deterministic_set_union"


def test_03_existing_union_prevents_duplicate():
    existing = ("SELECT patient_id FROM appointments "
                "UNION SELECT patient_id FROM billing_claims")
    sql, reason = synthesize_set_union(Q, CK, IDX, [INTER, existing])
    assert sql is None
    assert reason == "existing_candidate_already_satisfies_set"


def test_04_intersection_request_no_union():
    sql, reason = synthesize_set_union(
        "List patients that appear in both appointments and billing claims.",
        CK, IDX, [INTER])
    assert sql is None


def test_05_ambiguous_mapping_neutral():
    # no groundable sources for the alternatives -> neutral
    idx = {"tables": {"patients": [{"name": "patient_id", "is_key": True}],
                      "x": [{"name": "x_id", "is_key": True}]}, "relationships": []}
    sql, reason = synthesize_set_union(
        "List patient identifiers that appear either as red patients or blue patients.",
        {"target_entity": "patients", "output_columns": ["patients.patient_id"]},
        idx, [])
    assert sql is None


def test_06_attribute_request_no_simple_fallback():
    ck = dict(CK, output_columns=["patients.patient_id", "patients.first_name"])
    sql, reason = synthesize_set_union(Q, ck, IDX, [INTER])
    assert sql is None
    assert reason == "source_attribute_requested"


def test_07_role_qualified_common_alias():
    idx = {"tables": {
        "doctors": [{"name": "doctor_id", "is_key": True}],
        "patients": [{"name": "patient_id", "is_key": True}, {"name": "primary_doctor_id"}],
        "appointments": [{"name": "appointment_id", "is_key": True}, {"name": "doctor_id"}]},
        "relationships": []}
    ck = {"target_entity": "doctors", "output_columns": ["doctors.doctor_id"],
          "required_sql_shape": "plain_select"}
    q = ("List doctor identifiers that appear either as primary doctors or "
         "appointment doctors.")
    sql, meta = synthesize_set_union(q, ck, idx, ["SELECT doctor_id FROM doctors"])
    assert sql is not None
    low = sql.lower()
    assert "primary_doctor_id as doctor_id" in low        # role column, common alias
    assert "doctor_id as doctor_id from appointments" in low
    assert meta["identifier"] == "doctor_id"


def test_08_aggregate_request_no_union():
    sql, reason = synthesize_set_union(
        "How many patients appear either in appointments or billing claims?",
        CK, IDX, [INTER])
    assert sql is None
    assert reason in ("aggregate_requested", "not_a_multi_source_either_request")


def test_09_synthesized_union_parses_and_is_distinct_per_branch():
    sql, _ = synthesize_set_union(Q, CK, IDX, [INTER])
    tree = parse_one(sql, read="sqlite")
    from sqlglot import exp
    assert isinstance(tree, exp.Union)
    # each branch selects the id with a NOT NULL guard
    assert sql.lower().count("is not null") == 2
    assert sql.lower().count("select distinct") == 2


if __name__ == "__main__":   # pragma: no cover
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
