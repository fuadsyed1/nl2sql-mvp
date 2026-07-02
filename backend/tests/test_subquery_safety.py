"""
test_subquery_safety.py

Unit tests for the post-Stage-7 generic root-cause fixes:
  (#2) unsafe subquery aliasing — a repeated table inside an existence subquery
       is never re-joined; its ON equality is folded into the subquery WHERE.
  (#3) value_ref dict leakage — a filter whose value is a column-ref dict is
       promoted to value_ref before rendering; a final guard declines if any
       non-scalar parameter would reach the binder.

No database, no model.

Run:  python -m tests.test_subquery_safety
"""

from semantic.ir_builder import build_from_extraction
from semantic.ir_normalizer import promote_dict_value_refs
from generation.sql_clauses import render_anti_exists
from generation.multitable_sql_generator import generate_sql
from generation.sql_types import to_dict as sql_to_dict


GRAPH = {
    "tables": [
        {"table_name": "owners", "columns": [
            {"column_name": "owner_id"}, {"column_name": "owner_name"}]},
        {"table_name": "pets", "columns": [
            {"column_name": "pet_id"}, {"column_name": "owner_id"},
            {"column_name": "species"}, {"column_name": "adoption_date"}]},
        {"table_name": "foods", "columns": [
            {"column_name": "food_id"}, {"column_name": "species_target"},
            {"column_name": "brand"}]},
        {"table_name": "purchases", "columns": [
            {"column_name": "purchase_id"}, {"column_name": "owner_id"},
            {"column_name": "food_id"}, {"column_name": "purchase_date"}]},
        {"table_name": "feeding_history", "columns": [
            {"column_name": "feed_id"}, {"column_name": "pet_id"},
            {"column_name": "food_id"}, {"column_name": "feed_date"}]},
    ]
}


def _plan(ir, from_table="foods", joins=None):
    return {"resolved": True, "from_table": from_table, "joins": joins or [],
            "bridge_tables": [], "ir": ir}


# ---------------------------------------------------------------------------
# #2 subquery aliasing safety
# ---------------------------------------------------------------------------
def test_duplicate_target_join_is_folded_not_rejoined():
    # joins target the SAME table as FROM (pets); must NOT emit FROM pets JOIN pets.
    clauses, params = render_anti_exists([{
        "target_table": "pets",
        "joins": [
            {"from_table": "purchases", "from_column": "owner_id",
             "to_table": "pets", "to_column": "owner_id"},
            {"from_table": "foods", "from_column": "species_target",
             "to_table": "pets", "to_column": "species"},
        ],
        "where": [],
    }])
    sql = clauses[0]
    assert sql.count('"pets"') >= 1, sql
    assert "JOIN" not in sql, sql                      # both dup joins folded
    assert '"purchases"."owner_id" = "pets"."owner_id"' in sql, sql
    assert '"foods"."species_target" = "pets"."species"' in sql, sql
    print("[1] duplicate joins to FROM table folded into WHERE (no re-join) -> OK")


def test_distinct_target_join_kept():
    clauses, _ = render_anti_exists([{
        "target_table": "feeding_history",
        "joins": [{"from_table": "feeding_history", "from_column": "food_id",
                   "to_table": "foods", "to_column": "food_id"}],
        "where": [{"left": {"table": "feeding_history", "column": "pet_id"},
                   "op": "=", "right": {"table": "pets", "column": "pet_id"}}],
    }])
    assert 'INNER JOIN "foods" ON "feeding_history"."food_id" = "foods"."food_id"' in clauses[0], clauses[0]
    print("[2] a genuinely distinct join is still emitted -> OK")


def test_repeated_distinct_table_only_joined_once():
    # Two joins both bringing in 'foods' -> join once, fold the second.
    clauses, _ = render_anti_exists([{
        "target_table": "feeding_history",
        "joins": [
            {"from_table": "feeding_history", "from_column": "food_id",
             "to_table": "foods", "to_column": "food_id"},
            {"from_table": "purchases", "from_column": "food_id",
             "to_table": "foods", "to_column": "food_id"},
        ],
        "where": [],
    }])
    assert clauses[0].count('JOIN "foods"') == 1, clauses[0]
    assert '"purchases"."food_id" = "foods"."food_id"' in clauses[0], clauses[0]
    print("[3] repeated join to same non-target table done once, rest folded -> OK")


# ---------------------------------------------------------------------------
# #3 value_ref dict leakage
# ---------------------------------------------------------------------------
def test_promote_dict_value_unit():
    out = promote_dict_value_refs([
        {"table": "purchases", "column": "purchase_date", "op": ">",
         "value": {"table": "pets", "column": "adoption_date"}},
    ])
    assert "value" not in out[0], out[0]
    assert out[0]["value_ref"] == {"table": "pets", "column": "adoption_date"}, out[0]
    print("[4] dict value promoted to value_ref (unit) -> OK")


def test_e2e_date_dict_becomes_column_comparison():
    extraction = {
        "tables": ["purchases", "pets"],
        "select": [{"table": "pets", "column": "pet_id"}],
        "filters": [{"table": "purchases", "column": "purchase_date", "op": ">",
                     "value": {"table": "pets", "column": "adoption_date"}}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    out = sql_to_dict(generate_sql(_plan(
        ir, "purchases",
        [{"join_type": "inner", "from_table": "purchases", "from_column": "owner_id",
          "to_table": "pets", "to_column": "owner_id"}])))
    assert out["generated"], out
    assert '"purchases"."purchase_date" > "pets"."adoption_date"' in out["sql"], out["sql"]
    assert out["params"] == [], out["params"]            # no dict bound as a param
    print("[5] e2e date-vs-date dict value -> column comparison, no param -> OK")


def test_guard_declines_non_scalar_param():
    # A value_ref-free dict value that the normalizer can't promote (no column)
    # must NOT reach the binder; the guard declines.
    extraction = {
        "tables": ["pets"],
        "select": [{"table": "pets", "column": "pet_id"}],
        "filters": [{"table": "pets", "column": "species", "op": "=",
                     "value": {"weird": "shape"}}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir, "pets")))
    assert not out["generated"], out
    assert out.get("failure_reason") == "non_scalar_parameter" or \
        out.get("reason") == "non_scalar_parameter", out
    print("[6] final guard declines a non-scalar parameter (no crash) -> OK")


def test_normal_scalar_unaffected():
    extraction = {
        "tables": ["pets"],
        "select": [{"table": "pets", "column": "pet_id"}],
        "filters": [{"table": "pets", "column": "species", "op": "=", "value": "dog"}],
    }
    ir = build_from_extraction(1, extraction, GRAPH)
    out = sql_to_dict(generate_sql(_plan(ir, "pets")))
    assert out["generated"] and out["params"] == ["dog"], out
    print("[7] normal scalar parameter unaffected -> OK")


def main():
    tests = [
        test_duplicate_target_join_is_folded_not_rejoined,
        test_distinct_target_join_kept,
        test_repeated_distinct_table_only_joined_once,
        test_promote_dict_value_unit,
        test_e2e_date_dict_becomes_column_comparison,
        test_guard_declines_non_scalar_param,
        test_normal_scalar_unaffected,
    ]
    passed = 0
    for t in tests:
        t(); passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed -- subquery safety verified")


if __name__ == "__main__":
    main()
