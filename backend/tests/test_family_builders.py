"""
test_family_builders.py

Builder-output tests for the six implemented query families. Each builder turns
(question, schema index) into an extraction dict; we assert the key structural
slots resolved correctly from schema metadata (no hardcoded names in the
implementation). Pure — no SQL generation, no model.

Run:  python -m tests.test_family_builders
"""

from query_families.builders import build_family
from query_families import family_types as ft
from query_families import slot_extractor as se
from tests.test_query_family_router import GRAPH, _col


IDX = se.index_schema(GRAPH)


def _cols(entries):
    return {(e.get("table"), e.get("column")) for e in entries}


def test_min_max_builder_slots():
    q = ("Find food types where the same owner both purchased the cheapest and "
         "the most expensive food of that type.")
    ex = build_family(ft.MIN_MAX_SAME_ENTITY_PER_GROUP, q, IDX)
    assert ex is not None, "builder returned None"
    names = [r["name"] for r in ex["derived_relations"]]
    assert names == ["base_items", "group_extremes"], names
    base = ex["derived_relations"][0]
    # entity=owners.owner_id, group=foods.food_type, value=foods.price
    assert base["from_table"] == "owners", base
    assert _cols(base["select"]) == {("owners", "owner_id"), ("foods", "food_type"),
                                     ("foods", "price")}, base["select"]
    assert base["joins"][0]["to_table"] == "purchases", base["joins"]
    assert base["joins"][-1]["to_table"] == "foods", base["joins"]
    assert {a["alias"] for a in ex["aliases"]} == {"low", "high", "g"}
    assert ex["distinct"] is True
    print("[1] min_max builder resolved entity/group/value + base path -> OK")


def _pairs(joins):
    return {(j["from_table"], j["from_column"], j["to_table"], j["to_column"]) for j in joins}


# A schema where feeding_history is listed BEFORE purchases, so a plain
# shortest-path BFS would wrongly pick owners->feeding_history->foods.
_ACTION_GRAPH = {
    "tables": [
        {"table_name": "owners", "columns": [
            _col("owner_id", "INTEGER", True), _col("owner_name")]},
        {"table_name": "foods", "columns": [
            _col("food_id", "INTEGER", True), _col("food_type"), _col("price", "REAL")]},
        {"table_name": "feeding_history", "columns": [
            _col("feed_id", "INTEGER", True), _col("owner_id", "INTEGER"),
            _col("food_id", "INTEGER")]},
        {"table_name": "purchases", "columns": [
            _col("purchase_id", "INTEGER", True), _col("owner_id", "INTEGER"),
            _col("food_id", "INTEGER")]},
    ],
    "relationships": [
        {"from_table": "feeding_history", "from_column": "owner_id", "to_table": "owners", "to_column": "owner_id"},
        {"from_table": "feeding_history", "from_column": "food_id", "to_table": "foods", "to_column": "food_id"},
        {"from_table": "purchases", "from_column": "owner_id", "to_table": "owners", "to_column": "owner_id"},
        {"from_table": "purchases", "from_column": "food_id", "to_table": "foods", "to_column": "food_id"},
    ],
}
_ACTION_IDX = se.index_schema(_ACTION_GRAPH)


def test_min_max_prefers_purchased_path():
    q = ("Find food types where the same owner both purchased the cheapest and "
         "the most expensive food of that type.")
    ex = build_family(ft.MIN_MAX_SAME_ENTITY_PER_GROUP, q, _ACTION_IDX)
    assert ex is not None
    joins = ex["derived_relations"][0]["joins"]
    assert ("owners", "owner_id", "purchases", "owner_id") in _pairs(joins), joins
    assert ("purchases", "food_id", "foods", "food_id") in _pairs(joins), joins
    assert not any(j["to_table"] == "feeding_history" for j in joins), joins
    print("[1b] min_max 'purchased' -> owners->purchases->foods (not feeding) -> OK")


def test_min_max_prefers_fed_path():
    q = ("Find food types where the same owner both fed the cheapest and the "
         "most expensive food of that type.")
    ex = build_family(ft.MIN_MAX_SAME_ENTITY_PER_GROUP, q, _ACTION_IDX)
    assert ex is not None
    joins = ex["derived_relations"][0]["joins"]
    assert ("owners", "owner_id", "feeding_history", "owner_id") in _pairs(joins), joins
    assert ("feeding_history", "food_id", "foods", "food_id") in _pairs(joins), joins
    assert not any(j["to_table"] == "purchases" for j in joins), joins
    print("[1c] min_max 'fed' -> owners->feeding_history->foods (not purchases) -> OK")


def test_derived_aggregate_builder_slots():
    q = "List owners who bought the highest total quantity of food for each city."
    ex = build_family(ft.DERIVED_AGGREGATE_CTE, q, IDX)
    assert ex is not None
    cte = ex["derived_relations"][0]
    assert ex["main_from"] == cte["name"], ex
    agg = cte["aggregations"][0]
    assert agg["function"] == "SUM" and (agg["table"], agg["column"]) == ("purchases", "quantity"), agg
    assert _cols(cte["group_by"]) >= {("owners", "owner_id")}, cte["group_by"]
    assert ex["top_per_group"][0]["order_by"]["direction"] == "desc", ex["top_per_group"]
    print("[2] derived_aggregate builder: SUM(purchases.quantity) per city + top ties -> OK")


def test_count_distinct_comparison_builder():
    q = "Find owners whose pets consumed foods from more brands than the owner purchased."
    ex = build_family(ft.COUNT_DISTINCT_COMPARISON, q, IDX)
    assert ex is not None
    assert len(ex["derived_relations"]) == 2, ex["derived_relations"]
    for cte in ex["derived_relations"]:
        agg = cte["aggregations"][0]
        assert agg["function"] == "COUNT" and agg.get("distinct") is True, agg
        assert (agg["table"], agg["column"]) == ("foods", "brand"), agg
    assert ex["explicit_joins"][0]["join_type"] == "inner"
    assert ex["filters"][0].get("value_ref"), ex["filters"]
    print("[3] count_distinct_comparison: two COUNT(DISTINCT brand) CTEs joined -> OK")


def test_self_join_pair_builder():
    q = "List pairs of pets owned by the same owner where both love the same flavor."
    ex = build_family(ft.SELF_JOIN_PAIR, q, IDX)
    assert ex is not None
    base_aliases = [a for a in ex["aliases"] if a["table"] == "pets"]
    assert {a["alias"] for a in base_aliases} == {"p1", "p2"}, ex["aliases"]
    # same-owner equality join + a "<" dedup guard on the pair key
    ops = [(j["from"].get("column"), j["op"]) for j in ex["alias_joins"]]
    assert ("owner_id", "=") in ops, ops
    assert any(op == "<" for _, op in ops), ops
    # same-flavor comparison lives on the related pet_likes copies
    assert any(f["left"].get("column") == "flavor" for f in ex["alias_filters"]), ex["alias_filters"]
    print("[4] self_join_pair: p1/p2 + same-owner join + '<' guard + flavor filter -> OK")


def test_outer_join_null_builder():
    q = "List owners and pets using an outer join so owners without pets are still visible."
    ex = build_family(ft.OUTER_JOIN_NULL, q, IDX)
    assert ex is not None
    ej = ex["explicit_joins"][0]
    assert ej["join_type"] == "left" and ej["from_table"] == "owners" and ej["to_table"] == "pets", ej
    print("[5] outer_join_null: owners LEFT JOIN pets -> OK")


def test_anti_exists_builder():
    q = "List foods never purchased."
    ex = build_family(ft.ANTI_EXISTS, q, IDX)
    assert ex is not None
    ax = ex["anti_exists"][0]
    assert ax["target_table"] == "purchases", ax
    w = ax["where"][0]
    assert w["left"]["table"] == "purchases" and w["right"]["table"] == "foods", w
    print("[6] anti_exists: foods never purchased -> NOT EXISTS purchases -> OK")


def test_top_per_group_builder():
    q = "List the highest priced food for each brand."
    ex = build_family(ft.TOP_PER_GROUP, q, IDX)
    assert ex is not None
    tpg = ex["top_per_group"][0]
    assert tpg["table"] == "foods", tpg
    assert (tpg["order_by"]["table"], tpg["order_by"]["column"]) == ("foods", "price"), tpg
    assert tpg["order_by"]["direction"] == "desc" and tpg["rank"] == 1, tpg
    assert _cols(tpg["partition_by"]) == {("foods", "brand")}, tpg
    print("[7] top_per_group: highest price per brand -> OK")


def test_latest_earliest_builder():
    q = "List pets whose latest feeding was not vet approved."
    ex = build_family(ft.LATEST_EARLIEST_PER_ENTITY, q, IDX)
    assert ex is not None
    tpg = ex["top_per_group"][0]
    assert tpg["table"] == "feeding_history", tpg
    ob = tpg["order_by"]
    assert (ob["table"], ob["column"]) == ("feeding_history", "feed_date"), ob
    assert ob["direction"] == "desc", ob                       # latest
    assert _cols(tpg["partition_by"]) == {("feeding_history", "pet_id")}, tpg
    print("[8] latest_earliest: latest feeding per pet (date column) -> OK")


def test_mismatch_builder():
    q = "Find owners who bought food for a species they do not own."
    ex = build_family(ft.MISMATCH_COMPARISON, q, IDX)
    assert ex is not None
    f = ex["filters"][0]
    assert f["op"] == "!=", f
    assert (f["table"], f["column"]) == ("foods", "species_target"), f
    assert f["value_ref"] == {"table": "pets", "column": "species"}, f
    print("[9] mismatch: foods.species_target != pets.species (value_ref) -> OK")


def test_universal_builder():
    q = ("Find owners where every pet they own has been fed at least one food "
         "matching that pet's species.")
    ex = build_family(ft.UNIVERSAL_EVERY_ALL, q, IDX)
    assert ex is not None
    u = ex["universal"][0]
    assert u["domain_table"] == "pets", u
    assert u["domain_filters"][0]["left"]["table"] == "pets", u
    me = u["must_exist"]
    assert me["target_table"] == "feeding_history", me
    # the species match must appear inside must_exist
    matches = [w for w in me["where"] if isinstance(w.get("right"), dict)
               and w["right"].get("table") == "pets" and w["right"].get("column") == "species"]
    assert matches, me
    print("[10] universal: every pet fed matching-species food -> double NOT EXISTS -> OK")


def test_set_division_builder():
    q = "Find brands that have food for all species represented in pets."
    ex = build_family(ft.SET_DIVISION_COUNT_DISTINCT, q, IDX)
    assert ex is not None
    sd = ex["set_division"][0]
    assert _cols(sd["group_by"]) == {("foods", "brand")}, sd
    assert sd["left"]["function"] == "COUNT" and sd["left"].get("distinct") is True
    assert (sd["left"]["table"], sd["left"]["column"]) == ("foods", "species_target"), sd
    rs = sd["right_subquery"]
    assert (rs["table"], rs["column"]) == ("pets", "species") and rs.get("distinct") is True, rs
    print("[11] set_division: brands covering all pet species -> OK")


def test_normal_family_returns_none():
    assert build_family(ft.NORMAL_JOIN_FILTER_GROUP, "Show all rows from owners", IDX) is None
    print("[12] normal_join_filter_group builder returns None (LLM fallback) -> OK")


def test_self_join_no_duplicate_alias():
    from tests.test_family_guard import CLINIC
    cidx = se.index_schema(CLINIC)
    q = ("pairs of patients in the same city who saw the same doctor on different "
         "appointment dates.")
    ex = build_family(ft.SELF_JOIN_PAIR, q, cidx)
    assert ex is not None, ex
    names = [a["alias"] for a in ex["aliases"]]
    assert len(names) == len(set(names)), names            # no duplicate alias
    assert names.count("l1_appointments") == 1, names      # related table joined once
    print("[13] self_join dedups related-table aliases (Q09) -> OK")


def test_count_distinct_two_concepts():
    from tests.test_family_guard import CYBER_TRAIN
    cidx = se.index_schema(CYBER_TRAIN)
    q = ("employees whose devices triggered more distinct alert types than the "
         "number of distinct courses they passed.")
    ex = build_family(ft.COUNT_DISTINCT_COMPARISON, q, cidx)
    assert ex is not None, ex
    aggs = [(a["table"], a["column"]) for r in ex["derived_relations"]
            for a in r["aggregations"] if a.get("distinct")]
    assert ("alerts", "alert_type") in aggs and ("training_records", "course_name") in aggs, aggs
    # no table joined twice inside a CTE
    for r in ex["derived_relations"]:
        tos = [j["to_table"] for j in r["joins"]]
        assert len(tos) == len(set(tos)), r["joins"]
    print("[14] count_distinct counts two DIFFERENT concepts, no dup table -> OK")


def main():
    tests = [
        test_min_max_builder_slots,
        test_min_max_prefers_purchased_path,
        test_min_max_prefers_fed_path,
        test_derived_aggregate_builder_slots,
        test_count_distinct_comparison_builder,
        test_self_join_pair_builder,
        test_outer_join_null_builder,
        test_anti_exists_builder,
        test_top_per_group_builder,
        test_latest_earliest_builder,
        test_mismatch_builder,
        test_universal_builder,
        test_set_division_builder,
        test_normal_family_returns_none,
        test_self_join_no_duplicate_alias,
        test_count_distinct_two_concepts,
    ]
    passed = 0
    for t in tests:
        t(); passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed -- family builders verified")


if __name__ == "__main__":
    main()
