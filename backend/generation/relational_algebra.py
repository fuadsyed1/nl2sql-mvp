"""
relational_algebra.py

Deterministic relational-algebra rendering from a resolved query plan + its
embedded IR. No SQL-string parsing and no model call. Operators (innermost ->
outermost): joins (⋈ / ⟕ / ⟖ / ⟗) -> σ selection -> γ group/aggregation ->
π projection -> τ sort -> LIMIT suffix. The outer π is always emitted.

Columns are bare (e.g. game_id) for single-table queries and table-qualified
(e.g. owners.owner_id) when joins are present, matching the requested format.
Generic: reads only plan/IR structure — no table, column, dataset, or question
hardcoding. On anything it cannot express it returns a fixed fallback string.
"""

__all__ = ["to_relational_algebra"]

_UNAVAILABLE = "Relational algebra unavailable for this query."

_JOIN_SYM = {"inner": "⋈", "left": "⟕", "right": "⟖", "full": "⟗"}
_EXPR_PREC = {"*": 2, "/": 2, "+": 1, "-": 1}


def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _qualified(qualify, table, column):
    if column is not None and str(column).strip() == "*":
        return f"{table}.*" if qualify else "*"
    return f"{table}.{column}" if qualify else f"{column}"


def _ref(qualify, entry):
    return _qualified(qualify, _get(entry, "table"), _get(entry, "column"))


def _expr_str(node, qualify, parent_prec=0):
    if not isinstance(node, dict):
        return str(node)
    if "col" in node:
        c = node["col"]
        return _qualified(qualify, c.get("table"), c.get("column"))
    if "lit" in node:
        v = node["lit"]
        return repr(v) if isinstance(v, float) else str(v)
    if "op" in node:
        op = str(node["op"])
        prec = _EXPR_PREC.get(op, 0)
        left = _expr_str(node.get("left"), qualify, prec)
        right = _expr_str(node.get("right"), qualify, prec)
        s = f"{left} {op} {right}"
        return f"({s})" if prec < parent_prec else s
    return "?"


def _agg_str(qualify, agg):
    fn = str(_get(agg, "function", "")).upper()
    expr_node = _get(agg, "expr")
    if expr_node is not None:
        arg = _expr_str(expr_node, qualify)
    else:
        col = _get(agg, "column")
        if col is None or str(col).strip() == "*":
            arg = "*"
        else:
            arg = _qualified(qualify, _get(agg, "table"), col)
    out = f"{fn}({arg})"
    alias = _get(agg, "alias")
    if alias:
        out += f"→{alias}"
    return out


def _predicate(qualify, f):
    lhs = _ref(qualify, f)
    op = str(_get(f, "op", "")).strip().upper()
    if op in ("IS NULL", "IS NOT NULL"):
        return f"{lhs} {op}"
    vref = _get(f, "value_ref")
    if vref:
        return f"{lhs} {op} {_qualified(qualify, vref.get('table'), vref.get('column'))}"
    return f"{lhs} {op} {_get(f, 'value')}"


def _selection(qualify, filters):
    parts = []
    for i, f in enumerate(filters):
        pred = _predicate(qualify, f)
        if i == 0:
            parts.append(pred)
        else:
            prev = str(_get(filters[i - 1], "connector", "") or "").strip().upper()
            conn = prev if prev in ("AND", "OR") else "AND"
            parts.append(f"{conn} {pred}")
    return " ".join(parts)


def _join_chain(qualify, from_table, joins):
    acc = str(from_table)
    for i, j in enumerate(joins):
        sym = _JOIN_SYM.get(str(_get(j, "join_type", "inner")).lower(), "⋈")
        cond = (f"{_get(j, 'from_table')}.{_get(j, 'from_column')} = "
                f"{_get(j, 'to_table')}.{_get(j, 'to_column')}")
        left = f"({acc})" if i > 0 else acc
        acc = f"{left} {sym} {cond} {_get(j, 'to_table')}"
    return acc


def _order_spec(qualify, order_by):
    parts = []
    for o in order_by:
        direction = str(_get(o, "direction", "ASC")).upper()
        if direction not in ("ASC", "DESC"):
            direction = "ASC"
        alias = _get(o, "aggregation_alias")
        ref = alias if alias else _ref(qualify, o)
        parts.append(f"{ref} {direction}")
    return ", ".join(parts)


def to_relational_algebra(plan):
    """Return a relational-algebra string for a resolved plan, or the fixed
    fallback string on unresolved/unsupported shapes. Never raises."""
    try:
        if not _get(plan, "resolved", False):
            return _UNAVAILABLE

        ir = _get(plan, "ir") or {}
        select = list(_get(ir, "select") or [])
        aggregations = list(_get(ir, "aggregations") or [])
        if not select and not aggregations:
            return _UNAVAILABLE

        from_table = _get(plan, "from_table")
        joins = list(_get(plan, "joins") or [])
        qualify = bool(joins)

        filters = list(_get(ir, "filters") or [])
        group_by = list(_get(ir, "group_by") or [])
        order_by = list(_get(ir, "order_by") or [])
        limit = _get(ir, "limit")

        expr = _join_chain(qualify, from_table, joins)

        if filters:
            expr = f"σ {_selection(qualify, filters)} ({expr})"

        if group_by or aggregations:
            gcols = ", ".join(_ref(qualify, g) for g in group_by)
            aggs = ", ".join(_agg_str(qualify, a) for a in aggregations)
            head = "; ".join(p for p in (gcols, aggs) if p)
            expr = f"γ {head} ({expr})"

        proj = [_ref(qualify, s) for s in select]
        proj += [_agg_str(qualify, a) for a in aggregations]
        expr = f"π {', '.join(proj)} ({expr})"

        if order_by:
            expr = f"τ {_order_spec(qualify, order_by)} ({expr})"
        if limit is not None:
            expr = f"{expr} LIMIT {int(limit)}"

        return expr
    except Exception:
        return _UNAVAILABLE
