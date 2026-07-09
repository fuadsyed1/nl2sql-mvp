"""
test_containment_step3.py — offline tests for containment Step 3 (safe DISTINCT
key-set comparison).

No server, no LLM. A temporary SQLite database is built and
containment.checker.get_database_path is monkeypatched to point at it.

    python -m pytest backend/tests/test_containment_step3.py -q
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
            (3,'Gamma','LA',2500),
            (4,'Delta','SF',3500);
        CREATE TABLE students(student_id INTEGER PRIMARY KEY, student_name TEXT);
        INSERT INTO students VALUES (1,'S1'),(2,'S2');
        """
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(checker, "get_database_path", lambda database_id: path)
    yield path
    os.remove(path)


def _qr(qid, sql, db_path):
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
    return _classify_pair(DB_ID, _qr(1, sql_a, db_path), _qr(2, sql_b, db_path))


def test_distinct_canonical_key_different_descriptive_cols(db):
    # Both expose club_id (canonical) but different second columns.
    a = "SELECT DISTINCT club_id, club_name FROM clubs WHERE budget > 2000"
    b = "SELECT DISTINCT club_id, city FROM clubs WHERE budget > 3000"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert rel != "unknown"
    assert compared_on == "distinct_key:club_id"
    # budget>3000 clubs subset of budget>2000 clubs -> b in a.
    assert rel == "query_b_contained_in_query_a"


def test_distinct_city_superset_subset(db):
    a = "SELECT DISTINCT city FROM clubs"
    b = "SELECT DISTINCT city FROM clubs WHERE budget > 3000"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert compared_on == "distinct_keys:city"
    # {NY,SF} subset of {NY,LA,SF} -> b in a.
    assert rel == "query_b_contained_in_query_a"


def test_distinct_with_limit_unknown(db):
    a = "SELECT DISTINCT city FROM clubs ORDER BY city LIMIT 2"
    b = "SELECT DISTINCT city FROM clubs"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert rel == "unknown"
    assert compared_on is None
    assert "limit/top-k" in expl


def test_distinct_with_aggregate_unknown(db):
    a = "SELECT DISTINCT COUNT(*) AS n FROM clubs"
    b = "SELECT DISTINCT city FROM clubs"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert rel == "unknown"
    assert compared_on is None
    assert "aggregate" in expl


def test_distinct_with_setop_unknown(db):
    a = "SELECT DISTINCT city FROM clubs UNION SELECT city FROM clubs"
    b = "SELECT DISTINCT city FROM clubs"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert rel == "unknown"
    assert compared_on is None


def test_distinct_different_entities_unknown(db):
    # No shared canonical key and different selected columns -> not comparable.
    a = "SELECT DISTINCT city FROM clubs"
    b = "SELECT DISTINCT club_name FROM clubs"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert rel == "unknown"
    assert compared_on is None
    assert "different selected columns" in expl


def test_distinct_different_entity_keys_unknown(db):
    # club_id vs student_id: different canonical keys -> unknown.
    a = "SELECT DISTINCT club_id FROM clubs"
    b = "SELECT DISTINCT student_id FROM students"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert rel == "unknown"
    assert compared_on is None
