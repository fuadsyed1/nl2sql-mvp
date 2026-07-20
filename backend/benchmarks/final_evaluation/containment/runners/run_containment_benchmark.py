"""
Final containment benchmark runner (resumable, sequential).

    python -m benchmarks.final_evaluation.containment.runners.run_containment_benchmark \
        [--category equivalence] [--limit 5] [--start-index 0] [--resume]
        [--output-prefix smoke] [--timeout 600] [--max-retries 1]
        [--smoke-per-category 2]

Posts each group's questions to /database/{id}/check_containment_batch and
scores: per-query SQL generation, pairwise relations, full hierarchy,
broadest/narrowest sets, equivalence classes, incomparable pairs,
counterexample validity, controlled failures, and 2-5-query input parsing.
Data-dependent evaluation on the frozen databases — not a symbolic proof.
"""

import argparse
import collections
import csv
import json
import os
import time
import urllib.error
import urllib.request

from benchmarks.final_evaluation.common import manifest as mf
from benchmarks.final_evaluation.common import scoring

BASE = os.path.join(os.path.dirname(__file__), "..", "..")
MAN_DIR = os.path.join(BASE, "containment", "manifests")
REF_DIR = os.path.join(BASE, "containment", "references")
RES_DIR = os.path.join(BASE, "containment", "results")
REP_DIR = os.path.join(BASE, "containment", "reports")
BASE_URL = os.environ.get("SPIDERSQL_URL", "http://127.0.0.1:8000")

# service relationship string -> benchmark relation, oriented left=query_a
_REL_MAP = {
    "query_a_contained_in_query_b": "contained_in",
    "query_b_contained_in_query_a": "contains",
    "equivalent_on_current_database": "equivalent",
    "incomparable_on_current_database": "incomparable",
    "unknown": "unknown",
}


def post_group(database_id, questions, timeout):
    url = f"{BASE_URL}/database/{database_id}/check_containment_batch"
    payload = json.dumps({"queries": questions}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"},
        method="POST")
    started = time.time()
    timed_out = False
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        data = {"success": False,
                "_error": exc.read().decode("utf-8", errors="replace")}
    except Exception as exc:
        timed_out = "timed out" in str(exc).lower()
        data = {"success": False, "_error": repr(exc)}
    return data, round(time.time() - started, 2), timed_out


def _reported_pairs(response, qids):
    """{(left_qid, right_qid): relation} oriented as benchmark pairs."""
    out = {}
    for p in (response or {}).get("pairwise_relationships") or []:
        try:
            a, b = int(p["query_a"]), int(p["query_b"])
            la, lb = qids[a - 1], qids[b - 1]
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        out[(la, lb)] = _REL_MAP.get(p.get("relationship"), "unknown")
        out[("__rows__", la, lb)] = (p.get("a_minus_b_rows") or [],
                                     p.get("b_minus_a_rows") or [])
    return out


def _validate_counterexamples(response, qids, refs):
    """(checked, valid): every returned counterexample row must exist in the
    claimed left reference set and be absent from the right one. Rows whose
    projection cannot be matched to the canonical comparison columns are
    counted as unverified (not valid, not fatal)."""
    checked = valid = 0
    ref_sets = {qid: {tuple(r) for r in refs["queries"][qid]["rows"]}
                for qid in refs.get("queries", {})}
    ncols = {qid: len(refs["queries"][qid]["columns"])
             for qid in refs.get("queries", {})}
    for p in (response or {}).get("pairwise_relationships") or []:
        try:
            a, b = qids[int(p["query_a"]) - 1], qids[int(p["query_b"]) - 1]
        except Exception:
            continue
        for rows, left, right in ((p.get("a_minus_b_rows") or [], a, b),
                                  (p.get("b_minus_a_rows") or [], b, a)):
            for row in rows[:5]:
                checked += 1
                norm = tuple(scoring.normalize_rows([row])[0])
                if left in ref_sets and right in ref_sets \
                        and len(norm) == ncols.get(left) \
                        and ncols.get(left) == ncols.get(right):
                    if norm in ref_sets[left] and norm not in ref_sets[right]:
                        valid += 1
    return checked, valid


def score_group(grp, refs, response):
    qids = [q["query_id"] for q in grp["queries"]]
    reported = _reported_pairs(response, qids)
    expected = {(p["left"], p["right"]): p["relation"]
                for p in grp["expected_pairwise"]}
    pair_total = len(expected)
    pair_ok = sum(1 for k, v in expected.items()
                  if reported.get(k) == v)
    inc_total = sum(1 for v in expected.values() if v == "incomparable")
    inc_ok = sum(1 for k, v in expected.items()
                 if v == "incomparable" and reported.get(k) == v)

    analysis = (response or {}).get("analysis") or {}
    mains = sorted(qids[m["index"] - 1]
                   for m in analysis.get("main_queries") or []
                   if 0 < m.get("index", 0) <= len(qids))
    # narrowest from reported pairwise: queries that contain nothing
    contains_any = set()
    for (l, r), v in expected.items():
        pass
    rep_narrow = sorted(
        q for q in qids
        if not any(reported.get((q, o)) == "contains"
                   or reported.get((o, q)) == "contained_in"
                   for o in qids if o != q)
        and any(reported.get((q, o), reported.get((o, q), "unknown"))
                != "unknown" for o in qids if o != q))
    eq_rep = sorted(sorted(qids[i - 1] for i in grpx if 0 < i <= len(qids))
                    for grpx in analysis.get("equivalent_groups") or [])
    eq_exp = sorted(sorted(c) for c in grp["expected_equivalence_classes"])

    q_results = (response or {}).get("query_results") or []
    gen_ok = sum(1 for qr in q_results if qr.get("success")
                 and qr.get("sql"))
    parse_ok = len(q_results) == len(qids)
    ce_checked, ce_valid = _validate_counterexamples(response, qids,
                                                     refs or {})
    hierarchy_ok = (pair_ok == pair_total
                    and mains == grp["expected_broadest"]
                    and rep_narrow == grp["expected_narrowest"])
    return {
        "pairs_total": pair_total, "pairs_correct": pair_ok,
        "incomparable_total": inc_total, "incomparable_correct": inc_ok,
        "broadest_expected": grp["expected_broadest"],
        "broadest_reported": mains,
        "broadest_correct": mains == grp["expected_broadest"],
        "narrowest_expected": grp["expected_narrowest"],
        "narrowest_reported": rep_narrow,
        "narrowest_correct": rep_narrow == grp["expected_narrowest"],
        "equivalence_expected": eq_exp, "equivalence_reported": eq_rep,
        "equivalence_correct": eq_rep == eq_exp,
        "hierarchy_correct": hierarchy_ok,
        "sql_generated_ok": gen_ok, "query_count": len(qids),
        "input_parse_ok": parse_ok,
        "counterexamples_checked": ce_checked,
        "counterexamples_valid": ce_valid,
        "controlled_failures": sum(
            1 for qr in q_results
            if not qr.get("success") or qr.get("has_fatal_validation")),
    }


def write_reports(records, prefix):
    os.makedirs(REP_DIR, exist_ok=True)

    def _csv(name, header, rows):
        with open(os.path.join(REP_DIR, f"{prefix}_{name}.csv"), "w",
                  newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)

    flat = ["group_id", "category", "difficulty", "query_count",
            "sql_generated_ok", "pairs_total", "pairs_correct",
            "hierarchy_correct", "broadest_correct", "narrowest_correct",
            "equivalence_correct", "counterexamples_checked",
            "counterexamples_valid", "controlled_failures", "latency_s"]
    _csv("groups_flat", flat, [[r.get(k) for k in flat] for r in records])
    pair_rows = []
    for r in records:
        for p in r.get("pair_detail") or []:
            pair_rows.append([r["group_id"], p["left"], p["right"],
                              p["expected"], p["reported"],
                              p["expected"] == p["reported"]])
    _csv("pairwise", ["group_id", "left", "right", "expected",
                      "reported", "correct"], pair_rows)

    agg = collections.defaultdict(list)
    for r in records:
        agg[r["category"]].append(r)
    cat_rows, lines = [], [
        "FINAL CONTAINMENT BENCHMARK REPORT",
        "(data-dependent containment on frozen databases — not symbolic "
        "proof)", "",
        "| Containment Type | Groups | Query SQL Accuracy | Pairwise "
        "Accuracy | Full Hierarchy Accuracy | Counterexample Accuracy | "
        "Controlled Failures | Average Latency |",
        "|---|---|---|---|---|---|---|---|"]
    for cat in sorted(agg):
        rs = agg[cat]
        qtotal = sum(r["query_count"] for r in rs)
        qok = sum(r["sql_generated_ok"] for r in rs)
        pt = sum(r["pairs_total"] for r in rs)
        pk = sum(r["pairs_correct"] for r in rs)
        h = sum(1 for r in rs if r["hierarchy_correct"])
        cc = sum(r["counterexamples_checked"] for r in rs)
        cv = sum(r["counterexamples_valid"] for r in rs)
        cf = sum(r["controlled_failures"] for r in rs)
        lat = sum(r["latency_s"] for r in rs) / len(rs)
        row = [cat, len(rs), f"{qok}/{qtotal}",
               f"{pk / pt:.2f}" if pt else "-",
               f"{h / len(rs):.2f}",
               f"{cv / cc:.2f}" if cc else "-", cf, f"{lat:.1f}s"]
        cat_rows.append(row)
        lines.append("| " + " | ".join(str(x) for x in row) + " |")
    _csv("category_summary",
         ["category", "groups", "sql_ok", "pairwise_acc",
          "hierarchy_acc", "counterexample_acc", "controlled_failures",
          "avg_latency"], cat_rows)
    _csv("hierarchy_summary",
         ["group_id", "hierarchy_correct", "broadest_correct",
          "narrowest_correct", "equivalence_correct"],
         [[r["group_id"], r["hierarchy_correct"], r["broadest_correct"],
           r["narrowest_correct"], r["equivalence_correct"]]
          for r in records])
    _csv("counterexample_summary",
         ["group_id", "checked", "valid"],
         [[r["group_id"], r["counterexamples_checked"],
           r["counterexamples_valid"]] for r in records])
    _csv("controlled_failures", ["group_id", "count"],
         [[r["group_id"], r["controlled_failures"]] for r in records
          if r["controlled_failures"]])
    sz = collections.defaultdict(list)
    for r in records:
        sz[r["query_count"]].append(r["latency_s"])
    _csv("latency_by_group_size", ["group_size", "groups", "avg_latency"],
         [[k, len(v), f"{sum(v) / len(v):.1f}"] for k, v in
          sorted(sz.items())])
    with open(os.path.join(REP_DIR, f"{prefix}_report.txt"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(REP_DIR, f"{prefix}_results.json"), "w",
              encoding="utf-8") as f:
        json.dump(records, f, indent=1, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", action="append", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--start-index", type=int, default=0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--output-prefix", default="full")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--max-retries", type=int, default=1)
    ap.add_argument("--smoke-per-category", type=int, default=None)
    args = ap.parse_args()

    categories = args.category or list(mf.CONTAINMENT_CATEGORIES)
    groups, refs = [], {}
    for cat in categories:
        groups.extend(mf.read_jsonl(os.path.join(MAN_DIR, f"{cat}.jsonl")))
        for r in mf.read_jsonl(os.path.join(REF_DIR, f"{cat}_refs.jsonl")):
            refs[r["group_id"]] = r
    if args.smoke_per_category:
        seen = collections.Counter()
        groups = [gp for gp in groups
                  if seen.update([gp["category"]]) or
                  seen[gp["category"]] <= args.smoke_per_category]
    groups = groups[args.start_index:]
    if args.limit:
        groups = groups[:args.limit]

    os.makedirs(RES_DIR, exist_ok=True)
    out_path = os.path.join(RES_DIR, f"{args.output_prefix}_results.jsonl")
    records, done = [], set()
    if args.resume and os.path.exists(out_path):
        records = mf.read_jsonl(out_path)
        done = {r["group_id"] for r in records}
        print(f"resume: {len(done)} groups already completed")
    elif os.path.exists(out_path) and not args.resume:
        raise SystemExit(f"{out_path} exists; use --resume or a new "
                         f"--output-prefix")

    with open(out_path, "a", encoding="utf-8") as out:
        for i, grp in enumerate(groups):
            if grp["group_id"] in done:
                continue
            questions = [q["question"] for q in grp["queries"]]
            response, elapsed, timed_out = None, 0.0, False
            for attempt in range(args.max_retries + 1):
                response, elapsed, timed_out = post_group(
                    grp["database_id"], questions, args.timeout)
                if "_error" not in (response or {}):
                    break
                time.sleep(2 * (attempt + 1))
            scores = score_group(grp, refs.get(grp["group_id"]), response)
            qids = [q["query_id"] for q in grp["queries"]]
            reported = _reported_pairs(response, qids)
            rec = {
                "group_id": grp["group_id"], "category": grp["category"],
                "difficulty": grp["difficulty"],
                "database_id": grp["database_id"],
                "latency_s": elapsed, "timed_out": timed_out,
                "pair_detail": [
                    {"left": p["left"], "right": p["right"],
                     "expected": p["relation"],
                     "reported": reported.get((p["left"], p["right"]),
                                              "missing")}
                    for p in grp["expected_pairwise"]],
                "generated_sql": [
                    {"query_id": qids[j], "sql": qr.get("sql"),
                     "success": qr.get("success")}
                    for j, qr in enumerate(
                        (response or {}).get("query_results") or [])
                    if j < len(qids)],
                **scores,
            }
            records.append(rec)
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            print(f"[{i + 1}/{len(groups)}] {grp['group_id']}: pairs "
                  f"{scores['pairs_correct']}/{scores['pairs_total']} "
                  f"hier={'Y' if scores['hierarchy_correct'] else 'N'} "
                  f"({elapsed}s)", flush=True)

    write_reports(records, args.output_prefix)
    print(f"done: {len(records)} groups -> {out_path}")


if __name__ == "__main__":
    main()
