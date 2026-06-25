"""
test_schema_graph_adapter.py — offline test for Phase 6 step 2.

Runnable as a plain script (no server, no LLM, no SQL, no pytest):

    python test_schema_graph_adapter.py
"""

from planning.schema_graph_adapter import build_adjacency, edges_for, all_tables

# owners / owns / pets, plus an isolated 'payments' table.
# rel1 uses DIFFERING column names (pets.owner_id -> owners.oid) to prove the
# bidirectional orientation swaps columns correctly.
GRAPH = {
    "tables": [
        {"table_name": "owners", "columns": [{"column_name": "oid"}]},
        {"table_name": "owns", "columns": [{"column_name": "petid"}]},
        {"table_name": "pets", "columns": [{"column_name": "petid"}]},
        {"table_name": "payments", "columns": [{"column_name": "pid"}]},
    ],
    "relationships": [
        {"relationship_id": 1, "from_table": "pets", "from_column": "owner_id",
         "to_table": "owners", "to_column": "oid", "confirmed": True, "confidence": 1.0},
        {"relationship_id": 2, "from_table": "owns", "from_column": "petid",
         "to_table": "pets", "to_column": "petid", "confirmed": False, "confidence": 0.7},
    ],
}


def test_nodes_and_isolated():
    adj = build_adjacency(GRAPH)
    assert all_tables(adj) == ["owners", "owns", "payments", "pets"]
    # isolated table present with no edges
    assert edges_for(adj, "payments") == []
    print("[1] all tables as nodes (sorted); isolated 'payments' has [] -> OK")


def test_bidirectional_and_column_swap():
    adj = build_adjacency(GRAPH)

    # owners <- pets edge (owners side): oriented from owners, columns swapped
    owners_edges = edges_for(adj, "owners")
    assert len(owners_edges) == 1
    e = owners_edges[0]
    assert e["from_table"] == "owners" and e["from_column"] == "oid"
    assert e["to_table"] == "pets" and e["to_column"] == "owner_id"

    # pets side of the same relationship: orientation reversed
    pets_edges = edges_for(adj, "pets")
    rel1 = [x for x in pets_edges if x.get("relationship_id") == 1][0]
    assert rel1["from_table"] == "pets" and rel1["from_column"] == "owner_id"
    assert rel1["to_table"] == "owners" and rel1["to_column"] == "oid"
    print("[2] relationships bidirectional with correct column swap -> OK")


def test_metadata_preserved():
    adj = build_adjacency(GRAPH)
    pets_edges = edges_for(adj, "pets")

    rel1 = [x for x in pets_edges if x.get("relationship_id") == 1][0]
    assert rel1["confirmed"] is True and rel1["confidence"] == 1.0 and rel1["relationship_id"] == 1

    rel2 = [x for x in pets_edges if x.get("relationship_id") == 2][0]
    assert rel2["confirmed"] is False and rel2["confidence"] == 0.7 and rel2["relationship_id"] == 2
    # owns side of rel2
    owns_edges = edges_for(adj, "owns")
    assert owns_edges[0]["to_table"] == "pets" and owns_edges[0]["confirmed"] is False
    print("[3] edge metadata (confirmed, confidence, relationship_id) preserved -> OK")


def test_deterministic_and_sorted():
    adj1 = build_adjacency(GRAPH)

    # reverse the input ordering of tables and relationships — output must match
    shuffled = {
        "tables": list(reversed(GRAPH["tables"])),
        "relationships": list(reversed(GRAPH["relationships"])),
    }
    adj2 = build_adjacency(shuffled)
    assert adj1 == adj2, "adjacency must be independent of input ordering"

    # each node's edges are sorted by the total edge key
    for table in all_tables(adj1):
        edges = edges_for(adj1, table)
        keys = [(e["to_table"], e["from_column"], e["to_column"], e.get("relationship_id", -1))
                for e in edges]
        assert keys == sorted(keys), f"edges for {table} not sorted"
    print("[4] deterministic (order-independent) + edges sorted -> OK")


def test_tolerant_inputs():
    # empty graph
    assert build_adjacency({}) == {}
    assert build_adjacency(None) == {}
    # graph wrapped under 'database'
    wrapped = {"database": GRAPH}
    assert all_tables(build_adjacency(wrapped)) == ["owners", "owns", "payments", "pets"]
    # unknown / case-insensitive lookups
    adj = build_adjacency(GRAPH)
    assert edges_for(adj, "OWNERS") == edges_for(adj, "owners")
    assert edges_for(adj, "does_not_exist") == []
    print("[5] tolerant: empty/None, 'database' wrapper, case-insensitive lookup -> OK")


def main():
    tests = [
        test_nodes_and_isolated,
        test_bidirectional_and_column_swap,
        test_metadata_preserved,
        test_deterministic_and_sorted,
        test_tolerant_inputs,
    ]
    passed = 0
    for t in tests:
        t()
        passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed — schema_graph_adapter.py verified")


if __name__ == "__main__":
    main()