"""
Run 20 complicated containment-check test cases against a loaded Lahman database.

This benchmark is mixed:
- Cases 01-10: structured natural-language queries
- Cases 11-20: normal SQL queries

Default database_id is 49 because the current loaded Lahman database is:
Lahman Baseball #49

Run from backend folder while the server is running:

    python run_lahman_containment_mixed_20_db49.py

Optional:

    python run_lahman_containment_mixed_20_db49.py --db-id 49 --base-url http://127.0.0.1:8000

Useful partial runs:

    python run_lahman_containment_mixed_20_db49.py --only structured_nl
    python run_lahman_containment_mixed_20_db49.py --only sql
    python run_lahman_containment_mixed_20_db49.py --start 1 --end 5

Output:

    benchmarks/results/containment_mixed_20_db49_<timestamp>.json
    benchmarks/results/containment_mixed_20_db49_<timestamp>.txt

Endpoint called:

    POST /database/{database_id}/check_containment_batch

Each case sends:
    {"queries": [...]}

The backend should generate SQL for NL inputs, accept SQL inputs if supported,
and compare all safe pairs using containment logic.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


TEST_CASES: list[dict[str, Any]] = [
    # ------------------------------------------------------------------
    # 01-10: STRUCTURED NATURAL-LANGUAGE CONTAINMENT TESTS
    # ------------------------------------------------------------------
    {
        "id": 1,
        "type": "structured_nl",
        "name": "Single-season batting threshold containment",
        "queries": [
            "List batting seasons where a player hit more than 50 home runs and had more than 120 RBIs. Show player, year, team, home runs, and RBIs.",
            "List batting seasons where a player hit more than 50 home runs. Show player, year, team, home runs, and RBIs.",
            "List batting seasons where a player had more than 120 RBIs. Show player, year, team, home runs, and RBIs.",
            "List batting seasons where a player hit more than 40 home runs and had more than 100 RBIs. Show player, year, team, home runs, and RBIs.",
        ],
        "expected_note": "HR>50 and RBI>120 should be contained in HR>50, RBI>120, and usually HR>40/RBI>100.",
    },
    {
        "id": 2,
        "type": "structured_nl",
        "name": "Career batting aggregate containment",
        "queries": [
            "Find players with more than 500 career home runs and more than 1500 career RBIs. Show player and career totals.",
            "Find players with more than 500 career home runs. Show player and career home runs.",
            "Find players with more than 1500 career RBIs. Show player and career RBIs.",
            "Find players with more than 300 career home runs. Show player and career home runs.",
        ],
        "expected_note": "Career HR>500/RBI>1500 is narrower than HR>500 and RBI>1500. HR>500 is contained in HR>300.",
    },
    {
        "id": 3,
        "type": "structured_nl",
        "name": "Pitching strikeout and win threshold containment",
        "queries": [
            "List pitching seasons where a pitcher had more than 250 strikeouts and more than 20 wins. Show pitcher, year, team, wins, and strikeouts.",
            "List pitching seasons where a pitcher had more than 250 strikeouts. Show pitcher, year, team, wins, and strikeouts.",
            "List pitching seasons where a pitcher had more than 20 wins. Show pitcher, year, team, wins, and strikeouts.",
            "List pitching seasons where a pitcher had more than 200 strikeouts and more than 15 wins. Show pitcher, year, team, wins, and strikeouts.",
        ],
        "expected_note": "SO>250/W>20 should be contained in SO>250, W>20, and SO>200/W>15.",
    },
    {
        "id": 4,
        "type": "structured_nl",
        "name": "Team season wins, year, and rank containment",
        "queries": [
            "List teams after 1990 that won more than 100 games and finished rank 1. Show year, team, league, wins, losses, and rank.",
            "List teams after 1990 that won more than 100 games. Show year, team, league, wins, losses, and rank.",
            "List teams after 1990 that finished rank 1. Show year, team, league, wins, losses, and rank.",
            "List teams after 1990 that won more than 90 games. Show year, team, league, wins, losses, and rank.",
        ],
        "expected_note": "After-1990/W>100/rank=1 should be contained in after-1990/W>100, after-1990/rank=1, and after-1990/W>90.",
    },
    {
        "id": 5,
        "type": "structured_nl",
        "name": "Player/team season join containment",
        "queries": [
            "Find 2001 batting seasons where a player hit more than 40 home runs and his team won more than 90 games. Show player, team, team wins, and home runs.",
            "Find 2001 batting seasons where a player hit more than 40 home runs. Show player, team, and home runs.",
            "Find 2001 batting seasons for players whose teams won more than 90 games. Show player, team, and team wins.",
            "Find 2001 batting seasons where a player hit more than 30 home runs and his team won more than 80 games. Show player, team, team wins, and home runs.",
        ],
        "expected_note": "HR>40/team wins>90 is narrower than HR>40, team wins>90, and HR>30/team wins>80.",
    },
    {
        "id": 6,
        "type": "structured_nl",
        "name": "Award and batting performance containment",
        "queries": [
            "List players who won a Most Valuable Player award and hit more than 40 home runs in the same year. Show player, year, team, award, and home runs.",
            "List players who won a Most Valuable Player award. Show player, year, and award.",
            "List players who hit more than 40 home runs in a season. Show player, year, team, and home runs.",
            "List players who won any player award and hit more than 40 home runs in the same year. Show player, year, award, and home runs.",
        ],
        "expected_note": "MVP+HR>40 same-year should be contained in MVP winners, HR>40 seasons, and award+HR>40 seasons if generated on compatible player-year keys.",
    },
    {
        "id": 7,
        "type": "structured_nl",
        "name": "Hall of Fame and career batting containment",
        "queries": [
            "Find Hall of Fame inducted players with more than 500 career home runs. Show player and total career home runs.",
            "Find Hall of Fame inducted players. Show player and induction year.",
            "Find players with more than 500 career home runs. Show player and total career home runs.",
            "Find Hall of Fame players with more than 300 career home runs. Show player and total career home runs.",
        ],
        "expected_note": "Inducted+HR>500 should be contained in inducted players, HR>500 players, and inducted+HR>300.",
    },
    {
        "id": 8,
        "type": "structured_nl",
        "name": "College school and career batting containment",
        "queries": [
            "List players who attended a school in California and later had more than 100 career home runs. Show player, school, state, and career home runs.",
            "List players who attended a school in California. Show player, school, and state.",
            "List players with more than 100 career home runs. Show player and career home runs.",
            "List players who attended a school in the United States and later had more than 100 career home runs. Show player, school, country, and career home runs.",
        ],
        "expected_note": "California school + HR>100 should be contained in California school players, HR>100 players, and US school + HR>100 players if state/country mapping is correct.",
    },
    {
        "id": 9,
        "type": "structured_nl",
        "name": "Salary and batting same-season containment",
        "queries": [
            "List player seasons after 2000 where the player salary was more than 20000000 and the player hit more than 30 home runs. Show player, year, team, salary, and home runs.",
            "List player seasons after 2000 where the player salary was more than 20000000. Show player, year, team, and salary.",
            "List batting seasons after 2000 where the player hit more than 30 home runs. Show player, year, team, and home runs.",
            "List player seasons after 2000 where the player salary was more than 10000000 and the player hit more than 20 home runs. Show player, year, team, salary, and home runs.",
        ],
        "expected_note": "Salary>20M/HR>30 after 2000 should be contained in salary>20M, HR>30, and salary>10M/HR>20.",
    },
    {
        "id": 10,
        "type": "structured_nl",
        "name": "Team attendance and winning season containment",
        "queries": [
            "List team seasons after 1990 where attendance was above 3000000 and the team won more than 90 games. Show year, team, attendance, wins, and losses.",
            "List team seasons after 1990 where attendance was above 3000000. Show year, team, attendance, wins, and losses.",
            "List team seasons after 1990 where the team won more than 90 games. Show year, team, attendance, wins, and losses.",
            "List team seasons after 1990 where attendance was above 2000000 and the team won more than 80 games. Show year, team, attendance, wins, and losses.",
        ],
        "expected_note": "Attendance>3M/W>90 after 1990 should be contained in each single condition and the weaker combined threshold.",
    },

    # ------------------------------------------------------------------
    # 11-20: NORMAL SQL CONTAINMENT TESTS
    # ------------------------------------------------------------------
    {
        "id": 11,
        "type": "sql",
        "name": "SQL batting threshold chain",
        "queries": [
            "SELECT playerID, yearID, teamID FROM Batting WHERE HR > 50 AND RBI > 120",
            "SELECT playerID, yearID, teamID FROM Batting WHERE HR > 50",
            "SELECT playerID, yearID, teamID FROM Batting WHERE RBI > 120",
            "SELECT playerID, yearID, teamID FROM Batting WHERE HR > 40 AND RBI > 100",
        ],
        "expected_note": "First SQL result should be contained in the next three.",
    },
    {
        "id": 12,
        "type": "sql",
        "name": "SQL pitching threshold chain",
        "queries": [
            "SELECT playerID, yearID, teamID FROM Pitching WHERE SO > 250 AND W > 20",
            "SELECT playerID, yearID, teamID FROM Pitching WHERE SO > 250",
            "SELECT playerID, yearID, teamID FROM Pitching WHERE W > 20",
            "SELECT playerID, yearID, teamID FROM Pitching WHERE SO > 200 AND W > 15",
        ],
        "expected_note": "First SQL result should be contained in the next three.",
    },
    {
        "id": 13,
        "type": "sql",
        "name": "SQL team season wins and rank",
        "queries": [
            "SELECT yearID, teamID, lgID FROM Teams WHERE yearID > 1990 AND W > 100 AND Rank = 1",
            "SELECT yearID, teamID, lgID FROM Teams WHERE yearID > 1990 AND W > 100",
            "SELECT yearID, teamID, lgID FROM Teams WHERE yearID > 1990 AND Rank = 1",
            "SELECT yearID, teamID, lgID FROM Teams WHERE yearID > 1990 AND W > 90",
        ],
        "expected_note": "First SQL result should be contained in the next three.",
    },
    {
        "id": 14,
        "type": "sql",
        "name": "SQL People birth-year and debut-date containment",
        "queries": [
            "SELECT playerID FROM People WHERE birthYear >= 1980 AND debut >= '2000-01-01'",
            "SELECT playerID FROM People WHERE birthYear >= 1980",
            "SELECT playerID FROM People WHERE debut >= '2000-01-01'",
            "SELECT playerID FROM People WHERE birthYear >= 1970 AND debut >= '1990-01-01'",
        ],
        "expected_note": "First SQL result should be contained in the next three if date strings are comparable.",
    },
    {
        "id": 15,
        "type": "sql",
        "name": "SQL salary threshold containment",
        "queries": [
            "SELECT playerID, yearID, teamID, lgID FROM Salaries WHERE yearID >= 2000 AND salary > 20000000",
            "SELECT playerID, yearID, teamID, lgID FROM Salaries WHERE yearID >= 2000 AND salary > 10000000",
            "SELECT playerID, yearID, teamID, lgID FROM Salaries WHERE salary > 20000000",
            "SELECT playerID, yearID, teamID, lgID FROM Salaries WHERE yearID >= 1990 AND salary > 10000000",
        ],
        "expected_note": "First SQL result should be contained in the next three.",
    },
    {
        "id": 16,
        "type": "sql",
        "name": "SQL People-Batting player containment",
        "queries": [
            "SELECT DISTINCT p.playerID FROM People p JOIN Batting b ON p.playerID = b.playerID WHERE b.HR > 50 AND b.RBI > 120",
            "SELECT DISTINCT p.playerID FROM People p JOIN Batting b ON p.playerID = b.playerID WHERE b.HR > 50",
            "SELECT DISTINCT p.playerID FROM People p JOIN Batting b ON p.playerID = b.playerID WHERE b.RBI > 120",
            "SELECT DISTINCT p.playerID FROM People p JOIN Batting b ON p.playerID = b.playerID WHERE b.HR > 40 AND b.RBI > 100",
        ],
        "expected_note": "First player set should be contained in all three broader player sets.",
    },
    {
        "id": 17,
        "type": "sql",
        "name": "SQL Batting-Teams same-season containment",
        "queries": [
            "SELECT b.playerID, b.yearID, b.teamID FROM Batting b JOIN Teams t ON b.yearID = t.yearID AND b.teamID = t.teamID AND b.lgID = t.lgID WHERE b.yearID = 2001 AND b.HR > 40 AND t.W > 90",
            "SELECT b.playerID, b.yearID, b.teamID FROM Batting b JOIN Teams t ON b.yearID = t.yearID AND b.teamID = t.teamID AND b.lgID = t.lgID WHERE b.yearID = 2001 AND b.HR > 40",
            "SELECT b.playerID, b.yearID, b.teamID FROM Batting b JOIN Teams t ON b.yearID = t.yearID AND b.teamID = t.teamID AND b.lgID = t.lgID WHERE b.yearID = 2001 AND t.W > 90",
            "SELECT b.playerID, b.yearID, b.teamID FROM Batting b JOIN Teams t ON b.yearID = t.yearID AND b.teamID = t.teamID AND b.lgID = t.lgID WHERE b.yearID = 2001 AND b.HR > 30 AND t.W > 80",
        ],
        "expected_note": "First SQL result should be contained in the three broader 2001 player-season sets.",
    },
    {
        "id": 18,
        "type": "sql",
        "name": "SQL CollegePlaying-Schools state containment",
        "queries": [
            "SELECT DISTINCT cp.playerID FROM CollegePlaying cp JOIN Schools s ON cp.schoolID = s.schoolID WHERE s.state = 'CA' AND s.country = 'USA'",
            "SELECT DISTINCT cp.playerID FROM CollegePlaying cp JOIN Schools s ON cp.schoolID = s.schoolID WHERE s.state = 'CA'",
            "SELECT DISTINCT cp.playerID FROM CollegePlaying cp JOIN Schools s ON cp.schoolID = s.schoolID WHERE s.country = 'USA'",
            "SELECT DISTINCT cp.playerID FROM CollegePlaying cp JOIN Schools s ON cp.schoolID = s.schoolID WHERE s.state IN ('CA', 'TX', 'FL') AND s.country = 'USA'",
        ],
        "expected_note": "CA/USA should be contained in CA, USA, and CA/TX/FL in USA.",
    },
    {
        "id": 19,
        "type": "sql",
        "name": "SQL Hall of Fame and career HR containment",
        "queries": [
            "SELECT h.playerID FROM HallOfFame h JOIN Batting b ON h.playerID = b.playerID WHERE h.inducted = 'Y' GROUP BY h.playerID HAVING SUM(b.HR) > 500",
            "SELECT playerID FROM HallOfFame WHERE inducted = 'Y'",
            "SELECT playerID FROM Batting GROUP BY playerID HAVING SUM(HR) > 500",
            "SELECT h.playerID FROM HallOfFame h JOIN Batting b ON h.playerID = b.playerID WHERE h.inducted = 'Y' GROUP BY h.playerID HAVING SUM(b.HR) > 300",
        ],
        "expected_note": "Inducted+career HR>500 should be contained in inducted, career HR>500, and inducted+career HR>300.",
    },
    {
        "id": 20,
        "type": "sql",
        "name": "SQL franchise aggregate containment",
        "queries": [
            "SELECT franchID FROM Teams GROUP BY franchID HAVING SUM(W) > 9000 AND SUM(L) > 8000",
            "SELECT franchID FROM Teams GROUP BY franchID HAVING SUM(W) > 9000",
            "SELECT franchID FROM Teams GROUP BY franchID HAVING SUM(L) > 8000",
            "SELECT franchID FROM Teams GROUP BY franchID HAVING SUM(W) > 7000",
        ],
        "expected_note": "First franchise set should be contained in the next three.",
    },
]


def post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = {"success": False, "raw_text": raw}
            body["_http_status"] = response.status
            return body

    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"success": False, "raw_text": raw}
        body["_http_status"] = exc.code
        return body

    except Exception as exc:
        return {
            "success": False,
            "_http_status": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def compact_json(obj: Any, max_chars: int = 12000) -> str:
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...<truncated>..."


def filtered_cases(only: str, start: int | None, end: int | None) -> list[dict[str, Any]]:
    cases = TEST_CASES

    if only != "all":
        cases = [case for case in cases if case["type"] == only]

    if start is not None:
        cases = [case for case in cases if case["id"] >= start]

    if end is not None:
        cases = [case for case in cases if case["id"] <= end]

    return cases


def write_case_text(f, case: dict[str, Any], response_json: dict[str, Any], elapsed: float) -> None:
    f.write("=" * 100 + "\n")
    f.write(f"CASE {case['id']:02d}: {case['name']}\n")
    f.write(f"TYPE: {case['type']}\n")
    f.write(f"EXPECTED NOTE: {case['expected_note']}\n")
    f.write(f"HTTP STATUS: {response_json.get('_http_status')}\n")
    f.write(f"SUCCESS: {response_json.get('success')}\n")
    f.write(f"ELAPSED SECONDS: {elapsed:.2f}\n")
    f.write("\nINPUT QUERIES:\n")
    for i, query in enumerate(case["queries"], start=1):
        f.write(f"  Q{i}: {query}\n")

    f.write("\nFULL RESPONSE PREVIEW:\n")
    f.write(compact_json(response_json))
    f.write("\n\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 20 mixed containment tests against Lahman.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--db-id", type=int, default=49)
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument("--only", choices=["all", "structured_nl", "sql"], default="all")
    parser.add_argument("--start", type=int, default=None)
    parser.add_argument("--end", type=int, default=None)
    args = parser.parse_args()

    cases = filtered_cases(args.only, args.start, args.end)
    if not cases:
        print("No test cases selected.")
        return 2

    base_url = args.base_url.rstrip("/")
    endpoint = f"{base_url}/database/{args.db_id}/check_containment_batch"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("benchmarks") / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / f"containment_mixed_20_db{args.db_id}_{timestamp}.json"
    txt_path = output_dir / f"containment_mixed_20_db{args.db_id}_{timestamp}.txt"

    all_results: list[dict[str, Any]] = []

    print("=" * 100)
    print("SpiderSQL Lahman Mixed Containment Benchmark")
    print(f"Database ID: {args.db_id}")
    print(f"Endpoint:    {endpoint}")
    print(f"Selected:    {len(cases)} case(s)")
    print(f"Timeout:     {args.timeout}s per case")
    print("=" * 100)

    with txt_path.open("w", encoding="utf-8") as f:
        f.write("SpiderSQL Lahman Mixed Containment Benchmark\n")
        f.write(f"Generated: {timestamp}\n")
        f.write(f"Database ID: {args.db_id}\n")
        f.write(f"Endpoint: {endpoint}\n")
        f.write(f"Selected case count: {len(cases)}\n")
        f.write("Cases 01-10 are structured natural language.\n")
        f.write("Cases 11-20 are normal SQL.\n")
        f.write("\n")

        for case in cases:
            print()
            print("-" * 100)
            print(f"CASE {case['id']:02d}: {case['name']} [{case['type']}]")
            for i, query in enumerate(case["queries"], start=1):
                print(f"  Q{i}: {query}")

            started = time.time()
            response_json = post_json(endpoint, {"queries": case["queries"]}, timeout=args.timeout)
            elapsed = time.time() - started

            result_entry = {
                "case": case,
                "elapsed_seconds": round(elapsed, 3),
                "http_status": response_json.get("_http_status"),
                "success": response_json.get("success"),
                "response": response_json,
            }
            all_results.append(result_entry)

            print(f"success:         {response_json.get('success')}")
            print(f"http_status:     {response_json.get('_http_status')}")
            print(f"elapsed_seconds: {elapsed:.2f}")

            # Print a small high-level preview if available. The response shape may evolve.
            for key in ["summary", "hierarchy", "comparisons", "relationships", "results"]:
                value = response_json.get(key)
                if value:
                    preview = compact_json(value, max_chars=2000)
                    print(f"{key}:")
                    print(preview)
                    break

            write_case_text(f, case, response_json, elapsed)
            time.sleep(args.sleep)

    json_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")

    success_count = sum(1 for item in all_results if item.get("success") is True)
    request_failures = sum(
        1 for item in all_results
        if item.get("http_status") is None and item.get("success") is not True
    )

    print()
    print("=" * 100)
    print("DONE")
    print(f"Successful endpoint responses: {success_count}/{len(all_results)}")
    print(f"Timeout/request failures:      {request_failures}/{len(all_results)}")
    print(f"JSON results saved to:         {json_path}")
    print(f"Text summary saved to:         {txt_path}")
    print("=" * 100)

    return 0 if success_count == len(all_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
