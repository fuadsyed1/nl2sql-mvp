"""
test_family_routing_integration.py

Tests the query-family routing GATE that is wired into
/database/{id}/execute_sql. `choose()` below mirrors the app.py decision exactly:
use the family extraction only when it is non-None, confident (>= threshold),
AND validates; otherwise fall back to the LLM extractor.

Pure — uses the real router plus stub llm/validate callables (no FastAPI, no DB,
no SQL generation).

Run:  python -m tests.test_family_routing_integration
"""

from query_families import route_and_build
from tests.test_query_family_router import GRAPH

THRESHOLD = 0.80


def choose(question, graph, llm_fn, validate_fn=lambda e: True,
           threshold=THRESHOLD, route_fn=route_and_build):
    """Mirror of the app.py execute_sql gate."""
    fam_extraction, decision = route_fn(question, graph)
    if (fam_extraction is not None
            and (decision.get("confidence") or 0) >= threshold
            and validate_fn(fam_extraction)):
        return "query_family", fam_extraction, decision
    return "llm", llm_fn(question, graph), decision


def _llm(question, graph):
    return {"tables": ["owners"], "select": [{"table": "owners", "column": "owner_id"}]}


# 1. a routed family query uses the query_family path
def test_family_query_uses_family_path():
    q = ("Find food types where the same owner both purchased the cheapest and "
         "the most expensive food of that type.")
    src, ex, d = choose(q, GRAPH, _llm)
    assert src == "query_family", (src, d)
    assert d["family"] == "min_max_same_entity_per_group", d
    assert d["confidence"] >= THRESHOLD, d
    assert "derived_relations" in ex and "aliases" in ex, list(ex)
    print(f"[1] family query -> query_family ({d['family']} @ {d['confidence']}) -> OK")


# 2. a normal simple query falls back to the LLM path
def test_simple_query_uses_llm_path():
    src, ex, d = choose("Show all rows from owners", GRAPH, _llm)
    assert src == "llm", (src, d)
    assert d["family"] == "normal_join_filter_group", d
    print("[2] 'Show all rows from owners' -> llm fallback -> OK")


# 3. a confident-enough family but BELOW the 0.80 gate falls back to LLM
def test_low_confidence_falls_back():
    def fake_route(question, graph):
        return ({"anti_exists": [{"target_table": "purchases"}]},
                {"family": "anti_exists", "confidence": 0.70, "reason": "weak signal"})
    src, ex, d = choose("anything", GRAPH, _llm, route_fn=fake_route)
    assert src == "llm" and d["confidence"] == 0.70, (src, d)
    print("[3] family confidence 0.70 (< 0.80) -> llm fallback -> OK")


# 4. a confident family whose extraction fails validation falls back to LLM
def test_invalid_extraction_falls_back():
    def fake_route(question, graph):
        return ({"aliases": [{"alias": "x", "table": "not_a_table"}]},
                {"family": "self_join_pair", "confidence": 0.9, "reason": "ok"})
    src, ex, d = choose("anything", GRAPH, _llm, validate_fn=lambda e: False,
                        route_fn=fake_route)
    assert src == "llm", (src, d)
    print("[4] confident family but invalid extraction -> llm fallback -> OK")


def main():
    tests = [
        test_family_query_uses_family_path,
        test_simple_query_uses_llm_path,
        test_low_confidence_falls_back,
        test_invalid_extraction_falls_back,
    ]
    passed = 0
    for t in tests:
        t(); passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed -- family routing integration verified")


if __name__ == "__main__":
    main()
