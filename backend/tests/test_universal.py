"""
test_universal.py

Unit tests for Stage 4: universal quantification / "only" via nested NOT EXISTS.
Covers the renderer (render_universal), validation, and end-to-end
build_from_extraction -> generate_sql. No database, no model.

Schema mirrors the report (owners/pets/foods/...) as TEST DATA only; the
implementation keys off spec structure + the column index, never these names.

Run:  python -m tests.test_universal
"""

from semantic.ir_builder import build_from_extraction
from semantic.ir_validator import validate_ir
from generation.sql_clauses import render_universal
from generation.multitable_sql_generator import generate_sql
from generation.sql_types import to_dict as sql_to_dict


GRAPH = {
    "tables": [
        {"table_name": "owners", "columns": [
            {"column_name": "owner_id"}, {"column_name": "owner_name"},
            {"column_name": "city"}]},
        {"table_name": "pets", "columns": [
            {"column_name": "pet_id"}, {"column_name": "owner_id"},
            {"column_name": "species"}]},
        {"table_name": "foods", "columns": [
            {"column_name": "food_id"}, {"column_name": "species_target"},
            {"column_name": "allergen_flag"}]},
        {"table_name": "purchases", "columns": [
            {"column_name": "purchase_id"}, {"column_name": "owner_id"}]},
        {"table_name": "feeding_history", "columns": [
            {"column_name": "feed_id"}, {"column_name": "pet_id"},
            {"column_name": "food_id"}]},
    ]
}


def _plan(ir, from_table, joins=None):
    return {"resolved": True, "from_table": from_table, "joins": joins or [],
            "bridge_tables": [], "ir": ir}


# ---------------------------------------------------------------------------
# Renderer unit tests
# ---------------------------------------------------------------------------
def test_render_for_all_double_not_exists():
    clauses, params = render_universal([{
        "domain_table": "pets",
        "domain_filters": [{"left": {"table": "pets", "column": "owner_id"},
                            "op": "=", "right": {"table": "owners", "column": "owner_id"}}],
        "must_exist": {
            "target_table": "feeding_history",
            "joins": [{"from_table": "feeding_history", "from_column": "food_id",
                       "to_table": "foods", "to_column": "food_id"}],
            "where": [
                {"left": {"table": "feeding_history", "column": "pet_id"},
                 "op": "=", "right": {"table": "pets", "column": "pet_id"}},
                {"left": {"table": "foods", "column": "species_target"},
                 "op": "=", "right": {"table": "pets", "column": "species"}},
            ],
        },
    }])
    assert params == [], params
    assert clauses == [
        'NOT EXISTS (SELECT 1 FROM "pets" WHERE '
        '"pets"."owner_id" = "owners"."owner_id" AND '
        'NOT EXISTS (SELECT 1 FROM "feeding_history" '
        'INNER JOIN "foods" ON "feeding_history"."food_id" = "foods"."food_id" '
        'WHERE "feeding_history"."pet_id" = "pets"."pet_id" AND '
        '"foods"."species_target" = "pets"."species"))'], clauses
    print("[1] for-all -> double NOT EXISTS -> OK")


def test_render_only_bad_match_single_not_exists():
    clauses, params = render_universal([{
        "bad_match": {
            "target_table": "feeding_history",
            "joins": [{"from_table": "feeding_history", "from_column": "food_id",
                       "to_table": "foods", "to_column": "food_id"}],
            "where": [
                {"left": {"table": "feeding_history", "column": "pet_id"},
                 "op": "=", "right": {"table": "pets", "column": "pet_id"}},
                {"left": {"table": "foods", "column": "allergen_flag"},
                 "op": "!=", "value": "no"},
            ],
        },
    }])
    assert params == ["no"], params
    assert clauses[0] == (
        'NOT EXISTS (SELECT 1 FROM "feeding_history" '
        'INNER JOIN "foods" ON "feeding_history"."food_id" = "foods"."food_id" '
        'WHERE "feeding_history"."pet_id" = "pets"."pet_id" AND '
        '"foods"."allergen_flag" != ?)'), clauses[0]
    print("[2] 'only' -> single NOT EXISTS over bad rows -> OK")


def test_render_compound_inner_exists_and_not_exists():
    # cities where every owner has no pets OR has a purchase
    clauses, params = render_universal([{
        "domain_table": "owners",
        "domain_alias": "ox",
        "domain_filters": [{"left": {"table": "ox", "column": "city"},
                            "op": "=", "right": {"table": "owners", "column": "city"}}],
        "inner": [
            {"exists": {"target_table": "pets",
                        "where": [{"left": {"table": "pets", "column": "owner_id"},
                                   "op": "=", "right": {"table": "ox", "column": "owner_id"}}]}},
            {"not_exists": {"target_table": "purchases",
                            "where": [{"left": {"table": "purchases", "column": "owner_id"},
                                       "op": "=", "right": {"table": "ox", "column": "owner_id"}}]}},
        ],
    }])
    assert params == [], params
    assert clauses[0] == (
        'NOT EXISTS (SELECT 1 FROM "owners" AS "ox" WHERE '
        '"ox"."city" = "owners"."city" AND '
        'EXISTS (SELECT 1 FROM "pets" WHERE "pets"."owner_id" = "ox"."owner_id") AND '
        'NOT EXISTS (SELECT 1 FROM "purchases" WHERE "purchases"."owner_id" = "ox"."owner_id"))'
    ), clauses[0]
    print("[3] compound inner EXISTS + NOT EXISTS with domain alias -> OK")


def test_render_skips_malformed():
    clauses, params = render_universal([
        {},                                   # nothing
        {"domain_table": "pets"},             # domain but no inner/must_exist
        {"must_exist": {"where": []}},        # must_exist without target & no domain
        "nope", None,
    ])
    assert clauses == [] and params == [], (clauses, params)
    print("[4] malformed universal specs skipped -> OK")


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------
def test_e2e_every_pet_has_compatible_feeding():
    extraction = {
        "tables": ["owners"],
        "select": [{"table": "owners", "column": "owner_name"}],
        "universal": [{
            "domain_table": "pets",
            "domain_filters": [{"left": {"table": "pets", "column": "owner_id"},
                                "op": "=", "right": {"table": "owners", "column": "owner_id"}}],
            "must_exist": {
                "target_table": "feeding_history",
                "joins": [{"from_table": "feeding_history", "from_column": "food_id",
                           "to_table": "foods", "to_column": "food_id"}],
                "where": [
                    {"left": {"table": "feeding_history", "column": "pet_id"},
                     "op": "=", "right": {"table": "pets", "column": "pet_id"}},
                    {"left": {"table": "foods", "column": "species_target"},
                     "op": "=", "right": {"table": "pets", "column": "species"}},
                ],
            },
        }],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    # Domain/inner tables must NOT leak into the outer table set.
    assert ir.tables == ["owners"], ir.tables
    assert validate_ir(ir, GRAPH)["valid"], validate_ir(ir, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir, "owners")))
    assert out["generated"], out
    assert out["sql"].count("NOT EXISTS") == 2, out["sql"]
    assert '"foods"."species_target" = "pets"."species"' in out["sql"], out["sql"]
    assert out["params"] == [], out["params"]
    print("[5] e2e every pet has compatible feeding -> double NOT EXISTS -> OK")


def test_e2e_only_allergen_free():
    extraction = {
        "tables": ["pets"],
        "select": [{"table": "pets", "column": "pet_id"}],
        "universal": [{
            "bad_match": {
                "target_table": "feeding_history",
                "joins": [{"from_table": "feeding_history", "from_column": "food_id",
                           "to_table": "foods", "to_column": "food_id"}],
                "where": [
                    {"left": {"table": "feeding_history", "column": "pet_id"},
                     "op": "=", "right": {"table": "pets", "column": "pet_id"}},
                    {"left": {"table": "foods", "column": "allergen_flag"},
                     "op": "!=", "value": "no"},
                ],
            },
        }],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    assert validate_ir(ir, GRAPH)["valid"], validate_ir(ir, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir, "pets")))
    assert out["generated"], out
    assert out["sql"].count("NOT EXISTS") == 1, out["sql"]
    assert '"foods"."allergen_flag" != ?' in out["sql"] and out["params"] == ["no"], out
    print("[6] e2e only allergen-free foods -> single NOT EXISTS + param -> OK")


def test_e2e_every_owner_no_pets_or_purchase():
    extraction = {
        "tables": ["owners"],
        "select": [{"table": "owners", "column": "city"}],
        "distinct": True,
        "universal": [{
            "domain_table": "owners",
            "domain_alias": "ox",
            "domain_filters": [{"left": {"table": "ox", "column": "city"},
                                "op": "=", "right": {"table": "owners", "column": "city"}}],
            "inner": [
                {"exists": {"target_table": "pets",
                            "where": [{"left": {"table": "pets", "column": "owner_id"},
                                       "op": "=", "right": {"table": "ox", "column": "owner_id"}}]}},
                {"not_exists": {"target_table": "purchases",
                                "where": [{"left": {"table": "purchases", "column": "owner_id"},
                                           "op": "=", "right": {"table": "ox", "column": "owner_id"}}]}},
            ],
        }],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    assert validate_ir(ir, GRAPH)["valid"], validate_ir(ir, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir, "owners")))
    assert out["generated"], out
    assert 'FROM "owners" AS "ox"' in out["sql"], out["sql"]
    assert "EXISTS (SELECT 1 FROM \"pets\"" in out["sql"], out["sql"]
    assert "NOT EXISTS (SELECT 1 FROM \"purchases\"" in out["sql"], out["sql"]
    print("[7] e2e every owner: no pets OR has purchase -> compound inner -> OK")


def test_e2e_filter_and_universal_param_order():
    extraction = {
        "tables": ["pets"],
        "select": [{"table": "pets", "column": "pet_id"}],
        "filters": [{"table": "pets", "column": "species", "op": "=", "value": "dog"}],
        "universal": [{
            "bad_match": {
                "target_table": "feeding_history",
                "joins": [{"from_table": "feeding_history", "from_column": "food_id",
                           "to_table": "foods", "to_column": "food_id"}],
                "where": [
                    {"left": {"table": "feeding_history", "column": "pet_id"},
                     "op": "=", "right": {"table": "pets", "column": "pet_id"}},
                    {"left": {"table": "foods", "column": "allergen_flag"},
                     "op": "!=", "value": "no"},
                ],
            },
        }],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir, "pets")))
    assert out["generated"], out
    assert out["params"] == ["dog", "no"], out["params"]   # filter param before universal param
    print("[8] filter param precedes universal param -> OK")


def test_no_universal_unchanged():
    extraction = {
        "tables": ["owners"],
        "select": [{"table": "owners", "column": "owner_name"}],
        "filters": [{"table": "owners", "column": "owner_id", "op": "=", "value": 5}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    assert ir.universal == [], ir.universal
    out = sql_to_dict(generate_sql(_plan(ir, "owners")))
    assert "NOT EXISTS" not in out["sql"] and out["params"] == [5], out
    print("[9] queries without universal unchanged -> OK")


def test_validation_flags_bad_domain_table():
    extraction = {
        "tables": ["owners"],
        "select": [{"table": "owners", "column": "owner_name"}],
        "universal": [{
            "domain_table": "nope",
            "must_exist": {"target_table": "pets",
                           "where": [{"left": {"table": "pets", "column": "owner_id"},
                                      "op": "=", "right": {"table": "owners", "column": "owner_id"}}]},
        }],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    res = validate_ir(ir, GRAPH)
    assert not res["valid"] and any("nope" in e for e in res["errors"]), res
    print("[10] validation flags unknown domain_table -> OK")


def main():
    tests = [
        test_render_for_all_double_not_exists,
        test_render_only_bad_match_single_not_exists,
        test_render_compound_inner_exists_and_not_exists,
        test_render_skips_malformed,
        test_e2e_every_pet_has_compatible_feeding,
        test_e2e_only_allergen_free,
        test_e2e_every_owner_no_pets_or_purchase,
        test_e2e_filter_and_universal_param_order,
        test_no_universal_unchanged,
        test_validation_flags_bad_domain_table,
    ]
    passed = 0
    for t in tests:
        t(); passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed -- universal verified")


if __name__ == "__main__":
    main()
