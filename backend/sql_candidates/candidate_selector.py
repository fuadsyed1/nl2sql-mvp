"""
sql_candidates/candidate_selector.py

Selection policy: pick the best SQL candidate from a scored, executed set.

Rules (in order):
  0. Hard disqualification. Candidates whose scorer flagged FATAL reasons
     (illegal join, bare CTE under comparison intent, guard-rejected family
     output, missing question-anchored concept) are excluded from selection.
     They may only win when EVERY candidate is disqualified/failed, and then
     the result carries an explicit low-confidence warning.
  1. Consensus first. Group viable executed candidates by result-set
     equivalence; the heaviest group (size + scores) wins, and its
     highest-scored member is selected. Independent agreement between the
     family builder and the LLM is the strongest correctness signal we have.
  2. Validation-score override. If some OTHER viable executed candidate
     outscores the consensus pick by >= OVERRIDE_MARGIN, structure beats
     agreement (protects against agreeing on the same wrong answer).
  3. No candidate executed: return the least-bad candidate by score, with a
     warning — never silently pretend success.
  4. Low best score (< LOW_SCORE_THRESHOLD): keep the selection but attach a
     low-confidence warning suggesting clarification.

Ties break by source priority: query_family > llm_sql_direct > llm_primary >
llm_variant (deterministic builders are more precise when they match at all,
and a clean direct-SQL candidate beats the extraction variants), then label.
"""

from sql_candidates.candidate_scorer import LOW_SCORE_THRESHOLD
from sql_candidates.candidate_types import to_public_dict
from sql_candidates.result_equivalence import group_candidates

__all__ = ["select_best", "OVERRIDE_MARGIN"]

OVERRIDE_MARGIN = 15.0
DIRECT_OVERRIDE_MARGIN = 10.0   # direct/repair beats a consensus pick at +10

_SOURCE_PRIORITY = {"query_family": 5, "llm_sql_repair": 4, "llm_sql_direct": 3,
                    "llm_sql_direct_grain": 3, "llm_sql_direct_variant": 3,
                    "semantic_join_path": 3,
                    "llm_primary": 2, "llm_variant": 1, "repair": 0}
_DIRECT_SOURCES = ("llm_sql_direct", "llm_sql_direct_grain",
                   "llm_sql_direct_variant", "llm_sql_repair")


def _rank_key(c):
    return (c.score, _SOURCE_PRIORITY.get(c.source, 0), c.label)


def _fatal(c):
    return bool((c.validation or {}).get("fatal"))


def _issue_count(c):
    """Missing-concept / unseen-literal burden of a candidate (lower = cleaner)."""
    val = c.validation or {}
    cl = val.get("checklist") or {}
    return (len(cl.get("missing_columns") or [])
            + len(cl.get("missing_tables") or [])
            + len(val.get("missing_concepts") or [])
            + len(val.get("unseen_literals") or []))


def select_best(candidates):
    """Return (selected_candidate_or_None, selection_meta_dict)."""
    meta = {
        "candidate_count": len(candidates),
        "selected_candidate_source": None,
        "selected_candidate_label": None,
        "selection_reason": None,
        "consensus_group_size": 0,
        "consensus_sources": [],
        "candidate_scores": [
            {"source": c.source, "label": c.label, "score": c.score,
             "executed": c.executed_ok, "row_count": c.row_count,
             "fatal": _fatal(c),
             "fatal_reasons": (c.validation or {}).get("fatal") or []}
            for c in candidates
        ],
        "candidate_reasons": {c.label: c.reasons for c in candidates},
        "rejected_candidates": [],
        "warnings": [],
        "low_confidence": False,
    }
    if not candidates:
        meta["warnings"].append("no candidates were generated")
        return None, meta

    executed = [c for c in candidates if c.executed_ok]

    # Hard disqualification: fatal candidates cannot win while any viable
    # executed candidate exists. If ALL executed candidates are fatal, they
    # compete among themselves — with an explicit warning.
    viable = [c for c in executed if not _fatal(c)]
    if executed and not viable:
        meta["warnings"].append(
            "all executed candidates failed hard semantic checks; "
            "low confidence")
    pool = viable or executed

    if pool:
        groups = group_candidates(pool)

        def _group_key(g):
            # Consensus on EMPTINESS is not agreement: a group whose members
            # all returned zero rows only wins when no reasonably-scored
            # group produced actual rows.
            has_rows = any((c.row_count or 0) > 0 for c in g)
            strong = max(c.score for c in g) >= LOW_SCORE_THRESHOLD
            return (1 if (has_rows and strong) else 0,
                    sum(1 + c.score / 100.0 for c in g),
                    max(c.score for c in g))

        best_group = max(groups, key=_group_key)
        pick = max(best_group, key=_rank_key)
        if len(best_group) > 1:
            meta["selection_reason"] = "consensus_group"
        else:
            meta["selection_reason"] = "best_scored_executed"

        top = max(pool, key=_rank_key)
        if top is not pick and top not in best_group \
                and top.score >= pick.score + OVERRIDE_MARGIN:
            pick = top
            meta["selection_reason"] = "validation_score_override"
            best_group = [top]

        # Direct/repair override: a non-fatal direct or repaired SQL that
        # outscores the consensus pick by DIRECT_OVERRIDE_MARGIN wins —
        # consensus between weaker candidates must not bury a stronger
        # independently-written query.
        best_direct = None
        for c in pool:
            if c.source in _DIRECT_SOURCES and c is not pick \
                    and c not in best_group:
                if best_direct is None or _rank_key(c) > _rank_key(best_direct):
                    best_direct = c
        if best_direct is not None \
                and best_direct.score >= pick.score + DIRECT_OVERRIDE_MARGIN:
            pick = best_direct
            meta["selection_reason"] = "direct_sql_override"
            best_group = [best_direct]

        # Executed direct/repair preference: at equal-or-better score, an
        # executed non-fatal direct/repair candidate with a concrete advantage
        # replaces the pick (fixes zero rows, uses more checklist concepts, or
        # carries no missing-concept/unseen-literal notes).
        challenger = None
        for c in pool:
            if c is pick or c in best_group or _fatal(c) \
                    or c.source not in _DIRECT_SOURCES or c.score < pick.score:
                continue
            zero_fix = (pick.row_count or 0) == 0 and (c.row_count or 0) > 0
            concept_fix = pick.source in ("llm_primary", "llm_variant") \
                and _issue_count(c) < _issue_count(pick)
            note_fix = _issue_count(pick) > 0 and _issue_count(c) == 0
            # At a score tie, query_family only keeps the win when it is the
            # one with rows AND has no warnings; otherwise direct/repair wins.
            family_fix = pick.source == "query_family" and not (
                (pick.row_count or 0) > 0 and (c.row_count or 0) == 0
                and not pick.reasons and not _fatal(pick))
            if zero_fix or concept_fix or note_fix or family_fix:
                if challenger is None or _rank_key(c) > _rank_key(challenger):
                    challenger = c
        if challenger is not None:
            pick = challenger
            meta["selection_reason"] = "direct_repair_preference"
            best_group = [challenger]

        meta["consensus_group_size"] = len(best_group)
        meta["consensus_sources"] = sorted({c.source for c in best_group})
    else:
        non_fatal = [c for c in candidates if not _fatal(c)]
        pick = max(non_fatal or candidates, key=_rank_key)
        meta["selection_reason"] = "least_bad_no_execution"
        meta["warnings"].append(
            "no candidate executed successfully; returning the least-bad SQL")

    if _fatal(pick):
        meta["low_confidence"] = True
        meta["warnings"].append(
            "LOW CONFIDENCE RESULT: every usable candidate failed hard "
            "semantic checks; this SQL is a best-effort fallback, NOT a "
            "normal success. Fatal reasons: "
            + "; ".join((pick.validation or {}).get("fatal") or []))

    if pick.score < LOW_SCORE_THRESHOLD:
        meta["low_confidence"] = True
        meta["warnings"].append(
            f"low confidence (score {pick.score} < {LOW_SCORE_THRESHOLD}); "
            "the question may need clarification")

    meta["selected_candidate_source"] = pick.source
    meta["selected_candidate_label"] = pick.label
    meta["rejected_candidates"] = [
        to_public_dict(c) for c in candidates if c is not pick
    ]
    return pick, meta
