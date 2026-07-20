"""Final stabilization Part B — Boolean-predicate validation.

Every WHERE / HAVING / JOIN ON / CASE WHEN condition must be an actual
Boolean predicate; a bare arithmetic expression (the Q48 run-2 bug:
`HAVING ... AND "total_billed" - "total_paid"`) is fatal.
"""

from sql_candidates.semantic_sql_guards import (
    boolean_predicate_violations, sql_guard_violations,
)

_MSG = "arithmetic expression is used as a Boolean predicate"


# 5. arithmetic-only HAVING is fatal ------------------------------------------
def test_arithmetic_only_having_is_fatal():
    sql = ("SELECT customer_id FROM orders GROUP BY customer_id "
           "HAVING SUM(amount) - SUM(fee)")
    v = boolean_predicate_violations(sql)
    assert any(_MSG in r for r in v), v
    # the exact Q48 run-2 shape: valid comparison AND bare arithmetic
    sql = ("SELECT customer_id FROM orders GROUP BY customer_id "
           "HAVING COUNT(order_id) > 1 AND SUM(amount) - SUM(fee)")
    v = boolean_predicate_violations(sql)
    assert any(_MSG in r for r in v), v
    # wired into the fatal guard aggregator
    assert any(_MSG in r for r in sql_guard_violations("q", sql))


# 6. arithmetic-only WHERE is fatal -------------------------------------------
def test_arithmetic_only_where_is_fatal():
    v = boolean_predicate_violations(
        "SELECT order_id FROM orders WHERE amount + fee")
    assert any(_MSG in r for r in v), v
    # bare aggregate as a condition
    v = boolean_predicate_violations(
        "SELECT customer_id FROM orders GROUP BY customer_id HAVING SUM(amount)")
    assert any(_MSG in r for r in v), v
    # bare non-flag column in an AND chain
    v = boolean_predicate_violations(
        "SELECT order_id FROM orders WHERE order_id > 5 AND amount")
    assert any(_MSG in r for r in v), v


# 7. a valid arithmetic COMPARISON passes --------------------------------------
def test_valid_arithmetic_comparison_passes():
    ok = [
        "SELECT customer_id FROM orders GROUP BY customer_id "
        "HAVING SUM(amount) - SUM(fee) > 100",
        "SELECT order_id FROM orders WHERE amount + fee >= 10",
        "SELECT order_id FROM orders WHERE status IN ('paid', 'open')",
        "SELECT order_id FROM orders WHERE amount BETWEEN 1 AND 5",
        "SELECT o.order_id FROM orders o JOIN customers c "
        "ON o.customer_id = c.customer_id WHERE NOT EXISTS "
        "(SELECT 1 FROM orders o2 WHERE o2.customer_id = c.customer_id "
        " AND o2.amount > o.amount)",
        # CASE WHEN with a proper condition
        "SELECT CASE WHEN amount > 5 THEN 1 ELSE 0 END FROM orders",
        # boolean-looking flag column is tolerated (never provably wrong)
        "SELECT order_id FROM orders WHERE is_active",
    ]
    for sql in ok:
        assert boolean_predicate_violations(sql) == [], sql


# unparseable SQL is never flagged ---------------------------------------------
def test_unparseable_sql_not_flagged():
    assert boolean_predicate_violations("SELEC nonsense FRM nowhere") == []
    assert boolean_predicate_violations("") == []
