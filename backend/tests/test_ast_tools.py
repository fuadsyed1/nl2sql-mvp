"""Stage 0 tests — sql_analysis/ast_tools.py (sqlglot AST utility layer).

Generic toy schemas only; no benchmark questions or SQL are hardcoded.
"""

from sqlglot import exp

from sql_analysis.ast_tools import (
    parse_sql, scope_nodes, scope_aggregates, aggregate_name,
    aggregate_arg_column, group_by_columns, comparison_predicates,
    columns_outside_aggregates, scope_has_limit_one, trace_column,
    trace_expression, side_origin,
)

IDX = {
    "tables": {
        "patients": [{"name": "patient_id"}, {"name": "name"},
                     {"name": "insurance_provider"}],
        "invoices": [{"name": "invoice_id"}, {"name": "patient_id"},
                     {"name": "amount"}, {"name": "balance"}],
        "stores": [{"name": "store_id"}, {"name": "region"}],
        "sales": [{"name": "sale_id"}, {"name": "store_id"},
                  {"name": "revenue"}],
    },
    "relationships": [],
}


# 1. sqlglot parses normal SQLite SELECT queries -----------------------------
def test_parses_normal_sqlite_selects():
    for sql in (
        "SELECT name FROM patients WHERE patient_id = 3",
        "SELECT p.name, COUNT(*) FROM patients p JOIN invoices i "
        "ON i.patient_id = p.patient_id GROUP BY p.patient_id HAVING COUNT(*) > 2",
        "WITH t AS (SELECT store_id, SUM(revenue) AS r FROM sales GROUP BY store_id) "
        "SELECT * FROM t ORDER BY r DESC LIMIT 5",
    ):
        parsed = parse_sql(sql)
        assert parsed.ok, parsed.error
        assert parsed.tree is not None
        assert parsed.scopes


# 2. aliases resolve correctly ------------------------------------------------
def test_alias_resolution_to_physical_table():
    parsed = parse_sql(
        "SELECT p.name, i.amount FROM patients AS p "
        "JOIN invoices i ON i.patient_id = p.patient_id")
    scope = parsed.root_scope
    cols = {c.sql(): c for c in scope.expression.selects if isinstance(c, exp.Column)}
    o1 = trace_column(scope, cols["p.name"], IDX)
    o2 = trace_column(scope, cols["i.amount"], IDX)
    assert o1.is_physical("patients", "name")
    assert o2.is_physical("invoices", "amount")


# 3. aggregate expressions are extracted --------------------------------------
def test_aggregates_extracted_with_args():
    parsed = parse_sql(
        "SELECT patient_id, SUM(amount) AS total, COUNT(*) AS n "
        "FROM invoices GROUP BY patient_id")
    aggs = scope_aggregates(parsed.root_scope)
    names = sorted(filter(None, (aggregate_name(a) for a in aggs)))
    assert names == ["count", "sum"]
    s = next(a for a in aggs if aggregate_name(a) == "sum")
    c = next(a for a in aggs if aggregate_name(a) == "count")
    assert aggregate_arg_column(s).name == "amount"
    assert aggregate_arg_column(c) is None          # COUNT(*) — uncertain


# 4. nested subqueries are separated by scope ---------------------------------
def test_subquery_scopes_are_separate():
    parsed = parse_sql(
        "SELECT s.region FROM stores s WHERE s.store_id IN "
        "(SELECT store_id FROM sales WHERE revenue > "
        " (SELECT AVG(revenue) FROM sales))")
    assert len(parsed.scopes) == 3
    # the AVG belongs ONLY to the innermost scope
    per_scope = [sorted(filter(None, (aggregate_name(a)
                                      for a in scope_aggregates(s))))
                 for s in parsed.scopes]
    assert per_scope.count(["avg"]) == 1
    assert per_scope.count([]) == 2


# 5. GROUP BY expressions are extracted ---------------------------------------
def test_group_by_columns_extracted():
    parsed = parse_sql(
        "SELECT store_id, SUM(revenue) FROM sales GROUP BY store_id")
    gcols = group_by_columns(parsed.root_scope)
    assert [g.name for g in gcols] == ["store_id"]

    parsed2 = parse_sql("SELECT region FROM stores")
    assert group_by_columns(parsed2.root_scope) == []

    parsed3 = parse_sql(
        "SELECT store_id, SUM(revenue) FROM sales GROUP BY 1")
    assert group_by_columns(parsed3.root_scope) is None   # ordinal — uncertain


# 6. parse failure is controlled ----------------------------------------------
def test_parse_failure_is_controlled():
    for bad in ("SELEC amount FRM invoices", "", None, "GROUP BY WHERE"):
        parsed = parse_sql(bad)
        assert parsed.ok is False
        assert parsed.error


# comparisons / outside-aggregate columns / limit-1 helpers -------------------
def test_comparison_predicates_and_outside_columns():
    parsed = parse_sql(
        "SELECT patient_id, balance FROM invoices "
        "GROUP BY patient_id HAVING SUM(amount) > 100")
    scope = parsed.root_scope
    comps = comparison_predicates(scope)
    assert len(comps) == 1 and isinstance(comps[0], exp.GT)
    outside = {c.name for c in columns_outside_aggregates(scope)}
    assert "balance" in outside          # bare column in a grouped query
    assert "amount" not in outside       # inside SUM
    assert "patient_id" not in outside   # group-by key


def test_limit_one_detection_and_trace():
    parsed = parse_sql(
        "SELECT (SELECT amount FROM invoices i WHERE i.patient_id = p.patient_id "
        "ORDER BY invoice_id DESC LIMIT 1) AS last_amount FROM patients p")
    inner = next(s for s in parsed.scopes if scope_has_limit_one(s))
    assert inner is not None
    sub = next(n for n in scope_nodes(parsed.root_scope)
               if isinstance(n, exp.Subquery))
    origin = side_origin(parsed, parsed.root_scope, sub, IDX)
    assert origin.is_physical("invoices", "amount")
    assert origin.limited_to_one_row is True


def test_trace_through_cte_to_aggregate():
    parsed = parse_sql(
        "WITH t AS (SELECT patient_id, SUM(amount) AS total FROM invoices "
        "GROUP BY patient_id) SELECT total FROM t WHERE total > 10")
    scope = parsed.root_scope
    col = next(c for c in scope.expression.selects if isinstance(c, exp.Column))
    origin = trace_column(scope, col, IDX)
    assert origin.kind == "aggregate"
    assert origin.aggregate == "sum"
    assert origin.inner.is_physical("invoices", "amount")
    assert [g.column for g in origin.group_keys] == ["patient_id"]


def test_unqualified_ambiguous_column_is_unknown():
    parsed = parse_sql(
        "SELECT patient_id FROM patients p JOIN invoices i "
        "ON i.patient_id = p.patient_id")
    scope = parsed.root_scope
    col = scope.expression.selects[0]
    origin = trace_expression(scope, col, IDX)
    assert origin.kind == "unknown"      # both tables own patient_id
