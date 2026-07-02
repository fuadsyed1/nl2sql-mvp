"""
test_column_comparison.py

Unit tests for Stage 1: column-vs-column predicate detection. A filter whose
right-hand side names a real schema column is rewritten to a `value_ref` so the
generator emits a column-to-column comparison (no parameter), while genuine
string literals stay parameterized.

The schema below mirrors the failing report cases (owners/pets/foods) purely as
TEST DATA — the normalizer itself keys only off the column index, never off
these names.

Run:  python -m tests.test_column_comparison
"""

from semantic.ir_normalizer import (
    build_column_index,
    resolve_column_comparisons,
)
from semantic.ir_builder import build_from_extraction
from generation.multitable_sql_generator import generate_sql
from generation.sql_types import to_dict as sql_to_dict


GRAPH = {
    "tables": [
        {"table_name": "owners", "columns": [
            {"column_name": "owner_id", "data_type": "INTEGER",
             "is_primary_key_candidate": True, "sample_values": [1, 2, 3]},
            {"column_name": "city", "data_type": "TEXT",
             "sample_values": ["Moscow", "Boston"]},
            {"column_name": "state", "data_type": "TEXT",
             "sample_values": ["Idaho", "Texas"]},
            {"column_name": "street_address", "data_type": "TEXT",
             "sample_values": ["12 Elm St", "9 Oak Ave"]},
        ]},
        {"table_name": "pets", "columns": [
            {"column_name": "pet_id", "data_type": "INTEGER",
             "is_primary_key_candidate": True, "sample_values": [1, 2]},
            {"column_name": "owner_id", "data_type": "INTEGER",
             "sample_values": [1, 2]},
            {"column_name": "species", "data_type": "TEXT",
             "sample_values": ["dog", "cat"]},
            {"column_name": "pet_address", "data_type": "TEXT",
             "sample_values": ["12 Elm St", "5 Pine Rd"]},
        ]},
        {"table_name": "foods", "columns": [
            {"column_name": "food_id", "data_type": "INTEGER",
             "is_primary_key_candidate": True, "sample_values": [1, 2]},
            {"column_name": "species_target", "data_type": "TEXT",
             "sample_values": ["dog", "cat"]},
        ]},
        {"table_name": "pet_likes", "columns": [
            {"column_name": "pet_id", "data_type": "INTEGER", "sample_values": [1]},
            {"column_name": "active", "data_type": "TEXT",
             "sample_values": ["yes", "no"]},
            {"column_name": "allergy_note", "data_type": "TEXT",
             "sample_values": ["none", "peanut"]},
        ]},
    ]
}
IDX = build_column_index(GRAPH)
ALL_TABLES = ["owners", "pets", "foods", "pet_likes"]


# ---------------------------------------------------------------------------
# Unit level: resolve_column_comparisons
# ---------------------------------------------------------------------------
def test_dotted_rhs_becomes_value_ref():
    out = resolve_column_comparisons(
        [{"table": "owners", "column": "street_address", "op": "!=",
          "value": "pets.pet_address"}], IDX, ALL_TABLES)
    assert "value" not in out[0], out[0]
    assert out[0]["value_ref"] == {"table": "pets", "column": "pet_address"}, out[0]
    print("[1] dotted RHS 'pets.pet_address' -> value_ref -> OK")


def test_bare_rhs_unambiguous_becomes_value_ref():
    # 'species_target' exists only in foods -> unambiguous.
    out = resolve_column_comparisons(
        [{"table": "pets", "column": "species", "op": "=",
          "value": "species_target"}], IDX, ALL_TABLES)
    assert out[0].get("value_ref") == {"table": "foods", "column": "species_target"}, out[0]
    print("[2] bare unambiguous RHS 'species_target' -> value_ref -> OK")


def test_literal_city_stays_parameter():
    out = resolve_column_comparisons(
        [{"table": "owners", "column": "city", "op": "=", "value": "Moscow"}],
        IDX, ALL_TABLES)
    assert out[0].get("value") == "Moscow" and "value_ref" not in out[0], out[0]
    print("[3] literal 'Moscow' (a sample value) stays a parameter -> OK")


def test_literal_state_and_boolean_stay_parameters():
    for tbl, col, val in [("owners", "state", "Idaho"),
                          ("pet_likes", "active", "yes"),
                          ("pet_likes", "allergy_note", "none")]:
        out = resolve_column_comparisons(
            [{"table": tbl, "column": col, "op": "=", "value": val}], IDX, ALL_TABLES)
        assert "value_ref" not in out[0] and out[0]["value"] == val, (val, out[0])
    print("[4] 'Idaho'/'yes'/'none' literals stay parameters -> OK")


def test_excluded_ops_unchanged():
    cases = [
        {"table": "owners", "column": "city", "op": "LIKE", "value": "species"},
        {"table": "owners", "column": "city", "op": "IN", "value": ["species"]},
        {"table": "pets", "column": "pet_address", "op": "IS NULL"},
    ]
    for f in cases:
        out = resolve_column_comparisons([dict(f)], IDX, ALL_TABLES)
        assert "value_ref" not in out[0], out[0]
    print("[5] LIKE / IN / IS NULL never converted -> OK")


def test_existing_value_ref_not_overwritten():
    f = {"table": "owners", "column": "street_address", "op": "=",
         "value_ref": {"table": "pets", "column": "pet_address"}}
    out = resolve_column_comparisons([dict(f)], IDX, ALL_TABLES)
    assert out[0]["value_ref"] == {"table": "pets", "column": "pet_address"}, out[0]
    print("[6] existing value_ref preserved -> OK")


def test_unknown_rhs_column_stays_parameter():
    out = resolve_column_comparisons(
        [{"table": "owners", "column": "city", "op": "=", "value": "not_a_column"}],
        IDX, ALL_TABLES)
    assert "value_ref" not in out[0], out[0]
    print("[7] RHS that is not a real column stays a parameter -> OK")


# ---------------------------------------------------------------------------
# End-to-end: build_from_extraction -> generate_sql
# ---------------------------------------------------------------------------
def _plan(ir, from_table, joins=None):
    return {"resolved": True, "from_table": from_table, "joins": joins or [],
            "bridge_tables": [], "ir": ir}


def test_e2e_q2_style_column_comparison_no_param():
    # Q2-style: owners.street_address <> pets.pet_address
    extraction = {
        "tables": ["owners", "pets"],
        "select": [{"table": "owners", "column": "owner_id"}],
        "filters": [{"table": "owners", "column": "street_address", "op": "<>",
                     "value": "pets.pet_address"}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    out = sql_to_dict(generate_sql(_plan(
        ir, "owners",
        [{"join_type": "inner", "from_table": "owners", "from_column": "owner_id",
          "to_table": "pets", "to_column": "owner_id"}])))
    assert out["generated"], out
    assert '"owners"."street_address" != "pets"."pet_address"' in out["sql"], out["sql"]
    assert out["params"] == [], out["params"]
    print("[8] e2e Q2-style: column comparison rendered, no '?' param -> OK")


def test_e2e_q4_style_column_comparison_no_param():
    # Q4/Q6-style: foods.species_target = pets.species
    extraction = {
        "tables": ["foods", "pets"],
        "select": [{"table": "foods", "column": "food_id"}],
        "filters": [{"table": "foods", "column": "species_target", "op": "=",
                     "value": "pets.species"}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    out = sql_to_dict(generate_sql(_plan(
        ir, "foods",
        [{"join_type": "inner", "from_table": "pets", "from_column": "pet_id",
          "to_table": "foods", "to_column": "food_id"}])))
    assert out["generated"], out
    assert '"foods"."species_target" = "pets"."species"' in out["sql"], out["sql"]
    assert out["params"] == [], out["params"]
    print("[9] e2e Q4-style: column comparison rendered, no '?' param -> OK")


def test_e2e_literal_still_parameterized():
    extraction = {
        "tables": ["owners"],
        "select": [{"table": "owners", "column": "owner_id"}],
        "filters": [{"table": "owners", "column": "city", "op": "=", "value": "Moscow"}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir, "owners")))
    assert out["generated"], out
    assert "?" in out["sql"] and "Moscow" in out["params"], out
    print("[10] e2e literal city stays parameterized -> OK")


def main():
    tests = [
        test_dotted_rhs_becomes_value_ref,
        test_bare_rhs_unambiguous_becomes_value_ref,
        test_literal_city_stays_parameter,
        test_literal_state_and_boolean_stay_parameters,
        test_excluded_ops_unchanged,
        test_existing_value_ref_not_overwritten,
        test_unknown_rhs_column_stays_parameter,
        test_e2e_q2_style_column_comparison_no_param,
        test_e2e_q4_style_column_comparison_no_param,
        test_e2e_literal_still_parameterized,
    ]
    passed = 0
    for t in tests:
        t(); passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed -- column comparison verified")


if __name__ == "__main__":
    main()
