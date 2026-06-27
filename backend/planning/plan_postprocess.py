"""
plan_postprocess.py

Tier-2 question-aware plan adjustment: LEFT JOIN for "each/all/every X with count
of Y". A per-entity count over an INNER JOIN silently drops X rows that have zero
related Y; the correct shape preserves all X via LEFT JOIN from X out to Y.

Generic — keys off wording (each/all/every), the IR's COUNT aggregation + GROUP
BY, and the resolved join chain. No table, column, domain, or question hardcoded.
It mutates only the `join_type` of the relevant join steps and never changes the
selected columns, filters, SQL, or the schema graph.
"""

import re

__all__ = ["apply_left_join_for_each"]

_EACH = re.compile(r"\b(each|every|all)\b", re.I)


def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _lower(v):
    return str(v).strip().lower() if v is not None else ""


def apply_left_join_for_each(question, plan):
    """If the question asks for "each/all/every X with count of Y", set
    join_type='left' on the resolved join steps from the base entity X out to the
    counted entity Y. Returns the (possibly mutated) plan unchanged otherwise."""
    if not _EACH.search(question or ""):
        return plan
    if not _get(plan, "resolved", False):
        return plan

    ir = _get(plan, "ir") or {}
    aggregations = _get(ir, "aggregations") or []
    group_by = _get(ir, "group_by") or []
    joins = _get(plan, "joins") or []
    if not aggregations or not group_by or not joins:
        return plan

    # Counted entity Y: the table of a COUNT aggregation.
    counted = None
    for a in aggregations:
        if str(_get(a, "function", "")).upper() == "COUNT":
            counted = _lower(_get(a, "table"))
            if counted:
                break
    if not counted:
        return plan

    # Base entity X must be the root AND the GROUP BY entity, so LEFT preserves X.
    base = _lower(_get(plan, "from_table"))
    group_tables = {_lower(_get(g, "table")) for g in group_by}
    if not base or base not in group_tables:
        return plan

    # Set join_type='left' on every step from the root up to and including the
    # one that reaches Y (covers a direct join and any bridge X -> Z -> Y).
    for step in joins:
        if not isinstance(step, dict):
            continue
        step["join_type"] = "left"
        if _lower(step.get("to_table")) == counted:
            break

    return plan
