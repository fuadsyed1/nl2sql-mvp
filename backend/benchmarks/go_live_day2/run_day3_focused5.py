"""
run_day3_focused5.py  (LOCAL-ONLY — do NOT run in the sandbox)

Focused live re-run of ONLY the five Day-3 target queries against a locally
running backend that has LLM (Ollama/MindRouter) access. Captures the selected
SQL from generated_sql.sql for each and writes day3_focused5_results.json.
Semantic correctness is confirmed by a human against question + schema; this
script never auto-marks a result correct.

Usage (PowerShell), from backend/ with the full-trace server already running:
    python benchmarks/go_live_day2/run_day3_focused5.py --base-url http://127.0.0.1:8000
"""
import argparse
import json
import os
import urllib.request

HERE = os.path.dirname(__file__)

# (database_id, test_id, question) — the five Day-3 targets.
QUERIES = [
    (56, 51, "Show each department with the number of unused beds based on bed "
             "capacity minus current occupancy."),
    (55, 142, "How many distinct programs have students advised by instructors "
              "from the same department as the program?"),
    (56, 401, "List doctor identifiers that appear either as primary doctors or "
              "appointment doctors."),
    (56, 403, "List patient identifiers that appear either in appointments or "
              "billing claims."),
    (56, 96, "For each patient, calculate abnormal lab tests as a percentage of "
             "completed lab tests."),
]


def post(base_url, database_id, question, test_id, timeout):
    url = f"{base_url.rstrip('/')}/database/{database_id}/execute_sql"
    body = json.dumps({"question": question}).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "X-SpiderSQL-Test-ID": str(test_id),
               "X-SpiderSQL-Trace-Run": "day3_focused5"}
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace") or "{}")
    except Exception as exc:                                   # pragma: no cover
        return {"success": False, "_client_error": str(exc)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()

    out = []
    for db, tid, q in QUERIES:
        resp = post(args.base_url, db, q, tid, args.timeout)
        after_sql = ((resp.get("generated_sql") or {}).get("sql")
                     or resp.get("sql") or "").replace("\n", " ")
        out.append({
            "database_id": db, "test_id": tid, "question": q,
            "after_sql": after_sql,
            "execution_success": bool(resp.get("success")),
            "endpoint_error": resp.get("error"),
            "selected_candidate_label": resp.get("selected_candidate_label"),
            "selected_candidate_score": resp.get("selected_candidate_score"),
            "selection_reason": resp.get("selection_reason"),
            "verdict": "PENDING_HUMAN_SEMANTIC_REVIEW",
        })
        print(f"DB{db} t{tid}: success={resp.get('success')} "
              f"label={resp.get('selected_candidate_label')} "
              f"reason={resp.get('selection_reason')}")

    path = os.path.join(HERE, "day3_focused5_results.json")
    json.dump({"note": "Day-3 focused 5-query live re-run; after_sql captured; "
                       "verdicts PENDING human semantic review.",
               "results": out}, open(path, "w"), indent=1)
    print("wrote", path)


if __name__ == "__main__":
    main()
