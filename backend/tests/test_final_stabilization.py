"""Final stabilization Parts C/D/E/F/G — distinct-count contracts, derived
measures, categorical literal groups, contract-driven repair prompts, and
pattern regressions. Generic shop schema; nothing benchmark-specific.
"""

from types import SimpleNamespace

from semantic.semantic_checklist import (
    _clean_checklist, literal_group_violations,
)
from semantic.semantic_contract import build_semantic_contract
from semantic.llm_sql_repair import _contract_block, _repair_instructions
from validators.grain_validator import validate_grain

IDX = {
    "tables": {
        "customers": [{"name": "customer_id"}, {"name": "name"},
                      {"name": "region"}],
        "orders": [{"name": "order_id"}, {"name": "customer_id"},
                   {"name": "amount"}, {"name": "fee"},
                   {"name": "order_date"}, {"name": "status"}],
        "tickets": [{"name": "ticket_id"}, {"name": "customer_id"},
                    {"name": "severity"}, {"name": "topic"}],
        "products": [{"name": "product_id"}, {"name": "category"},
                     {"name": "price"}],
    },
    "relationships": [],
}


def _distinct_contract(**overrides):
    entry = {
        "measure_column": "tickets.topic", "aggregation": "count",
        "entity_key": "customers.customer_id",
        "comparison_right_kind": "constant", "distinct": True,
        "comparison_operator": ">", "comparison_constant": 1,
        "measure_scope": "filtered_entity_rows", "confidence": "high",
    }
    entry.update(overrides)
    return build_semantic_contract({"grain_requirements": [entry]}, IDX)


# 8. COUNT(col) fails when COUNT(DISTINCT col) is required ---------------------
def test_count_without_distinct_fails():
    sql = ("SELECT customer_id FROM tickets GROUP BY customer_id "
           "HAVING COUNT(topic) > 1")
    v = validate_grain(_distinct_contract(), sql, IDX)
    assert any("DISTINCT" in f for f in v.fatal), v


# 9. COUNT(DISTINCT wrong_column) fails ----------------------------------------
def test_count_distinct_wrong_column_fails():
    sql = ("SELECT customer_id FROM tickets GROUP BY customer_id "
           "HAVING COUNT(DISTINCT ticket_id) > 1")
    v = validate_grain(_distinct_contract(), sql, IDX)
    assert any("COUNT(DISTINCT topic)" in f for f in v.fatal), v


# 10. COUNT(DISTINCT col) > 1 passes -------------------------------------------
def test_count_distinct_correct_passes():
    sql = ("SELECT customer_id FROM tickets GROUP BY customer_id "
           "HAVING COUNT(DISTINCT topic) > 1")
    v = validate_grain(_distinct_contract(), sql, IDX)
    assert v.fatal == [], v


# 11. a distinct-looking alias without DISTINCT fails ---------------------------
def test_distinct_alias_without_distinct_fails():
    sql = ("SELECT customer_id, COUNT(topic) AS distinct_topics "
           "FROM tickets GROUP BY customer_id HAVING distinct_topics > 1")
    v = validate_grain(_distinct_contract(), sql, IDX)
    assert any("proves nothing" in f or "DISTINCT" in f for f in v.fatal), v


# wrong constant/operator is caught ---------------------------------------------
def test_wrong_comparison_constant_fails():
    sql = ("SELECT customer_id FROM tickets GROUP BY customer_id "
           "HAVING COUNT(DISTINCT topic) > 3")
    v = validate_grain(_distinct_contract(), sql, IDX)
    assert any("not applied" in f for f in v.fatal), v


_DERIVED_ENTRY = {
    "measure_column": None,
    "measure_expression": {"operation": "subtract",
                           "components": ["orders.amount", "orders.fee"]},
    "aggregation": "sum", "entity_key": "customers.customer_id",
    "comparison_right_kind": "aggregate_of_entity_totals",
    "measure_scope": "all_entity_rows", "confidence": "high",
}


# 12. SUM(x-y) matches SUM(x)-SUM(y) under a derived contract -------------------
def test_derived_measure_forms_equivalent():
    c = build_semantic_contract({"grain_requirements": [dict(_DERIVED_ENTRY)]},
                                IDX)
    for total in ("SUM(amount - fee)", "SUM(amount) - SUM(fee)"):
        sql = (f"WITH ct AS (SELECT customer_id, {total} AS total "
               "FROM orders GROUP BY customer_id) "
               "SELECT ct.customer_id FROM ct "
               "WHERE ct.total > (SELECT AVG(total) FROM ct)")
        v = validate_grain(c, sql, IDX)
        assert v.fatal == [], (total, v)
        assert v.checks["requirement_1"]["comparison_applied"] is True


# 13. the derived-balance contract is actionable (Q04 stability) ----------------
def test_derived_contract_actionable():
    c = build_semantic_contract({"grain_requirements": [dict(_DERIVED_ENTRY)]},
                                IDX)
    r = c.requirements[0]
    assert r.is_actionable, r
    assert r.measure_table == "orders" and r.measure_column == "amount"
    assert len(r.measure_components) == 2
    assert r.measure_operation == "subtract"


# 14. missing/incomplete derived metadata stays nonfatal ------------------------
def test_missing_derived_metadata_nonfatal():
    entry = dict(_DERIVED_ENTRY,
                 measure_expression={"operation": "subtract",
                                     "components": ["orders.amount"]})
    c = build_semantic_contract({"grain_requirements": [entry]}, IDX)
    r = c.requirements[0]
    assert not r.is_actionable            # incomplete => low confidence
    v = validate_grain(c, "SELECT amount FROM orders", IDX)
    assert v.fatal == [] and v.skipped is not None


_LIT_CHECKLIST = {"required_literal_groups": [
    {"concept": "abnormal", "column": "tickets.severity",
     "literals": ["high", "low", "critical"], "confidence": "high"}]}


# 15. an unsupported semantic literal fails when a resolved group exists --------
def test_unsupported_literal_substitute_fails():
    sql = "SELECT ticket_id FROM tickets WHERE severity = 'abnormal'"
    v = literal_group_violations(_LIT_CHECKLIST, sql)
    assert v and "abnormal" in v[0], v
    # bound-parameter variant (the live Q48 shape: severity = ?)
    v = literal_group_violations(_LIT_CHECKLIST,
                                 "SELECT ticket_id FROM tickets "
                                 "WHERE severity = ?", params=["abnormal"])
    assert v, v


# 16. the correct resolved IN-list passes ---------------------------------------
def test_resolved_literal_set_passes():
    sql = ("SELECT ticket_id FROM tickets "
           "WHERE severity IN ('high', 'low', 'critical')")
    assert literal_group_violations(_LIT_CHECKLIST, sql) == []
    # a single resolved literal also counts as applied
    assert literal_group_violations(
        _LIT_CHECKLIST,
        "SELECT ticket_id FROM tickets WHERE severity = 'critical'") == []


# 17. low/medium resolution confidence is never fatal ---------------------------
def test_low_confidence_literal_group_nonfatal():
    cl = {"required_literal_groups": [
        {"concept": "abnormal", "column": "tickets.severity",
         "literals": ["high", "low"], "confidence": "medium"}]}
    sql = "SELECT ticket_id FROM tickets WHERE severity = 'abnormal'"
    assert literal_group_violations(cl, sql) == []


# checklist cleaning of literal groups ------------------------------------------
def test_clean_checklist_validates_literal_groups():
    cleaned = _clean_checklist({"required_literal_groups": [
        {"concept": "abnormal", "column": "tickets.severity",
         "literals": ["high", "low", "critical"], "confidence": "high"},
        {"concept": "ghost", "column": "tickets.no_such",
         "literals": ["x"], "confidence": "high"},
    ]}, IDX)
    groups = cleaned["required_literal_groups"]
    assert len(groups) == 1 and groups[0]["column"] == "tickets.severity"


# --- Part F: contract-driven repair prompt --------------------------------------
def _fatal_cand(*reasons):
    return SimpleNamespace(validation={"fatal": list(reasons)})


def _repair_contract():
    return build_semantic_contract({"grain_requirements": [
        {"measure_column": "orders.amount", "aggregation": "sum",
         "entity_key": "customers.customer_id",
         "comparison_right_kind": "aggregate_of_entity_totals",
         "measure_scope": "all_entity_rows", "confidence": "high"},
        {"measure_column": "tickets.topic", "aggregation": "count",
         "distinct": True, "comparison_operator": ">",
         "comparison_constant": 1,
         "entity_key": "customers.customer_id",
         "comparison_right_kind": "constant",
         "measure_scope": "filtered_entity_rows", "confidence": "high"},
    ]}, IDX)


# 18. filtered qualification vs all-row measure -> split-CTE instruction --------
def test_repair_instruction_split_ctes():
    text = _repair_instructions(
        None, [_fatal_cand("grain violation: ... computed from a restricted "
                           "scope: measure scope is filtered by an unrelated "
                           "qualifying condition on tickets.severity")],
        _repair_contract())
    assert "OWN CTE" in text and "SEPARATE" in text


# 19. latest-event qualifier vs lifetime aggregate are separated ----------------
def test_repair_instruction_latest_event_separation():
    text = _repair_instructions(
        None, [_fatal_cand("grain violation: ... MAX-equality pins rows to a "
                           "single extremum event")],
        _repair_contract())
    assert "latest" in text.lower()
    assert "Do NOT restrict a lifetime" in text


# 20. two-level entity-total comparison instruction -----------------------------
def test_repair_instruction_two_level():
    text = _repair_instructions(None, [], _repair_contract())
    assert "AVG of those per-entity totals" in text
    block = _contract_block(_repair_contract())
    assert "SUM(orders.amount)" in block
    assert "per customers.customer_id" in block


# 21. distinct-count repair instruction -----------------------------------------
def test_repair_instruction_distinct():
    text = _repair_instructions(None, [], _repair_contract())
    assert "COUNT(DISTINCT" in text
    block = _contract_block(_repair_contract())
    assert "COUNT(DISTINCT tickets.topic)" in block
    assert "> 1" in block


# --- pattern regressions (22-27) -------------------------------------------------
def _contract(**overrides):
    entry = {
        "measure_column": "orders.amount", "aggregation": "sum",
        "entity_key": "customers.customer_id",
        "comparison_right_kind": "aggregate_of_entity_totals",
        "population_key": None, "measure_scope": None, "confidence": "high",
    }
    entry.update(overrides)
    return build_semantic_contract({"grain_requirements": [entry]}, IDX)


# 22. Q02-shaped pattern still passes -------------------------------------------
def test_q02_pattern_passes():
    sql = (
        "WITH ct AS (SELECT o.customer_id, c.region, SUM(o.amount) AS total "
        "FROM orders o JOIN customers c ON c.customer_id = o.customer_id "
        "GROUP BY o.customer_id, c.region), "
        "pa AS (SELECT region, AVG(total) AS avg_total FROM ct GROUP BY region) "
        "SELECT ct.customer_id FROM ct JOIN pa ON pa.region = ct.region "
        "WHERE ct.customer_id IN (SELECT customer_id FROM tickets "
        "GROUP BY customer_id HAVING COUNT(DISTINCT topic) > 1) "
        "AND ct.total > pa.avg_total")
    v = validate_grain(_contract(population_key="customers.region",
                                 measure_scope="all_entity_rows"), sql, IDX)
    assert v.fatal == [], v


# 23. Q04-shaped derived-balance pattern passes ----------------------------------
def test_q04_pattern_passes():
    c = build_semantic_contract({"grain_requirements": [dict(
        _DERIVED_ENTRY, population_key="customers.region")]}, IDX)
    sql = (
        "WITH ct AS (SELECT o.customer_id, c.region, "
        "SUM(o.amount - o.fee) AS balance FROM orders o "
        "JOIN customers c ON c.customer_id = o.customer_id "
        "GROUP BY o.customer_id, c.region) "
        "SELECT c.name FROM customers c JOIN ct ON ct.customer_id = "
        "c.customer_id WHERE ct.balance > (SELECT AVG(ct2.balance) FROM ct "
        "ct2 WHERE ct2.region = c.region)")
    v = validate_grain(c, sql, IDX)
    assert v.fatal == [], v


# 24. Q13-shaped correct decomposition passes -------------------------------------
def test_q13_pattern_passes():
    sql = (
        "WITH ct AS (SELECT customer_id, SUM(amount) AS total FROM orders "
        "GROUP BY customer_id) "
        "SELECT c.name FROM customers c JOIN ct ON ct.customer_id = "
        "c.customer_id WHERE c.customer_id IN "
        "(SELECT o.customer_id FROM orders o WHERE o.status = 'delivered' "
        " AND o.order_date = (SELECT MAX(o2.order_date) FROM orders o2 "
        "  WHERE o2.customer_id = o.customer_id)) "
        "AND ct.total > (SELECT AVG(ct2.total) FROM ct ct2 "
        "JOIN customers c2 ON c2.customer_id = ct2.customer_id "
        "WHERE c2.region = c.region)")
    v = validate_grain(_contract(population_key="customers.region",
                                 measure_scope="all_entity_rows"), sql, IDX)
    assert v.fatal == [], v


# 25. Q40-shaped correct decomposition passes -------------------------------------
def test_q40_pattern_passes():
    c = build_semantic_contract({"grain_requirements": [
        {"measure_column": "products.price", "aggregation": "avg",
         "entity_key": "products.category",
         "comparison_right_kind": "aggregate_of_rows", "confidence": "high"},
        {"measure_column": "orders.amount", "aggregation": "sum",
         "entity_key": "customers.customer_id",
         "comparison_right_kind": "aggregate_of_entity_totals",
         "measure_scope": "all_entity_rows", "confidence": "high"},
    ]}, IDX)
    sql = (
        "WITH ct AS (SELECT customer_id, SUM(amount) AS total FROM orders "
        "GROUP BY customer_id) "
        "SELECT p.product_id FROM products p "
        "JOIN orders o ON o.order_id = o.order_id "
        "JOIN ct ON ct.customer_id = o.customer_id "
        "WHERE p.price > (SELECT AVG(p2.price) FROM products p2 "
        " WHERE p2.category = p.category) "
        "AND ct.total > (SELECT AVG(total) FROM ct)")
    v = validate_grain(c, sql, IDX)
    assert v.fatal == [], v


# 26. Q48-shaped correct decomposition passes -------------------------------------
def test_q48_pattern_passes():
    c = build_semantic_contract({"grain_requirements": [
        {"measure_column": "tickets.topic", "aggregation": "count",
         "distinct": True, "comparison_operator": ">",
         "comparison_constant": 1,
         "entity_key": "customers.customer_id",
         "comparison_right_kind": "constant",
         "measure_scope": "filtered_entity_rows", "confidence": "high"},
        dict(_DERIVED_ENTRY),
    ]}, IDX)
    sql = (
        "WITH flagged AS (SELECT customer_id FROM tickets "
        "WHERE severity IN ('high', 'low', 'critical') GROUP BY customer_id "
        "HAVING COUNT(DISTINCT topic) > 1), "
        "ct AS (SELECT customer_id, SUM(amount) - SUM(fee) AS total "
        "FROM orders GROUP BY customer_id) "
        "SELECT c.name FROM customers c "
        "JOIN ct ON ct.customer_id = c.customer_id "
        "JOIN flagged f ON f.customer_id = c.customer_id "
        "WHERE ct.total > (SELECT AVG(total) FROM ct)")
    v = validate_grain(c, sql, IDX)
    assert v.fatal == [], v


# 27. simple filters and aggregates do not regress --------------------------------
def test_simple_queries_not_rejected():
    from sql_candidates.semantic_sql_guards import sql_guard_violations
    simple = [
        "SELECT name FROM customers WHERE region = 'west'",
        "SELECT customer_id, SUM(amount) FROM orders GROUP BY customer_id",
        "SELECT COUNT(*) FROM orders WHERE status = 'paid'",
    ]
    for sql in simple:
        assert sql_guard_violations("list rows", sql) == [], sql
    v = validate_grain(_contract(comparison_right_kind=None),
                       simple[1], IDX)
    assert v.fatal == [], v
