"""
sql_candidates/semantic_sql_guards.py

Generic FATAL semantic guards for generated SQL. These catch "executes but is
nonsense" candidates that the shape/execution scorers otherwise reward:

  * Cartesian join       — `JOIN ... ON 1=1` / `ON TRUE` (no real predicate)
  * Uncorrelated absence — `NOT EXISTS (subquery)` that never references the
                           outer row, for an "employees who have no ..." question
  * Constant measure     — `SUM(1)` / `SUM(<col aliased to a constant>)` when the
                           question asks for a monetary/quantity total
  * Wrong ranking measure— `ROW_NUMBER() OVER (... ORDER BY <id/metadata-date>)`
                           when the question ranks by a value/amount

Everything is derived from the SQL text + the question + the checklist — no
table, column, or database is hardcoded. Each function returns a reason string
(or None); `sql_guard_violations` aggregates them. Never raises.
"""

import re

__all__ = [
    "sql_guard_violations",
    "cartesian_join_violation",
    "uncorrelated_absence_violation",
    "constant_measure_violation",
    "ranking_measure_violation",
]

# -- intent vocabularies -----------------------------------------------------
_ABSENCE_WORDS = (
    "have no ", "has no ", "with no ", "no matching", "never ", "not purchased",
    "not bought", "without ", "does not ", "do not ", "did not ", "no record",
    "not recorded", "not assigned", "not present", "have not ", "has not ",
)
_MONEY_WORDS = (
    "spend", "spent", "spending", "revenue", "amount", "total due", "value",
    " cost", "price", " paid", "payment", "sales", "monetary", "dollar",
    "expenditure", "purchase order value", "running total",
)
_CROSS_OK_WORDS = ("cross join", "cartesian", "every combination",
                   "all combinations", "each pair of")


def _strip_strings(sql):
    return re.sub(r"'(?:[^']|'')*'", "''", sql or "")


def _q(question):
    return " " + str(question or "").lower().strip() + " "


def _any(hay, words):
    return any(w in hay for w in words)


def _is_id_like(col):
    n = re.sub(r"[^a-z0-9]", "", str(col or "").lower())
    return n == "id" or n.endswith("id")


def _is_metadata_date(col):
    n = str(col or "").lower()
    return ("modifieddate" in n or "rowguid" in n or n.endswith("guid")
            or "createddate" in n or "updateddate" in n)


# ---------------------------------------------------------------------------
# 1) Cartesian join
# ---------------------------------------------------------------------------
_CARTESIAN_RE = re.compile(
    r"\bjoin\b[^()]*?\bon\b\s*\(?\s*(?:1\s*=\s*1|true|0\s*=\s*0)\s*\)?",
    re.IGNORECASE,
)


def cartesian_join_violation(sql, question):
    """A JOIN whose ON predicate is a constant truth (1=1 / TRUE): a Cartesian
    product masquerading as a join. Allowed only if the question explicitly asks
    for a cross product."""
    if not sql:
        return None
    if _any(_q(question), _CROSS_OK_WORDS):
        return None
    if _CARTESIAN_RE.search(_strip_strings(sql)):
        return ("Cartesian join: a JOIN uses a constant ON predicate (ON 1=1 / "
                "ON TRUE) instead of a real key relationship")
    return None


# ---------------------------------------------------------------------------
# 2) Uncorrelated NOT EXISTS for absence questions
# ---------------------------------------------------------------------------
_NOT_EXISTS_RE = re.compile(r"\bnot\s+exists\s*\(", re.IGNORECASE)
_SUBQ_DEF_RE = re.compile(
    r'\b(?:from|join)\s+"?([a-z_]\w*)"?'
    r'(?:\s+(?:as\s+)?"?(?!(?:where|on|group|order|having|limit|inner|left|'
    r'right|outer|cross|full|join|and|or|not|union|select)\b)([a-z_]\w*)"?)?',
    re.IGNORECASE,
)
_QUALREF_RE = re.compile(r'\b([a-z_]\w*)\s*\.\s*[a-z_*]', re.IGNORECASE)


def _balanced_after(text, open_paren_idx):
    """Return the substring INSIDE the parentheses that open at
    open_paren_idx (which must point at '('), or '' if unbalanced."""
    depth = 0
    for i in range(open_paren_idx, len(text)):
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren_idx + 1:i]
    return ""


def uncorrelated_absence_violation(sql, question):
    """For an absence question ('employees who have no ...'), a NOT EXISTS
    subquery must reference the OUTER row. A subquery whose every qualifier is
    defined inside itself is uncorrelated — it is the same all-or-nothing
    condition for every outer row, which is never the intended per-entity
    absence check."""
    if not sql or not _any(_q(question), _ABSENCE_WORDS):
        return None
    text = _strip_strings(sql)
    for m in _NOT_EXISTS_RE.finditer(text):
        open_idx = text.index("(", m.end() - 1)
        body = _balanced_after(text, open_idx)
        if not body:
            continue
        defined = set()
        for dm in _SUBQ_DEF_RE.finditer(body):
            tbl = (dm.group(1) or "").lower()
            alias = (dm.group(2) or "").lower()
            if tbl:
                defined.add(tbl)
            if alias:
                defined.add(alias)
        refs = {rm.group(1).lower() for rm in _QUALREF_RE.finditer(body)}
        outer_refs = refs - defined
        if not outer_refs:
            return ("uncorrelated NOT EXISTS: the absence subquery never "
                    "references the outer row, so it applies the same "
                    "all-or-nothing condition to every row")
    return None


# ---------------------------------------------------------------------------
# 3) Constant used as a monetary/quantity measure
# ---------------------------------------------------------------------------
_CONST_AGG_RE = re.compile(
    r"\b(?:sum|total|avg|average)\s*\(\s*[-+]?\d+(?:\.\d+)?\s*\)", re.IGNORECASE)
_CONST_ALIAS_RE = re.compile(
    r"(?<![\w.])[-+]?\d+(?:\.\d+)?\s+as\s+\"?([a-z_]\w*)\"?", re.IGNORECASE)


def constant_measure_violation(sql, question, checklist=None):
    """A monetary/quantity question whose aggregated measure is a numeric
    CONSTANT (SUM(1), or SUM(x) where x is an alias for a literal). This is the
    'every vendor's running total is 1' failure."""
    if not sql:
        return None
    ql = _q(question)
    measure_intent = _any(ql, _MONEY_WORDS)
    if checklist:
        mc = str((checklist or {}).get("measure_column") or "").lower()
        if any(w.strip() in mc for w in _MONEY_WORDS):
            measure_intent = True
    if not measure_intent:
        return None
    text = _strip_strings(sql)
    if _CONST_AGG_RE.search(text):
        return ("constant measure: a monetary/quantity total is computed over a "
                "numeric constant (e.g. SUM(1)) instead of a real value column")
    const_aliases = {m.group(1).lower() for m in _CONST_ALIAS_RE.finditer(text)}
    for alias in const_aliases:
        if re.search(r"\b(?:sum|total|avg|average)\s*\(\s*\"?"
                     + re.escape(alias) + r"\"?\s*\)", text, re.IGNORECASE):
            return ("constant measure: the aggregated column '" + alias
                    + "' is a constant literal, not a real value column")
    return None


# ---------------------------------------------------------------------------
# 4) Ranking by an id / metadata date when a value ranking was requested
# ---------------------------------------------------------------------------
_RANK_OVER_RE = re.compile(
    r"\b(?:row_number|rank|dense_rank)\s*\(\s*\)\s*over\s*\(([^)]*)\)",
    re.IGNORECASE)
_ORDER_KEY_RE = re.compile(
    r"\border\s+by\s+([a-z_][\w.]*)", re.IGNORECASE)
_RANK_INTENT_RE = re.compile(
    r"\b(greatest|highest|largest|top|most|biggest|maximum|lowest|smallest|"
    r"minimum|least)\b", re.IGNORECASE)


def ranking_measure_violation(sql, question):
    """A 'top/greatest ... value/amount' question must rank by a real measure.
    Ranking by an id column or a metadata date (ModifiedDate/rowguid) is a wrong
    ranking key."""
    if not sql:
        return None
    ql = _q(question)
    if not (_RANK_INTENT_RE.search(ql) and _any(ql, _MONEY_WORDS)):
        return None
    text = _strip_strings(sql)
    for m in _RANK_OVER_RE.finditer(text):
        ok = _ORDER_KEY_RE.search(m.group(1))
        if ok:
            key = ok.group(1).split(".")[-1]
            if _is_id_like(key) or _is_metadata_date(key):
                return ("wrong ranking measure: results are ranked by '" + key
                        + "' (an id/metadata column), not by the requested "
                        "value/amount")
    return None


# ---------------------------------------------------------------------------
# Boolean-predicate validation (final stabilization, Part B): every WHERE /
# HAVING / JOIN ON / CASE WHEN condition must be an actual Boolean predicate.
# An arithmetic expression, a bare aggregate, or a bare non-flag column used
# as a condition (e.g. `HAVING total_billed - total_paid`) executes under
# SQLite's truthiness rules but is semantically meaningless — fatal.
# ---------------------------------------------------------------------------
_BOOL_FLAG_NAME_RE = re.compile(r"(^is_|^has_|^can_|flag|active|enabled|valid)",
                                re.IGNORECASE)


def boolean_predicate_violations(sql):
    """Fatal reasons for non-Boolean expressions used as conditions.
    AST-based (sqlglot); unknown/unparseable shapes are never flagged."""
    from sqlglot import exp as _e
    from sql_analysis import ast_tools as _at

    parsed = _at.parse_sql(sql)
    if not parsed.ok:
        return []
    valid_roots = (_e.EQ, _e.NEQ, _e.GT, _e.GTE, _e.LT, _e.LTE, _e.In,
                   _e.Between, _e.Like, _e.ILike, _e.Is, _e.Exists,
                   _e.Boolean, _e.Subquery)
    arithmetic = (_e.Add, _e.Sub, _e.Mul, _e.Div)
    out = []

    def _check(node, where_name):
        while isinstance(node, _e.Paren):
            node = node.this
        if node is None:
            return
        if isinstance(node, (_e.And, _e.Or)):
            _check(node.this, where_name)
            _check(node.expression, where_name)
            return
        if isinstance(node, _e.Not):
            _check(node.this, where_name)
            return
        if isinstance(node, valid_roots):
            return
        if isinstance(node, arithmetic) or isinstance(node, _e.AggFunc):
            out.append(
                "semantic violation: arithmetic expression is used as a "
                f"Boolean predicate without a comparison operator "
                f"({where_name}: {node.sql()[:60]})")
            return
        if isinstance(node, _e.Column) \
                and not _BOOL_FLAG_NAME_RE.search(node.name or ""):
            out.append(
                "semantic violation: arithmetic expression is used as a "
                f"Boolean predicate without a comparison operator "
                f"({where_name}: bare column {node.sql()[:40]})")
            return
        # anything else (functions, CASE, literals, unknown) — uncertain,
        # never flagged

    for scope in parsed.scopes:
        e = scope.expression
        where = e.args.get("where")
        if where is not None:
            _check(where.this, "WHERE")
        having = e.args.get("having")
        if having is not None:
            _check(having.this, "HAVING")
        for join in e.args.get("joins") or []:
            on = join.args.get("on")
            if on is not None:
                _check(on, "JOIN ON")
        for node in _at.scope_nodes(scope):
            if isinstance(node, _e.If) and node.args.get("this") is not None:
                _check(node.this, "CASE WHEN")
    return out


def sql_guard_violations(question, sql, checklist=None, idx=None):
    """All fatal semantic-guard reasons for this SQL (empty => clean)."""
    reasons = []
    for fn, args in (
        (cartesian_join_violation, (sql, question)),
        (uncorrelated_absence_violation, (sql, question)),
        (constant_measure_violation, (sql, question, checklist)),
        (ranking_measure_violation, (sql, question)),
    ):
        try:
            r = fn(*args)
        except Exception:
            r = None
        if r:
            reasons.append(r)
    try:
        reasons.extend(boolean_predicate_violations(sql))
    except Exception:
        pass
    return reasons
