"""
test_sql_clauses_expr.py

Renderer-capability tests for Tier 3: expression aggregations and column-reference
predicates. No database, no model. Run: python -m tests.test_sql_clauses_expr
"""

from generation.sql_clauses import _render_aggregation, _render_expr, render_where


def _mul(a, b):
    return {"op": "*", "left": a, "right": b}


def _col(t, c):
    return {"col": {"table": t, "column": c}}


def test_expr_aggregation_with_discount():
    # SUM(quantity * unit_price * (1 - discount_percent / 100.0))
    expr = _mul(
        _mul(_col("order_items", "quantity"), _col("products", "unit_price")),
        {"op": "-", "left": {"lit": 1},
         "right": {"op": "/", "left": _col("order_items", "discount_percent"),
                   "right": {"lit": 100.0}}},
    )
    sql = _render_aggregation({"function": "SUM", "expr": expr, "alias": "total_revenue"})
    assert sql == (
        'SUM("order_items"."quantity" * "products"."unit_price" * '
        '(1 - "order_items"."discount_percent" / 100.0)) AS "total_revenue"'
    ), sql
    print("[1] expr aggregation WITH discount -> OK")


def test_expr_aggregation_without_discount():
    expr = _mul(_col("order_items", "quantity"), _col("products", "unit_price"))
    sql = _render_aggregation({"function": "SUM", "expr": expr, "alias": "total_revenue"})
    assert sql == ('SUM("order_items"."quantity" * "products"."unit_price") '
                   'AS "total_revenue"'), sql
    print("[2] expr aggregation WITHOUT discount -> OK")


def test_value_ref_predicate_zero_params():
    where, params = render_where([
        {"table": "games", "column": "home_score", "op": ">",
         "value_ref": {"table": "games", "column": "away_score"}},
    ])
    assert where == 'WHERE "games"."home_score" > "games"."away_score"', where
    assert params == [], params
    print("[3] value_ref predicate (home_score > away_score), zero params -> OK")


def test_normal_filter_still_parameterized():
    where, params = render_where([
        {"table": "menu_items", "column": "category", "op": "=", "value": "dessert"},
    ])
    assert where == 'WHERE "menu_items"."category" = ?', where
    assert params == ["dessert"], params
    print("[4] normal literal filter stays parameterized -> OK")


def test_plain_aggregation_unchanged():
    assert _render_aggregation({"function": "COUNT", "column": None, "alias": "n"}) \
        == 'COUNT(*) AS "n"'
    assert _render_aggregation({"function": "SUM", "table": "purchases",
                                "column": "quantity", "alias": "tq"}) \
        == 'SUM("purchases"."quantity") AS "tq"'
    print("[5] plain aggregations (no expr) unchanged -> OK")


def test_expr_precedence():
    # a + b * c  -> no parens needed around b*c
    e = {"op": "+", "left": _col("t", "a"),
         "right": {"op": "*", "left": _col("t", "b"), "right": _col("t", "c")}}
    assert _render_expr(e) == '"t"."a" + "t"."b" * "t"."c"', _render_expr(e)
    # (a + b) * c  -> parens around a+b
    e2 = {"op": "*", "left": {"op": "+", "left": _col("t", "a"), "right": _col("t", "b")},
          "right": _col("t", "c")}
    assert _render_expr(e2) == '("t"."a" + "t"."b") * "t"."c"', _render_expr(e2)
    print("[6] expression precedence/parenthesization -> OK")


def main():
    tests = [
        test_expr_aggregation_with_discount,
        test_expr_aggregation_without_discount,
        test_value_ref_predicate_zero_params,
        test_normal_filter_still_parameterized,
        test_plain_aggregation_unchanged,
        test_expr_precedence,
    ]
    passed = 0
    for t in tests:
        t(); passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed -- sql_clauses expr/value_ref verified")


if __name__ == "__main__":
    main()
