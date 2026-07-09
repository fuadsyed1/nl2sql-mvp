"""
test_containment_step5.py — offline tests for containment Step 5 (batch-level
hierarchy / main-set analysis).

Tests 1-5 exercise _build_analysis directly with fabricated pairwise results
(no DB needed). Test 6 runs the full check_containment_batch against real SQLite
(get_database_path monkeypatched) to confirm the pairwise response is preserved
and the analysis is attached.

    python -m pytest backend/tests/test_containment_step5.py -q
"""

import os
import sqlite3
import tempfile

import pytest

import containment.checker as checker
from containment.models import BatchQueryResult, PairwiseRelationship, ContainmentBatchRequest
from containment.service import _build_analysis, check_containment_batch


def R(i, empty=False):
    return BatchQueryResult(
        query_id=i, question=f"q{i}", success=True, sql="SELECT k FROM t",
        execution_columns=["k"], row_count=(0 if empty else 5),
        empty_result=empty, safe=True,
    )


def P(a, b, rel, expl="reason"):
    return PairwiseRelationship(query_a=a, query_b=b, relationship=rel, explanation=expl)


def test_three_query_hierarchy():
    # Q1 contains Q2 contains Q3 (pairwise both-directions already reduced).
    results = [R(1), R(2), R(3)]
    pairwise = [
        P(1, 2, "query_b_contained_in_query_a"),
        P(1, 3, "query_b_contained_in_query_a"),
        P(2, 3, "query_b_contained_in_query_a"),
    ]
    a = _build_analysis(results, pairwise)
    main_idx = [m.index for m in a.main_queries]
    assert main_idx == [1]
    assert a.main_queries[0].contains == [2, 3]
    edges = {(e.superset, e.subset) for e in a.containment_edges}
    assert (1, 2) in edges and (2, 3) in edges
    assert a.independent_queries == []


def test_equivalent_group():
    a = _build_analysis([R(1), R(2)], [P(1, 2, "equivalent_on_current_database")])
    assert a.equivalent_groups == [[1, 2]]
    assert a.containment_edges == []
    # A representative main lists the other as equivalent.
    assert a.main_queries[0].equivalent_to == [2]


def test_independent_incomparable_no_edges():
    a = _build_analysis([R(1), R(2)], [P(1, 2, "incomparable_on_current_database")])
    assert a.containment_edges == []
    assert a.independent_queries == [1, 2]
    assert [(p.left, p.right) for p in a.incomparable_pairs] == [(1, 2)]


def test_unknown_pair_not_edge():
    a = _build_analysis([R(1), R(2)], [P(1, 2, "unknown", "not normalizable")])
    assert a.containment_edges == []
    assert len(a.unknown_pairs) == 1
    assert a.unknown_pairs[0].reason == "not normalizable"


def test_empty_query_not_main():
    # Q2 is empty -> contained in Q1 -> subset, never a main query.
    results = [R(1), R(2, empty=True)]
    pairwise = [P(1, 2, "query_b_contained_in_query_a")]
    a = _build_analysis(results, pairwise)
    assert a.empty_queries == [2]
    main_idx = [m.index for m in a.main_queries]
    assert 2 not in main_idx
    assert main_idx == [1]


# ---------------------------------------------------------------------------
# End-to-end: pairwise preserved + analysis attached
# ---------------------------------------------------------------------------

@pytest.fixture()
def db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE clubs(club_id INTEGER PRIMARY KEY, club_name TEXT, budget INTEGER);
        INSERT INTO clubs VALUES (1,'A',6000),(2,'B',4000),(3,'C',3500),(4,'D',2000);
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(checker, "get_database_path", lambda database_id: path)
    yield path
    os.remove(path)


def _pipeline(db_path):
    def fn(database_id, question):
        # Map the two known questions to SQL; run to capture columns/rows.
        sql = ("SELECT club_id FROM clubs WHERE budget > 5000"
               if "5000" in question else
               "SELECT club_id FROM clubs WHERE budget > 3000")
        conn = sqlite3.connect(db_path)
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        conn.close()
        return {
            "success": True, "selected_candidate_source": "test",
            "selected_candidate_score": 90.0, "low_confidence": False,
            "warnings": [], "selected_candidate_validation": {"fatal": []},
            "generated_sql": {"generated": True, "sql": sql, "params": []},
            "execution": {"executed": True, "columns": cols,
                          "rows": [list(r) for r in rows], "row_count": len(rows)},
        }
    return fn


def test_end_to_end_pairwise_preserved_and_analysis(db):
    req = ContainmentBatchRequest(queries=[
        "clubs with budget over 5000", "clubs with budget over 3000"])
    resp = check_containment_batch(1, req, _pipeline(db))
    # Pairwise preserved exactly (one pair, real relationship).
    assert len(resp.pairwise_relationships) == 1
    assert resp.pairwise_relationships[0].relationship == "query_a_contained_in_query_b"
    # Analysis attached and consistent.
    assert resp.analysis is not None
    assert resp.analysis.query_count == 2
    edges = {(e.superset, e.subset) for e in resp.analysis.containment_edges}
    assert edges == {(2, 1)}          # Q2 (>3000) is the superset of Q1 (>5000)
    assert [m.index for m in resp.analysis.main_queries] == [2]
