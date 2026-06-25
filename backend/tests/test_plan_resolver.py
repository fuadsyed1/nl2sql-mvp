"""
test_plan_resolver.py — offline integration test for Phase 6 step 5.

Runnable as a plain script (no server, no LLM, no SQL, no pytest):

    python test_plan_resolver.py
"""

import copy
from planning.plan_resolver import resolve_plan
from planning.query_plan import to_dict
from semantic.semantic_ir import MultiTableSemanticIR, to_dict as ir_to_dict

SUCCESS_KEYS = ["resolved", "from_table", "joins", "tables_used",
                "bridge_tables", "ir", "diagnostics"]
FAILURE_KEYS = ["resolved", "reason", "unresolved_tables", "components",
                "from_table", "joins", "tables_used", "bridge_tables",
                "ir", "diagnostics"]

# owners / owns / pets via the junction, plus an isolated 'payments'.
GRAPH = {
    "tables": [
        {"table_name": "owners"}, {"table_name": "owns"},
        {"table_name": "pets"}, {"table_name": "payments"},
    ],
    "relationships": [
        {"relationship_id": 1, "from_table": "owns", "from_column": "oid",
         "to_table": "owners", "to_column": "oid", "confirmed": True, "confidence": 1.0},
        {"relationship_id": 2, "from_table": "owns", "from_column": "petid",
         "to_table": "pets", "to_column": "petid", "confirmed": True, "confidence": 1.0},
    ],
}

# graph with tables but NO relationships, for the no_relationships case.
GRAPH_NO_REL = {"tables": [{"table_name": "owners"}, {"table_name": "pets"}],
                "relationships": []}


def mk_ir(tables, **kw):
    return MultiTableSemanticIR(database_id=7, tables=list(tables), **kw)


def test_single_table_success():
    ir = mk_ir(["pets"], select=[{"table": "pets", "column": "name"}])
    plan = resolve_plan(ir, GRAPH)
    d = to_dict(plan)
    assert d["resolved"] is True
    assert d["from_table"] == "pets" and d["joins"] == []
    assert d["tables_used"] == ["pets"] and d["bridge_tables"] == []
    print("[1] single-table IR success (empty joins) -> OK")


def test_owners_pets_via_owns():
    ir = mk_ir(["owners", "pets"])
    d = to_dict(resolve_plan(ir, GRAPH))
    assert d["resolved"] is True
    assert d["tables_used"] == ["owners", "owns", "pets"]
    assert [(j["from_table"], j["to_table"]) for j in d["joins"]] == [
        ("owners", "owns"), ("owns", "pets")]
    print("[2] owners + pets resolves through owns -> OK")


def test_bridge_tables_contains_owns():
    d = to_dict(resolve_plan(mk_ir(["owners", "pets"]), GRAPH))
    assert d["bridge_tables"] == ["owns"]
    print("[3] bridge_tables contains owns -> OK")


def test_disconnected_failure():
    d = to_dict(resolve_plan(mk_ir(["owners", "pets", "payments"]), GRAPH))
    assert d["resolved"] is False
    assert "payments" in d["unresolved_tables"]
    assert d["from_table"] is None and d["joins"] == []
    print("[4] disconnected tables -> resolved: false -> OK")


def test_failure_reasons():
    # edges exist but don't connect 'payments' -> disconnected_tables
    d1 = to_dict(resolve_plan(mk_ir(["owners", "pets", "payments"]), GRAPH))
    assert d1["reason"] == "disconnected_tables", d1["reason"]
    # no relationships at all -> no_relationships
    d2 = to_dict(resolve_plan(mk_ir(["owners", "pets"]), GRAPH_NO_REL))
    assert d2["reason"] == "no_relationships", d2["reason"]
    # no tables -> empty_tables
    d3 = to_dict(resolve_plan(mk_ir([]), GRAPH))
    assert d3["reason"] == "empty_tables", d3["reason"]
    print("[5] correct failure reasons (disconnected/no_relationships/empty) -> OK")


def test_ir_preserved_byte_identical():
    ir = mk_ir(["owners", "pets"],
               select=[{"table": "owners", "column": "lastname"}],
               filters=[{"table": "pets", "column": "species", "op": "=", "value": "dog"}])
    snapshot = copy.deepcopy(ir_to_dict(ir))
    plan = resolve_plan(ir, GRAPH)
    d = to_dict(plan)
    # same object embedded, unchanged
    assert d["ir"] is ir
    assert ir_to_dict(ir) == snapshot, "IR must be byte-identical after resolve"
    print("[6] IR preserved byte-identically inside the plan -> OK")


def test_graph_not_mutated():
    before = copy.deepcopy(GRAPH)
    _ = resolve_plan(mk_ir(["owners", "pets"]), GRAPH)
    assert GRAPH == before, "graph must not be mutated"
    print("[7] graph not mutated -> OK")


def test_deterministic():
    ir = mk_ir(["owners", "pets"])
    a = to_dict(resolve_plan(ir, GRAPH))
    b = to_dict(resolve_plan(ir, GRAPH))
    c = to_dict(resolve_plan(ir, GRAPH))
    assert a == b == c, "output must be identical across runs"
    print("[8] deterministic output across repeated runs -> OK")


def test_plan_shapes_match_contract():
    s = to_dict(resolve_plan(mk_ir(["owners", "pets"]), GRAPH))
    assert list(s.keys()) == SUCCESS_KEYS, list(s.keys())
    f = to_dict(resolve_plan(mk_ir(["owners", "pets", "payments"]), GRAPH))
    assert list(f.keys()) == FAILURE_KEYS, list(f.keys())
    # accepts a plain dict IR too (not only the dataclass)
    sd = to_dict(resolve_plan({"database_id": 7, "tables": ["pets"]}, GRAPH))
    assert sd["resolved"] is True and sd["from_table"] == "pets"
    print("[9] success/failure shapes match query_plan contract (+dict IR) -> OK")


def main():
    tests = [
        test_single_table_success,
        test_owners_pets_via_owns,
        test_bridge_tables_contains_owns,
        test_disconnected_failure,
        test_failure_reasons,
        test_ir_preserved_byte_identical,
        test_graph_not_mutated,
        test_deterministic,
        test_plan_shapes_match_contract,
    ]
    passed = 0
    for t in tests:
        t()
        passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed — plan_resolver.py verified")


if __name__ == "__main__":
    main()