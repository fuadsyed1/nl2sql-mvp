"""
test_ir_normalizer.py

Unit tests for the deterministic IR normalizations (year/date filters, GROUP BY
label in SELECT, stored-value casing/booleans) plus an end-to-end check through
build_from_extraction -> generate_sql. No database, no model.

Run:  python -m tests.test_ir_normalizer
"""

from semantic.ir_normalizer import (
    build_column_index,
    expand_year_filters,
    ensure_group_by_in_select,
    normalize_string_values,
    normalize_ir,
)
from semantic.ir_builder import build_from_extraction
from generation.multitable_sql_generator import generate_sql
from generation.sql_types import to_dict as sql_to_dict


GRAPH = {
    "tables": [
        {"table_name": "purchases", "columns": [
            {"column_name": "purchase_id", "data_type": "INTEGER",
             "is_primary_key_candidate": True, "sample_values": [1, 2, 3]},
            {"column_name": "quantity", "data_type": "INTEGER",
             "sample_values": [4, 2, 7]},
            {"column_name": "purchase_date", "data_type": "TEXT",
             "sample_values": ["2025-11-23", "2026-01-02"]},
        ]},
        {"table_name": "menu_items", "columns": [
            {"column_name": "is_vegetarian", "data_type": "TEXT",
             "sample_values": ["yes", "no"]},
            {"column_name": "category", "data_type": "TEXT",
             "sample_values": ["dessert", "drink", "main", "side"]},
            {"column_name": "item_name", "data_type": "TEXT",
             "sample_values": ["Salad1", "Curry2"]},
        ]},
        {"table_name": "patients", "columns": [
            {"column_name": "city", "data_type": "TEXT",
             "sample_values": ["Seattle", "Boston"]},
        ]},
    ]
}
IDX = build_column_index(GRAPH)


def test_year_filter_expands_to_range():
    out = expand_year_filters(
        [{"table": "purchases", "column": "purchase_date", "op": "=", "value": "2026"}], IDX)
    assert len(out) == 2, out
    assert out[0]["op"] == ">=" and out[0]["value"] == "2026-01-01", out[0]
    assert out[1]["op"] == "<" and out[1]["value"] == "2027-01-01", out[1]
    print("[1] year '=' filter -> half-open date range -> OK")


def test_empty_op_year_also_expands():
    out = expand_year_filters(
        [{"table": "purchases", "column": "purchase_date", "op": "", "value": "2026"}], IDX)
    assert len(out) == 2 and out[0]["op"] == ">=" and out[1]["op"] == "<"
    print("[2] empty-op year filter (the `col ?` bug) -> range -> OK")


def test_empty_op_nonyear_defaults_equals():
    out = expand_year_filters(
        [{"table": "menu_items", "column": "category", "op": "", "value": "dessert"}], IDX)
    assert len(out) == 1 and out[0]["op"] == "=", out
    print("[3] empty/unknown operator repaired to '=' (never `col ?`) -> OK")


def _assert_range(out, year):
    assert len(out) == 2, out
    assert out[0]["op"] == ">=" and out[0]["value"] == f"{year}-01-01", out[0]
    assert out[1]["op"] == "<" and out[1]["value"] == f"{year + 1}-01-01", out[1]


def test_full_date_value_collapses():
    out = expand_year_filters(
        [{"table": "purchases", "column": "purchase_date", "op": "=",
          "value": "2025-06-15"}], IDX)
    _assert_range(out, 2025)
    print("[3a] full-date value -> year range -> OK")


def test_two_equality_filters_same_year_collapse():
    out = expand_year_filters([
        {"table": "purchases", "column": "purchase_date", "op": "=", "value": "2025-01-01"},
        {"table": "purchases", "column": "purchase_date", "op": "=", "value": "2025-12-31"},
    ], IDX)
    _assert_range(out, 2025)
    print("[3b] two equality filters, same year -> single range -> OK")


def test_like_year_pattern_collapses():
    out = expand_year_filters(
        [{"table": "purchases", "column": "purchase_date", "op": "LIKE",
          "value": "2026%"}], IDX)
    _assert_range(out, 2026)
    print("[3c] LIKE 'YYYY%' -> year range -> OK")


def test_correct_range_left_unchanged():
    rng = [
        {"table": "purchases", "column": "purchase_date", "op": ">=",
         "value": "2025-01-01", "connector": "AND"},
        {"table": "purchases", "column": "purchase_date", "op": "<",
         "value": "2026-01-01"},
    ]
    out = expand_year_filters(rng, IDX)
    assert out == rng, out
    # a single open-ended >= is also preserved
    open_end = [{"table": "purchases", "column": "purchase_date", "op": ">=",
                 "value": "2025-01-01"}]
    assert expand_year_filters(open_end, IDX) == open_end
    print("[3d] already-correct >=/< range (and open-ended >=) unchanged -> OK")


def test_group_by_added_to_select():
    sel = ensure_group_by_in_select([], [{"table": "patients", "column": "city"}])
    assert sel == [{"table": "patients", "column": "city"}], sel
    # already present -> not duplicated
    sel2 = ensure_group_by_in_select(
        [{"table": "patients", "column": "city"}],
        [{"table": "patients", "column": "city"}])
    assert len(sel2) == 1, sel2
    print("[4] GROUP BY column prepended to SELECT (no dup) -> OK")


def test_boolean_value_maps_to_stored():
    for raw, want in [(True, "yes"), (1, "yes"), ("true", "yes"),
                      (False, "no"), (0, "no"), ("no", "no")]:
        out = normalize_string_values(
            [{"table": "menu_items", "column": "is_vegetarian", "op": "=", "value": raw}], IDX)
        assert out[0]["value"] == want, (raw, out[0]["value"])
    print("[5] boolean synonyms map to stored yes/no via samples -> OK")


def test_categorical_casefold_and_safety():
    out = normalize_string_values(
        [{"table": "menu_items", "column": "category", "op": "=", "value": "Dessert"}], IDX)
    assert out[0]["value"] == "dessert", out[0]
    # high-cardinality / unknown value left untouched
    out2 = normalize_string_values(
        [{"table": "menu_items", "column": "item_name", "op": "=", "value": "Burger9"}], IDX)
    assert out2[0]["value"] == "Burger9", out2
    print("[6] categorical case-fold; unknown high-cardinality value untouched -> OK")


def _plan(ir, from_table, joins=None):
    return {"resolved": True, "from_table": from_table, "joins": joins or [],
            "bridge_tables": [], "ir": ir}


def test_end_to_end_generates_correct_sql():
    extraction = {
        "tables": ["purchases"],
        "select": [],
        "aggregations": [{"table": "purchases", "column": "purchase_id",
                          "function": "count", "alias": "n"}],
        "group_by": [],
        "filters": [
            {"table": "purchases", "column": "purchase_date", "op": "=", "value": "2026"},
        ],
    }
    ir = build_from_extraction(2, extraction, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir, "purchases")))
    assert out["generated"], out
    assert ">=" in out["sql"] and "<" in out["sql"], out["sql"]
    assert "2026-01-01" in out["params"] and "2027-01-01" in out["params"], out["params"]
    print("[7] end-to-end: year filter -> ranged WHERE with date params -> OK")


def test_end_to_end_group_by_label_and_boolean():
    extraction = {
        "tables": ["menu_items"],
        "select": [],
        "aggregations": [{"table": "menu_items", "column": "menu_item_id",
                          "function": "count", "alias": "n"}],
        "group_by": [{"table": "menu_items", "column": "category"}],
        "filters": [
            {"table": "menu_items", "column": "is_vegetarian", "op": "=", "value": True},
        ],
    }
    ir = build_from_extraction(6, extraction, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir, "menu_items")))
    assert out["generated"], out
    assert '"menu_items"."category"' in out["sql"], "group-by label missing from SELECT: " + out["sql"]
    assert "yes" in out["params"], out["params"]
    print("[8] end-to-end: GROUP BY label in SELECT + boolean 'yes' param -> OK")


def main():
    tests = [
        test_year_filter_expands_to_range,
        test_empty_op_year_also_expands,
        test_empty_op_nonyear_defaults_equals,
        test_full_date_value_collapses,
        test_two_equality_filters_same_year_collapse,
        test_like_year_pattern_collapses,
        test_correct_range_left_unchanged,
        test_group_by_added_to_select,
        test_boolean_value_maps_to_stored,
        test_categorical_casefold_and_safety,
        test_end_to_end_generates_correct_sql,
        test_end_to_end_group_by_label_and_boolean,
    ]
    passed = 0
    for t in tests:
        t(); passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed -- ir_normalizer.py verified")


if __name__ == "__main__":
    main()
