"""
test_self_join.py

Unit tests for Stage 6: self-join / pair queries via table aliases. Covers the
alias renderers, validation, and end-to-end build_from_extraction ->
generate_sql. No database, no model.

Schema mirrors the report (pets/pet_likes/owners) as TEST DATA only.

Run:  python -m tests.test_self_join
"""

from semantic.ir_builder import build_from_extraction
from semantic.ir_validator import validate_ir
from generation.sql_clauses import (
    render_alias_select, render_alias_from_joins, render_alias_where,
)
from generation.multitable_sql_generator import generate_sql
from generation.sql_types import to_dict as sql_to_dict


GRAPH = {
    "tables": [
        {"table_name": "owners", "columns": [
            {"column_name": "owner_id"}, {"column_name": "owner_name"}]},
        {"table_name": "pets", "columns": [
            {"column_name": "pet_id"}, {"column_name": "owner_id"},
            {"column_name": "pet_address"}]},
        {"table_name": "pet_likes", "columns": [
            {"column_name": "like_id"}, {"column_name": "pet_id"},
            {"column_name": "flavor"}, {"column_name": "preferred_brand"}]},
    ]
}


def _plan(ir, from_table="pets", joins=None):
    return {"resolved": True, "from_table": from_table, "joins": joins or [],
            "bridge_tables": [], "ir": ir}


# ---------------------------------------------------------------------------
# Renderer unit tests
# ---------------------------------------------------------------------------
def test_render_alias_select_with_output_aliases():
    sql = render_alias_select([
        {"alias": "p1", "column": "pet_id", "as": "pet1_id"},
        {"alias": "p2", "column": "pet_id", "as": "pet2_id"},
    ])
    assert sql == ('SELECT "p1"."pet_id" AS "pet1_id", '
                   '"p2"."pet_id" AS "pet2_id"'), sql
    print("[1] alias SELECT with output aliases -> OK")


def test_render_alias_from_joins_self_join():
    aliases = [{"alias": "p1", "table": "pets"}, {"alias": "p2", "table": "pets"}]
    joins = [
        {"from": {"alias": "p1", "column": "owner_id"},
         "to": {"alias": "p2", "column": "owner_id"}, "op": "="},
        {"from": {"alias": "p1", "column": "pet_id"},
         "to": {"alias": "p2", "column": "pet_id"}, "op": "<"},
    ]
    sql, leftover = render_alias_from_joins(aliases, joins)
    assert leftover == [], leftover
    assert sql == ('FROM "pets" AS "p1" INNER JOIN "pets" AS "p2" '
                   'ON "p1"."owner_id" = "p2"."owner_id" AND '
                   '"p1"."pet_id" < "p2"."pet_id"'), sql
    print("[2] self-join FROM with two ON conditions (incl '<') -> OK")


def test_render_alias_where_column_comparison():
    clause, params = render_alias_where([
        {"left": {"alias": "l1", "column": "flavor"}, "op": "=",
         "right": {"alias": "l2", "column": "flavor"}},
    ], [])
    assert params == [] and clause == 'WHERE "l1"."flavor" = "l2"."flavor"', (clause, params)
    print("[3] alias WHERE column-vs-column, no param -> OK")


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------
def test_e2e_pairs_same_owner_same_flavor():
    extraction = {
        "aliases": [
            {"alias": "p1", "table": "pets"}, {"alias": "p2", "table": "pets"},
            {"alias": "l1", "table": "pet_likes"}, {"alias": "l2", "table": "pet_likes"},
        ],
        "alias_joins": [
            {"from": {"alias": "p1", "column": "owner_id"},
             "to": {"alias": "p2", "column": "owner_id"}, "op": "="},
            {"from": {"alias": "p1", "column": "pet_id"},
             "to": {"alias": "p2", "column": "pet_id"}, "op": "<"},
            {"from": {"alias": "p1", "column": "pet_id"},
             "to": {"alias": "l1", "column": "pet_id"}, "op": "="},
            {"from": {"alias": "p2", "column": "pet_id"},
             "to": {"alias": "l2", "column": "pet_id"}, "op": "="},
        ],
        "alias_filters": [
            {"left": {"alias": "l1", "column": "flavor"}, "op": "=",
             "right": {"alias": "l2", "column": "flavor"}},
        ],
        "alias_select": [
            {"alias": "p1", "column": "pet_id", "as": "pet1_id"},
            {"alias": "p2", "column": "pet_id", "as": "pet2_id"},
        ],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    # alias base tables fed to the planner; validation passes.
    assert "pets" in ir.tables and "pet_likes" in ir.tables, ir.tables
    assert validate_ir(ir, GRAPH)["valid"], validate_ir(ir, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir)))
    assert out["generated"], out
    sql = out["sql"]
    assert sql.startswith('SELECT "p1"."pet_id" AS "pet1_id"'), sql
    assert 'FROM "pets" AS "p1" INNER JOIN "pets" AS "p2"' in sql, sql
    assert '"p1"."pet_id" < "p2"."pet_id"' in sql, sql            # duplicate-pair guard
    assert 'INNER JOIN "pet_likes" AS "l1" ON "p1"."pet_id" = "l1"."pet_id"' in sql, sql
    assert 'INNER JOIN "pet_likes" AS "l2" ON "p2"."pet_id" = "l2"."pet_id"' in sql, sql
    assert 'WHERE "l1"."flavor" = "l2"."flavor"' in sql, sql
    assert out["params"] == [], out["params"]
    print("[4] e2e pairs same owner + same liked flavor -> OK")


def test_e2e_pairs_diff_owners_same_address_same_brand():
    extraction = {
        "aliases": [
            {"alias": "p1", "table": "pets"}, {"alias": "p2", "table": "pets"},
            {"alias": "l1", "table": "pet_likes"}, {"alias": "l2", "table": "pet_likes"},
        ],
        "alias_joins": [
            {"from": {"alias": "p1", "column": "pet_address"},
             "to": {"alias": "p2", "column": "pet_address"}, "op": "="},
            {"from": {"alias": "p1", "column": "owner_id"},
             "to": {"alias": "p2", "column": "owner_id"}, "op": "<>"},
            {"from": {"alias": "p1", "column": "pet_id"},
             "to": {"alias": "l1", "column": "pet_id"}, "op": "="},
            {"from": {"alias": "p2", "column": "pet_id"},
             "to": {"alias": "l2", "column": "pet_id"}, "op": "="},
        ],
        "alias_filters": [
            {"left": {"alias": "l1", "column": "preferred_brand"}, "op": "=",
             "right": {"alias": "l2", "column": "preferred_brand"}},
        ],
        "alias_select": [
            {"alias": "p1", "column": "pet_id", "as": "pet1_id"},
            {"alias": "p2", "column": "pet_id", "as": "pet2_id"},
        ],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    assert validate_ir(ir, GRAPH)["valid"], validate_ir(ir, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir)))
    assert out["generated"], out
    assert '"p1"."pet_address" = "p2"."pet_address" AND "p1"."owner_id" != "p2"."owner_id"' in out["sql"], out["sql"]
    assert 'WHERE "l1"."preferred_brand" = "l2"."preferred_brand"' in out["sql"], out["sql"]
    print("[5] e2e pairs different owners, same address + brand ('<>') -> OK")


def test_e2e_alias_literal_filter_param():
    extraction = {
        "aliases": [{"alias": "p1", "table": "pets"}, {"alias": "p2", "table": "pets"}],
        "alias_joins": [
            {"from": {"alias": "p1", "column": "owner_id"},
             "to": {"alias": "p2", "column": "owner_id"}, "op": "="},
            {"from": {"alias": "p1", "column": "pet_id"},
             "to": {"alias": "p2", "column": "pet_id"}, "op": "<"},
        ],
        "alias_filters": [
            {"left": {"alias": "p1", "column": "pet_address"}, "op": "=", "value": "12 Elm St"},
        ],
        "alias_select": [{"alias": "p1", "column": "pet_id"},
                         {"alias": "p2", "column": "pet_id"}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir)))
    assert out["generated"], out
    assert '"p1"."pet_address" = ?' in out["sql"] and out["params"] == ["12 Elm St"], out
    print("[6] alias literal filter parameterized -> OK")


def test_non_alias_query_unchanged():
    extraction = {
        "tables": ["owners"],
        "select": [{"table": "owners", "column": "owner_name"}],
        "filters": [{"table": "owners", "column": "owner_id", "op": "=", "value": 5}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    assert ir.aliases == [], ir.aliases
    out = sql_to_dict(generate_sql(_plan(ir, from_table="owners")))
    assert out["generated"], out
    assert " AS " not in out["sql"] and out["params"] == [5], out
    print("[7] non-alias query unchanged -> OK")


def test_validation_flags_unknown_alias():
    extraction = {
        "aliases": [{"alias": "p1", "table": "pets"}],
        "alias_filters": [
            {"left": {"alias": "pX", "column": "pet_id"}, "op": "=",
             "right": {"alias": "p1", "column": "pet_id"}},
        ],
        "alias_select": [{"alias": "p1", "column": "pet_id"}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    res = validate_ir(ir, GRAPH)
    assert not res["valid"] and any("px" in e.lower() for e in res["errors"]), res
    print("[8] validation flags unknown alias reference -> OK")


def test_validation_flags_bad_alias_column():
    extraction = {
        "aliases": [{"alias": "p1", "table": "pets"}, {"alias": "p2", "table": "pets"}],
        "alias_select": [{"alias": "p1", "column": "nope"}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    res = validate_ir(ir, GRAPH)
    assert not res["valid"] and any("nope" in e for e in res["errors"]), res
    print("[9] validation flags unknown alias column -> OK")


def main():
    tests = [
        test_render_alias_select_with_output_aliases,
        test_render_alias_from_joins_self_join,
        test_render_alias_where_column_comparison,
        test_e2e_pairs_same_owner_same_flavor,
        test_e2e_pairs_diff_owners_same_address_same_brand,
        test_e2e_alias_literal_filter_param,
        test_non_alias_query_unchanged,
        test_validation_flags_unknown_alias,
        test_validation_flags_bad_alias_column,
    ]
    passed = 0
    for t in tests:
        t(); passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed -- self_join verified")


if __name__ == "__main__":
    main()
