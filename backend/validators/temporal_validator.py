"""
validators/temporal_validator.py

Final temporal patch — latest-event QUALIFICATION validator.

Distinguishes two meanings that generation keeps conflating:

  "whose most recent X was Y"   (qualifier_timing = after_extremum)
      -> select the extremum event across ALL of the entity's events FIRST,
         then test whether THAT event satisfies the qualifier;
  "most recent Y X"             (qualifier_timing = before_extremum)
      -> filtering to qualifying events before the extremum is intended
         (never validated here).

For after_extremum requirements the validator inspects every scope that
computes the extremum of the event's order column — MAX/MIN aggregates
(correlated subquery, grouped CTE, same-scope HAVING) and ROW_NUMBER windows
ordered by it — and checks whether the qualifier column PROVABLY filters that
scope's rows (its own WHERE/JOIN ON literal filters, or those of a source
scope feeding it). If EVERY extremum computation is qualifier-filtered, the
SQL finds the latest QUALIFYING event instead of testing the latest event —
fatal. Accepted shapes (never flagged): correlated MAX over all events with
the qualifier applied outside, ROW_NUMBER over all events with the qualifier
in an outer scope, an all-event extremum CTE joined back, and NOT-EXISTS-a-
later-event (no extremum aggregate at all).

Fatal ONLY when the requirement is high-confidence after_extremum AND the
contamination is provable from the AST; mixed/unresolved shapes stay
warnings. No table, column, status value, or benchmark name is hardcoded.
"""

from dataclasses import dataclass, field

from sqlglot import exp

from sql_analysis import ast_tools as at

__all__ = ["TemporalValidation", "validate_temporal"]

_FATAL_MSG = ("temporal violation: the qualifying condition is applied "
              "before selecting the latest event, so the SQL finds the "
              "latest qualifying event instead of checking whether the "
              "latest event qualifies")


@dataclass
class TemporalValidation:
    fatal: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    checks: dict = field(default_factory=dict)
    skipped: str | None = None


def _has_qualifier_filter(scope, qtable, qcolumn, idx, _depth=0):
    """True when this scope's row filters (WHERE / JOIN ON), or those of a
    scope FEEDING it, provably compare qualifier column against literals."""
    for t, c in at.literal_filters(scope, idx):
        if t == qtable and c == qcolumn:
            return True
    if _depth >= 3:
        return False
    for src in at.scope_selected_sources(scope).values():
        if isinstance(src, at.Scope) \
                and _has_qualifier_filter(src, qtable, qcolumn, idx,
                                          _depth + 1):
            return True
    return False


def _is_row_number(fn) -> bool:
    key = (getattr(fn, "key", "") or "").lower().replace("_", "")
    return key == "rownumber"


def _extremum_scopes(parsed, req, idx):
    """Scopes that compute the extremum of the event's order column:
    MAX/MIN(<order column>) aggregates or ROW_NUMBER() windows ordered by
    it. Returns a list of Scope objects (deduped)."""
    order_t = req.order_table or req.event_table
    order_c = req.order_column
    agg_name = "min" if req.direction == "earliest" else "max"
    hits = []
    for scope in parsed.scopes:
        found = False
        for node in at.scope_aggregates(scope):
            if at.aggregate_name(node) != agg_name:
                continue
            cols = at.aggregate_arg_columns(node)
            if cols and any(
                    at.trace_column(scope, c, idx).is_physical(order_t, order_c)
                    for c in cols):
                found = True
                break
        if not found:
            for node in at.scope_nodes(scope):
                if not isinstance(node, exp.Window):
                    continue
                if not _is_row_number(node.this):
                    continue
                order = node.args.get("order")
                ocols = (list(order.find_all(exp.Column))
                         if order is not None else [])
                if any(at.trace_column(scope, c, idx)
                       .is_physical(order_t, order_c) for c in ocols):
                    found = True
                    break
        if found:
            hits.append(scope)
    return hits


def validate_temporal(contract, sql, idx=None) -> TemporalValidation:
    """Validate one SQL string against every actionable (high-confidence,
    after_extremum) temporal requirement. Never raises; every uncertain path
    degrades to skip/warning."""
    v = TemporalValidation()
    if contract is None:
        v.skipped = "no typed contract"
        return v
    reqs = list(getattr(contract, "actionable_temporal", []) or [])
    if not reqs:
        v.skipped = "no actionable temporal requirement"
        return v

    parsed = at.parse_sql(sql)
    if not parsed.ok:
        v.skipped = f"SQL not analyzable: {parsed.error}"
        return v

    many = len(reqs) > 1
    for n, req in enumerate(reqs, start=1):
        tag = f" [temporal {n}/{len(reqs)}]" if many else ""
        rc = {"event": req.event_table,
              "order": f"{req.order_table or req.event_table}."
                       f"{req.order_column}",
              "qualifier": f"{req.qualifier_table or req.event_table}."
                           f"{req.qualifier_column}"}
        try:
            scopes = _extremum_scopes(parsed, req, idx)
            qtable = req.qualifier_table or req.event_table
            contaminated = [s for s in scopes if _has_qualifier_filter(
                s, qtable, req.qualifier_column, idx)]
            rc["extremum_scopes"] = len(scopes)
            rc["contaminated_scopes"] = len(contaminated)
            if scopes and len(contaminated) == len(scopes):
                v.fatal.append(
                    _FATAL_MSG + tag
                    + f" (every {('MIN' if req.direction == 'earliest' else 'MAX')}"
                      f"/ROW_NUMBER over "
                      f"{rc['order']} is computed from rows filtered by "
                      f"{rc['qualifier']})")
            elif contaminated:
                v.warnings.append(
                    f"temporal note{tag}: one extremum over {rc['order']} is "
                    f"computed from qualifier-filtered rows, but an "
                    f"unfiltered extremum also exists — verify which one "
                    f"drives the qualification")
            # no extremum aggregate at all: NOT-EXISTS-later-event and other
            # shapes are legitimate — never fatal, nothing to prove
        except Exception as exc:               # analysis bug → advisory only
            rc["error"] = f"{type(exc).__name__}: {exc}"
            v.warnings.append(f"temporal validation incomplete{tag}: "
                              f"{type(exc).__name__}: {exc}")
        v.checks[f"temporal_{n}"] = rc

    v.checks["fatal_count"] = len(v.fatal)
    return v
