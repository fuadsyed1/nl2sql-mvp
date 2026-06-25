"""
test_path_resolver.py — offline test for Phase 6 step 3.

Runnable as a plain script (no server, no LLM, no SQL, no pytest):

    python test_path_resolver.py
"""

import copy
from planning.path_resolver import find_best_path
from planning.schema_graph_adapter import build_adjacency


def edge(ft, fc, tt, tc, confirmed=True, confidence=1.0, rid=None):
    e = {"from_table": ft, "from_column": fc, "to_table": tt, "to_column": tc,
         "confirmed": confirmed, "confidence": confidence}
    if rid is not None:
        e["relationship_id"] = rid
    return e


def link(adj, a, ca, b, cb, confirmed=True, confidence=1.0, rid=None):
    """Add a bidirectional connection a<->b to a hand-built adjacency."""
    adj.setdefault(a, []).append(edge(a, ca, b, cb, confirmed, confidence, rid))
    adj.setdefault(b, []).append(edge(b, cb, a, ca, confirmed, confidence, rid))


def tables_in(path):
    """Ordered table sequence a path visits, including the source."""
    if not path:
        return []
    seq = [path[0]["from_table"]]
    for e in path:
        seq.append(e["to_table"])
    return seq


# --- 1. direct path ---------------------------------------------------------
def test_direct_path():
    adj = {}
    link(adj, "owners", "oid", "pets", "owner_id", rid=1)
    path = find_best_path(adj, "owners", "pets")
    assert path is not None and len(path) == 1
    assert tables_in(path) == ["owners", "pets"]
    print("[1] direct path -> OK")


# --- 2. multi-hop owners -> owns -> pets (via the real adapter) -------------
def test_multi_hop():
    graph = {
        "tables": [{"table_name": "owners"}, {"table_name": "owns"}, {"table_name": "pets"}],
        "relationships": [
            {"relationship_id": 1, "from_table": "owns", "from_column": "oid",
             "to_table": "owners", "to_column": "oid", "confirmed": True, "confidence": 1.0},
            {"relationship_id": 2, "from_table": "owns", "from_column": "petid",
             "to_table": "pets", "to_column": "petid", "confirmed": True, "confidence": 1.0},
        ],
    }
    adj = build_adjacency(graph)
    path = find_best_path(adj, "owners", "pets")
    assert tables_in(path) == ["owners", "owns", "pets"]
    print("[2] multi-hop owners -> owns -> pets -> OK")


# --- 3. no path -> None -----------------------------------------------------
def test_no_path():
    adj = {}
    link(adj, "owners", "oid", "owns", "oid")
    adj.setdefault("payments", [])  # isolated
    assert find_best_path(adj, "owners", "payments") is None
    print("[3] unreachable target -> None -> OK")


# --- 4. shortest beats longer ----------------------------------------------
def test_shortest_wins():
    adj = {}
    link(adj, "owners", "oid", "pets", "owner_id", rid=10)          # direct (1 hop)
    link(adj, "owners", "oid", "mid", "oid", rid=11)               # owners-mid-pets (2 hops)
    link(adj, "mid", "petid", "pets", "petid", rid=12)
    path = find_best_path(adj, "owners", "pets")
    assert tables_in(path) == ["owners", "pets"], tables_in(path)
    print("[4] shortest path beats longer -> OK")


# --- 5. equal hops, fewer unconfirmed wins ---------------------------------
def test_fewer_unconfirmed_wins():
    adj = {}
    # path via 'a': both edges confirmed
    link(adj, "owners", "k", "a", "k", confirmed=True, rid=1)
    link(adj, "a", "k", "pets", "k", confirmed=True, rid=2)
    # path via 'b': both edges unconfirmed (same hop count)
    link(adj, "owners", "k", "b", "k", confirmed=False, rid=3)
    link(adj, "b", "k", "pets", "k", confirmed=False, rid=4)
    path = find_best_path(adj, "owners", "pets")
    assert tables_in(path) == ["owners", "a", "pets"], tables_in(path)
    print("[5] equal hops, fewer unconfirmed edges wins -> OK")


# --- 6. equal confirmed count, higher MIN confidence wins ------------------
def test_higher_min_confidence_wins():
    adj = {}
    # via 'a': min confidence 0.9
    link(adj, "owners", "k", "a", "k", confirmed=True, confidence=0.9, rid=1)
    link(adj, "a", "k", "pets", "k", confirmed=True, confidence=0.95, rid=2)
    # via 'b': min confidence 0.6 (one weak link)
    link(adj, "owners", "k", "b", "k", confirmed=True, confidence=0.6, rid=3)
    link(adj, "b", "k", "pets", "k", confirmed=True, confidence=0.99, rid=4)
    path = find_best_path(adj, "owners", "pets")
    assert tables_in(path) == ["owners", "a", "pets"], tables_in(path)
    print("[6] equal confirmed count, higher MIN confidence wins -> OK")


# --- 7. hints break ties only after hop/confirmed/confidence ---------------
def test_hints_break_ties():
    adj = {}
    # two paths identical on hop(2)/unconfirmed(0)/min_conf(1.0); differ only by name
    link(adj, "owners", "k", "a", "k", confirmed=True, confidence=1.0, rid=1)
    link(adj, "a", "k", "pets", "k", confirmed=True, confidence=1.0, rid=2)
    link(adj, "owners", "k", "b", "k", confirmed=True, confidence=1.0, rid=3)
    link(adj, "b", "k", "pets", "k", confirmed=True, confidence=1.0, rid=4)

    # no hints: pure signature tie-break -> 'a' (lexically smaller) wins
    assert tables_in(find_best_path(adj, "owners", "pets")) == ["owners", "a", "pets"]

    # hints matching the 'b' path must override the signature default -> 'b' wins
    hints = [
        {"from_table": "owners", "from_column": "k", "to_table": "b", "to_column": "k"},
        {"from_table": "b", "from_column": "k", "to_table": "pets", "to_column": "k"},
    ]
    assert tables_in(find_best_path(adj, "owners", "pets", hints=hints)) == ["owners", "b", "pets"]
    print("[7] hints break ties only after hop/confirmed/confidence -> OK")


# --- 8. final lexical signature tie-break is deterministic -----------------
def test_signature_tiebreak():
    adj = {}
    link(adj, "owners", "k", "a", "k", confirmed=True, confidence=1.0, rid=1)
    link(adj, "a", "k", "pets", "k", confirmed=True, confidence=1.0, rid=2)
    link(adj, "owners", "k", "b", "k", confirmed=True, confidence=1.0, rid=3)
    link(adj, "b", "k", "pets", "k", confirmed=True, confidence=1.0, rid=4)
    # everything ties except signature; 'a' < 'b'
    assert tables_in(find_best_path(adj, "owners", "pets")) == ["owners", "a", "pets"]
    print("[8] final lexical path_signature tie-break deterministic -> OK")


# --- 9. low-confidence-only path is still returned -------------------------
def test_low_confidence_still_returned():
    adj = {}
    link(adj, "owners", "k", "pets", "k", confirmed=False, confidence=0.1, rid=1)
    path = find_best_path(adj, "owners", "pets")
    assert path is not None and tables_in(path) == ["owners", "pets"]
    print("[9] low-confidence-only path still returned -> OK")


# --- 10. byte-identical output across repeated runs; adjacency untouched ----
def test_deterministic_and_readonly():
    adj = {}
    link(adj, "owners", "k", "a", "k", confirmed=True, confidence=0.9, rid=1)
    link(adj, "a", "k", "pets", "k", confirmed=True, confidence=0.95, rid=2)
    link(adj, "owners", "k", "b", "k", confirmed=True, confidence=0.6, rid=3)
    link(adj, "b", "k", "pets", "k", confirmed=True, confidence=0.99, rid=4)

    before = copy.deepcopy(adj)
    r1 = find_best_path(adj, "owners", "pets")
    r2 = find_best_path(adj, "owners", "pets")
    r3 = find_best_path(adj, "owners", "pets")
    assert r1 == r2 == r3, "result must be identical across runs"
    assert adj == before, "adjacency must not be mutated"
    print("[10] identical across runs; adjacency not mutated -> OK")


def main():
    tests = [
        test_direct_path,
        test_multi_hop,
        test_no_path,
        test_shortest_wins,
        test_fewer_unconfirmed_wins,
        test_higher_min_confidence_wins,
        test_hints_break_ties,
        test_signature_tiebreak,
        test_low_confidence_still_returned,
        test_deterministic_and_readonly,
    ]
    passed = 0
    for t in tests:
        t()
        passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed — path_resolver.py verified")


if __name__ == "__main__":
    main()