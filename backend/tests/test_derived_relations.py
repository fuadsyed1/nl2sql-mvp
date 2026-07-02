"""
test_derived_relations.py

Unit tests for the derived-relations / CTE capability: WITH clauses, a main
query sourced from a CTE, top_per_group over CTE columns, and two-CTE aggregate
comparison via explicit_joins + value_ref. Covers the renderer, validation, and
end-to-end build_from_extraction -> generate_sql. No database, no model.

Schema mirrors the report (owners/purchases/feeding_history/foods) as TEST DATA.

Run:  python -m tests.test_derived_relations
"""

from semantic.ir_builder import build_from_extraction
from semantic.ir_validator import validate_ir
from generation.sql_clauses import render_with_clause
from generation.multitable_sql_generator import generate_sql
from generation.sql_types import to_dict as sql_to_dict


GRAPH = {
    "tables": [
        {"table_name": "owners", "columns": [
            {"column_name": "owner_id"}, {"column_name": "owner_name"},
            {"column_name": "city"}]},
        {"table_name": "purchases", "columns": [
            {"column_name": "purchase_id"}, {"column_name": "owner_id"},
            {"column_name": "food_id"}, {"column_name": "quantity"},
            {"column_name": "total_amount"}]},
        {"table_name": "feeding_history", "columns": [
            {"column_name": "feed_id"}, {"column_name": "owner_id"},
            {"column_name": "food_id"}]},
        {"table_name": "foods", "columns": [
            {"column_name": "food_id"}, {"column_name": "brand"}]},
    ]
}


def _plan(ir, from_table="owners", joins=None):
    return {"resolved": True, "from_table": from_table, "joins": joins or [],
            "bridge_tables": [], "ir": ir}


def _owner_totals_cte():
    return {
        "name": "owner_purchase_totals",
        "from_table": "owners",
        "joins": [{"from_table": "owners", "from_column": "owner_id",
                   "to_table": "purchases", "to_column": "owner_id",
                   "join_type": "inner"}],
        "select": [{"table": "owners", "column": "owner_id", "alias": "owner_id"},
                   {"table": "owners", "column": "city", "alias": "city"}],
        "aggregations": [{"function": "SUM", "table": "purchases",
                          "column": "quantity", "alias": "total_quantity"}],
        "group_by": [{"table": "owners", "column": "owner_id"},
                     {"table": "owners", "column": "city"}],
    }


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------
def test_render_with_clause():
    sql, params = render_with_clause([_owner_totals_cte()])
    assert params == [], params
    assert sql == (
        'WITH "owner_purchase_totals" AS ('
        'SELECT "owners"."owner_id" AS "owner_id", "owners"."city" AS "city", '
        'SUM("purchases"."quantity") AS "total_quantity" '
        'FROM "owners" INNER JOIN "purchases" ON "owners"."owner_id" = "purchases"."owner_id" '
        'GROUP BY "owners"."owner_id", "owners"."city")'), sql
    print("[1] WITH clause render -> OK")


def test_render_with_skips_malformed():
    sql, params = render_with_clause([{"name": "x"}, {}, "nope", None,
                                      {"from_table": "owners"}])
    assert sql == "" and params == [], (sql, params)
    print("[2] malformed CTE specs skipped -> OK")


# ---------------------------------------------------------------------------
# End-to-end: CTE + top_per_group (highest total per city incl. ties)
# ---------------------------------------------------------------------------
def test_e2e_top_total_per_city_with_ties():
    extraction = {
        "derived_relations": [_owner_totals_cte()],
        "main_from": "owner_purchase_totals",
        "top_per_group": [{
            "table": "owner_purchase_totals",
            "partition_by": [{"table": "owner_purchase_totals", "column": "city"}],
            "order_by": {"table": "owner_purchase_totals", "column": "total_quantity",
                         "direction": "desc"},
            "rank": 1, "include_ties": True,
        }],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    # CTE name not in ir.tables; underlying real tables present for the planner.
    assert "owner_purchase_totals" not in ir.tables, ir.tables
    assert "owners" in ir.tables and "purchases" in ir.tables, ir.tables
    assert validate_ir(ir, GRAPH)["valid"], validate_ir(ir, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir)))
    assert out["generated"], out
    sql = out["sql"]
    assert sql.startswith('WITH "owner_purchase_totals" AS ('), sql
    assert 'SELECT * FROM "owner_purchase_totals" WHERE NOT EXISTS (' in sql, sql
    assert ('FROM "owner_purchase_totals" AS "owner_purchase_totals__g0" WHERE '
            '"owner_purchase_totals__g0"."city" = "owner_purchase_totals"."city" AND '
            '"owner_purchase_totals__g0"."total_quantity" > '
            '"owner_purchase_totals"."total_quantity"') in sql, sql
    assert out["params"] == [], out["params"]
    print("[3] e2e highest total quantity per city incl. ties (CTE + top_per_group) -> OK")


# ---------------------------------------------------------------------------
# End-to-end: two-CTE aggregate comparison (fed vs purchased distinct brands)
# ---------------------------------------------------------------------------
def test_e2e_two_cte_distinct_count_comparison():
    fed = {
        "name": "fed_counts", "from_table": "owners",
        "joins": [
            {"from_table": "owners", "from_column": "owner_id",
             "to_table": "feeding_history", "to_column": "owner_id"},
            {"from_table": "feeding_history", "from_column": "food_id",
             "to_table": "foods", "to_column": "food_id"},
        ],
        "select": [{"table": "owners", "column": "owner_id", "alias": "owner_id"}],
        "aggregations": [{"function": "COUNT", "distinct": True, "table": "foods",
                          "column": "brand", "alias": "fed_brands"}],
        "group_by": [{"table": "owners", "column": "owner_id"}],
    }
    bought = {
        "name": "bought_counts", "from_table": "owners",
        "joins": [
            {"from_table": "owners", "from_column": "owner_id",
             "to_table": "purchases", "to_column": "owner_id"},
            {"from_table": "purchases", "from_column": "food_id",
             "to_table": "foods", "to_column": "food_id"},
        ],
        "select": [{"table": "owners", "column": "owner_id", "alias": "owner_id"}],
        "aggregations": [{"function": "COUNT", "distinct": True, "table": "foods",
                          "column": "brand", "alias": "bought_brands"}],
        "group_by": [{"table": "owners", "column": "owner_id"}],
    }
    extraction = {
        "derived_relations": [fed, bought],
        "select": [{"table": "fed_counts", "column": "owner_id"}],
        "explicit_joins": [{
            "join_type": "inner", "from_table": "fed_counts", "to_table": "bought_counts",
            "conditions": [{"left": {"table": "fed_counts", "column": "owner_id"},
                            "op": "=", "right": {"table": "bought_counts", "column": "owner_id"}}],
        }],
        "filters": [{"table": "fed_counts", "column": "fed_brands", "op": ">",
                     "value_ref": {"table": "bought_counts", "column": "bought_brands"}}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    assert validate_ir(ir, GRAPH)["valid"], validate_ir(ir, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir)))
    assert out["generated"], out
    sql = out["sql"]
    assert sql.startswith('WITH "fed_counts" AS ('), sql
    assert '"bought_counts" AS (' in sql, sql
    assert 'FROM "fed_counts" INNER JOIN "bought_counts" ON "fed_counts"."owner_id" = "bought_counts"."owner_id"' in sql, sql
    assert 'WHERE "fed_counts"."fed_brands" > "bought_counts"."bought_brands"' in sql, sql
    assert 'COUNT(DISTINCT "foods"."brand") AS "fed_brands"' in sql, sql
    assert out["params"] == [], out["params"]
    print("[4] e2e fed vs purchased distinct brand counts (two CTEs) -> OK")


# ---------------------------------------------------------------------------
# Validation + non-CTE unchanged
# ---------------------------------------------------------------------------
def test_validation_flags_bad_main_from():
    extraction = {
        "derived_relations": [_owner_totals_cte()],
        "main_from": "does_not_exist",
        "select": [],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    res = validate_ir(ir, GRAPH)
    assert not res["valid"] and any("does_not_exist" in e for e in res["errors"]), res
    print("[5] validation flags unknown main_from -> OK")


def test_validation_flags_bad_cte_body_column():
    bad = dict(_owner_totals_cte())
    bad["aggregations"] = [{"function": "SUM", "table": "purchases",
                            "column": "nope", "alias": "total_quantity"}]
    extraction = {"derived_relations": [bad], "main_from": "owner_purchase_totals",
                  "select": []}
    ir = build_from_extraction(1, extraction, GRAPH)
    res = validate_ir(ir, GRAPH)
    assert not res["valid"] and any("nope" in e for e in res["errors"]), res
    print("[6] validation flags bad column inside CTE body -> OK")


def test_non_cte_query_unchanged():
    extraction = {
        "tables": ["owners"],
        "select": [{"table": "owners", "column": "owner_name"}],
        "filters": [{"table": "owners", "column": "city", "op": "=", "value": "Moscow"}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    assert ir.derived_relations == [] and ir.main_from is None, ir
    out = sql_to_dict(generate_sql(_plan(ir)))
    assert out["generated"], out
    assert "WITH" not in out["sql"] and out["params"] == ["Moscow"], out
    print("[7] non-CTE query unchanged -> OK")


def main():
    tests = [
        test_render_with_clause,
        test_render_with_skips_malformed,
        test_e2e_top_total_per_city_with_ties,
        test_e2e_two_cte_distinct_count_comparison,
        test_validation_flags_bad_main_from,
        test_validation_flags_bad_cte_body_column,
        test_non_cte_query_unchanged,
    ]
    passed = 0
    for t in tests:
        t(); passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed -- derived_relations verified")


if __name__ == "__main__":
    main()
