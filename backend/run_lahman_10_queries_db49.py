"""
Run 10 complicated natural-language test queries against the loaded Lahman database.

Default database_id is 49 because the UI showed:
Database created: Lahman Baseball #49

Usage:
    python run_lahman_10_queries_db49.py

Optional:
    python run_lahman_10_queries_db49.py --db-id 49 --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import requests


QUERIES: list[str] = [
    "Find the top 10 players by total career home runs. Show playerID, first name, last name, total home runs, total RBIs, number of seasons played, and number of distinct teams. Order by total home runs descending.",

    "For each team in the 2001 season, compare the team's recorded home run total in Teams with the sum of player home runs from Batting. Show yearID, teamID, team name, Teams.HR, summed player HR, and the difference. Only show teams where the values do not match.",

    "List players who had at least 3 seasons with 40 or more home runs. Show playerID, first name, last name, number of 40-HR seasons, career home runs, and the first and last year they achieved 40 HR. Order by number of 40-HR seasons descending, then career home runs descending.",

    "Find Hall of Fame inducted players and summarize their career batting totals. Show playerID, first name, last name, Hall of Fame induction year, total hits, total home runs, total RBIs, total games, and career batting average calculated as total hits divided by total at-bats. Only include inducted players with at least 3000 career at-bats.",

    "For every franchise, find the season with the best win percentage. Show franchID, teamID, team name, yearID, wins, losses, games, and win percentage. Ignore seasons with fewer than 100 games. Return the top 25 franchise seasons by win percentage.",

    "Find pitchers who won at least one Cy Young Award and also had at least one season with 250 or more strikeouts. Show playerID, first name, last name, award year, maximum single-season strikeouts, total career wins, and total career strikeouts.",

    "For each decade, find the player with the highest total batting hits in that decade. Show decade, playerID, first name, last name, total hits, total at-bats, total home runs, and number of teams played for in that decade.",

    "Find teams that won the World Series and had a regular-season winning percentage above .600. Show yearID, teamID, team name, league, wins, losses, games, winning percentage, and rank in division or league if available. Order by yearID descending.",

    "Find players whose career batting average is at least .320 and who have at least 5000 career at-bats. Show playerID, first name, last name, total hits, total at-bats, batting average, total doubles, total triples, total home runs, and total RBIs. Order by batting average descending.",

    "For each school, find how many major league players attended it and the total career home runs produced by those players. Show schoolID, school name, city, state, player count, total career home runs, and total career hits. Keep only schools with at least 20 players and order by total career home runs descending.",
]


def compact(obj: Any, max_chars: int = 4000) -> str:
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...<truncated>..."


def extract_sql(response_json: dict[str, Any]) -> str:
    generated = response_json.get("generated_sql")
    if isinstance(generated, dict):
        return str(generated.get("sql") or "")
    if isinstance(generated, str):
        return generated
    return ""


def extract_row_count(response_json: dict[str, Any]) -> Any:
    execution = response_json.get("execution")
    if isinstance(execution, dict):
        return execution.get("row_count")
    return None


def run_query(base_url: str, db_id: int, question: str, timeout: int) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/database/{db_id}/execute_sql"
    response = requests.post(url, json={"question": question}, timeout=timeout)
    try:
        payload = response.json()
    except Exception:
        payload = {"success": False, "raw_text": response.text}
    payload["_http_status"] = response.status_code
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--db-id", type=int, default=49)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument("--out", default="lahman_10_query_results_db49.json")
    parser.add_argument("--txt", default="lahman_10_query_results_db49.txt")
    args = parser.parse_args()

    all_results: list[dict[str, Any]] = []
    text_lines: list[str] = []

    print(f"Running {len(QUERIES)} Lahman NL queries against database #{args.db_id}")
    print(f"Backend: {args.base_url}")
    print("-" * 80)

    for i, question in enumerate(QUERIES, start=1):
        print(f"\nQUERY {i:02d}")
        print(question)

        started = time.time()
        try:
            result = run_query(args.base_url, args.db_id, question, args.timeout)
        except requests.RequestException as exc:
            result = {"success": False, "error": str(exc), "_http_status": None}
        elapsed = time.time() - started

        sql = extract_sql(result)
        row_count = extract_row_count(result)

        all_results.append({
            "query_number": i,
            "question": question,
            "elapsed_seconds": round(elapsed, 3),
            "response": result,
        })

        success = result.get("success")
        print(f"success: {success}")
        print(f"http_status: {result.get('_http_status')}")
        print(f"row_count: {row_count}")
        print(f"elapsed_seconds: {elapsed:.2f}")
        if sql:
            print("SQL:")
            print(sql)

        text_lines.extend([
            "=" * 80,
            f"QUERY {i:02d}",
            "",
            "NL:",
            question,
            "",
            f"SUCCESS: {success}",
            f"HTTP STATUS: {result.get('_http_status')}",
            f"ROW COUNT: {row_count}",
            f"ELAPSED SECONDS: {elapsed:.2f}",
            "",
            "SQL:",
            sql or "<no sql>",
            "",
            "RESPONSE PREVIEW:",
            compact(result, max_chars=3000),
            "",
        ])

        time.sleep(args.sleep)

    out_path = Path(args.out)
    txt_path = Path(args.txt)
    out_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
    txt_path.write_text("\n".join(text_lines), encoding="utf-8")

    print("\n" + "=" * 80)
    print(f"Saved full JSON results to: {out_path.resolve()}")
    print(f"Saved text summary to:     {txt_path.resolve()}")
    successes = sum(1 for r in all_results if r["response"].get("success"))
    print(f"Successful responses: {successes}/{len(all_results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
