"""Focused tests for generic derived-arithmetic obligations.

Division / rate (X per Y, X divided by Y, ratio of X to Y, count denominators)
and row-level addition (A + B, combined A and B, total ... both roles), the
distinction from cross-row aggregation, and preservation of the no_aggregation
safeguard. Abstract schemas only — no DB/table/column/test-id specific logic.
"""
from sql_candidates.semantic_obligations import (
    question_derived_obligation as QDO, derived_operand_grounding as DOG,
    derived_output_satisfied as DOS, _parse, _schema_columns)
from sql_candidates.semantic_relationship_verifier import verify_semantic_relationships
from sql_candidates.candidate_types import SqlCandidate
from sql_candidates.candidate_selector import select_best


def _g(idx):
    return _schema_columns(idx)


def _ground(q, kind, idx):
    cols, keys = _g(idx)
    return DOG(q, kind, cols, keys, None, None, idx)


def _c(label, source, score, sql, rows):
    c = SqlCandidate(source=source, label=label, sql=sql,
                     execution={"executed": True, "columns": ["a"], "rows": rows,
                                "row_count": len(rows)})
    c.score = score
    c.validation = {"fatal": []}
    return c


IDX_DIV = {"tables": {"g": [{"name": "g_id", "is_key": True}, {"name": "budget"},
                            {"name": "member_count"}, {"name": "cost"},
                            {"name": "unit_count"}, {"name": "amount"},
                            {"name": "item_count"}]}}
IDX_ENTITY = {"tables": {"g": [{"name": "g_id", "is_key": True}, {"name": "budget"}],
                         "members": [{"name": "member_id", "is_key": True},
                                     {"name": "g_id"}]}}
IDX_ADD = {"tables": {"e": [{"name": "e_id", "is_key": True}, {"name": "home_value"},
                            {"name": "away_value"}, {"name": "first_amount"},
                            {"name": "second_amount"}]}}


# ===================== DIVISION / RATE =====================================
def test_1_budget_per_member_detects_division():
    q = "Show each group with budget per member."
    assert "ratio" in QDO(q)
    g = _ground(q, "ratio", IDX_DIV)
    assert g and g["kind"] == "ratio" and g["num"] == {"budget"} and g["den"] == {"member_count"}


def test_2_divided_by_detects_division():
    q = "Show cost divided by unit count."
    g = _ground(q, "ratio", IDX_DIV)
    assert g and g["num"] == {"cost"} and g["den"] == {"unit_count"}


def test_3_ratio_of_x_to_y_detects_division():
    q = "Show the ratio of amount to item count."
    assert "ratio" in QDO(q)
    g = _ground(q, "ratio", IDX_DIV)
    assert g and g["num"] == {"amount"} and g["den"] == {"item_count"}


def test_4_count_denominator_uses_count_entity_key():
    q = "Show each group with budget per member."
    g = _ground(q, "ratio", IDX_ENTITY)            # no member_count column
    assert g and g["num"] == {"budget"} and g["den"] == {"member_id"}
    ok = DOS(_parse("SELECT g.g_id, g.budget/NULLIF(COUNT(m.member_id),0) AS r "
                    "FROM g JOIN members m ON g.g_id = m.g_id GROUP BY g.g_id"), q, IDX_ENTITY)
    assert ok == (True, True)


def test_5_member_per_group_is_not_division():
    q = "Show each member per group."
    assert "ratio" not in QDO(q)                    # 'per' is output grain, not a rate


def test_6_numerator_denominator_separate_is_incomplete():
    q = "Show each group with budget per member."
    assert DOS(_parse("SELECT g_id, budget, member_count FROM g"), q, IDX_DIV) == (True, False)


def test_7_ratio_outranks_count_only_denominator():
    q = "Show each group with budget per member."
    good = _c("llm_sql_direct", "llm_sql_direct", 82,
              "SELECT g_id, budget, member_count, budget*1.0/NULLIF(member_count,0) AS r "
              "FROM g GROUP BY g_id", [[1]])
    bad = _c("llm_primary", "llm_primary", 90,
             "SELECT g_id, budget, member_count FROM g GROUP BY g_id", [[1]])
    sel, _ = select_best([bad, good], idx=IDX_DIV, question=q)
    assert sel is good


def test_8_reversed_division_is_incorrect():
    q = "Show each group with budget per member."
    assert DOS(_parse("SELECT g_id, member_count*1.0/NULLIF(budget,0) AS r FROM g GROUP BY g_id"),
               q, IDX_DIV) == (True, False)


# ===================== ROW-LEVEL ADDITION =================================
def test_9_total_both_sides_detects_addition():
    q = "Show each event with total values from both sides."
    IDX = {"tables": {"e": [{"name": "e_id", "is_key": True},
                            {"name": "home_value"}, {"name": "away_value"}]}}
    assert "add" in QDO(q)
    g = _ground(q, "add", IDX)
    assert g and g["kind"] == "set" and g["ops"] == {"home_value", "away_value"}


def test_10_combined_named_operands_detects_addition():
    q = "Show the combined value of first_amount and second_amount."
    assert "add" in QDO(q)
    g = _ground(q, "add", IDX_ADD)
    assert g and {"first_amount", "second_amount"} <= g["ops"]


def test_11_a_plus_b_satisfies():
    q = "Show each event with total values from both sides."
    IDX = {"tables": {"e": [{"name": "e_id", "is_key": True},
                            {"name": "home_value"}, {"name": "away_value"}]}}
    assert DOS(_parse("SELECT e_id, home_value + away_value AS total FROM e"), q, IDX) == (True, True)


def test_12_sum_grouped_does_not_satisfy_addition():
    q = "Show each event with total values from both sides."
    IDX = {"tables": {"e": [{"name": "e_id", "is_key": True},
                            {"name": "home_value"}, {"name": "away_value"}]}}
    assert DOS(_parse("SELECT e_id, SUM(home_value) AS h, SUM(away_value) AS a "
                      "FROM e GROUP BY e_id"), q, IDX) == (True, False)


def test_13_operands_separate_is_incomplete():
    q = "Show each event with total values from both sides."
    IDX = {"tables": {"e": [{"name": "e_id", "is_key": True},
                            {"name": "home_value"}, {"name": "away_value"}]}}
    assert DOS(_parse("SELECT e_id, home_value, away_value FROM e"), q, IDX) == (True, False)


def test_14_subtraction_does_not_satisfy_addition():
    q = "Show each event with total values from both sides."
    IDX = {"tables": {"e": [{"name": "e_id", "is_key": True},
                            {"name": "home_value"}, {"name": "away_value"}]}}
    assert DOS(_parse("SELECT e_id, home_value - away_value AS d FROM e"), q, IDX) == (True, False)


def test_15_row_level_addition_no_no_aggregation_penalty():
    q = "Show each event with total values from both sides."
    IDX = {"tables": {"e": [{"name": "e_id", "is_key": True},
                            {"name": "home_value"}, {"name": "away_value"}]}}
    delta, _r, checks = verify_semantic_relationships(
        q, None, "SELECT e_id, home_value + away_value AS total FROM e", IDX)
    assert checks.get("generic_fallback") is None
    assert checks.get("no_aggregation_suppressed_row_level_formula") is True


# ===================== AGGREGATE PRESERVATION =============================
def test_16_total_across_all_rows_is_not_a_derived_formula():
    assert QDO("Total amount across all rows.") == set()


def test_17_total_by_category_is_not_a_derived_formula():
    assert QDO("Total amount by category.") == set()


def test_18_bare_projection_for_aggregate_question_still_penalized():
    IDX = {"tables": {"orders": [{"name": "order_id"}, {"name": "revenue"}]}}
    delta, _r, checks = verify_semantic_relationships(
        "Show total revenue across all orders.", None, "SELECT revenue FROM orders", IDX)
    assert checks.get("generic_fallback") == "no_aggregation" and delta < 0


# ===================== AMBIGUITY ==========================================
def test_19_missing_second_operand_no_formula():
    q = "Show the combined value of first_amount."
    assert _ground(q, "add", IDX_ADD) is None


def test_20_both_without_grounded_pair_no_addition():
    q = "List groups that have both doctors and nurses."
    IDX = {"tables": {"g": [{"name": "g_id", "is_key": True},
                            {"name": "doctor_count"}, {"name": "nurse_count"}]}}
    assert _ground(q, "add", IDX) is None


def test_21_per_as_output_grain_no_division():
    for q in ("Show one row per customer.", "Display records per category.",
              "List one entry per order."):
        assert "ratio" not in QDO(q)


# ===================== OFFLINE REPRODUCTIONS ==============================
def test_repro_db56_t52_division():
    q = "Show each department with annual budget per doctor."
    IDX = {"tables": {"departments": [{"name": "department_id", "is_key": True},
                                      {"name": "department_name"}, {"name": "annual_budget"},
                                      {"name": "doctor_count"}]}}
    assert "ratio" in QDO(q)
    correct = ("SELECT department_name, annual_budget, doctor_count, "
               "annual_budget*1.0/NULLIF(doctor_count,0) AS annual_budget_per_doctor "
               "FROM departments GROUP BY department_id")
    wrong = "SELECT department_name, annual_budget, doctor_count FROM departments GROUP BY department_id"
    assert DOS(_parse(correct), q, IDX) == (True, True)
    assert DOS(_parse(wrong), q, IDX) == (True, False)
    sel, _ = select_best([_c("llm_primary", "llm_primary", 86, wrong, [[1]]),
                          _c("llm_sql_direct", "llm_sql_direct", 94, correct, [[1]])],
                         idx=IDX, question=q)
    assert sel.sql == correct


def test_repro_db57_t62_addition():
    q = "Show each match with total points scored by both teams."
    IDX = {"tables": {"matches": [{"name": "match_id", "is_key": True},
                                  {"name": "home_score"}, {"name": "away_score"}]}}
    assert "add" in QDO(q)
    correct = "SELECT match_id, home_score + away_score AS total_points FROM matches"
    wrong = ("SELECT match_id, SUM(home_score) AS h, SUM(away_score) AS a "
             "FROM matches GROUP BY match_id")
    assert DOS(_parse(correct), q, IDX) == (True, True)
    assert DOS(_parse(wrong), q, IDX) == (True, False)
    # correct row-level addition receives no no_aggregation penalty
    _d, _r, checks = verify_semantic_relationships(q, None, correct, IDX)
    assert checks.get("generic_fallback") is None
    # and it wins despite the SUM candidate scoring higher (RC5 obligation dominance)
    sel, _m = select_best([_c("llm_primary", "llm_primary", 93, wrong, [[1, 3, 2]]),
                           _c("llm_sql_direct", "llm_sql_direct", 78, correct, [[1, 5]])],
                          idx=IDX, question=q)
    assert sel.sql == correct
