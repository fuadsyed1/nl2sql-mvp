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


def test_where_connectors_and_or_mixed():
    # Case A (OR stored on the CURRENT filter — still works)
    a, ap = render_where([
        {"table": "owners", "column": "city", "op": "=", "value": "Moscow"},
        {"table": "owners", "column": "city", "op": "=", "value": "Pullman", "connector": "OR"},
    ])
    assert a == 'WHERE "owners"."city" = ? OR "owners"."city" = ?', a
    assert ap == ["Moscow", "Pullman"]

    # Case B: AND chain
    b, bp = render_where([
        {"table": "owners", "column": "city", "op": "=", "value": "Moscow"},
        {"table": "owners", "column": "lastname", "op": "=", "value": "Smith", "connector": "AND"},
    ])
    assert b == 'WHERE "owners"."city" = ? AND "owners"."lastname" = ?', b
    assert bp == ["Moscow", "Smith"]

    # Case C: three-filter OR chain (current-filter placement)
    c, cp = render_where([
        {"table": "owners", "column": "city", "op": "=", "value": "Moscow"},
        {"table": "owners", "column": "city", "op": "=", "value": "Pullman", "connector": "OR"},
        {"table": "owners", "column": "city", "op": "=", "value": "Boise", "connector": "OR"},
    ])
    assert c == ('WHERE "owners"."city" = ? OR "owners"."city" = ? '
                 'OR "owners"."city" = ?'), c
    assert cp == ["Moscow", "Pullman", "Boise"]
    print("[5b] connectors: OR / AND / 3-filter (current-filter placement) -> OK")


def test_where_connector_previous_filter_placement():
    # The extractor's convention: connector is stored on the PREVIOUS filter
    # (the one it connects from). [Pullman OR, Moscow None] -> ... = ? OR ... = ?
    clause, params = render_where([
        {"table": "owners", "column": "city", "op": "=", "value": "Pullman", "connector": "OR"},
        {"table": "owners", "column": "city", "op": "=", "value": "Moscow", "connector": None},
    ])
    assert "NONE" not in clause, clause
    assert clause == 'WHERE "owners"."city" = ? OR "owners"."city" = ?', clause
    assert params == ["Pullman", "Moscow"]

    # three-filter OR via previous-filter placement
    c3, p3 = render_where([
        {"table": "owners", "column": "city", "op": "=", "value": "Moscow", "connector": "OR"},
        {"table": "owners", "column": "city", "op": "=", "value": "Pullman", "connector": "OR"},
        {"table": "owners", "column": "city", "op": "=", "value": "Boise", "connector": None},
    ])
    assert c3 == ('WHERE "owners"."city" = ? OR "owners"."city" = ? '
                  'OR "owners"."city" = ?'), c3
    assert p3 == ["Moscow", "Pullman", "Boise"]

    # AND via previous-filter placement
    aclause, _ = render_where([
        {"table": "owners", "column": "city", "op": "=", "value": "Moscow", "connector": "AND"},
        {"table": "owners", "column": "lastname", "op": "=", "value": "Smith", "connector": None},
    ])
    assert aclause == 'WHERE "owners"."city" = ? AND "owners"."lastname" = ?', aclause
    print("[5d] connector on PREVIOUS filter honored (OR/AND, no NONE) -> OK")


def test_where_connector_none_regression():
    # Both filters None on a chain -> default AND, never 'NONE'.
    clause, params = render_where([
        {"table": "owners", "column": "city", "op": "=", "value": "Pullman", "connector": None},
        {"table": "owners", "column": "city", "op": "=", "value": "Moscow", "connector": None},
    ])
    assert "NONE" not in clause, clause
    assert clause == 'WHERE "owners"."city" = ? AND "owners"."city" = ?', clause
    assert params == ["Pullman", "Moscow"]
    # empty string and garbage connectors also coalesce to AND
    c2, _ = render_where([
        {"table": "owners", "column": "city", "op": "=", "value": "A", "connector": ""},
        {"table": "owners", "column": "city", "op": "=", "value": "B", "connector": "THEN"},
        {"table": "owners", "column": "city", "op": "=", "value": "C"},
    ])
    assert "NONE" not in c2 and "THEN" not in c2, c2
    assert c2 == ('WHERE "owners"."city" = ? AND "owners"."city" = ? '
                  'AND "owners"."city" = ?'), c2
    print("[5c] None/empty/invalid connector -> AND (no 'NONE'/'THEN') -> OK")


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
        test_where_connectors_and_or_mixed,
        test_where_connector_previous_filter_placement,
        test_where_connector_none_regression,
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