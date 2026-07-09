"""
Run 25 natural-language containment benchmark tests against SpiderSQL backend.

Usage from backend folder while server is running:
    python run_containment_25_tests_db42.py

Optional:
    set CONTAINMENT_DB_ID=42
    set SPIDERSQL_BASE_URL=http://localhost:8000

Output:
    benchmarks/results/containment_batch_25_results_db<id>_<timestamp>.txt

This script calls:
    POST /database/{database_id}/check_containment_batch

Each test contains 2+ natural-language queries. The backend should generate SQL
for all queries and compare every safe pair using live-database EXCEPT logic.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


BASE_URL = os.environ.get("SPIDERSQL_BASE_URL", "http://localhost:8000").rstrip("/")
DATABASE_ID = int(os.environ.get("CONTAINMENT_DB_ID", "42"))
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("CONTAINMENT_TIMEOUT", "240"))


TEST_CASES: List[Dict[str, Any]] = [
    {
        "id": 1,
        "name": "Club budget threshold chain with empty result",
        "queries": [
            "Which clubs have a budget greater than 5000?",
            "Which clubs have a budget greater than 3000?",
            "Which clubs have a budget greater than 1000?",
            "Which clubs have a budget greater than 9000?",
        ],
        "expected_note": "Budget > 5000 should be contained in > 3000 and > 1000. Budget > 9000 may be empty and contained in all compatible results on the current DB.",
    },
    {
        "id": 2,
        "name": "Club budget and founded-year narrowing",
        "queries": [
            "Which clubs have a budget greater than 3000 and were founded after 2000?",
            "Which clubs have a budget greater than 3000?",
            "Which clubs were founded after 2000?",
            "Which clubs have a budget greater than 1000?",
        ],
        "expected_note": "The first query should be narrower than the budget-only and founded-year-only queries when SQL generation is correct.",
    },
    {
        "id": 3,
        "name": "Club category and budget interactions",
        "queries": [
            "Which sports clubs have a budget greater than 3000?",
            "Which sports clubs have a budget greater than 1000?",
            "Which clubs have a budget greater than 3000?",
            "Which cultural clubs have a budget greater than 3000?",
        ],
        "expected_note": "Sports + high budget should be contained in sports + lower budget and all high-budget clubs. Sports and cultural high-budget queries should usually be incomparable or disjoint.",
    },
    {
        "id": 4,
        "name": "Student GPA threshold chain",
        "queries": [
            "Which students have a GPA greater than 3.8?",
            "Which students have a GPA greater than 3.5?",
            "Which students have a GPA greater than 3.0?",
            "Which students have a GPA greater than 4.0?",
        ],
        "expected_note": "Higher GPA thresholds should be contained in lower GPA thresholds. GPA > 4.0 may be empty.",
    },
    {
        "id": 5,
        "name": "Student GPA, scholarship, and major",
        "queries": [
            "Which scholarship students have a GPA greater than 3.5?",
            "Which students have a GPA greater than 3.5?",
            "Which scholarship students have a GPA greater than 3.0?",
            "Which biology students have a GPA greater than 3.5?",
        ],
        "expected_note": "Scholarship+GPA should be contained in GPA-only and scholarship+lower-GPA. Biology+GPA may be incomparable with scholarship+GPA.",
    },
    {
        "id": 6,
        "name": "Active memberships and officer roles",
        "queries": [
            "Which students are active officers in clubs?",
            "Which students are active members of clubs?",
            "Which students are officers in clubs?",
            "Which students are active presidents in clubs?",
        ],
        "expected_note": "Active officers should be contained in active members and officers. Active presidents may be contained in active members and possibly officers only if role mapping is generated correctly.",
    },
    {
        "id": 7,
        "name": "Membership role chain by club entity",
        "queries": [
            "Which clubs have active president memberships?",
            "Which clubs have active officer memberships?",
            "Which clubs have active memberships?",
            "Which clubs have inactive memberships?",
        ],
        "expected_note": "Active role-specific club queries should be contained in clubs with active memberships. Active and inactive membership sets may be incomparable.",
    },
    {
        "id": 8,
        "name": "Event capacity threshold chain",
        "queries": [
            "Which events have capacity greater than 100?",
            "Which events have capacity greater than 75?",
            "Which events have capacity greater than 50?",
            "Which events have capacity greater than 300?",
        ],
        "expected_note": "Capacity > 100 should be contained in > 75 and > 50. Capacity > 300 may be empty.",
    },
    {
        "id": 9,
        "name": "Event type and food narrowing",
        "queries": [
            "Which workshop events provided food?",
            "Which workshop events were held?",
            "Which events provided food?",
            "Which social events provided food?",
        ],
        "expected_note": "Workshop+food should be contained in workshops and food events. Social+food may be incomparable with workshop+food.",
    },
    {
        "id": 10,
        "name": "Events by date and capacity",
        "queries": [
            "Which events after February 1 2025 have capacity greater than 100?",
            "Which events after February 1 2025 have capacity greater than 50?",
            "Which events have capacity greater than 100?",
            "Which events before February 1 2025 have capacity greater than 100?",
        ],
        "expected_note": "After-date+capacity should be contained in after-date lower capacity and all capacity>100. Before-date and after-date versions may be incomparable.",
    },
    {
        "id": 11,
        "name": "Club-hosted events with type and food",
        "queries": [
            "Which clubs hosted workshop events with food provided?",
            "Which clubs hosted workshop events?",
            "Which clubs hosted events with food provided?",
            "Which clubs hosted any events?",
        ],
        "expected_note": "Workshop+food clubs should be contained in workshop-event clubs, food-event clubs, and event-hosting clubs.",
    },
    {
        "id": 12,
        "name": "Club-hosted events by capacity threshold",
        "queries": [
            "Which clubs hosted events with capacity greater than 150?",
            "Which clubs hosted events with capacity greater than 100?",
            "Which clubs hosted events with capacity greater than 50?",
            "Which clubs hosted workshop events with capacity greater than 100?",
        ],
        "expected_note": "Higher capacity thresholds should be contained in lower thresholds. Workshop+capacity should be contained in all clubs hosting capacity>100 events.",
    },
    {
        "id": 13,
        "name": "Attendance feedback and stayed minutes by student",
        "queries": [
            "Which students attended events and gave feedback score greater than 4?",
            "Which students attended events and gave feedback score greater than 3?",
            "Which students attended events and stayed more than 90 minutes?",
            "Which students attended events?",
        ],
        "expected_note": "High feedback students should be contained in lower feedback and attended-event students. Stayed-minute query may overlap but can be incomparable with feedback queries.",
    },
    {
        "id": 14,
        "name": "Attendance by event entity with feedback/stay filters",
        "queries": [
            "Which events had attendees with feedback score greater than 4?",
            "Which events had attendees with feedback score greater than 3?",
            "Which events had attendees who stayed more than 90 minutes?",
            "Which events had any attendance?",
        ],
        "expected_note": "Feedback >4 should be contained in feedback >3 and any attendance. Stayed>90 may be incomparable with feedback thresholds.",
    },
    {
        "id": 15,
        "name": "Vendor approval and city/service filters",
        "queries": [
            "Which approved vendors are in Boise?",
            "Which vendors are in Boise?",
            "Which approved vendors were used for event expenses?",
            "Which vendors were used for event expenses?",
        ],
        "expected_note": "Approved Boise vendors should be contained in Boise vendors. Approved used vendors should be contained in used vendors. Cross comparisons may be incomparable.",
    },
    {
        "id": 16,
        "name": "Vendor service type and approval",
        "queries": [
            "Which approved printing vendors were used for event expenses?",
            "Which printing vendors were used for event expenses?",
            "Which approved vendors were used for event expenses?",
            "Which vendors were used for event expenses?",
        ],
        "expected_note": "Approved printing used vendors should be contained in printing used vendors, approved used vendors, and all used vendors.",
    },
    {
        "id": 17,
        "name": "Event expenses amount and reimbursement",
        "queries": [
            "Which event expenses were reimbursed and had amount greater than 200?",
            "Which event expenses were reimbursed?",
            "Which event expenses had amount greater than 200?",
            "Which event expenses had amount greater than 100?",
        ],
        "expected_note": "Reimbursed+amount>200 should be contained in reimbursed and amount>200. Amount>200 should be contained in amount>100.",
    },
    {
        "id": 18,
        "name": "Events with expensive reimbursed expenses",
        "queries": [
            "Which events had reimbursed expenses greater than 200?",
            "Which events had reimbursed expenses?",
            "Which events had expenses greater than 200?",
            "Which events had any expenses?",
        ],
        "expected_note": "Events with reimbursed expenses >200 should be contained in reimbursed-expense events, amount>200 expense events, and any-expense events.",
    },
    {
        "id": 19,
        "name": "Clubs with event expenses and vendors",
        "queries": [
            "Which clubs had events with approved vendors for expenses?",
            "Which clubs had events with vendors for expenses?",
            "Which clubs had events with reimbursed expenses?",
            "Which clubs had any event expenses?",
        ],
        "expected_note": "Approved-vendor expense clubs should be contained in vendor-expense clubs and any-expense clubs. Reimbursed expense clubs should be contained in any-expense clubs.",
    },
    {
        "id": 20,
        "name": "Equipment loan return condition by student",
        "queries": [
            "Which students returned equipment in damaged condition?",
            "Which students returned equipment in damaged or missing part condition?",
            "Which students borrowed equipment?",
            "Which students returned equipment in good condition?",
        ],
        "expected_note": "Damaged-return students should be contained in damaged-or-missing and borrowed-equipment students. Good condition may be incomparable with damaged condition.",
    },
    {
        "id": 21,
        "name": "Equipment loan status by club",
        "queries": [
            "Which clubs have equipment loans with missing part condition on return?",
            "Which clubs have equipment loans that were returned with any condition?",
            "Which clubs have equipment loans?",
            "Which clubs have equipment loans that have not been returned?",
        ],
        "expected_note": "Missing-part returned loans should be contained in returned loans and all equipment-loan clubs. Not-returned loans may be incomparable with returned loans.",
    },
    {
        "id": 22,
        "name": "Cross-table students: active membership plus attendance",
        "queries": [
            "Which students are active club members and attended events?",
            "Which students are active club members?",
            "Which students attended events?",
            "Which students are inactive club members and attended events?",
        ],
        "expected_note": "Active-member attendees should be contained in active members and attended students. Inactive-member attendees may be incomparable with active-member attendees.",
    },
    {
        "id": 23,
        "name": "Cross-table clubs: active members plus events",
        "queries": [
            "Which clubs have active members and hosted events with food provided?",
            "Which clubs have active members and hosted events?",
            "Which clubs hosted events with food provided?",
            "Which clubs have active members?",
        ],
        "expected_note": "Active-members+food-events should be contained in active-members+events, food-event clubs, and active-member clubs.",
    },
    {
        "id": 24,
        "name": "Multi-condition event expense categories",
        "queries": [
            "Which events had travel expenses greater than 100?",
            "Which events had travel expenses?",
            "Which events had expenses greater than 100?",
            "Which events had supplies expenses greater than 100?",
        ],
        "expected_note": "Travel+amount>100 should be contained in travel-expense events and amount>100 expense events. Supplies+amount>100 may be incomparable with travel+amount>100.",
    },
    {
        "id": 25,
        "name": "Mixed club filters: budget, events, and equipment",
        "queries": [
            "Which clubs have a budget greater than 3000 and hosted events?",
            "Which clubs have a budget greater than 3000?",
            "Which clubs hosted events?",
            "Which clubs have equipment loans and a budget greater than 3000?",
            "Which clubs have equipment loans?",
        ],
        "expected_note": "Budget+events should be contained in budget-only and event-hosting clubs. Budget+equipment should be contained in budget-only and equipment-loan clubs. The two combined queries may be incomparable.",
    },
]


def post_json(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        text = resp.read().decode("utf-8", errors="replace")
        return json.loads(text)


def qlabel(query_id: int) -> str:
    return f"Q{query_id}"


def fmt_list(values: List[Any]) -> str:
    if not values:
        return "-"
    return ", ".join(qlabel(int(v)) for v in values)


def summarize_query_result(q: Dict[str, Any]) -> List[str]:
    lines = []
    query_id = q.get("query_id", "?")
    lines.append(f"{qlabel(int(query_id))}. {q.get('question', '')}")
    lines.append(f"   success: {q.get('success')} | safe: {q.get('safe')} | rows: {q.get('row_count')} | empty: {q.get('empty_result')}")
    if q.get("safety_reason"):
        lines.append(f"   safety_reason: {q.get('safety_reason')}")
    if q.get("low_confidence"):
        lines.append("   low_confidence: true")
    if q.get("has_fatal_validation"):
        lines.append("   has_fatal_validation: true")
    warnings = q.get("warnings") or []
    if warnings:
        lines.append(f"   warnings: {warnings}")
    lines.append(f"   columns: {q.get('execution_columns')}")
    sql = (q.get("sql") or "").replace("\n", " ").strip()
    lines.append(f"   sql: {sql}")
    return lines


def summarize_query_summary(s: Dict[str, Any]) -> str:
    return (
        f"{qlabel(int(s.get('query_id')))} | status={s.get('status')} | empty={s.get('empty_result')} | "
        f"contained_in={fmt_list(s.get('contained_in') or [])} | "
        f"contains={fmt_list(s.get('contains') or [])} | "
        f"equivalent_to={fmt_list(s.get('equivalent_to') or [])} | "
        f"incomparable_with={fmt_list(s.get('incomparable_with') or [])} | "
        f"unknown_with={fmt_list(s.get('unknown_with') or [])}"
    )


def summarize_pairwise(p: Dict[str, Any]) -> List[str]:
    a = int(p.get("query_a"))
    b = int(p.get("query_b"))
    rel = p.get("relationship")
    lines = [f"{qlabel(a)} vs {qlabel(b)}: {rel}"]
    if p.get("explanation"):
        lines.append(f"   {p.get('explanation')}")
    a_rows = p.get("a_minus_b_rows") or []
    b_rows = p.get("b_minus_a_rows") or []
    if a_rows:
        lines.append(f"   {qlabel(a)} rows missing from {qlabel(b)}: {len(a_rows)} sample rows")
        lines.append(f"   sample: {a_rows[:5]}")
    if b_rows:
        lines.append(f"   {qlabel(b)} rows missing from {qlabel(a)}: {len(b_rows)} sample rows")
        lines.append(f"   sample: {b_rows[:5]}")
    return lines


def write_case_report(f, case: Dict[str, Any], response: Dict[str, Any], elapsed: float) -> None:
    f.write("\n" + "=" * 100 + "\n")
    f.write(f"TEST {case['id']:02d}: {case['name']}\n")
    f.write("=" * 100 + "\n")
    f.write(f"Expected note: {case['expected_note']}\n")
    f.write(f"Elapsed seconds: {elapsed:.2f}\n")
    f.write(f"success: {response.get('success')} | proof_type: {response.get('proof_type')} | checked_on_current_database: {response.get('checked_on_current_database')}\n")
    if response.get("limitations"):
        f.write(f"limitations: {response.get('limitations')}\n")
    warnings = response.get("warnings") or []
    if warnings:
        f.write(f"warnings: {warnings}\n")

    f.write("\nINPUT QUERIES\n")
    for i, q in enumerate(case["queries"], 1):
        f.write(f"  Q{i}: {q}\n")

    f.write("\nGENERATED SQL / QUERY RESULTS\n")
    for q in response.get("query_results", []):
        for line in summarize_query_result(q):
            f.write(line + "\n")

    f.write("\nRELATIONSHIP SUMMARY\n")
    for s in response.get("query_summaries", []):
        f.write("  " + summarize_query_summary(s) + "\n")

    f.write("\nPAIRWISE RELATIONSHIPS\n")
    for p in response.get("pairwise_relationships", []):
        for line in summarize_pairwise(p):
            f.write("  " + line + "\n")

    f.write("\nRAW JSON\n")
    f.write(json.dumps(response, indent=2, ensure_ascii=False))
    f.write("\n")


def main() -> int:
    output_dir = Path("benchmarks") / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"containment_batch_25_results_db{DATABASE_ID}_{timestamp}.txt"

    endpoint = f"{BASE_URL}/database/{DATABASE_ID}/check_containment_batch"
    started = datetime.now()
    pass_count = 0
    fail_count = 0

    with output_path.open("w", encoding="utf-8") as f:
        f.write("SpiderSQL Containment Batch Benchmark - 25 Complicated Tests\n")
        f.write(f"Started: {started.isoformat(timespec='seconds')}\n")
        f.write(f"Base URL: {BASE_URL}\n")
        f.write(f"Database ID: {DATABASE_ID}\n")
        f.write(f"Endpoint: {endpoint}\n")
        f.write("\nManual scoring note:\n")
        f.write("These tests are for manual review. The script records generated SQL, row counts, pairwise relationships, and counterexamples.\n")
        f.write("A backend response can be executable but semantically wrong, so manually inspect SQL and relationships.\n")

        for case in TEST_CASES:
            print(f"[{case['id']:02d}/25] {case['name']} ...", flush=True)
            payload = {"queries": case["queries"]}
            t0 = time.time()
            try:
                response = post_json(endpoint, payload)
                elapsed = time.time() - t0
                write_case_report(f, case, response, elapsed)
                if response.get("success"):
                    pass_count += 1
                    print(f"  OK ({elapsed:.2f}s)", flush=True)
                else:
                    fail_count += 1
                    print(f"  RESPONSE success=false ({elapsed:.2f}s)", flush=True)
            except urllib.error.HTTPError as e:
                fail_count += 1
                elapsed = time.time() - t0
                body = e.read().decode("utf-8", errors="replace")
                f.write("\n" + "=" * 100 + "\n")
                f.write(f"TEST {case['id']:02d}: {case['name']}\n")
                f.write("HTTP ERROR\n")
                f.write(f"status: {e.code}\n")
                f.write(f"body: {body}\n")
                print(f"  HTTP ERROR {e.code} ({elapsed:.2f}s)", flush=True)
            except Exception:
                fail_count += 1
                elapsed = time.time() - t0
                err = traceback.format_exc()
                f.write("\n" + "=" * 100 + "\n")
                f.write(f"TEST {case['id']:02d}: {case['name']}\n")
                f.write("PYTHON ERROR\n")
                f.write(err + "\n")
                print(f"  ERROR ({elapsed:.2f}s)", flush=True)

        finished = datetime.now()
        f.write("\n" + "=" * 100 + "\n")
        f.write("FINAL SUMMARY\n")
        f.write("=" * 100 + "\n")
        f.write(f"Finished: {finished.isoformat(timespec='seconds')}\n")
        f.write(f"Total tests: {len(TEST_CASES)}\n")
        f.write(f"Backend success responses: {pass_count}\n")
        f.write(f"Failed requests/responses: {fail_count}\n")

    print("\nDONE")
    print(f"Results written to: {output_path}")
    print(f"Backend success responses: {pass_count}/{len(TEST_CASES)}")
    if fail_count:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
