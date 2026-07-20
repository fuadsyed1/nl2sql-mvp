#!/usr/bin/env python3
"""
RC5 LIVE end-to-end API smoke test.

Runs the 26 recovered queries through the REAL production path via
POST /database/{id}/execute_sql (candidate generation -> checklist/contract ->
scoring -> production select_best -> execution). It does NOT call select_best
directly, does NOT inject captured candidates, does NOT use offline data, and
adds NO LLM call of its own. Run it where MindRouter is reachable:

    SPIDERSQL_URL=http://127.0.0.1:8000 NORTHSTAR_DB_ID=53 \\
        python3 benchmarks/rc5_live_smoke_test.py

Semantic correctness is NOT auto-claimed from candidate labels: a live generator
may emit different SQL under the same source label. Each case is recorded with
semantic_correct=null and semantic_review_status="pending_manual_sql_review";
the selected SQL must be reviewed one by one against the audited semantics.

Artifacts (timestamped) are written to benchmarks/results/:
  * rc5_live_smoke_<ts>.json  - complete raw API response per query + parsed view
  * rc5_live_smoke_<ts>.txt   - readable per-query report

Exit code is nonzero if any query has an HTTP, application, or SQL-execution
failure.
"""
import os
import sys
import json
import time
import datetime

try:
    import requests
except Exception:                      # pragma: no cover
    print("ERROR: this harness requires the 'requests' package.", file=sys.stderr)
    sys.exit(2)

BASE_URL = os.environ.get("SPIDERSQL_URL", "http://127.0.0.1:8000").rstrip("/")
DB_ID = int(os.environ.get("NORTHSTAR_DB_ID", "53"))
TIMEOUT = int(os.environ.get("SPIDERSQL_TIMEOUT", "180"))
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

CASES = [
 {
  "test_id": "128",
  "bucket": "RC1_RC2",
  "question": "How many distinct suppliers have products with a sale price above 500?",
  "audited_correct_labels": [
   "llm_sql_direct",
   "llm_sql_direct_grain",
   "llm_sql_direct_variant",
   "llm_sql_repair"
  ],
  "audited_correct_reference": "see audit_note",
  "audit_note": "DISTINCT applies to the single COUNT result, not supplier IDs; it counts qualifying product rows rather than distinct suppliers."
 },
 {
  "test_id": "129",
  "bucket": "RC1_RC2",
  "question": "How many distinct warehouses currently store discontinued products?",
  "audited_correct_labels": [
   "llm_sql_direct",
   "llm_sql_direct_grain",
   "llm_sql_direct_variant",
   "llm_sql_repair"
  ],
  "audited_correct_reference": "see audit_note",
  "audit_note": "DISTINCT applies to the single COUNT result, so inventory rows are counted instead of distinct warehouses."
 },
 {
  "test_id": "133",
  "bucket": "RC1_RC2",
  "question": "How many distinct sales representatives handled orders from enterprise customers?",
  "audited_correct_labels": [
   "llm_sql_direct",
   "llm_sql_direct_grain",
   "llm_sql_direct_variant",
   "llm_sql_repair"
  ],
  "audited_correct_reference": "see audit_note",
  "audit_note": "DISTINCT applies to the aggregate result, so order rows are counted rather than distinct sales representatives."
 },
 {
  "test_id": "142",
  "bucket": "RC1_RC2",
  "question": "How many distinct products are both low in stock and supplied by a high-risk supplier?",
  "audited_correct_labels": [
   "llm_sql_direct",
   "llm_sql_direct_grain",
   "llm_sql_direct_variant"
  ],
  "audited_correct_reference": "see audit_note",
  "audit_note": "Does not join inventory or test low-stock status and does not return one scalar distinct-product count."
 },
 {
  "test_id": "144",
  "bucket": "RC1_RC2",
  "question": "How many distinct carriers delivered orders containing Electronics products?",
  "audited_correct_labels": [
   "llm_sql_direct",
   "llm_sql_direct_variant"
  ],
  "audited_correct_reference": "see audit_note",
  "audit_note": "Selects a carrier with COUNT(*) without grouping or COUNT(DISTINCT carrier), producing an arbitrary carrier and a row count."
 },
 {
  "test_id": "466",
  "bucket": "RC1_RC2",
  "question": "List products priced above the average sale price for their category.",
  "audited_correct_labels": [
   "llm_sql_direct",
   "llm_sql_direct_grain",
   "llm_sql_direct_variant"
  ],
  "audited_correct_reference": "see audit_note",
  "audit_note": "Groups by category and selects one arbitrary product per category, rather than comparing every product with its category average."
 },
 {
  "test_id": "467",
  "bucket": "RC1_RC2",
  "question": "List employees earning more than the average salary in their department.",
  "audited_correct_labels": [
   "llm_sql_direct",
   "llm_sql_direct_grain",
   "llm_sql_direct_variant",
   "llm_sql_repair"
  ],
  "audited_correct_reference": "see audit_note",
  "audit_note": "Groups by department and selects one arbitrary employee per department, rather than comparing every employee with the department average."
 },
 {
  "test_id": "473",
  "bucket": "RC1_RC2",
  "question": "List shipments whose shipping cost is above the average cost for the same carrier.",
  "audited_correct_labels": [
   "llm_sql_direct",
   "llm_sql_direct_grain",
   "llm_sql_direct_variant"
  ],
  "audited_correct_reference": "see audit_note",
  "audit_note": "Groups by carrier and selects one arbitrary shipment per carrier, rather than comparing every shipment with its carrier average."
 },
 {
  "test_id": "153",
  "bucket": "RC3",
  "question": "Count addresses by state.",
  "audited_correct_labels": [
   "llm_primary",
   "llm_sql_direct_grain"
  ],
  "audited_correct_reference": "see audit_note",
  "audit_note": "Groups addresses by state but omits the count."
 },
 {
  "test_id": "156",
  "bucket": "RC3",
  "question": "Count products by category.",
  "audited_correct_labels": [
   "llm_primary",
   "llm_sql_direct_grain"
  ],
  "audited_correct_reference": "see audit_note",
  "audit_note": "Groups products by category but omits the product count."
 },
 {
  "test_id": "343",
  "bucket": "RC3",
  "question": "List products supplied by rating-1 suppliers that generated delivered-order revenue in 2025, with revenue by warehouse.",
  "audited_correct_labels": [
   "llm_sql_direct_grain"
  ],
  "audited_correct_reference": "see audit_note",
  "audit_note": "Correctly filters and groups qualifying rows, but the requested revenue-by-warehouse value is not selected."
 },
 {
  "test_id": "392",
  "bucket": "RC3",
  "question": "Show the top 5 customer cities by average delivered-order value, considering only cities with at least 5 delivered orders.",
  "audited_correct_labels": [
   "llm_primary"
  ],
  "audited_correct_reference": "see audit_note",
  "audit_note": "Uses every address belonging to a customer rather than the order's relevant address, which can duplicate orders and assign revenue to the wrong city."
 },
 {
  "test_id": "68",
  "bucket": "RC4",
  "question": "Calculate the refund rate for each payment method using refunded amount divided by payment amount.",
  "audited_correct_labels": [
   "llm_sql_direct",
   "llm_sql_direct_grain",
   "llm_sql_direct_variant"
  ],
  "audited_correct_reference": "see audit_note",
  "audit_note": "Does not calculate refunded_amount / payment_amount. It returns payment methods whose refunded total is above the global average."
 },
 {
  "test_id": "73",
  "bucket": "RC4",
  "question": "Calculate the employee salary cost per current department headcount for each department.",
  "audited_correct_labels": [
   "llm_sql_direct",
   "llm_sql_direct_variant"
  ],
  "audited_correct_reference": "see audit_note",
  "audit_note": "Returns total salary and an employee count but never divides salary cost by the department's current headcount; it also adds an unrequested active-employee filter."
 },
 {
  "test_id": "81",
  "bucket": "RC4",
  "question": "Calculate the percentage of shipments delivered on or before their estimated delivery date for each carrier.",
  "audited_correct_labels": [
   "llm_sql_direct",
   "llm_sql_direct_grain",
   "llm_sql_direct_variant"
  ],
  "audited_correct_reference": "see audit_note",
  "audit_note": "Calculates an on-time percentage but incorrectly filters out carriers whose shipment count is not above the average carrier count."
 },
 {
  "test_id": "98",
  "bucket": "RC4",
  "question": "For each department, calculate average employee performance rating per ten thousand dollars of average salary.",
  "audited_correct_labels": [
   "llm_sql_direct",
   "llm_sql_direct_grain",
   "llm_sql_direct_variant"
  ],
  "audited_correct_reference": "see audit_note",
  "audit_note": "Computes department metrics internally but returns only departments above an unrelated global benchmark, omitting the requested per-department metric."
 },
 {
  "test_id": "137",
  "bucket": "RC4",
  "question": "How many distinct products were sold through both online and store channels?",
  "audited_correct_labels": [
   "llm_sql_direct_variant"
  ],
  "audited_correct_reference": "see audit_note",
  "audit_note": "Requires sales_channel to equal two different values in the same row and returns grouped product rows instead of one distinct-product count."
 },
 {
  "test_id": "242",
  "bucket": "RC4",
  "question": "List customer segments whose refund rate is above 5 percent.",
  "audited_correct_labels": [
   "llm_sql_direct",
   "llm_sql_direct_grain",
   "llm_sql_direct_variant",
   "llm_sql_repair"
  ],
  "audited_correct_reference": "see audit_note",
  "audit_note": "Tests total_refunded > total_paid, effectively a rate above 100%, rather than a refund rate above 5%."
 },
 {
  "test_id": "401",
  "bucket": "RC4",
  "question": "List cities that appear either in customer addresses or in warehouse locations.",
  "audited_correct_labels": [
   "llm_sql_direct",
   "llm_sql_direct_grain",
   "llm_sql_direct_variant",
   "llm_sql_repair"
  ],
  "audited_correct_reference": "see audit_note",
  "audit_note": "Returns address-city/warehouse-city pairs linked through shipments, not a single union of all cities from both sources."
 },
 {
  "test_id": "447",
  "bucket": "RC4",
  "question": "List customers who had both refunded and settled payments but no failed payments.",
  "audited_correct_labels": [
   "llm_sql_direct",
   "llm_sql_direct_grain",
   "llm_sql_direct_variant",
   "llm_sql_repair"
  ],
  "audited_correct_reference": "see audit_note",
  "audit_note": "All three counts are COUNT(*), so refunded, settled, and failed counts are identical and do not test payment statuses."
 },
 {
  "test_id": "146",
  "bucket": "RC5",
  "question": "How many distinct suppliers had products stored in at least three different warehouses?",
  "audited_correct_labels": [
   "llm_sql_direct"
  ],
  "audited_correct_reference": "scalar COUNT(*) FROM (...) not a supplier list",
  "audit_note": "Returns one row per supplier with a warehouse count instead of the requested number of distinct suppliers."
 },
 {
  "test_id": "286",
  "bucket": "RC5",
  "question": "List customers whose primary address city matches the city of an open warehouse.",
  "audited_correct_labels": [
   "llm_sql_direct",
   "llm_sql_direct_grain",
   "llm_sql_direct_variant"
  ],
  "audited_correct_reference": "per-entity comparison not LIMIT 1",
  "audit_note": "Compares each primary-address city with only one arbitrary open-warehouse city because of LIMIT 1."
 },
 {
  "test_id": "289",
  "bucket": "RC5",
  "question": "List products whose supplier state matches the state of a warehouse storing that product.",
  "audited_correct_labels": [
   "llm_variant_2",
   "llm_sql_direct",
   "llm_sql_direct_grain",
   "llm_sql_direct_variant"
  ],
  "audited_correct_reference": "WHERE supplier.state_code = warehouse.state_code",
  "audit_note": "Joins supplier and warehouse states but never filters for equality."
 },
 {
  "test_id": "317",
  "bucket": "RC5",
  "question": "List Gold customers with their delivered order numbers and payment amounts.",
  "audited_correct_labels": [
   "llm_sql_direct"
  ],
  "audited_correct_reference": "payment joined via order_id (not customer_id)",
  "audit_note": "Joins payments to the customer rather than to the specific delivered order, pairing unrelated payments with orders."
 },
 {
  "test_id": "336",
  "bucket": "RC5",
  "question": "List customers who placed delivered online orders for Electronics products, with order number, product, payment amount, and carrier.",
  "audited_correct_labels": [
   "llm_sql_direct_variant"
  ],
  "audited_correct_reference": "payment joined via order_id (not customer_id)",
  "audit_note": "Joins payments through customer_id instead of order_id, attaching unrelated payments to delivered online orders."
 },
 {
  "test_id": "437",
  "bucket": "RC5",
  "question": "List products sold to both Gold and Platinum customers but not to Bronze customers.",
  "audited_correct_labels": [
   "llm_sql_direct_variant",
   "llm_sql_direct",
   "llm_sql_direct_grain"
  ],
  "audited_correct_reference": "Gold AND Platinum (INTERSECT) AND NOT Bronze",
  "audit_note": "Only excludes Bronze customers; it never requires that the product was sold to both Gold and Platinum customers."
 }
]

# ---------------------------------------------------------------------------
# response parsing - real /execute_sql structure only
# ---------------------------------------------------------------------------
def extract_sql(data):
    """Final SQL from the real response path: generated_sql.sql, with a safe
    fallback to a top-level `sql` field only if it exists."""
    gs = data.get("generated_sql")
    if isinstance(gs, dict) and gs.get("sql") is not None:
        return gs.get("sql")
    if "sql" in data:
        return data.get("sql")
    return None


def extract_execution(data):
    """Read the actual `execution` object (never conflate with app success)."""
    ex = data.get("execution") or {}
    rows = ex.get("rows")
    sig = None
    if isinstance(rows, list):
        try:
            norm = tuple(sorted(tuple(str(v) for v in r) for r in rows))
            sig = [len(ex.get("columns") or []), len(rows), hash(norm)]
        except Exception:
            sig = None
    return {
        "executed": ex.get("executed"),
        "row_count": ex.get("row_count"),
        "reason": ex.get("reason"),
        "error": ex.get("error"),
        "columns": ex.get("columns"),
        "truncated": ex.get("truncated"),
        "result_signature": sig,
        "rows_present": isinstance(rows, list) and len(rows) > 0,
    }


def merge_candidates(data):
    """Full per-candidate detail: label/source/score/executed/row_count/fatal/
    fatal_reasons (from candidate_scores) + SQL + reasons/warnings (from
    rejected_candidates; the selected candidate's SQL comes from generated_sql).
    Eligibility is derived from semantic_incomplete + fatal/executed."""
    scores = {c.get("label"): c for c in (data.get("candidate_scores") or [])}
    rejected = {c.get("label"): c for c in (data.get("rejected_candidates") or [])}
    incomplete = {x.get("label"): x.get("missing")
                  for x in (data.get("semantic_incomplete") or [])}
    sel_label = data.get("selected_candidate_label")
    sel_sql = extract_sql(data)
    out = []
    for label, s in scores.items():
        sql = None
        if label == sel_label:
            sql = sel_sql
        elif label in rejected:
            sql = rejected[label].get("sql")
        fatal = bool(s.get("fatal"))
        if fatal:
            elig = "fatal"
        elif label in incomplete:
            elig = "incomplete"
        elif s.get("executed"):
            elig = "eligible"
        else:
            elig = "not_executed"
        out.append({
            "label": label,
            "source": s.get("source"),
            "sql": sql,
            "score": s.get("score"),
            "executed": s.get("executed"),
            "row_count": s.get("row_count"),
            "fatal": fatal,
            "fatal_reasons": s.get("fatal_reasons") or [],
            "warnings": (rejected.get(label, {}) or {}).get("reasons") or [],
            "eligibility": elig,
            "missing_obligations": incomplete.get(label),
        })
    return out


def rc3_trace(data):
    return {
        "semantic_eligible_count": data.get("semantic_eligible_count"),
        "semantic_incomplete": data.get("semantic_incomplete"),
        "consensus_group_size": data.get("consensus_group_size"),
        "consensus_sources": data.get("consensus_sources"),
    }


def rc4_trace(data):
    return {
        "override_trace": data.get("override_trace"),
        "direct_override_trace": data.get("direct_override_trace"),
        "override_blocked": data.get("override_blocked"),
        "override_block_reason": data.get("override_block_reason"),
    }


def classify(http_ok, data, execinfo):
    if not http_ok:
        return "request_failed"
    if not data.get("success"):
        return "application_failed"
    if not execinfo.get("executed"):
        return "execution_failed"
    return "executed_pending_semantic_review"


def run_one(case):
    url = "%s/database/%d/execute_sql" % (BASE_URL, DB_ID)
    rec = {"test_id": case["test_id"], "bucket": case["bucket"],
           "question": case["question"],
           "audited_correct_labels": case["audited_correct_labels"],
           "audited_correct_reference": case["audited_correct_reference"],
           "audit_note": case["audit_note"],
           "semantic_correct": None,
           "semantic_review_status": "pending_manual_sql_review"}
    try:
        r = requests.post(url, json={"question": case["question"]},
                          headers={"x-spidersql-test-id": case["test_id"]},
                          timeout=TIMEOUT)
        rec["http_status"] = r.status_code
        http_ok = r.status_code == 200
        try:
            data = r.json()
        except Exception:
            data = {"_non_json_body": r.text[:2000]}
    except Exception as e:
        rec["http_status"] = None
        rec["transport_error"] = repr(e)
        rec["outcome"] = "request_failed"
        rec["raw_response"] = None
        return rec

    execinfo = extract_execution(data)
    cands = merge_candidates(data)
    generated_labels = [c["label"] for c in cands]
    rec.update({
        "raw_response": data,                       # complete raw API response
        "application_success": bool(data.get("success")),
        "execution": execinfo,
        "selected_label": data.get("selected_candidate_label"),
        "selected_source": data.get("selected_candidate_source"),
        "selected_sql": extract_sql(data),
        "selection_reason": data.get("selection_reason"),
        "generated_candidates": cands,
        "rc3_trace": rc3_trace(data),
        "rc4_trace": rc4_trace(data),
        "rc5_trace": data.get("rc5_trace"),
        # whether a candidate under an audited-correct SOURCE label was generated
        # (this is NOT semantic correctness - the live SQL may differ):
        "audited_source_generated": bool(
            set(case["audited_correct_labels"]) & set(generated_labels)),
        "outcome": classify(http_ok, data, execinfo),
    })
    return rec


def write_txt(path, records):
    L = []
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    L.append("RC5 LIVE end-to-end API smoke test  (%s)" % ts)
    L.append("endpoint: %s/database/%d/execute_sql" % (BASE_URL, DB_ID))
    L.append("=" * 78)
    for r in records:
        L.append("")
        L.append("[%s] bucket=%s  outcome=%s" % (r["test_id"], r["bucket"], r.get("outcome")))
        L.append("  question              : %s" % r["question"])
        L.append("  http_status           : %s" % r.get("http_status"))
        L.append("  application_success   : %s" % r.get("application_success"))
        ex = r.get("execution") or {}
        L.append("  execution.executed    : %s   row_count=%s" % (ex.get("executed"), ex.get("row_count")))
        L.append("  execution.error       : %s" % ex.get("error"))
        L.append("  result_signature      : %s" % ex.get("result_signature"))
        L.append("  generated candidates  :")
        for c in r.get("generated_candidates") or []:
            L.append("     - %-24s src=%-20s score=%-5s elig=%-11s fatal=%s"
                     % (c["label"], c["source"], c["score"], c["eligibility"], c["fatal"]))
            if c["fatal_reasons"]:
                L.append("         fatal_reasons: %s" % c["fatal_reasons"])
            if c["warnings"]:
                L.append("         warnings: %s" % c["warnings"])
            L.append("         sql: %s" % ((c["sql"] or "")[:220]))
        L.append("  selected_label        : %s (source=%s)" % (r.get("selected_label"), r.get("selected_source")))
        L.append("  selection_reason      : %s" % r.get("selection_reason"))
        L.append("  selected_sql          : %s" % ((r.get("selected_sql") or "")[:300]))
        L.append("  RC3 trace             : %s" % r.get("rc3_trace"))
        L.append("  RC4 override trace    : %s" % r.get("rc4_trace"))
        L.append("  RC5 trace             : %s" % r.get("rc5_trace"))
        L.append("  audited_source_generated : %s  (NOT correctness)" % r.get("audited_source_generated"))
        L.append("  audited_correct_ref   : %s" % r.get("audited_correct_reference"))
        L.append("  audit_note            : %s" % r.get("audit_note"))
        L.append("  semantic_correct      : %s" % r.get("semantic_correct"))
        L.append("  semantic_review_status: %s" % r.get("semantic_review_status"))
        L.append("  >> REVIEW the selected_sql above against the audited semantics.")
    open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    records = [run_one(c) for c in CASES]
    for c in CASES:
        time.sleep(0)  # no-op; POSTs already done sequentially in run_one order
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    jpath = os.path.join(RESULTS_DIR, "rc5_live_smoke_%s.json" % ts)
    tpath = os.path.join(RESULTS_DIR, "rc5_live_smoke_%s.txt" % ts)
    json.dump({"base_url": BASE_URL, "db_id": DB_ID, "timestamp": ts,
               "cases": records}, open(jpath, "w"), indent=1, default=str)
    write_txt(tpath, records)

    n = len(records)
    http_ok = sum(1 for r in records if r.get("http_status") == 200)
    app_ok = sum(1 for r in records if r.get("application_success"))
    exec_ok = sum(1 for r in records if (r.get("execution") or {}).get("executed"))
    rc3 = sum(1 for r in records if (r.get("rc3_trace") or {}).get("semantic_eligible_count") is not None)
    rc4 = sum(1 for r in records if (r.get("rc4_trace") or {}).get("override_trace"))
    rc5 = sum(1 for r in records if r.get("rc5_trace"))
    aud = sum(1 for r in records if r.get("audited_source_generated"))
    pending = sum(1 for r in records if r.get("semantic_review_status") == "pending_manual_sql_review")
    failures = [r["test_id"] for r in records
                if r.get("outcome") in ("request_failed", "application_failed", "execution_failed")]

    print("\n" + "=" * 78)
    print("RC5 LIVE SMOKE SUMMARY  (semantic correctness NOT auto-claimed)")
    print("  HTTP 200 responses            : %d/%d" % (http_ok, n))
    print("  Application successes         : %d/%d" % (app_ok, n))
    print("  SQL executions (execution.executed): %d/%d" % (exec_ok, n))
    print("  Cases with RC3 trace          : %d/%d" % (rc3, n))
    print("  Cases with RC4 override trace : %d/%d" % (rc4, n))
    print("  Cases with RC5 trace          : %d/%d" % (rc5, n))
    print("  Cases where audited source appeared (NOT correctness): %d/%d" % (aud, n))
    print("  Cases pending manual semantic review : %d/%d" % (pending, n))
    print("  Artifacts:\n    %s\n    %s" % (jpath, tpath))
    if failures:
        print("  FAILURES (transport/app/execution): %s" % failures)
    print("=" * 78)
    print("NOTE: correctness is determined by reviewing each selected_sql; this "
          "harness does not print '26/26 correct'. A case where the live LLM did "
          "not generate the audited-correct candidate is a GENERATION difference, "
          "not a selector regression.")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
