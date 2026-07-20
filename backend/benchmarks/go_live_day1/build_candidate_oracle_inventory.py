"""
build_candidate_oracle_inventory.py
    -> candidate_oracle_audit.csv
     + candidate_oracle_manual_review.csv
     + candidate_oracle_summary.json

One row per CANDIDATE of every semantically-failed query. The selected candidate
is identified with the robust multi-signal matcher (selected_candidate_number,
selected SQL text, exact then normalized source label) so suffixed labels like
'llm_variant_1' align with the 'llm_variant' candidate block -- every executed
semantic failure now has exactly one selected candidate.

Failure sources:
  * executed_semantically_wrong  (delivered SQL executed but audit = INCORRECT)
  * no_selected_sql              (controlled no-SQL failures; kept separate)

Query disposition for the executed-wrong failures is a HEURISTIC partition from
execution / fatal / SQL-difference signals (NOT a per-candidate semantic oracle,
which does not exist):
  * only_selected_candidate_available        - every candidate reproduced the delivered wrong SQL
  * plausible_clean_alternative_available  - a clean-executed alternative that DIFFERS from the
                                  delivered wrong SQL was available but not selected
  * no_clean_different_alternative      - a differing alternative existed but was dropped
                                  (fatal validation / execution failure)
  * unresolved_manual_review    - signals insufficient to bin automatically
The prioritized manual-review CSV lists exactly the plausible (clean, differing,
non-selected) candidates a human should verify; nothing is asserted correct.
"""
import csv, json, re
import day1_common as dc

AUDIT_COLUMNS = [
    "database_id", "test_id", "question", "semantic_verdict", "failure_source",
    "query_disposition", "candidate_number", "candidate_source",
    "execution_success", "execution_error", "row_count", "fatal_count", "score",
    "was_selected", "select_match_method", "selected_source",
    "differs_from_selected", "plausibly_correct", "semantic_oracle",
    "oracle_basis", "needs_manual_review", "extracted_sql", "trace_file",
]
REVIEW_COLUMNS = [
    "priority_rank", "database_id", "test_id", "query_disposition", "question",
    "candidate_number", "candidate_source", "score", "row_count",
    "execution_success", "fatal_count", "selected_source",
    "review_reason", "candidate_sql", "delivered_wrong_sql",
]
DISPOSITIONS = ["only_selected_candidate_available", "plausible_clean_alternative_available",
                "no_clean_different_alternative", "unresolved_manual_review"]


def _norm(q):
    return re.sub(r"\s+", " ", (q or "").strip()).lower()


def _is_no_sql(v):
    sql = (v.get("sql") or "").upper()
    return (v.get("execution_status") or "").upper() == "FAIL" \
        or "NO SQL GENERATED" in sql or not v.get("sql")


def _fatal(c):
    return (c.get("fatal_count") or 0) > 0


def classify_disposition(selected, nonsel):
    """Heuristic partition from execution/fatal/SQL-difference signals."""
    sel_sql = dc.normalize_sql(selected.get("sql")) if selected else None
    differing = [c for c in nonsel if c.get("sql")
                 and dc.normalize_sql(c["sql"]) != sel_sql]
    if not differing:
        return "only_selected_candidate_available", []
    plausible = [c for c in differing
                 if c.get("execution_success") is True and not _fatal(c)]
    if plausible:
        return "plausible_clean_alternative_available", plausible
    lost = [c for c in differing
            if c.get("execution_success") is False or _fatal(c)]
    if lost:
        return "no_clean_different_alternative", []
    return "unresolved_manual_review", []


def main():
    cfg = dc.load_config()
    ia = cfg["input_artifacts"]
    audit_rows, review_rows = [], []
    summary = {
        "failed_queries": 0,
        "executed_semantically_wrong": 0,
        "no_selected_sql": 0,
        "selected_candidate_coverage": {
            "executed_wrong_total": 0, "executed_wrong_with_selected": 0},
        "select_match_methods": {},
        "query_dispositions": {d: 0 for d in DISPOSITIONS},
        "no_selected_sql_bucket": {"count": 0, "test_ids_by_db": {}},
        "by_database": {},
        "candidate_rows": 0,
    }

    for db in ia["sql_result_files"]:
        info = ia["semantic_audit_files"].get(db)
        if not info:
            continue
        rrecs = dc.parse_result_file(dc.rp(ia["sql_result_files"][db]))
        audit = dc.parse_semantic_audit(dc.rp(info["path"]), info.get("format"))
        vmap = dc.build_verdict_map(audit, rrecs)
        trel = ia["sql_trace_files"].get(db)
        tfname = trel.split("/")[-1] if trel else ""
        trace_by_q = {}
        if trel and dc.file_meta(dc.rp(trel))["exists"]:
            for rec in dc.parse_trace_file(dc.rp(trel)):
                trace_by_q[_norm(rec["question"])] = rec

        for tid, v in sorted(vmap.items()):
            if v["semantic_verdict"] != "INCORRECT":
                continue
            summary["failed_queries"] += 1
            no_sql = _is_no_sql(v)
            src = "no_selected_sql" if no_sql else "executed_semantically_wrong"
            summary[src] += 1
            dbd = summary["by_database"].setdefault(
                db, {"executed_semantically_wrong": 0, "no_selected_sql": 0,
                     "candidate_rows": 0})
            dbd[src] += 1
            tr = trace_by_q.get(_norm(v["query"]))

            if no_sql:
                summary["no_selected_sql_bucket"]["count"] += 1
                summary["no_selected_sql_bucket"]["test_ids_by_db"].setdefault(
                    db, []).append(tid)
                selected, method = (None, "no_selected_sql")
                disposition = "no_selected_sql"
            else:
                summary["selected_candidate_coverage"]["executed_wrong_total"] += 1
                selected, method = dc.match_selected_candidate(tr) if tr else (None, "no_trace")
                summary["select_match_methods"][method] = \
                    summary["select_match_methods"].get(method, 0) + 1
                if selected is not None:
                    summary["selected_candidate_coverage"]["executed_wrong_with_selected"] += 1
                cands = tr["candidates"] if tr else []
                nonsel = [c for c in cands if c is not selected]
                disposition, plausible = classify_disposition(selected, nonsel)
                summary["query_dispositions"][disposition] += 1
                # manual-review rows: plausible non-selected candidates only
                for c in plausible:
                    review_rows.append({
                        "priority_rank": None, "database_id": int(db),
                        "test_id": tid, "query_disposition": disposition,
                        "question": v.get("query"),
                        "candidate_number": c["number"],
                        "candidate_source": c["source"], "score": c["score"],
                        "row_count": c["row_count"],
                        "execution_success": c["execution_success"],
                        "fatal_count": c["fatal_count"],
                        "selected_source": (selected or {}).get("source"),
                        "review_reason": "clean-executed alternative differing "
                                         "from delivered wrong SQL",
                        "candidate_sql": (c["sql"] or "").replace("\n", " ")[:400],
                        "delivered_wrong_sql":
                            ((selected or {}).get("sql") or "").replace("\n", " ")[:400],
                    })

            # emit audit rows for every candidate
            sel_sql_norm = dc.normalize_sql((selected or {}).get("sql")) if selected else None
            for c in (tr["candidates"] if tr else []):
                was_sel = (selected is not None and c is selected)
                differs = bool(c.get("sql")) and sel_sql_norm is not None \
                    and dc.normalize_sql(c["sql"]) != sel_sql_norm
                plaus = (not was_sel) and differs \
                    and c.get("execution_success") is True and not _fatal(c)
                if was_sel:
                    oracle, basis, needs = "incorrect", \
                        "audit verdict INCORRECT (delivered/selected SQL audited)", False
                else:
                    oracle, basis, needs = "needs_manual_review", \
                        "no per-candidate semantic label available", True
                audit_rows.append({
                    "database_id": int(db), "test_id": tid,
                    "question": v.get("query"), "semantic_verdict": "INCORRECT",
                    "failure_source": src, "query_disposition": disposition,
                    "candidate_number": c["number"], "candidate_source": c["source"],
                    "execution_success": c["execution_success"],
                    "execution_error": c["execution_error"],
                    "row_count": c["row_count"], "fatal_count": c["fatal_count"],
                    "score": c["score"], "was_selected": was_sel,
                    "select_match_method": method if was_sel else "",
                    "selected_source": (selected or {}).get("source"),
                    "differs_from_selected": differs, "plausibly_correct": plaus,
                    "semantic_oracle": oracle, "oracle_basis": basis,
                    "needs_manual_review": needs,
                    "extracted_sql": (c["sql"] or "").replace("\n", " ")[:300],
                    "trace_file": tfname,
                })
                dbd["candidate_rows"] += 1

    # collapse exact-duplicate plausible SQL within a query (distinct alternatives
    # only), keeping the highest-scoring representative, then prioritize globally.
    dedup = {}
    for r in review_rows:
        key = (r["database_id"], r["test_id"], dc.normalize_sql(r["candidate_sql"]))
        if key not in dedup or (r["score"] or 0) > (dedup[key]["score"] or 0):
            dedup[key] = r
    review_rows = list(dedup.values())
    review_rows.sort(key=lambda r: (-(r["score"] or 0), r["database_id"], r["test_id"]))
    for i, r in enumerate(review_rows, 1):
        r["priority_rank"] = i

    cov = summary["selected_candidate_coverage"]
    cov["coverage_pct"] = round(
        100.0 * cov["executed_wrong_with_selected"] / cov["executed_wrong_total"], 2) \
        if cov["executed_wrong_total"] else None
    summary["candidate_rows"] = len(audit_rows)
    summary["manual_review_rows"] = len(review_rows)
    summary["disposition_note"] = (
        "query_dispositions is a HEURISTIC partition of the executed-wrong "
        "failures from execution/fatal/SQL-difference signals, not a per-candidate "
        "semantic oracle. The manual-review CSV lists the plausible alternatives to "
        "confirm; correctness is never asserted automatically.")
    summary["generated_at"] = dc.now_iso()

    audit_rows.sort(key=lambda r: (r["database_id"], r["test_id"],
                                   r["candidate_number"] or 0))
    with open(dc.out("candidate_oracle_audit.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=AUDIT_COLUMNS); w.writeheader(); w.writerows(audit_rows)
    with open(dc.out("candidate_oracle_manual_review.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS); w.writeheader(); w.writerows(review_rows)
    with open(dc.out("candidate_oracle_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("wrote candidate_oracle_audit.csv rows:", len(audit_rows))
    print("  selected coverage:", cov["executed_wrong_with_selected"], "/",
          cov["executed_wrong_total"], f"({cov['coverage_pct']}%)",
          "| match methods:", summary["select_match_methods"])
    print("  no_selected_sql bucket:", summary["no_selected_sql_bucket"]["count"])
    print("  query_dispositions:", summary["query_dispositions"])
    print("  manual-review rows:", len(review_rows))


if __name__ == "__main__":
    main()
