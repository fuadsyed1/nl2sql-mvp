"""
test_ir_semantics.py

Unit tests for the Tier-1 question-aware IR rewrites. No database, no model.

Run:  python -m tests.test_ir_semantics
"""

from semantic.ir_semantics import apply_question_semantics


def _col(name, dtype, samples=None):
    return {"column_name": name, "data_type": dtype, "sample_values": samples or []}


GRAPH = {
    "tables": [
        {"table_name": "owners", "columns": [
            _col("owner_id", "INTEGER"), _col("owner_name", "TEXT")]},
        {"table_name": "purchases", "columns": [
            _col("purchase_id", "INTEGER"), _col("owner_id", "INTEGER"),
            _col("food_id", "INTEGER"), _col("quantity", "INTEGER"),
            _col("purchase_date", "TEXT", ["2025-01-02"])]},
        {"table_name": "foods", "columns": [
            _col("food_id", "INTEGER"), _col("brand", "TEXT")]},
        {"table_name": "books", "columns": [
            _col("book_id", "INTEGER"), _col("title", "TEXT")]},
        {"table_name": "loans", "columns": [
            _col("loan_id", "INTEGER"), _col("book_id", "INTEGER"),
            _col("loan_date", "TEXT", ["2024-05-01"]),
            _col("return_date", "TEXT", ["2025-06-01"])]},
        {"table_name": "users", "columns": [
            _col("user_id", "INTEGER"), _col("user_name", "TEXT")]},
        {"table_name": "watch_history", "columns": [
            _col("wh_id", "INTEGER"), _col("user_id", "INTEGER"),
            _col("minutes_watched", "INTEGER")]},
        {"table_name": "products", "columns": [
            _col("product_id", "INTEGER"), _col("product_name", "TEXT"),
            _col("unit_price", "REAL")]},
        {"table_name": "order_items", "columns": [
            _col("order_item_id", "INTEGER"), _col("order_id", "INTEGER"),
            _col("product_id", "INTEGER"), _col("quantity", "INTEGER"),
            _col("discount_percent", "REAL")]},
        {"table_name": "order_items_nodisc", "columns": [
            _col("oi2_id", "INTEGER"), _col("product_id", "INTEGER"),
            _col("quantity", "INTEGER")]},
        {"table_name": "orders", "columns": [
            _col("order_id", "INTEGER"), _col("customer_id", "INTEGER"),
            _col("restaurant_id", "INTEGER")]},
        {"table_name": "customers", "columns": [
            _col("customer_id", "INTEGER"), _col("loyalty_level", "TEXT"),
            _col("preferred_cuisine", "TEXT")]},
        {"table_name": "restaurants", "columns": [
            _col("restaurant_id", "INTEGER"), _col("cuisine", "TEXT")]},
        {"table_name": "games", "columns": [
            _col("game_id", "INTEGER"), _col("home_score", "INTEGER"),
            _col("away_score", "INTEGER")]},
    ],
    "relationships": [
        {"from_table": "purchases", "from_column": "owner_id",
         "to_table": "owners", "to_column": "owner_id"},
        {"from_table": "purchases", "from_column": "food_id",
         "to_table": "foods", "to_column": "food_id"},
        {"from_table": "loans", "from_column": "book_id",
         "to_table": "books", "to_column": "book_id"},
        {"from_table": "watch_history", "from_column": "user_id",
         "to_table": "users", "to_column": "user_id"},
        {"from_table": "order_items", "from_column": "product_id",
         "to_table": "products", "to_column": "product_id"},
        {"from_table": "order_items_nodisc", "from_column": "product_id",
         "to_table": "products", "to_column": "product_id"},
        {"from_table": "order_items", "from_column": "order_id",
         "to_table": "orders", "to_column": "order_id"},
        {"from_table": "orders", "from_column": "customer_id",
         "to_table": "customers", "to_column": "customer_id"},
        {"from_table": "orders", "from_column": "restaurant_id",
         "to_table": "restaurants", "to_column": "restaurant_id"},
    ],
}


def test_row_level_quantity():
    q = "List owners who bought more than 5 items in one purchase."
    ex = {
        "tables": ["owners", "purchases"],
        "select": [{"table": "owners", "column": "owner_id"}],
        "aggregations": [{"table": "purchases", "column": "quantity",
                          "function": "COUNT", "alias": "total_quantity"}],
        "group_by": [{"table": "owners", "column": "owner_id"}],
        "having": [{"aggregation_alias": "total_quantity", "op": ">", "value": 5}],
        "filters": [],
    }
    out = apply_question_semantics(q, ex, GRAPH)
    assert out["aggregations"] == [] and out["group_by"] == [] and out["having"] == []
    assert out["distinct"] is True
    qf = [f for f in out["filters"] if f["column"] == "quantity"]
    assert qf and qf[0]["op"] == ">" and qf[0]["value"] == 5, out["filters"]
    cols = {(s["table"], s["column"]) for s in out["select"]}
    assert ("owners", "owner_name") in cols, out["select"]
    print("[1] 'more than N in one purchase' -> row-level WHERE quantity > N + name -> OK")


def test_prefer_sum_quantity():
    q = "Which food brand was purchased the most?"
    ex = {
        "tables": ["foods", "purchases"],
        "select": [{"table": "foods", "column": "brand"}],
        "aggregations": [{"table": "purchases", "column": "purchase_id",
                          "function": "COUNT", "alias": "purchase_count"}],
        "group_by": [{"table": "foods", "column": "brand"}],
        "order_by": [{"aggregation_alias": "purchase_count", "direction": "DESC"}],
        "limit": 1,
    }
    out = apply_question_semantics(q, ex, GRAPH)
    a = out["aggregations"][0]
    assert a["function"] == "SUM" and a["table"] == "purchases" and a["column"] == "quantity", a
    assert a["alias"] == "purchase_count"  # alias preserved for ORDER BY
    print("[2] 'purchased the most' -> SUM(quantity), alias preserved -> OK")


def test_not_returned_before_year():
    q = "List books not returned before 2026."
    ex = {
        "tables": ["books", "loans"],
        "select": [{"table": "books", "column": "book_id"},
                   {"table": "books", "column": "title"}],
        "filters": [
            {"table": "loans", "column": "return_date", "op": "IS NULL"},
            {"table": "loans", "column": "loan_date", "op": ">=", "value": "2026"},
        ],
    }
    out = apply_question_semantics(q, ex, GRAPH)
    fs = out["filters"]
    assert not any(f["column"] == "loan_date" for f in fs), fs
    isnull = [f for f in fs if f["column"] == "return_date" and f["op"] == "IS NULL"]
    ge = [f for f in fs if f["column"] == "return_date" and f["op"] == ">="]
    assert isnull and isnull[0].get("connector") == "OR", fs
    assert ge and ge[0]["value"] == "2026-01-01", fs
    print("[5] 'not returned before YEAR' -> return_date IS NULL OR >= 'YEAR-01-01' -> OK")


def test_entity_completeness():
    q = "Find users with more than 100 minutes watched in one session."
    ex = {
        "tables": ["watch_history"],
        "select": [{"table": "watch_history", "column": "user_id"}],
        "filters": [{"table": "watch_history", "column": "minutes_watched",
                     "op": ">", "value": 100}],
        "distinct": True,
    }
    out = apply_question_semantics(q, ex, GRAPH)
    cols = {(s["table"], s["column"]) for s in out["select"]}
    assert ("users", "user_id") in cols and ("users", "user_name") in cols, out["select"]
    assert "users" in [t for t in out["tables"]], out["tables"]
    # the row-level filter must be left intact (minutes_watched is not 'quantity')
    assert any(f["column"] == "minutes_watched" for f in out["filters"]), out["filters"]
    print("[7] FK id select -> add parent id + name; row filter intact -> OK")


def test_revenue_with_discount():
    q = "Show total revenue by product."
    ex = {
        "tables": ["products", "order_items"],
        "select": [{"table": "products", "column": "product_name"}],
        "aggregations": [{"table": "order_items", "column": "quantity",
                          "function": "SUM", "alias": "total_revenue"}],
        "group_by": [{"table": "products", "column": "product_name"}],
    }
    a = apply_question_semantics(q, ex, GRAPH)["aggregations"][0]
    assert a["function"] == "SUM" and a["column"] is None, a
    e = a["expr"]
    assert e["op"] == "*" and e["left"]["op"] == "*"
    assert e["left"]["left"]["col"] == {"table": "order_items", "column": "quantity"}
    assert e["left"]["right"]["col"] == {"table": "products", "column": "unit_price"}
    d = e["right"]
    assert d["op"] == "-" and d["left"] == {"lit": 1}
    assert d["right"]["op"] == "/"
    assert d["right"]["left"]["col"] == {"table": "order_items", "column": "discount_percent"}
    assert d["right"]["right"] == {"lit": 100.0}
    print("[9] revenue WITH discount -> SUM(qty*price*(1-discount/100.0)) -> OK")


def test_revenue_without_discount():
    q = "Show total sales by product."
    ex = {
        "tables": ["products", "order_items_nodisc"],
        "select": [{"table": "products", "column": "product_name"}],
        "aggregations": [{"table": "order_items_nodisc", "column": "quantity",
                          "function": "SUM", "alias": "total_sales"}],
        "group_by": [{"table": "products", "column": "product_name"}],
    }
    a = apply_question_semantics(q, ex, GRAPH)["aggregations"][0]
    e = a["expr"]
    assert e["op"] == "*" and "op" not in e["left"], e
    assert e["left"]["col"] == {"table": "order_items_nodisc", "column": "quantity"}
    assert e["right"]["col"] == {"table": "products", "column": "unit_price"}
    print("[10] revenue WITHOUT discount -> SUM(qty*price) -> OK")


def test_field_to_field_opposite_prefix():
    # Non-empty placeholder value + 'won' wording must still fire.
    q = "List games where home team won."
    ex = {"tables": ["games"],
          "filters": [{"table": "games", "column": "home_score", "op": ">", "value": "?"}],
          "select": [{"table": "games", "column": "game_id"}]}
    f = apply_question_semantics(q, ex, GRAPH)["filters"][0]
    assert f["op"] == ">" and "value" not in f, f
    assert f["value_ref"] == {"table": "games", "column": "away_score"}, f
    print("[11] opposite prefix + 'won' -> home_score > away_score -> OK")


def test_field_to_field_descriptor_prefix():
    # Non-empty placeholder + 'their' wording; restaurants already in IR.
    q = "Find customers ordering their preferred cuisine."
    ex = {"tables": ["customers", "orders", "restaurants"],
          "filters": [{"table": "customers", "column": "preferred_cuisine",
                       "op": "=", "value": "preferred"}],
          "select": [{"table": "customers", "column": "customer_id"}]}
    f = apply_question_semantics(q, ex, GRAPH)["filters"][0]
    assert f["value_ref"] == {"table": "restaurants", "column": "cuisine"}, f
    assert "value" not in f, f
    print("[12] descriptor prefix + 'their' -> preferred_cuisine = restaurants.cuisine -> OK")


def test_field_to_field_adds_missing_table():
    # restaurants NOT in IR -> must be added (reachable via orders.restaurant_id).
    q = "Find customers ordering their preferred cuisine."
    ex = {"tables": ["customers", "orders"],
          "filters": [{"table": "customers", "column": "preferred_cuisine",
                       "op": "=", "value": None}],
          "select": [{"table": "customers", "column": "customer_id"}]}
    out = apply_question_semantics(q, ex, GRAPH)
    assert out["filters"][0]["value_ref"] == {"table": "restaurants", "column": "cuisine"}
    assert "restaurants" in out["tables"], out["tables"]
    print("[13] descriptor target table added to IR when missing -> OK")


def test_field_to_field_negative_literal_untouched():
    # A real literal with no comparison wording must stay parameterized.
    q = "Find customers who prefer Italian cuisine."
    ex = {"tables": ["customers"],
          "filters": [{"table": "customers", "column": "preferred_cuisine",
                       "op": "=", "value": "Italian"}],
          "select": [{"table": "customers", "column": "customer_id"}]}
    f = apply_question_semantics(q, ex, GRAPH)["filters"][0]
    assert "value_ref" not in f and f["value"] == "Italian", f
    print("[14] descriptor column with real literal + no 'their' -> stays parameterized -> OK")


def test_field_to_field_negative_no_victory_wording():
    q = "List games where home_score is above 5."   # no won/wins wording
    ex = {"tables": ["games"],
          "filters": [{"table": "games", "column": "home_score", "op": ">", "value": 5}],
          "select": [{"table": "games", "column": "game_id"}]}
    f = apply_question_semantics(q, ex, GRAPH)["filters"][0]
    assert "value_ref" not in f and f["value"] == 5, f
    print("[15] opposite column, real value, no victory wording -> stays parameterized -> OK")


def test_negative_plain_sum_quantity_untouched():
    q = "Show total quantity by product."           # no revenue/sales/spend wording
    ex = {"tables": ["products", "order_items"],
          "select": [{"table": "products", "column": "product_name"}],
          "aggregations": [{"table": "order_items", "column": "quantity",
                            "function": "SUM", "alias": "tq"}],
          "group_by": [{"table": "products", "column": "product_name"}]}
    a = apply_question_semantics(q, ex, GRAPH)["aggregations"][0]
    assert "expr" not in a and a["column"] == "quantity", a
    print("[16] plain SUM(quantity), non-revenue question -> untouched -> OK")


def test_negative_literal_filter_untouched():
    # No victory/comparison wording -> a real literal score filter stays parameterized.
    q = "List games with home score above 3."
    ex = {"tables": ["games"],
          "filters": [{"table": "games", "column": "home_score", "op": ">", "value": 3}],
          "select": [{"table": "games", "column": "game_id"}]}
    f = apply_question_semantics(q, ex, GRAPH)["filters"][0]
    assert "value_ref" not in f and f["value"] == 3, f
    print("[17] comparison filter, real literal, no victory wording -> parameterized -> OK")


def test_no_false_triggers():
    # A plain question must not be rewritten.
    q = "List all owners."
    ex = {"tables": ["owners"], "select": [{"table": "owners", "column": "owner_name"}],
          "filters": [], "aggregations": []}
    assert apply_question_semantics(q, ex, GRAPH) == ex
    print("[8] plain question -> no rewrite -> OK")


def main():
    tests = [
        test_row_level_quantity,
        test_prefer_sum_quantity,
        test_not_returned_before_year,
        test_entity_completeness,
        test_revenue_with_discount,
        test_revenue_without_discount,
        test_field_to_field_opposite_prefix,
        test_field_to_field_descriptor_prefix,
        test_field_to_field_adds_missing_table,
        test_field_to_field_negative_literal_untouched,
        test_field_to_field_negative_no_victory_wording,
        test_negative_plain_sum_quantity_untouched,
        test_negative_literal_filter_untouched,
        test_no_false_triggers,
    ]
    passed = 0
    for t in tests:
        t(); passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed -- ir_semantics.py verified")


if __name__ == "__main__":
    main()
