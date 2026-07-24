"""
sql_candidates/repair_normalize.py

Generic, deterministic repair-SQL validity normalization (no LLM, no DB names).

A non-aggregate outer SELECT that carries a HAVING clause but no GROUP BY and no
aggregate in its own projection/HAVING is invalid in SQLite ("HAVING clause on a
non-aggregate query"). This commonly happens when a repair pre-aggregates the
numerator and denominator in CTEs, joins them to the entity, and then filters a
precomputed CTE column with HAVING instead of WHERE.

  * outer_having_invalid(sql) -> bool
        detects the invalid shape (aggregates INSIDE CTEs / subqueries do NOT
        make the outer query an aggregate query).

  * safe_having_to_where(sql) -> (new_sql_or_None, action)
        moves the HAVING predicate to WHERE (AND-combined with any existing
        WHERE) ONLY when it is provably safe: the outer SELECT is non-aggregate,
        the HAVING predicate itself contains no aggregate, and it references no
        unqualified SELECT-list alias unavailable to WHERE. Otherwise returns
        (None, reason) and the caller leaves the SQL untouched (to be rejected by
        execution or retried) — never a blind rewrite.

Everything is schema-generic; nothing here hardcodes a table, column, or domain.
"""
from sqlglot import exp, parse_one

__all__ = ["outer_having_invalid", "safe_having_to_where"]


def _parse(sql):
    try:
        return parse_one(sql, read="sqlite")
    except Exception:
        return None


def _outer_select(tree):
    """The query's outermost SELECT (the one whose projection is the final
    output). A `WITH ... SELECT` parses as a Select whose CTEs hang off it, so
    that Select IS the outer scope; a UNION/subquery is unwrapped to its first
    branch's select for this local structural check."""
    if tree is None:
        return None
    if isinstance(tree, exp.Select):
        return tree
    if isinstance(tree, (exp.Subquery, exp.Paren)):
        return _outer_select(tree.this)
    if isinstance(tree, exp.Union):
        return _outer_select(tree.this)
    return None


def _has_scope_aggregate(select, node):
    """True when `node` (a projection expr or the HAVING predicate) contains an
    aggregate that belongs to THIS select's scope — an aggregate nested inside a
    subquery/CTE (its nearest enclosing Select differs) does not count."""
    if node is None:
        return False
    for agg in node.find_all(exp.AggFunc):
        p = agg.parent
        while p is not None and not isinstance(p, exp.Select):
            p = p.parent
        if p is select:
            return True
    return False


def _outer_is_aggregate(select):
    if select.args.get("group"):
        return True
    for e in (select.expressions or []):
        if _has_scope_aggregate(select, e):
            return True
    having = select.args.get("having")
    if having is not None and _has_scope_aggregate(select, having.this):
        return True
    return False


def outer_having_invalid(sql):
    """A non-aggregate outer SELECT with a HAVING clause (invalid in SQLite)."""
    tree = _parse(sql)
    sel = _outer_select(tree)
    if sel is None:
        return False
    if sel.args.get("having") is None:
        return False
    return not _outer_is_aggregate(sel)


def _select_aliases(select):
    out = set()
    for e in (select.expressions or []):
        if isinstance(e, exp.Alias):
            nm = (e.alias or "").lower()
            if nm:
                out.add(nm)
    return out


def safe_having_to_where(sql):
    """Return (new_sql, action). action is one of:
        'normalized_having_to_where'  — HAVING safely moved to WHERE
        'not_invalid'                 — no invalid outer HAVING present
        'unsafe_having_has_aggregate' — HAVING contains an aggregate; not moved
        'unsafe_having_uses_select_alias' — relies on a SELECT alias; not moved
        'parse_error'
    When the action is not 'normalized_having_to_where', new_sql is None and the
    caller must NOT rewrite (reject / retry instead)."""
    tree = _parse(sql)
    sel = _outer_select(tree)
    if sel is None:
        return None, "parse_error"
    having = sel.args.get("having")
    if having is None or _outer_is_aggregate(sel):
        return None, "not_invalid"
    pred = having.this
    if pred is None:
        return None, "not_invalid"
    # (2) the HAVING predicate itself must contain no aggregate.
    if _has_scope_aggregate(sel, pred):
        return None, "unsafe_having_has_aggregate"
    # (3)/(4) it must not depend on an unqualified SELECT-list alias (unavailable
    # to WHERE). A qualified column (t.col) is a source/CTE column and is safe.
    aliases = _select_aliases(sel)
    for col in pred.find_all(exp.Column):
        if not (col.table or "") and (col.name or "").lower() in aliases:
            return None, "unsafe_having_uses_select_alias"
    # (5)/(6) no GROUP BY -> moving to WHERE is equivalent; preserve any existing
    # WHERE by AND-combining.
    new_tree = tree.copy()
    nsel = _outer_select(new_tree)
    npred = nsel.args.get("having").this
    existing = nsel.args.get("where")
    combined = exp.and_(existing.this, npred) if existing is not None else npred
    nsel.set("where", exp.Where(this=combined))
    nsel.set("having", None)
    try:
        return new_tree.sql(dialect="sqlite"), "normalized_having_to_where"
    except Exception:
        return None, "parse_error"
