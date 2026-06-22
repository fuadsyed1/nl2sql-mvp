"""
test_sql_clauses.py — offline test for Phase 7 step 2 (sql_clauses.py).

Runnable as a plain script (no server, no LLM, no SQL execution, no pytest):

    python test_sql_clauses.py
"""

from sql_clauses import (
    quote_qualified,
    render_select,
    render_from_joins,
    render_where,
    render_group_by,
    render_having,
    render_order_by,
    render_limit,
)


def test_identifier_quoting():
    assert quote_qualified("owners.lastname") == '"owners"."lastname"'
    print("[1] identifier quoting -> OK")


def test_select_distinct():
    s = render_select([{"table": "owners", "column": "lastname"}], distinct=True)
    assert s == 'SELECT DISTINCT "owners"."lastname"', s
    # alias support
    s2 = render_select([{"table": "owners", "column": "lastname", "alias": "name"}])
    assert s2 == 'SELECT "owners"."lastname" AS "name"', s2
    print("[2] SELECT with DISTINCT (+alias) -> OK")


def test_select_aggregations():
    s = render_select(
        [{"table": "owners", "column": "city"}],
        [{"function": "COUNT", "table": "pets", "column": "petid", "alias": "pet_count"}],
    )
    assert s == 'SELECT "owners"."city", COUNT("pets"."petid") AS "pet_count"', s
    # COUNT(*) special case
    s2 = render_select([], [{"function": "COUNT", "column": "*", "alias": "n"}])
    assert s2 == 'SELECT COUNT(*) AS "n"', s2
    print("[3] SELECT with aggregations (incl COUNT(*)) -> OK")


def test_join_chain():
    joins = [
        {"from_table": "owners", "from_column": "oid", "to_table": "owns",
         "to_column": "oid", "join_type": "inner"},
        {"from_table": "owns", "from_column": "petid", "to_table": "pets",
         "to_column": "petid", "join_type": "inner"},
    ]
    s = render_from_joins("owners", joins)
    assert s == (
        'FROM "owners" '
        'INNER JOIN "owns" ON "owners"."oid" = "owns"."oid" '
        'INNER JOIN "pets" ON "owns"."petid" = "pets"."petid"'
    ), s
    # no joins -> bare FROM
    assert render_from_joins("owners", []) == 'FROM "owners"'
    print("[4] JOIN chain rendering -> OK")


def test_where_parameterization():
    clause, params = render_where([{"table": "pets", "column": "species", "op": "=", "value": "dog"}])
    assert clause == 'WHERE "pets"."species" = ?' and params == ["dog"]
    # chained connectors + a range op
    clause2, params2 = render_where([
        {"table": "pets", "column": "species", "op": "=", "value": "dog"},
        {"table": "owners", "column": "city", "op": "!=", "value": "Moscow", "connector": "AND"},
    ])
    assert clause2 == 'WHERE "pets"."species" = ? AND "owners"."city" != ?', clause2
    assert params2 == ["dog", "Moscow"]
    print("[5] WHERE parameterization (+connectors) -> OK")


def test_where_in():
    clause, params = render_where([
        {"table": "owners", "column": "city", "op": "IN", "value": ["Moscow", "Boise"]},
    ])
    assert clause == 'WHERE "owners"."city" IN (?, ?)', clause
    assert params == ["Moscow", "Boise"]
    print("[6] IN operator -> OK")


def test_where_is_null():
    c1, p1 = render_where([{"table": "pets", "column": "species", "op": "IS NULL"}])
    assert c1 == 'WHERE "pets"."species" IS NULL' and p1 == []
    c2, p2 = render_where([{"table": "pets", "column": "species", "op": "IS NOT NULL"}])
    assert c2 == 'WHERE "pets"."species" IS NOT NULL' and p2 == []
    print("[7] IS NULL / IS NOT NULL -> OK")


def test_group_by():
    assert render_group_by([{"table": "owners", "column": "city"}]) == 'GROUP BY "owners"."city"'
    assert render_group_by([]) == ""
    print("[8] GROUP BY -> OK")


def test_having_alias():
    clause, params = render_having([{"aggregation_alias": "pet_count", "op": ">", "value": 1}])
    assert clause == 'HAVING "pet_count" > ?' and params == [1]
    print("[9] HAVING alias (parameterized) -> OK")


def test_order_by_column():
    assert render_order_by([{"table": "owners", "column": "lastname", "direction": "ASC"}]) == \
        'ORDER BY "owners"."lastname" ASC'
    print("[10] ORDER BY column -> OK")


def test_order_by_alias():
    assert render_order_by([{"aggregation_alias": "pet_count", "direction": "DESC"}]) == \
        'ORDER BY "pet_count" DESC'
    print("[11] ORDER BY aggregation alias -> OK")


def test_limit():
    assert render_limit(10) == "LIMIT 10"
    assert render_limit(None) == ""
    print("[12] LIMIT (inline int; omitted when null) -> OK")


def test_deterministic():
    args = ([{"table": "owners", "column": "city"}],
            [{"function": "COUNT", "table": "pets", "column": "petid", "alias": "pet_count"}])
    a = render_select(*args)
    b = render_select(*args)
    assert a == b
    w1 = render_where([{"table": "owners", "column": "city", "op": "IN", "value": ["a", "b"]}])
    w2 = render_where([{"table": "owners", "column": "city", "op": "IN", "value": ["a", "b"]}])
    assert w1 == w2
    print("[13] deterministic output -> OK")


def main():
    tests = [
        test_identifier_quoting,
        test_select_distinct,
        test_select_aggregations,
        test_join_chain,
        test_where_parameterization,
        test_where_in,
        test_where_is_null,
        test_group_by,
        test_having_alias,
        test_order_by_column,
        test_order_by_alias,
        test_limit,
        test_deterministic,
    ]
    passed = 0
    for t in tests:
        t()
        passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed — sql_clauses.py verified")


if __name__ == "__main__":
    main()