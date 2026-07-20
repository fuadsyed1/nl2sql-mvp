"""
replay_day2_validators.py  (Task C — static protected replay, no LLM)

Runs the Day 2 static validators over the frozen Day 1 SQL:
  * 1,606 protected semantically-correct queries
  *   394 semantically-incorrect queries
For every rule it reports protected-flagged, incorrect-flagged, precision and
coverage, and enforces the acceptance rule: a rule may be FATAL only when it
flags ZERO protected queries. Outputs day2_validator_replay.csv and
day2_validator_replay_summary.json. Reads only frozen artifacts; changes nothing.
"""
import os, sys, csv, json
from collections import defaultdict

HERE = os.path.dirname(__file__)
BACKEND = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(BACKEND, "benchmarks", "go_live_day1"))
import day1_common as dc                                   # noqa: E402
from sql_candidates import day2_semantic_rules as d2       # noqa: E402


def load_all_queries():
    """(question, sql, verdict) for all 2000 tests from the frozen audits."""
    cfg = dc.load_config(); ia = cfg["input_artifacts"]
    rows = []
    for db in ia["sql_result_files"]:
        info = ia["semantic_audit_files"][db]
        rrecs = dc.parse_result_file(dc.rp(ia["sql_result_files"][db]))
        vmap = dc.build_verdict_map(
            dc.parse_semantic_audit(dc.rp(info["path"]), info.get("format")), rrecs)
        for tid, v in vmap.items():
            rows.append((int(db), tid, v.get("query"), v.get("sql"),
                         v.get("semantic_verdict")))
    return rows


def main():
    rows = load_all_queries()
    protected = sum(1 for r in rows if r[4] == "CORRECT")
    incorrect = sum(1 for r in rows if r[4] == "INCORRECT")

    fire_rows = []
    prot_flag = defaultdict(int); inc_flag = defaultdict(int)
    for db, tid, q, sql, verdict in rows:
        for f in d2.evaluate_rules(sql, q):
            fire_rows.append({"database_id": db, "test_id": tid, "verdict": verdict,
                              "rule": f["rule"], "severity": f["severity"],
                              "message": f["message"][:160]})
            if verdict == "CORRECT":
                prot_flag[f["rule"]] += 1
            elif verdict == "INCORRECT":
                inc_flag[f["rule"]] += 1

    with open(os.path.join(HERE, "day2_validator_replay.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["database_id", "test_id", "verdict",
                                          "rule", "severity", "message"])
        w.writeheader(); w.writerows(fire_rows)

    per_rule = {}
    fatal_eligible, kept_warning = [], []
    for rule in d2.RULES:
        pf, if_ = prot_flag.get(rule, 0), inc_flag.get(rule, 0)
        total_flag = pf + if_
        per_rule[rule] = {
            "severity": d2.RULE_SEVERITY.get(rule),
            "protected_flagged": pf, "incorrect_flagged": if_,
            "precision_estimate": round(if_ / total_flag, 4) if total_flag else None,
            "coverage_incorrect": round(if_ / incorrect, 4) if incorrect else None,
            "fatal_eligible": pf == 0 and if_ > 0,
        }
        if pf == 0 and if_ > 0:
            fatal_eligible.append(rule)
        if pf > 0:
            kept_warning.append(rule)

    # acceptance check: every rule currently marked fatal must flag 0 protected
    fatal_violations = [r for r in d2.RULES
                        if d2.RULE_SEVERITY.get(r) == "fatal" and prot_flag.get(r, 0) > 0]

    summary = {
        "generated_at": dc.now_iso(),
        "protected_total": protected, "incorrect_total": incorrect,
        "per_rule": per_rule,
        "fatal_eligible_rules": fatal_eligible,
        "currently_fatal_rules": [r for r in d2.RULES
                                  if d2.RULE_SEVERITY.get(r) == "fatal"],
        "fatal_rules_flagging_protected": fatal_violations,
        "acceptance_fatal_zero_protected": len(fatal_violations) == 0,
        "note": "A rule may be FATAL only when protected_flagged == 0. Rules that "
                "flag any protected query stay warning/diagnostic.",
    }
    with open(os.path.join(HERE, "day2_validator_replay_summary.json"), "w",
              encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"queries: protected={protected} incorrect={incorrect} "
          f"| firings={len(fire_rows)}")
    for rule in d2.RULES:
        pr = per_rule[rule]
        print(f"  {rule:38s} sev={pr['severity']:10s} prot={pr['protected_flagged']:4d} "
              f"inc={pr['incorrect_flagged']:4d} prec={pr['precision_estimate']} "
              f"cov={pr['coverage_incorrect']}")
    print("fatal-eligible (0 protected, >0 incorrect):", fatal_eligible)
    print("currently-fatal flagging protected (must be empty):", fatal_violations)


if __name__ == "__main__":
    main()
