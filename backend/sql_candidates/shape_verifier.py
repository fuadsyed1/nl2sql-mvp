"""
sql_candidates/shape_verifier.py

Generic SQL semantic-shape verifier. Pure text analysis — no LLM, no database
execution, no schema-specific rules. Called by candidate_scorer before
selection so structurally suspicious SQL loses to clean candidates and the
repair round gets concrete issues to fix.

FATAL (objectively invalid SQL, can never be correct):
  F1  unresolved bare identifier in WHERE/HAVING/ON — a name that is not a
      schema column, defined alias, CTE (or its declared columns), or table
      (e.g. HAVING product_price > 100 with no such column/alias anywhere).
  F2  self-comparison — an expression compared to itself (x = x,
      COUNT(*) = COUNT(*)), including via two aliases defined by the same
      expression.

ACTIVE PENALTIES:
  P1  weak universal shape (-15): every/all intent answered by a plain
      HAVING COUNT(..) cmp COUNT(..) over the same row set (no subquery, no
      CASE) — there is no universe to compare against.
  P2  fake distinct count (-12): alias says distinct/unique but the defining
      expression is COUNT(col) without DISTINCT.
  P4  incomplete pair query (-10): 'pairs' intent, one table aliased twice,
      but no inequality between the two aliases (duplicate/self pairs).

REPORT-ONLY (recorded in checks + reasons, ZERO score effect for now):
  P3  latest/earliest partitioned by a non-entity (measure/date) column.
  P5  grouping-grain suspicion: correlated aggregate keyed on a column that
      is not in the outer GROUP BY.

Total active penalty is clamped to PENALTY_FLOOR so a fundamentally sound
candidate can never be sunk by shape penalties alone.
"""

import re

__all__ = ["verify_shape", "PENALTY_FLOOR"]

PENALTY_FLOOR = -25.0
_P1_WEAK_UNIVERSAL = -15.0
_P2_FAKE_DISTINCT = -12.0
_P4_INCOMPLETE_PAIR = -10.0

_KEYWORDS = {
    "select", "from", "where", "on", "join", "left", "right", "inner", "outer",
    "cross", "full", "group", "order", "by", "having", "limit", "offset",
    "union", "all", "distinct", "as", "and", "or", "not", "exists", "in",
    "is", "null", "like", "between", "case", "when", "then", "else", "end",
    "with", "using", "asc", "desc", "set", "values", "escape", "collate",
    "glob", "intersect", "except", "cast", "integer", "real", "text", "blob",
    "true", "false", "current_date", "current_time", "current_timestamp",
    "over", "partition", "rows", "range", "unbounded", "preceding",
    "following", "current", "row", "filter", "window", "recursive",
}

_STR_RE = re.compile(r"'(?:[^']|'')*'")
_IDENT_RE = re.compile(r'"?([A-Za-z_]\w*)"?')
_AS_NAME_RE = re.compile(r'\bAS\s+"?([A-Za-z_]\w*)"?', re.IGNORECASE)
# bare alias right after a closing paren: `ROW_NUMBER() OVER (...) rn`,
# `(SELECT ...) x`, `COUNT(*) cnt` — defined without the AS keyword
_BARE_ALIAS_RE = re.compile(r'\)\s*"?([A-Za-z_]\w*)"?', re.IGNORECASE)
_CTE_RE = re.compile(
    r'(?:\bWITH\b|,)\s*"?([A-Za-z_]\w*)"?\s*(\(([^()]*)\))?\s+AS\s*\(',
    re.IGNORECASE)
_DEF_RE = re.compile(
    r'\b(?:FROM|JOIN)\s+"?([A-Za-z_]\w*)"?'
    r'(?:\s+(?:AS\s+)?"?(?!(?:LEFT|RIGHT|INNER|OUTER|CROSS|FULL|JOIN|WHERE|ON'
    r'|GROUP|ORDER|HAVING|LIMIT|UNION|SET|USING|AND|OR|NOT|EXISTS|AS|SELECT)\b)'
    r'"?([A-Za-z_]\w*)"?)?',
    re.IGNORECASE)
_PRED_RE = re.compile(
    r"\b(WHERE|HAVING|\bON)\b(.*?)(?=\bWHERE\b|\bGROUP\s+BY\b|\bORDER\s+BY\b"
    r"|\bHAVING\b|\bLIMIT\b|\bUNION\b|\bSELECT\b|\bWINDOW\b|$)",
    re.IGNORECASE | re.DOTALL)
# simple operand: qualified/bare identifier or one-level function call
_OPERAND = (r"(?:[A-Za-z_]\w*\s*\.\s*)?[A-Za-z_\"]\w*\"?"
            r"(?:\s*\(\s*(?:DISTINCT\s+)?[^()]*?\))?")
_CMP_RE = re.compile(
    r"({op})\s*(=|!=|<>|<=|>=|<|>)\s*({op})".format(op=_OPERAND))
_AGG_ALIAS_RE = re.compile(
    r'([A-Za-z_]\w*\s*\(\s*(?:DISTINCT\s+)?[^()]*\))\s+AS\s+"?([A-Za-z_]\w*)"?',
    re.IGNORECASE)
_HAVING_COUNT_CMP_RE = re.compile(
    r"\bHAVING\b[^()]*?(COUNT\s*\([^()]*\))\s*(=|!=|<>|<=|>=|<|>)\s*"
    r"(COUNT\s*\([^()]*\))", re.IGNORECASE)
_FAKE_DISTINCT_RE = re.compile(
    r'\bCOUNT\s*\(\s*(?!DISTINCT\b)[^()]*\)\s+AS\s+'
    r'"?(\w*(?:distinct|unique)\w*)"?', re.IGNORECASE)
_PARTITION_RE = re.compile(
    r"PARTITION\s+BY\s+(?:[A-Za-z_]\w*\s*\.\s*)?\"?([A-Za-z_]\w*)\"?",
    re.IGNORECASE)
_GROUP_BY_RE = re.compile(r"\bGROUP\s+BY\s+(.*?)(?=\bHAVING\b|\bORDER\b|\bLIMIT\b|\)|$)",
                          re.IGNORECASE | re.DOTALL)

_UNIVERSAL_WORDS = re.compile(r"\b(every|all)\b", re.IGNORECASE)
_PAIR_WORDS = re.compile(r"\bpairs?\b", re.IGNORECASE)
_LATEST_WORDS = re.compile(r"\b(latest|earliest|most recent)\b", re.IGNORECASE)


def _norm_expr(s):
    return re.sub(r'[\s"]+', "", (s or "").lower())


def _schema_names(idx):
    cols, tables = set(), set()
    for t, cs in (idx.get("tables") or {}).items():
        tables.add(t.lower())
        for c in cs:
            cols.add(c["name"].lower())
    return cols, tables


def _defined_names(text):
    """Every name legitimately defined ANYWHERE in the statement (scope-blind
    on purpose — resolution is conservative so nothing definable is fatal)."""
    names = set()
    for m in _AS_NAME_RE.finditer(text):
        names.add(m.group(1).lower())
    for m in _BARE_ALIAS_RE.finditer(text):
        name = m.group(1).lower()
        if name not in _KEYWORDS:
            names.add(name)
    for m in _CTE_RE.finditer(text):
        names.add(m.group(1).lower())
        for col in (m.group(3) or "").split(","):
            col = col.strip().strip('"')
            if col:
                names.add(col.lower())
    for m in _DEF_RE.finditer(text):
        names.add(m.group(1).lower())
        alias = (m.group(2) or "").lower()
        if alias and alias not in _KEYWORDS:
            names.add(alias)
    return names


# ---------------------------------------------------------------------------
# F1: unresolved bare identifiers in predicates
# ---------------------------------------------------------------------------
def _unresolved_predicate_names(text, idx):
    cols, tables = _schema_names(idx)
    known = cols | tables | _defined_names(text) | _KEYWORDS
    out = []
    for m in _PRED_RE.finditer(text):
        region = m.group(2)
        for im in _IDENT_RE.finditer(region):
            name = im.group(1)
            low = name.lower()
            start, end = im.start(1), im.end(1)
            before = region[:start].rstrip()
            after = region[end:].lstrip().lstrip('"')
            if before.endswith(".") or before.endswith('."'):
                continue                     # qualified column part
            if after.startswith("(") or after.startswith("."):
                continue                     # function call / qualifier
            if low in known or low.isdigit():
                continue
            if low not in {x["name"] for x in ()} and low not in out:
                out.append(low)
    return out


# ---------------------------------------------------------------------------
# F2: self-comparison (direct or via duplicate aliases)
# ---------------------------------------------------------------------------
def _self_comparisons(text):
    out = []
    for m in _CMP_RE.finditer(text):
        a, b = _norm_expr(m.group(1)), _norm_expr(m.group(3))
        if a and a == b:
            out.append(f"{m.group(1).strip()} {m.group(2)} {m.group(3).strip()}")
    alias_expr = {}
    for m in _AGG_ALIAS_RE.finditer(text):
        alias_expr[m.group(2).lower()] = _norm_expr(m.group(1))
    for m in _CMP_RE.finditer(text):
        a = alias_expr.get(_norm_expr(m.group(1)))
        b = alias_expr.get(_norm_expr(m.group(3)))
        if a and b and a == b and _norm_expr(m.group(1)) != _norm_expr(m.group(3)):
            out.append(f"aliases '{m.group(1).strip()}' and '{m.group(3).strip()}' "
                       "are the same expression")
    return out


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def verify_shape(question, sql, idx):
    """-> (delta, reasons, fatal, checks). Never raises on any input."""
    reasons, fatal, delta = [], [], 0.0
    checks = {"fatal": [], "penalties": [], "report_only": []}
    if not sql:
        return 0.0, reasons, fatal, checks
    text = _STR_RE.sub("''", sql)
    q = " " + str(question or "").lower() + " "

    # F1 ---------------------------------------------------------------
    for name in _unresolved_predicate_names(text, idx)[:2]:
        msg = (f"unresolved identifier '{name}' used in WHERE/HAVING/ON — "
               "not a column, alias, or CTE defined anywhere in the query")
        fatal.append(msg)
        reasons.append(msg)
        checks["fatal"].append({"code": "F1", "name": name})

    # F2 ---------------------------------------------------------------
    for cmp_txt in _self_comparisons(text)[:2]:
        msg = f"self-comparison is always true/false: {cmp_txt}"
        fatal.append(msg)
        reasons.append(msg)
        checks["fatal"].append({"code": "F2", "cmp": cmp_txt})

    # P1 weak universal --------------------------------------------------
    if _UNIVERSAL_WORDS.search(q):
        m = _HAVING_COUNT_CMP_RE.search(text)
        if m and "select" not in (m.group(0).lower()) \
                and "case" not in m.group(0).lower():
            delta += _P1_WEAK_UNIVERSAL
            msg = ("universal (every/all) intent answered by comparing two "
                   "plain COUNTs over the same rows — no universe comparison")
            reasons.append(msg)
            checks["penalties"].append({"code": "P1", "delta": _P1_WEAK_UNIVERSAL})

    # P2 fake distinct ----------------------------------------------------
    m = _FAKE_DISTINCT_RE.search(text)
    if m:
        delta += _P2_FAKE_DISTINCT
        msg = (f"alias '{m.group(1)}' claims distinct but the expression is "
               "COUNT(...) without DISTINCT")
        reasons.append(msg)
        checks["penalties"].append({"code": "P2", "delta": _P2_FAKE_DISTINCT,
                                    "alias": m.group(1)})

    # P4 incomplete pair ---------------------------------------------------
    if _PAIR_WORDS.search(q):
        base_aliases = {}
        for dm in _DEF_RE.finditer(text):
            table = dm.group(1).lower()
            alias = (dm.group(2) or table).lower()
            base_aliases.setdefault(table, set()).add(alias)
        doubled = {t: a for t, a in base_aliases.items() if len(a) >= 2}
        if doubled:
            has_ineq = False
            for t, aliases in doubled.items():
                pat = r"({a})\s*\.\s*\"?\w+\"?\s*(<|>|<>|!=)\s*({a})\s*\.".format(
                    a="|".join(re.escape(x) for x in aliases))
                if re.search(pat, text, re.IGNORECASE):
                    has_ineq = True
                    break
            if not has_ineq:
                delta += _P4_INCOMPLETE_PAIR
                msg = ("pair intent with a doubled table but no inequality "
                       "between the two aliases (self/duplicate pairs leak in)")
                reasons.append(msg)
                checks["penalties"].append({"code": "P4",
                                            "delta": _P4_INCOMPLETE_PAIR})

    # P3 report-only: latest/earliest partition sanity ----------------------
    if _LATEST_WORDS.search(q):
        cols, _ = _schema_names(idx)
        for pm in _PARTITION_RE.finditer(text):
            col = pm.group(1).lower()
            meta = None
            for cs in (idx.get("tables") or {}).values():
                for c in cs:
                    if c["name"] == col:
                        meta = c
                        break
            if meta is not None and (meta.get("is_date") or
                                     (meta.get("is_numeric") and not meta.get("is_key"))):
                checks["report_only"].append(
                    {"code": "P3", "note": f"latest/earliest partitioned by "
                     f"non-entity column '{col}' (report-only)"})
                reasons.append(f"[report-only] latest/earliest partitioned by "
                               f"non-entity column '{col}'")
                break

    # P5 report-only: grouping-grain suspicion ------------------------------
    gb = _GROUP_BY_RE.search(text)
    if gb:
        gcols = {c.strip().strip('"').split(".")[-1].strip().strip('"').lower()
                 for c in gb.group(1).split(",") if c.strip()}
        for cm in re.finditer(
                r"\(\s*SELECT\s+(?:MAX|MIN|AVG|SUM|COUNT)\b[^()]*"
                r"\bWHERE\b[^()]*?\.\s*\"?(\w+)\"?\s*=", text, re.IGNORECASE):
            corr = cm.group(1).lower()
            if gcols and corr not in gcols:
                checks["report_only"].append(
                    {"code": "P5", "note": f"correlated aggregate keyed on "
                     f"'{corr}' which is not in GROUP BY (report-only)"})
                reasons.append(f"[report-only] correlated aggregate keyed on "
                               f"'{corr}' not in GROUP BY")
                break

    return max(PENALTY_FLOOR, delta), reasons, fatal, checks
