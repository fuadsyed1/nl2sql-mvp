"""Unit tests for sql_candidates.execution_probes (Option A).

The probes are advisory: they run read-only SQL against a real temp SQLite
database and add a warning + small score penalty, never a fatal error and
never a rejection based on emptiness alone.

Contract checked here:
  * a contradictory zero-row query (relaxed form returns rows) is warned;
  * a legitimately empty query with no NOT EXISTS / HAVING is untouched;
  * a COUNT(*) aggregate over 2+ joins that fans out is warned;
  * the same shape using COUNT(DISTINCT id) is NOT warned;
  * a probe against an unusable database never raises;
  * plain, simple SQL is left completely unaffected.
"""

import os
import sqlite3
import tempfile

from sql_candidates.candidate_types import SqlCandidate
from sql_candidates.execution_probes import (
    annotate_with_probes,
    CONTRADICTION_WARNING,
    FANOUT_WARNING,
    CONTRADICTION_PENALTY,
    FANOUT_PENALTY,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _make_db(script):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript(script)
    conn.commit()
    conn.close()
    return path


def _exec(sql, path):
    """Run sql for real so the candidate's execution result is truthful."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in (cur.description or [])]
        rows = [list(r) for r in cur.fetchall()]
    finally:
        conn.close()
    return {"executed": True, "columns": cols, "rows": rows,
            "row_count": len(rows), "truncated": False, "diagnostics": {}}


def _cand(sql, path, score=80.0):
    c = SqlCandidate(source="llm_sql_direct", label="llm_sql_direct", sql=sql)
    c.execution = _exec(sql, path)
    c.score = score
    return c


_JOIN_DB = """
CREATE TABLE events (id INTEGER PRIMARY KEY, dept TEXT);
CREATE TABLE attendance (event_id INTEGER);
CREATE TABLE sponsors (event_id INTEGER);
INSERT INTO events VALUES (1,'A'),(2,'A'),(3,'B');
INSERT INTO attendance VALUES (1),(1),(2);
INSERT INTO sponsors VALUES (1),(1),(2);
"""

_MEMBER_DB = """
CREATE TABLE person (id INTEGER PRIMARY KEY);
CREATE TABLE membership (person_id INTEGER);
INSERT INTO person VALUES (1),(2);
INSERT INTO membership VALUES (1);
"""


# ---------------------------------------------------------------------------
# contradiction probe
# ---------------------------------------------------------------------------
def test_contradiction_query_gets_warning_and_penalty():
    path = _make_db(_MEMBER_DB)
    try:
        sql = ("SELECT p.id FROM person p "
               "WHERE NOT EXISTS (SELECT 1 FROM membership m "
               "WHERE m.person_id = p.id) "
               "AND p.id IN (SELECT person_id FROM membership)")
        c = _cand(sql, path, score=80.0)
        assert c.execution["row_count"] == 0        # genuinely empty
        annotate_with_probes(c, path)
        assert CONTRADICTION_WARNING in c.reasons
        assert c.score == 80.0 - CONTRADICTION_PENALTY
        assert c.validation["probes"]["checks"]["contradiction"][
            "relaxed_returned_rows"] is True
    finally:
        os.remove(path)


def test_legit_empty_query_without_notexists_or_having_is_untouched():
    path = _make_db(_MEMBER_DB)
    try:
        sql = "SELECT id FROM person WHERE id = 999"
        c = _cand(sql, path, score=77.0)
        assert c.execution["row_count"] == 0
        annotate_with_probes(c, path)
        assert CONTRADICTION_WARNING not in c.reasons
        assert c.score == 77.0                       # no penalty for emptiness
        # contradiction probe did not even run (no NOT EXISTS / HAVING)
        assert "contradiction" not in c.validation["probes"]["checks"]
    finally:
        os.remove(path)


def test_having_only_empty_but_satisfiable_is_warned():
    path = _make_db(_JOIN_DB)
    try:
        sql = ("SELECT dept, COUNT(*) c FROM events GROUP BY dept "
               "HAVING COUNT(*) > 100")
        c = _cand(sql, path, score=70.0)
        assert c.execution["row_count"] == 0
        annotate_with_probes(c, path)
        assert CONTRADICTION_WARNING in c.reasons
        assert c.score == 70.0 - CONTRADICTION_PENALTY
    finally:
        os.remove(path)


# ---------------------------------------------------------------------------
# fanout probe
# ---------------------------------------------------------------------------
def test_count_star_over_multijoin_gets_fanout_warning():
    path = _make_db(_JOIN_DB)
    try:
        sql = ("SELECT e.dept, COUNT(*) FROM events e "
               "JOIN attendance a ON a.event_id = e.id "
               "JOIN sponsors s ON s.event_id = e.id "
               "GROUP BY e.dept")
        c = _cand(sql, path, score=85.0)
        annotate_with_probes(c, path)
        assert FANOUT_WARNING in c.reasons
        assert c.score == 85.0 - FANOUT_PENALTY
        chk = c.validation["probes"]["checks"]["fanout"]
        assert chk["count_star"] > chk["count_distinct_driver"]
    finally:
        os.remove(path)


def test_count_distinct_over_multijoin_is_not_warned():
    path = _make_db(_JOIN_DB)
    try:
        sql = ("SELECT e.dept, COUNT(DISTINCT e.id) FROM events e "
               "JOIN attendance a ON a.event_id = e.id "
               "JOIN sponsors s ON s.event_id = e.id "
               "GROUP BY e.dept")
        c = _cand(sql, path, score=85.0)
        annotate_with_probes(c, path)
        assert FANOUT_WARNING not in c.reasons
        assert c.score == 85.0                       # no penalty
    finally:
        os.remove(path)


# ---------------------------------------------------------------------------
# safety
# ---------------------------------------------------------------------------
def test_probe_failure_does_not_raise_or_penalize():
    # db_path points nowhere: the relaxed/probe execution fails -> ignored.
    sql = ("SELECT p.id FROM person p "
           "WHERE NOT EXISTS (SELECT 1 FROM membership m "
           "WHERE m.person_id = p.id)")
    c = SqlCandidate(source="llm_sql_direct", label="llm_sql_direct", sql=sql)
    c.execution = {"executed": True, "columns": ["id"], "rows": [],
                   "row_count": 0, "truncated": False, "diagnostics": {}}
    c.score = 60.0
    result = annotate_with_probes(c, "/nonexistent/dir/missing.db")
    assert result["warnings"] == []
    assert c.score == 60.0
    assert CONTRADICTION_WARNING not in (c.reasons or [])


def test_simple_sql_is_unaffected():
    path = _make_db(_MEMBER_DB)
    try:
        sql = "SELECT id FROM person"
        c = _cand(sql, path, score=90.0)
        assert c.execution["row_count"] > 0
        annotate_with_probes(c, path)
        assert c.reasons in ([], None) or (
            CONTRADICTION_WARNING not in c.reasons
            and FANOUT_WARNING not in c.reasons)
        assert c.score == 90.0
        assert c.validation["probes"]["warnings"] == []
    finally:
        os.remove(path)


def test_non_executed_candidate_is_skipped():
    c = SqlCandidate(source="llm_sql_direct", label="llm_sql_direct",
                     sql="SELECT 1")
    c.execution = {"executed": False, "reason": "sql_error", "rows": [],
                   "row_count": 0, "columns": []}
    c.score = 30.0
    result = annotate_with_probes(c, "/whatever.db")
    assert result == {"warnings": [], "penalty": 0.0, "checks": {}}
    assert c.score == 30.0
