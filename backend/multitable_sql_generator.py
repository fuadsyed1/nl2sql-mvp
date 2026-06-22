"""
multitable_sql_generator.py

Phase 7, step 3 — convert a ResolvedQueryPlan into a GeneratedSQL object.

generate_sql(plan):
  * declines unresolved plans (unresolved_plan),
  * declines when there is nothing to project (empty_select: no select columns
    AND no aggregations),
  * otherwise renders the clauses in the fixed order
    SELECT -> FROM/JOIN -> WHERE -> GROUP BY -> HAVING -> ORDER BY -> LIMIT,
    joining non-empty clauses with a single space (no trailing spaces).

WHERE params come first, then HAVING params. The plan and its embedded IR are
read-only. This is the new multi-table path and does NOT touch the legacy
sql_generator.py or /query. It inspects no schema graph, resolves no joins, and
executes nothing.
"""

from sql_types import generated_sql, failed_sql
from sql_clauses import (
    render_select,
    render_from_joins,
    render_where,
    render_group_by,
    render_having,
    render_order_by,
    render_limit,
)

__all__ = ["generate_sql"]


def _get(obj, key, default=None):
    """Read a field from either a dict or an object (plan / IR may be either)."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def generate_sql(plan):
    """ResolvedQueryPlan -> GeneratedSQL (success or structured decline)."""
    # Rule 1: unresolved plan -> decline.
    if not _get(plan, "resolved", False):
        diagnostics = {}
        plan_reason = _get(plan, "reason")
        if plan_reason:
            diagnostics["plan_reason"] = plan_reason
        return failed_sql("unresolved_plan", diagnostics=diagnostics)

    ir = _get(plan, "ir") or {}
    select = _get(ir, "select") or []
    aggregations = _get(ir, "aggregations") or []

    # Rule 2: nothing to project -> decline.
    if not select and not aggregations:
        return failed_sql("empty_select")

    distinct = bool(_get(ir, "distinct", False))
    filters = _get(ir, "filters") or []
    group_by = _get(ir, "group_by") or []
    having = _get(ir, "having") or []
    order_by = _get(ir, "order_by") or []
    limit = _get(ir, "limit", None)

    from_table = _get(plan, "from_table")
    joins = _get(plan, "joins") or []
    bridge_tables = _get(plan, "bridge_tables") or []

    # Render clauses.
    select_sql = render_select(select, aggregations, distinct)
    from_sql = render_from_joins(from_table, joins)
    where_sql, where_params = render_where(filters)
    group_sql = render_group_by(group_by)
    having_sql, having_params = render_having(having)
    order_sql = render_order_by(order_by)
    limit_sql = render_limit(limit)

    # Assemble in fixed order; omit empties; single-space join; no trailing space.
    ordered = [select_sql, from_sql, where_sql, group_sql, having_sql, order_sql, limit_sql]
    sql = " ".join(part for part in ordered if part)

    # WHERE params first, then HAVING params.
    params = list(where_params) + list(having_params)

    join_count = len(joins)
    clauses = ["select", "from"]
    if join_count:
        clauses.append("join")
    if where_sql:
        clauses.append("where")
    if group_sql:
        clauses.append("group_by")
    if having_sql:
        clauses.append("having")
    if order_sql:
        clauses.append("order_by")
    if limit_sql:
        clauses.append("limit")

    diagnostics = {
        "from_table": from_table,
        "join_count": join_count,
        "bridge_tables": list(bridge_tables),
        "parameter_count": len(params),
        "clauses": clauses,
    }

    return generated_sql(sql, params, diagnostics)