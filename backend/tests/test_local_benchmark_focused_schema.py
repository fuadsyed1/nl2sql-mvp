"""
test_local_benchmark_focused_schema.py

Schema-linker must NOT expand must_use_tables to the whole related-table
neighborhood on big / local-benchmark schemas (shared keys like playerID must
not pull in every table). And the scorer must reject SQL that joins tables
outside the checklist's must_use_tables.
"""

from semantic.schema_linker import correct_checklist_tables
from sql_candidates.candidate_scorer import score_candidate
from sql_candidates.candidate_types import SqlCandidate


def _col(n):
    return {"column_name": n, "data_type": "INTEGER"}


def _lahman_graph():
    # Lahman-style: many tables sharing playerID, no declared FK edges.
    return {"tables": [
        {"table_name": "people", "columns": [
            _col("playerID"), _col("nameFirst"), _col("nameLast"),
            _col("birthYear")]},
        {"table_name": "batting", "columns": [
            _col("playerID"), _col("yearID"), _col("teamID"), _col("HR")]},
        {"table_name": "appearances", "columns": [
            _col("playerID"), _col("yearID"), _col("G_lf"), _col("G_of")]},
        {"table_name": "pitching", "columns": [
            _col("playerID"), _col("yearID"), _col("ERA")]},
        {"table_name": "fielding", "columns": [
            _col("playerID"), _col("yearID"), _col("PO")]},
        {"table_name": "salaries", "columns": [
            _col("playerID"), _col("yearID"), _col("salary")]},
    ], "relationships": []}


def _must(q, cl):
    return set(correct_checklist_tables(q, cl, _lahman_graph())["must_use_tables"])


# ---------------------------------------------------------------------------
# schema-linker focus
# ---------------------------------------------------------------------------

def test_people_only_stays_focused():
    q = "Show playerID, nameFirst, nameLast, birthYear from People limit 10"
    cl = {"must_use_tables": ["people"],
          "must_use_columns": ["people.playerid", "people.namefirst",
                               "people.namelast", "people.birthyear"]}
    assert _must(q, cl) == {"people"}


def test_batting_only_stays_focused():
    q = "Find the top 10 rows from Batting by home runs. Show playerID, yearID, teamID, HR."
    cl = {"must_use_tables": ["batting"],
          "must_use_columns": ["batting.playerid", "batting.yearid",
                               "batting.teamid", "batting.hr"]}
    assert _must(q, cl) == {"batting"}


def test_people_and_batting_two_tables_only():
    q = ("Join People and Batting using playerID. Show player names, yearID, "
         "teamID, and home runs for rows where HR is greater than 50.")
    cl = {"must_use_tables": ["people", "batting"],
          "must_use_columns": ["people.namefirst", "people.namelast",
                               "batting.yearid", "batting.teamid", "batting.hr"]}
    assert _must(q, cl) == {"people", "batting"}


def test_count_people_regression():
    q = "Count the number of rows in People"
    cl = {"must_use_tables": ["people"], "must_use_columns": ["people.playerid"]}
    m = _must(q, cl)
    assert m == {"people"}


def test_shared_key_does_not_expand_without_columns():
    # Even without must_use_columns, a bare People target must not expand to all
    # playerID tables via the (hardened) metric step.
    q = "Show playerID, nameFirst, nameLast, birthYear from People limit 10"
    m = _must(q, {"must_use_tables": ["people"]})
    assert "people" in m
    assert not ({"batting", "appearances", "pitching", "fielding", "salaries"} & m)


# ---------------------------------------------------------------------------
# scorer: reject joins outside must_use_tables
# ---------------------------------------------------------------------------

def _cand(sql):
    c = SqlCandidate(source="llm_sql_direct", label="t", sql=sql)
    c.execution = {"executed": True, "columns": ["playerID"], "rows": [[1]],
                   "row_count": 1}
    return c


def test_scorer_rejects_join_outside_must_use_tables():
    graph = _lahman_graph()
    cl = {"must_use_tables": ["people"]}
    sql = ("SELECT p.playerID, p.nameFirst FROM people p "
           "JOIN batting b ON p.playerID = b.playerID LIMIT 10")
    c = score_candidate("Show players from People", _cand(sql), graph, checklist=cl)
    assert "batting" in (c.validation.get("outside_tables") or [])
    assert any("outside must_use_tables" in f for f in c.validation.get("fatal", []))


def test_scorer_allows_single_table_no_join():
    graph = _lahman_graph()
    cl = {"must_use_tables": ["people"]}
    sql = "SELECT playerID, nameFirst, nameLast, birthYear FROM people LIMIT 10"
    c = score_candidate("Show players from People", _cand(sql), graph, checklist=cl)
    assert (c.validation.get("outside_tables") or []) == []
    assert not any("outside must_use_tables" in f for f in c.validation.get("fatal", []))
