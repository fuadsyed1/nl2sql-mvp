"""Focused tests for generic repaired-SQL validity.

Covers the invalid outer-HAVING shape (a non-aggregate outer SELECT that filters
a PRECOMPUTED CTE/subquery column with HAVING instead of WHERE, which SQLite
rejects) and the deterministic, provably-safe HAVING->WHERE normalization.

Everything uses ABSTRACT tables (groups / members / events) — no DB, table,
column, or test-id specific logic anywhere. The generic detector/normalizer is
exercised on shapes structurally equivalent to real multi-table repairs.
"""
import sqlite3
import pytest

from sql_candidates.repair_normalize import (
    outer_having_invalid, safe_having_to_where,
)


# --------------------------------------------------------------------------- #
# Abstract fixture DB. `groups` are the entity population; `members` belong to
# groups (some active); `events` are facts carrying their OWN member FK. This is
# structurally the same shape as any "per-entity rate over two populations"
# repair, with zero domain meaning.
# --------------------------------------------------------------------------- #
def _db():
    con = sqlite3.connect(":memory:")
    con.executescript(
        """
        CREATE TABLE groups  (group_id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE members (member_id INTEGER PRIMARY KEY, group_id INTEGER,
                              active INTEGER);
        CREATE TABLE events  (event_id INTEGER PRIMARY KEY, group_id INTEGER,
                              member_id INTEGER, magnitude INTEGER);
        INSERT INTO groups VALUES (1,'a'),(2,'b'),(3,'c');
        -- group 1: 2 active members; group 2: 1 active; group 3: 0 active
        INSERT INTO members VALUES (10,1,1),(11,1,1),(12,2,1),(13,3,0);
        -- events attributed by their own member/group FK
        INSERT INTO events VALUES (100,1,10,5),(101,1,11,3),(102,2,12,7);
        """
    )
    return con


def _runs(con, sql):
    """Execute; return (ok, rows_or_error)."""
    try:
        cur = con.execute(sql)
        return True, cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


# The DB57-shaped invalid repair: numerator and denominator pre-aggregated in
# INDEPENDENT CTEs, joined to the entity, then a non-aggregate outer SELECT that
# filters a precomputed column with HAVING (invalid).
INVALID_DB57_SHAPE = """
WITH miss AS (
    SELECT group_id AS g, SUM(magnitude) AS total_magnitude
    FROM events GROUP BY group_id
),
act AS (
    SELECT group_id AS g, COUNT(DISTINCT member_id) AS active_member_count
    FROM members WHERE active = 1 GROUP BY group_id
)
SELECT g.group_id,
       CAST(miss.total_magnitude AS REAL) / act.active_member_count AS rate
FROM groups g
JOIN miss ON miss.g = g.group_id
JOIN act  ON act.g  = g.group_id
HAVING act.active_member_count > 0
"""

# The safe target form: the SAME query with the precomputed-column filter in
# WHERE instead of HAVING.
VALID_WHERE_SHAPE = INVALID_DB57_SHAPE.replace(
    "HAVING act.active_member_count > 0", "WHERE act.active_member_count > 0")


# --------------------------------------------------------------------------- #
# 1. Detection: non-aggregate outer SELECT with HAVING on a precomputed column
#    is flagged invalid.
# --------------------------------------------------------------------------- #
def test_01_invalid_outer_having_detected():
    assert outer_having_invalid(INVALID_DB57_SHAPE) is True


# 2. The safe WHERE form is accepted (detector does NOT flag it).
def test_02_safe_where_form_not_flagged():
    assert outer_having_invalid(VALID_WHERE_SHAPE) is False


# 3. Normalizer moves the invalid HAVING to WHERE.
def test_03_normalizer_moves_having_to_where():
    fixed, action = safe_having_to_where(INVALID_DB57_SHAPE)
    assert action == "normalized_having_to_where"
    assert fixed is not None
    low = fixed.lower()
    assert "having" not in low
    assert "where" in low
    assert "active_member_count > 0" in low


# 4. A legitimately grouped outer SELECT with HAVING (aggregate query) is NOT
#    flagged and NOT rewritten.
def test_04_grouped_having_is_valid():
    sql = ("SELECT group_id, COUNT(*) AS n FROM members "
           "GROUP BY group_id HAVING COUNT(*) > 1")
    assert outer_having_invalid(sql) is False
    _, action = safe_having_to_where(sql)
    assert action == "not_invalid"


# 5. An outer SELECT with an aggregate in its projection (no GROUP BY) + HAVING
#    is a valid aggregate query — not flagged.
def test_05_outer_aggregate_projection_having_valid():
    sql = "SELECT COUNT(*) AS n FROM members HAVING COUNT(*) > 0"
    assert outer_having_invalid(sql) is False
    _, action = safe_having_to_where(sql)
    assert action == "not_invalid"


# 6. Aggregates INSIDE a CTE do not make the outer query an aggregate query:
#    the outer non-aggregate SELECT with HAVING is still flagged invalid.
def test_06_cte_aggregate_does_not_count_as_outer_aggregate():
    sql = ("WITH c AS (SELECT group_id AS g, COUNT(*) AS n FROM members "
           "GROUP BY group_id) "
           "SELECT g.group_id FROM groups g JOIN c ON c.g = g.group_id "
           "HAVING c.n > 0")
    assert outer_having_invalid(sql) is True
    _, action = safe_having_to_where(sql)
    assert action == "normalized_having_to_where"


# 7. Aggregates inside a scalar SUBQUERY (not a CTE) also do not count.
def test_07_subquery_aggregate_does_not_count():
    sql = ("SELECT g.group_id, "
           "(SELECT COUNT(*) FROM members m WHERE m.group_id = g.group_id) AS n "
           "FROM groups g HAVING n > 0")
    # `n` here is a SELECT alias -> unsafe to move (see test 9); still invalid.
    assert outer_having_invalid(sql) is True


# 8. A qualified precomputed column (t.col) in HAVING is safe to move to WHERE.
def test_08_qualified_column_is_safe():
    fixed, action = safe_having_to_where(INVALID_DB57_SHAPE)
    assert action == "normalized_having_to_where"
    assert "act.active_member_count > 0" in fixed.lower()


# 9. A HAVING that depends on an unqualified SELECT-list ALIAS is NOT moved
#    (aliases are unavailable to WHERE) — rejected, not blindly rewritten.
def test_09_having_on_select_alias_not_moved():
    sql = ("SELECT g.group_id, act.active_member_count AS ac "
           "FROM groups g "
           "JOIN (SELECT group_id AS gid, COUNT(*) AS active_member_count "
           "      FROM members GROUP BY group_id) act ON act.gid = g.group_id "
           "HAVING ac > 0")
    assert outer_having_invalid(sql) is True
    fixed, action = safe_having_to_where(sql)
    assert fixed is None
    assert action == "unsafe_having_uses_select_alias"


# 10. An existing WHERE is preserved (AND-combined) when the HAVING is moved.
def test_10_existing_where_preserved_via_and():
    sql = INVALID_DB57_SHAPE.replace(
        "JOIN act  ON act.g  = g.group_id\n",
        "JOIN act  ON act.g  = g.group_id\nWHERE g.group_id < 100\n")
    fixed, action = safe_having_to_where(sql)
    assert action == "normalized_having_to_where"
    low = fixed.lower()
    assert "g.group_id < 100" in low
    assert "active_member_count > 0" in low
    assert " and " in low
    assert "having" not in low


# 11. The normalized SQL parses AND executes as valid SQLite (the invalid one
#     does not).
def test_11_invalid_rejected_normalized_executes():
    con = _db()
    ok_bad, _ = _runs(con, INVALID_DB57_SHAPE)
    assert ok_bad is False  # SQLite rejects HAVING on a non-aggregate query
    fixed, _ = safe_having_to_where(INVALID_DB57_SHAPE)
    ok_fixed, rows = _runs(con, fixed)
    assert ok_fixed is True
    con.close()
    assert rows is not None


# 12. Semantics preserved: the WHERE filter yields the same rows the HAVING
#     intended (groups with a positive active-member count), and independent
#     pre-aggregation gives the correct per-entity rate.
def test_12_normalized_matches_intended_semantics():
    con = _db()
    fixed, _ = safe_having_to_where(INVALID_DB57_SHAPE)
    ok, rows = _runs(con, fixed)
    assert ok
    # group 1: total 8 over 2 active -> 4.0 ; group 2: 7 over 1 -> 7.0 ;
    # group 3 has 0 active members and no events -> excluded by the join anyway.
    got = {r[0]: r[1] for r in rows}
    con.close()
    assert got == {1: 4.0, 2: 7.0}


# 13. Independent denominator: COUNT(DISTINCT) over the FULL member population
#     is NOT reduced to only members that appear in the event (numerator) table.
def test_13_denominator_independent_of_numerator_population():
    con = _db()
    # member 13 (group 3) is inactive and has no events; member 12 (group 2)
    # is active with an event. Denominator counts the active population only,
    # independent of who produced events.
    denom = con.execute(
        "SELECT group_id, COUNT(DISTINCT member_id) FROM members "
        "WHERE active = 1 GROUP BY group_id").fetchall()
    con.close()
    d = {g: n for g, n in denom}
    assert d == {1: 2, 2: 1}  # group 3 has 0 active -> absent, not miscounted


# 14. Fact-time attribution: events are attributed by their OWN member FK, so a
#     member's events map to the member regardless of any parent remapping.
def test_14_fact_attributed_by_own_fk():
    con = _db()
    rows = con.execute(
        "SELECT member_id, SUM(magnitude) FROM events "
        "GROUP BY member_id ORDER BY member_id").fetchall()
    con.close()
    assert rows == [(10, 5), (11, 3), (12, 7)]


# 15. A subquery-wrapped outer SELECT is unwrapped and evaluated correctly.
def test_15_subquery_wrapped_outer_select():
    inner = ("SELECT g.group_id FROM groups g "
             "JOIN (SELECT group_id AS gid, COUNT(*) AS c FROM members "
             "      GROUP BY group_id) t ON t.gid = g.group_id "
             "HAVING t.c > 0")
    sql = f"({inner})"
    assert outer_having_invalid(sql) is True


# 16. Non-invalid SQL is passed through untouched (idempotent / no rewrite).
def test_16_valid_sql_untouched():
    fixed, action = safe_having_to_where(VALID_WHERE_SHAPE)
    assert fixed is None
    assert action == "not_invalid"
    # a plain SELECT with neither HAVING nor GROUP BY is likewise untouched
    assert outer_having_invalid("SELECT group_id FROM members") is False


# 17. Regression guard: the normalizer never flags a valid aggregate/grouped
#     query and never fabricates or moves a clause. (The aggregate-with-HAVING-
#     but-no-GROUP-BY form is standard SQL but is separately rejected by strict
#     SQLite builds; the normalizer must still leave it untouched rather than
#     "fix" it by moving an aggregate into WHERE, which would be wrong.)
def test_17_no_regression_on_valid_queries():
    # (sql, executable_in_strict_sqlite)
    valids = [
        ("SELECT group_id, COUNT(*) n FROM members GROUP BY group_id HAVING COUNT(*) >= 1", True),
        ("SELECT AVG(magnitude) FROM events HAVING AVG(magnitude) > 0", False),
        ("SELECT group_id FROM members", True),
        ("SELECT group_id, SUM(magnitude) FROM events GROUP BY group_id", True),
    ]
    con = _db()
    for sql, executable in valids:
        assert outer_having_invalid(sql) is False, sql
        fixed, action = safe_having_to_where(sql)
        assert fixed is None and action == "not_invalid", sql
        if executable:
            ok, _ = _runs(con, sql)
            assert ok, sql  # remains executable, untouched
    con.close()


# Extra: parse errors degrade safely (no exception, no false rewrite).
def test_18_parse_error_is_safe():
    assert outer_having_invalid("this is not sql !!!") is False
    fixed, action = safe_having_to_where("this is not sql !!!")
    assert fixed is None
    assert action in ("parse_error", "not_invalid")


if __name__ == "__main__":  # pragma: no cover
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
