"""
test_benchmark_relationships.py

Trusted relationship + canonical-key layer for local benchmarks (Lahman): valid
joins must become legal, and ambiguous multi-id tables (Teams) must get a
canonical key — all backend-only (no persistence, no UI).
"""

import sqlite3

from local_benchmarks.benchmark_relationships import (
    augment_graph, canonical_keys,
)
from query_families.slot_extractor import index_schema, is_legal_edge
from sql_candidates.candidate_scorer import score_candidate
from sql_candidates.candidate_types import SqlCandidate
import containment.checker as checker


def _c(name, pk=False):
    return {"column_name": name, "data_type": "TEXT",
            "is_primary_key_candidate": pk}


def _lahman_graph():
    # People.playerID unique (key); child playerID columns are NOT unique.
    return {"tables": [
        {"table_name": "people", "columns": [
            _c("playerid", pk=True), _c("namefirst"), _c("namelast"), _c("birthyear")]},
        {"table_name": "batting", "columns": [
            _c("playerid"), _c("yearid"), _c("teamid"), _c("lgid"), _c("hr")]},
        {"table_name": "pitching", "columns": [
            _c("playerid"), _c("yearid"), _c("era")]},
        {"table_name": "teams", "columns": [
            _c("yearid"), _c("teamid"), _c("lgid"), _c("franchid"), _c("name")]},
        {"table_name": "halloffame", "columns": [
            _c("playerid"), _c("yearid"), _c("inducted")]},
    ], "relationships": []}


def test_augment_adds_trusted_edges_without_mutating_source():
    g = _lahman_graph()
    aug = augment_graph(g)
    pairs = {frozenset({(r["from_table"], r["from_column"]),
                        (r["to_table"], r["to_column"])})
             for r in aug["relationships"]}
    assert frozenset({("batting", "playerid"), ("people", "playerid")}) in pairs
    assert frozenset({("batting", "teamid"), ("teams", "teamid")}) in pairs
    assert g["relationships"] == []   # source graph untouched


def test_non_benchmark_graph_unchanged():
    g = {"tables": [
        {"table_name": "foo", "columns": [_c("id", pk=True)]},
        {"table_name": "bar", "columns": [_c("x")]}],
        "relationships": []}
    assert augment_graph(g) is g


def test_illegal_join_becomes_legal_after_augment():
    idx0 = index_schema(_lahman_graph())
    assert is_legal_edge(idx0, "batting", "playerid", "people", "playerid") is False
    idx1 = index_schema(augment_graph(_lahman_graph()))
    assert is_legal_edge(idx1, "batting", "playerid", "people", "playerid") is True
    assert is_legal_edge(idx1, "pitching", "playerid", "people", "playerid") is True


def test_scorer_no_illegal_fatal_after_augment():
    graph = augment_graph(_lahman_graph())
    sql = ("SELECT p.nameFirst, p.nameLast, SUM(b.HR) FROM Batting b "
           "JOIN People p ON b.playerID = p.playerID "
           "GROUP BY b.playerID HAVING SUM(b.HR) > 500")
    c = SqlCandidate(source="llm_sql_direct", label="t", sql=sql)
    c.execution = {"executed": True, "columns": ["nameFirst", "nameLast", "hr"],
                   "rows": [["a", "b", 600]], "row_count": 1}
    score_candidate("players with career home runs over 500", c, graph,
                    checklist={"must_use_tables": ["batting", "people"]})
    assert not any("illegal join" in f.lower() for f in c.validation.get("fatal", []))


def test_canonical_keys_registry():
    ck = canonical_keys({"people", "batting", "pitching", "teams", "halloffame"})
    assert ck.get("teams") == ["teamid", "yearid", "lgid"]
    assert ck.get("people") == ["playerid"]
    assert canonical_keys({"foo", "bar"}) == {}


def test_containment_teams_canonical_key(monkeypatch, tmp_path):
    p = str(tmp_path / "lahman.sqlite")
    conn = sqlite3.connect(p)
    conn.executescript(
        "CREATE TABLE people(playerid TEXT, namefirst TEXT);"
        "CREATE TABLE batting(playerid TEXT, yearid INT, teamid TEXT);"
        "CREATE TABLE pitching(playerid TEXT, yearid INT);"
        "CREATE TABLE halloffame(playerid TEXT, inducted TEXT);"
        "CREATE TABLE teams(yearid INT, teamid TEXT, lgid TEXT, name TEXT);"
        "INSERT INTO teams VALUES (2000,'NYA','AL','Yankees'),(2000,'BOS','AL','Red Sox');"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(checker, "get_database_path", lambda db_id: p)

    # Output drops any single id column -> generic id-like keying is ambiguous;
    # the benchmark canonical key (teamid, yearid, lgid) resolves it.
    res = checker.build_key_comparison(1, "SELECT name FROM teams WHERE lgid = 'AL'", ["name"])
    assert res["ok"] is True
    assert res["key"] == "lgid,teamid,yearid"
    for col in ("teamid", "yearid", "lgid"):
        assert col in res["comparison_sql"]


# ---------------------------------------------------------------------------
# Canonical comparison SQL: grouped-without-output-key + joined answer key
# ---------------------------------------------------------------------------

def _lahman_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE people(playerID TEXT, nameFirst TEXT, nameLast TEXT);"
        "CREATE TABLE batting(playerID TEXT, yearID INT, teamID TEXT, lgID TEXT, HR INT, RBI INT);"
        "CREATE TABLE pitching(playerID TEXT, yearID INT, ERA REAL);"
        "CREATE TABLE teams(yearID INT, teamID TEXT, lgID TEXT, name TEXT, W INT);"
        "CREATE TABLE halloffame(playerID TEXT, yearID INT, inducted TEXT);"
        "INSERT INTO people VALUES ('a01','Al','A'),('b01','Bob','B'),('c01','Cal','C');"
        "INSERT INTO batting VALUES "
        "('a01',2000,'NYA','AL',60,200),('a01',2001,'NYA','AL',10,30),"
        "('b01',2000,'BOS','AL',40,100),('c01',2000,'LAN','NL',5,10);"
        "INSERT INTO teams VALUES "
        "(2000,'NYA','AL','Yankees',95),(2001,'NYA','AL','Yankees',90),"
        "(2000,'BOS','AL','Red Sox',85),(2000,'LAN','NL','Dodgers',80);"
    )
    conn.commit()
    conn.close()


import pytest
from containment.models import BatchQueryResult
from containment.service import _classify_pair


@pytest.fixture()
def lahman(monkeypatch, tmp_path):
    p = str(tmp_path / "lahman.sqlite")
    _lahman_db(p)
    monkeypatch.setattr(checker, "get_database_path", lambda db_id: p)
    return p


def _qr(qid, sql, p):
    conn = sqlite3.connect(p)
    cur = conn.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    conn.close()
    return BatchQueryResult(
        query_id=qid, question=f"q{qid}", success=True, sql=sql, params=[],
        execution_columns=cols, row_count=len(rows), safe=True,
        empty_result=(len(rows) == 0))


def _classify(p, sa, sb):
    return _classify_pair(1, _qr(1, sa, p), _qr(2, sb, p))


def test_case2_grouped_career_display_without_playerid(lahman):
    # Display shows only names; comparison happens on the GROUP BY key playerID.
    a = ("SELECT p.nameFirst FROM batting b JOIN people p ON b.playerID = p.playerID "
         "GROUP BY b.playerID HAVING SUM(b.HR) > 50")
    b = ("SELECT p.nameFirst FROM batting b JOIN people p ON b.playerID = p.playerID "
         "GROUP BY b.playerID HAVING SUM(b.HR) > 30")
    rel, expl, amb, bma, co = _classify(lahman, a, b)
    assert co == "group_key:playerid"
    assert rel == "query_a_contained_in_query_b"   # HR>50 subset of HR>30


def test_joined_answer_key_direct(lahman):
    res = checker.build_key_comparison(
        1, "SELECT p.nameFirst FROM batting b JOIN people p "
           "ON b.playerID = p.playerID WHERE b.HR > 50", ["nameFirst"])
    assert res["ok"] is True
    assert res["strategy"] == "benchmark_answer_key"
    assert res["key"] == "lgid,playerid,teamid,yearid"
    assert "b.playerid" in res["comparison_sql"]


def test_case5_season_join_answer_key(lahman):
    # Different display columns -> Step 1 -> compared on batting season key.
    a = ("SELECT p.nameFirst FROM batting b JOIN people p ON b.playerID = p.playerID "
         "JOIN teams t ON b.yearID = t.yearID AND b.teamID = t.teamID AND b.lgID = t.lgID "
         "WHERE b.HR > 50")
    b = ("SELECT p.nameFirst, p.nameLast FROM batting b JOIN people p ON b.playerID = p.playerID "
         "JOIN teams t ON b.yearID = t.yearID AND b.teamID = t.teamID AND b.lgID = t.lgID "
         "WHERE b.HR > 20")
    rel, expl, amb, bma, co = _classify(lahman, a, b)
    assert co and co.startswith("canonical_key:")
    assert rel == "query_a_contained_in_query_b"


def test_case10_team_name_display_uses_teams_key(lahman):
    a = "SELECT name FROM teams WHERE lgID = 'AL' AND yearID = 2000"
    b = "SELECT name, teamID FROM teams WHERE lgID = 'AL'"
    rel, expl, amb, bma, co = _classify(lahman, a, b)
    assert co and co.startswith("canonical_key:")
    assert rel == "query_a_contained_in_query_b"
