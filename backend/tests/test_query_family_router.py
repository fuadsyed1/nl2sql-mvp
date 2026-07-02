"""
test_query_family_router.py

Router decision tests for the relational query-family layer. Pure logic (schema
graph in, family out) — no SQL generation, no model. Schema mirrors the report
as TEST DATA only; the router keys off schema metadata + generic intent words.

Run:  python -m tests.test_query_family_router
"""

from query_families.query_family_router import route
from query_families import family_types as ft


def _col(name, dtype="TEXT", pk=False):
    return {"column_name": name, "data_type": dtype, "is_primary_key_candidate": pk}


GRAPH = {
    "tables": [
        {"table_name": "owners", "columns": [
            _col("owner_id", "INTEGER", True), _col("owner_name"), _col("city"),
            _col("state"), _col("street_address"), _col("annual_income", "INTEGER"),
            _col("age", "INTEGER")]},
        {"table_name": "pets", "columns": [
            _col("pet_id", "INTEGER", True), _col("pet_name"), _col("species"),
            _col("owner_id", "INTEGER"), _col("pet_address"), _col("adoption_date", "DATE")]},
        {"table_name": "foods", "columns": [
            _col("food_id", "INTEGER", True), _col("brand"), _col("food_name"),
            _col("food_type"), _col("species_target"), _col("flavor"),
            _col("price", "REAL"), _col("stock_quantity", "INTEGER")]},
        {"table_name": "purchases", "columns": [
            _col("purchase_id", "INTEGER", True), _col("owner_id", "INTEGER"),
            _col("food_id", "INTEGER"), _col("purchase_date", "DATE"),
            _col("quantity", "INTEGER"), _col("unit_price", "REAL"),
            _col("total_amount", "REAL"), _col("store_city")]},
        {"table_name": "pet_likes", "columns": [
            _col("like_id", "INTEGER", True), _col("pet_id", "INTEGER"),
            _col("food_type"), _col("flavor"), _col("preferred_brand"), _col("active")]},
        {"table_name": "feeding_history", "columns": [
            _col("feed_id", "INTEGER", True), _col("pet_id", "INTEGER"),
            _col("food_id", "INTEGER"), _col("owner_id", "INTEGER"),
            _col("feed_date", "DATE"), _col("servings", "INTEGER")]},
    ],
    "relationships": [
        {"from_table": "pets", "from_column": "owner_id", "to_table": "owners", "to_column": "owner_id"},
        {"from_table": "purchases", "from_column": "owner_id", "to_table": "owners", "to_column": "owner_id"},
        {"from_table": "purchases", "from_column": "food_id", "to_table": "foods", "to_column": "food_id"},
        {"from_table": "pet_likes", "from_column": "pet_id", "to_table": "pets", "to_column": "pet_id"},
        {"from_table": "feeding_history", "from_column": "pet_id", "to_table": "pets", "to_column": "pet_id"},
        {"from_table": "feeding_history", "from_column": "food_id", "to_table": "foods", "to_column": "food_id"},
        {"from_table": "feeding_history", "from_column": "owner_id", "to_table": "owners", "to_column": "owner_id"},
    ],
}


CASES = [
    ("Find food types where the same owner both purchased the cheapest and the "
     "most expensive food of that type.",
     {ft.MIN_MAX_SAME_ENTITY_PER_GROUP}),
    ("List pairs of pets owned by the same owner where both love the same flavor.",
     {ft.SELF_JOIN_PAIR}),
    ("List owners and pets using an outer join so owners without pets are still visible.",
     {ft.OUTER_JOIN_NULL}),
    ("Find brands that have food for all species represented in pets.",
     {ft.SET_DIVISION_COUNT_DISTINCT}),
    ("Find owners whose pets consumed foods from more brands than the owner purchased.",
     {ft.COUNT_DISTINCT_COMPARISON, ft.DERIVED_AGGREGATE_CTE}),
    ("List owners who bought the highest total quantity of food for each city.",
     {ft.DERIVED_AGGREGATE_CTE}),
]


def test_routes():
    for i, (question, expected) in enumerate(CASES, 1):
        d = route(question, GRAPH)
        assert d["family"] in expected, (question, d)
        assert d["confidence"] >= 0.55, (question, d)
        print(f"[{i}] {d['family']:<32} conf={d['confidence']} <- {question[:48]}...")
    print("routed all 6 example questions correctly")


def test_fallback_for_plain_question():
    d = route("List all owners in the city of Moscow.", GRAPH)
    assert d["family"] == ft.NORMAL_JOIN_FILTER_GROUP, d
    print("[7] plain question -> normal_join_filter_group (fallback) -> OK")


def test_twelve_families_declared():
    assert len(ft.FAMILIES) == 12 and len(set(ft.FAMILIES)) == 12, ft.FAMILIES
    assert set(ft.IMPLEMENTED_FAMILIES) <= set(ft.FAMILIES)
    print("[8] 12 families declared; implemented set is a subset -> OK")


def main():
    tests = [test_routes, test_fallback_for_plain_question, test_twelve_families_declared]
    passed = 0
    for t in tests:
        t(); passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed -- query_family_router verified")


if __name__ == "__main__":
    main()
