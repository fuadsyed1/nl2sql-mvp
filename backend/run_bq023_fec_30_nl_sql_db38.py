#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

BASE_URL = "http://127.0.0.1:8000"
DATABASE_ID = 38
TIMEOUT_SECONDS = 240
OUTPUT_FILE = "bq023_fec_30_nl_sql_db38.txt"

QUESTIONS: List[str] = [
    "Using indiv20, zipcode_to_census_tracts, census_tracts_new_york, and censustract_2018_5yr, list Kings County census tracts with the average 2020 individual donation amount and 2018 median income.",
    "For New York donors in indiv20, find the top 10 ZIP codes by total individual contribution amount and show donor count, total amount, and average amount.",
    "For each New York congressional district in candidate_2020, list the number of candidates and total 2020 individual contributions received through their authorized committees.",
    "Find 2020 committees that received individual contributions from New York donors and are linked to more than one candidate in candidate_committee_2020; show committee name, candidate count, and total donations.",
    "For each party in candidate_2020, calculate total 2020 individual contributions from New York donors by joining candidate_2020, candidate_committee_2020, committee_2020, and indiv20.",
    "List the top 20 2020 candidates by total donations from Kings County census tracts, using ZIP-to-tract mapping and New York census tract geography.",
    "For every Kings County census tract, compare total 2020 donation amount with median_income and return tracts where donation total is greater than median_income.",
    "Find census tracts in Kings County where the average 2020 donation amount is above the countywide average donation amount and median_income is below the countywide median income.",
    "List 2020 committees that received donations from every New York borough represented in census_tracts_new_york, using donor ZIP code mapped to census tracts.",
    "Find employers in indiv20 with donors in at least 5 different New York census tracts and total donations above 50000; show employer, tract count, donor count, and total amount.",
    "For each occupation in indiv20 among New York donors, show total amount, average donation, distinct donor count, and number of distinct ZIP codes; keep occupations with at least 100 donors.",
    "Find New York ZIP codes where donors contributed to both Democratic and Republican candidates in 2020; show ZIP code and totals by party.",
    "For each census tract in Kings County, count distinct committees receiving donations and return the top 15 tracts by committee diversity.",
    "Find 2020 candidates who received donations from donors in every Kings County ZIP code present in indiv20 after mapping ZIPs to census tracts.",
    "List committees in committee_2020 that have no matching individual contribution rows in indiv20, returning committee id, committee name, and committee type.",
    "Find individual donors in New York who gave to more than 10 distinct committees in 2020; show donor name, ZIP code, committee count, and total amount.",
    "For each month in 2020, calculate New York individual contribution totals and the month-over-month percent change in total contribution amount.",
    "Find the top 5 transaction types in indiv20 for New York donors by total amount and show count, average amount, and maximum transaction amount.",
    "For each candidate office in candidate_2020, show the total number of New York donors and total contribution amount received through linked committees.",
    "Find census tracts in Kings County that have median_income above 100000 but average donation amount below 100, using indiv20 and ACS 2018 census tract data.",
    "Compare 2016 and 2020 individual contributions by committee for committees that exist in both committee_2016 and committee_2020; show committee id, 2016 total, 2020 total, and difference.",
    "Find committees whose 2020 New York donor total is higher than their national 2020 individual contribution total from donors outside New York.",
    "For each New York county represented in census_tracts_new_york, calculate total 2020 individual donations, average donation amount, and median ACS median_income.",
    "Find candidate committees in 2020 where the linked candidate and committee states do not match, then show total New York donations received by those committees.",
    "List donors in indiv20 whose single largest contribution is above the average contribution amount for their ZIP code; show donor name, ZIP code, max amount, and ZIP average.",
    "For each Kings County census tract, rank committees by total donation amount and return the top committee per tract with its total amount.",
    "Find pairs of committees that received donations from the same New York donor on the same transaction date, showing committee ids, donor name, date, and combined amount.",
    "Find 2020 candidates whose New York donation total is above the average New York donation total across all candidates running for the same office.",
    "For each ZIP code in New York, compare the number of unique individual donors with the ACS total_pop of its mapped census tracts and show donor-to-population ratio.",
    "Using indiv20, candidate_2020, candidate_committee_2020, and committee_2020, find candidates who received contributions from donors in all income quartiles of Kings County census tracts based on 2018 median_income.",
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
