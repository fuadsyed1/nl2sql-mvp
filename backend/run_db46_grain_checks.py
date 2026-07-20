#!/usr/bin/env python3
"""
Stage 1 manual grain checks — DB46 clinic benchmark Q02 / Q04 / Q13 / Q40 / Q48.

Start the FastAPI backend first (with Ollama/MindRouter reachable), then:

    cd C:\\Projects\\nl2sql-mvp\\backend
    python run_db46_grain_checks.py

For each question the report contains: the typed grain contract, every
generated candidate (source, score, fatal reasons, grain-validator output),
the selected candidate, whether the request was accepted / repaired /
controlled-failed, the final SQL, and a semantic-verdict placeholder for
manual review. Output: db46_grain_checks_results.txt (+ .json).
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "http://127.0.0.1:8000"
DATABASE_ID = 46
TIMEOUT_SECONDS = 300
# optional CLI arg = output basename, e.g.
#   python run_db46_grain_checks.py db46_final_stabilization_run1
_BASENAME = (sys.argv[1] if len(sys.argv) > 1
             else "db46_grain_checks_results")
OUT_TXT = Path(f"{_BASENAME}.txt")
OUT_JSON = Path(f"{_BASENAME}.json")

QUESTIONS = {
    "Q02": "Find patients who were seen by doctors from more than one "
           "specialty and whose total invoiced amount is above the average "
           "total for patients with the same insurance provider.",
    "Q04": "Find patients whose unpaid or partially paid balance is higher "
           "than the average outstanding balance for patients with the same "
           "insurance provider.",
    "Q13": "Find patients whose most recent appointment was completed and "
           "whose lifetime invoiced amount is above the average for patients "
           "with the same insurance provider.",
    "Q40": "Find lab results whose value is above the average for the same "
           "test and whose patient has spent more than the average patient.",
    "Q48": "Find patients with abnormal results in more than one type of lab "
           "test and an outstanding balance above the average patient "
           "outstanding balance.",
}


def post_query(question: str) -> dict:
    url = f"{BASE_URL}/database/{DATABASE_ID}/execute_sql"
    payload = json.dumps({"question": question}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"},
        method="POST")
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        data = {"success": False,
                "_error": exc.read().decode("utf-8", errors="replace")}
    except Exception as exc:
        data = {"success": False, "_error": repr(exc)}
    data["_elapsed_seconds"] = round(time.time() - started, 2)
    return data


def extract_sql(response: dict) -> str:
    generated = response.get("generated_sql")
    if isinstance(generated, dict) and isinstance(generated.get("sql"), str):
        return generated["sql"].strip()
    if isinstance(generated, str):
        return generated.strip()
    for key in ("selected_sql", "sql"):
        if isinstance(response.get(key), str):
            return response[key].strip()
    return ""


def outcome_of(response: dict) -> str:
    if response.get("error") == "no_semantically_valid_sql":
        return "CONTROLLED FAILURE (no_semantically_valid_sql)"
    if response.get("repair_selected"):
        return "REPAIRED (llm_sql_repair candidate selected)"
    if response.get("success"):
        return "ACCEPTED"
    return "FAILED (see error)"


def fmt(qid: str, question: str, r: dict) -> str:
    sql = extract_sql(r)
    grain = ((r.get("selected_candidate_validation") or {})
             .get("grain_contract"))
    lines = [
        "=" * 100,
        f"{qid}: {question}",
        f"ELAPSED: {r.get('_elapsed_seconds')}s   "
        f"SUCCESS: {bool(r.get('success'))}   OUTCOME: {outcome_of(r)}",
        "",
        "TYPED CONTRACT:",
        json.dumps(r.get("semantic_contract"), indent=2, default=str),
        "",
        "CANDIDATES (source / score / executed / fatal):",
    ]
    for c in r.get("candidate_scores") or []:
        lines.append(f"  - {c.get('label'):26s} score={c.get('score')} "
                     f"executed={c.get('executed')} fatal={c.get('fatal')}")
        for fr in c.get("fatal_reasons") or []:
            lines.append(f"      FATAL: {fr}")
    lines += [
        "",
        f"SELECTED: {r.get('selected_candidate_label')} "
        f"({r.get('selection_reason')}), "
        f"score={r.get('selected_candidate_score')}",
        "",
        "GRAIN VALIDATOR OUTPUT (selected candidate):",
        json.dumps(grain, indent=2, default=str),
        "",
        "SQL:",
        sql or "-- NO SQL RETURNED",
        "",
        f"ROW COUNT: {(r.get('execution') or {}).get('row_count')}",
        f"WARNINGS: {r.get('warnings')}",
        f"ERROR: {r.get('error') or r.get('_error') or ''}",
        "",
        "SEMANTIC VERDICT: (fill in manually: correct grain / wrong grain "
        "correctly blocked / wrong grain NOT blocked / other)",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    OUT_TXT.write_text("DB46 grain checks — semantic-contract Stage 1\n\n",
                       encoding="utf-8")
    all_results = {}
    for qid, question in QUESTIONS.items():
        print(f"{qid} ...", flush=True)
        r = post_query(question)
        all_results[qid] = r
        print(f"{qid}: {outcome_of(r)}  ({r.get('_elapsed_seconds')}s)",
              flush=True)
        with OUT_TXT.open("a", encoding="utf-8") as f:
            f.write(fmt(qid, question, r) + "\n")
    OUT_JSON.write_text(json.dumps(all_results, indent=2, default=str),
                        encoding="utf-8")
    print(f"Saved: {OUT_TXT} and {OUT_JSON}")


if __name__ == "__main__":
    main()
