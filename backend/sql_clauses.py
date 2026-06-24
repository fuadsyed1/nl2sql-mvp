"""
sql_clauses.py

Phase 7, step 2 — pure SQL clause renderers.

Each function renders one clause from decomposed IR/plan fragments (lists/dicts),
returning a string fragment and, for value-bearing clauses, a params list. No
function takes the plan object, reads the graph, resolves joins, executes SQL,
or calls a model. Filter/having values are parameterized; LIMIT is an inlined
validated integer (decision locked for Phase 7).
"""

__all__ = [
    "quote_ident",
    "qualify",
    "qualify_ref",
    "quote_qualified",
    "render_select",
    "render_from_joins",
    "render_where",
    "render_group_by",
    "render_having",
    "render_order_by",
    "render_limit",
]

_SYMBOLIC = {
    "=": "=", "!=": "!=", "<>": "!=",
    "<": "<", ">": ">", "<=": "<=", ">=": ">=",
    "LIKE": "LIKE",
}

_JOIN_KEYWORDS = {
    "inner": "INNER JOIN",
    "left": "LEFT JOIN",
    "right": "RIGHT JOIN",
    "full": "FULL JOIN",
}


# ---------------------------------------------------------------------------
# Identifier quoting
# ---------------------------------------------------------------------------
def quote_ident(name):
    """Double-quote an identifier, escaping embedded quotes."""
    return '"' + str(name).replace('"', '""') + '"'


def qualify(table, column):
    """Render a table-qualified column. A column of '*' yields "table".*."""
    if column is not None and str(column).strip() == "*":
        return f"{quote_ident(table)}.*"
    return f"{quote_ident(table)}.{quote_ident(column)}"


def qualify_ref(ref):
    """Qualify a {table, column} reference dict."""
    return qualify(ref.get("table"), ref.get("column"))


def quote_qualified(dotted):
    """Quote a dotted identifier string: 'owners.lastname' -> "owners"."lastname"."""
    text = str(dotted)
    if "." in text:
        table, column = text.split(".", 1)
        return qualify(table, column)
    return quote_ident(text)


# ---------------------------------------------------------------------------
# Predicate helper (shared by WHERE and HAVING)
# ---------------------------------------------------------------------------
def _normalize_op(op):
    return str(op or "").strip().upper()


def _render_predicate(ref_sql, op, value):
    """Return (predicate_str, params) for one comparison."""
    op = _normalize_op(op)
    if op in ("IS NULL", "IS NOT NULL"):
        return f"{ref_sql} {op}", []
    if op == "IN":
        vals = list(value) if isinstance(value, (list, tuple)) else [value]
        placeholders = ", ".join(["?"] * len(vals))
        return f"{ref_sql} IN ({placeholders})", vals
    sym = _SYMBOLIC.get(op, op)
    return f"{ref_sql} {sym} ?", [value]


def _coerce_connector(value):
    """Return 'AND'/'OR' if `value` is a recognized connector, else '' (empty),
    so callers can fall back to another source before defaulting to 'AND'."""
    text = str(value).strip().upper() if value is not None else ""
    return text if text in ("AND", "OR") else ""


def _chain(entries, ref_of):
    """Chain predicates with their connectors. entries: list of dicts carrying
    op/value/connector; ref_of(entry) -> the left-hand reference SQL.

    Connector placement is tolerant: the extractor stores the connector on the
    PREVIOUS filter (the one it connects from), so for predicate i > 0 we prefer
    entries[i-1]["connector"], then fall back to entries[i]["connector"], and
    normalize anything missing/None/invalid to 'AND'. No invalid token (e.g.
    'NONE') can ever be emitted.
    """
    parts = []
    params = []
    for i, e in enumerate(entries):
        pred, p = _render_predicate(ref_of(e), e.get("op"), e.get("value"))
        params.extend(p)
        if i == 0:
            parts.append(pred)
        else:
            prev = _coerce_connector(entries[i - 1].get("connector"))
            connector = prev or _coerce_connector(entries[i].get("connector")) or "AND"
            parts.append(f"{connector} {pred}")
    return " ".join(parts), params


# ---------------------------------------------------------------------------
# Clause renderers
# ---------------------------------------------------------------------------
def _render_aggregation(agg):
    fn = str(agg.get("function", "")).upper()
    col = agg.get("column")
    arg = "*" if (col is None or str(col).strip() == "*") else qualify(agg.get("table"), col)
    expr = f"{fn}({arg})"
    alias = agg.get("alias")
    if alias:
        expr += f" AS {quote_ident(alias)}"
    return expr


def _render_select_column(ref):
    expr = qualify_ref(ref)
    alias = ref.get("alias")
    if alias:
        expr += f" AS {quote_ident(alias)}"
    return expr


def render_select(select=None, aggregations=None, distinct=False):
    """SELECT [DISTINCT] cols..., aggregations... — select columns first, then
    aggregation expressions, each in list order."""
    exprs = [_render_select_column(r) for r in (select or [])]
    exprs += [_render_aggregation(a) for a in (aggregations or [])]
    keyword = "SELECT DISTINCT" if distinct else "SELECT"
    return f"{keyword} " + ", ".join(exprs)


def render_from_joins(from_table, joins=None):
    """FROM <root> then one '<JOIN_TYPE> <to> ON <from> = <to>' per step."""
    sql = f"FROM {quote_ident(from_table)}"
    for j in (joins or []):
        kw = _JOIN_KEYWORDS.get(str(j.get("join_type", "inner")).lower(), "INNER JOIN")
        on = f'{qualify(j["from_table"], j["from_column"])} = {qualify(j["to_table"], j["to_column"])}'
        sql += f' {kw} {quote_ident(j["to_table"])} ON {on}'
    return sql


def render_where(filters=None):
    """Return (clause, params). Empty filters -> ('', [])."""
    filters = filters or []
    if not filters:
        return "", []
    body, params = _chain(filters, qualify_ref)
    return "WHERE " + body, params


def render_group_by(group_by=None):
    cols = [qualify_ref(g) for g in (group_by or [])]
    if not cols:
        return ""
    return "GROUP BY " + ", ".join(cols)


def render_having(having=None):
    """Return (clause, params). HAVING references aggregation aliases."""
    having = having or []
    if not having:
        return "", []
    body, params = _chain(having, lambda h: quote_ident(h.get("aggregation_alias")))
    return "HAVING " + body, params


def render_order_by(order_by=None):
    """ORDER BY of qualified columns and/or aggregation aliases, with ASC/DESC."""
    order_by = order_by or []
    if not order_by:
        return ""
    parts = []
    for o in order_by:
        direction = str(o.get("direction", "ASC")).upper()
        if direction not in ("ASC", "DESC"):
            direction = "ASC"
        if o.get("aggregation_alias"):
            ref = quote_ident(o["aggregation_alias"])
        else:
            ref = qualify(o.get("table"), o.get("column"))
        parts.append(f"{ref} {direction}")
    return "ORDER BY " + ", ".join(parts)


def render_limit(limit=None):
    """Inline validated integer literal; '' when None."""
    if limit is None:
        return ""
    return f"LIMIT {int(limit)}"