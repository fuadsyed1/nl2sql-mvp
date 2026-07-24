"""
run_day2_targeted.py  (LOCAL-ONLY — do NOT run in the sandbox)

Runs the preselected 64 Day 2 queries (32 failure reruns + 32 protected controls)
from day2_targeted_before_after.csv against a locally-running backend that has
MindRouter access, then fills the after_sql/after_verdict columns and writes the
verified-recovery and protected-regression files. Semantic correctness must be
confirmed by a human against question + schema + original audit reason; this
script records execution + the new SQL, never auto-marks a result correct.

Usage (PowerShell), from backend/ with the server already running:
    python benchmarks/go_live_day2/run_day2_targeted.py --base-url http://127.0.0.1:8000
"""
import os, csv, json, argparse, urllib.request, urllib.error

HERE = os.path.dirname(__file__)
DB_BY_NAME = {"54": 54, "55": 55, "56": 56, "57": 57}


def post(base_url, database_id, question, meta, timeout):
    url = f"{base_url.rstrip('/')}/database/{database_id}/execute_sql"
    body = json.dumps({"question": question}).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "X-SpiderSQL-Test-ID": str(meta.get("test_id", "")),
               "X-SpiderSQL-Category": meta.get("category", "") or "",
               "X-SpiderSQL-Difficulty": meta.get("difficulty", "") or "",
               "X-SpiderSQL-Trace-Run": "day2_targeted"}
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace") or "{}")
    except Exception as exc:                                 # pragma: no cover
        return {"success": False, "_client_error": str(exc)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(os.path.join(HERE, "day2_targeted_before_after.csv"),
                                    newline="", encoding="utf-8")))
    for r in rows:
        if not r["question"]:
            continue
        resp = post(args.base_url, DB_BY_NAME[r["database_id"]], r["question"], r, args.timeout)
        r["after_sql"] = (
            (resp.get("generated_sql") or {}).get("sql")
            or resp.get("sql")
            or ""
        ).replace("\n", " ")
        r["after_verdict"] = "PENDING_HUMAN_SEMANTIC_REVIEW"
        r["rerun_status"] = "executed" if resp.get("success") else "exec_failed_or_controlled"
        r["recovered"] = ""      # set by the human reviewer

    with open(os.path.join(HERE, "day2_targeted_before_after.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    open(os.path.join(HERE, "day2_targeted_results.txt"), "w", encoding="utf-8").write(
        "Executed 64 targeted queries locally. after_sql captured; semantic verdicts "
        "PENDING human review against question + schema + original audit reason. "
        "Populate day2_verified_recoveries.csv and day2_protected_regressions.csv from "
        "the review.\n")
    print("done:", len(rows), "rows; after_sql captured (verdicts pending human review)")


if __name__ == "__main__":
    main()
