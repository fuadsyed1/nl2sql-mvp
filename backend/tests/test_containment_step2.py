"""
test_containment_step2.py — offline tests for containment Step 2 (safe GROUP BY
group-key comparison), plus a Step-1 canonical-key regression.

No server, no LLM. A temporary SQLite database is built and
containment.checker.get_database_path is monkeypatched to point at it, so the
whole containment classification runs against real SQLite via EXCEPT.

    python -m pytest backend/tests/test_containment_step2.py -q
"""

import os
import sqlite3
import tempfile

import pytest

import containment.checker as checker
from containment.models import BatchQueryResult
from containment.service import _classify_pair

DB_ID = 1


@pytest.fixture()
def db(monkeypatch):
    """Build a campus-style DB and point the checker at it."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE clubs(club_id INTEGER PRIMARY KEY, club_name TEXT,
                           city TEXT, budget INTEGER);
        INSERT INTO clubs VALUES
            (1,'Alpha','NY',6000),
            (2,'Beta','NY',4000),
            (3,'Gamma','LA',2000),
            (4,'Delta','SF',3500);
        CREATE TABLE events(event_id INTEGER PRIMARY KEY, club_id INTEGER,
                            attendance INTEGER);
        INSERT INTO events VALUES
            (1,1,150),(2,1,50),(3,2,200),(4,3,10),(5,4,120);
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(checker, "get_database_path", lambda database_id: path)
    yield path
    os.remove(path)


def _qr(qid, sql, db_path):
    """Build a BatchQueryResult by running the SQL to capture real output
    columns and row count (mirrors what the pipeline projection would carry)."""
    conn = sqlite3.connect(db_path)
    cur = conn.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    conn.close()
    return BatchQueryResult(
        query_id=qid, question=f"q{qid}", success=True, sql=sql, params=[],
        execution_columns=cols, row_count=len(rows), safe=True,
        empty_result=(len(rows) == 0),
    )


def classify(db_path, sql_a, sql_b):
    rel, expl, amb, bma, compared_on = _classify_pair(
        DB_ID, _qr(1, sql_a, db_path), _qr(2, sql_b, db_path)
    )
    return rel, expl, amb, bma, compared_on


# ---------------------------------------------------------------------------
# Step 2 tests
# ---------------------------------------------------------------------------

def test_same_group_entity_different_aggregate_cols_not_unknown(db):
    # Same group key (club_id), different aggregate columns (COUNT vs SUM).
    a = "SELECT club_id, COUNT(*) AS cnt FROM events GROUP BY club_id"
    b = "SELECT club_id, SUM(attendance) AS total FROM events GROUP BY club_id"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert rel != "unknown"
    assert compared_on == "group_key:club_id"
    # Same set of clubs in both -> equivalent on group key (counts ignored).
    assert rel == "equivalent_on_current_database"


def test_grouped_matching_columns_compares_keys_not_counts(db):
    # Identical output columns [club_id, cnt] but different counts due to HAVING/
    # WHERE. Full-tuple EXCEPT would call these incomparable; group-key must not.
    a = "SELECT club_id, COUNT(*) AS cnt FROM events GROUP BY club_id"
    b = ("SELECT club_id, COUNT(*) AS cnt FROM events WHERE attendance > 100 "
         "GROUP BY club_id")
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert compared_on == "group_key:club_id"
    # b's clubs (1,2,4) are a subset of a's clubs (1,2,3,4) -> b contained in a.
    assert rel == "query_b_contained_in_query_a"


def test_group_by_city_superset_subset(db):
    a = "SELECT city, COUNT(*) AS n FROM clubs GROUP BY city"
    b = "SELECT city, COUNT(*) AS n FROM clubs WHERE budget > 3000 GROUP BY city"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert compared_on == "group_keys:city"
    # budget>3000 cities {NY,SF} subset of all cities {NY,LA,SF} -> b in a.
    assert rel == "query_b_contained_in_query_a"


def test_having_is_preserved(db):
    a = "SELECT city, COUNT(*) AS n FROM clubs GROUP BY city"
    b = "SELECT city, COUNT(*) AS n FROM clubs GROUP BY city HAVING COUNT(*) >= 2"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert compared_on == "group_keys:city"
    # Only NY has >=2 clubs -> b groups {NY} subset of a {NY,LA,SF} -> b in a.
    assert rel == "query_b_contained_in_query_a"


def test_limit_grouped_remains_unknown(db):
    a = ("SELECT city, COUNT(*) AS n FROM clubs GROUP BY city "
         "ORDER BY n DESC LIMIT 2")
    b = "SELECT city, COUNT(*) AS n FROM clubs GROUP BY city"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert rel == "unknown"
    assert compared_on is None
    assert "limit/top-k" in expl


def test_setop_grouped_remains_unknown(db):
    a = ("SELECT city FROM clubs GROUP BY city "
         "UNION SELECT city FROM clubs GROUP BY city")
    b = "SELECT city, COUNT(*) AS n FROM clubs GROUP BY city"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert rel == "unknown"
    assert compared_on is None


def test_unexposed_group_key_now_compares(db):
    # Groups by city but does NOT select city. The comparison SQL rewrites the
    # projection to the GROUP BY key, so it now compares on city (no longer
    # "unknown: group key not exposed").
    a = "SELECT COUNT(*) AS n FROM clubs GROUP BY city"
    b = "SELECT city, COUNT(*) AS n FROM clubs GROUP BY city"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert compared_on == "group_keys:city"
    assert rel == "equivalent_on_current_database"


# ---------------------------------------------------------------------------
# Step 1 regression (must still pass, unchanged)
# ---------------------------------------------------------------------------

def test_step1_canonical_key_still_works(db):
    a = "SELECT club_id, club_name FROM clubs WHERE budget > 3000"
    b = "SELECT club_name FROM clubs WHERE budget > 5000"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert compared_on == "canonical_key:club_id"
    # budget>5000 (Alpha) subset of budget>3000 (Alpha,Beta,Delta) -> b in a.
    assert rel == "query_b_contained_in_query_a"


def test_step1_plain_matching_columns_unchanged(db):
    a = "SELECT club_id FROM clubs WHERE budget > 3000"
    b = "SELECT club_id FROM clubs WHERE budget > 5000"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert compared_on == "output_columns"
    assert rel == "query_b_contained_in_query_a"
