"""
test_anti_exists.py

Unit tests for Stage 2: anti-join / NOT EXISTS support. Covers the renderer
(render_anti_exists), validation, and end-to-end build_from_extraction ->
generate_sql for the report's absence patterns. No database, no model.

The schema mirrors the report (owners/pets/foods/...) purely as TEST DATA; the
implementation keys only off the spec structure and the column index.

Run:  python -m tests.test_anti_exists
"""

from semantic.ir_builder import build_from_extraction
from semantic.ir_validator import validate_ir
from generation.sql_clauses import render_anti_exists
from generation.multitable_sql_generator import generate_sql
from generation.sql_types import to_dict as sql_to_dict


GRAPH = {
    "tables": [
        {"table_name": "owners", "columns": [
            {"column_name": "owner_id"}, {"column_name": "owner_name"}]},
        {"table_name": "pets", "columns": [
            {"column_name": "pet_id"}, {"column_name": "pet_name"},
            {"column_name": "owner_id"}, {"column_name": "species"}]},
        {"table_name": "foods", "columns": [
            {"column_name": "food_id"}, {"column_name": "food_name"},
            {"column_name": "brand"}, {"column_name": "food_type"},
            {"column_name": "flavor"}, {"column_name": "species_target"}]},
        {"table_name": "purchases", "columns": [
            {"column_name": "purchase_id"}, {"column_name": "owner_id"},
            {"column_name": "food_id"}]},
        {"table_name": "pet_likes", "columns": [
            {"column_name": "like_id"}, {"column_name": "pet_id"},
            {"column_name": "food_type"}, {"column_name": "flavor"},
            {"column_name": "preferred_brand"}, {"column_name": "active"}]},
        {"table_name": "feeding_history", "columns": [
            {"column_name": "feed_id"}, {"column_name": "pet_id"},
            {"column_name": "food_id"}, {"column_name": "owner_id"}]},
    ]
}


def _plan(ir, from_table, joins=None):
    return {"resolved": True, "from_table": from_table, "joins": joins or [],
            "bridge_tables": [], "ir": ir}


# ---------------------------------------------------------------------------
# Renderer unit tests
# ---------------------------------------------------------------------------
def test_render_simple_correlated_not_exists():
    clauses, params = render_anti_exists([{
        "target_table": "purchases",
        "where": [{"left": {"table": "purchases", "column": "food_id"},
                   "op": "=", "right": {"table": "foods", "column": "food_id"}}],
    }])
    assert params == [], params
    assert clauses == [
        'NOT EXISTS (SELECT 1 FROM "purchases" WHERE '
        '"purchases"."food_id" = "foods"."food_id")'], clauses
    print("[1] simple correlated NOT EXISTS, no params -> OK")


def test_render_with_join_and_literal_param():
    clauses, params = render_anti_exists([{
        "target_table": "feeding_history",
        "joins": [{"from_table": "feeding_history", "from_column": "food_id",
                   "to_table": "foods", "to_column": "food_id"}],
        "where": [
            {"left": {"table": "feeding_history", "column": "pet_id"},
             "op": "=", "right": {"table": "pets", "column": "pet_id"}},
            {"left": {"table": "foods", "column": "brand"},
             "op": "=", "value": "Acme"},
        ],
    }])
    assert params == ["Acme"], params
    assert clauses[0] == (
        'NOT EXISTS (SELECT 1 FROM "feeding_history" '
        'INNER JOIN "foods" ON "feeding_history"."food_id" = "foods"."food_id" '
        'WHERE "feeding_history"."pet_id" = "pets"."pet_id" '
        'AND "foods"."brand" = ?)'), clauses[0]
    print("[2] NOT EXISTS with inner join + literal param -> OK")


def test_render_skips_malformed():
    clauses, params = render_anti_exists([{"where": []}, {}, "nonsense", None])
    assert clauses == [] and params == [], (clauses, params)
    print("[3] malformed specs (no target_table) skipped -> OK")


# ---------------------------------------------------------------------------
# End-to-end: extraction -> SQL
# ---------------------------------------------------------------------------
def test_e2e_food_never_purchased():
    extraction = {
        "tables": ["foods"],
        "select": [{"table": "foods", "column": "food_name"}],
        "anti_exists": [{
            "target_table": "purchases",
            "where": [{"left": {"table": "purchases", "column": "food_id"},
                       "op": "=", "right": {"table": "foods", "column": "food_id"}}],
        }],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    # Subquery table must NOT leak into the outer table set / joins.
    assert "purchases" not in ir.tables, ir.tables
    assert validate_ir(ir, GRAPH)["valid"], validate_ir(ir, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir, "foods")))
    assert out["generated"], out
    assert "NOT EXISTS" in out["sql"], out["sql"]
    assert '"purchases"."food_id" = "foods"."food_id"' in out["sql"], out["sql"]
    assert "HAVING" not in out["sql"] and out["params"] == [], out
    print("[4] e2e food never purchased -> NOT EXISTS, no HAVING/param -> OK")


def test_e2e_pet_never_ate_matching_loved_type_flavor():
    extraction = {
        "tables": ["pets"],
        "select": [{"table": "pets", "column": "pet_id"},
                   {"table": "pets", "column": "pet_name"}],
        "anti_exists": [{
            "target_table": "pet_likes",
            "joins": [
                {"from_table": "pet_likes", "from_column": "pet_id",
                 "to_table": "feeding_history", "to_column": "pet_id"},
                {"from_table": "feeding_history", "from_column": "food_id",
                 "to_table": "foods", "to_column": "food_id"},
            ],
            "where": [
                {"left": {"table": "pet_likes", "column": "pet_id"},
                 "op": "=", "right": {"table": "pets", "column": "pet_id"}},
                {"left": {"table": "pet_likes", "column": "active"},
                 "op": "=", "value": "yes"},
                {"left": {"table": "pet_likes", "column": "food_type"},
                 "op": "=", "right": {"table": "foods", "column": "food_type"}},
                {"left": {"table": "pet_likes", "column": "flavor"},
                 "op": "=", "right": {"table": "foods", "column": "flavor"}},
            ],
        }],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    assert validate_ir(ir, GRAPH)["valid"], validate_ir(ir, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir, "pets")))
    assert out["generated"], out
    sql = out["sql"]
    assert "NOT EXISTS" in sql and 'INNER JOIN "feeding_history"' in sql, sql
    assert '"pet_likes"."pet_id" = "pets"."pet_id"' in sql, sql
    assert '"pet_likes"."food_type" = "foods"."food_type"' in sql, sql
    assert out["params"] == ["yes"], out["params"]
    print("[5] e2e pet never ate matching loved type/flavor -> nested join + param -> OK")


def test_e2e_owner_never_purchased_food_matching_pet_species():
    extraction = {
        "tables": ["owners", "pets"],
        "select": [{"table": "owners", "column": "owner_name"}],
        "anti_exists": [{
            "target_table": "purchases",
            "joins": [{"from_table": "purchases", "from_column": "food_id",
                       "to_table": "foods", "to_column": "food_id"}],
            "where": [
                {"left": {"table": "purchases", "column": "owner_id"},
                 "op": "=", "right": {"table": "owners", "column": "owner_id"}},
                {"left": {"table": "foods", "column": "species_target"},
                 "op": "=", "right": {"table": "pets", "column": "species"}},
            ],
        }],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    assert validate_ir(ir, GRAPH)["valid"], validate_ir(ir, GRAPH)
    out = sql_to_dict(generate_sql(_plan(
        ir, "owners",
        [{"join_type": "inner", "from_table": "owners", "from_column": "owner_id",
          "to_table": "pets", "to_column": "owner_id"}])))
    assert out["generated"], out
    assert '"foods"."species_target" = "pets"."species"' in out["sql"], out["sql"]
    assert out["params"] == [], out["params"]
    print("[6] e2e owner never purchased food matching pet species -> OK")


def test_e2e_filters_and_anti_exists_param_order():
    # A plain filter param must come BEFORE the anti-exists literal param.
    extraction = {
        "tables": ["pets"],
        "select": [{"table": "pets", "column": "pet_id"}],
        "filters": [{"table": "pets", "column": "species", "op": "=", "value": "dog"}],
        "anti_exists": [{
            "target_table": "pet_likes",
            "where": [
                {"left": {"table": "pet_likes", "column": "pet_id"},
                 "op": "=", "right": {"table": "pets", "column": "pet_id"}},
                {"left": {"table": "pet_likes", "column": "active"},
                 "op": "=", "value": "yes"},
            ],
        }],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir, "pets")))
    assert out["generated"], out
    # One outer WHERE (the filter), then the anti-exists merged with AND. The
    # only other 'WHERE' is inside the NOT EXISTS subquery.
    assert '"pets"."species" = ?' in out["sql"], out["sql"]
    assert " AND NOT EXISTS (SELECT 1 FROM" in out["sql"], out["sql"]
    assert out["params"] == ["dog", "yes"], out["params"]
    print("[7] filter param precedes anti-exists param; merged WHERE -> OK")


def test_no_anti_exists_unchanged():
    extraction = {
        "tables": ["owners"],
        "select": [{"table": "owners", "column": "owner_name"}],
        "filters": [{"table": "owners", "column": "owner_id", "op": "=", "value": 5}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    assert ir.anti_exists == [], ir.anti_exists
    out = sql_to_dict(generate_sql(_plan(ir, "owners")))
    assert "NOT EXISTS" not in out["sql"], out["sql"]
    assert out["params"] == [5], out["params"]
    print("[8] queries without anti_exists are unchanged -> OK")


def test_validation_rejects_bad_target_table():
    extraction = {
        "tables": ["foods"],
        "select": [{"table": "foods", "column": "food_name"}],
        "anti_exists": [{"target_table": "nope",
                         "where": [{"left": {"table": "foods", "column": "food_id"},
                                    "op": "=", "value": 1}]}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    res = validate_ir(ir, GRAPH)
    assert not res["valid"] and any("nope" in e for e in res["errors"]), res
    print("[9] validation flags unknown anti_exists target_table -> OK")


def main():
    tests = [
        test_render_simple_correlated_not_exists,
        test_render_with_join_and_literal_param,
        test_render_skips_malformed,
        test_e2e_food_never_purchased,
        test_e2e_pet_never_ate_matching_loved_type_flavor,
        test_e2e_owner_never_purchased_food_matching_pet_species,
        test_e2e_filters_and_anti_exists_param_order,
        test_no_anti_exists_unchanged,
        test_validation_rejects_bad_target_table,
    ]
    passed = 0
    for t in tests:
        t(); passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed -- anti_exists verified")


if __name__ == "__main__":
    main()
