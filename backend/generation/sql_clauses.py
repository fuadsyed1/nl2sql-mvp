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
    "render_anti_exists",
    "render_universal",
    "render_top_per_group",
    "render_group_by",
    "render_having",
    "render_set_division",
    "render_alias_select",
    "render_alias_from_joins",
    "render_alias_where",
    "render_explicit_joins",
    "render_null_filters",
    "render_compound_filters",
    "render_with_clause",
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


def _render_predicate(ref_sql, op, value, value_ref=None):
    """Return (predicate_str, params) for one comparison.

    When `value_ref` ({table, column}) is given, the right-hand side is rendered
    as that qualified column (a column-to-column comparison) with NO parameter."""
    op = _normalize_op(op)
    if op in ("IS NULL", "IS NOT NULL"):
        return f"{ref_sql} {op}", []
    if value_ref:
        sym = _SYMBOLIC.get(op, op)
        return f"{ref_sql} {sym} {qualify_ref(value_ref)}", []
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


def _chain(entries, render_one):
    """Chain predicates with their connectors. entries: list of dicts carrying a
    connector; render_one(entry) -> (predicate_sql, params).

    Connector placement is tolerant: the extractor stores the connector on the
    PREVIOUS filter (the one it connects from), so for predicate i > 0 we prefer
    entries[i-1]["connector"], then fall back to entries[i]["connector"], and
    normalize anything missing/None/invalid to 'AND'. No invalid token (e.g.
    'NONE') can ever be emitted.
    """
    parts = []
    params = []
    for i, e in enumerate(entries):
        pred, p = render_one(e)
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
_EXPR_PREC = {"*": 2, "/": 2, "+": 1, "-": 1}


def _render_expr(node, parent_prec=0):
    """Render a small arithmetic expression tree:
        {"col": {table, column}} | {"lit": <number>} |
        {"op": "*|/|+|-", "left": <node>, "right": <node>}
    A binary node is parenthesized only when its operator binds looser than its
    parent (so  a * b * (1 - c / 100.0)  comes out correctly)."""
    if not isinstance(node, dict):
        return str(node)
    if "col" in node:
        return qualify_ref(node["col"])
    if "lit" in node:
        v = node["lit"]
        return repr(v) if isinstance(v, float) else str(v)
    if "op" in node:
        op = str(node["op"])
        prec = _EXPR_PREC.get(op, 0)
        left = _render_expr(node.get("left"), prec)
        right = _render_expr(node.get("right"), prec)
        rendered = f"{left} {op} {right}"
        return f"({rendered})" if prec < parent_prec else rendered
    return ""


def _render_aggregation(agg):
    fn = str(agg.get("function", "")).upper()
    expr_node = agg.get("expr")
    if expr_node is not None:
        arg = _render_expr(expr_node)
    else:
        col = agg.get("column")
        arg = "*" if (col is None or str(col).strip() == "*") else qualify(agg.get("table"), col)
    if agg.get("distinct") and arg != "*":
        expr = f"{fn}(DISTINCT {arg})"
    else:
        expr = f"{fn}({arg})"
    alias = agg.get("alias")
    if alias:
        expr += f" AS {quote_ident(alias)}"
    return expr


def _render_simple_aggregate(a):
    """Render a bare aggregate (no alias): FN([DISTINCT] arg). Used by
    set_division's left expression and scalar right subquery."""
    fn = str(a.get("function", "COUNT")).upper()
    col = a.get("column")
    arg = "*" if (col is None or str(col).strip() == "*") else qualify(a.get("table"), col)
    if a.get("distinct") and arg != "*":
        return f"{fn}(DISTINCT {arg})"
    return f"{fn}({arg})"


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
    body, params = _chain(
        filters,
        lambda f: _render_predicate(qualify_ref(f), f.get("op"),
                                    f.get("value"), f.get("value_ref")),
    )
    return "WHERE " + body, params


# ---------------------------------------------------------------------------
# Anti-join / NOT EXISTS subqueries
# ---------------------------------------------------------------------------
def _render_subquery_predicate(p):
    """One predicate inside an anti-exists subquery. Supports:
      {"left":{t,c}, "op":op, "right":{t,c}}        -> col op col   (no param)
      {"left":{t,c}, "op":op, "value":v}            -> col op ?      (param)
      {"left":{t,c}, "op":"IS NULL"|"IS NOT NULL"}  -> col IS [NOT] NULL
    Returns (sql, params) or (None, []) for a malformed predicate."""
    if not isinstance(p, dict) or not isinstance(p.get("left"), dict):
        return None, []
    op = _normalize_op(p.get("op"))
    left = qualify_ref(p["left"])
    if op in ("IS NULL", "IS NOT NULL"):
        return f"{left} {op}", []
    right = p.get("right")
    if isinstance(right, dict) and right.get("table") and right.get("column"):
        sym = _SYMBOLIC.get(op, op)
        return f"{left} {sym} {qualify_ref(right)}", []
    sym = _SYMBOLIC.get(op or "=", op or "=")
    return f"{left} {sym} ?", [p.get("value")]


def _subquery_predicates(spec):
    """Collected predicate list, tolerating the keys where / join_conditions /
    filters (any subset), in that order."""
    preds = []
    for key in ("join_conditions", "where", "filters"):
        items = spec.get(key)
        if isinstance(items, list):
            preds.extend(items)
    return preds


def _render_subquery_select(spec):
    """Render the inner 'SELECT 1 FROM <target> [JOIN ...] [WHERE ...]' of an
    existence subquery, or (None, []) if it has no target_table. Shared by
    anti_exists, universal must_exist/bad_match, and EXISTS/NOT EXISTS conditions."""
    if not isinstance(spec, dict):
        return None, []
    target = spec.get("target_table")
    if not target:
        return None, []

    # Build the FROM clause, but NEVER join a table that is already present
    # (the target or an already-joined table). A repeated join to the same bare
    # table name produces an ambiguous-column SQL error; instead we drop the
    # duplicate join and fold its ON equality into the WHERE predicates, so the
    # intended correlation is preserved without a second copy of the table.
    from_sql = f"FROM {quote_ident(target)}"
    present = {str(target).strip().lower()}
    folded = []
    for j in spec.get("joins") or []:
        if not isinstance(j, dict) or not j.get("to_table"):
            continue
        to_l = str(j["to_table"]).strip().lower()
        if to_l in present:
            folded.append({
                "left": {"table": j.get("from_table"), "column": j.get("from_column")},
                "op": "=",
                "right": {"table": j.get("to_table"), "column": j.get("to_column")},
            })
            continue
        kw = _JOIN_KEYWORDS.get(str(j.get("join_type", "inner")).lower(), "INNER JOIN")
        on = (f'{qualify(j["from_table"], j["from_column"])} = '
              f'{qualify(j["to_table"], j["to_column"])}')
        from_sql += f' {kw} {quote_ident(j["to_table"])} ON {on}'
        present.add(to_l)

    bodies, params = [], []
    for p in folded + _subquery_predicates(spec):
        sql, prm = _render_subquery_predicate(p)
        if sql is None:
            continue
        bodies.append(sql)
        params.extend(prm)

    where = (" WHERE " + " AND ".join(bodies)) if bodies else ""
    return f"SELECT 1 {from_sql}{where}", params


def _render_anti_exists_one(spec):
    """Render one spec to ('NOT EXISTS (...)', params) or (None, []) if invalid
    (no target_table)."""
    sub, params = _render_subquery_select(spec)
    if sub is None:
        return None, []
    return f"NOT EXISTS ({sub})", params


def render_anti_exists(anti_exists=None):
    """Return (clauses, params): a list of 'NOT EXISTS (...)' strings and their
    ordered parameters. Malformed/empty specs are skipped."""
    clauses, params = [], []
    for spec in anti_exists or []:
        sql, prm = _render_anti_exists_one(spec)
        if sql is None:
            continue
        clauses.append(sql)
        params.extend(prm)
    return clauses, params


# ---------------------------------------------------------------------------
# Universal quantification ("for all" / "only") via nested NOT EXISTS
# ---------------------------------------------------------------------------
def _render_exists_condition(cond):
    """One inner condition of a universal body, returns (sql, params):
      {"exists": subspec}      -> 'EXISTS (SELECT 1 ...)'
      {"not_exists": subspec}  -> 'NOT EXISTS (SELECT 1 ...)'
      {left, op, right|value}  -> a plain comparison predicate."""
    if not isinstance(cond, dict):
        return None, []
    if isinstance(cond.get("exists"), dict):
        sub, prm = _render_subquery_select(cond["exists"])
        return (f"EXISTS ({sub})", prm) if sub else (None, [])
    if isinstance(cond.get("not_exists"), dict):
        sub, prm = _render_subquery_select(cond["not_exists"])
        return (f"NOT EXISTS ({sub})", prm) if sub else (None, [])
    return _render_subquery_predicate(cond)


def _render_universal_one(spec):
    """Render one universal spec, or (None, []) if malformed.

    'bad_match' without a domain_table -> single NOT EXISTS (the 'only' form).
    Otherwise -> NOT EXISTS over the domain whose body is the negation of the
    per-element requirement: must_exist (shorthand) and/or an explicit `inner`
    list of EXISTS / NOT EXISTS / comparison conditions, all ANDed."""
    if not isinstance(spec, dict):
        return None, []

    bad = spec.get("bad_match")
    if not spec.get("domain_table") and isinstance(bad, dict) and bad.get("target_table"):
        sub, prm = _render_subquery_select(bad)
        return (f"NOT EXISTS ({sub})", prm) if sub else (None, [])

    domain = spec.get("domain_table")
    if not domain:
        return None, []

    bodies, params = [], []
    for p in spec.get("domain_filters") or []:
        sql, prm = _render_subquery_predicate(p)
        if sql is None:
            continue
        bodies.append(sql)
        params.extend(prm)

    must = spec.get("must_exist")
    if isinstance(must, dict) and must.get("target_table"):
        sub, prm = _render_subquery_select(must)
        if sub:
            bodies.append(f"NOT EXISTS ({sub})")
            params.extend(prm)

    for cond in spec.get("inner") or []:
        sql, prm = _render_exists_condition(cond)
        if sql is None:
            continue
        bodies.append(sql)
        params.extend(prm)

    if not bodies:
        return None, []

    from_sql = f"FROM {quote_ident(domain)}"
    alias = spec.get("domain_alias")
    if alias:
        from_sql += f" AS {quote_ident(alias)}"
    return f"NOT EXISTS (SELECT 1 {from_sql} WHERE {' AND '.join(bodies)})", params


def render_universal(universal=None):
    """Return (clauses, params) for universal-quantification predicates. Empty/
    malformed specs are skipped."""
    clauses, params = [], []
    for spec in universal or []:
        sql, prm = _render_universal_one(spec)
        if sql is None:
            continue
        clauses.append(sql)
        params.extend(prm)
    return clauses, params


# ---------------------------------------------------------------------------
# Top-per-group / ranking-within-group (correlated, no parameters)
# ---------------------------------------------------------------------------
def _cmp_for_direction(direction):
    """'asc'/'ascending' -> '<' (rank from smallest); otherwise '>' (largest)."""
    return "<" if str(direction or "desc").strip().lower().startswith("asc") else ">"


def _render_top_per_group_one(spec, idx):
    """Render one grouped-extrema/ranking predicate, or None if malformed.

    rank 1 -> NOT EXISTS(... a strictly-better row in the same partition).
    rank N -> (SELECT COUNT(DISTINCT order) ... strictly-better) = N-1.
    Self-correlation uses a unique inner alias so the same table can reference
    its own outer row. No parameters (rank is an inlined validated integer)."""
    if not isinstance(spec, dict):
        return None
    table = spec.get("table")
    ob = spec.get("order_by") or {}
    order_col = ob.get("column")
    if not table or not order_col:
        return None
    order_tbl = ob.get("table") or table
    cmp = _cmp_for_direction(ob.get("direction"))

    try:
        rank = int(spec.get("rank", 1))
    except (TypeError, ValueError):
        rank = 1
    if rank < 1:
        rank = 1

    method = str(spec.get("method") or
                 ("not_exists" if rank == 1 else "count_distinct")).strip().lower()
    if rank > 1:
        method = "count_distinct"   # NOT EXISTS only expresses the rank-1 extremum

    alias = f"{table}__g{idx}"
    eqs = []
    for pc in spec.get("partition_by") or []:
        if not isinstance(pc, dict) or not pc.get("column"):
            continue
        pcol = pc["column"]
        ptbl = pc.get("table") or table
        eqs.append(f"{qualify(alias, pcol)} = {qualify(ptbl, pcol)}")
    better = f"{qualify(alias, order_col)} {cmp} {qualify(order_tbl, order_col)}"
    inner_where = " AND ".join(eqs + [better])
    from_inner = f"FROM {quote_ident(table)} AS {quote_ident(alias)}"

    if method == "not_exists":
        return f"NOT EXISTS (SELECT 1 {from_inner} WHERE {inner_where})"
    return (f"(SELECT COUNT(DISTINCT {qualify(alias, order_col)}) "
            f"{from_inner} WHERE {inner_where}) = {rank - 1}")


def render_top_per_group(top_per_group=None):
    """Return (clauses, params). Params are always [] (correlated, rank inlined).
    Malformed specs are skipped."""
    clauses = []
    for i, spec in enumerate(top_per_group or []):
        sql = _render_top_per_group_one(spec, i)
        if sql:
            clauses.append(sql)
    return clauses, []


def render_group_by(group_by=None):
    cols = [qualify_ref(g) for g in (group_by or [])]
    if not cols:
        return ""
    return "GROUP BY " + ", ".join(cols)


def _render_having_predicate(h):
    """One HAVING predicate over an aggregation alias. Supports a scalar value
    (parameterized), another aggregation alias (`right_aggregation_alias`, no
    param, for aggregate-vs-aggregate), IN, and IS [NOT] NULL."""
    op = _normalize_op(h.get("op"))
    left = quote_ident(h.get("aggregation_alias"))
    if op in ("IS NULL", "IS NOT NULL"):
        return f"{left} {op}", []
    rqa = h.get("right_aggregation_alias")
    if rqa:
        sym = _SYMBOLIC.get(op, op)
        return f"{left} {sym} {quote_ident(rqa)}", []
    if op == "IN":
        value = h.get("value")
        vals = list(value) if isinstance(value, (list, tuple)) else [value]
        placeholders = ", ".join(["?"] * len(vals))
        return f"{left} IN ({placeholders})", vals
    sym = _SYMBOLIC.get(op, op)
    return f"{left} {sym} ?", [h.get("value")]


def render_having(having=None):
    """Return (clause, params). HAVING references aggregation aliases."""
    having = having or []
    if not having:
        return "", []
    body, params = _chain(having, _render_having_predicate)
    return "HAVING " + body, params


# ---------------------------------------------------------------------------
# Set division: HAVING COUNT(DISTINCT t.c) op (SELECT COUNT(DISTINCT u.d) FROM u)
# ---------------------------------------------------------------------------
def _render_set_division_one(spec):
    """Render one set-division spec to (having_predicate, params, group_cols),
    or None if malformed."""
    if not isinstance(spec, dict):
        return None
    left = spec.get("left")
    right = spec.get("right_subquery")
    if not isinstance(left, dict) or not isinstance(right, dict):
        return None
    from_table = right.get("from_table") or right.get("table")
    if not from_table:
        return None

    op = _normalize_op(spec.get("op") or "=")
    sym = _SYMBOLIC.get(op, op)
    left_sql = _render_simple_aggregate(left)
    right_sql = _render_simple_aggregate(right)

    sub = render_from_joins(from_table, right.get("joins"))   # 'FROM u [JOIN ...]'
    params = []
    preds = []
    for p in _subquery_predicates(right):
        s, prm = _render_subquery_predicate(p)
        if s is None:
            continue
        preds.append(s)
        params.extend(prm)
    where = (" WHERE " + " AND ".join(preds)) if preds else ""
    subquery = f"(SELECT {right_sql} {sub}{where})"
    having_pred = f"{left_sql} {sym} {subquery}"
    return having_pred, params, list(spec.get("group_by") or [])


def render_set_division(set_division=None):
    """Return (having_clauses, params, group_cols) contributed by set-division
    specs. Malformed specs skipped."""
    havings, params, group_cols = [], [], []
    for spec in set_division or []:
        rendered = _render_set_division_one(spec)
        if rendered is None:
            continue
        hp, prm, gc = rendered
        havings.append(hp)
        params.extend(prm)
        group_cols.extend(gc)
    return havings, params, group_cols


# ---------------------------------------------------------------------------
# Alias / self-join pair queries
# ---------------------------------------------------------------------------
def _qualify_aliasref(ref):
    """Qualify an {alias, column} reference: 'p1'.'pet_id' -> "p1"."pet_id"."""
    return qualify(ref.get("alias"), ref.get("column"))


def _render_alias_join_cond(j):
    """Render '<from> op <to>' for an alias join/comparison (column to column)."""
    op = _normalize_op(j.get("op") or "=")
    sym = _SYMBOLIC.get(op, op)
    return f"{_qualify_aliasref(j.get('from', {}))} {sym} {_qualify_aliasref(j.get('to', {}))}"


def render_alias_select(alias_select=None, distinct=False):
    """SELECT [DISTINCT] of {alias, column, as?} entries."""
    exprs = []
    for s in alias_select or []:
        if not isinstance(s, dict):
            continue
        expr = _qualify_aliasref(s)
        if s.get("as"):
            expr += f" AS {quote_ident(s['as'])}"
        exprs.append(expr)
    keyword = "SELECT DISTINCT" if distinct else "SELECT"
    return f"{keyword} " + ", ".join(exprs)


def render_alias_from_joins(aliases=None, alias_joins=None):
    """Build 'FROM <t> AS <a1> JOIN <t> AS <a2> ON ... ' from declared aliases
    and alias_joins. Returns (sql, leftover_joins) where leftover_joins are
    comparisons between already-introduced aliases (rendered later in WHERE).
    Each non-first alias is joined via the alias_joins that connect it to an
    already-introduced alias; an alias with none gets 'ON 1 = 1' (cross join)."""
    aliases = [a for a in (aliases or []) if isinstance(a, dict) and a.get("alias")]
    alias_joins = list(alias_joins or [])
    if not aliases:
        return "", alias_joins

    table_of = {a["alias"]: a.get("table") for a in aliases}
    order = [a["alias"] for a in aliases]

    first = order[0]
    sql = f"FROM {quote_ident(table_of[first])} AS {quote_ident(first)}"
    introduced = {first}
    consumed = set()

    for a in order[1:]:
        ons, kw = [], "INNER JOIN"
        for idx, j in enumerate(alias_joins):
            if idx in consumed or not isinstance(j, dict):
                continue
            fa = (j.get("from") or {}).get("alias")
            ta = (j.get("to") or {}).get("alias")
            if (ta == a and fa in introduced) or (fa == a and ta in introduced):
                if not ons:  # keyword from the first connecting join
                    kw = _JOIN_KEYWORDS.get(str(j.get("join_type", "inner")).lower(),
                                            "INNER JOIN")
                ons.append(_render_alias_join_cond(j))
                consumed.add(idx)
        on_sql = " AND ".join(ons) if ons else "1 = 1"
        sql += f" {kw} {quote_ident(table_of[a])} AS {quote_ident(a)} ON {on_sql}"
        introduced.add(a)

    leftover = [j for idx, j in enumerate(alias_joins) if idx not in consumed]
    return sql, leftover


def _render_alias_filter(f):
    """One alias WHERE predicate: column-vs-column (no param), column-vs-literal
    (param), or IS [NOT] NULL. Returns (sql, params) or (None, [])."""
    if not isinstance(f, dict) or not isinstance(f.get("left"), dict):
        return None, []
    op = _normalize_op(f.get("op"))
    left = _qualify_aliasref(f["left"])
    if op in ("IS NULL", "IS NOT NULL"):
        return f"{left} {op}", []
    right = f.get("right")
    if isinstance(right, dict) and right.get("alias") and right.get("column"):
        sym = _SYMBOLIC.get(op, op)
        return f"{left} {sym} {_qualify_aliasref(right)}", []
    sym = _SYMBOLIC.get(op or "=", op or "=")
    return f"{left} {sym} ?", [f.get("value")]


def render_alias_where(alias_filters=None, leftover_joins=None):
    """Return (clause, params) for the alias WHERE: alias_filters plus any
    leftover alias_joins (comparisons between already-joined aliases)."""
    bodies, params = [], []
    for j in leftover_joins or []:
        if isinstance(j, dict):
            bodies.append(_render_alias_join_cond(j))
    for f in alias_filters or []:
        sql, prm = _render_alias_filter(f)
        if sql is None:
            continue
        bodies.append(sql)
        params.extend(prm)
    if not bodies:
        return "", []
    return "WHERE " + " AND ".join(bodies), params


# ---------------------------------------------------------------------------
# Explicit outer joins + NULL tests + compound (OR/AND) filter groups
# ---------------------------------------------------------------------------
def _render_any_predicate(p):
    """Render a predicate in either shape, returns (sql, params):
      {left:{table,column}, op, right:{table,column}|value}  (column-form), or
      {table, column, op, value|value_ref}                   (filter-form),
    including IS [NOT] NULL. Returns (None, []) if malformed."""
    if not isinstance(p, dict):
        return None, []
    if isinstance(p.get("left"), dict):
        return _render_subquery_predicate(p)
    op = _normalize_op(p.get("op"))
    if p.get("table") is None and p.get("column") is None:
        return None, []
    ref = qualify_ref(p)
    if op in ("IS NULL", "IS NOT NULL"):
        return f"{ref} {op}", []
    return _render_predicate(ref, p.get("op"), p.get("value"), p.get("value_ref"))


def render_explicit_joins(explicit_joins=None):
    """Build 'FROM <root> [LEFT/INNER] JOIN <t> ON <conds> ...' from explicit
    join specs. The root is the first spec's from_table. Returns (sql, params);
    params come from any literal ON conditions (rare). Empty -> ('', [])."""
    specs = [j for j in (explicit_joins or []) if isinstance(j, dict) and j.get("to_table")]
    if not specs:
        return "", []
    root = specs[0].get("from_table")
    sql = f"FROM {quote_ident(root)}"
    params = []
    for j in specs:
        kw = _JOIN_KEYWORDS.get(str(j.get("join_type", "inner")).lower(), "INNER JOIN")
        ons, p = [], []
        for c in j.get("conditions") or []:
            s, prm = _render_any_predicate(c)
            if s is None:
                continue
            ons.append(s)
            p.extend(prm)
        on_sql = " AND ".join(ons) if ons else "1 = 1"
        sql += f" {kw} {quote_ident(j['to_table'])} ON {on_sql}"
        params.extend(p)
    return sql, params


def render_null_filters(null_filters=None):
    """Return a list of 'col IS [NOT] NULL' predicate strings (no params)."""
    clauses = []
    for f in null_filters or []:
        if not isinstance(f, dict):
            continue
        op = _normalize_op(f.get("op")) or "IS NULL"
        if op not in ("IS NULL", "IS NOT NULL"):
            op = "IS NULL"
        clauses.append(f"{qualify_ref(f)} {op}")
    return clauses


def render_compound_filters(compound_filters=None):
    """Return (clauses, params): each group rendered as '(p1 <conn> p2 ...)'
    with its connector (default OR). Malformed conditions are skipped."""
    clauses, params = [], []
    for grp in compound_filters or []:
        if not isinstance(grp, dict):
            continue
        conn = str(grp.get("connector") or "OR").strip().upper()
        if conn not in ("AND", "OR"):
            conn = "OR"
        bodies, gp = [], []
        for c in grp.get("conditions") or []:
            s, prm = _render_any_predicate(c)
            if s is None:
                continue
            bodies.append(s)
            gp.extend(prm)
        if not bodies:
            continue
        clauses.append("(" + f" {conn} ".join(bodies) + ")")
        params.extend(gp)
    return clauses, params


# ---------------------------------------------------------------------------
# Derived relations (CTEs): WITH <name> AS ( SELECT ... ), ...
# ---------------------------------------------------------------------------
def _render_derived_relation(spec):
    """Render one CTE to ('<name> AS (SELECT ...)', params) or (None, []). The
    body is a normal aggregate SELECT over REAL tables (reuses the standard
    select/from/where/group-by renderers)."""
    if not isinstance(spec, dict):
        return None, []
    name = spec.get("name")
    if not name or not spec.get("from_table"):
        return None, []
    select = spec.get("select") or []
    aggregations = spec.get("aggregations") or []
    if not select and not aggregations:
        return None, []
    sel = render_select(select, aggregations, bool(spec.get("distinct")))
    frm = render_from_joins(spec.get("from_table"), spec.get("joins"))
    where_sql, where_params = render_where(spec.get("filters"))
    grp = render_group_by(spec.get("group_by"))
    body = " ".join(part for part in [sel, frm, where_sql, grp] if part)
    return f"{quote_ident(name)} AS ({body})", where_params


def render_with_clause(derived_relations=None):
    """Return ('WITH r1 AS (...), r2 AS (...)', params) or ('', []) if none.
    Malformed CTE specs are skipped."""
    parts, params = [], []
    for spec in derived_relations or []:
        rendered, prm = _render_derived_relation(spec)
        if rendered is None:
            continue
        parts.append(rendered)
        params.extend(prm)
    if not parts:
        return "", []
    return "WITH " + ", ".join(parts), params


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

# (Stage 2: render_anti_exists added above.)