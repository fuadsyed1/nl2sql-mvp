#!/usr/bin/env python3
"""
Run 50 normal natural-language queries against SpiderSQL database 46.

Start the FastAPI backend first, then run:

    cd C:\\Projects\\nl2sql-mvp\\backend
    python run_appointments_db46_50_queries.py

The terminal shows PASS or FAIL for each query.
All questions, generated SQL, execution results, and errors are saved in:

    appointments_db46_50_results.txt
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

BASE_URL = "http://127.0.0.1:8000"
DATABASE_ID = 46
TIMEOUT_SECONDS = 180
OUTPUT_FILE = Path("appointments_db46_50_results.txt")

QUESTIONS: List[str] = ['Find doctors who treated patients from a different city and whose average invoice total is higher than the average invoice total for doctors in the same specialty.', 'Find patients who were seen by doctors from more than one specialty and whose total invoiced amount is above the average total for patients with the same insurance provider.', 'Find doctors who handled at least five urgent appointments and whose average base fee for those visits is above the average urgent-visit fee across all doctors.', 'Find patients whose unpaid or partially paid balance is higher than the average outstanding balance for patients with the same insurance provider.', 'Find doctors whose no-show rate is higher than the average no-show rate of doctors in the same specialty and who have handled at least five appointments.', 'Find patients with a chronic condition whose number of completed appointments is higher than the average among patients with a chronic condition.', 'Find medications that were prescribed to patients in both Idaho and Washington and whose average days supplied is above the average for medications in the same class.', 'Find doctors who prescribed controlled substances more often than the average doctor in the same specialty.', 'Find patients who had an abnormal lab result and an unpaid or partially paid invoice for the same appointment.', 'Find appointments whose invoice total is above the average invoice total for the same doctor and that also have a high or critical lab result.', 'Find doctors whose average insurance coverage percentage is lower than the average for doctors in the same specialty.', 'Find patient cities where both the average invoice total and the no-show rate are above the corresponding averages across all cities.', 'Find patients whose most recent appointment was completed and whose lifetime invoiced amount is above the average for patients with the same insurance provider.', 'Find the three doctors with the highest total invoiced amount within each specialty.', 'Find the appointment with the highest invoice total for each patient, including the doctor and appointment date.', 'Find the medication with the greatest total prescribed days within each medication class.', 'Find the latest abnormal lab result for each patient, including the test name, result value, and result date.', 'Find the patient with the largest unpaid balance in each city.', 'Find doctors whose total invoiced amount from completed appointments is above the average doctor total in the same clinic city.', 'Find patients who visited doctors in more than one clinic city and received at least one prescription.', 'Find doctors who treated patients from a different state and whose average invoice total is above the average for doctors in the same specialty.', 'Find medications that were prescribed during completed appointments but were never prescribed during cancelled appointments.', 'Find patients who had at least one appointment with a lab result but no prescription for that same appointment.', 'Find appointments that have at least one prescription but no lab result.', 'Find doctors who have handled appointments but none of their appointments has a lab result.', 'Find medications that have never been prescribed.', 'Find patients who have completed appointments but have never received a prescription during any completed appointment.', 'Find doctors for whom every completed appointment has a fully paid invoice.', 'Find patients for whom every urgent appointment has at least one lab result.', 'Find medications for which every prescription allows a refill.', 'Find doctors whose patients with chronic conditions make up a larger share of their appointments than the average doctor in the same specialty.', 'Find patients who have had at least one appointment of every visit type represented in the appointment records.', "Show each doctor's monthly completed-appointment count together with the previous month's count and the change from the previous month.", 'Show a running total of invoiced amount for each patient ordered by invoice date.', "Show monthly invoiced totals for each specialty together with the previous month's total and percentage change.", 'Show the cumulative prescribed days for each medication over time using the related appointment dates.', 'Find patients whose monthly invoiced amount increased for at least two consecutive months.', 'Find doctors whose average invoice total for a visit type is above the overall average for that same visit type.', 'Find appointments whose invoice total is higher than the average invoice total for appointments of the same visit type.', 'Find lab results whose value is above the average for the same test and whose patient has spent more than the average patient.', 'Find medications whose unit cost is above the average for their class and whose prescription count is also above the average prescription count for medications in that class.', 'Find pairs of doctors in the same specialty whose appointment counts differ by more than ten.', 'Find pairs of patients in the same city whose lifetime invoiced amounts differ by more than 500 dollars.', 'Find patients who have been treated by at least one doctor from every specialty represented in the doctor records.', 'Find doctors who have prescribed at least one medication from every medication class represented in the medication records.', 'Find insurance providers for which every patient with a chronic condition has at least one completed appointment.', 'Find specialties where every doctor has handled at least one completed appointment.', 'Find patients with abnormal results in more than one type of lab test and an outstanding balance above the average patient outstanding balance.', 'Find doctors whose average number of lab tests per appointment is above the average for their specialty and whose total invoiced amount is above the average for their clinic city.', 'Find doctors who treated patients from a different city, prescribed at least one medication to those patients, and have an average invoice total above the average for their specialty.']


def post_query(question: str) -> Dict[str, Any]:
    url = f"{BASE_URL}/database/{DATABASE_ID}/execute_sql"
    payload = json.dumps({"question": question}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.time()

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
            data["_http_status"] = response.status
            data["_elapsed_seconds"] = round(time.time() - started, 2)
            return data
    except urllib.error.HTTPError as exc:
        return {
            "success": False,
            "_http_status": exc.code,
            "_elapsed_seconds": round(time.time() - started, 2),
            "_error": exc.read().decode("utf-8", errors="replace"),
        }
    except Exception as exc:
        return {
            "success": False,
            "_http_status": None,
            "_elapsed_seconds": round(time.time() - started, 2),
            "_error": repr(exc),
        }


def extract_sql(response: Dict[str, Any]) -> str:
    generated = response.get("generated_sql")

    if isinstance(generated, dict):
        sql = generated.get("sql")
        if isinstance(sql, str):
            return sql.strip()

    if isinstance(generated, str):
        return generated.strip()

    for key in ("selected_sql", "sql"):
        value = response.get(key)
        if isinstance(value, str):
            return value.strip()

    return ""


def format_result(
    number: int,
    question: str,
    response: Dict[str, Any],
) -> str:
    sql = extract_sql(response)
    execution = response.get("execution")
    if not isinstance(execution, dict):
        execution = {}

    error = (
        response.get("_error")
        or response.get("error")
        or response.get("detail")
        or execution.get("error")
        or ""
    )

    lines = [
        "=" * 100,
        f"QUERY {number:02d}",
        f"QUESTION: {question}",
        f"SUCCESS: {bool(response.get('success'))}",
        f"HTTP STATUS: {response.get('_http_status')}",
        f"ELAPSED SECONDS: {response.get('_elapsed_seconds')}",
        f"ROW COUNT: {execution.get('row_count')}",
        "",
        "SQL:",
        sql or "-- NO SQL GENERATED",
        "",
        "RESULT:",
    ]

    result_data = {
        "columns": execution.get("columns"),
        "rows": execution.get("rows"),
        "row_count": execution.get("row_count"),
    }
    lines.append(json.dumps(result_data, indent=2, ensure_ascii=False, default=str))

    if error:
        lines.extend(["", "ERROR:", str(error)])

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUTPUT_FILE.write_text(
        "SpiderSQL Appointments Database #46 - 50 Query Results\n\n",
        encoding="utf-8",
    )

    passed = 0

    for index, question in enumerate(QUESTIONS, start=1):
        response = post_query(question)
        sql = extract_sql(response)
        success = bool(response.get("success")) and bool(sql)

        if success:
            passed += 1

        status = "PASS" if success else "FAIL"
        print(
            f"[{index:02d}/50] {status} "
            f"{response.get('_elapsed_seconds')}s",
            flush=True,
        )

        with OUTPUT_FILE.open("a", encoding="utf-8") as output:
            output.write(format_result(index, question, response))
            output.write("\n")

    with OUTPUT_FILE.open("a", encoding="utf-8") as output:
        output.write("=" * 100 + "\n")
        output.write(f"SUMMARY: {passed} PASS, {50 - passed} FAIL\n")

    print(f"Saved results to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
