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
                    "llm_primary": 2, "llm_variant": 1, "repair": 0}
_DIRECT_SOURCES = ("llm_sql_direct", "llm_sql_repair")


def _rank_key(c):
    return (c.score, _SOURCE_PRIORITY.get(c.source, 0), c.label)


def _fatal(c):
    return bool((c.validation or {}).get("fatal"))


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
    }
    if not candidates:
        meta["warnings"].append("no candidates were generated")
        return None, meta

    executed = [c for c in candidates if c.executed_ok]

    # Hard disqualification: fatal candidates cannot win while any viable
    # executed candidate exists. If ALL executed candidates are fatal, they
    # compete among themselves — with an explicit warning.
    viable = [c for c in executed if not _fatal(c)]
    rescue = None
    if executed and not viable:
        meta["warnings"].append(
            "all executed candidates failed hard semantic checks; "
            "low confidence")
        # A fatal executed candidate must never beat a NON-fatal direct/repair
        # attempt, even one that failed to execute.
        rescuable = [c for c in candidates
                     if c.sql and not _fatal(c) and c.source in _DIRECT_SOURCES]
        if rescuable:
            rescue = max(rescuable, key=_rank_key)
    pool = viable or executed

    if rescue is not None:
        pick = rescue
        meta["selection_reason"] = "non_fatal_direct_over_fatal_executed"
        meta["warnings"].append(
            "returning a non-fatal direct/repair SQL that did not execute, "
            "instead of a disqualified executed candidate")
        meta["consensus_group_size"] = 1
        meta["consensus_sources"] = [pick.source]
    elif pool:
        groups = group_candidates(pool)
        best_group = max(
            groups,
            key=lambda g: (sum(1 + c.score / 100.0 for c in g),
                           max(c.score for c in g)),
        )
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

        meta["consensus_group_size"] = len(best_group)
        meta["consensus_sources"] = sorted({c.source for c in best_group})
    else:
        non_fatal = [c for c in candidates if not _fatal(c)]
        pick = max(non_fatal or candidates, key=_rank_key)
        meta["selection_reason"] = "least_bad_no_execution"
        meta["warnings"].append(
            "no candidate executed successfully; returning the least-bad SQL")

    if _fatal(pick):
        meta["warnings"].append(
            "selected candidate failed hard semantic checks: "
            + "; ".join((pick.validation or {}).get("fatal") or []))

    if pick.score < LOW_SCORE_THRESHOLD:
        meta["warnings"].append(
            f"low confidence (score {pick.score} < {LOW_SCORE_THRESHOLD}); "
            "the question may need clarification")

    meta["selected_candidate_source"] = pick.source
    meta["selected_candidate_label"] = pick.label
    meta["rejected_candidates"] = [
        to_public_dict(c) for c in candidates if c is not pick
    ]
    return pick, meta
