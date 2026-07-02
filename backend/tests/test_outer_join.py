"""
test_outer_join.py

Unit tests for Stage 7: explicit outer joins + NULL tests + compound OR/AND
filter groups. Covers the renderers, validation, and end-to-end
build_from_extraction -> generate_sql. No database, no model.

Schema mirrors the report (owners/pets/pet_likes/purchases/foods) as TEST DATA.

Run:  python -m tests.test_outer_join
"""

from semantic.ir_builder import build_from_extraction
from semantic.ir_validator import validate_ir
from generation.sql_clauses import (
    render_explicit_joins, render_null_filters, render_compound_filters,
)
from generation.multitable_sql_generator import generate_sql
from generation.sql_types import to_dict as sql_to_dict


GRAPH = {
    "tables": [
        {"table_name": "owners", "columns": [
            {"column_name": "owner_id"}, {"column_name": "owner_name"},
            {"column_name": "street_address"}]},
        {"table_name": "pets", "columns": [
            {"column_name": "pet_id"}, {"column_name": "pet_name"},
            {"column_name": "owner_id"}, {"column_name": "pet_address"}]},
        {"table_name": "purchases", "columns": [
            {"column_name": "purchase_id"}, {"column_name": "owner_id"},
            {"column_name": "food_id"}]},
        {"table_name": "pet_likes", "columns": [
            {"column_name": "like_id"}, {"column_name": "pet_id"},
            {"column_name": "food_type"}, {"column_name": "flavor"},
            {"column_name": "preferred_brand"}]},
        {"table_name": "foods", "columns": [
            {"column_name": "food_id"}, {"column_name": "brand"},
            {"column_name": "food_type"}, {"column_name": "flavor"}]},
    ]
}


def _plan(ir, from_table="owners", joins=None):
    return {"resolved": True, "from_table": from_table, "joins": joins or [],
            "bridge_tables": [], "ir": ir}


# ---------------------------------------------------------------------------
# Renderer unit tests
# ---------------------------------------------------------------------------
def test_render_left_join():
    sql, params = render_explicit_joins([{
        "join_type": "left", "from_table": "owners", "to_table": "pets",
        "conditions": [{"left": {"table": "owners", "column": "owner_id"},
                        "op": "=", "right": {"table": "pets", "column": "owner_id"}}],
    }])
    assert params == [] and sql == (
        'FROM "owners" LEFT JOIN "pets" ON '
        '"owners"."owner_id" = "pets"."owner_id"'), sql
    print("[1] explicit LEFT JOIN render -> OK")


def test_render_null_filters():
    clauses = render_null_filters([
        {"table": "pets", "column": "pet_id", "op": "IS NULL"},
        {"table": "foods", "column": "food_id", "op": "IS NOT NULL"},
    ])
    assert clauses == ['"pets"."pet_id" IS NULL', '"foods"."food_id" IS NOT NULL'], clauses
    print("[2] NULL / NOT NULL filters render -> OK")


def test_render_compound_or_group():
    clauses, params = render_compound_filters([{
        "connector": "OR",
        "conditions": [
            {"table": "pets", "column": "pet_id", "op": "IS NULL"},
            {"left": {"table": "owners", "column": "street_address"}, "op": "<>",
             "right": {"table": "pets", "column": "pet_address"}},
        ],
    }])
    assert params == [], params
    assert clauses == [
        '("pets"."pet_id" IS NULL OR '
        '"owners"."street_address" != "pets"."pet_address")'], clauses
    print("[3] compound OR (null OR mismatch) render -> OK")


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------
def test_e2e_owners_without_pets():
    extraction = {
        "select": [{"table": "owners", "column": "owner_id"},
                   {"table": "owners", "column": "owner_name"}],
        "explicit_joins": [{
            "join_type": "left", "from_table": "owners", "to_table": "pets",
            "conditions": [{"left": {"table": "owners", "column": "owner_id"},
                            "op": "=", "right": {"table": "pets", "column": "owner_id"}}],
        }],
        "null_filters": [{"table": "pets", "column": "pet_id", "op": "IS NULL"}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    assert "pets" in ir.tables and "owners" in ir.tables, ir.tables
    assert validate_ir(ir, GRAPH)["valid"], validate_ir(ir, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir)))
    assert out["generated"], out
    assert 'FROM "owners" LEFT JOIN "pets" ON "owners"."owner_id" = "pets"."owner_id"' in out["sql"], out["sql"]
    assert 'WHERE "pets"."pet_id" IS NULL' in out["sql"], out["sql"]
    assert out["params"] == [], out["params"]
    print("[4] e2e owners without pets -> LEFT JOIN + IS NULL -> OK")


def test_e2e_owners_pets_different_address_include_unmatched():
    extraction = {
        "select": [{"table": "owners", "column": "owner_id"},
                   {"table": "pets", "column": "pet_id"}],
        "explicit_joins": [{
            "join_type": "left", "from_table": "owners", "to_table": "pets",
            "conditions": [{"left": {"table": "owners", "column": "owner_id"},
                            "op": "=", "right": {"table": "pets", "column": "owner_id"}}],
        }],
        "compound_filters": [{
            "connector": "OR",
            "conditions": [
                {"table": "pets", "column": "pet_id", "op": "IS NULL"},
                {"left": {"table": "owners", "column": "street_address"}, "op": "<>",
                 "right": {"table": "pets", "column": "pet_address"}},
            ],
        }],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    assert validate_ir(ir, GRAPH)["valid"], validate_ir(ir, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir)))
    assert out["generated"], out
    assert 'LEFT JOIN "pets"' in out["sql"], out["sql"]
    assert ('WHERE ("pets"."pet_id" IS NULL OR '
            '"owners"."street_address" != "pets"."pet_address")') in out["sql"], out["sql"]
    print("[5] e2e include owners without pets OR different address -> OK")


def test_e2e_left_join_chain_multi_condition_on_with_null():
    extraction = {
        "select": [{"table": "owners", "column": "owner_name"},
                   {"table": "pet_likes", "column": "preferred_brand"}],
        "explicit_joins": [
            {"join_type": "inner", "from_table": "owners", "to_table": "pets",
             "conditions": [{"left": {"table": "owners", "column": "owner_id"}, "op": "=",
                             "right": {"table": "pets", "column": "owner_id"}}]},
            {"join_type": "inner", "from_table": "pets", "to_table": "pet_likes",
             "conditions": [{"left": {"table": "pets", "column": "pet_id"}, "op": "=",
                             "right": {"table": "pet_likes", "column": "pet_id"}}]},
            {"join_type": "left", "from_table": "owners", "to_table": "purchases",
             "conditions": [{"left": {"table": "purchases", "column": "owner_id"}, "op": "=",
                             "right": {"table": "owners", "column": "owner_id"}}]},
            {"join_type": "left", "from_table": "purchases", "to_table": "foods",
             "conditions": [
                 {"left": {"table": "foods", "column": "food_id"}, "op": "=",
                  "right": {"table": "purchases", "column": "food_id"}},
                 {"left": {"table": "foods", "column": "brand"}, "op": "=",
                  "right": {"table": "pet_likes", "column": "preferred_brand"}},
                 {"left": {"table": "foods", "column": "food_type"}, "op": "=",
                  "right": {"table": "pet_likes", "column": "food_type"}},
                 {"left": {"table": "foods", "column": "flavor"}, "op": "=",
                  "right": {"table": "pet_likes", "column": "flavor"}},
             ]},
        ],
        "null_filters": [{"table": "foods", "column": "food_id", "op": "IS NULL"}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    assert validate_ir(ir, GRAPH)["valid"], validate_ir(ir, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir)))
    assert out["generated"], out
    sql = out["sql"]
    assert 'FROM "owners" INNER JOIN "pets" ON' in sql, sql
    assert 'LEFT JOIN "purchases" ON' in sql, sql
    assert ('LEFT JOIN "foods" ON "foods"."food_id" = "purchases"."food_id" AND '
            '"foods"."brand" = "pet_likes"."preferred_brand" AND '
            '"foods"."food_type" = "pet_likes"."food_type" AND '
            '"foods"."flavor" = "pet_likes"."flavor"') in sql, sql
    assert 'WHERE "foods"."food_id" IS NULL' in sql, sql
    print("[6] e2e LEFT JOIN chain w/ multi-cond ON + IS NULL -> OK")


def test_inner_join_query_unchanged():
    extraction = {
        "tables": ["owners", "pets"],
        "select": [{"table": "owners", "column": "owner_name"}],
        "filters": [{"table": "pets", "column": "pet_name", "op": "=", "value": "Rex"}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    assert ir.explicit_joins == [] and ir.null_filters == [], ir
    plan = _plan(ir, from_table="owners",
                 joins=[{"join_type": "inner", "from_table": "owners",
                         "from_column": "owner_id", "to_table": "pets",
                         "to_column": "owner_id"}])
    out = sql_to_dict(generate_sql(plan))
    assert out["generated"], out
    assert 'FROM "owners" INNER JOIN "pets" ON "owners"."owner_id" = "pets"."owner_id"' in out["sql"], out["sql"]
    assert "LEFT JOIN" not in out["sql"] and out["params"] == ["Rex"], out
    print("[7] existing inner-join query unchanged -> OK")


def test_validation_flags_bad_explicit_join_table():
    extraction = {
        "select": [{"table": "owners", "column": "owner_id"}],
        "explicit_joins": [{
            "join_type": "left", "from_table": "owners", "to_table": "nope",
            "conditions": [{"left": {"table": "owners", "column": "owner_id"}, "op": "=",
                            "right": {"table": "nope", "column": "owner_id"}}],
        }],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    res = validate_ir(ir, GRAPH)
    assert not res["valid"] and any("nope" in e for e in res["errors"]), res
    print("[8] validation flags unknown explicit_join table -> OK")


def test_render_skips_malformed_explicit_join():
    sql, params = render_explicit_joins([{"join_type": "left"}, {}, "x", None])
    assert sql == "" and params == [], (sql, params)
    print("[9] malformed explicit_joins (no to_table) skipped -> OK")


def main():
    tests = [
        test_render_left_join,
        test_render_null_filters,
        test_render_compound_or_group,
        test_e2e_owners_without_pets,
        test_e2e_owners_pets_different_address_include_unmatched,
        test_e2e_left_join_chain_multi_condition_on_with_null,
        test_inner_join_query_unchanged,
        test_validation_flags_bad_explicit_join_table,
        test_render_skips_malformed_explicit_join,
    ]
    passed = 0
    for t in tests:
        t(); passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed -- outer_join verified")


if __name__ == "__main__":
    main()
