"""
benchmarks/run_meta.py

Shared helpers for the debug runners: extract per-candidate selection
metadata from an /execute_sql response and format it for console/markdown.
"""

__all__ = ["candidate_meta", "format_candidates", "format_gold",
           "repair_meta", "format_repair"]


def repair_meta(response):
    """One-shot-repair metadata from an /execute_sql response."""
    return {
        "repair_attempted": bool(response.get("repair_attempted")),
        "repair_triggers": response.get("repair_triggers") or [],
        "repair_executed": bool(response.get("repair_executed")),
        "repair_score": response.get("repair_score"),
        "repair_selected": bool(response.get("repair_selected")),
        "selected_source_before_repair":
            response.get("selected_source_before_repair"),
        "selected_source_after": response.get("selected_candidate_source"),
    }


def format_repair(meta):
    """One-line repair verdict."""
    if not meta or not meta.get("repair_attempted"):
        return "REPAIR: not attempted"
    return (f"REPAIR: attempted | executed={meta.get('repair_executed')} "
            f"score={meta.get('repair_score')} "
            f"selected={meta.get('repair_selected')} | "
            f"source {meta.get('selected_source_before_repair')} -> "
            f"{meta.get('selected_source_after')}")


def candidate_meta(response):
    """Selection metadata: every candidate's source/score/executed/fatal +
    reasons, the winner, and the selection warnings."""
    scores = response.get("candidate_scores") or []
    reasons = response.get("candidate_reasons") or {}
    return {
        "selected_candidate_source": response.get("selected_candidate_source"),
        "selection_reason": response.get("selection_reason"),
        "candidate_count": response.get("candidate_count"),
        "warnings": response.get("warnings") or [],
        "candidates": [
            {
                "source": c.get("source"),
                "label": c.get("label"),
                "score": c.get("score"),
                "executed": c.get("executed"),
                "row_count": c.get("row_count"),
                "fatal": bool(c.get("fatal")),
                "fatal_reasons": c.get("fatal_reasons") or [],
                "reasons": reasons.get(c.get("label")) or [],
            }
            for c in scores
        ],
    }


def format_candidates(meta):
    """Compact text lines describing the candidate set."""
    lines = [
        f"SELECTED: {meta['selected_candidate_source']} "
        f"(reason={meta['selection_reason']}, candidates={meta['candidate_count']})"
    ]
    for c in meta["candidates"]:
        lines.append(
            f"  - {c['label']}: score={c['score']} executed={c['executed']} "
            f"rows={c['row_count']} fatal={c['fatal']}"
        )
        for r in (c["fatal_reasons"] or [])[:2]:
            lines.append(f"      FATAL: {r}")
        for r in (c["reasons"] or [])[:3]:
            lines.append(f"      note: {r}")
    for w in meta["warnings"]:
        lines.append(f"  WARNING: {w}")
    return lines


def format_gold(g):
    """One-line gold verdict."""
    if not g:
        return "GOLD: (not graded)"
    if not g.get("gold_found"):
        return f"GOLD: no gold entry ({g.get('note')})"
    if g.get("gold_error"):
        return f"GOLD: gold_error {g['gold_error']}"
    if g.get("gen_error"):
        return f"GOLD: WRONG (gen_error: {g['gen_error']})"
    verdict = "OK" if g.get("semantic_ok") else "WRONG"
    extra = " (both empty — weak)" if g.get("both_empty") else ""
    return (f"GOLD: {verdict} level={g.get('match_level')} "
            f"gold_rows={g.get('gold_rows')} gen_rows={g.get('gen_rows')}{extra}")
