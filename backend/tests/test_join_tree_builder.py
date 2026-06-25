"""
test_join_tree_builder.py — offline test for Phase 6 step 4.

Runnable as a plain script (no server, no LLM, no SQL, no pytest):

    python test_join_tree_builder.py
"""

import copy
from planning.join_tree_builder import build_join_tree
from planning.schema_graph_adapter import build_adjacency

# owners / owns / pets connected through the junction 'owns', plus an isolated
# 'payments' table for the disconnection cases.
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
ADJ = build_adjacency(GRAPH)


def assert_invariant(result):
    """Every emitted join's from_table must already be in the growing tree."""
    tree = {result["from_table"]}
    for j in result["joins"]:
        assert j["from_table"] in tree, f"invariant broken at {j}"
        tree.add(j["to_table"])


def test_single_table():
    r = build_join_tree(["pets"], ADJ)
    assert r["connected"] is True
    assert r["from_table"] == "pets"
    assert r["joins"] == []
    assert r["tables_used"] == ["pets"]
    assert r["bridge_tables"] == []
    print("[1] single-table case -> OK")


def test_bridge_case():
    r = build_join_tree(["owners", "pets"], ADJ)
    assert r["connected"] is True
    assert r["tables_used"] == ["owners", "owns", "pets"]
    assert [(j["from_table"], j["to_table"]) for j in r["joins"]] == [
        ("owners", "owns"), ("owns", "pets")]
    assert_invariant(r)
    print("[2] owners -> owns -> pets bridge case -> OK")


def test_bridge_tables_contains_owns():
    r = build_join_tree(["owners", "pets"], ADJ)
    assert r["bridge_tables"] == ["owns"]
    print("[3] bridge_tables contains 'owns' -> OK")


def test_ir_tables_unchanged():
    ir_tables = ["Owners", "Pets"]
    snapshot = copy.deepcopy(ir_tables)
    _ = build_join_tree(ir_tables, ADJ)
    assert ir_tables == snapshot, "ir_tables must not be mutated"
    print("[4] IR tables unchanged -> OK")


def test_root_owners_first():
    r = build_join_tree(["owners", "pets"], ADJ)
    assert r["from_table"] == "owners"
    print("[5] root selection ['owners','pets'] -> owners -> OK")


def test_root_pets_first():
    r = build_join_tree(["pets", "owners"], ADJ)
    assert r["from_table"] == "pets"
    print("[6] root selection ['pets','owners'] -> pets -> OK")


def test_join_order_reverses():
    r = build_join_tree(["pets", "owners"], ADJ)
    assert r["tables_used"] == ["pets", "owns", "owners"]
    assert [(j["from_table"], j["to_table"]) for j in r["joins"]] == [
        ("pets", "owns"), ("owns", "owners")]
    # and the join columns are oriented for the reversed direction
    assert r["joins"][0]["from_table"] == "pets" and r["joins"][0]["to_table"] == "owns"
    assert_invariant(r)
    print("[7] join order reverses when root flips -> OK")


def test_tables_used_includes_bridge():
    r = build_join_tree(["owners", "pets"], ADJ)
    assert "owns" in r["tables_used"]
    print("[8] tables_used includes bridge table -> OK")


def test_disconnected_detected():
    r = build_join_tree(["owners", "pets", "payments"], ADJ)
    assert r["connected"] is False
    assert r["from_table"] is None and r["joins"] == []
    assert "payments" in r["unresolved_tables"]
    print("[9] disconnected required table detected -> OK")


def test_components_reported():
    r = build_join_tree(["owners", "pets", "payments"], ADJ)
    # owners & pets share a component (via owns); payments is isolated
    assert r["components"] == [["owners", "pets"], ["payments"]], r["components"]
    print("[10] connected components reported correctly -> OK")


def test_deterministic():
    a = build_join_tree(["owners", "pets"], ADJ)
    b = build_join_tree(["owners", "pets"], ADJ)
    c = build_join_tree(["owners", "pets"], ADJ)
    assert a == b == c, "output must be identical across runs"
    # adjacency not mutated
    assert build_adjacency(GRAPH) == ADJ
    print("[11] deterministic output across repeated runs -> OK")


def main():
    tests = [
        test_single_table,
        test_bridge_case,
        test_bridge_tables_contains_owns,
        test_ir_tables_unchanged,
        test_root_owners_first,
        test_root_pets_first,
        test_join_order_reverses,
        test_tables_used_includes_bridge,
        test_disconnected_detected,
        test_components_reported,
        test_deterministic,
    ]
    passed = 0
    for t in tests:
        t()
        passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed — join_tree_builder.py verified")


if __name__ == "__main__":
    main()