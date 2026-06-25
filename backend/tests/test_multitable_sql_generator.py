"""
test_multitable_sql_generator.py — offline test for Phase 7 step 3.

Runnable as a plain script (no server, no LLM, no SQL execution, no pytest):

    python test_multitable_sql_generator.py
"""

import copy
from generation.multitable_sql_generator import generate_sql
from planning.query_plan import (
    success_plan, single_table_plan, failure_plan, join_step,
    to_dict as plan_to_dict,
)
from generation.sql_types import to_dict as sql_to_dict
from semantic.semantic_ir import MultiTableSemanticIR, to_dict as ir_to_dict

# canonical owners -> owns -> pets join steps
JOINS = [
    join_step("owners", "oid", "owns", "oid"),
    join_step("owns", "petid", "pets", "petid"),
]
FROM_JOIN = ('FROM "owners" '
             'INNER JOIN "owns" ON "owners"."oid" = "owns"."oid" '
             'INNER JOIN "pets" ON "owns"."petid" = "pets"."petid"')


def mk_ir(**kw):
    return MultiTableSemanticIR(database_id=7, **kw)


def petshop_plan(ir):
    return success_plan("owners", JOINS, ["owners", "owns", "pets"], ["owns"], ir)


def test_single_table():
    ir = mk_ir(tables=["owners"], select=[{"table": "owners", "column": "lastname"}])
    d = sql_to_dict(generate_sql(single_table_plan("owners", ir)))
    assert d["generated"] is True
    assert d["sql"] == 'SELECT "owners"."lastname" FROM "owners"'
    assert d["params"] == []
    assert d["diagnostics"]["join_count"] == 0 and d["diagnostics"]["bridge_tables"] == []
    print("[1] single-table query generation -> OK")


def test_join_sql():
    ir = mk_ir(tables=["owners", "pets"],
               select=[{"table": "owners", "column": "lastname"},
                       {"table": "pets", "column": "name"}])
    d = sql_to_dict(generate_sql(petshop_plan(ir)))
    assert d["sql"] == (
        'SELECT "owners"."lastname", "pets"."name" ' + FROM_JOIN), d["sql"]
    assert d["diagnostics"]["join_count"] == 2
    assert d["diagnostics"]["bridge_tables"] == ["owns"]
    print("[2] owners -> owns -> pets join SQL -> OK")


def test_where_parameterization():
    ir = mk_ir(tables=["owners", "pets"],
               select=[{"table": "owners", "column": "lastname"}],
               filters=[{"table": "pets", "column": "species", "op": "=", "value": "dog"}],
               distinct=True)
    d = sql_to_dict(generate_sql(petshop_plan(ir)))
    assert d["sql"] == (
        'SELECT DISTINCT "owners"."lastname" ' + FROM_JOIN +
        ' WHERE "pets"."species" = ?'), d["sql"]
    assert d["params"] == ["dog"] and d["diagnostics"]["parameter_count"] == 1
    print("[3] WHERE parameterization (+DISTINCT) -> OK")


def test_group_by_aggregation():
    ir = mk_ir(tables=["owners", "pets"],
               select=[{"table": "owners", "column": "city"}],
               aggregations=[{"function": "COUNT", "table": "pets",
                              "column": "petid", "alias": "pet_count"}],
               group_by=[{"table": "owners", "column": "city"}])
    d = sql_to_dict(generate_sql(petshop_plan(ir)))
    assert d["sql"] == (
        'SELECT "owners"."city", COUNT("pets"."petid") AS "pet_count" ' + FROM_JOIN +
        ' GROUP BY "owners"."city"'), d["sql"]
    print("[4] GROUP BY + aggregation -> OK")


def test_having_and_param_order():
    # WHERE + HAVING together: WHERE params first, then HAVING params
    ir = mk_ir(tables=["owners", "pets"],
               select=[{"table": "owners", "column": "city"}],
               aggregations=[{"function": "COUNT", "table": "pets",
                              "column": "petid", "alias": "pet_count"}],
               filters=[{"table": "pets", "column": "species", "op": "=", "value": "dog"}],
               group_by=[{"table": "owners", "column": "city"}],
               having=[{"aggregation_alias": "pet_count", "op": ">", "value": 1}])
    d = sql_to_dict(generate_sql(petshop_plan(ir)))
    assert 'HAVING "pet_count" > ?' in d["sql"]
    assert d["sql"].index("WHERE") < d["sql"].index("GROUP BY") < d["sql"].index("HAVING")
    assert d["params"] == ["dog", 1], d["params"]   # WHERE first, HAVING second
    print("[5] HAVING generation + param order (WHERE then HAVING) -> OK")


def test_order_by_alias_and_limit():
    ir = mk_ir(tables=["owners", "pets"],
               select=[{"table": "owners", "column": "city"}],
               aggregations=[{"function": "COUNT", "table": "pets",
                              "column": "petid", "alias": "pet_count"}],
               filters=[{"table": "pets", "column": "species", "op": "=", "value": "dog"}],
               group_by=[{"table": "owners", "column": "city"}],
               having=[{"aggregation_alias": "pet_count", "op": ">", "value": 1}],
               order_by=[{"aggregation_alias": "pet_count", "direction": "DESC"}],
               limit=5)
    d = sql_to_dict(generate_sql(petshop_plan(ir)))
    expected = (
        'SELECT "owners"."city", COUNT("pets"."petid") AS "pet_count" ' + FROM_JOIN +
        ' WHERE "pets"."species" = ?'
        ' GROUP BY "owners"."city"'
        ' HAVING "pet_count" > ?'
        ' ORDER BY "pet_count" DESC'
        ' LIMIT 5')
    assert d["sql"] == expected, d["sql"]
    assert d["params"] == ["dog", 1]
    assert d["diagnostics"]["clauses"] == [
        "select", "from", "join", "where", "group_by", "having", "order_by", "limit"]
    # no trailing space, single-space joined
    assert "  " not in d["sql"] and not d["sql"].endswith(" ")
    print("[6/7] ORDER BY alias + LIMIT (full clause order) -> OK")


def test_or_filter_chain_generation():
    # Exact reported case + exact extractor convention: connector "OR" is stored
    # on the PREVIOUS filter (Pullman), Moscow's connector is null.
    ir = mk_ir(tables=["owners"],
               select=[{"table": "owners", "column": "lastname"}],
               filters=[
                   {"table": "owners", "column": "city", "op": "=", "value": "Pullman", "connector": "OR"},
                   {"table": "owners", "column": "city", "op": "=", "value": "Moscow", "connector": None},
               ])
    d = sql_to_dict(generate_sql(single_table_plan("owners", ir)))
    assert d["generated"] is True
    assert "NONE" not in d["sql"], d["sql"]
    assert d["sql"] == (
        'SELECT "owners"."lastname" FROM "owners" '
        'WHERE "owners"."city" = ? OR "owners"."city" = ?'), d["sql"]
    assert d["params"] == ["Pullman", "Moscow"]

    # current-filter placement still works too
    ir2 = mk_ir(tables=["owners"],
                select=[{"table": "owners", "column": "lastname"}],
                filters=[
                    {"table": "owners", "column": "city", "op": "=", "value": "Pullman"},
                    {"table": "owners", "column": "city", "op": "=", "value": "Moscow", "connector": "OR"},
                ])
    d2 = sql_to_dict(generate_sql(single_table_plan("owners", ir2)))
    assert d2["sql"].endswith('WHERE "owners"."city" = ? OR "owners"."city" = ?'), d2["sql"]
    print("[12] OR-filter chain (prev- and current-filter placement, no NONE) -> OK")


def test_unresolved_failure():
    plan = failure_plan("disconnected_tables", unresolved_tables=["payments"],
                        components=[["owners"], ["payments"]], ir=mk_ir(tables=["owners", "payments"]))
    d = sql_to_dict(generate_sql(plan))
    assert d["generated"] is False and d["reason"] == "unresolved_plan"
    assert d["sql"] is None and d["params"] == []
    print("[8] unresolved plan -> failed_sql('unresolved_plan') -> OK")


def test_empty_select_failure():
    ir = mk_ir(tables=["owners"], select=[], aggregations=[])
    d = sql_to_dict(generate_sql(single_table_plan("owners", ir)))
    assert d["generated"] is False and d["reason"] == "empty_select"
    print("[9] no select + no aggregations -> failed_sql('empty_select') -> OK")


def test_deterministic():
    ir = mk_ir(tables=["owners", "pets"],
               select=[{"table": "owners", "column": "lastname"}],
               filters=[{"table": "pets", "column": "species", "op": "=", "value": "dog"}])
    a = sql_to_dict(generate_sql(petshop_plan(ir)))
    b = sql_to_dict(generate_sql(petshop_plan(ir)))
    assert a == b, "output must be identical across runs"
    print("[10] deterministic output -> OK")


def test_no_mutation():
    ir = mk_ir(tables=["owners", "pets"],
               select=[{"table": "owners", "column": "lastname"}],
               filters=[{"table": "pets", "column": "species", "op": "=", "value": "dog"}])
    plan = petshop_plan(ir)
    ir_snap = copy.deepcopy(ir_to_dict(ir))
    plan_snap = copy.deepcopy(plan_to_dict(plan))
    _ = generate_sql(plan)
    assert ir_to_dict(ir) == ir_snap, "embedded IR must not be mutated"
    assert plan_to_dict(plan) == plan_snap, "plan must not be mutated"
    print("[11] no mutation of plan or embedded IR -> OK")


def main():
    tests = [
        test_single_table,
        test_join_sql,
        test_where_parameterization,
        test_group_by_aggregation,
        test_having_and_param_order,
        test_order_by_alias_and_limit,
        test_or_filter_chain_generation,
        test_unresolved_failure,
        test_empty_select_failure,
        test_deterministic,
        test_no_mutation,
    ]
    passed = 0
    for t in tests:
        t()
        passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed — multitable_sql_generator.py verified")


if __name__ == "__main__":
    main()