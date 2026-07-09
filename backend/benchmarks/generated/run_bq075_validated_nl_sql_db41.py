#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

BASE_URL = "http://127.0.0.1:8000"
DATABASE_ID = 41
TIMEOUT_SECONDS = 240
OUTPUT_FILE = "bq075_validated_nl_sql_db41.txt"

QUESTIONS: List[str] = [
    "Using t_1990_q1, find geoid groups whose average qtrly_estabs_11_agriculture_forestry_fishing_and_hunting is greater than the overall average qtrly_estabs_11_agriculture_forestry_fishing_and_hunting in t_1990_q1; show geoid, row count, average qtrly_estabs_11_agriculture_forestry_fishing_and_hunting, and the difference from the overall average.",
    "Using t_1990_q1, group rows by geoid; for each group calculate row count, total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting, and average avg_wkly_wage_11_agriculture_forestry_fishing_and_hunting; return only groups whose total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting is above the average group total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting, ordered by total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting descending.",
    "Using t_1990_q1, group rows by the pair (geoid, area_fips); show both columns and the row count, keep only pairs with at least 2 rows, and order by geoid then row count descending.",
    "Using t_1990_q2, find geoid groups whose average qtrly_estabs_11_agriculture_forestry_fishing_and_hunting is greater than the overall average qtrly_estabs_11_agriculture_forestry_fishing_and_hunting in t_1990_q2; show geoid, row count, average qtrly_estabs_11_agriculture_forestry_fishing_and_hunting, and the difference from the overall average.",
    "Using t_1990_q2, group rows by geoid; for each group calculate row count, total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting, and average avg_wkly_wage_11_agriculture_forestry_fishing_and_hunting; return only groups whose total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting is above the average group total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting, ordered by total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting descending.",
    "Using t_1990_q2, group rows by the pair (geoid, area_fips); show both columns and the row count, keep only pairs with at least 2 rows, and order by geoid then row count descending.",
    "Using t_1990_q3, find geoid groups whose average qtrly_estabs_11_agriculture_forestry_fishing_and_hunting is greater than the overall average qtrly_estabs_11_agriculture_forestry_fishing_and_hunting in t_1990_q3; show geoid, row count, average qtrly_estabs_11_agriculture_forestry_fishing_and_hunting, and the difference from the overall average.",
    "Using t_1990_q3, group rows by geoid; for each group calculate row count, total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting, and average avg_wkly_wage_11_agriculture_forestry_fishing_and_hunting; return only groups whose total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting is above the average group total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting, ordered by total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting descending.",
    "Using t_1990_q3, group rows by the pair (geoid, area_fips); show both columns and the row count, keep only pairs with at least 2 rows, and order by geoid then row count descending.",
    "Using t_1990_q4, find geoid groups whose average qtrly_estabs_11_agriculture_forestry_fishing_and_hunting is greater than the overall average qtrly_estabs_11_agriculture_forestry_fishing_and_hunting in t_1990_q4; show geoid, row count, average qtrly_estabs_11_agriculture_forestry_fishing_and_hunting, and the difference from the overall average.",
    "Using t_1990_q4, group rows by geoid; for each group calculate row count, total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting, and average avg_wkly_wage_11_agriculture_forestry_fishing_and_hunting; return only groups whose total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting is above the average group total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting, ordered by total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting descending.",
    "Using t_1990_q4, group rows by the pair (geoid, area_fips); show both columns and the row count, keep only pairs with at least 2 rows, and order by geoid then row count descending.",
    "Using t_1991_q1, find geoid groups whose average qtrly_estabs_11_agriculture_forestry_fishing_and_hunting is greater than the overall average qtrly_estabs_11_agriculture_forestry_fishing_and_hunting in t_1991_q1; show geoid, row count, average qtrly_estabs_11_agriculture_forestry_fishing_and_hunting, and the difference from the overall average.",
    "Using t_1991_q1, group rows by geoid; for each group calculate row count, total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting, and average avg_wkly_wage_11_agriculture_forestry_fishing_and_hunting; return only groups whose total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting is above the average group total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting, ordered by total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting descending.",
    "Using t_1991_q1, group rows by the pair (geoid, area_fips); show both columns and the row count, keep only pairs with at least 2 rows, and order by geoid then row count descending.",
    "Using t_1991_q2, find geoid groups whose average qtrly_estabs_11_agriculture_forestry_fishing_and_hunting is greater than the overall average qtrly_estabs_11_agriculture_forestry_fishing_and_hunting in t_1991_q2; show geoid, row count, average qtrly_estabs_11_agriculture_forestry_fishing_and_hunting, and the difference from the overall average.",
    "Using t_1991_q2, group rows by geoid; for each group calculate row count, total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting, and average avg_wkly_wage_11_agriculture_forestry_fishing_and_hunting; return only groups whose total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting is above the average group total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting, ordered by total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting descending.",
    "Using t_1991_q2, group rows by the pair (geoid, area_fips); show both columns and the row count, keep only pairs with at least 2 rows, and order by geoid then row count descending.",
    "Using t_1991_q3, find geoid groups whose average qtrly_estabs_11_agriculture_forestry_fishing_and_hunting is greater than the overall average qtrly_estabs_11_agriculture_forestry_fishing_and_hunting in t_1991_q3; show geoid, row count, average qtrly_estabs_11_agriculture_forestry_fishing_and_hunting, and the difference from the overall average.",
    "Using t_1991_q3, group rows by geoid; for each group calculate row count, total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting, and average avg_wkly_wage_11_agriculture_forestry_fishing_and_hunting; return only groups whose total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting is above the average group total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting, ordered by total qtrly_estabs_11_agriculture_forestry_fishing_and_hunting descending."
]


def post_query(question: str) -> Dict[str, Any]:
    payload = json.dumps({"question": question}).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}/database/{DATABASE_ID}/execute_sql",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_sql(response: Dict[str, Any]) -> str:
    generated = response.get("generated_sql")
    if isinstance(generated, dict):
        sql = generated.get("sql")
        if isinstance(sql, str) and sql.strip():
            return sql.strip()
    sql = response.get("sql")
    if isinstance(sql, str) and sql.strip():
        return sql.strip()
    return "-- NO SQL GENERATED"


def normalize_sql(sql: str) -> str:
    sql = sql.strip()
    if not sql:
        return "-- NO SQL GENERATED;"
    if sql.startswith("--"):
        return sql
    return sql if sql.endswith(";") else sql + ";"


def main() -> None:
    output_path = Path(OUTPUT_FILE)
    with output_path.open("w", encoding="utf-8") as out:
        for i, question in enumerate(QUESTIONS, start=1):
            print(f"\n===== QUERY {i:02d} =====")
            print("NL:")
            print(question)
            out.write(f"===== QUERY {i:02d} =====\n")
            out.write("NL:\n")
            out.write(question + "\n\n")

            try:
                sql = normalize_sql(extract_sql(post_query(question)))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                sql = f"-- ERROR: HTTPError {exc.code}: {body}"
            except Exception as exc:
                sql = f"-- ERROR: {type(exc).__name__}: {exc}"

            print("SQL:")
            print(sql)
            print()
            out.write("SQL:\n")
            out.write(sql + "\n\n")

    print(f"Saved NL + SQL output to: {output_path.resolve()}")


if __name__ == "__main__":
    main()
