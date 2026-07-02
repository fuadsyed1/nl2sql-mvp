"""
test_top_per_group.py

Unit tests for Stage 3: top-per-group / ranking-within-group. Covers the
renderer (render_top_per_group), validation, and end-to-end
build_from_extraction -> generate_sql. No database, no model.

Schema mirrors the report (foods/owners) as TEST DATA only; the implementation
keys off spec structure + the column index, never these names.

Run:  python -m tests.test_top_per_group
"""

from semantic.ir_builder import build_from_extraction
from semantic.ir_validator import validate_ir
from generation.sql_clauses import render_top_per_group
from generation.multitable_sql_generator import generate_sql
from generation.sql_types import to_dict as sql_to_dict


GRAPH = {
    "tables": [
        {"table_name": "foods", "columns": [
            {"column_name": "food_id"}, {"column_name": "food_name"},
            {"column_name": "brand"}, {"column_name": "food_type"},
            {"column_name": "price"}]},
        {"table_name": "owners", "columns": [
            {"column_name": "owner_id"}, {"column_name": "owner_name"},
            {"column_name": "city"}, {"column_name": "annual_income"}]},
    ]
}


def _plan(ir, from_table, joins=None):
    return {"resolved": True, "from_table": from_table, "joins": joins or [],
            "bridge_tables": [], "ir": ir}


# ---------------------------------------------------------------------------
# Renderer unit tests
# ---------------------------------------------------------------------------
def test_render_rank1_max_not_exists():
    clauses, params = render_top_per_group([{
        "table": "foods",
        "partition_by": [{"table": "foods", "column": "brand"}],
        "order_by": {"table": "foods", "column": "price", "direction": "desc"},
        "rank": 1, "include_ties": True,
    }])
    assert params == [], params
    assert clauses == [
        'NOT EXISTS (SELECT 1 FROM "foods" AS "foods__g0" WHERE '
        '"foods__g0"."brand" = "foods"."brand" AND '
        '"foods__g0"."price" > "foods"."price")'], clauses
    print("[1] rank-1 max -> NOT EXISTS with '>' -> OK")


def test_render_rank1_min_uses_less_than():
    clauses, _ = render_top_per_group([{
        "table": "owners",
        "partition_by": [{"table": "owners", "column": "city"}],
        "order_by": {"table": "owners", "column": "annual_income", "direction": "asc"},
        "rank": 1,
    }])
    assert '"owners__g0"."annual_income" < "owners"."annual_income"' in clauses[0], clauses
    assert clauses[0].startswith("NOT EXISTS"), clauses
    print("[2] rank-1 min -> NOT EXISTS with '<' -> OK")


def test_render_rank2_count_distinct():
    clauses, params = render_top_per_group([{
        "table": "foods",
        "partition_by": [{"table": "foods", "column": "brand"}],
        "order_by": {"table": "foods", "column": "price", "direction": "desc"},
        "rank": 2,
    }])
    assert params == [], params
    assert clauses == [
        '(SELECT COUNT(DISTINCT "foods__g0"."price") FROM "foods" AS "foods__g0" '
        'WHERE "foods__g0"."brand" = "foods"."brand" AND '
        '"foods__g0"."price" > "foods"."price") = 1'], clauses
    print("[3] rank-2 max -> COUNT(DISTINCT greater) = 1 -> OK")


def test_render_multiple_partition_columns():
    clauses, _ = render_top_per_group([{
        "table": "foods",
        "partition_by": [{"table": "foods", "column": "brand"},
                         {"table": "foods", "column": "food_type"}],
        "order_by": {"table": "foods", "column": "price", "direction": "desc"},
        "rank": 1,
    }])
    assert '"foods__g0"."brand" = "foods"."brand"' in clauses[0], clauses
    assert '"foods__g0"."food_type" = "foods"."food_type"' in clauses[0], clauses
    print("[4] multiple partition columns -> both equalities -> OK")


def test_render_skips_malformed():
    clauses, params = render_top_per_group([
        {"partition_by": []},                                   # no table
        {"table": "foods"},                                     # no order_by
        {"table": "foods", "order_by": {"table": "foods"}},     # no order column
        "nope", None,
    ])
    assert clauses == [] and params == [], (clauses, params)
    print("[5] malformed specs skipped -> OK")


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------
def test_e2e_highest_price_per_brand():
    extraction = {
        "tables": ["foods"],
        "select": [{"table": "foods", "column": "food_name"},
                   {"table": "foods", "column": "price"}],
        "top_per_group": [{
            "table": "foods",
            "partition_by": [{"table": "foods", "column": "brand"}],
            "order_by": {"table": "foods", "column": "price", "direction": "DESC"},
            "rank": 1, "include_ties": True,
        }],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    assert validate_ir(ir, GRAPH)["valid"], validate_ir(ir, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir, "foods")))
    assert out["generated"], out
    assert "NOT EXISTS" in out["sql"] and '"foods__g0"."price" > "foods"."price"' in out["sql"], out["sql"]
    assert "GROUP BY" not in out["sql"] and out["params"] == [], out
    print("[6] e2e highest price per brand -> NOT EXISTS, no GROUP BY/param -> OK")


def test_e2e_lowest_income_per_city():
    extraction = {
        "tables": ["owners"],
        "select": [{"table": "owners", "column": "owner_name"}],
        "top_per_group": [{
            "table": "owners",
            "partition_by": [{"table": "owners", "column": "city"}],
            "order_by": {"table": "owners", "column": "annual_income", "direction": "asc"},
            "rank": 1,
        }],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    assert validate_ir(ir, GRAPH)["valid"], validate_ir(ir, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir, "owners")))
    assert out["generated"], out
    assert '"owners__g0"."annual_income" < "owners"."annual_income"' in out["sql"], out["sql"]
    print("[7] e2e lowest income per city -> OK")


def test_e2e_second_highest_price_per_brand():
    extraction = {
        "tables": ["foods"],
        "select": [{"table": "foods", "column": "food_name"}],
        "top_per_group": [{
            "table": "foods",
            "partition_by": [{"table": "foods", "column": "brand"}],
            "order_by": {"table": "foods", "column": "price", "direction": "desc"},
            "rank": 2,
        }],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir, "foods")))
    assert out["generated"], out
    assert "COUNT(DISTINCT" in out["sql"] and ") = 1" in out["sql"], out["sql"]
    assert "LIMIT" not in out["sql"], out["sql"]
    print("[8] e2e second highest price per brand -> COUNT(DISTINCT)=1, no LIMIT -> OK")


def test_e2e_filter_and_top_per_group_coexist():
    extraction = {
        "tables": ["foods"],
        "select": [{"table": "foods", "column": "food_name"}],
        "filters": [{"table": "foods", "column": "food_type", "op": "=", "value": "dry"}],
        "top_per_group": [{
            "table": "foods",
            "partition_by": [{"table": "foods", "column": "brand"}],
            "order_by": {"table": "foods", "column": "price", "direction": "desc"},
            "rank": 1,
        }],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir, "foods")))
    assert out["generated"], out
    assert '"foods"."food_type" = ?' in out["sql"] and " AND NOT EXISTS" in out["sql"], out["sql"]
    assert out["params"] == ["dry"], out["params"]
    print("[9] filter + top_per_group merge in WHERE; param preserved -> OK")


def test_no_top_per_group_unchanged():
    extraction = {
        "tables": ["foods"],
        "select": [{"table": "foods", "column": "food_name"}],
        "filters": [{"table": "foods", "column": "price", "op": ">", "value": 10}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    assert ir.top_per_group == [], ir.top_per_group
    out = sql_to_dict(generate_sql(_plan(ir, "foods")))
    assert "NOT EXISTS" not in out["sql"] and out["params"] == [10], out
    print("[10] queries without top_per_group unchanged -> OK")


def test_validation_rejects_bad_column():
    extraction = {
        "tables": ["foods"],
        "select": [{"table": "foods", "column": "food_name"}],
        "top_per_group": [{
            "table": "foods",
            "partition_by": [{"table": "foods", "column": "nope"}],
            "order_by": {"table": "foods", "column": "price", "direction": "desc"},
            "rank": 1,
        }],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    res = validate_ir(ir, GRAPH)
    assert not res["valid"] and any("nope" in e for e in res["errors"]), res
    print("[11] validation flags unknown partition column -> OK")


def main():
    tests = [
        test_render_rank1_max_not_exists,
        test_render_rank1_min_uses_less_than,
        test_render_rank2_count_distinct,
        test_render_multiple_partition_columns,
        test_render_skips_malformed,
        test_e2e_highest_price_per_brand,
        test_e2e_lowest_income_per_city,
        test_e2e_second_highest_price_per_brand,
        test_e2e_filter_and_top_per_group_coexist,
        test_no_top_per_group_unchanged,
        test_validation_rejects_bad_column,
    ]
    passed = 0
    for t in tests:
        t(); passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed -- top_per_group verified")


if __name__ == "__main__":
    main()
