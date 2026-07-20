"""
sql_analysis/ast_tools.py

Small, focused sqlglot helpers for SEMANTIC CONTRACT validation (Stage 0).

Everything here is read-only analysis of one SQL string using the SQLite
dialect. The functions are deliberately conservative: whenever something
cannot be PROVEN from the AST (unknown alias, ambiguous unqualified column,
set operations, ordinal GROUP BY, ...), the answer is "unknown" — callers
(the grain validator) must treat "unknown" as non-fatal.

Scope model: sqlglot's `traverse_scope` gives one Scope per SELECT
(CTEs, subqueries, and the outer query each get their own scope). A scope's
`sources` map alias -> exp.Table (physical table) or Scope (CTE/derived
table), which lets us trace a column through CTE/subquery projections down
to the physical table.column it came from — or to the aggregate that
produced it.

This module contains NO validation policy and NO checklist/contract logic.
"""

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.scope import Scope, traverse_scope

__all__ = [
    "DIALECT", "ParsedSql", "ColumnOrigin", "parse_sql", "scope_nodes",
    "scope_aggregates", "aggregate_name", "aggregate_arg_column",
    "aggregate_arg_columns", "origin_ranges_over", "scope_selected_sources",
    "group_by_columns", "comparison_predicates", "columns_outside_aggregates",
    "scope_has_limit_one", "trace_column", "trace_expression", "side_origin",
    "row_filter_nodes", "literal_filters", "extremum_equalities",
]

DIALECT = "sqlite"

# aggregate functions we reason about (SQLite core aggregates)
_AGG_NAMES = {"sum": "sum", "avg": "avg", "count": "count",
              "min": "min", "max": "max", "total": "sum",
              "group_concat": "group_concat"}

_COMPARISONS = (exp.GT, exp.GTE, exp.LT, exp.LTE, exp.EQ, exp.NEQ)


# ---------------------------------------------------------------------------
# parse (controlled failure)
# ---------------------------------------------------------------------------
@dataclass
class ParsedSql:
    ok: bool
    tree: exp.Expression | None = None
    scopes: list = field(default_factory=list)   # list[Scope], root LAST
    error: str | None = None

    @property
    def root_scope(self):
        return self.scopes[-1] if self.scopes else None


def parse_sql(sql: str) -> ParsedSql:
    """Parse one statement with the SQLite dialect. Never raises."""
    if not isinstance(sql, str) or not sql.strip():
        return ParsedSql(ok=False, error="empty SQL")
    try:
        tree = sqlglot.parse_one(sql, read=DIALECT)
    except SqlglotError as e:
        return ParsedSql(ok=False, error=f"parse error: {e}")
    except Exception as e:                                   # pragma: no cover
        return ParsedSql(ok=False, error=f"unexpected parse failure: {e}")
    if tree is None:
        return ParsedSql(ok=False, error="no statement parsed")
    try:
        scopes = list(traverse_scope(tree))
    except Exception as e:
        # a tree we cannot scope (odd DDL, set-ops edge cases) is a
        # controlled analysis failure, not a crash
        return ParsedSql(ok=False, tree=tree, error=f"scope analysis failed: {e}")
    if not scopes:
        return ParsedSql(ok=False, tree=tree, error="no SELECT scope found")
    return ParsedSql(ok=True, tree=tree, scopes=scopes)


# ---------------------------------------------------------------------------
# per-scope node access (never descends into nested SELECTs)
# ---------------------------------------------------------------------------
def scope_nodes(scope: Scope):
    """All expression nodes belonging to THIS scope only (subquery/CTE
    bodies are pruned — they have their own Scope)."""
    root = scope.expression
    for node in root.walk(prune=lambda n: isinstance(n, exp.Select) and n is not root):
        if isinstance(node, exp.Select) and node is not root:
            continue                       # the pruned boundary node itself
        yield node


def scope_aggregates(scope: Scope):
    """Aggregate-function nodes of this scope (not those of subqueries)."""
    return [n for n in scope_nodes(scope) if isinstance(n, exp.AggFunc)]


def aggregate_name(agg: exp.AggFunc) -> str | None:
    """Canonical lowercase aggregate name ('sum', 'avg', ...) or None."""
    return _AGG_NAMES.get(agg.key.lower()) if isinstance(agg, exp.AggFunc) else None


def aggregate_arg_column(agg: exp.AggFunc) -> exp.Column | None:
    """The single column the aggregate is computed over, if provable.
    Returns None for COUNT(*), multi-column expressions, or nested
    aggregates (uncertain cases)."""
    cols = list(agg.find_all(exp.Column))
    inner_aggs = [a for a in agg.find_all(exp.AggFunc) if a is not agg]
    if len(cols) != 1 or inner_aggs:
        return None
    return cols[0]


def aggregate_arg_columns(agg: exp.AggFunc) -> list | None:
    """Columns an aggregate provably ranges over when its argument is a single
    column OR an ADDITIVE (+/-) combination of columns and constants
    (a derived additive measure, e.g. SUM(total - paid)). DISTINCT wrappers
    are transparent. Returns a non-empty list of exp.Column, or None when the
    argument has any other shape (function calls, CASE, nested aggregates,
    multiplication, ... — all uncertain)."""
    if not isinstance(agg, exp.AggFunc):
        return None
    if any(a is not agg for a in agg.find_all(exp.AggFunc)):
        return None
    cols, stack = [], [agg.this]
    while stack:
        n = stack.pop()
        while isinstance(n, (exp.Paren, exp.Neg, exp.Cast, exp.Alias)):
            n = n.this
        if isinstance(n, (exp.Add, exp.Sub)):
            stack.extend([n.this, n.expression])
        elif isinstance(n, exp.Distinct):
            stack.extend(n.expressions)
        elif isinstance(n, exp.Column):
            cols.append(n)
        elif isinstance(n, (exp.Literal, exp.Null)):
            continue
        else:
            return None
    return cols or None


def group_by_columns(scope: Scope) -> list | None:
    """GROUP BY column nodes of this scope. Returns None (uncertain) when
    GROUP BY uses ordinals or non-column expressions; [] when no GROUP BY."""
    group = scope.expression.args.get("group")
    if group is None:
        return []
    out = []
    for e in group.expressions:
        e = e.unnest() if isinstance(e, exp.Paren) else e
        if isinstance(e, exp.Column):
            out.append(e)
        else:
            return None                    # ordinal / expression — uncertain
    return out


def comparison_predicates(scope: Scope):
    """Binary comparison nodes (>, >=, <, <=, =, <>) of this scope."""
    return [n for n in scope_nodes(scope) if isinstance(n, _COMPARISONS)]


def columns_outside_aggregates(scope: Scope):
    """Column nodes of this scope that are NOT inside any aggregate call and
    do NOT match a GROUP BY key (matched by qualified name, so the SELECT-list
    repeat of a group key is not reported as a bare measure)."""
    group = scope.expression.args.get("group")
    gkeys = set()
    for g in (group.expressions if group is not None else []):
        g = g.unnest() if isinstance(g, exp.Paren) else g
        if isinstance(g, exp.Column):
            gkeys.add(((g.table or "").lower(), (g.name or "").lower()))
    out = []
    for node in scope_nodes(scope):
        if not isinstance(node, exp.Column):
            continue
        qual = ((node.table or "").lower(), (node.name or "").lower())
        # group-by key (same name; tolerate a missing qualifier on either side)
        if qual in gkeys or any(k[1] == qual[1] and ("" in (k[0], qual[0]))
                                for k in gkeys):
            continue
        inside = False
        p = node.parent
        while p is not None and p is not scope.expression.parent:
            if isinstance(p, exp.AggFunc):
                inside = True
                break
            if p is group:
                inside = True              # non-column GROUP BY expression
                break
            p = p.parent
        if not inside:
            out.append(node)
    return out


def scope_has_limit_one(scope: Scope) -> bool:
    """True when this scope's SELECT has LIMIT 1 (single-event restriction)."""
    limit = scope.expression.args.get("limit")
    if limit is None:
        return False
    n = limit.expression
    return isinstance(n, exp.Literal) and n.this == "1"


# ---------------------------------------------------------------------------
# column-origin tracing (through CTEs / derived tables)
# ---------------------------------------------------------------------------
@dataclass
class ColumnOrigin:
    """Where a column's value ultimately comes from.

    kind:
      "physical"   a real table column          -> table, column
      "aggregate"  produced by an aggregate     -> aggregate, inner, group_keys
      "literal"    a constant
      "unknown"    cannot be proven (ambiguous alias, expression, depth, ...)
    """
    kind: str
    table: str | None = None
    column: str | None = None
    aggregate: str | None = None            # 'sum' / 'avg' / 'row_number' ...
    inner: "ColumnOrigin | None" = None     # what the aggregate ranges over
    components: list = field(default_factory=list)
    # ^ for aggregates over a derived ADDITIVE measure (SUM(x-y) or
    #   SUM(x)-SUM(y)): the physical column origins the value ranges over.
    #   Single-column aggregates carry [inner] here too when provable.
    group_keys: list = field(default_factory=list)   # list[ColumnOrigin]
    distinct: bool = False                  # aggregate over DISTINCT values
    limited_to_one_row: bool = False        # produced under LIMIT 1
    note: str | None = None
    scope: object = field(default=None, repr=False, compare=False)
    # ^ the Scope where an aggregate/window value was computed (kind
    #   "aggregate"/"window"); lets validators inspect that scope's filters

    def is_physical(self, table: str, column: str) -> bool:
        return (self.kind == "physical"
                and self.table == (table or "").lower()
                and self.column == (column or "").lower())


def origin_ranges_over(origin, table: str, column: str) -> bool:
    """True when an aggregate-kind origin PROVABLY ranges over the physical
    table.column — via its single-column inner or any additive component."""
    if origin is None or origin.kind != "aggregate":
        return False
    if origin.inner is not None and origin.inner.is_physical(table, column):
        return True
    return any(c.is_physical(table, column) for c in (origin.components or []))


_UNKNOWN = ColumnOrigin(kind="unknown")
_MAX_DEPTH = 6


def scope_selected_sources(scope: Scope) -> dict:
    """alias -> source (exp.Table | Scope), restricted to sources the scope
    actually SELECTs from (FROM/JOIN). sqlglot's `scope.sources` also lists
    CTEs that are merely *visible* to the scope — those must not make
    unqualified columns ambiguous or count as measure inputs."""
    try:
        return {alias: src for alias, (_node, src)
                in (scope.selected_sources or {}).items()}
    except Exception:                                    # pragma: no cover
        return dict(scope.sources or {})


def _source_for(scope: Scope, qualifier: str | None, column_name: str,
                schema_idx=None):
    """Resolve which source (alias) a column belongs to. Returns
    (source_object, note) — source is exp.Table | Scope | None."""
    sources = scope_selected_sources(scope)
    if qualifier:
        src = sources.get(qualifier) or (scope.sources or {}).get(qualifier)
        if src is None:
            # correlated reference to an OUTER scope's alias
            parent, hops = getattr(scope, "parent", None), 0
            while parent is not None and hops < _MAX_DEPTH:
                psources = scope_selected_sources(parent)
                if qualifier in psources:
                    return psources[qualifier], None
                parent, hops = getattr(parent, "parent", None), hops + 1
        return src, None
    if len(sources) == 1:
        return next(iter(sources.values())), None
    # unqualified with several selected sources: provable only via schema
    if schema_idx:
        owners = []
        for alias, src in sources.items():
            if isinstance(src, exp.Table):
                cols = (schema_idx.get("tables") or {}).get(src.name.lower()) or []
                if any(c.get("name") == column_name.lower() for c in cols):
                    owners.append(src)
            elif isinstance(src, Scope):
                names = {s.alias_or_name.lower() for s in src.expression.selects}
                if column_name.lower() in names:
                    owners.append(src)
        if len(owners) == 1:
            return owners[0], None
    return None, "ambiguous unqualified column"


def trace_column(scope: Scope, column: exp.Column, schema_idx=None,
                 _depth: int = 0,
                 _skip_aliases: frozenset = frozenset()) -> ColumnOrigin:
    """Trace a column reference to its origin. Conservative: 'unknown'
    whenever a step cannot be proven. An UNQUALIFIED name that does not
    resolve to any source is also checked against this scope's own SELECT
    aliases (SQLite allows `HAVING total > avg_x` referring to projections)
    — aliases never define grain, only the traced expression does."""
    if _depth > _MAX_DEPTH:
        return ColumnOrigin(kind="unknown", note="max trace depth")
    name = (column.name or "").lower()
    qualifier = (column.table or "").lower() or None
    src, note = _source_for(scope, qualifier, name, schema_idx)
    if src is None:
        if qualifier is None and name not in _skip_aliases:
            for sel in scope.expression.selects:
                if isinstance(sel, exp.Alias) \
                        and (sel.alias or "").lower() == name:
                    origin = trace_expression(
                        scope, sel.this, schema_idx, _depth + 1,
                        _skip_aliases | {name})
                    return origin
        return ColumnOrigin(kind="unknown", column=name, note=note or "unresolved source")
    if isinstance(src, exp.Table):
        return ColumnOrigin(kind="physical", table=src.name.lower(), column=name)
    if isinstance(src, Scope):
        for sel in src.expression.selects:
            if (sel.alias_or_name or "").lower() == name:
                origin = trace_expression(src, sel, schema_idx, _depth + 1)
                if scope_has_limit_one(src):
                    origin.limited_to_one_row = True
                return origin
        # SELECT * passthrough or unknown projection
        if any(isinstance(s, exp.Star) for s in src.expression.selects):
            return ColumnOrigin(kind="unknown", column=name, note="SELECT * passthrough")
        return ColumnOrigin(kind="unknown", column=name, note="projection not found")
    return ColumnOrigin(kind="unknown", column=name, note="unrecognized source type")


def trace_expression(scope: Scope, node: exp.Expression, schema_idx=None,
                     _depth: int = 0,
                     _skip_aliases: frozenset = frozenset()) -> ColumnOrigin:
    """Trace an arbitrary projected expression to its origin."""
    if _depth > _MAX_DEPTH:
        return ColumnOrigin(kind="unknown", note="max trace depth")
    while isinstance(node, (exp.Alias, exp.Paren, exp.Cast, exp.Neg)):
        node = node.this
    if isinstance(node, exp.Column):
        return trace_column(scope, node, schema_idx, _depth, _skip_aliases)
    if isinstance(node, exp.Literal):
        return ColumnOrigin(kind="literal")
    if isinstance(node, exp.Window):
        fn = node.this
        wname = fn.key.lower() if isinstance(fn, exp.Expression) else None
        return ColumnOrigin(kind="window", aggregate=wname, scope=scope)
    if isinstance(node, exp.AggFunc):
        arg = aggregate_arg_column(node)
        components = []
        if arg is not None:
            inner = trace_column(scope, arg, schema_idx, _depth + 1)
            if inner.kind == "physical":
                components = [inner]
        else:
            # derived ADDITIVE measure: SUM(x - y) etc.
            cols = aggregate_arg_columns(node)
            traced = ([trace_column(scope, c, schema_idx, _depth + 1)
                       for c in cols] if cols else [])
            if traced and all(o.kind == "physical" for o in traced):
                components = traced
                inner = ColumnOrigin(kind="unknown",
                                     note="additive aggregate arg")
            else:
                inner = ColumnOrigin(kind="unknown",
                                     note="non-single-column aggregate arg")
        gcols = group_by_columns(scope)
        gkeys = ([trace_column(scope, g, schema_idx, _depth + 1) for g in gcols]
                 if gcols is not None else
                 [ColumnOrigin(kind="unknown", note="non-column GROUP BY")])
        return ColumnOrigin(kind="aggregate", aggregate=aggregate_name(node),
                            inner=inner, components=components,
                            distinct=isinstance(node.this, exp.Distinct),
                            group_keys=gkeys, scope=scope)
    if isinstance(node, (exp.Add, exp.Sub)):
        # arithmetic COMBINATION of aggregates from the SAME scope with the
        # SAME aggregate name (SUM(x) - SUM(y)) is grain-equivalent to one
        # aggregate over the derived additive measure. Anything mixed or
        # unprovable stays unknown (conservative).
        terms, stack = [], [node]
        while stack:
            n = stack.pop()
            while isinstance(n, (exp.Paren, exp.Neg, exp.Cast)):
                n = n.this
            if isinstance(n, (exp.Add, exp.Sub)):
                stack.extend([n.this, n.expression])
            elif isinstance(n, exp.Literal):
                continue                      # constant offsets keep the grain
            else:
                terms.append(trace_expression(scope, n, schema_idx,
                                              _depth + 1, _skip_aliases))
        if terms and all(t.kind == "aggregate" for t in terms):
            names = {t.aggregate for t in terms}
            scopes = {id(t.scope) for t in terms}
            if len(names) == 1 and len(scopes) == 1:
                components = []
                for t in terms:
                    components.extend(t.components or [])
                return ColumnOrigin(
                    kind="aggregate", aggregate=terms[0].aggregate,
                    inner=terms[0].inner, components=components,
                    group_keys=terms[0].group_keys,
                    limited_to_one_row=any(t.limited_to_one_row for t in terms),
                    scope=terms[0].scope)
        return ColumnOrigin(kind="unknown", note="mixed arithmetic expression")
    return ColumnOrigin(kind="unknown", note=f"expression {node.key}")


def side_origin(parsed: ParsedSql, scope: Scope, node: exp.Expression,
                schema_idx=None) -> ColumnOrigin:
    """Origin of ONE side of a comparison: a column, a scalar subquery, an
    aggregate call, or a literal. Anything else is unknown."""
    while isinstance(node, (exp.Paren, exp.Cast)):
        node = node.this
    if isinstance(node, (exp.Column, exp.Literal, exp.AggFunc,
                         exp.Add, exp.Sub, exp.Neg)):
        return trace_expression(scope, node, schema_idx)
    if isinstance(node, exp.Subquery):
        inner_select = node.this
        for s in parsed.scopes:
            if s.expression is inner_select:
                selects = s.expression.selects
                if len(selects) == 1:
                    origin = trace_expression(s, selects[0], schema_idx)
                    if scope_has_limit_one(s):
                        origin.limited_to_one_row = True
                    return origin
                return ColumnOrigin(kind="unknown", note="multi-column subquery")
        return ColumnOrigin(kind="unknown", note="subquery scope not found")
    return ColumnOrigin(kind="unknown", note=f"comparison side {node.key}")


# ---------------------------------------------------------------------------
# row-level filter analysis (WHERE + JOIN ON of one scope, pre-aggregation)
# ---------------------------------------------------------------------------
def row_filter_nodes(scope: Scope):
    """Expression nodes of this scope's row filters: the WHERE clause and
    every JOIN ... ON condition. HAVING is intentionally EXCLUDED — it
    filters groups after aggregation and does not restrict measure rows.
    Nested SELECT bodies are pruned (they have their own scopes)."""
    roots = []
    where = scope.expression.args.get("where")
    if where is not None:
        roots.append(where)
    for join in scope.expression.args.get("joins") or []:
        on = join.args.get("on")
        if on is not None:
            roots.append(on)
    for root in roots:
        for node in root.walk(prune=lambda n: isinstance(n, exp.Select)):
            if isinstance(node, exp.Select):
                continue
            yield node


_LITERALISH = (exp.Literal, exp.Placeholder, exp.Null, exp.Boolean)


def _is_literalish(node) -> bool:
    while isinstance(node, (exp.Paren, exp.Cast, exp.Neg)):
        node = node.this
    return isinstance(node, _LITERALISH)


def literal_filters(scope: Scope, schema_idx=None):
    """Row filters of this scope that compare a column against constants
    (=, <>, <, >, IN (literals), LIKE, BETWEEN). Returns a list of
    (table, column) for columns that PROVABLY resolve to physical tables.
    Join predicates (column = column) are never included."""
    out = []
    for node in row_filter_nodes(scope):
        col = None
        if isinstance(node, _COMPARISONS + (exp.Like, exp.ILike)):
            l, r = node.this, node.expression
            if isinstance(l, exp.Column) and _is_literalish(r):
                col = l
            elif isinstance(r, exp.Column) and _is_literalish(l):
                col = r
        elif isinstance(node, exp.In):
            if isinstance(node.this, exp.Column) and node.expressions \
                    and all(_is_literalish(e) for e in node.expressions):
                col = node.this
        elif isinstance(node, exp.Between):
            if isinstance(node.this, exp.Column) \
                    and _is_literalish(node.args.get("low")) \
                    and _is_literalish(node.args.get("high")):
                col = node.this
        if col is None:
            continue
        origin = trace_column(scope, col, schema_idx)
        if origin.kind == "physical":
            out.append((origin.table, origin.column))
    return out


def extremum_equalities(parsed: ParsedSql, scope: Scope, schema_idx=None):
    """Row-filter equalities that pin rows to an extremum / single row:
    `col = (SELECT MAX/MIN ...)`, `col = MAX(col) OVER ...` aliases, or a
    ROW_NUMBER() value compared to 1. Returns human-readable notes."""
    notes = []
    for node in row_filter_nodes(scope):
        if not isinstance(node, exp.EQ):
            continue
        for side, other in ((node.this, node.expression),
                            (node.expression, node.this)):
            origin = side_origin(parsed, scope, side, schema_idx)
            if origin.kind == "aggregate" and origin.aggregate in ("max", "min"):
                notes.append(f"{origin.aggregate.upper()}-equality pins rows "
                             f"to a single extremum event")
                break
            if origin.kind == "window" \
                    and (origin.aggregate or "").replace("_", "") == "rownumber" \
                    and _is_literalish(other):
                notes.append("ROW_NUMBER() = <constant> pins rows to a "
                             "single ranked event")
                break
    return notes
