"""
test_relational_algebra.py

Deterministic relational-algebra rendering from a resolved plan. No DB, no model.
Run:  python -m tests.test_relational_algebra
"""

from generation.relational_algebra import to_relational_algebra


def plan(from_table, joins, ir, resolved=True):
    return {"resolved": resolved, "from_table": from_table, "joins": joins, "ir": ir}


def js(ft, fc, tt, tc, jt="inner"):
    return {"from_table": ft, "from_column": fc, "to_table": tt, "to_column": tc,
            "join_type": jt}


def test_simple_selection():
    ra = to_relational_algebra(plan("games", [], {
        "select": [{"table": "games", "column": "game_id"},
                   {"table": "games", "column": "home_score"},
                   {"table": "games", "column": "away_score"}],
        "filters": [{"table": "games", "column": "home_score", "op": ">",
                     "value_ref": {"table": "games", "column": "away_score"}}],
    }))
    assert ra == ("π game_id, home_score, away_score "
                  "(σ home_score > away_score (games))"), ra
    print("[1] selection (single table, value_ref) -> OK")


def test_inner_join():
    ra = to_relational_algebra(plan("owners", [js("owners", "owner_id", "purchases", "owner_id")], {
        "select": [{"table": "owners", "column": "owner_id"},
                   {"table": "owners", "column": "owner_name"}],
        "filters": [{"table": "purchases", "column": "quantity", "op": ">", "value": 5}],
    }))
    assert ra == ("π owners.owner_id, owners.owner_name "
                  "(σ purchases.quantity > 5 "
                  "(owners ⋈ owners.owner_id = purchases.owner_id purchases))"), ra
    print("[2] inner join ⋈ with condition + σ -> OK")


def test_left_join_group_aggregation():
    ra = to_relational_algebra(plan("owners", [js("owners", "owner_id", "pets", "owner_id", "left")], {
        "select": [{"table": "owners", "column": "owner_id"},
                   {"table": "owners", "column": "owner_name"}],
        "aggregations": [{"function": "COUNT", "table": "pets", "column": "pet_id",
                          "alias": "pet_count"}],
        "group_by": [{"table": "owners", "column": "owner_id"},
                     {"table": "owners", "column": "owner_name"}],
    }))
    assert ra == (
        "π owners.owner_id, owners.owner_name, COUNT(pets.pet_id)→pet_count "
        "(γ owners.owner_id, owners.owner_name; COUNT(pets.pet_id)→pet_count "
        "(owners ⟕ owners.owner_id = pets.owner_id pets))"
    ), ra
    print("[3] left join ⟕ + γ group/aggregation + outer π -> OK")


def test_group_always_has_outer_projection():
    ra = to_relational_algebra(plan("shows", [js("shows", "show_id", "watch_history", "show_id")], {
        "select": [{"table": "shows", "column": "genre"}],
        "aggregations": [{"function": "SUM", "table": "watch_history",
                          "column": "minutes_watched", "alias": "total_minutes"}],
        "group_by": [{"table": "shows", "column": "genre"}],
    }))
    assert ra.startswith("π shows.genre, SUM(watch_history.minutes_watched)→total_minutes (γ "), ra
    assert "γ shows.genre; SUM(watch_history.minutes_watched)→total_minutes" in ra, ra
    print("[4] outer π always emitted for GROUP BY queries -> OK")


def test_order_and_limit():
    ra = to_relational_algebra(plan("foods", [js("foods", "food_id", "purchases", "food_id")], {
        "select": [{"table": "foods", "column": "brand"}],
        "aggregations": [{"function": "SUM", "table": "purchases", "column": "quantity",
                          "alias": "total_quantity"}],
        "group_by": [{"table": "foods", "column": "brand"}],
        "order_by": [{"aggregation_alias": "total_quantity", "direction": "DESC"}],
        "limit": 1,
    }))
    assert ra.startswith("τ total_quantity DESC (π "), ra
    assert ra.endswith("LIMIT 1"), ra
    print("[5] τ order + LIMIT notation -> OK")


def test_expr_aggregation_alias():
    ra = to_relational_algebra(plan("products", [js("products", "product_id", "order_items", "product_id")], {
        "select": [{"table": "products", "column": "product_name"}],
        "aggregations": [{"function": "SUM",
                          "expr": {"op": "*",
                                   "left": {"col": {"table": "order_items", "column": "quantity"}},
                                   "right": {"col": {"table": "products", "column": "unit_price"}}},
                          "alias": "total_revenue"}],
        "group_by": [{"table": "products", "column": "product_name"}],
    }))
    assert "SUM(order_items.quantity * products.unit_price)→total_revenue" in ra, ra
    print("[6] projection with expression aggregation alias -> OK")


def test_unresolved_backoff():
    assert to_relational_algebra({"resolved": False}) == \
        "Relational algebra unavailable for this query."
    assert to_relational_algebra({"resolved": True, "from_table": "t", "joins": [],
                                  "ir": {"select": [], "aggregations": []}}) == \
        "Relational algebra unavailable for this query."
    print("[7] unresolved / empty -> backoff string -> OK")


def main():
    tests = [
        test_simple_selection,
        test_inner_join,
        test_left_join_group_aggregation,
        test_group_always_has_outer_projection,
        test_order_and_limit,
        test_expr_aggregation_alias,
        test_unresolved_backoff,
    ]
    passed = 0
    for t in tests:
        t(); passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed -- relational_algebra.py verified")


if __name__ == "__main__":
    main()
