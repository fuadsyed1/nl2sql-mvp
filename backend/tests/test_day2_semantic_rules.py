"""Day 2 generic semantic obligation + validator tests.

Synthetic schemas only (invented names: widgets, gadgets, ledger, roster...).
NO benchmark database (DB54-57) table or column names are used, and no test IDs
or expected benchmark SQL are referenced.
"""
from sql_candidates import day2_semantic_rules as d2


def _fired(sql, question):
    return {f["rule"] for f in d2.evaluate_rules(sql, question)}


# --- derived metric obligation -------------------------------------------
def test_difference_list_price_minus_sale_price():
    dm = d2.derived_metric_obligation("show the difference between list_amount and sale_amount")
    assert dm["calculate_expression"] and dm["operation"] == "difference"
    # returns operands only -> flagged; computes the difference -> not flagged
    assert "missing_requested_derived_expression" in _fired(
        "SELECT list_amount, sale_amount FROM widgets", "difference between list_amount and sale_amount")
    assert "missing_requested_derived_expression" not in _fired(
        "SELECT list_amount - sale_amount AS diff FROM widgets", "difference between list_amount and sale_amount")


def test_addition_faculty_plus_staff():
    dm = d2.derived_metric_obligation("headcount as faculty plus staff")
    assert dm["wants_sum"] and dm["operation"] == "add"
    assert "missing_requested_derived_expression" not in _fired(
        "SELECT faculty_ct + staff_ct AS headcount FROM roster", "faculty plus staff")


def test_percentage_of_a_constant():
    dm = d2.derived_metric_obligation("what percentage of the 500 seats are filled")
    assert dm["wants_percentage"] and dm["percentage_or_ratio"]
    assert "missing_requested_derived_expression" not in _fired(
        "SELECT CAST(filled AS REAL) * 100 / 500 AS pct FROM hall", "percentage of the 500 seats")


def test_ratio_of_two_aggregates():
    assert "missing_requested_derived_expression" in _fired(
        "SELECT SUM(a_amt), SUM(b_amt) FROM ledger", "ratio of total a_amt to total b_amt")
    assert "missing_requested_derived_expression" not in _fired(
        "SELECT CAST(SUM(a_amt) AS REAL)/NULLIF(SUM(b_amt),0) FROM ledger",
        "ratio of total a_amt to total b_amt")


# --- safe division --------------------------------------------------------
def test_zero_safe_division():
    assert "unsafe_integer_division" in _fired(
        "SELECT a_ct / b_ct FROM ledger", "a_ct divided by b_ct")
    assert "unsafe_integer_division" not in _fired(
        "SELECT CAST(a_ct AS REAL) / NULLIF(b_ct,0) FROM ledger", "a_ct divided by b_ct")


# --- output completeness (obligation extractor) --------------------------
def test_requested_output_completeness_obligation():
    ro = d2.requested_output_obligation("list each vendor with its name and total spend")
    assert ro["wants_name"] and ro["wants_each_entity"]


# --- explicit conditions --------------------------------------------------
def test_required_status_and_year_conditions_detected():
    ec = d2.explicit_condition_obligation("active gizmos launched in 2025 above 40 units")
    assert "2025" in ec["years"] and ec["thresholds"] and ec["has_explicit_condition"]


def test_unrequested_status_filter_not_invented():
    # a plain question has no explicit condition to preserve
    ec = d2.explicit_condition_obligation("how many gizmos are there")
    assert not ec["has_explicit_condition"]


# --- WHERE vs HAVING ------------------------------------------------------
def test_aggregate_predicate_in_where_flagged_warning():
    # detected but NOT fatal (demoted: it flagged 0 protected AND 0 incorrect in
    # the static replay, so it is kept warning rather than a non-discriminating fatal)
    fired = d2.evaluate_rules("SELECT region FROM depots WHERE SUM(units) > 5 GROUP BY region",
                              "regions with more than 5 units")
    rule = next(f for f in fired if f["rule"] == "aggregate_predicate_in_where")
    assert rule["severity"] == "warning"
    assert d2.RULE_SEVERITY["aggregate_predicate_in_where"] == "warning"


def test_both_as_union_is_only_fatal_rule():
    assert [r for r in d2.RULES if d2.RULE_SEVERITY[r] == "fatal"] == ["both_as_union"]
    assert d2.day2_fatal_reasons("SELECT id FROM r1 UNION SELECT id FROM r2",
                                 "vendors in both zone_a and zone_b")


def test_row_level_predicate_in_having_flagged_warning():
    fired = _fired("SELECT region, AVG(v) FROM depots GROUP BY region HAVING cap_units > 0",
                   "average v per region where cap_units positive")
    assert "row_level_predicate_in_having" in fired
    assert d2.RULE_SEVERITY["row_level_predicate_in_having"] == "warning"


# --- set / existential logic ---------------------------------------------
def test_either_vs_both():
    si_either = d2.set_intent_obligation("vendors in either zone_a or zone_b")
    si_both = d2.set_intent_obligation("vendors in both zone_a and zone_b")
    assert si_either["either"] and not si_either["both"]
    assert si_both["both"]
    # both -> UNION is a fatal contradiction
    assert d2.day2_fatal_reasons("SELECT id FROM r1 UNION SELECT id FROM r2",
                                 "vendors in both zone_a and zone_b")
    # either -> INTERSECT is a warning
    assert "either_or_as_intersection" in _fired(
        "SELECT id FROM r1 INTERSECT SELECT id FROM r2", "vendors in either zone_a or zone_b")


def test_a_but_not_b():
    si = d2.set_intent_obligation("vendors in zone_a but not in zone_b")
    assert si["but_not"] and si["negative_existence"]


def test_never_no_child_rows_negative_existence():
    si = d2.set_intent_obligation("vendors that never shipped an order")
    assert si["negative_existence"]
    assert "negative_existence_inner_join" in _fired(
        "SELECT v.id FROM vendors v JOIN shipments s ON s.vid = v.id",
        "vendors that never shipped an order")
    assert "negative_existence_inner_join" not in _fired(
        "SELECT v.id FROM vendors v WHERE NOT EXISTS (SELECT 1 FROM shipments s WHERE s.vid=v.id)",
        "vendors that never shipped an order")


def test_two_independent_exists_intent():
    si = d2.set_intent_obligation("vendors that have a paid order and have a pending order")
    assert si["independent_existential"]


# --- repair revalidation --------------------------------------------------
def test_repair_output_revalidated_by_fatal_rules():
    # a "repaired" SQL that still contradicts a 'both' request with UNION is
    # caught again by the fatal revalidation path
    bad_repair = "SELECT id FROM r1 UNION SELECT id FROM r2"
    assert d2.day2_fatal_reasons(bad_repair, "vendors in both zone_a and zone_b")


# --- no database-specific hardcoding -------------------------------------
def test_rules_are_schema_independent_under_renaming():
    # identical structure, different identifiers -> identical rule firings
    q = "ratio of total x to total y"
    a = _fired("SELECT SUM(alpha), SUM(beta) FROM foo", q)
    b = _fired("SELECT SUM(mu), SUM(nu) FROM bar", q)
    assert a == b


def test_no_benchmark_table_names_in_module():
    src = open(d2.__file__, encoding="utf-8").read().lower()
    for name in ("customers", "students", "doctors", "players", "warehouses",
                 "suppliers", "leagues", "enrollments", "sales_orders"):
        assert name not in src


def test_derived_operand_only_penalty_gating():
    # fires only when derived requested AND a sibling computes the expression
    q = "difference between list_amount and sale_amount"
    sqls = ["SELECT list_amount, sale_amount FROM widgets",      # operands only
            "SELECT list_amount - sale_amount AS d FROM widgets"]  # computes it
    pens = d2.derived_operand_only_penalties(q, sqls)
    assert pens[0] > 0 and pens[1] == 0.0
    # no sibling computes it -> no penalty (no pool evidence)
    only_operands = ["SELECT list_amount, sale_amount FROM widgets",
                     "SELECT list_amount FROM widgets"]
    assert d2.derived_operand_only_penalties(q, only_operands) == [0.0, 0.0]
    # no derived request -> never penalize
    assert d2.derived_operand_only_penalties("list widgets", sqls) == [0.0, 0.0]


def test_parse_strips_normalized_sql_echo():
    # trace-noise robustness: a trailing normalized_sql echo must not break parsing
    sql = "SELECT (a - b) AS d FROM t\nnormalized_sql:\nSELECT (a - b) AS d FROM t"
    assert d2._parse(sql) is not None
