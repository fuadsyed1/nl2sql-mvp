"""
test_distinct_aggregation.py

Unit tests for Stage 5: COUNT(DISTINCT ...), aggregate-vs-aggregate HAVING, and
COUNT(DISTINCT)-based set division. Covers the renderers, validation, and
end-to-end build_from_extraction -> generate_sql. No database, no model.

Schema mirrors the report (foods/owners/pets/...) as TEST DATA only.

Run:  python -m tests.test_distinct_aggregation
"""

from semantic.ir_builder import build_from_extraction
from semantic.ir_validator import validate_ir
from generation.sql_clauses import render_set_division
from generation.multitable_sql_generator import generate_sql
from generation.sql_types import to_dict as sql_to_dict


GRAPH = {
    "tables": [
        {"table_name": "foods", "columns": [
            {"column_name": "food_id"}, {"column_name": "brand"},
            {"column_name": "flavor"}, {"column_name": "species_target"}]},
        {"table_name": "pets", "columns": [
            {"column_name": "pet_id"}, {"column_name": "pet_name"},
            {"column_name": "species"}]},
        {"table_name": "feeding_history", "columns": [
            {"column_name": "feed_id"}, {"column_name": "pet_id"},
            {"column_name": "food_id"}]},
        {"table_name": "purchases", "columns": [
            {"column_name": "purchase_id"}, {"column_name": "owner_id"},
            {"column_name": "food_id"}]},
        {"table_name": "owners", "columns": [
            {"column_name": "owner_id"}, {"column_name": "owner_name"}]},
    ]
}


def _plan(ir, from_table, joins=None):
    return {"resolved": True, "from_table": from_table, "joins": joins or [],
            "bridge_tables": [], "ir": ir}


# ---------------------------------------------------------------------------
# COUNT(DISTINCT ...)
# ---------------------------------------------------------------------------
def test_count_distinct_render():
    extraction = {
        "tables": ["foods"],
        "select": [],
        "aggregations": [{"function": "COUNT", "distinct": True, "table": "foods",
                          "column": "brand", "alias": "distinct_brand_count"}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir, "foods")))
    assert out["generated"], out
    assert 'COUNT(DISTINCT "foods"."brand") AS "distinct_brand_count"' in out["sql"], out["sql"]
    print("[1] COUNT(DISTINCT foods.brand) -> OK")


def test_count_star_unchanged():
    extraction = {
        "tables": ["foods"],
        "select": [],
        "aggregations": [{"function": "COUNT", "table": "foods", "column": "*",
                          "alias": "n"}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir, "foods")))
    assert "COUNT(*)" in out["sql"] and "DISTINCT" not in out["sql"], out["sql"]
    print("[2] normal COUNT(*) unchanged (distinct not forced) -> OK")


# ---------------------------------------------------------------------------
# Aggregate-vs-aggregate HAVING
# ---------------------------------------------------------------------------
def test_having_aggregate_vs_aggregate():
    extraction = {
        "tables": ["owners"],
        "select": [{"table": "owners", "column": "owner_id"}],
        "aggregations": [
            {"function": "COUNT", "distinct": True, "table": "feeding_history",
             "column": "food_id", "alias": "fed_brands"},
            {"function": "COUNT", "distinct": True, "table": "purchases",
             "column": "food_id", "alias": "bought_brands"},
        ],
        "group_by": [{"table": "owners", "column": "owner_id"}],
        "having": [{"aggregation_alias": "fed_brands", "op": ">",
                    "right_aggregation_alias": "bought_brands"}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir, "owners")))
    assert out["generated"], out
    assert 'HAVING "fed_brands" > "bought_brands"' in out["sql"], out["sql"]
    assert out["params"] == [], out["params"]
    print("[3] HAVING aggregate > aggregate (no param) -> OK")


def test_having_scalar_still_parameterized():
    extraction = {
        "tables": ["foods"],
        "select": [{"table": "foods", "column": "brand"}],
        "aggregations": [{"function": "COUNT", "distinct": True, "table": "foods",
                          "column": "flavor", "alias": "flavors"}],
        "group_by": [{"table": "foods", "column": "brand"}],
        "having": [{"aggregation_alias": "flavors", "op": "<", "value": 2}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir, "foods")))
    assert 'HAVING "flavors" < ?' in out["sql"] and out["params"] == [2], out
    print("[4] scalar HAVING still parameterized (pets < 2 distinct brands shape) -> OK")


# ---------------------------------------------------------------------------
# Set division
# ---------------------------------------------------------------------------
def test_render_set_division():
    havings, params, group_cols = render_set_division([{
        "group_by": [{"table": "foods", "column": "brand"}],
        "left": {"function": "COUNT", "distinct": True, "table": "foods",
                 "column": "species_target"},
        "op": "=",
        "right_subquery": {"function": "COUNT", "distinct": True, "table": "pets",
                           "column": "species"},
    }])
    assert params == [], params
    assert group_cols == [{"table": "foods", "column": "brand"}], group_cols
    assert havings == [
        'COUNT(DISTINCT "foods"."species_target") = '
        '(SELECT COUNT(DISTINCT "pets"."species") FROM "pets")'], havings
    print("[5] set_division render -> COUNT(DISTINCT) = (subquery) -> OK")


def test_e2e_set_division_all_species():
    extraction = {
        "tables": ["foods"],
        "select": [{"table": "foods", "column": "brand"}],
        "set_division": [{
            "group_by": [{"table": "foods", "column": "brand"}],
            "left": {"function": "COUNT", "distinct": True, "table": "foods",
                     "column": "species_target"},
            "op": "=",
            "right_subquery": {"function": "COUNT", "distinct": True, "table": "pets",
                               "column": "species"},
        }],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    assert validate_ir(ir, GRAPH)["valid"], validate_ir(ir, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir, "foods")))
    assert out["generated"], out
    assert 'GROUP BY "foods"."brand"' in out["sql"], out["sql"]
    assert ('HAVING COUNT(DISTINCT "foods"."species_target") = '
            '(SELECT COUNT(DISTINCT "pets"."species") FROM "pets")') in out["sql"], out["sql"]
    assert out["params"] == [], out["params"]
    print("[6] e2e set division: brand has food for all pet species -> OK")


def test_set_division_with_subquery_where_param():
    havings, params, _ = render_set_division([{
        "group_by": [{"table": "foods", "column": "brand"}],
        "left": {"function": "COUNT", "distinct": True, "table": "foods",
                 "column": "species_target"},
        "op": ">=",
        "right_subquery": {
            "function": "COUNT", "distinct": True, "table": "pets", "column": "species",
            "where": [{"left": {"table": "pets", "column": "species"}, "op": "!=", "value": "fish"}],
        },
    }])
    assert params == ["fish"], params
    assert 'WHERE "pets"."species" != ?)' in havings[0], havings[0]
    print("[7] set_division right-subquery WHERE contributes a param -> OK")


def test_no_distinct_features_unchanged():
    extraction = {
        "tables": ["foods"],
        "select": [],
        "aggregations": [{"function": "COUNT", "table": "foods", "column": "food_id",
                          "alias": "n"}],
        "group_by": [{"table": "foods", "column": "brand"}],
        "having": [{"aggregation_alias": "n", "op": ">=", "value": 3}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    assert ir.set_division == [], ir.set_division
    out = sql_to_dict(generate_sql(_plan(ir, "foods")))
    assert "DISTINCT" not in out["sql"] and out["params"] == [3], out
    print("[8] queries without distinct/set_division unchanged -> OK")


def test_render_set_division_skips_malformed():
    havings, params, group_cols = render_set_division([
        {}, {"left": {}}, {"right_subquery": {}}, "x", None,
        {"left": {"function": "COUNT", "table": "foods", "column": "brand"}},  # no right
    ])
    assert havings == [] and params == [] and group_cols == [], (havings, params, group_cols)
    print("[9] malformed set_division specs skipped -> OK")


def test_validation_flags_bad_set_division_column():
    extraction = {
        "tables": ["foods"],
        "select": [{"table": "foods", "column": "brand"}],
        "set_division": [{
            "group_by": [{"table": "foods", "column": "brand"}],
            "left": {"function": "COUNT", "distinct": True, "table": "foods",
                     "column": "nope"},
            "op": "=",
            "right_subquery": {"function": "COUNT", "distinct": True, "table": "pets",
                               "column": "species"},
        }],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    res = validate_ir(ir, GRAPH)
    assert not res["valid"] and any("nope" in e for e in res["errors"]), res
    print("[10] validation flags unknown set_division.left column -> OK")


def main():
    tests = [
        test_count_distinct_render,
        test_count_star_unchanged,
        test_having_aggregate_vs_aggregate,
        test_having_scalar_still_parameterized,
        test_render_set_division,
        test_e2e_set_division_all_species,
        test_set_division_with_subquery_where_param,
        test_no_distinct_features_unchanged,
        test_render_set_division_skips_malformed,
        test_validation_flags_bad_set_division_column,
    ]
    passed = 0
    for t in tests:
        t(); passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed -- distinct/aggregate/set_division verified")


if __name__ == "__main__":
    main()
