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

from generation.sql_types import generated_sql, failed_sql
from generation.sql_clauses import (
    quote_ident,
    render_select,
    render_from_joins,
    render_where,
    render_anti_exists,
    render_universal,
    render_top_per_group,
    render_group_by,
    render_having,
    render_set_division,
    render_alias_select,
    render_alias_from_joins,
    render_alias_where,
    render_explicit_joins,
    render_null_filters,
    render_compound_filters,
    render_with_clause,
    render_order_by,
    render_limit,
)

__all__ = ["generate_sql"]


def _get(obj, key, default=None):
    """Read a field from either a dict or an object (plan / IR may be either)."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _non_scalar_params(params):
    """Return any parameters that are not bindable scalars. Guards against a
    column-ref dict / list leaking into a SQLite bind position."""
    return [p for p in params
            if isinstance(p, (dict, list, set, tuple, bytearray))]


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

    # Self-join / pair queries take a dedicated alias render path (built entirely
    # from the alias_* fields, ignoring the planner's join path). Non-alias
    # queries fall through to the normal path unchanged.
    if _get(ir, "aliases"):
        return _generate_alias_sql(ir)

    select = _get(ir, "select") or []
    aggregations = _get(ir, "aggregations") or []
    derived_relations = _get(ir, "derived_relations") or []
    main_from = _get(ir, "main_from")

    # Rule 2: nothing to project. A resolved single-table plan (a from_table and
    # no joins) is a "show all rows from <table>" request -> SELECT * FROM table.
    # A CTE-sourced query (main_from) with no projection means SELECT * FROM cte.
    # Truly invalid plans (no from_table) still decline with empty_select.
    select_all = False
    if not select and not aggregations:
        if main_from:
            select_all = True
        else:
            ft = _get(plan, "from_table")
            jns = _get(plan, "joins") or []
            if ft and not jns:
                from_sql = render_from_joins(ft, jns)
                diagnostics = {
                    "from_table": ft,
                    "join_count": 0,
                    "bridge_tables": list(_get(plan, "bridge_tables") or []),
                    "parameter_count": 0,
                    "clauses": ["select", "from"],
                    "select_all": True,
                }
                return generated_sql(f"SELECT * {from_sql}", [], diagnostics)
            return failed_sql("empty_select")

    distinct = bool(_get(ir, "distinct", False))
    filters = _get(ir, "filters") or []
    anti_exists = _get(ir, "anti_exists") or []
    universal = _get(ir, "universal") or []
    top_per_group = _get(ir, "top_per_group") or []
    explicit_joins = _get(ir, "explicit_joins") or []
    null_filters = _get(ir, "null_filters") or []
    compound_filters = _get(ir, "compound_filters") or []
    set_division = _get(ir, "set_division") or []
    group_by = _get(ir, "group_by") or []
    having = _get(ir, "having") or []
    order_by = _get(ir, "order_by") or []
    limit = _get(ir, "limit", None)

    from_table = _get(plan, "from_table")
    joins = _get(plan, "joins") or []
    bridge_tables = _get(plan, "bridge_tables") or []

    # Render clauses.
    select_sql = "SELECT *" if select_all else render_select(select, aggregations, distinct)
    # FROM precedence: explicit (outer) joins, else a derived relation (CTE) named
    # by main_from, else the resolved plan's joins. ON-condition params (rare)
    # come first in the parameter order.
    if explicit_joins:
        from_sql, ej_params = render_explicit_joins(explicit_joins)
    elif main_from:
        from_sql, ej_params = f"FROM {quote_ident(main_from)}", []
    else:
        from_sql, ej_params = render_from_joins(from_table, joins), []
    where_sql, where_params = render_where(filters)
    # Merge null tests, compound OR/AND groups, anti-join/NOT EXISTS, universal,
    # and top-per-group predicates into WHERE (after the plain filters). Parameter
    # order mirrors clause order: filters, compound, anti-exists, universal.
    nf_clauses = render_null_filters(null_filters)
    cf_clauses, cf_params = render_compound_filters(compound_filters)
    ax_clauses, ax_params = render_anti_exists(anti_exists)
    uni_clauses, uni_params = render_universal(universal)
    tpg_clauses, _tpg_params = render_top_per_group(top_per_group)
    extra_clauses = (list(nf_clauses) + list(cf_clauses) + list(ax_clauses)
                     + list(uni_clauses) + list(tpg_clauses))
    if extra_clauses:
        joined = " AND ".join(extra_clauses)
        where_sql = f"{where_sql} AND {joined}" if where_sql else f"WHERE {joined}"
        where_params = (list(where_params) + list(cf_params) + list(ax_params)
                        + list(uni_params))
    # Set division contributes GROUP BY columns and a HAVING comparison whose
    # right side is a scalar COUNT(DISTINCT ...) subquery.
    sd_havings, sd_params, sd_group_cols = render_set_division(set_division)
    group_for_render = list(group_by) + [g for g in sd_group_cols if g not in group_by]
    group_sql = render_group_by(group_for_render)
    having_sql, having_params = render_having(having)
    if sd_havings:
        joined_h = " AND ".join(sd_havings)
        having_sql = f"{having_sql} AND {joined_h}" if having_sql else f"HAVING {joined_h}"
        having_params = list(having_params) + list(sd_params)
    order_sql = render_order_by(order_by)
    limit_sql = render_limit(limit)

    # Derived relations render as a leading WITH clause; its params come first.
    with_sql, with_params = render_with_clause(derived_relations)

    # Assemble in fixed order; omit empties; single-space join; no trailing space.
    ordered = [select_sql, from_sql, where_sql, group_sql, having_sql, order_sql, limit_sql]
    main_sql = " ".join(part for part in ordered if part)
    sql = f"{with_sql} {main_sql}" if with_sql else main_sql

    # WITH params first, then ON-condition (FROM), then WHERE, then HAVING.
    params = (list(with_params) + list(ej_params) + list(where_params)
              + list(having_params))

    # Final guard: never let a non-scalar (e.g. a leaked column-ref dict) reach
    # the SQLite binder. Decline cleanly instead.
    bad = _non_scalar_params(params)
    if bad:
        return failed_sql("non_scalar_parameter",
                          diagnostics={"non_scalar": [str(b) for b in bad]})

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


def _generate_alias_sql(ir):
    """Render a self-join / pair query from the alias_* IR fields:
        SELECT [DISTINCT] <alias_select>
        FROM <t> AS <a1> JOIN <t> AS <a2> ON ... [more aliases]
        WHERE <alias_filters> [AND existence predicates]
    Existence predicates (anti_exists / universal / top_per_group) that
    reference aliases are merged into WHERE. Aggregations / GROUP BY / HAVING are
    not part of this path (alias+aggregate is deferred)."""
    aliases = _get(ir, "aliases") or []
    alias_select = _get(ir, "alias_select") or []
    if not aliases or not alias_select:
        return failed_sql("empty_alias_query")

    distinct = bool(_get(ir, "distinct", False))
    select_sql = render_alias_select(alias_select, distinct)
    from_sql, leftover = render_alias_from_joins(aliases, _get(ir, "alias_joins") or [])
    where_sql, where_params = render_alias_where(_get(ir, "alias_filters") or [], leftover)

    # Merge existence predicates (their correlation may reference aliases).
    ax_clauses, ax_params = render_anti_exists(_get(ir, "anti_exists") or [])
    uni_clauses, uni_params = render_universal(_get(ir, "universal") or [])
    tpg_clauses, _tpg = render_top_per_group(_get(ir, "top_per_group") or [])
    extra = list(ax_clauses) + list(uni_clauses) + list(tpg_clauses)
    if extra:
        joined = " AND ".join(extra)
        where_sql = f"{where_sql} AND {joined}" if where_sql else f"WHERE {joined}"
        where_params = list(where_params) + list(ax_params) + list(uni_params)

    # Derived relations (CTEs) may back the alias self-join (e.g. min/max over a
    # base relation); emit them as a leading WITH, params first.
    with_sql, with_params = render_with_clause(_get(ir, "derived_relations") or [])
    where_params = list(with_params) + list(where_params)

    bad = _non_scalar_params(where_params)
    if bad:
        return failed_sql("non_scalar_parameter",
                          diagnostics={"non_scalar": [str(b) for b in bad]})

    main_sql = " ".join(part for part in [select_sql, from_sql, where_sql] if part)
    sql = f"{with_sql} {main_sql}" if with_sql else main_sql
    diagnostics = {
        "alias_query": True,
        "alias_count": len([a for a in aliases if isinstance(a, dict)]),
        "parameter_count": len(where_params),
        "clauses": ["select", "from"] + (["where"] if where_sql else []),
    }
    return generated_sql(sql, list(where_params), diagnostics)