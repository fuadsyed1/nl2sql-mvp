"""
test_containment_step4.py — offline tests for containment Step 4 (deterministic
safe-refusal reasons for shapes we do not normalize yet), plus Step 2 / Step 3
success regressions.

    python -m pytest backend/tests/test_containment_step4.py -q
"""

import os
import sqlite3
import tempfile

import pytest

import containment.checker as checker
from containment.checker import (
    REASON_SETOP,
    REASON_LIMIT,
    REASON_SCALAR_AGG,
    REASON_NO_COMMON_KEY,
)
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
        CREATE TABLE events(event_id INTEGER PRIMARY KEY, club_id INTEGER,
                            attendance INTEGER);
        INSERT INTO events VALUES
            (1,1,150),(2,1,50),(3,2,200),(4,3,10),(5,4,120);
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


# ---------------------------------------------------------------------------
# Set operations -> unknown with the set-op reason
# ---------------------------------------------------------------------------

def test_union_unknown_setop_reason(db):
    a = "SELECT city FROM clubs UNION SELECT city FROM clubs"
    b = "SELECT city FROM clubs"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert rel == "unknown"
    assert compared_on is None
    assert REASON_SETOP in expl


def test_intersect_unknown_setop_reason(db):
    a = "SELECT city FROM clubs INTERSECT SELECT city FROM clubs WHERE budget > 3000"
    b = "SELECT city FROM clubs"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert rel == "unknown"
    assert REASON_SETOP in expl


def test_except_unknown_setop_reason(db):
    a = "SELECT city FROM clubs EXCEPT SELECT city FROM clubs WHERE budget > 3000"
    b = "SELECT city FROM clubs"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert rel == "unknown"
    assert REASON_SETOP in expl


# ---------------------------------------------------------------------------
# LIMIT / top-k -> unknown with the limit reason
# ---------------------------------------------------------------------------

def test_limit_grouped_unknown_limit_reason(db):
    a = "SELECT city, COUNT(*) AS n FROM clubs GROUP BY city LIMIT 2"
    b = "SELECT city, COUNT(*) AS n FROM clubs GROUP BY city"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert rel == "unknown"
    assert compared_on is None
    assert REASON_LIMIT in expl


def test_limit_distinct_unknown_limit_reason(db):
    a = "SELECT DISTINCT city FROM clubs LIMIT 2"
    b = "SELECT DISTINCT city FROM clubs"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert rel == "unknown"
    assert REASON_LIMIT in expl


# ---------------------------------------------------------------------------
# Scalar aggregate -> unknown; different entities -> unknown
# ---------------------------------------------------------------------------

def test_scalar_count_unknown_scalar_reason(db):
    a = "SELECT COUNT(*) AS n FROM clubs"
    b = "SELECT COUNT(*) AS n FROM clubs WHERE budget > 3000"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert rel == "unknown"
    assert compared_on is None
    assert REASON_SCALAR_AGG in expl


def test_different_entities_unknown_common_key_reason(db):
    a = "SELECT club_id FROM clubs"
    b = "SELECT student_id FROM students"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert rel == "unknown"
    assert compared_on is None
    assert REASON_NO_COMMON_KEY in expl


# ---------------------------------------------------------------------------
# Step 2 / Step 3 success must not regress
# ---------------------------------------------------------------------------

def test_step2_grouped_success_not_regressed(db):
    a = "SELECT club_id, COUNT(*) AS n FROM events GROUP BY club_id"
    b = ("SELECT club_id, COUNT(*) AS n FROM events WHERE attendance > 100 "
         "GROUP BY club_id")
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert compared_on == "group_key:club_id"
    assert rel == "query_b_contained_in_query_a"


def test_step3_distinct_success_not_regressed(db):
    a = "SELECT DISTINCT city FROM clubs"
    b = "SELECT DISTINCT city FROM clubs WHERE budget > 3000"
    rel, expl, amb, bma, compared_on = classify(db, a, b)
    assert compared_on == "distinct_keys:city"
    assert rel == "query_b_contained_in_query_a"
