"""
tests/test_grain_comparison_obligation.py

RC1 — grain-contract comparison-obligation gating (generic; no DB/table/column
hardcoded in production logic). Comparison-application fatals fire ONLY when the
question actually compares the measure. Output-only metrics, scalar distinct
counts, conditional aggregates, and row-vs-peer comparisons are recognized.
"""
import validators.grain_validator as gv
from semantic.semantic_contract import GrainRequirement, SemanticContract
from query_families import slot_extractor as se


def _idx(tables):
    graph = {"tables": [
        {"table_name": t, "columns": [{"column_name": c, "data_type": "INTEGER"}
                                      for c in cols]}
        for t, cols in tables.items()]}
    return se.index_schema(graph)


def _contract(**kw):
    kw.setdefault("confidence", "high")
    return SemanticContract(requirements=(GrainRequirement(**kw),))


def test_output_only_grouped_metric_no_comparison_no_fatal():
    idx = _idx({"payments": ["payment_method", "refunded_amount", "amount"]})
    c = _contract(measure_table="payments", measure_column="refunded_amount",
                  measure_aggregation="sum", entity_table="payments",
                  entity_key_column="payment_method",
                  comparison_right_kind="aggregate_of_entity_totals")
    sql = ("SELECT payment_method, SUM(refunded_amount)*1.0/SUM(amount) AS r "
           "FROM payments GROUP BY payment_method HAVING SUM(amount) > 0")
    v = gv.validate_grain(c, sql, idx)
    assert not v.fatal, v.fatal


def test_output_only_ratio_two_aggregates_no_fatal():
    idx = _idx({"sales_order_items": ["product_id", "quantity_shipped",
                                      "quantity_ordered"]})
    c = _contract(measure_table="sales_order_items",
                  measure_column="quantity_shipped", measure_aggregation="sum",
                  entity_table="sales_order_items", entity_key_column="product_id",
                  comparison_right_kind="aggregate_of_rows")
    sql = ("SELECT product_id, SUM(quantity_shipped)*1.0/SUM(quantity_ordered) "
           "AS ratio FROM sales_order_items GROUP BY product_id")
    v = gv.validate_grain(c, sql, idx)
    assert not v.fatal, v.fatal


def test_scalar_distinct_count_output_no_fatal():
    idx = _idx({"products": ["supplier_id", "sale_price"],
                "suppliers": ["supplier_id"]})
    c = _contract(measure_table="suppliers", measure_column="supplier_id",
                  measure_aggregation="count", entity_table="suppliers",
                  entity_key_column="supplier_id", distinct=True,
                  comparison_right_kind="aggregate_of_rows")
    sql = ("SELECT COUNT(DISTINCT s.supplier_id) FROM products p "
           "JOIN suppliers s ON p.supplier_id = s.supplier_id "
           "WHERE p.sale_price > 500")
    v = gv.validate_grain(c, sql, idx)
    assert not v.fatal, v.fatal


def test_conditional_aggregate_no_fatal():
    idx = _idx({"customers": ["customer_id"],
                "payments": ["customer_id", "payment_status"]})
    c = _contract(measure_table="payments", measure_column="payment_status",
                  measure_aggregation="count", entity_table="customers",
                  entity_key_column="customer_id",
                  comparison_operator=">", comparison_constant=0.0,
                  comparison_right_kind="aggregate_of_rows")
    sql = ("SELECT c.customer_id FROM customers c "
           "JOIN payments p ON c.customer_id = p.customer_id "
           "GROUP BY c.customer_id "
           "HAVING SUM(CASE WHEN p.payment_status = 'refunded' THEN 1 ELSE 0 END) > 0")
    v = gv.validate_grain(c, sql, idx)
    assert not v.fatal, v.fatal


def test_row_vs_correlated_group_average_no_fatal():
    idx = _idx({"products": ["product_id", "category", "sale_price"]})
    c = _contract(measure_table="products", measure_column="sale_price",
                  measure_aggregation="avg", entity_table="products",
                  entity_key_column="category", comparison_operator=">",
                  comparison_right_kind="aggregate_of_entity_totals")
    sql = ("SELECT p.product_id, p.sale_price FROM products p "
           "WHERE p.sale_price > (SELECT AVG(p2.sale_price) FROM products p2 "
           "WHERE p2.category = p.category)")
    v = gv.validate_grain(c, sql, idx)
    assert not v.fatal, v.fatal


def test_group_vs_global_average_no_false_avg_over_avg_fatal():
    idx = _idx({"employees": ["salary", "department_id"],
                "departments": ["department_id", "department_name"]})
    c = _contract(measure_table="employees", measure_column="salary",
                  measure_aggregation="avg", entity_table="departments",
                  entity_key_column="department_id", comparison_operator=">",
                  comparison_right_kind="aggregate_of_entity_totals")
    sql = ("SELECT d.department_id FROM departments d "
           "JOIN employees e ON d.department_id = e.department_id "
           "GROUP BY d.department_id "
           "HAVING AVG(e.salary) > (SELECT AVG(salary) FROM employees)")
    v = gv.validate_grain(c, sql, idx)
    assert not v.fatal, v.fatal


def test_row_vs_raw_peer_comparison_no_fatal():
    # "balance greater than one of their orders" — both sides raw, no aggregate.
    idx = _idx({"customers": ["customer_id", "current_balance"],
                "sales_orders": ["customer_id", "grand_total"]})
    c = _contract(measure_table="sales_orders", measure_column="grand_total",
                  measure_aggregation="max", entity_table="customers",
                  entity_key_column="customer_id", comparison_operator=">",
                  comparison_right_kind="aggregate_of_entity_totals")
    sql = ("SELECT c.customer_id FROM customers c "
           "JOIN sales_orders so ON c.customer_id = so.customer_id "
           "WHERE c.current_balance > so.grand_total "
           "GROUP BY c.customer_id")
    v = gv.validate_grain(c, sql, idx)
    assert not v.fatal, v.fatal


def test_genuine_unmet_comparison_still_fatal():
    # Guard against over-permissiveness: a real comparison obligation whose
    # measure is never compared (only projected) must STILL be fatal.
    idx = _idx({"departments": ["department_id"],
                "employees": ["department_id", "performance_rating"]})
    c = _contract(measure_table="employees", measure_column="performance_rating",
                  measure_aggregation="avg", entity_table="departments",
                  entity_key_column="department_id", comparison_operator=">",
                  comparison_constant=5.0,
                  comparison_right_kind="aggregate_of_rows")
    # measure appears only in SELECT; no comparison predicate uses it
    sql = ("SELECT d.department_id, AVG(e.performance_rating) AS r "
           "FROM departments d JOIN employees e ON d.department_id = e.department_id "
           "GROUP BY d.department_id")
    v = gv.validate_grain(c, sql, idx)
    assert v.fatal, "a genuine unmet comparison obligation must stay fatal"


def test_nested_scalar_count_over_grouped_having_distinct_not_fatal():
    # RC1 (test-146 shape): an outer scalar COUNT(*) over a grouped subquery that
    # applies HAVING COUNT(DISTINCT related_key) >= N must NOT make the validator
    # demand another comparison predicate. Generic; no schema names in logic.
    idx = _idx({"parents": ["parent_id"], "children": ["parent_id", "related_key"]})
    c = _contract(measure_table="children", measure_column="related_key",
                  measure_aggregation="count", entity_table="parents",
                  entity_key_column="parent_id", distinct=True,
                  comparison_operator=">=", comparison_constant=3.0,
                  comparison_right_kind="constant")
    sql = ("SELECT COUNT(*) FROM (SELECT c.parent_id FROM children c "
           "GROUP BY c.parent_id HAVING COUNT(DISTINCT c.related_key) >= 3) t")
    v = gv.validate_grain(c, sql, idx)
    assert not v.fatal, v.fatal
