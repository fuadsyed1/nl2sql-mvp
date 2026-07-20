#!/usr/bin/env python3
"""
SpiderSQL Lahman 100-test SQL classification benchmark.

Purpose:
- 100 total tests for Lahman local benchmark DB #49.
- 10 SQL categories.
- Each category has 5 structured natural-language tests and 5 direct SQL tests.
- Structured tests call /database/{db_id}/execute_sql and compare generated SQL results to gold SQL.
- Direct SQL tests call /database/{db_id}/check_containment_batch with one SQL query and compare endpoint execution metadata to local SQLite gold execution.
- Saves JSON, TXT, and CSV summary files for graphing category accuracy.

Run from backend folder:
    cd C:\Projects\nl2sql-mvp\backend
    python run_lahman_100_sql_classification_benchmark_db49.py

Optional:
    python run_lahman_100_sql_classification_benchmark_db49.py --only-category join
    python run_lahman_100_sql_classification_benchmark_db49.py --only-mode structured
    python run_lahman_100_sql_classification_benchmark_db49.py --sqlite-path path\to\lahman.sqlite
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

BASE_URL_DEFAULT = "http://127.0.0.1:8000"
DB_ID_DEFAULT = 49
TIMEOUT_DEFAULT = 420

# --------------------------------------------------------------------------------------
# Test set
# --------------------------------------------------------------------------------------

TESTS: List[Dict[str, Any]] = []


def add(tid: str, category: str, mode: str, question: str, gold_sql: str) -> None:
    TESTS.append(
        {
            "id": tid,
            "category": category,
            "mode": mode,  # structured | sql
            "question": question.strip(),
            "gold_sql": re.sub(r"\s+", " ", gold_sql.strip()).strip().rstrip(";"),
        }
    )


# 1) JOIN -------------------------------------------------------------------------------
add(
    "JOIN-S01",
    "join",
    "structured",
    "For the 2001 season, list players who hit more than 40 home runs with their team name and team wins. Show first name, last name, year, team, wins, and home runs.",
    """
    SELECT p.nameFirst, p.nameLast, b.yearID, t.name, t.W, b.HR
    FROM Batting b
    JOIN People p ON b.playerID = p.playerID
    JOIN Teams t ON b.yearID = t.yearID AND b.teamID = t.teamID AND b.lgID = t.lgID
    WHERE b.yearID = 2001 AND b.HR > 40
    ORDER BY b.HR DESC, p.nameLast, p.nameFirst
    """,
)
add(
    "JOIN-S02",
    "join",
    "structured",
    "List pitching seasons after 2010 where the pitcher won more than 18 games. Include pitcher name, year, team name, wins, losses, and strikeouts.",
    """
    SELECT p.nameFirst, p.nameLast, pi.yearID, t.name, pi.W, pi.L, pi.SO
    FROM Pitching pi
    JOIN People p ON pi.playerID = p.playerID
    JOIN Teams t ON pi.yearID = t.yearID AND pi.teamID = t.teamID AND pi.lgID = t.lgID
    WHERE pi.yearID > 2010 AND pi.W > 18
    ORDER BY pi.yearID, pi.W DESC, pi.SO DESC
    """,
)
add(
    "JOIN-S03",
    "join",
    "structured",
    "Show players who attended California schools after 2000. Include player name, school name, state, and college year.",
    """
    SELECT p.nameFirst, p.nameLast, s.name_full, s.state, cp.yearID
    FROM CollegePlaying cp
    JOIN People p ON cp.playerID = p.playerID
    JOIN Schools s ON cp.schoolID = s.schoolID
    WHERE s.state = 'CA' AND cp.yearID > 2000
    ORDER BY cp.yearID, s.name_full, p.nameLast, p.nameFirst
    LIMIT 100
    """,
)
add(
    "JOIN-S04",
    "join",
    "structured",
    "List salary records after 2015 where the player earned more than 20 million dollars. Show player name, year, team, league, and salary.",
    """
    SELECT p.nameFirst, p.nameLast, s.yearID, s.teamID, s.lgID, s.salary
    FROM Salaries s
    JOIN People p ON s.playerID = p.playerID
    WHERE s.yearID > 2015 AND s.salary > 20000000
    ORDER BY s.salary DESC, s.yearID DESC
    """,
)
add(
    "JOIN-S05",
    "join",
    "structured",
    "List Hall of Fame inducted players born after 1960. Show first name, last name, birth year, and induction year.",
    """
    SELECT p.nameFirst, p.nameLast, p.birthYear, h.yearid
    FROM HallOfFame h
    JOIN People p ON h.playerID = p.playerID
    WHERE h.inducted = 'Y' AND h.category = 'Player' AND p.birthYear > 1960
    ORDER BY h.yearid, p.nameLast, p.nameFirst
    """,
)
add(
    "JOIN-Q01",
    "join",
    "sql",
    """
    SELECT p.nameFirst, p.nameLast, b.yearID, t.name, t.W, b.HR
    FROM Batting b
    JOIN People p ON b.playerID = p.playerID
    JOIN Teams t ON b.yearID = t.yearID AND b.teamID = t.teamID AND b.lgID = t.lgID
    WHERE b.yearID = 1998 AND b.HR > 45
    ORDER BY b.HR DESC, p.nameLast
    """,
    """
    SELECT p.nameFirst, p.nameLast, b.yearID, t.name, t.W, b.HR
    FROM Batting b
    JOIN People p ON b.playerID = p.playerID
    JOIN Teams t ON b.yearID = t.yearID AND b.teamID = t.teamID AND b.lgID = t.lgID
    WHERE b.yearID = 1998 AND b.HR > 45
    ORDER BY b.HR DESC, p.nameLast
    """,
)
add(
    "JOIN-Q02",
    "join",
    "sql",
    """
    SELECT p.nameFirst, p.nameLast, pi.yearID, t.name, pi.W, pi.SO
    FROM Pitching pi
    JOIN People p ON pi.playerID = p.playerID
    JOIN Teams t ON pi.yearID = t.yearID AND pi.teamID = t.teamID AND pi.lgID = t.lgID
    WHERE pi.yearID BETWEEN 2015 AND 2022 AND pi.SO > 250
    ORDER BY pi.SO DESC
    """,
    """
    SELECT p.nameFirst, p.nameLast, pi.yearID, t.name, pi.W, pi.SO
    FROM Pitching pi
    JOIN People p ON pi.playerID = p.playerID
    JOIN Teams t ON pi.yearID = t.yearID AND pi.teamID = t.teamID AND pi.lgID = t.lgID
    WHERE pi.yearID BETWEEN 2015 AND 2022 AND pi.SO > 250
    ORDER BY pi.SO DESC
    """,
)
add(
    "JOIN-Q03",
    "join",
    "sql",
    """
    SELECT p.nameFirst, p.nameLast, h.yearid, h.votedBy
    FROM HallOfFame h
    JOIN People p ON h.playerID = p.playerID
    WHERE h.inducted = 'Y' AND h.category = 'Player' AND h.yearid >= 2000
    ORDER BY h.yearid, p.nameLast
    """,
    """
    SELECT p.nameFirst, p.nameLast, h.yearid, h.votedBy
    FROM HallOfFame h
    JOIN People p ON h.playerID = p.playerID
    WHERE h.inducted = 'Y' AND h.category = 'Player' AND h.yearid >= 2000
    ORDER BY h.yearid, p.nameLast
    """,
)
add(
    "JOIN-Q04",
    "join",
    "sql",
    """
    SELECT p.nameFirst, p.nameLast, s.yearID, s.teamID, s.salary
    FROM Salaries s
    JOIN People p ON s.playerID = p.playerID
    WHERE s.salary > 25000000
    ORDER BY s.salary DESC, s.yearID DESC
    LIMIT 50
    """,
    """
    SELECT p.nameFirst, p.nameLast, s.yearID, s.teamID, s.salary
    FROM Salaries s
    JOIN People p ON s.playerID = p.playerID
    WHERE s.salary > 25000000
    ORDER BY s.salary DESC, s.yearID DESC
    LIMIT 50
    """,
)
add(
    "JOIN-Q05",
    "join",
    "sql",
    """
    SELECT p.nameFirst, p.nameLast, sc.name_full, sc.state, cp.yearID
    FROM CollegePlaying cp
    JOIN People p ON cp.playerID = p.playerID
    JOIN Schools sc ON cp.schoolID = sc.schoolID
    WHERE sc.country = 'USA' AND sc.state = 'TX' AND cp.yearID >= 1995
    ORDER BY cp.yearID, sc.name_full, p.nameLast
    LIMIT 100
    """,
    """
    SELECT p.nameFirst, p.nameLast, sc.name_full, sc.state, cp.yearID
    FROM CollegePlaying cp
    JOIN People p ON cp.playerID = p.playerID
    JOIN Schools sc ON cp.schoolID = sc.schoolID
    WHERE sc.country = 'USA' AND sc.state = 'TX' AND cp.yearID >= 1995
    ORDER BY cp.yearID, sc.name_full, p.nameLast
    LIMIT 100
    """,
)

# 2) MULTI JOIN -------------------------------------------------------------------------
add(
    "MJ-S01",
    "multi_join",
    "structured",
    "For player seasons after 2000, list players who made more than 20 million dollars and hit more than 30 home runs in the same year and team. Show name, year, team, salary, and home runs.",
    """
    SELECT p.nameFirst, p.nameLast, s.yearID, t.name, s.salary, b.HR
    FROM Salaries s
    JOIN People p ON s.playerID = p.playerID
    JOIN Batting b ON s.playerID = b.playerID AND s.yearID = b.yearID AND s.teamID = b.teamID AND s.lgID = b.lgID
    JOIN Teams t ON s.yearID = t.yearID AND s.teamID = t.teamID AND s.lgID = t.lgID
    WHERE s.yearID > 2000 AND s.salary > 20000000 AND b.HR > 30
    ORDER BY s.yearID, s.salary DESC
    """,
)
add(
    "MJ-S02",
    "multi_join",
    "structured",
    "List players who attended a California school and later hit more than 40 home runs in a season. Show player, school, batting year, team, and home runs.",
    """
    SELECT DISTINCT p.nameFirst, p.nameLast, sc.name_full, b.yearID, b.teamID, b.HR
    FROM People p
    JOIN CollegePlaying cp ON p.playerID = cp.playerID
    JOIN Schools sc ON cp.schoolID = sc.schoolID
    JOIN Batting b ON p.playerID = b.playerID
    WHERE sc.state = 'CA' AND b.HR > 40 AND b.yearID > cp.yearID
    ORDER BY b.HR DESC, b.yearID, p.nameLast
    """,
)
add(
    "MJ-S03",
    "multi_join",
    "structured",
    "List Hall of Fame inducted players who had a season with more than 40 home runs. Show player, induction year, batting year, team name, and home runs.",
    """
    SELECT DISTINCT p.nameFirst, p.nameLast, h.yearid AS induction_year, b.yearID, t.name, b.HR
    FROM HallOfFame h
    JOIN People p ON h.playerID = p.playerID
    JOIN Batting b ON h.playerID = b.playerID
    JOIN Teams t ON b.yearID = t.yearID AND b.teamID = t.teamID AND b.lgID = t.lgID
    WHERE h.inducted = 'Y' AND h.category = 'Player' AND b.HR > 40
    ORDER BY b.HR DESC, p.nameLast
    """,
)
add(
    "MJ-S04",
    "multi_join",
    "structured",
    "Find award-winning player seasons where a player won a Silver Slugger award and hit more than 35 home runs in that same year. Show player, year, team, award, and home runs.",
    """
    SELECT p.nameFirst, p.nameLast, ap.yearID, b.teamID, ap.awardID, b.HR
    FROM AwardsPlayers ap
    JOIN People p ON ap.playerID = p.playerID
    JOIN Batting b ON ap.playerID = b.playerID AND ap.yearID = b.yearID
    WHERE ap.awardID = 'Silver Slugger' AND b.HR > 35
    ORDER BY ap.yearID, b.HR DESC, p.nameLast
    """,
)
add(
    "MJ-S05",
    "multi_join",
    "structured",
    "Show pitchers after 2010 who had more than 200 strikeouts and whose team won more than 90 games. Include pitcher, year, team, pitcher strikeouts, and team wins.",
    """
    SELECT p.nameFirst, p.nameLast, pi.yearID, t.name, pi.SO, t.W
    FROM Pitching pi
    JOIN People p ON pi.playerID = p.playerID
    JOIN Teams t ON pi.yearID = t.yearID AND pi.teamID = t.teamID AND pi.lgID = t.lgID
    WHERE pi.yearID > 2010 AND pi.SO > 200 AND t.W > 90
    ORDER BY pi.yearID, pi.SO DESC
    """,
)
for i, sql in enumerate(
    [
        """
        SELECT p.nameFirst, p.nameLast, s.yearID, t.name, s.salary, b.HR
        FROM Salaries s
        JOIN People p ON s.playerID = p.playerID
        JOIN Batting b ON s.playerID = b.playerID AND s.yearID = b.yearID AND s.teamID = b.teamID AND s.lgID = b.lgID
        JOIN Teams t ON s.yearID = t.yearID AND s.teamID = t.teamID AND s.lgID = t.lgID
        WHERE s.yearID BETWEEN 2010 AND 2016 AND s.salary > 15000000 AND b.HR > 25
        ORDER BY s.salary DESC
        """,
        """
        SELECT DISTINCT p.nameFirst, p.nameLast, sc.name_full, b.yearID, b.HR
        FROM People p
        JOIN CollegePlaying cp ON p.playerID = cp.playerID
        JOIN Schools sc ON cp.schoolID = sc.schoolID
        JOIN Batting b ON p.playerID = b.playerID
        WHERE sc.state = 'FL' AND b.HR > 30 AND b.yearID > cp.yearID
        ORDER BY b.HR DESC
        """,
        """
        SELECT p.nameFirst, p.nameLast, h.yearid, b.yearID, b.HR
        FROM HallOfFame h
        JOIN People p ON h.playerID = p.playerID
        JOIN Batting b ON h.playerID = b.playerID
        WHERE h.inducted = 'Y' AND b.HR > 45
        ORDER BY b.HR DESC, h.yearid
        """,
        """
        SELECT p.nameFirst, p.nameLast, ap.yearID, ap.awardID, b.HR
        FROM AwardsPlayers ap
        JOIN People p ON ap.playerID = p.playerID
        JOIN Batting b ON ap.playerID = b.playerID AND ap.yearID = b.yearID
        WHERE ap.awardID = 'Gold Glove' AND b.HR > 25
        ORDER BY ap.yearID DESC, b.HR DESC
        """,
        """
        SELECT p.nameFirst, p.nameLast, pi.yearID, t.name, pi.W, pi.SO, t.W AS team_wins
        FROM Pitching pi
        JOIN People p ON pi.playerID = p.playerID
        JOIN Teams t ON pi.yearID = t.yearID AND pi.teamID = t.teamID AND pi.lgID = t.lgID
        WHERE pi.yearID >= 2000 AND pi.W > 18 AND pi.SO > 180 AND t.W > 90
        ORDER BY pi.yearID DESC, pi.SO DESC
        """,
    ],
    start=1,
):
    add(f"MJ-Q{i:02d}", "multi_join", "sql", sql, sql)

# 3) GROUP BY ---------------------------------------------------------------------------
add("GB-S01", "group_by", "structured", "For every year after 2000, show total home runs and total RBIs from Batting. Order by year.", """
SELECT yearID, SUM(HR) AS total_hr, SUM(RBI) AS total_rbi
FROM Batting
WHERE yearID > 2000
GROUP BY yearID
ORDER BY yearID
""")
add("GB-S02", "group_by", "structured", "Show each franchise's total wins and total losses after 1990, ordered by total wins descending.", """
SELECT franchID, SUM(W) AS total_wins, SUM(L) AS total_losses
FROM Teams
WHERE yearID > 1990
GROUP BY franchID
ORDER BY total_wins DESC, franchID
""")
add("GB-S03", "group_by", "structured", "For each player, calculate career home runs and RBIs, and show only players with at least one home run. Order by career home runs descending and limit to 50.", """
SELECT playerID, SUM(HR) AS career_hr, SUM(RBI) AS career_rbi
FROM Batting
GROUP BY playerID
HAVING SUM(HR) > 0
ORDER BY career_hr DESC, playerID
LIMIT 50
""")
add("GB-S04", "group_by", "structured", "For each salary year after 2000, show average salary, maximum salary, and number of salary records. Order by year.", """
SELECT yearID, AVG(salary) AS avg_salary, MAX(salary) AS max_salary, COUNT(*) AS salary_records
FROM Salaries
WHERE yearID > 2000
GROUP BY yearID
ORDER BY yearID
""")
add("GB-S05", "group_by", "structured", "For each school state in the United States, show how many distinct players attended schools there. Order by player count descending and show top 25.", """
SELECT sc.state, COUNT(DISTINCT cp.playerID) AS player_count
FROM CollegePlaying cp
JOIN Schools sc ON cp.schoolID = sc.schoolID
WHERE sc.country = 'USA' AND sc.state IS NOT NULL
GROUP BY sc.state
ORDER BY player_count DESC, sc.state
LIMIT 25
""")
for i, sql in enumerate([
"""SELECT yearID, SUM(HR) AS total_hr, SUM(RBI) AS total_rbi FROM Batting WHERE yearID BETWEEN 1990 AND 2010 GROUP BY yearID ORDER BY total_hr DESC""",
"""SELECT teamID, lgID, COUNT(*) AS seasons, SUM(W) AS total_wins FROM Teams WHERE yearID >= 2000 GROUP BY teamID, lgID ORDER BY total_wins DESC LIMIT 30""",
"""SELECT playerID, SUM(SO) AS career_so, SUM(W) AS career_wins FROM Pitching GROUP BY playerID HAVING SUM(SO) > 1000 ORDER BY career_so DESC LIMIT 50""",
"""SELECT yearID, COUNT(*) AS salary_count, AVG(salary) AS avg_salary FROM Salaries WHERE salary > 1000000 GROUP BY yearID ORDER BY yearID""",
"""SELECT sc.country, COUNT(DISTINCT cp.playerID) AS players FROM CollegePlaying cp JOIN Schools sc ON cp.schoolID = sc.schoolID GROUP BY sc.country ORDER BY players DESC LIMIT 20""",
], start=1):
    add(f"GB-Q{i:02d}", "group_by", "sql", sql, sql)

# 4) HAVING -----------------------------------------------------------------------------
add("HV-S01", "having", "structured", "Find players with more than 300 career home runs and more than 1000 career RBIs. Show playerID, career home runs, and career RBIs.", """
SELECT playerID, SUM(HR) AS career_hr, SUM(RBI) AS career_rbi
FROM Batting
GROUP BY playerID
HAVING SUM(HR) > 300 AND SUM(RBI) > 1000
ORDER BY career_hr DESC
""")
add("HV-S02", "having", "structured", "Find franchises after 1990 with more than 2500 total wins. Show franchise, total wins, total losses, and seasons.", """
SELECT franchID, SUM(W) AS total_wins, SUM(L) AS total_losses, COUNT(*) AS seasons
FROM Teams
WHERE yearID > 1990
GROUP BY franchID
HAVING SUM(W) > 2500
ORDER BY total_wins DESC
""")
add("HV-S03", "having", "structured", "Find schools that produced more than 50 distinct major league players. Show school name and player count.", """
SELECT sc.name_full, COUNT(DISTINCT cp.playerID) AS player_count
FROM CollegePlaying cp
JOIN Schools sc ON cp.schoolID = sc.schoolID
GROUP BY sc.schoolID, sc.name_full
HAVING COUNT(DISTINCT cp.playerID) > 50
ORDER BY player_count DESC, sc.name_full
""")
add("HV-S04", "having", "structured", "Find seasons after 1990 where all batting records combined had more than 5000 home runs and more than 20000 RBIs. Show year and totals.", """
SELECT yearID, SUM(HR) AS total_hr, SUM(RBI) AS total_rbi
FROM Batting
WHERE yearID > 1990
GROUP BY yearID
HAVING SUM(HR) > 5000 AND SUM(RBI) > 20000
ORDER BY yearID
""")
add("HV-S05", "having", "structured", "Find pitchers with more than 2000 career strikeouts and more than 150 career wins. Show playerID, career strikeouts, and career wins.", """
SELECT playerID, SUM(SO) AS career_so, SUM(W) AS career_wins
FROM Pitching
GROUP BY playerID
HAVING SUM(SO) > 2000 AND SUM(W) > 150
ORDER BY career_so DESC
""")
for i, sql in enumerate([
"""SELECT playerID, SUM(HR) AS career_hr FROM Batting GROUP BY playerID HAVING SUM(HR) > 500 ORDER BY career_hr DESC""",
"""SELECT yearID, SUM(W) AS total_wins FROM Teams GROUP BY yearID HAVING SUM(W) > 2400 ORDER BY yearID""",
"""SELECT teamID, COUNT(*) AS seasons_over_90 FROM Teams WHERE W > 90 GROUP BY teamID HAVING COUNT(*) >= 10 ORDER BY seasons_over_90 DESC""",
"""SELECT playerID, AVG(salary) AS avg_salary, MAX(salary) AS max_salary FROM Salaries GROUP BY playerID HAVING AVG(salary) > 10000000 ORDER BY avg_salary DESC LIMIT 50""",
"""SELECT sc.state, COUNT(DISTINCT cp.playerID) AS players FROM CollegePlaying cp JOIN Schools sc ON cp.schoolID = sc.schoolID WHERE sc.country = 'USA' GROUP BY sc.state HAVING COUNT(DISTINCT cp.playerID) > 200 ORDER BY players DESC""",
], start=1):
    add(f"HV-Q{i:02d}", "having", "sql", sql, sql)

# 5) SUBQUERY ---------------------------------------------------------------------------
add("SUB-S01", "subquery", "structured", "List 2001 batting rows where the player's home runs were above the average home runs for all 2001 batting rows with at least 100 at-bats. Show playerID, team, home runs, and at-bats.", """
SELECT playerID, teamID, HR, AB
FROM Batting
WHERE yearID = 2001 AND AB >= 100
  AND HR > (SELECT AVG(HR) FROM Batting WHERE yearID = 2001 AND AB >= 100)
ORDER BY HR DESC, playerID
""")
add("SUB-S02", "subquery", "structured", "Find teams in 2019 whose wins were above the average wins for all 2019 teams. Show team name, league, wins, and losses.", """
SELECT name, lgID, W, L
FROM Teams
WHERE yearID = 2019
  AND W > (SELECT AVG(W) FROM Teams WHERE yearID = 2019)
ORDER BY W DESC, name
""")
add("SUB-S03", "subquery", "structured", "Show salary records in 2016 where salary was above the 2016 average salary. Include playerID, team, and salary.", """
SELECT playerID, teamID, salary
FROM Salaries
WHERE yearID = 2016
  AND salary > (SELECT AVG(salary) FROM Salaries WHERE yearID = 2016)
ORDER BY salary DESC, playerID
""")
add("SUB-S04", "subquery", "structured", "Find players who have at least one Hall of Fame inducted record and more than 400 career home runs. Show playerID and career home runs.", """
SELECT b.playerID, SUM(b.HR) AS career_hr
FROM Batting b
WHERE b.playerID IN (SELECT playerID FROM HallOfFame WHERE inducted = 'Y' AND category = 'Player')
GROUP BY b.playerID
HAVING SUM(b.HR) > 400
ORDER BY career_hr DESC
""")
add("SUB-S05", "subquery", "structured", "Find schools in states that have more than 100 schools in the Schools table. Show schoolID, school name, and state.", """
SELECT schoolID, name_full, state
FROM Schools
WHERE state IN (
  SELECT state FROM Schools WHERE country = 'USA' AND state IS NOT NULL GROUP BY state HAVING COUNT(*) > 100
)
ORDER BY state, name_full
LIMIT 200
""")
for i, sql in enumerate([
"""SELECT playerID, yearID, teamID, HR FROM Batting WHERE yearID = 1998 AND HR > (SELECT AVG(HR) FROM Batting WHERE yearID = 1998 AND AB >= 100) ORDER BY HR DESC""",
"""SELECT name, yearID, W, L FROM Teams t WHERE yearID = 2021 AND W > (SELECT AVG(W) FROM Teams WHERE yearID = t.yearID) ORDER BY W DESC""",
"""SELECT playerID, yearID, salary FROM Salaries s WHERE salary > (SELECT AVG(salary) FROM Salaries WHERE yearID = s.yearID) AND yearID >= 2015 ORDER BY yearID, salary DESC LIMIT 100""",
"""SELECT playerID, SUM(HR) AS career_hr FROM Batting WHERE playerID IN (SELECT playerID FROM HallOfFame WHERE inducted = 'Y') GROUP BY playerID HAVING SUM(HR) > 300 ORDER BY career_hr DESC""",
"""SELECT schoolID, name_full, country, state FROM Schools WHERE country = 'USA' AND state IN (SELECT state FROM Schools GROUP BY state HAVING COUNT(*) > 75) ORDER BY state, name_full LIMIT 100""",
], start=1):
    add(f"SUB-Q{i:02d}", "subquery", "sql", sql, sql)

# 6) SET OPERATIONS ---------------------------------------------------------------------
add("SET-S01", "set_operation", "structured", "Find playerIDs who had both a batting record and a pitching record in 2001. Use a set intersection and order the playerIDs.", """
SELECT playerID FROM Batting WHERE yearID = 2001
INTERSECT
SELECT playerID FROM Pitching WHERE yearID = 2001
ORDER BY playerID
""")
add("SET-S02", "set_operation", "structured", "Find playerIDs who had a salary record in 2016 but no batting record in 2016. Use EXCEPT and order the playerIDs.", """
SELECT playerID FROM Salaries WHERE yearID = 2016
EXCEPT
SELECT playerID FROM Batting WHERE yearID = 2016
ORDER BY playerID
""")
add("SET-S03", "set_operation", "structured", "Create one list of playerIDs who either hit more than 60 home runs in any season or struck out more than 350 batters in any pitching season. Use UNION and order the result.", """
SELECT playerID FROM Batting WHERE HR > 60
UNION
SELECT playerID FROM Pitching WHERE SO > 350
ORDER BY playerID
""")
add("SET-S04", "set_operation", "structured", "Find teamIDs that appear in Teams after 2000 but do not appear in Salaries after 2000. Use EXCEPT.", """
SELECT DISTINCT teamID FROM Teams WHERE yearID > 2000
EXCEPT
SELECT DISTINCT teamID FROM Salaries WHERE yearID > 2000
ORDER BY teamID
""")
add("SET-S05", "set_operation", "structured", "Find playerIDs who attended college and also appear in the Hall of Fame table. Use INTERSECT.", """
SELECT DISTINCT playerID FROM CollegePlaying
INTERSECT
SELECT DISTINCT playerID FROM HallOfFame
ORDER BY playerID
""")
for i, sql in enumerate([
"""SELECT playerID FROM Batting WHERE yearID = 2019 INTERSECT SELECT playerID FROM Salaries WHERE yearID = 2019 ORDER BY playerID""",
"""SELECT playerID FROM Salaries WHERE yearID = 2015 EXCEPT SELECT playerID FROM Pitching WHERE yearID = 2015 ORDER BY playerID LIMIT 200""",
"""SELECT playerID FROM Batting WHERE HR > 55 UNION SELECT playerID FROM Pitching WHERE SO > 300 ORDER BY playerID""",
"""SELECT DISTINCT teamID FROM Batting WHERE yearID = 2020 EXCEPT SELECT DISTINCT teamID FROM Teams WHERE yearID = 2020 ORDER BY teamID""",
"""SELECT DISTINCT playerID FROM AwardsPlayers INTERSECT SELECT DISTINCT playerID FROM HallOfFame ORDER BY playerID LIMIT 200""",
], start=1):
    add(f"SET-Q{i:02d}", "set_operation", "sql", sql, sql)

# 7) ORDER LIMIT / TOP-K ----------------------------------------------------------------
add("TOP-S01", "order_limit_topk", "structured", "Show the top 10 players by career home runs. Include player name and career home runs.", """
SELECT p.nameFirst, p.nameLast, SUM(b.HR) AS career_hr
FROM Batting b
JOIN People p ON b.playerID = p.playerID
GROUP BY b.playerID
ORDER BY career_hr DESC, p.nameLast
LIMIT 10
""")
add("TOP-S02", "order_limit_topk", "structured", "Show the top 15 team seasons by wins after 1990. Include year, team name, league, wins, and losses.", """
SELECT yearID, name, lgID, W, L
FROM Teams
WHERE yearID > 1990
ORDER BY W DESC, yearID, name
LIMIT 15
""")
add("TOP-S03", "order_limit_topk", "structured", "Show the top 20 salaries after 2010 with player name, year, team, and salary.", """
SELECT p.nameFirst, p.nameLast, s.yearID, s.teamID, s.salary
FROM Salaries s
JOIN People p ON s.playerID = p.playerID
WHERE s.yearID > 2010
ORDER BY s.salary DESC, s.yearID DESC
LIMIT 20
""")
add("TOP-S04", "order_limit_topk", "structured", "Show the top 10 schools by distinct players. Include school name, state, country, and player count.", """
SELECT sc.name_full, sc.state, sc.country, COUNT(DISTINCT cp.playerID) AS player_count
FROM CollegePlaying cp
JOIN Schools sc ON cp.schoolID = sc.schoolID
GROUP BY sc.schoolID, sc.name_full, sc.state, sc.country
ORDER BY player_count DESC, sc.name_full
LIMIT 10
""")
add("TOP-S05", "order_limit_topk", "structured", "Show the top 10 pitchers by career strikeouts with player name and career strikeouts.", """
SELECT p.nameFirst, p.nameLast, SUM(pi.SO) AS career_so
FROM Pitching pi
JOIN People p ON pi.playerID = p.playerID
GROUP BY pi.playerID
ORDER BY career_so DESC, p.nameLast
LIMIT 10
""")
for i, sql in enumerate([
"""SELECT playerID, SUM(HR) AS career_hr FROM Batting GROUP BY playerID ORDER BY career_hr DESC, playerID LIMIT 25""",
"""SELECT yearID, name, W, L FROM Teams ORDER BY W DESC, yearID LIMIT 20""",
"""SELECT playerID, yearID, salary FROM Salaries ORDER BY salary DESC, yearID DESC LIMIT 30""",
"""SELECT playerID, SUM(SO) AS career_so FROM Pitching GROUP BY playerID ORDER BY career_so DESC LIMIT 15""",
"""SELECT sc.name_full, COUNT(DISTINCT cp.playerID) AS players FROM CollegePlaying cp JOIN Schools sc ON cp.schoolID = sc.schoolID GROUP BY sc.schoolID, sc.name_full ORDER BY players DESC LIMIT 15""",
], start=1):
    add(f"TOP-Q{i:02d}", "order_limit_topk", "sql", sql, sql)

# 8) AGGREGATION WITHOUT GROUP ----------------------------------------------------------
add("AGG-S01", "aggregation", "structured", "For batting records in 2001, show total home runs, total RBIs, and average home runs.", """
SELECT SUM(HR) AS total_hr, SUM(RBI) AS total_rbi, AVG(HR) AS avg_hr
FROM Batting
WHERE yearID = 2001
""")
add("AGG-S02", "aggregation", "structured", "For salary records in 2016, show number of salaries, average salary, minimum salary, and maximum salary.", """
SELECT COUNT(*) AS salary_count, AVG(salary) AS avg_salary, MIN(salary) AS min_salary, MAX(salary) AS max_salary
FROM Salaries
WHERE yearID = 2016
""")
add("AGG-S03", "aggregation", "structured", "Count players born after 1980 who have a non-null debut date.", """
SELECT COUNT(*) AS player_count
FROM People
WHERE birthYear > 1980 AND debut IS NOT NULL
""")
add("AGG-S04", "aggregation", "structured", "For team seasons after 2000 with attendance above 3 million, show total wins, total losses, and average attendance.", """
SELECT SUM(W) AS total_wins, SUM(L) AS total_losses, AVG(attendance) AS avg_attendance
FROM Teams
WHERE yearID > 2000 AND attendance > 3000000
""")
add("AGG-S05", "aggregation", "structured", "For pitching seasons after 2010, show total strikeouts, maximum wins, and average ERA for rows with ERA not null.", """
SELECT SUM(SO) AS total_so, MAX(W) AS max_wins, AVG(ERA) AS avg_era
FROM Pitching
WHERE yearID > 2010 AND ERA IS NOT NULL
""")
for i, sql in enumerate([
"""SELECT COUNT(*) AS batting_rows, SUM(HR) AS total_hr, SUM(RBI) AS total_rbi FROM Batting WHERE yearID BETWEEN 1995 AND 2005""",
"""SELECT COUNT(*) AS people_count, MIN(birthYear) AS min_birth, MAX(birthYear) AS max_birth FROM People WHERE birthYear IS NOT NULL""",
"""SELECT AVG(W) AS avg_wins, AVG(L) AS avg_losses, SUM(attendance) AS total_attendance FROM Teams WHERE yearID = 2019""",
"""SELECT COUNT(*) AS hof_inducted FROM HallOfFame WHERE inducted = 'Y' AND category = 'Player'""",
"""SELECT SUM(salary) AS total_salary, AVG(salary) AS avg_salary FROM Salaries WHERE yearID >= 2010 AND salary > 10000000""",
], start=1):
    add(f"AGG-Q{i:02d}", "aggregation", "sql", sql, sql)

# 9) DISTINCT / COUNT DISTINCT ----------------------------------------------------------
add("DST-S01", "distinct_count", "structured", "Count distinct players who hit more than 40 home runs in any season after 1990.", """
SELECT COUNT(DISTINCT playerID) AS player_count
FROM Batting
WHERE yearID > 1990 AND HR > 40
""")
add("DST-S02", "distinct_count", "structured", "Count distinct teams with more than 90 wins after 2000.", """
SELECT COUNT(DISTINCT teamID) AS team_count
FROM Teams
WHERE yearID > 2000 AND W > 90
""")
add("DST-S03", "distinct_count", "structured", "List distinct school states in the United States that have college playing records. Order alphabetically.", """
SELECT DISTINCT sc.state
FROM CollegePlaying cp
JOIN Schools sc ON cp.schoolID = sc.schoolID
WHERE sc.country = 'USA' AND sc.state IS NOT NULL
ORDER BY sc.state
""")
add("DST-S04", "distinct_count", "structured", "Count distinct players who received any award after 2000.", """
SELECT COUNT(DISTINCT playerID) AS award_player_count
FROM AwardsPlayers
WHERE yearID > 2000
""")
add("DST-S05", "distinct_count", "structured", "For each year after 2010, count distinct salaried players and distinct teams paying salaries.", """
SELECT yearID, COUNT(DISTINCT playerID) AS player_count, COUNT(DISTINCT teamID) AS team_count
FROM Salaries
WHERE yearID > 2010
GROUP BY yearID
ORDER BY yearID
""")
for i, sql in enumerate([
"""SELECT COUNT(DISTINCT playerID) AS players FROM Pitching WHERE yearID >= 2000 AND SO > 200""",
"""SELECT DISTINCT lgID FROM Teams WHERE yearID >= 1900 ORDER BY lgID""",
"""SELECT yearID, COUNT(DISTINCT teamID) AS teams FROM Teams WHERE yearID >= 2000 GROUP BY yearID ORDER BY yearID""",
"""SELECT COUNT(DISTINCT schoolID) AS schools FROM CollegePlaying WHERE yearID >= 2000""",
"""SELECT DISTINCT awardID FROM AwardsPlayers WHERE yearID >= 2010 ORDER BY awardID""",
], start=1):
    add(f"DST-Q{i:02d}", "distinct_count", "sql", sql, sql)

# 10) DERIVED METRICS / RATIOS ----------------------------------------------------------
add("DRV-S01", "derived_metric", "structured", "For batting seasons after 2010 with at least 500 at-bats, show playerID, year, hits, at-bats, and batting average. Order by batting average descending and limit to 25.", """
SELECT playerID, yearID, H, AB, 1.0 * H / NULLIF(AB, 0) AS batting_avg
FROM Batting
WHERE yearID > 2010 AND AB >= 500
ORDER BY batting_avg DESC, playerID
LIMIT 25
""")
add("DRV-S02", "derived_metric", "structured", "For team seasons after 2000, show year, team name, wins, losses, and winning percentage for teams with more than 95 wins. Order by winning percentage descending.", """
SELECT yearID, name, W, L, 1.0 * W / NULLIF(W + L, 0) AS win_pct
FROM Teams
WHERE yearID > 2000 AND W > 95
ORDER BY win_pct DESC, yearID, name
""")
add("DRV-S03", "derived_metric", "structured", "For player salary and batting seasons after 2010, show playerID, year, salary, home runs, and salary per home run for seasons with more than 20 home runs and salary above 10 million.", """
SELECT s.playerID, s.yearID, s.salary, b.HR, 1.0 * s.salary / NULLIF(b.HR, 0) AS salary_per_hr
FROM Salaries s
JOIN Batting b ON s.playerID = b.playerID AND s.yearID = b.yearID AND s.teamID = b.teamID AND s.lgID = b.lgID
WHERE s.yearID > 2010 AND s.salary > 10000000 AND b.HR > 20
ORDER BY salary_per_hr DESC, s.yearID
""")
add("DRV-S04", "derived_metric", "structured", "For pitchers after 2015 with at least 150 strikeouts, show playerID, year, strikeouts, walks, and strikeout-to-walk ratio. Order by the ratio descending.", """
SELECT playerID, yearID, SO, BB, 1.0 * SO / NULLIF(BB, 0) AS so_bb_ratio
FROM Pitching
WHERE yearID > 2015 AND SO >= 150 AND BB IS NOT NULL
ORDER BY so_bb_ratio DESC, playerID
LIMIT 50
""")
add("DRV-S05", "derived_metric", "structured", "For teams after 2010 with attendance above 2 million, show year, team, attendance, games, and attendance per home game. Order by attendance per game descending.", """
SELECT yearID, name, attendance, Ghome, 1.0 * attendance / NULLIF(Ghome, 0) AS attendance_per_home_game
FROM Teams
WHERE yearID > 2010 AND attendance > 2000000 AND Ghome IS NOT NULL
ORDER BY attendance_per_home_game DESC, yearID
LIMIT 50
""")
for i, sql in enumerate([
"""SELECT playerID, yearID, H, AB, 1.0 * H / NULLIF(AB, 0) AS batting_avg FROM Batting WHERE yearID = 2019 AND AB >= 400 ORDER BY batting_avg DESC LIMIT 30""",
"""SELECT yearID, name, W, L, 1.0 * W / NULLIF(W + L, 0) AS win_pct FROM Teams WHERE yearID = 2021 ORDER BY win_pct DESC, name""",
"""SELECT s.playerID, s.yearID, s.salary, b.HR, 1.0 * s.salary / NULLIF(b.HR, 0) AS salary_per_hr FROM Salaries s JOIN Batting b ON s.playerID = b.playerID AND s.yearID = b.yearID AND s.teamID = b.teamID AND s.lgID = b.lgID WHERE s.yearID = 2016 AND b.HR > 10 ORDER BY salary_per_hr DESC LIMIT 50""",
"""SELECT playerID, yearID, SO, BB, 1.0 * SO / NULLIF(BB, 0) AS so_bb_ratio FROM Pitching WHERE yearID = 2022 AND SO >= 150 ORDER BY so_bb_ratio DESC""",
"""SELECT yearID, name, attendance, Ghome, 1.0 * attendance / NULLIF(Ghome, 0) AS attendance_per_home_game FROM Teams WHERE yearID >= 2015 AND attendance > 2500000 AND Ghome IS NOT NULL ORDER BY attendance_per_home_game DESC LIMIT 25""",
], start=1):
    add(f"DRV-Q{i:02d}", "derived_metric", "sql", sql, sql)

assert len(TESTS) == 100, f"Expected 100 tests, got {len(TESTS)}"

# --------------------------------------------------------------------------------------
# Runtime helpers
# --------------------------------------------------------------------------------------


def post_json(url: str, payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(text) if text else {}
            parsed["_http_status"] = resp.status
            return parsed
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body) if body else {}
        except Exception:
            parsed = {"raw_body": body}
        parsed["_http_status"] = exc.code
        parsed["_http_error"] = True
        return parsed
    except Exception as exc:
        return {"_http_status": None, "_request_error": str(exc)}


def discover_lahman_sqlite(explicit: Optional[str] = None) -> str:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise FileNotFoundError(f"Provided --sqlite-path does not exist: {p}")
        return str(p)

    start_dirs = [Path.cwd(), Path.cwd().parent]
    names = {"lahman.sqlite", "lahman.db", "lahman.sqlite3"}
    candidates: List[Path] = []
    for base in start_dirs:
        if not base.exists():
            continue
        for root, dirs, files in os.walk(base):
            # Avoid expensive irrelevant folders.
            dirs[:] = [d for d in dirs if d.lower() not in {"venv", ".git", "node_modules", "__pycache__"}]
            for f in files:
                lf = f.lower()
                if lf in names or ("lahman" in lf and lf.endswith((".sqlite", ".db", ".sqlite3"))):
                    candidates.append(Path(root) / f)
        if candidates:
            break

    if not candidates:
        raise FileNotFoundError(
            "Could not auto-find lahman.sqlite. Re-run with --sqlite-path C:\\path\\to\\lahman.sqlite"
        )
    # Prefer a path under local_benchmarks if available.
    candidates.sort(key=lambda p: ("local_benchmarks" not in str(p).lower(), len(str(p))))
    return str(candidates[0])


def normalize_value(v: Any) -> Any:
    if isinstance(v, float):
        return round(v, 8)
    if isinstance(v, bytes):
        return v.hex()
    return v


def normalize_rows(rows: Sequence[Sequence[Any]]) -> List[Tuple[Any, ...]]:
    return [tuple(normalize_value(v) for v in row) for row in rows]


def has_order_or_limit(sql: str) -> bool:
    low = sql.lower()
    return " order by " in low or " limit " in low


def compare_rows(gold_cols: List[str], gold_rows: List[Tuple[Any, ...]], got_cols: List[str], got_rows: List[Tuple[Any, ...]], ordered: bool) -> Tuple[bool, str]:
    gold_cols_l = [c.lower() for c in gold_cols]
    got_cols_l = [c.lower() for c in got_cols]
    if gold_cols_l != got_cols_l:
        return False, f"column mismatch: expected {gold_cols}, got {got_cols}"
    if ordered:
        if gold_rows != got_rows:
            return False, f"ordered row mismatch: expected {len(gold_rows)} rows, got {len(got_rows)} rows"
    else:
        if collections.Counter(gold_rows) != collections.Counter(got_rows):
            return False, f"row-set mismatch: expected {len(gold_rows)} rows, got {len(got_rows)} rows"
    return True, "rows match"


def execute_sqlite(conn: sqlite3.Connection, sql: str, params: Optional[Sequence[Any]] = None) -> Tuple[List[str], List[Tuple[Any, ...]], Optional[str]]:
    try:
        cur = conn.execute(sql, list(params or []))
        cols = [d[0] for d in (cur.description or [])]
        rows = normalize_rows(cur.fetchall())
        return cols, rows, None
    except Exception as exc:
        return [], [], str(exc)


def extract_execute_sql_response(resp: Dict[str, Any]) -> Dict[str, Any]:
    """Flexible extraction for /execute_sql response."""
    sql = None
    params: List[Any] = []
    success = bool(resp.get("success"))
    low_confidence = bool(resp.get("low_confidence", False))
    fatal = bool(resp.get("has_fatal_validation", False))
    warnings = resp.get("warnings") or []

    gen = resp.get("generated_sql")
    if isinstance(gen, dict):
        sql = gen.get("sql") or gen.get("query") or gen.get("text")
        params = gen.get("params") or []
        low_confidence = bool(gen.get("low_confidence", low_confidence))
        fatal = bool(gen.get("has_fatal_validation", fatal))
        warnings = gen.get("warnings", warnings) or warnings
    elif isinstance(gen, str):
        sql = gen

    if not sql:
        # Some endpoints may return sql at top-level.
        sql = resp.get("sql") or resp.get("query")
        params = resp.get("params") or []

    execution = resp.get("execution") or {}
    row_count = execution.get("row_count", resp.get("row_count"))
    columns = execution.get("columns") or execution.get("execution_columns") or resp.get("execution_columns")

    return {
        "success": success,
        "sql": sql,
        "params": params,
        "row_count": row_count,
        "columns": columns,
        "low_confidence": low_confidence,
        "fatal": fatal,
        "warnings": warnings,
    }


def extract_containment_single_response(resp: Dict[str, Any]) -> Dict[str, Any]:
    qrs = resp.get("query_results") or []
    qr = qrs[0] if qrs else {}
    return {
        "success": bool(resp.get("success")) and bool(qr.get("success", True)),
        "sql": qr.get("sql"),
        "params": qr.get("params") or [],
        "row_count": qr.get("row_count"),
        "columns": qr.get("execution_columns"),
        "low_confidence": bool(qr.get("low_confidence", False)),
        "fatal": bool(qr.get("has_fatal_validation", False)),
        "safe": bool(qr.get("safe", True)),
        "safety_reason": qr.get("safety_reason"),
        "warnings": qr.get("warnings") or [],
    }


def run_structured(test: Dict[str, Any], base_url: str, db_id: int, timeout: int, conn: sqlite3.Connection) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/database/{db_id}/execute_sql"
    started = time.time()
    resp = post_json(url, {"question": test["question"]}, timeout=timeout)
    elapsed = round(time.time() - started, 3)
    extracted = extract_execute_sql_response(resp)

    gold_cols, gold_rows, gold_err = execute_sqlite(conn, test["gold_sql"])
    passed = False
    reason = ""
    got_cols: List[str] = []
    got_rows: List[Tuple[Any, ...]] = []
    got_err: Optional[str] = None

    if gold_err:
        reason = f"gold SQL failed locally: {gold_err}"
    elif resp.get("_request_error"):
        reason = f"request error: {resp.get('_request_error')}"
    elif not extracted["success"]:
        reason = "backend success=false"
    elif extracted["low_confidence"] or extracted["fatal"]:
        reason = f"low_confidence={extracted['low_confidence']} fatal={extracted['fatal']}"
    elif not extracted["sql"]:
        reason = "no generated SQL returned"
    else:
        got_cols, got_rows, got_err = execute_sqlite(conn, extracted["sql"], extracted["params"])
        if got_err:
            reason = f"generated SQL failed locally: {got_err}"
        else:
            passed, reason = compare_rows(gold_cols, gold_rows, got_cols, got_rows, has_order_or_limit(test["gold_sql"]))

    return {
        "id": test["id"],
        "category": test["category"],
        "mode": test["mode"],
        "passed": passed,
        "reason": reason,
        "elapsed_seconds": elapsed,
        "http_status": resp.get("_http_status"),
        "question": test["question"],
        "gold_sql": test["gold_sql"],
        "generated_sql": extracted.get("sql"),
        "generated_params": extracted.get("params"),
        "expected_row_count": len(gold_rows) if not gold_err else None,
        "actual_row_count": len(got_rows) if got_rows is not None else None,
        "expected_columns": gold_cols,
        "actual_columns": got_cols,
        "backend_meta": {k: extracted.get(k) for k in ["success", "row_count", "columns", "low_confidence", "fatal", "warnings"]},
    }


def run_sql(test: Dict[str, Any], base_url: str, db_id: int, timeout: int, conn: sqlite3.Connection) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/database/{db_id}/check_containment_batch"
    started = time.time()
    resp = post_json(url, {"queries": [test["question"]]}, timeout=timeout)
    # Fallback if endpoint rejects a single query.
    if not resp.get("query_results"):
        resp = post_json(url, {"queries": [test["question"], test["question"]]}, timeout=timeout)
    elapsed = round(time.time() - started, 3)
    extracted = extract_containment_single_response(resp)

    gold_cols, gold_rows, gold_err = execute_sqlite(conn, test["gold_sql"])
    passed = False
    reason = ""
    got_cols: List[str] = []
    got_rows: List[Tuple[Any, ...]] = []
    got_err: Optional[str] = None

    if gold_err:
        reason = f"gold SQL failed locally: {gold_err}"
    elif resp.get("_request_error"):
        reason = f"request error: {resp.get('_request_error')}"
    elif not extracted["success"]:
        reason = "backend/direct SQL success=false"
    elif extracted["low_confidence"] or extracted["fatal"] or not extracted.get("safe", True):
        reason = f"unsafe/low confidence: low={extracted['low_confidence']} fatal={extracted['fatal']} safe={extracted.get('safe')} reason={extracted.get('safety_reason')}"
    elif not extracted["sql"]:
        reason = "no SQL returned from direct SQL path"
    else:
        got_cols, got_rows, got_err = execute_sqlite(conn, extracted["sql"], extracted["params"])
        if got_err:
            reason = f"returned SQL failed locally: {got_err}"
        else:
            passed, reason = compare_rows(gold_cols, gold_rows, got_cols, got_rows, has_order_or_limit(test["gold_sql"]))

    return {
        "id": test["id"],
        "category": test["category"],
        "mode": test["mode"],
        "passed": passed,
        "reason": reason,
        "elapsed_seconds": elapsed,
        "http_status": resp.get("_http_status"),
        "question": test["question"],
        "gold_sql": test["gold_sql"],
        "generated_sql": extracted.get("sql"),
        "generated_params": extracted.get("params"),
        "expected_row_count": len(gold_rows) if not gold_err else None,
        "actual_row_count": len(got_rows) if got_rows is not None else None,
        "expected_columns": gold_cols,
        "actual_columns": got_cols,
        "backend_meta": {k: extracted.get(k) for k in ["success", "row_count", "columns", "low_confidence", "fatal", "safe", "safety_reason", "warnings"]},
    }


def summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "overall": {"total": len(results), "passed": sum(1 for r in results if r["passed"]), "failed": sum(1 for r in results if not r["passed"])},
        "by_category": {},
        "by_category_mode": {},
        "graph_rows": [],
    }
    summary["overall"]["accuracy_percent"] = round(100.0 * summary["overall"]["passed"] / max(1, summary["overall"]["total"]), 2)

    categories = sorted({r["category"] for r in results})
    for category in categories:
        cat_rows = [r for r in results if r["category"] == category]
        passed = sum(1 for r in cat_rows if r["passed"])
        total = len(cat_rows)
        summary["by_category"][category] = {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "accuracy_percent": round(100.0 * passed / max(1, total), 2),
        }
        summary["graph_rows"].append(
            {
                "category": category,
                "mode": "combined",
                "total": total,
                "passed": passed,
                "failed": total - passed,
                "accuracy_percent": round(100.0 * passed / max(1, total), 2),
            }
        )
        for mode in ["structured", "sql"]:
            rows = [r for r in cat_rows if r["mode"] == mode]
            m_passed = sum(1 for r in rows if r["passed"])
            key = f"{category}:{mode}"
            summary["by_category_mode"][key] = {
                "category": category,
                "mode": mode,
                "total": len(rows),
                "passed": m_passed,
                "failed": len(rows) - m_passed,
                "accuracy_percent": round(100.0 * m_passed / max(1, len(rows)), 2),
            }
            summary["graph_rows"].append(summary["by_category_mode"][key])
    return summary


def save_outputs(results: List[Dict[str, Any]], summary: Dict[str, Any], args: argparse.Namespace, sqlite_path: str) -> Dict[str, str]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("benchmarks") / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"lahman_100_sqlclass_db{args.db_id}_{ts}"
    json_path = out_dir / f"{stem}.json"
    txt_path = out_dir / f"{stem}.txt"
    csv_path = out_dir / f"{stem}_graph.csv"

    payload = {
        "generated": ts,
        "database_id": args.db_id,
        "base_url": args.base_url,
        "sqlite_path": sqlite_path,
        "test_count": len(results),
        "summary": summary,
        "results": results,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["category", "mode", "total", "passed", "failed", "accuracy_percent"])
        writer.writeheader()
        for row in summary["graph_rows"]:
            writer.writerow(row)

    lines: List[str] = []
    lines.append("SpiderSQL Lahman 100-Test SQL Classification Benchmark")
    lines.append(f"Generated: {ts}")
    lines.append(f"Database ID: {args.db_id}")
    lines.append(f"SQLite path: {sqlite_path}")
    lines.append(f"Total tests: {summary['overall']['total']}")
    lines.append(f"Passed: {summary['overall']['passed']}")
    lines.append(f"Failed: {summary['overall']['failed']}")
    lines.append(f"Accuracy: {summary['overall']['accuracy_percent']}%")
    lines.append("")
    lines.append("CATEGORY SUMMARY")
    lines.append("category | structured passed/total | sql passed/total | combined accuracy")
    lines.append("-" * 90)
    for category, cat_sum in summary["by_category"].items():
        s = summary["by_category_mode"].get(f"{category}:structured", {})
        q = summary["by_category_mode"].get(f"{category}:sql", {})
        lines.append(
            f"{category:18s} | structured {s.get('passed', 0)}/{s.get('total', 0)} "
            f"| sql {q.get('passed', 0)}/{q.get('total', 0)} "
            f"| combined {cat_sum['passed']}/{cat_sum['total']} = {cat_sum['accuracy_percent']}%"
        )
    lines.append("")
    lines.append("FAILED TESTS")
    lines.append("-" * 90)
    failed = [r for r in results if not r["passed"]]
    if not failed:
        lines.append("None")
    for r in failed:
        lines.append(f"{r['id']} [{r['category']} / {r['mode']}] {r['reason']}")
        lines.append(f"  Question/SQL: {r['question'][:300]}")
        if r.get("generated_sql"):
            lines.append(f"  Generated SQL: {str(r['generated_sql'])[:500]}")
        lines.append("")
    txt_path.write_text("\n".join(lines), encoding="utf-8")

    return {"json": str(json_path), "txt": str(txt_path), "csv": str(csv_path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=BASE_URL_DEFAULT)
    parser.add_argument("--db-id", type=int, default=DB_ID_DEFAULT)
    parser.add_argument("--timeout", type=int, default=TIMEOUT_DEFAULT)
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--sqlite-path", default=None)
    parser.add_argument("--only-category", default=None, help="Example: join, group_by, having, subquery")
    parser.add_argument("--only-mode", choices=["structured", "sql", "all"], default="all")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    selected = TESTS
    if args.only_category:
        selected = [t for t in selected if t["category"] == args.only_category]
    if args.only_mode != "all":
        selected = [t for t in selected if t["mode"] == args.only_mode]
    if args.limit is not None:
        selected = selected[: args.limit]

    sqlite_path = discover_lahman_sqlite(args.sqlite_path)
    conn = sqlite3.connect(sqlite_path)

    print("=" * 100)
    print("SpiderSQL Lahman 100-Test SQL Classification Benchmark")
    print(f"Database ID: {args.db_id}")
    print(f"Endpoint:    {args.base_url}")
    print(f"SQLite:      {sqlite_path}")
    print(f"Selected:    {len(selected)} test(s)")
    print("=" * 100)

    results: List[Dict[str, Any]] = []
    for idx, test in enumerate(selected, start=1):
        print(f"[{idx:03d}/{len(selected):03d}] {test['id']} [{test['category']} / {test['mode']}]", flush=True)
        if test["mode"] == "structured":
            result = run_structured(test, args.base_url, args.db_id, args.timeout, conn)
        else:
            result = run_sql(test, args.base_url, args.db_id, args.timeout, conn)
        results.append(result)
        status = "PASS" if result["passed"] else "FAIL"
        print(f"  {status}: {result['reason']} ({result['elapsed_seconds']}s)", flush=True)
        if args.sleep:
            time.sleep(args.sleep)

    summary = summarize(results)
    paths = save_outputs(results, summary, args, sqlite_path)

    print("=" * 100)
    print("DONE")
    print(f"Passed:   {summary['overall']['passed']}/{summary['overall']['total']}")
    print(f"Accuracy: {summary['overall']['accuracy_percent']}%")
    print("\nCategory summary:")
    for category, cat_sum in summary["by_category"].items():
        s = summary["by_category_mode"].get(f"{category}:structured", {})
        q = summary["by_category_mode"].get(f"{category}:sql", {})
        print(
            f"  {category:18s} structured {s.get('passed', 0)}/{s.get('total', 0)} | "
            f"sql {q.get('passed', 0)}/{q.get('total', 0)} | combined {cat_sum['accuracy_percent']}%"
        )
    print("\nSaved:")
    print(f"  JSON: {paths['json']}")
    print(f"  TXT:  {paths['txt']}")
    print(f"  CSV:  {paths['csv']}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
