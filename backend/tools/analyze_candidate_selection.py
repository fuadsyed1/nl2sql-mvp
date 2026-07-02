"""
tools/analyze_candidate_selection.py

Summarize multi-candidate selection behavior from benchmark debug JSONs
(run_petfood_50_sql_debug_db28.py / run_2db_40_sql_debug.py outputs).

Usage (from the backend folder, after rerunning the benchmarks):
    python tools/analyze_candidate_selection.py petfood_50_sql_debug_db28_<ts>.json
    python tools/analyze_candidate_selection.py spidersql_2db_40_sql_debug_<ts>.json
    python tools/analyze_candidate_selection.py <file1.json> <file2.json>

Reports:
  * candidate_count average
  * selected source breakdown + selection_reason breakdown
  * EXEC_OK count
  * estimated perfect-SQL count (heuristic: executed + score >= 70 + no
    warnings + no scorer complaints; NOT a substitute for manual grading)
  * examples where the selected candidate beat query_family
  * examples where the selected candidate beat the LLM primary path
  * remaining failures / low-confidence answers
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PERFECT_SCORE_FLOOR = 70.0


def _records(payload):
    if isinstance(payload, list):          # run_2db_40 writes a bare list
        return payload
    for key in ("results", "items", "records"):
        if isinstance(payload.get(key), list):
            return payload[key]
    return []


def _resp(record):
    return record.get("response") or record.get("full_response") or {}


def _fmt_q(record, width=90):
    q = record.get("question") or ""
    return q if len(q) <= width else q[: width - 3] + "..."


def _idx(record):
    """Question label: petfood uses 'index', 2db uses 'query_number' + db name."""
    i = record.get("index")
    if i is not None:
        return f"Q{i:02d}"
    n = record.get("query_number")
    db = record.get("database_name") or record.get("database_id") or ""
    return f"{db} Q{n:02d}" if n is not None else "Q??"


def analyze(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = _records(payload)
    n = len(records)
    print("=" * 100)
    print(f"FILE: {path.name}   ({n} questions)")

    counts, reasons, consensus = [], Counter(), Counter()
    sources = Counter()
    exec_ok = 0
    perfect_est = 0
    beat_family, beat_llm, failures, low_conf = [], [], [], []

    for r in records:
        resp = _resp(r)
        scores = resp.get("candidate_scores") or []
        if scores:
            counts.append(len(scores))
        src = resp.get("selected_candidate_source") or r.get("extraction_source")
        if src:
            sources[src] += 1
        if resp.get("selection_reason"):
            reasons[resp["selection_reason"]] += 1
        if resp.get("consensus_group_size"):
            consensus[resp["consensus_group_size"]] += 1

        ok = bool(r.get("success"))
        exec_ok += ok
        sel_score = resp.get("selected_candidate_score")
        warnings = resp.get("warnings") or []
        sel_label = resp.get("selected_candidate_label")
        sel_reasons = (resp.get("candidate_reasons") or {}).get(sel_label) or []

        if ok and sel_score is not None and sel_score >= PERFECT_SCORE_FLOOR \
                and not warnings and not sel_reasons:
            perfect_est += 1

        by_source = {}
        for s in scores:
            by_source.setdefault(s["source"], []).append(s)

        # selected candidate beat an executable query_family candidate
        fam = by_source.get("query_family", [])
        if fam and src and src != "query_family":
            f = fam[0]
            beat_family.append((r.get("index"), _fmt_q(r), src, sel_score,
                                f.get("score"), f.get("executed")))

        # selected candidate beat the LLM primary path
        prim = by_source.get("llm_primary", [])
        if prim and src in ("query_family", "llm_variant"):
            p = prim[0]
            beat_llm.append((r.get("index"), _fmt_q(r), src, sel_score,
                             p.get("score"), p.get("executed")))

        if not ok:
            failures.append((r.get("index"), _fmt_q(r),
                             r.get("error") or "; ".join(warnings)))
        elif warnings:
            low_conf.append((r.get("index"), _fmt_q(r), sel_score,
                             "; ".join(warnings)))

    avg = (sum(counts) / len(counts)) if counts else 0
    print(f"\ncandidate_count average : {avg:.2f}  (min {min(counts, default=0)}, max {max(counts, default=0)})")
    print(f"EXEC_OK                 : {exec_ok}/{n}")
    print(f"estimated perfect SQL   : {perfect_est}/{n}  "
          f"(executed + score>={PERFECT_SCORE_FLOOR:.0f} + clean; heuristic, verify manually)")
    print(f"selected source         : {dict(sources)}")
    print(f"selection reason        : {dict(reasons)}")
    print(f"consensus group sizes   : {dict(consensus)}")

    def _section(title, rows, fmt):
        print(f"\n-- {title} ({len(rows)})")
        for row in rows[:10]:
            print("   " + fmt(*row))
        if len(rows) > 10:
            print(f"   ... and {len(rows) - 10} more")

    _section("selected candidate beat query_family", beat_family,
             lambda i, q, s, ss, fs, fx:
             f"Q{i:02d} [{s} {ss} vs family {fs}{'' if fx else ' (exec fail)'}] {q}")
    _section("selected candidate beat LLM primary", beat_llm,
             lambda i, q, s, ss, ps, px:
             f"Q{i:02d} [{s} {ss} vs llm_primary {ps}{'' if px else ' (exec fail)'}] {q}")
    _section("remaining failures", failures,
             lambda i, q, e: f"Q{i:02d} {q}  ERROR: {e}")
    _section("executed but low-confidence (check by hand)", low_conf,
             lambda i, q, s, w: f"Q{i:02d} [score {s}] {q}  WARN: {w}")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    for a in args:
        analyze(Path(a))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
