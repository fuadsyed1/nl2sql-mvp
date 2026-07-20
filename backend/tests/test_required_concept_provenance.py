"""
tests/test_required_concept_provenance.py

RC2 — required-concept provenance + equivalence (generic; no DB/table/column
names in production logic). A model-INFERRED column that merely shares a generic
token with the question must not be treated as 'named in the question', and an
equivalent expression (COUNT for an entity-row/id count) satisfies the concept.
"""
from semantic.semantic_checklist import checklist_alignment

IDX = {"tables": {
    "customers": [{"name": "customer_id"}, {"name": "credit_limit"}],
    "sales_orders": [{"name": "order_id"}, {"name": "grand_total"},
                     {"name": "customer_id"}],
    "sales_order_items": [{"name": "line_total"}, {"name": "order_id"}],
    "shipments": [{"name": "shipment_id"}, {"name": "shipping_address_id"},
                  {"name": "shipment_status"}],
    "addresses": [{"name": "address_id"}, {"name": "state_code"}],
}}


def _fatal(question, must_use_columns, sql, literals=None):
    checklist = {"must_use_columns": must_use_columns, "literals": literals or []}
    _delta, _reasons, fatal, _checks = checklist_alignment(
        question, checklist, sql, IDX)
    return fatal


def test_inferred_measure_generic_token_not_fatal():
    # "delivered-order total" -> the model inferred sales_order_items.line_total,
    # but the correct answer is an order-grain SUM(grand_total). "line total" is
    # NOT in the question, so the inferred column must not be fatal.
    q = "list customers whose delivered-order total is greater than their credit limit"
    sql = ('SELECT c.customer_id, SUM(so.grand_total) AS delivered_order_total '
           'FROM customers c JOIN sales_orders so ON c.customer_id = so.customer_id '
           'GROUP BY c.customer_id HAVING SUM(so.grand_total) > c.credit_limit')
    assert _fatal(q, ["sales_order_items.line_total"], sql) == []


def test_inferred_id_satisfied_by_count_star_not_fatal():
    # "delivered shipment count" -> inferred shipments.shipment_id, answered with
    # COUNT(*). Not explicitly named AND COUNT equivalence applies.
    q = "show the top 5 destination states by delivered shipment count"
    sql = ('SELECT a.state_code, COUNT(*) AS delivered_count FROM shipments s '
           'JOIN addresses a ON s.shipping_address_id = a.address_id '
           "WHERE s.shipment_status = 'delivered' GROUP BY a.state_code "
           'ORDER BY delivered_count DESC LIMIT 5')
    assert _fatal(q, ["shipments.shipment_id"], sql) == []


def test_explicitly_named_column_missing_is_fatal():
    # The user literally names "line total" and the SQL omits it -> fatal.
    q = "show the line total for each order"
    sql = "SELECT order_id FROM sales_order_items GROUP BY order_id"
    fatal = _fatal(q, ["sales_order_items.line_total"], sql)
    assert any("line_total" in f for f in fatal), fatal


def test_count_equivalence_overrides_even_when_named():
    # Even when an id column is named, COUNT(...) satisfies an entity-row count.
    q = "count the shipment_id values"
    sql = "SELECT COUNT(*) FROM shipments"
    assert _fatal(q, ["shipments.shipment_id"], sql) == []
