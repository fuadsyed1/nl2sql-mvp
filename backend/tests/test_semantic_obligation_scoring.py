"""
Focused tests for the generic derived-output / set-either semantic obligation.

Covers the two new, question-gated + AST-decided obligations added to the
candidate profile (semantic_obligations), the RC5 ranking (rc5_ranking) and the
scorer (candidate_scorer):

  * a candidate that PROJECTS a requested add / subtract / ratio / percentage /
    date expression dominates one that omits it;
  * a candidate that realises "either A or B" with union-compatible set
    semantics dominates an inner-join intersection;
  * a repair that DROPS the requested formula loses;
  * every alias / CAST / NULLIF / CTE / subquery formulation of the derived
    expression counts as satisfied;
  * a query with NO derived/either request receives NO obligation and NO score
    change (the neutrality guarantee).

Everything is schema-generic; concrete names live only in these fixtures.
"""
from sql_candidates.semantic_obligations import (
    question_derived_obligation, question_either_union_obligation,
    _projects_derived_expression, _projects_any_derived_expression,
    _final_output_projects, derived_output_satisfied,
    either_union_satisfied, either_required_sources, question_multi_source_either,
    _parse, _select_scopes, compute_profile)
from sql_candidates.rc5_ranking import rc5_obligations, rc5_dominates, RC5_ORDER
from sql_candidates.candidate_types import SqlCandidate
from sql_candidates.candidate_scorer import score_candidate
from sql_candidates.candidate_selector import select_best

IDX = {"tables": {
    "departments": [{"name": "department_id", "is_key": True},
                    {"name": "department_name"}, {"name": "faculty_count"},
                    {"name": "staff_count"}, {"name": "bed_capacity"},
                    {"name": "current_occupancy"}, {"name": "annual_budget"},
                    {"name": "student_count"}],
    "doctors": [{"name": "doctor_id", "is_key": True},
                {"name": "license_expiration_date"}, {"name": "active_flag"}],
    "patients": [{"name": "patient_id", "is_key": True}],
    "appointments": [{"name": "appointment_id", "is_key": True},
                     {"name": "patient_id"}],
    "billing_claims": [{"name": "claim_id", "is_key": True},
                       {"name": "appointment_id"}, {"name": "patient_id"}],
}}


def _ob(sql, question):
    o, ap = rc5_obligations(sql, None, None, IDX, question, {"_numeric_score": 0})
    return o, ap


def _selects(sql):
    return _select_scopes(_parse(sql))


# ---- detection precision (neutrality) ------------------------------------
def test_no_obligation_for_plain_total_or_average():
    assert question_derived_obligation("What is the total balance of all customers?") == set()
    assert question_derived_obligation("What is the average GPA across students?") == set()
    assert question_either_union_obligation("Count customers by status.") is False


def test_per_grouping_and_superlative_are_not_ratios():
    # "per" meaning "for each" / a superlative ranking must NOT be a ratio.
    assert question_derived_obligation("List the highest priced food per brand") == set()
    assert question_derived_obligation("Show the number of orders per customer") == set()


# ---- 1. addition: a + b vs two separate SUM columns ----------------------
def test_addition_projection_dominates_two_sums():
    q = "Show each department with the number of employees formed by adding its faculty count and staff count."
    good = "SELECT department_name, faculty_count + staff_count AS employees FROM departments"
    bad = ("SELECT department_name, SUM(faculty_count) AS a, SUM(staff_count) AS b "
           "FROM departments GROUP BY department_name")
    assert question_derived_obligation(q) == {"add"}
    og, ap = _ob(good, q)
    ob, _ = _ob(bad, q)
    assert og["derived_output_projected"] and not ob["derived_output_projected"]
    dom, why, _ = rc5_dominates(og, ob, ap)
    assert dom and "derived_output_projected" in why


# ---- 2. subtraction: a - b vs plain projection ---------------------------
def test_subtraction_projection_dominates_plain():
    q = "Show each department with the number of unused beds based on bed capacity minus current occupancy."
    good = "SELECT department_name, (bed_capacity - current_occupancy) AS unused_beds FROM departments"
    bad = "SELECT department_name, bed_capacity, current_occupancy FROM departments"
    assert question_derived_obligation(q) == {"subtract"}
    og, ap = _ob(good, q); ob, _ = _ob(bad, q)
    assert og["derived_output_projected"] and not ob["derived_output_projected"]
    assert rc5_dominates(og, ob, ap)[0]


# ---- 3. ratio: budget per student vs the two source columns --------------
def test_ratio_projection_dominates_two_columns():
    q = "Show each department with its annual budget per enrolled department student."
    good = ("SELECT department_name, CAST(annual_budget AS REAL) / NULLIF(student_count, 0) "
            "AS budget_per_student FROM departments")
    bad = "SELECT department_name, annual_budget, student_count FROM departments"
    assert question_derived_obligation(q) == {"ratio"}
    og, ap = _ob(good, q); ob, _ = _ob(bad, q)
    assert og["derived_output_projected"] and not ob["derived_output_projected"]
    assert rc5_dominates(og, ob, ap)[0]


# ---- 4. markup percentage vs AVG(price) ----------------------------------
def test_markup_percentage_projection_vs_avg_price():
    q = "Show each category with its average markup percentage."
    good = ("SELECT category, AVG((unit_price - unit_cost) / NULLIF(unit_cost, 0) * 100) "
            "AS markup_pct FROM items GROUP BY category")
    bad = "SELECT category, AVG(unit_price) AS avg_price FROM items GROUP BY category"
    assert "ratio" in question_derived_obligation(q)
    assert _projects_derived_expression(_parse(good), ("ratio",))
    assert not _projects_derived_expression(_parse(bad), ("ratio",))


# ---- 5. years remaining date calc vs plain date projection ---------------
def test_date_difference_projection_vs_plain_date():
    q = "Show each doctor with the number of years remaining until license expiration."
    good = ("SELECT doctor_id, CAST((julianday(license_expiration_date) - julianday('now')) "
            "/ 365.25 AS INTEGER) AS years_remaining FROM doctors")
    bad = "SELECT doctor_id, license_expiration_date FROM doctors"
    assert question_derived_obligation(q) == {"date"}
    og, ap = _ob(good, q); ob, _ = _ob(bad, q)
    assert og["derived_output_projected"] and not ob["derived_output_projected"]
    assert rc5_dominates(og, ob, ap)[0]


# ---- 6. UNION for "either" vs INNER JOIN intersection --------------------
def test_union_dominates_inner_join_for_either():
    q = "List patient identifiers that appear either in appointments or billing claims."
    good = ("SELECT patient_id FROM appointments UNION "
            "SELECT patient_id FROM billing_claims")
    bad = ("SELECT DISTINCT p.patient_id FROM appointments a "
           "JOIN billing_claims b ON a.appointment_id = b.appointment_id "
           "JOIN patients p ON a.patient_id = p.patient_id")
    assert question_either_union_obligation(q) is True
    og, ap = _ob(good, q); ob, _ = _ob(bad, q)
    assert og["set_union_either"] and not ob["set_union_either"]
    dom, why, _ = rc5_dominates(og, ob, ap)
    assert dom and "set_union_either" in why


def test_single_table_or_counts_as_union_compatible():
    # "either A or B" on ONE source (OR filter) is satisfied, never penalized.
    q = "List patients who either have a chronic condition or currently smoke."
    sql = "SELECT patient_id FROM patients WHERE chronic_flag = 1 OR smoking = 'current'"
    assert question_either_union_obligation(q) is True
    assert either_union_satisfied(_parse(sql)) is True


# ---- 7. no derived obligation -> no effect (neutrality guarantee) --------
def test_plain_query_gets_no_obligation_and_no_scorer_reason():
    # The chosen variant is RC5-only (no scorer numeric delta); a plain query
    # imposes no obligation and the scorer never attaches an obligation reason.
    q = "List departments by name."
    assert question_derived_obligation(q) == set()
    assert question_either_union_obligation(q) is False
    c = SqlCandidate(source="llm_primary", label="p",
                     sql="SELECT department_name FROM departments",
                     execution={"executed": True, "columns": ["department_name"],
                                "rows": [["x"]], "row_count": 1})
    score_candidate(q, c, {"tables": [
        {"table_name": "departments", "columns": [
            {"column_name": "department_id", "is_primary_key_candidate": True},
            {"column_name": "department_name"}]}], "relationships": []})
    assert not any(("derived" in r or "either" in r or "union" in r)
                   for r in c.reasons)


def test_rc5_obligations_neutral_when_no_obligation():
    # applies=False for both new obligations on a plain query, so they can never
    # change RC5 dominance (backward-compatible neutrality).
    _o, ap = _ob("SELECT department_name FROM departments", "List departments by name.")
    assert ap["derived_output_projected"] is False
    assert ap["set_union_either"] is False


# ---- 8. repair that removes the requested formula loses ------------------
def test_repair_dropping_formula_is_dominated():
    q = "Show each department with the number of unused beds based on bed capacity minus current occupancy."
    computing = ("SELECT department_name, (bed_capacity - current_occupancy) "
                 "AS unused_beds FROM departments")
    repair_dropped = "SELECT department_name, bed_capacity, current_occupancy FROM departments"
    og, ap = _ob(computing, q); orep, _ = _ob(repair_dropped, q)
    assert og["derived_output_projected"] and not orep["derived_output_projected"]
    # the computing candidate dominates the repair that dropped the formula
    assert rc5_dominates(og, orep, ap)[0]
    # ... and the repair does NOT dominate the computing one
    assert not rc5_dominates(orep, og, ap)[0]


# ---- 9. alias / CAST / NULLIF / CTE / subquery equivalences --------------
def test_derived_expression_detected_across_formulations():
    forms = [
        "SELECT a + b AS s FROM t",                                  # bare alias
        "SELECT CAST(a AS REAL) / NULLIF(b, 0) AS r FROM t",         # CAST + NULLIF
        "SELECT (a - b) * 1.0 AS d FROM t",                          # parens + mul
        "WITH x AS (SELECT a - b AS d FROM t) SELECT d FROM x",      # CTE computes it
        "SELECT s FROM (SELECT a / b AS s FROM t)",                  # subquery computes it
        "SELECT SUM(a - b) AS m FROM t GROUP BY c",                  # inside aggregate
    ]
    for sql in forms:
        assert _projects_any_derived_expression(_parse(sql)), sql
    # a plain aggregate of ONE column is NOT a derived expression
    assert not _projects_any_derived_expression(_parse("SELECT SUM(a) AS m FROM t"))


# ---- selector integration: the correct candidate is selected -------------
def _c(label, source, score, rows, sql):
    c = SqlCandidate(source=source, label=label, sql=sql,
                     execution={"executed": True, "columns": ["a"],
                                "rows": rows, "row_count": len(rows)})
    c.score = score
    c.validation = {"fatal": []}
    return c


def test_select_best_prefers_derived_projection_over_higher_scored_omitter():
    q = "Show each department with the number of unused beds based on bed capacity minus current occupancy."
    # the omitting candidate is scored HIGHER; obligation dominance must still win.
    omit = _c("llm_primary", "llm_primary", 90, [["a", 10, 3]],
              "SELECT department_name, bed_capacity, current_occupancy FROM departments")
    computing = _c("llm_sql_direct", "llm_sql_direct", 78, [["a", 7]],
                   "SELECT department_name, (bed_capacity - current_occupancy) "
                   "AS unused_beds FROM departments")
    sel, meta = select_best([omit, computing], idx=IDX, question=q)
    assert sel is computing


def test_select_best_prefers_union_over_inner_join_for_either():
    q = "List patient identifiers that appear either in appointments or billing claims."
    inter = _c("llm_primary", "llm_primary", 84, [[1], [2]],
               "SELECT DISTINCT p.patient_id FROM appointments a "
               "JOIN billing_claims b ON a.appointment_id = b.appointment_id "
               "JOIN patients p ON a.patient_id = p.patient_id")
    union = _c("llm_sql_direct", "llm_sql_direct", 59, [[1], [2], [3]],
               "SELECT patient_id FROM appointments UNION "
               "SELECT patient_id FROM billing_claims")
    sel, meta = select_best([inter, union], idx=IDX, question=q)
    assert sel is union


# ==========================================================================
# BLOCKER 1 — operator-specific arithmetic (negative tests)
# ==========================================================================
def _q_add():
    return "Show each department with employees formed by adding faculty count and staff count."


def _q_sub():
    return "Show each department with unused beds based on bed capacity minus current occupancy."


def _q_ratio():
    return "Show each department with its annual budget per enrolled department student."


def _q_mul():
    return "Show each order line with the extended amount computed as quantity multiplied by unit price."


def _q_date():
    return "Show each doctor with the number of years remaining until license expiration."


def test_neg_addition_not_satisfied_by_subtraction():
    assert question_derived_obligation(_q_add()) == {"add"}
    assert not _projects_derived_expression(_parse("SELECT a - b AS x FROM t"), ("add",))


def test_neg_addition_not_satisfied_by_division():
    assert not _projects_derived_expression(
        _parse("SELECT a / NULLIF(b,0) AS x FROM t"), ("add",))


def test_neg_subtraction_not_satisfied_by_addition():
    assert question_derived_obligation(_q_sub()) == {"subtract"}
    assert not _projects_derived_expression(_parse("SELECT a + b AS x FROM t"), ("subtract",))


def test_neg_ratio_not_satisfied_by_multiplication_alone():
    assert "ratio" in question_derived_obligation(_q_ratio())
    assert not _projects_derived_expression(_parse("SELECT a * b AS x FROM t"), ("ratio",))
    # a real ratio (with the multiply-by-100 of a percentage) still passes
    assert _projects_derived_expression(
        _parse("SELECT a * 100.0 / NULLIF(b,0) AS pct FROM t"), ("ratio",))


def test_neg_multiplication_not_satisfied_by_division():
    assert not _projects_derived_expression(_parse("SELECT a / b AS x FROM t"), ("multiply",))
    assert _projects_derived_expression(_parse("SELECT a * b AS x FROM t"), ("multiply",))


def test_neg_date_not_satisfied_by_plain_numeric_subtraction():
    assert question_derived_obligation(_q_date()) == {"date"}
    # ordinary numeric subtraction of two columns (no date function) is NOT a date calc
    assert not _projects_derived_expression(_parse("SELECT a - b AS x FROM t"), ("date",))
    assert _projects_derived_expression(
        _parse("SELECT (julianday(exp_date) - julianday('now')) / 365.25 AS y FROM t"),
        ("date",))


def test_neg_wrong_arithmetic_candidate_does_not_dominate_correct():
    q = _q_add()  # addition requested
    correct = "SELECT department_name, faculty_count + staff_count AS n FROM departments"
    wrong = "SELECT department_name, faculty_count - staff_count AS n FROM departments"
    oc, ap = _ob(correct, q)
    ow, _ = _ob(wrong, q)
    assert oc["derived_output_projected"] and not ow["derived_output_projected"]
    # the wrong-operator candidate must NOT dominate the correct one
    from sql_candidates.rc5_ranking import rc5_dominates
    assert not rc5_dominates(ow, oc, ap)[0]
    # and the correct one DOES dominate the wrong-operator candidate
    assert rc5_dominates(oc, ow, ap)[0]


def test_multi_operation_requires_all_operators():
    # "percentage based on a difference" needs BOTH division and subtraction
    kinds = ("ratio", "subtract")
    assert _projects_derived_expression(_parse("SELECT (a - b) / NULLIF(c,0) AS x FROM t"), kinds)
    assert not _projects_derived_expression(_parse("SELECT a / NULLIF(c,0) AS x FROM t"), kinds)
    assert not _projects_derived_expression(_parse("SELECT a - b AS x FROM t"), kinds)


# ==========================================================================
# BLOCKER 2 — two-source "either" coverage (negative tests)
# ==========================================================================
_Q_TWO_SOURCE = "List patient identifiers that appear either in appointments or billing claims."
_TABLES = list(IDX["tables"].keys())


def _req():
    r = either_required_sources(_Q_TWO_SOURCE, _TABLES)
    assert r == {"appointments", "billing_claims"}, r
    return r


def test_two_source_union_passes():
    assert either_union_satisfied(
        _parse("SELECT patient_id FROM appointments UNION SELECT patient_id FROM billing_claims"),
        _req()) is True


def test_two_source_inner_join_fails():
    assert either_union_satisfied(
        _parse("SELECT DISTINCT p.patient_id FROM appointments a "
               "JOIN billing_claims b ON a.appointment_id = b.appointment_id "
               "JOIN patients p ON a.patient_id = p.patient_id"), _req()) is False


def test_two_source_appointments_only_fails():
    assert either_union_satisfied(_parse("SELECT patient_id FROM appointments"), _req()) is False


def test_two_source_billing_claims_only_fails():
    assert either_union_satisfied(_parse("SELECT patient_id FROM billing_claims"), _req()) is False


def test_two_source_union_same_source_twice_fails():
    assert either_union_satisfied(
        _parse("SELECT patient_id FROM appointments UNION "
               "SELECT patient_id FROM appointments"), _req()) is False


def test_single_source_or_still_passes():
    q = "List patients who either have a chronic condition or currently smoke."
    req = either_required_sources(q, _TABLES)
    assert req == set()  # single-source: no two schema sources named
    assert either_union_satisfied(
        _parse("SELECT patient_id FROM patients WHERE chronic_flag = 1 OR smoking = 'current'"),
        req) is True


def test_single_source_ignoring_one_required_source_does_not_dominate():
    q = _Q_TWO_SOURCE
    covering = "SELECT patient_id FROM appointments UNION SELECT patient_id FROM billing_claims"
    one_only = "SELECT patient_id FROM appointments"
    oc, ap = _ob(covering, q)
    oo, _ = _ob(one_only, q)
    assert oc["set_union_either"] and not oo["set_union_either"]
    from sql_candidates.rc5_ranking import rc5_dominates
    assert not rc5_dominates(oo, oc, ap)[0]      # one-source cannot dominate
    assert rc5_dominates(oc, oo, ap)[0]          # union covering both dominates


# ==========================================================================
# BLOCKER 1 (v2) — FINAL-OUTPUT lineage
# ==========================================================================
def test_lineage_cte_projects_alias_passes():
    sql = ("WITH x AS (SELECT department_id, bed_capacity - current_occupancy AS ub "
           "FROM departments) SELECT department_id, ub FROM x")
    assert _final_output_projects(_parse(sql), "subtract") is True


def test_lineage_cte_drops_alias_fails():
    sql = ("WITH x AS (SELECT department_id, bed_capacity - current_occupancy AS ub "
           "FROM departments) SELECT department_id FROM x")
    assert _final_output_projects(_parse(sql), "subtract") is False


def test_lineage_subquery_projects_alias_passes():
    sql = ("SELECT department_name, ec FROM "
           "(SELECT department_name, faculty_count + staff_count AS ec FROM departments) x")
    assert _final_output_projects(_parse(sql), "add") is True


def test_lineage_subquery_drops_alias_fails():
    sql = ("SELECT department_name FROM "
           "(SELECT department_name, faculty_count + staff_count AS ec FROM departments) x")
    assert _final_output_projects(_parse(sql), "add") is False


def test_lineage_formula_only_in_having_fails():
    sql = ("SELECT category FROM items GROUP BY category "
           "HAVING AVG((unit_price - unit_cost) / NULLIF(unit_cost,0)) > 40")
    assert _final_output_projects(_parse(sql), "ratio") is False


def test_lineage_formula_only_in_order_by_fails():
    sql = "SELECT department_name FROM departments ORDER BY bed_capacity - current_occupancy"
    assert _final_output_projects(_parse(sql), "subtract") is False


def test_lineage_repair_rewrites_into_cte_but_drops_alias_fails():
    # a repair that moves the formula into a CTE but never projects its alias
    sql = ("WITH r AS (SELECT department_id, faculty_count + staff_count AS ec FROM departments) "
           "SELECT department_id FROM r")
    assert _final_output_projects(_parse(sql), "add") is False


# ==========================================================================
# BLOCKER 2 (v2) — requested operand grounding
# ==========================================================================
_QADD = "Show each department with employees formed by adding faculty count and staff count."
_QSUB = "Show each department with unused beds based on bed capacity minus current occupancy."
_QRATIO = "Show each department with its annual budget per enrolled department student."


def _sat(sql, q):
    return derived_output_satisfied(_parse(sql), q, IDX)[1]


def test_ground_addition_correct_operands_pass():
    assert _sat("SELECT faculty_count + staff_count AS e FROM departments", _QADD) is True


def test_ground_addition_wrong_operand_fails():
    assert _sat("SELECT faculty_count + department_id AS e FROM departments", _QADD) is False


def test_ground_subtraction_correct_order_passes():
    assert _sat("SELECT (bed_capacity - current_occupancy) AS u FROM departments", _QSUB) is True


def test_ground_subtraction_reversed_fails():
    assert _sat("SELECT (current_occupancy - bed_capacity) AS u FROM departments", _QSUB) is False


def test_ground_ratio_wrong_denominator_fails():
    assert _sat("SELECT annual_budget / faculty_count AS r FROM departments", _QRATIO) is False


def test_ground_ratio_through_nullif_cast_passes():
    assert _sat("SELECT CAST(annual_budget AS REAL) / NULLIF(student_count,0) AS r FROM departments",
                _QRATIO) is True


def test_ground_operands_through_cte_alias_pass():
    sql = ("WITH x AS (SELECT department_id, faculty_count + staff_count AS e FROM departments) "
           "SELECT department_id, e FROM x")
    assert _sat(sql, _QADD) is True


def test_ground_ambiguous_operands_are_neutral_not_dominant():
    # a derived question with no groundable operands -> obligation does not apply
    applies, _ = derived_output_satisfied(_parse("SELECT a / b AS x FROM t"),
                                          "Show each row with a computed value.", IDX)
    assert applies is False


# ==========================================================================
# BLOCKER 3 (v2) — branch-level multi-source union provenance
# ==========================================================================
_QU = "List patient identifiers that appear either in appointments or billing claims."


def _rq():
    return either_required_sources(_QU, list(IDX["tables"].keys()))


def test_branch_a_union_b_passes():
    assert either_union_satisfied(
        _parse("SELECT patient_id FROM appointments UNION SELECT patient_id FROM billing_claims"),
        _rq()) is True


def test_branch_a_union_a_with_unrelated_exists_b_fails():
    assert either_union_satisfied(
        _parse("SELECT patient_id FROM appointments UNION "
               "SELECT patient_id FROM appointments WHERE EXISTS(SELECT 1 FROM billing_claims)"),
        _rq()) is False


def test_branch_joins_b_only_as_filter_fails():
    assert either_union_satisfied(
        _parse("SELECT a.patient_id FROM appointments a "
               "JOIN billing_claims b ON a.appointment_id = b.appointment_id "
               "UNION SELECT patient_id FROM appointments"), _rq()) is False


def test_branch_entity_exists_or_exists_passes():
    assert either_union_satisfied(
        _parse("SELECT p.patient_id FROM patients p "
               "WHERE EXISTS(SELECT 1 FROM appointments a WHERE a.patient_id = p.patient_id) "
               "OR EXISTS(SELECT 1 FROM billing_claims b WHERE b.patient_id = p.patient_id)"),
        _rq()) is True


def test_branch_entity_in_or_in_passes():
    assert either_union_satisfied(
        _parse("SELECT p.patient_id FROM patients p "
               "WHERE p.patient_id IN (SELECT patient_id FROM appointments) "
               "OR p.patient_id IN (SELECT patient_id FROM billing_claims)"), _rq()) is True


def test_branch_entity_exists_and_exists_fails():
    assert either_union_satisfied(
        _parse("SELECT p.patient_id FROM patients p "
               "WHERE EXISTS(SELECT 1 FROM appointments a WHERE a.patient_id = p.patient_id) "
               "AND EXISTS(SELECT 1 FROM billing_claims b WHERE b.patient_id = p.patient_id)"),
        _rq()) is False


def test_branch_inner_join_fails():
    assert either_union_satisfied(
        _parse("SELECT DISTINCT p.patient_id FROM appointments a "
               "JOIN billing_claims b ON a.appointment_id = b.appointment_id "
               "JOIN patients p ON a.patient_id = p.patient_id"), _rq()) is False


def test_branch_only_a_fails():
    assert either_union_satisfied(_parse("SELECT patient_id FROM appointments"), _rq()) is False


def test_branch_only_b_fails():
    assert either_union_satisfied(_parse("SELECT patient_id FROM billing_claims"), _rq()) is False


def test_branch_inner_join_projecting_both_columns_still_fails():
    # an inner join that PROJECTS a column from each source is still an
    # intersection, not a union -> must fail.
    assert either_union_satisfied(
        _parse("SELECT DISTINCT a.patient_id, b.patient_id FROM appointments a "
               "JOIN billing_claims b ON a.appointment_id = b.appointment_id"),
        _rq()) is False


def test_branch_entity_joined_to_each_source_union_passes():
    # 'entity JOIN A' UNION 'entity JOIN B' is a valid union: the entity is the
    # common projected key and A / B are the distinguishing membership sources.
    assert either_union_satisfied(
        _parse("SELECT DISTINCT p.patient_id FROM patients p "
               "JOIN appointments a ON p.patient_id = a.patient_id "
               "UNION SELECT DISTINCT p.patient_id FROM patients p "
               "JOIN billing_claims b ON p.patient_id = b.patient_id"), _rq()) is True


# ==========================================================================
# BLOCKER 3 (v2) — per-branch / per-disjunct SEPARABILITY
# A and B together in ONE intersection unit must never satisfy 'either A or B'.
# ==========================================================================
def test_sep_union_a_join_b_then_unrelated_fails():
    assert either_union_satisfied(
        _parse("SELECT a.patient_id FROM appointments a "
               "JOIN billing_claims b ON a.appointment_id = b.appointment_id "
               "UNION SELECT patient_id FROM patients"), _rq()) is False


def test_sep_union_a_join_b_then_a_fails():
    assert either_union_satisfied(
        _parse("SELECT a.patient_id FROM appointments a "
               "JOIN billing_claims b ON a.appointment_id = b.appointment_id "
               "UNION SELECT patient_id FROM appointments"), _rq()) is False


def test_sep_union_a_join_b_twice_fails():
    assert either_union_satisfied(
        _parse("SELECT a.patient_id FROM appointments a "
               "JOIN billing_claims b ON a.appointment_id = b.appointment_id "
               "UNION SELECT a.patient_id FROM appointments a "
               "JOIN billing_claims b ON a.appointment_id = b.appointment_id"), _rq()) is False


def test_sep_union_a_with_b_only_in_join_filter_fails():
    assert either_union_satisfied(
        _parse("SELECT patient_id FROM appointments "
               "UNION SELECT a.patient_id FROM appointments a "
               "JOIN billing_claims b ON a.appointment_id = b.appointment_id"), _rq()) is False


def test_sep_or_intersection_disjunct_plus_false_fails():
    assert either_union_satisfied(
        _parse("SELECT p.patient_id FROM patients p WHERE "
               "(EXISTS(SELECT 1 FROM appointments a WHERE a.patient_id = p.patient_id) "
               "AND EXISTS(SELECT 1 FROM billing_claims b WHERE b.patient_id = p.patient_id)) "
               "OR 1 = 0"), _rq()) is False


def test_sep_or_a_alone_plus_a_and_b_fails():
    assert either_union_satisfied(
        _parse("SELECT p.patient_id FROM patients p WHERE "
               "(EXISTS(SELECT 1 FROM appointments a WHERE a.patient_id = p.patient_id) AND p.patient_id > 0) "
               "OR (EXISTS(SELECT 1 FROM appointments a WHERE a.patient_id = p.patient_id) "
               "AND EXISTS(SELECT 1 FROM billing_claims b WHERE b.patient_id = p.patient_id))"),
        _rq()) is False


def test_sep_or_exists_a_or_exists_b_passes():
    assert either_union_satisfied(
        _parse("SELECT p.patient_id FROM patients p WHERE "
               "EXISTS(SELECT 1 FROM appointments a WHERE a.patient_id = p.patient_id) "
               "OR EXISTS(SELECT 1 FROM billing_claims b WHERE b.patient_id = p.patient_id)"),
        _rq()) is True


# ---- ungrounded multi-source intent -> RC5 obligation is neutral ----------
def test_multi_source_intent_detected():
    assert question_multi_source_either(_QU) is True
    assert question_multi_source_either(
        "List patients who either have a chronic condition or currently smoke.") is False


def test_ungrounded_multi_source_is_non_applicable():
    # multi-source intent ('appear either in A or B') but only ONE source grounds
    # -> the RC5 union obligation must NOT apply (neutral), so a one-source
    # candidate cannot dominate via it.
    q = "List ids that appear either in appointments or widgets."  # 'widgets' not in schema
    _o, ap = _ob("SELECT patient_id FROM appointments", q)
    assert ap["set_union_either"] is False


def test_grounded_multi_source_still_applies():
    _o, ap = _ob("SELECT patient_id FROM appointments UNION SELECT patient_id FROM billing_claims", _QU)
    assert ap["set_union_either"] is True


# ---- preposition-before-either membership forms (both orders) --------------
def test_found_in_either_ungrounded_is_non_applicable():
    q = "List IDs found in either appointments or widgets."   # widgets absent
    _o, ap = _ob("SELECT patient_id FROM appointments", q)
    assert ap["set_union_either"] is False


def test_from_either_ungrounded_is_non_applicable():
    q = "List IDs from either appointments or widgets."       # widgets absent
    _o, ap = _ob("SELECT patient_id FROM appointments", q)
    assert ap["set_union_either"] is False


def test_within_either_ungrounded_is_non_applicable():
    q = "List IDs within either appointments or widgets."     # widgets absent
    _o, ap = _ob("SELECT patient_id FROM appointments", q)
    assert ap["set_union_either"] is False


def test_preposition_before_either_both_sources_present_applies():
    for q in ("List IDs found in either appointments or billing claims.",
              "List IDs from either appointments or billing claims.",
              "List IDs within either appointments or billing claims.",
              "List IDs recorded as either appointments or billing claims."):
        _o, ap = _ob("SELECT patient_id FROM appointments "
                     "UNION SELECT patient_id FROM billing_claims", q)
        assert ap["set_union_either"] is True, q


def test_preposition_before_either_intent_detected_and_predicate_neutral():
    assert question_multi_source_either("List IDs found in either appointments or widgets.") is True
    assert question_multi_source_either("List IDs from either appointments or widgets.") is True
    assert question_multi_source_either("List IDs within either appointments or widgets.") is True
    # single-table predicate alternatives are NOT multi-source membership
    assert question_multi_source_either(
        "List patients who either smoke or have a chronic condition.") is False
