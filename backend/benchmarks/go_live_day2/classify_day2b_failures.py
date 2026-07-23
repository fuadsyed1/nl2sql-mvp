"""
classify_day2b_failures.py  (Day 2B — offline, trace-verified classification)

LIMITATION / SUPERSEDED FOR THE LIVE RERUN:
  main() below classifies against the FROZEN Day 1 traces (dc.load_config()'s
  ia["sql_trace_files"]). Those pools do NOT contain the candidates the Day 2
  targeted live rerun actually generated, so its A/B/C verdicts diverge from the
  live evidence. The authoritative, Day-2-live-trace-verified classification is
  produced by build_day2b_live_classification.py (writes day2b_live_*), which
  reads benchmarks/results/day2_targeted_full_trace_db54..57.txt directly and
  applies manual per-candidate semantic judgement. The helper
  obligation_signals() added here is the classifier-only utility for recognising
  the derived-metric / set / output obligations that the live redo relies on
  (bare "per" ratios, "based on" formulas, totals implied by several named
  components, and paraphrased add/subtract/multiply/divide). It is pure and has
  no side effects; it does not change main()'s behaviour.

For each of the 21 remaining incorrect failure reruns, classify using the frozen
Day 1 full traces (captured candidate pools):
  * correct_candidate_generated_but_not_selected  (a clean, executed candidate
    that supplies the requested computation/structure the selected SQL lacks)
  * correct_candidate_generated_but_rejected       (such a candidate exists but
    was fatal / rejected)
  * no_correct_candidate_generated
A "fix candidate" is detected generically (schema-independent): it must (a)
differ from the wrong selected SQL, (b) supply the specific missing structure for
the failure pattern (a derived arithmetic expression / a set-or-anti-join
operator / a moved-or-added explicit predicate), and (c) not introduce a new
day2 violation. No test-id or DB-specific logic.
"""
import os, sys, csv, re
HERE = os.path.dirname(__file__)
BACKEND = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(BACKEND, "benchmarks", "go_live_day1"))
import day1_common as dc                                      # noqa
from sql_candidates import day2_semantic_rules as d2          # noqa
from sqlglot import exp

REVIEW = "/sessions/funny-nice-meitner/mnt/uploads/day2_targeted_before_after_reviewed.csv"


def _norm(q): return re.sub(r"\s+", " ", (q or "").strip()).lower()
def _nsql(s): return re.sub(r"\s+", " ", (s or "").strip().rstrip(";")).lower()


def _has_arith(sql):
    t = d2._parse(sql)
    return bool(t) and any(d2._has_arith_projection(s) for s in d2._selects(t))


def _set_ops(sql):
    t = d2._parse(sql)
    if not t:
        return set()
    ops = set()
    for cls, name in ((exp.Union, "UNION"), (exp.Intersect, "INTERSECT"),
                      (exp.Except, "EXCEPT")):
        if next(t.find_all(cls), None) is not None:
            ops.add(name)
    if any(isinstance(n, exp.Not) and next(n.find_all(exp.Exists), None)
           for n in t.find_all(exp.Not)):
        ops.add("NOT_EXISTS")
    if next(t.find_all(exp.Exists), None) is not None:
        ops.add("EXISTS")
    return ops


def _literals(sql):
    t = d2._parse(sql)
    if not t:
        return set()
    return {str(l.this).lower() for l in t.find_all(exp.Literal)}


def _fired(sql, q):
    return {f["rule"] for f in d2.evaluate_rules(sql, q)}


def is_fix_candidate(pattern, sel_sql, cand_sql, question):
    """Generic, pattern-aware: does the candidate supply the missing structure?"""
    if not cand_sql or _nsql(cand_sql) == _nsql(sel_sql):
        return False
    # never worse on day2 rules
    if _fired(cand_sql, question) - _fired(sel_sql, question):
        return False
    if pattern in ("aggregation_or_formula_error", "missing_metric_or_output"):
        dm = d2.derived_metric_obligation(question)
        if dm["calculate_expression"]:
            return _has_arith(cand_sql) and not _has_arith(sel_sql)
    if pattern == "set_logic_error":
        return bool(_set_ops(cand_sql) - _set_ops(sel_sql))
    if pattern == "wrong_filter_or_placement":
        extra = _literals(cand_sql) - _literals(sel_sql)
        moved = ("row_level_predicate_in_having" in _fired(sel_sql, question)
                 and "row_level_predicate_in_having" not in _fired(cand_sql, question))
        return bool(extra) or moved
    # fallback: repairs a day2 violation present in the selected SQL
    return bool(_fired(sel_sql, question) - _fired(cand_sql, question))


def obligation_signals(question):
    """Classifier-only, schema-independent recognition of the derived-obligation
    and set/output patterns the earlier keyword logic under-detected. Returns a
    dict of booleans. Judgement of whether a *candidate* satisfies an obligation
    still requires per-candidate semantic review (see build_day2b_live_*): this
    only flags what the QUESTION obliges, so a reviewer/scorer knows to look.

    No test-id or DB-specific logic; pattern vocabulary only."""
    q = " " + re.sub(r"\s+", " ", (question or "").strip().lower()) + " "
    def has(*toks):
        return any(t in q for t in toks)
    # bare "per X" ratio, e.g. "cost per completed appointment", "budget per student"
    per_ratio = bool(re.search(r"\bper\b(?!cent| cent)", q)) and not has("percentage", "percent")
    # explicit percentage / share
    percentage = has("percentage", "percent", " share of ", "as a percentage")
    # "based on <a>, <b>, and <c>" / total implied by several named components
    based_on_formula = has(" based on ") or bool(
        re.search(r"\b(total|number|sum|combined)\b.*\b(and)\b", q) and
        re.search(r",\s*[a-z].+,\s*and\b", q))
    # paraphrased arithmetic
    addition = has(" adding ", " sum of ", " plus ", " combined ", " total of ")
    subtraction = has(" minus ", " difference ", " remaining ", " still needed",
                      " unused ", " left ", " reduce", " subtract")
    multiplication = has(" times ", " multiplied ", " product of ")
    division = per_ratio or percentage or has(" ratio", " average number of ",
                                              " divided by ", " per ")
    # set "either/both/never/but-not" intent
    set_either = has(" either ", " appear in ", " or ") and has(" appear", " records", " identifiers")
    set_anti = has(" never ", " not in ", " but not ", " without ", " have no ", " excluding ")
    return {
        "derived_expression": bool(addition or subtraction or multiplication
                                   or division or based_on_formula or percentage),
        "per_ratio": per_ratio, "percentage": percentage,
        "based_on_formula": based_on_formula, "addition": addition,
        "subtraction": subtraction, "multiplication": multiplication,
        "division": division, "set_either": set_either, "set_anti": set_anti,
    }


def main():
    rows = list(csv.DictReader(open(REVIEW, newline="", encoding="utf-8-sig")))
    inc = [r for r in rows if r["kind"] == "failure_rerun" and r["recovered"].strip() == "NO"]
    cfg = dc.load_config(); ia = cfg["input_artifacts"]
    traces = {db: {_norm(t["question"]): t
                   for t in dc.parse_trace_file(dc.rp(ia["sql_trace_files"][db]))}
              for db in ia["sql_trace_files"]}

    out = []
    for r in inc:
        db, tid, q, pat = r["database_id"], r["test_id"], r["question"], r["group"]
        sel = r["before_sql"]
        t = traces[db][_norm(q)]
        clean, rejected = [], []
        for c in t["candidates"]:
            if is_fix_candidate(pat, sel, c.get("sql"), q):
                if (c.get("fatal_count") or 0) == 0 and c.get("execution_success"):
                    clean.append(c)
                else:
                    rejected.append(c)
        if clean:
            klass = "correct_candidate_generated_but_not_selected"
        elif rejected:
            klass = "correct_candidate_generated_but_rejected"
        else:
            klass = "no_correct_candidate_generated"
        best = max(clean, key=lambda c: c.get("score") or 0, default=None)
        out.append({
            "database_id": db, "test_id": tid, "pattern": pat,
            "difficulty": r["difficulty"], "question": q,
            "classification": klass,
            "selected_source": t["selected_label"],
            "selected_score": (dc.match_selected_candidate(t)[0] or {}).get("score"),
            "fix_candidate_source": best["source"] if best else "",
            "fix_candidate_score": best["score"] if best else "",
            "num_clean_fix_candidates": len(clean),
            "num_rejected_fix_candidates": len(rejected),
            "audit_reason": r["audit_reason"],
            "selected_sql": (sel or "").replace("\n", " ")[:300],
            "fix_candidate_sql": (best["sql"] if best else "").replace("\n", " ")[:300],
        })
    return out


if __name__ == "__main__":
    from collections import Counter
    res = main()
    print("classification:", dict(Counter(r["classification"] for r in res)))
    for r in res:
        tag = {"correct_candidate_generated_but_not_selected": "LOSS",
               "correct_candidate_generated_but_rejected": "REJECT",
               "no_correct_candidate_generated": "NONE"}[r["classification"]]
        print(f"  {tag:6s} DB{r['database_id']} t{r['test_id']:>3} {r['pattern'][:24]:24s} "
              f"sel={r['selected_source']}({r['selected_score']}) "
              f"fix={r['fix_candidate_source']}({r['fix_candidate_score']})")


def write_outputs():
    res = main()
    import csv as _csv
    cols = ["database_id", "test_id", "pattern", "difficulty", "classification",
            "selected_source", "selected_score", "fix_candidate_source",
            "fix_candidate_score", "num_clean_fix_candidates",
            "num_rejected_fix_candidates", "question", "audit_reason",
            "selected_sql", "fix_candidate_sql"]
    with open(os.path.join(HERE, "day2b_failure_classification.csv"), "w",
              newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(res)

    loss = [r for r in res if r["classification"] == "correct_candidate_generated_but_not_selected"]
    rej = [r for r in res if r["classification"] == "correct_candidate_generated_but_rejected"]
    none = [r for r in res if r["classification"] == "no_correct_candidate_generated"]

    L = ["# Day 2B — Selection-loss analysis (correct candidate generated but not selected)\n",
         "_Trace-verified over the frozen Day 1 candidate pools. A fix candidate "
         "supplies the requested computation/structure the selected SQL lacks, "
         "executed cleanly, and adds no new day2 violation._\n",
         f"**Selection-loss cases: {len(loss)}. Rejected-correct: {len(rej)}.**\n"]
    for r in loss + rej:
        L.append(f"## DB{r['database_id']} test {r['test_id']} — {r['pattern']} "
                 f"({r['classification'].split('_')[-1]})\n")
        L.append(f"- **Question:** {r['question']}")
        L.append(f"- **Audit reason:** {r['audit_reason']}")
        L.append(f"- **Selected (wrong):** `{r['selected_source']}` score "
                 f"{r['selected_score']} — `{r['selected_sql'][:180]}`")
        L.append(f"- **Fix candidate:** `{r['fix_candidate_source']}` score "
                 f"{r['fix_candidate_score']} — `{r['fix_candidate_sql'][:180]}`")
        L.append("- **Why it lost:** a lower-precedence / consensus-grouped operand-"
                 "only or mis-placed candidate outranked the computing candidate; a "
                 "generic derived-expression / output penalty should let the "
                 "computing candidate win.\n")
    open(os.path.join(HERE, "day2b_selection_loss_analysis.md"), "w",
         encoding="utf-8").write("\n".join(L) + "\n")

    from collections import Counter
    M = ["# Day 2B — No-correct-candidate analysis\n",
         "_Cases where NO generated candidate supplies the requested "
         "computation/structure. These need a semantic-contract / generation-"
         "prompt improvement for the recurring pattern, not a selection change._\n",
         f"**No-correct cases: {len(none)}** — by pattern "
         f"{dict(Counter(r['pattern'] for r in none))}\n"]
    for pat in ("aggregation_or_formula_error", "missing_metric_or_output",
                "wrong_filter_or_placement", "set_logic_error"):
        grp = [r for r in none if r["pattern"] == pat]
        if not grp:
            continue
        M.append(f"## {pat} ({len(grp)})\n")
        for r in grp:
            M.append(f"- DB{r['database_id']} t{r['test_id']} — {r['audit_reason']}")
        M.append("")
    M.append("## Recurring generation gaps\n")
    M.append("- Derived expressions (difference/profit/ratio/add) not emitted even "
             "with reminders — strengthen the derived-metric contract obligation.")
    M.append("- Set / anti-join intent (never/without, but-not, either/both) not "
             "structurally realized — strengthen set-intent contract + prompt.")
    M.append("- Explicit filter placement (WHERE vs HAVING) and preserved literals "
             "— strengthen explicit-condition obligation.")
    open(os.path.join(HERE, "day2b_no_correct_candidate_analysis.md"), "w",
         encoding="utf-8").write("\n".join(M) + "\n")
    print("wrote 3 classification files:",
          f"loss={len(loss)} rejected={len(rej)} none={len(none)}")


if __name__ == "__main__":
    pass
