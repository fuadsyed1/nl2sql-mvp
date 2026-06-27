"""
test_plan_postprocess.py

Unit tests for the Tier-2 LEFT JOIN rewrite ("each/all/every X with count of Y").
No database, no model. Run:  python -m tests.test_plan_postprocess
"""

from planning.plan_postprocess import apply_left_join_for_each


def js(ft, fc, tt, tc):
    return {"from_table": ft, "from_column": fc, "to_table": tt, "to_column": tc,
            "join_type": "inner"}


def plan(from_table, joins, group_by, aggregations):
    return {"resolved": True, "from_table": from_table, "joins": joins,
            "ir": {"group_by": group_by, "aggregations": aggregations}}


def test_direct_each_becomes_left():
    p = plan(
        "owners",
        [js("owners", "owner_id", "pets", "owner_id")],
        [{"table": "owners", "column": "owner_id"}],
        [{"table": "pets", "function": "COUNT", "column": "pet_id", "alias": "pet_count"}],
    )
    apply_left_join_for_each("Show each owner with count of pets.", p)
    assert p["joins"][0]["join_type"] == "left", p["joins"]
    print("[1] 'each owner with count of pets' -> owners->pets LEFT JOIN -> OK")


def test_no_each_stays_inner():
    p = plan(
        "owners",
        [js("owners", "owner_id", "pets", "owner_id")],
        [{"table": "owners", "column": "owner_id"}],
        [{"table": "pets", "function": "COUNT", "column": "pet_id", "alias": "pet_count"}],
    )
    apply_left_join_for_each("Show owners and their pets.", p)
    assert p["joins"][0]["join_type"] == "inner", p["joins"]
    print("[2] no each/all wording -> stays INNER JOIN -> OK")


def test_each_without_count_stays_inner():
    p = plan(
        "owners",
        [js("owners", "owner_id", "pets", "owner_id")],
        [{"table": "owners", "column": "owner_id"}],
        [],  # no COUNT aggregation
    )
    apply_left_join_for_each("Show each owner and their pets.", p)
    assert p["joins"][0]["join_type"] == "inner", p["joins"]
    print("[3] each/all but no COUNT aggregation -> stays INNER JOIN -> OK")


def test_bridge_all_joins_left():
    p = plan(
        "customers",
        [js("customers", "customer_id", "orders", "customer_id"),
         js("orders", "order_id", "order_items", "order_id")],
        [{"table": "customers", "column": "customer_id"}],
        [{"table": "order_items", "function": "COUNT", "column": "order_item_id", "alias": "n"}],
    )
    apply_left_join_for_each("List every customer with the number of order_items.", p)
    assert [j["join_type"] for j in p["joins"]] == ["left", "left"], p["joins"]
    print("[4] bridge X->Z->Y -> both joins LEFT -> OK")


def test_root_not_group_by_entity_unchanged():
    # If the root is not the group_by entity, do not alter (LEFT could be wrong).
    p = plan(
        "pets",
        [js("pets", "owner_id", "owners", "owner_id")],
        [{"table": "owners", "column": "owner_id"}],
        [{"table": "pets", "function": "COUNT", "column": "pet_id", "alias": "n"}],
    )
    apply_left_join_for_each("Show each owner with count of pets.", p)
    assert p["joins"][0]["join_type"] == "inner", p["joins"]
    print("[5] root != group_by entity -> unchanged -> OK")


def main():
    tests = [
        test_direct_each_becomes_left,
        test_no_each_stays_inner,
        test_each_without_count_stays_inner,
        test_bridge_all_joins_left,
        test_root_not_group_by_entity_unchanged,
    ]
    passed = 0
    for t in tests:
        t(); passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed -- plan_postprocess.py verified")


if __name__ == "__main__":
    main()
