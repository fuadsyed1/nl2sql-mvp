"""Stage 1C tests — checklist grain normalization, comparison application
(F7), CTE scope contamination through derived measures, and additive
derived-measure equivalence.

Generic shop schema (customers / orders / tickets / products); no benchmark
SQL, tables, or question hardcoded. Covers the 18 mandated Stage 1C cases.
"""

from semantic.semantic_checklist import _clean_checklist
from semantic.semantic_contract import build_semantic_contract
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


def _checklist(question, entry):
    return _clean_checklist({"grain_requirements": [entry]}, IDX, question)


def _contract(**overrides):
    entry = {
        "measure_column": "orders.amount",
        "aggregation": "sum",
        "entity_key": "customers.customer_id",
        "comparison_right_kind": "aggregate_of_entity_totals",
        "population_key": None,
        "measure_scope": None,
        "confidence": "high",
    }
    entry.update(overrides)
    return build_semantic_contract({"grain_requirements": [entry]}, IDX)


# 1. "entity has spent more than the average entity" => SUM per entity -------
def test_spent_wording_normalizes_avg_to_sum():
    cleaned = _checklist(
        "Find customers who have spent more than the average customer.",
        {"measure_column": "orders.amount", "aggregation": "avg",
         "entity_key": "customers.customer_id",
         "comparison_right_kind": "aggregate_of_entity_totals",
         "population_key": "customers.customer_id", "confidence": "high"})
    entry = cleaned["grain_requirements"][0]
    assert entry["aggregation"] == "sum"
    assert entry["population_key"] is None
    c = build_semantic_contract(cleaned, IDX)
    r = c.requirements[0]
    assert r.measure_aggregation == "sum" and r.population_column is None
    assert r.is_actionable


# 2. "average <entity>" with no "same" phrase => no population key -----------
def test_average_entity_without_same_drops_population():
    cleaned = _checklist(
        "Find customers whose order total is above the average customer.",
        {"measure_column": "orders.amount", "aggregation": "sum",
         "entity_key": "customers.customer_id",
         "comparison_right_kind": "aggregate_of_entity_totals",
         "population_key": "customers.region", "confidence": "high"})
    assert cleaned["grain_requirements"][0]["population_key"] is None


# 3. "average for the same category" preserves the population key ------------
def test_same_category_preserves_population():
    cleaned = _checklist(
        "Find products priced above the average price for the same category.",
        {"measure_column": "products.price", "aggregation": "avg",
         "entity_key": "products.category",
         "comparison_right_kind": "aggregate_of_rows",
         "population_key": "products.category", "confidence": "high"})
    assert cleaned["grain_requirements"][0]["population_key"] \
        == "products.category"


# 4. the entity key is not automatically copied into the population key ------
def test_entity_key_not_copied_to_population():
    cleaned = _checklist(
        "Find customers who ordered more than the average customer.",
        {"measure_column": "orders.amount", "aggregation": "sum",
         "entity_key": "customers.customer_id",
         "comparison_right_kind": "aggregate_of_entity_totals",
         "population_key": "customers.customer_id", "confidence": "high"})
    assert cleaned["grain_requirements"][0]["population_key"] is None
    # ... but an explicit "same region" phrase keeps a real group column
    cleaned = _checklist(
        "Find customers spending above the average for customers in the "
        "same region.",
        {"measure_column": "orders.amount", "aggregation": "sum",
         "entity_key": "customers.customer_id",
         "comparison_right_kind": "aggregate_of_entity_totals",
         "population_key": "customers.region", "confidence": "high"})
    assert cleaned["grain_requirements"][0]["population_key"] \
        == "customers.region"


# 5. a required aggregate appearing only in SELECT does not satisfy ----------
def test_output_only_grouped_aggregate_is_not_fatal():
    # RC1 (comparison-obligation gating): an output-only grouped metric (a total
    # per entity, projected in SELECT, with no comparison obligation) is
    # validated in the SELECT expression, NOT demanded in WHERE/HAVING. It must
    # not be fatal.
    sql = ("SELECT customer_id, SUM(amount) AS total FROM orders "
           "GROUP BY customer_id")
    v = validate_grain(_contract(), sql, IDX)
    assert not v.fatal, v


# 6. one requirement applied + one ignored => fatal for the ignored one ------
_TWO_REQ = {"grain_requirements": [
    {"measure_column": "products.price", "aggregation": "avg",
     "entity_key": "products.category",
     "comparison_right_kind": "aggregate_of_rows", "confidence": "high"},
    {"measure_column": "orders.amount", "aggregation": "sum",
     "entity_key": "customers.customer_id",
     "comparison_right_kind": "aggregate_of_entity_totals",
     "comparison_operator": ">", "comparison_constant": 1000,
     "confidence": "high"},
]}


def test_one_requirement_ignored_is_fatal():
    c = build_semantic_contract(_TWO_REQ, IDX)
    sql = (
        "SELECT p.product_id, (SELECT SUM(o.amount) FROM orders o) AS spent "
        "FROM products p WHERE p.price > "
        "(SELECT AVG(p2.price) FROM products p2 WHERE p2.category = p.category)")
    v = validate_grain(c, sql, IDX)
    assert any("requirement 2/2" in f and "never applied" in f
               for f in v.fatal), v
    assert not any("requirement 1/2" in f for f in v.fatal), v


# 7. raw row value vs same-group AVG passes ----------------------------------
def test_raw_vs_same_group_avg_passes():
    c = build_semantic_contract({"grain_requirements": [
        {"measure_column": "products.price", "aggregation": "avg",
         "entity_key": "products.category",
         "comparison_right_kind": "aggregate_of_rows",
         "confidence": "high"}]}, IDX)
    sql = ("SELECT p.product_id FROM products p WHERE p.price > "
           "(SELECT AVG(p2.price) FROM products p2 "
           " WHERE p2.category = p.category)")
    v = validate_grain(c, sql, IDX)
    assert v.fatal == [], v


# 8. entity SUM vs AVG(entity SUM) passes -------------------------------------
def test_entity_sum_vs_avg_of_sums_passes():
    sql = (
        "WITH ct AS (SELECT customer_id, SUM(amount) AS total FROM orders "
        "GROUP BY customer_id) "
        "SELECT c.name FROM customers c JOIN ct ON ct.customer_id = "
        "c.customer_id WHERE ct.total > (SELECT AVG(total) FROM ct)")
    v = validate_grain(_contract(), sql, IDX)
    assert v.fatal == [], v
    assert v.checks["requirement_1"]["comparison_applied"] is True


# 9. SUM and AVG of raw rows in the same entity group fails -------------------
def test_sum_vs_avg_raw_same_group_fails():
    sql = ("SELECT customer_id FROM orders GROUP BY customer_id "
           "HAVING SUM(amount) > AVG(amount)")
    v = validate_grain(_contract(), sql, IDX)
    assert any("raw rows" in f for f in v.fatal), v


# 10. CTE aggregate under an unrelated child filter fails (all_entity_rows) ---
_CONTAMINATED = (
    "WITH ct AS (SELECT o.customer_id, "
    "SUM(o.amount) - SUM(o.fee) AS total "
    "FROM orders o JOIN tickets t ON t.customer_id = o.customer_id "
    "WHERE t.severity = 'high' GROUP BY o.customer_id) "
    "SELECT ct.customer_id FROM ct "
    "WHERE ct.total > (SELECT AVG(total) FROM ct)")


def test_contaminated_cte_fails_for_all_entity_rows():
    v = validate_grain(_contract(measure_scope="all_entity_rows"),
                       _CONTAMINATED, IDX)
    assert any("restricted scope" in f and "tickets.severity" in f
               for f in v.fatal), v


# 11. the same contaminated CTE referenced through an alias still fails -------
def test_contaminated_cte_via_alias_still_fails():
    sql = (
        "WITH ct AS (SELECT o.customer_id, "
        "SUM(o.amount) - SUM(o.fee) AS total "
        "FROM orders o JOIN tickets t ON t.customer_id = o.customer_id "
        "WHERE t.severity = 'high' GROUP BY o.customer_id) "
        "SELECT x.customer_id FROM ct x "
        "WHERE x.total > (SELECT AVG(y.total) FROM ct y)")
    v = validate_grain(_contract(measure_scope="all_entity_rows"), sql, IDX)
    assert any("restricted scope" in f for f in v.fatal), v


# 12. qualifying CTE separated from the all-row measure CTE passes ------------
_SEPARATED = (
    "WITH flagged AS (SELECT customer_id FROM tickets "
    "WHERE severity = 'high' GROUP BY customer_id "
    "HAVING COUNT(DISTINCT topic) > 1), "
    "ct AS (SELECT customer_id, SUM(amount) - SUM(fee) AS total "
    "FROM orders GROUP BY customer_id) "
    "SELECT c.name FROM customers c "
    "JOIN ct ON ct.customer_id = c.customer_id "
    "JOIN flagged f ON f.customer_id = c.customer_id "
    "WHERE ct.total > (SELECT AVG(total) FROM ct)")


def test_separated_qualifier_and_measure_ctes_pass():
    v = validate_grain(_contract(measure_scope="all_entity_rows"),
                       _SEPARATED, IDX)
    assert v.fatal == [], v


# 13. SUM(x - y) is grain-equivalent to SUM(x) - SUM(y) ------------------------
def test_derived_measure_forms_are_equivalent():
    inline = (
        "WITH ct AS (SELECT customer_id, SUM(amount - fee) AS total "
        "FROM orders GROUP BY customer_id) "
        "SELECT ct.customer_id FROM ct "
        "WHERE ct.total > (SELECT AVG(total) FROM ct)")
    split = (
        "WITH ct AS (SELECT customer_id, SUM(amount) - SUM(fee) AS total "
        "FROM orders GROUP BY customer_id) "
        "SELECT ct.customer_id FROM ct "
        "WHERE ct.total > (SELECT AVG(total) FROM ct)")
    for sql in (inline, split):
        v = validate_grain(_contract(measure_scope="all_entity_rows"),
                           sql, IDX)
        assert v.fatal == [], (sql, v)
        assert v.checks["requirement_1"]["entity_total_uses"] >= 1, (sql, v)
        assert v.checks["requirement_1"]["comparison_applied"] is True


# 14. correct Q04-shaped outstanding-balance SQL passes ------------------------
def test_outstanding_balance_with_population_passes():
    sql = (
        "WITH ct AS (SELECT o.customer_id, c.region, "
        "SUM(o.amount - o.fee) AS balance FROM orders o "
        "JOIN customers c ON c.customer_id = o.customer_id "
        "GROUP BY o.customer_id, c.region) "
        "SELECT c.name FROM customers c JOIN ct ON ct.customer_id = "
        "c.customer_id WHERE ct.balance > (SELECT AVG(ct2.balance) FROM ct "
        "ct2 WHERE ct2.region = c.region)")
    v = validate_grain(
        _contract(population_key="customers.region",
                  measure_scope="all_entity_rows"), sql, IDX)
    assert v.fatal == [], v


# 15. correct Q48-shaped independent CTE decomposition passes ------------------
def test_independent_decomposition_two_requirements_pass():
    c = build_semantic_contract({"grain_requirements": [
        {"measure_column": "tickets.topic", "aggregation": "count",
         "entity_key": "customers.customer_id",
         "comparison_right_kind": "constant",
         "measure_scope": "filtered_entity_rows", "confidence": "high"},
        {"measure_column": "orders.amount", "aggregation": "sum",
         "entity_key": "customers.customer_id",
         "comparison_right_kind": "aggregate_of_entity_totals",
         "measure_scope": "all_entity_rows", "confidence": "high"},
    ]}, IDX)
    v = validate_grain(c, _SEPARATED, IDX)
    assert v.fatal == [], v


# 16. incomplete expression information stays nonfatal -------------------------
def test_unprovable_expression_is_nonfatal():
    sql = (
        "WITH ct AS (SELECT customer_id, "
        "SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END) AS total "
        "FROM orders GROUP BY customer_id) "
        "SELECT ct.customer_id FROM ct "
        "WHERE ct.total > (SELECT AVG(total) FROM ct)")
    v = validate_grain(_contract(measure_scope="all_entity_rows"), sql, IDX)
    assert v.fatal == [], v
    assert v.warnings, v            # uncertainty is reported, never fatal


# 17. simple aggregation without a comparison intent is not rejected -----------
def test_plain_aggregation_without_comparison_intent_passes():
    c = _contract(comparison_right_kind=None)
    sql = ("SELECT customer_id, SUM(amount) FROM orders GROUP BY customer_id")
    v = validate_grain(c, sql, IDX)
    assert v.fatal == [], v


# 18. Q02- and Q13-shaped correct patterns continue to pass --------------------
def test_q02_q13_shaped_patterns_still_pass():
    # Q02 shape: multi-child qualifier + two-level population comparison
    q02 = (
        "WITH ct AS (SELECT o.customer_id, c.region, SUM(o.amount) AS total "
        "FROM orders o JOIN customers c ON c.customer_id = o.customer_id "
        "GROUP BY o.customer_id, c.region), "
        "pa AS (SELECT region, AVG(total) AS avg_total FROM ct GROUP BY region) "
        "SELECT ct.customer_id FROM ct "
        "JOIN pa ON pa.region = ct.region "
        "WHERE ct.customer_id IN (SELECT customer_id FROM tickets "
        "GROUP BY customer_id HAVING COUNT(DISTINCT topic) > 1) "
        "AND ct.total > pa.avg_total")
    v = validate_grain(
        _contract(population_key="customers.region",
                  measure_scope="all_entity_rows"), q02, IDX)
    assert v.fatal == [], v

    # Q13 shape: latest-event qualifier separated from the lifetime total
    q13 = (
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
    v = validate_grain(
        _contract(population_key="customers.region",
                  measure_scope="all_entity_rows"), q13, IDX)
    assert v.fatal == [], v
