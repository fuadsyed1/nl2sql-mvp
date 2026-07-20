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
from sql_candidates.semantic_obligations import (
    compute_profile, canonical_signature, lineage_family, is_eligible,
    override_dominates)
from sql_candidates.rc5_ranking import (
    rc5_obligations, rc5_dominates, rc5_rank_tuple)
from sql_candidates.consensus_ranking import consensus_select

__all__ = ["select_best", "enforce_selection_safety", "OVERRIDE_MARGIN"]

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


def enforce_selection_safety(selected, candidates):
    """HARD selection invariant (final stabilization, Part A).

    A candidate may be returned as a NORMAL SUCCESS only when it executed and
    carries no fatal reason (scorer fatal list — grain contract, semantic
    guards, shape, checklist concepts, ...). This function is the last gate
    before response assembly:

      * selected is clean            -> unchanged;
      * selected is fatal, but some  -> the best non-fatal executed candidate
        non-fatal executed exists       replaces it (never a fatal one);
      * selected is fatal and no     -> (None, True, fatal_reasons): the
        clean executed candidate        caller MUST return the controlled
        exists                          no_semantically_valid_sql failure and
                                        may expose the rejected SQL only as an
                                        explicitly labeled debug field.

    A selected candidate that merely did not execute is left unchanged — the
    response is already success=False in that case (never a normal success).
    """
    if selected is None or not _fatal(selected):
        return selected, False, []
    viable = [c for c in candidates if c.executed_ok and not _fatal(c)]
    if viable:
        return max(viable, key=_rank_key), False, []
    return None, True, list((selected.validation or {}).get("fatal") or [])


def _rc5_keys():
    from sql_candidates.rc5_ranking import RC5_ORDER
    return RC5_ORDER


def select_best(candidates, checklist=None, contract=None, idx=None,
                question=None):
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

    # RC3 — semantic eligibility (separate hard eligibility from soft scoring).
    # A candidate that misses a MANDATORY obligation (a requested output, the
    # requested aggregate, the derived formula, required grouping/set logic, a
    # correct relationship role, grain, or population) is "semantically
    # incomplete" and is demoted: it may serve only as a fallback when no
    # complete candidate exists, and it never counts as a full consensus vote.
    for c in executed:
        try:
            c._profile = compute_profile(c.sql, c.validation, checklist,
                                         contract, idx)
            c._signature = canonical_signature(c.sql)
            c._lineage = lineage_family(c.source)
        except Exception:
            c._profile = {"eligibility": "eligible", "_missing": []}
            c._signature = ("raw", (c.sql or ""))
            c._lineage = lineage_family(c.source)
    eligible = [c for c in viable if is_eligible(c._profile)]
    meta["semantic_eligible_count"] = len(eligible)
    meta["semantic_incomplete"] = [
        {"label": c.label, "missing": c._profile.get("_missing")}
        for c in viable if not is_eligible(c._profile)]
    pool = eligible or viable or executed

    if pool:
        # Precompute RC5 obligation profiles ONCE (independent-consensus
        # dominance check + the RC5 ranking stage below both reuse them).
        for c in pool:
            try:
                base = dict(getattr(c, "_profile", None) or {})
                base["_execution"] = getattr(c, "execution", None)
                base["_numeric_score"] = c.score
                c._rc5_ob, c._rc5_ap = rc5_obligations(
                    c.sql, checklist, contract, idx, question, base)
            except Exception:
                c._rc5_ob, c._rc5_ap = {}, {}

        # Independent SEMANTIC consensus replaces raw execution-result majority:
        # one vote per independent generator lineage, grouped by normalized AST
        # fingerprint (+ result-signature guard), requiring >= 2 independent
        # lineages, and never overriding a candidate that semantically dominates
        # the consensus representative. When there is no valid independent
        # consensus, no winner is manufactured — selection continues on the
        # existing deterministic best-score path and the reason is recorded.
        cpick, cmeta, cmembers = consensus_select(
            pool, LOW_SCORE_THRESHOLD, _SOURCE_PRIORITY)
        for _k, _v in cmeta.items():
            meta[_k] = _v
        if cpick is not None:
            pick = cpick
            best_group = list(cmembers)
            meta["selection_reason"] = "consensus_group"
        else:
            groups = group_candidates(pool)

            def _fallback_key(grp):
                has_rows = any((c.row_count or 0) > 0 for c in grp)
                strong = max(c.score for c in grp) >= LOW_SCORE_THRESHOLD
                return (1 if (has_rows and strong) else 0,
                        sum(1 + c.score / 100.0 for c in grp),
                        max(c.score for c in grp))

            best_group = max(groups, key=_fallback_key)
            pick = max(best_group, key=_rank_key)
            meta["selection_reason"] = "best_scored_executed"
        meta["consensus_lineages"] = len(
            {getattr(c, "_lineage", None) for c in best_group})
        meta["consensus_collapsed_duplicates"] = \
            len(best_group) - len({getattr(c, "_lineage", None) for c in best_group})

        # Candidates blocked by the RC4 dominance gate below. A blocked
        # candidate must NOT be silently re-promoted by any later raw-score
        # override stage (spec: "do not fall through to another raw-score
        # override"); it is excluded from the direct/repair override and the
        # direct/repair preference that follow.
        blocked_overrides = []

        top = max(pool, key=_rank_key)
        if top is not pick and top not in best_group \
                and top.score >= pick.score + OVERRIDE_MARGIN:
            # RC4 — a higher validation score may NOT override the current
            # selection on its own; the proposed candidate must semantically
            # dominate it. Otherwise the override is blocked and the current
            # selection is kept, with the blocking obligation recorded.
            allowed, why, detail = override_dominates(
                getattr(top, "_profile", None) or {},
                getattr(pick, "_profile", None) or {})
            meta["override_trace"] = {
                "override_attempted": True,
                "current_candidate": pick.label,
                "proposed_candidate": top.label,
                "current_score": pick.score,
                "proposed_score": top.score,
                "obligations_lost": detail.get("obligations_lost", []),
                "obligations_gained": detail.get("obligations_gained", []),
                "new_semantic_defects": detail.get("new_semantic_defects", []),
                "semantic_dominance": bool(allowed),
                "override_allowed": bool(allowed),
                "override_block_reason": None if allowed else why,
            }
            if allowed:
                pick = top
                meta["selection_reason"] = "validation_score_override"
                best_group = [top]
            else:
                blocked_overrides.append(top)
                meta["override_blocked"] = True
                meta["override_block_reason"] = why

        # Direct/repair override: a non-fatal direct or repaired SQL that
        # outscores the consensus pick by DIRECT_OVERRIDE_MARGIN wins —
        # consensus between weaker candidates must not bury a stronger
        # independently-written query. A candidate the dominance gate just
        # blocked is excluded so it cannot re-enter here on raw score.
        best_direct = None
        for c in pool:
            if c.source in _DIRECT_SOURCES and c is not pick \
                    and c not in best_group and c not in blocked_overrides:
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
                    or c.source not in _DIRECT_SOURCES or c.score < pick.score \
                    or c in blocked_overrides:
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

        # RC5 — general semantic best-candidate ranking / tie-breaking. Runs
        # AFTER the provisional selection above. Among eligible, non-blocked
        # candidates, replace the pick with one that SEMANTICALLY DOMINATES it
        # (identity-preserving superset of satisfied request obligations, in the
        # fixed RC5 priority order). Numeric score never overrides a semantic
        # difference; an RC4-blocked candidate is excluded; genuinely
        # incomparable candidates are recorded, not silently overridden.
        rank_pool = [c for c in (eligible or viable) if c not in blocked_overrides]
        if len(rank_pool) > 1 and pick in rank_pool:
            def _rc5(c):
                ob = getattr(c, "_rc5_ob", None)
                ap = getattr(c, "_rc5_ap", None)
                if ob is None or ap is None:
                    base = dict(getattr(c, "_profile", None) or {})
                    base["_execution"] = getattr(c, "execution", None)
                    ob, ap = rc5_obligations(c.sql, checklist, contract, idx,
                                             question, base)
                ob["_numeric_score"] = c.score
                return ob, ap
            pick_ob, applies = _rc5(pick)
            best = None
            best_ob = pick_ob
            best_det = None
            incomparable = []
            for c in rank_pool:
                if c is pick:
                    continue
                ob, _ap = _rc5(c)
                dom, why, det = rc5_dominates(ob, pick_ob, applies)
                if dom:
                    if best is None or rc5_rank_tuple(ob) > rc5_rank_tuple(best_ob):
                        best, best_ob, best_det = c, ob, det
                elif det["obligations_gained"] and det["obligations_lost"]:
                    incomparable.append({"label": c.label, **det})
            if best is not None:
                meta["rc5_trace"] = {
                    "stage": "semantic_best_candidate",
                    "previous_pick": pick.label, "previous_score": pick.score,
                    "previous_profile": {k: pick_ob.get(k) for k in _rc5_keys()},
                    "new_pick": best.label, "new_score": best.score,
                    "new_profile": {k: best_ob.get(k) for k in _rc5_keys()},
                    "obligations_gained": best_det["obligations_gained"],
                    "obligations_lost": best_det["obligations_lost"],
                    "semantic_winner": best.label,
                    "incomparable": incomparable,
                    "numeric_score_consulted": False,
                    "tie_break_reason": "semantic_dominance",
                }
                pick = best
                meta["selection_reason"] = "semantic_best_candidate"
                best_group = [best]
            elif incomparable:
                meta["rc5_trace"] = {
                    "stage": "semantic_incomparable_controlled_fallback",
                    "kept": pick.label, "incomparable": incomparable,
                    "numeric_score_consulted": True,
                    "tie_break_reason": "semantic_incomparable_controlled_fallback",
                }

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
