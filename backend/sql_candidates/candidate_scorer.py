"""
sql_candidates/candidate_scorer.py

Validation scoring for SQL candidates. The purpose is to make WRONG-BUT-
EXECUTABLE SQL score low: execution success is worth points, but far fewer
than the structural/semantic checks combined, so a candidate that runs yet
ignores the question's required shape (NOT EXISTS for "never", LEFT JOIN for
outer-join intent, COUNT(DISTINCT) for distinct counts, CTE/window for
top-per-group) or joins illegally can never outscore a structurally right one.

score_candidate(question, candidate, graph) -> mutates candidate.score /
candidate.reasons / candidate.validation and returns the candidate.

Checks (start at BASE=50, clamp 0..100):
  execution        executed +25 / failed -40 / no SQL produced -45 / empty -3
  joins            illegal join or correlation (extraction- AND sql-level) -40 each
  columns          referenced column missing from schema -20 each
  question mention clearly-named table absent from candidate -12 each
                   concept (brand/flavor/city/...) named but unused -8 each
  required shape   absence intent w/o NOT EXISTS|NOT IN|LEFT JOIN+IS NULL -20 (+8 ok)
                   outer intent w/o LEFT JOIN -20 (+8 ok)
                   distinct-count intent w/o COUNT(DISTINCT) -15 (+6 ok)
                   top-per-group intent w/o window/CTE/correlated agg -15 (+6 ok)
  aliases          duplicate table alias in same scope -25; undefined alias -25
  output           executed but zero result columns -10
  family guard     family candidate whose guard rejected it -15

This module intentionally REUSES the semantic helpers in
query_families.family_guard / slot_extractor (single source of truth for
join legality and concept checks) rather than duplicating them.
"""

import re

from query_families import slot_extractor as se
from query_families.family_guard import (
    _join_edges,
    _collect,
    _wants_count_distinct,
    _COLUMN_CONCEPTS,
)
from semantic.semantic_checklist import checklist_alignment
from schema.value_profiler import literal_check

__all__ = ["score_candidate", "BASE_SCORE", "LOW_SCORE_THRESHOLD"]

BASE_SCORE = 50.0
LOW_SCORE_THRESHOLD = 40.0

# points
_EXEC_OK = +25
_EXEC_FAIL = -40
_NO_SQL = -45
_EMPTY_RESULT = -3
_ILLEGAL_JOIN = -40          # per distinct illegal pair, max 2 counted
_UNKNOWN_COLUMN = -20        # per distinct missing column, max 3 counted
_MISSING_TABLE = -12         # per clearly-mentioned table absent, max 3
_MISSING_CONCEPT = -8        # per concept named but unused, max 3
_SHAPE = {
    "not_exists":    (-20, +8),
    "left_join":     (-20, +8),
    "count_distinct": (-15, +6),
    "top_per_group": (-15, +6),
}
_DUP_ALIAS = -25
_UNDEF_ALIAS = -25
_NO_OUTPUT_COLUMNS = -10
_GUARD_INVALID = -15
_BARE_CTE = -20
_UNSEEN_LITERAL = -12       # per literal not among sampled column values, max 2

# Comparison/superlative intent: a bare `WITH cte AS (...) SELECT * FROM cte`
# that computes per-entity values but never APPLIES the comparison must not win.
_COMPARE_WORDS = ("more than", "fewer than", "less than", "greater than",
                  "higher than", "lower than", " above ", " below ",
                  "highest", "lowest", " most ", " least ", " top ",
                  "cheapest", "most expensive", "second highest",
                  "second lowest", "maximum", "minimum", "at least",
                  "at most", "exceed")

# Final top-level `SELECT ... FROM <name>` with nothing after it (no WHERE /
# JOIN / GROUP / ORDER / parens) at the very end of a WITH query.
_BARE_FINAL_RE = re.compile(
    r'\)\s*SELECT\s+[^()]*?\bFROM\s+"?([A-Za-z_]\w*)"?\s*;?\s*$',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# SQL-text helpers (alias scanning, scope tracking, join extraction)
# ---------------------------------------------------------------------------
_SQL_KEYWORDS = {
    "select", "from", "where", "on", "join", "left", "right", "inner", "outer",
    "cross", "full", "group", "order", "by", "having", "limit", "offset",
    "union", "all", "distinct", "as", "and", "or", "not", "exists", "in",
    "is", "null", "like", "between", "case", "when", "then", "else", "end",
    "with", "using", "asc", "desc", "set", "values",
}


def _strip_strings(sql: str) -> str:
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def _scope_ids(sql: str):
    """Per-character scope id. Each '(' opens a NEW id (sibling subqueries get
    different ids), ')' returns to the parent."""
    ids, stack, next_id = [], [0], 1
    for ch in sql:
        if ch == "(":
            stack.append(next_id)
            next_id += 1
        ids.append(stack[-1])
        if ch == ")" and len(stack) > 1:
            stack.pop()
    return ids


_DEF_RE = re.compile(
    r'\b(FROM|JOIN)\s+"?([A-Za-z_]\w*)"?'
    r'(?:\s+(?:AS\s+)?"?'
    r'(?!(?:LEFT|RIGHT|INNER|OUTER|CROSS|FULL|JOIN|WHERE|ON|GROUP|ORDER'
    r'|HAVING|LIMIT|UNION|SET|USING|AND|OR|NOT|EXISTS|AS|SELECT)\b)'
    r'([A-Za-z_]\w*)"?)?',
    re.IGNORECASE,
)
_SUBQ_ALIAS_RE = re.compile(r'\)\s*(?:AS\s+)?"?([A-Za-z_]\w*)"?', re.IGNORECASE)
_CTE_RE = re.compile(r'(?:\bWITH\b|,)\s*"?([A-Za-z_]\w*)"?\s+AS\s*\(', re.IGNORECASE)
_REF_RE = re.compile(r'"?([A-Za-z_]\w*)"?\s*\.\s*"?(?:[A-Za-z_]\w*|\*)"?')
_EQ_JOIN_RE = re.compile(
    r'"?([A-Za-z_]\w*)"?\s*\.\s*"?([A-Za-z_]\w*)"?\s*=\s*'
    r'"?([A-Za-z_]\w*)"?\s*\.\s*"?([A-Za-z_]\w*)"?'
)


def _scan_sql(sql: str, idx):
    """One pass over the SQL text. Returns dict with:
    duplicates   [(scope, alias)] defined twice in the same scope
    undefined    [qualifier] referenced via `q.col` but never defined
    sql_edges    [(t1,c1,t2,c2)] alias-resolved equality joins/correlations
    """
    out = {"duplicates": [], "undefined": [], "sql_edges": []}
    if not sql:
        return out
    text = _strip_strings(sql)
    scopes = _scope_ids(text)
    schema_tables = set(idx["tables"])

    cte_names = {m.group(1).lower() for m in _CTE_RE.finditer(text)}

    defs = {}            # (scope, qualifier) -> count
    alias_to_table = {}  # qualifier -> base table (real tables only)
    qualifiers = set()

    for m in _DEF_RE.finditer(text):
        table = m.group(2).lower()
        alias = (m.group(3) or "").lower()
        if alias in _SQL_KEYWORDS:
            alias = ""
        qualifier = alias or table
        scope = scopes[m.start()]
        defs[(scope, qualifier)] = defs.get((scope, qualifier), 0) + 1
        qualifiers.add(qualifier)
        if table in schema_tables:
            alias_to_table.setdefault(qualifier, table)

    for m in _SUBQ_ALIAS_RE.finditer(text):
        name = m.group(1).lower()
        if name not in _SQL_KEYWORDS:
            qualifiers.add(name)

    out["duplicates"] = [k for k, n in defs.items() if n > 1]

    known = qualifiers | schema_tables | cte_names
    seen_undef = set()
    for m in _REF_RE.finditer(text):
        q = m.group(1).lower()
        if q not in known and q not in _SQL_KEYWORDS and q not in seen_undef:
            seen_undef.add(q)
            out["undefined"].append(q)

    seen_edges = set()
    for m in _EQ_JOIN_RE.finditer(text):
        q1, c1, q2, c2 = (m.group(i).lower() for i in (1, 2, 3, 4))
        t1 = alias_to_table.get(q1, q1)
        t2 = alias_to_table.get(q2, q2)
        if t1 in schema_tables and t2 in schema_tables:
            key = tuple(sorted([(t1, c1), (t2, c2)]))
            if key not in seen_edges:
                seen_edges.add(key)
                out["sql_edges"].append((t1, c1, t2, c2))
    return out


# ---------------------------------------------------------------------------
# extraction helpers
# ---------------------------------------------------------------------------
def _column_pairs(obj, pairs):
    """Collect every (table, column) reference in an extraction."""
    if isinstance(obj, dict):
        t, c = obj.get("table"), obj.get("column")
        if isinstance(t, str) and isinstance(c, str):
            pairs.append((t.lower(), c.lower()))
        for a, b in (("from_table", "from_column"), ("to_table", "to_column")):
            if isinstance(obj.get(a), str) and isinstance(obj.get(b), str):
                pairs.append((obj[a].lower(), obj[b].lower()))
        for v in obj.values():
            _column_pairs(v, pairs)
    elif isinstance(obj, list):
        for x in obj:
            _column_pairs(x, pairs)


def _unknown_columns(extraction, idx):
    pairs = []
    _column_pairs(extraction or {}, pairs)
    schema = idx["tables"]
    missing = []
    for t, c in dict.fromkeys(pairs):
        if c == "*" or t not in schema:      # CTE/alias table names are skipped
            continue
        if not any(col["name"] == c for col in schema[t]):
            missing.append(f"{t}.{c}")
    return missing


# ---------------------------------------------------------------------------
# question-intent detection (keyword-gated, mirrors family_guard vocabulary)
# ---------------------------------------------------------------------------
_ABSENCE_WORDS = ("never ", "no matching", "not purchased", "not fed",
                  "not bought", "without matching", "has no ", "have no ",
                  "does not exist", "not eaten", "not prescribed",
                  "never actually", "never purchased", "never ate")
_OUTER_WORDS = ("outer join", "left join", "include unmatched", "still visible",
                "unmatched", "no matching record", "even when no",
                "even if no", "including those without")
_TPG_RE = re.compile(
    r"\b(highest|lowest|most|least|latest|earliest|cheapest|second[- ]highest"
    r"|second[- ]lowest|top|maximum|minimum|most expensive|best)\b"
    r".{0,60}\b(per|for each|for every|within (each|their|its)|in each"
    r"|of (each|every))\b")
_TPG_ALT = ("second highest", "second-highest", "second lowest")


def _q(question):
    return " " + str(question or "").lower().strip() + " "


def _any(q, words):
    return any(w in q for w in words)


def _required_shapes(q):
    shapes = {}
    if _any(q, _ABSENCE_WORDS):
        shapes["not_exists"] = True
    if _any(q, _OUTER_WORDS):
        shapes["left_join"] = True
    if _wants_count_distinct(q):
        shapes["count_distinct"] = True
    if _TPG_RE.search(q) or _any(q, _TPG_ALT):
        shapes["top_per_group"] = True
    return shapes


def _shape_present(shape, sql_upper):
    if shape == "not_exists":
        return ("NOT EXISTS" in sql_upper or "NOT IN" in sql_upper
                or ("LEFT JOIN" in sql_upper and " IS NULL" in sql_upper))
    if shape == "left_join":
        return "LEFT JOIN" in sql_upper or "LEFT OUTER JOIN" in sql_upper
    if shape == "count_distinct":
        return bool(re.search(r"COUNT\s*\(\s*DISTINCT", sql_upper))
    if shape == "top_per_group":
        return ("OVER" in sql_upper and "(" in sql_upper) or "WITH " in sql_upper \
            or bool(re.search(r"\(\s*SELECT\s+(MAX|MIN|AVG|COUNT|SUM)\b", sql_upper))
    return False


def _bare_cte_final(sql):
    """The CTE name when the query is `WITH ... SELECT ... FROM <cte>` with no
    filter/comparison in the final select; else None."""
    text = _strip_strings(sql or "").strip()
    if not re.match(r"\s*WITH\b", text, re.IGNORECASE):
        return None
    m = _BARE_FINAL_RE.search(text)
    if not m:
        return None
    tail = m.group(0).upper()
    if any(k in tail for k in (" WHERE ", " GROUP ", " HAVING ",
                               " ORDER ", " LIMIT ", " JOIN ")):
        return None
    name = m.group(1).lower()
    cte_names = {c.lower() for c in _CTE_RE.findall(text)}
    return name if name in cte_names else None


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def score_candidate(question, candidate, graph, checklist=None,
                    value_profile=None):
    """Score one candidate in place. Never raises.

    Also populates candidate.validation["fatal"] — hard-disqualification
    reasons (illegal join, bare CTE under comparison intent, guard-rejected
    family output, question-anchored missing concept). A candidate with fatal
    reasons still gets a score, but the selector will not let it win unless
    every candidate is bad.
    """
    idx = se.index_schema(graph)
    q = _q(question)
    sql = candidate.sql or ""
    sql_upper = sql.upper()
    score = BASE_SCORE
    reasons = []
    checks = {}
    fatal = []

    # 1) execution --------------------------------------------------------
    if not sql:
        score += _NO_SQL
        reasons.append("no SQL produced (invalid IR / unresolved plan / generation failure)")
        checks["executed"] = False
    elif candidate.executed_ok:
        score += _EXEC_OK
        checks["executed"] = True
        if not (candidate.execution.get("columns") or []):
            score += _NO_OUTPUT_COLUMNS
            reasons.append("executed but returned no result columns")
        if candidate.execution.get("row_count", 0) == 0:
            score += _EMPTY_RESULT
            reasons.append("executed but returned zero rows (weak signal)")
    else:
        score += _EXEC_FAIL
        checks["executed"] = False
        err = (candidate.execution or {}).get("error")
        reasons.append(f"execution failed: {err or (candidate.execution or {}).get('reason')}")

    extraction = candidate.extraction or {}

    # 2) join legality (extraction-level + sql-level, deduped) -------------
    illegal = []
    seen_pairs = set()
    try:
        for (t1, c1, t2, c2) in _join_edges(extraction):
            key = tuple(sorted([(t1, c1), (t2, c2)]))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            if not se.is_legal_edge(idx, t1, c1, t2, c2):
                illegal.append(f"{t1}.{c1} = {t2}.{c2}")
    except Exception:
        pass
    scan = _scan_sql(sql, idx)
    for (t1, c1, t2, c2) in scan["sql_edges"]:
        key = tuple(sorted([(t1, c1), (t2, c2)]))
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        if not se.is_legal_edge(idx, t1, c1, t2, c2):
            illegal.append(f"{t1}.{c1} = {t2}.{c2}")
    for pair in illegal[:2]:
        score += _ILLEGAL_JOIN
        reasons.append(f"illegal join/correlation {pair} (not a declared FK; e.g. key = measure)")
    checks["illegal_joins"] = illegal
    if illegal:
        fatal.append(f"illegal join: {illegal[0]}")

    # 3) referenced columns exist ------------------------------------------
    missing_cols = _unknown_columns(extraction, idx)
    for mc in missing_cols[:3]:
        score += _UNKNOWN_COLUMN
        reasons.append(f"referenced column does not exist: {mc}")
    checks["unknown_columns"] = missing_cols

    # 4) clearly-mentioned tables / concepts represented -------------------
    used_tables, used_cols, _flags = set(), set(), {}
    try:
        used_tables, used_cols, _flags = _collect(extraction, idx)
    except Exception:
        pass
    sql_lower = sql.lower()
    missing_tables = []
    for t in se.mentioned_tables(question, idx):
        if t not in used_tables and not re.search(
                r"(?<![a-z0-9_])" + re.escape(t) + r"(?![a-z0-9_])", sql_lower):
            missing_tables.append(t)
    for mt in missing_tables[:3]:
        score += _MISSING_TABLE
        reasons.append(f"question names table '{mt}' but the candidate never uses it")
    checks["missing_tables"] = missing_tables

    missing_concepts = []
    for name, triggers, subs in _COLUMN_CONCEPTS:
        if _any(q, triggers):
            in_cols = any(any(s in c for s in subs) for c in used_cols)
            in_sql = any(s in sql_lower for s in subs)
            if not (in_cols or in_sql):
                missing_concepts.append(name)
    for mc in missing_concepts[:3]:
        score += _MISSING_CONCEPT
        reasons.append(f"concept '{mc}' mentioned in the question but no matching column is used")
    checks["missing_concepts"] = missing_concepts

    # 5) required SQL shape -------------------------------------------------
    shape_results = {}
    for shape in _required_shapes(q):
        present = bool(sql) and _shape_present(shape, sql_upper)
        shape_results[shape] = present
        penalty, bonus = _SHAPE[shape]
        if present:
            score += bonus
        else:
            score += penalty
            label = {
                "not_exists": "absence intent ('never/no/not ...') but no NOT EXISTS / NOT IN / LEFT JOIN+IS NULL",
                "left_join": "outer-join intent but no LEFT JOIN",
                "count_distinct": "distinct-count intent but no COUNT(DISTINCT)",
                "top_per_group": "top-per-group intent but no window function / CTE / correlated aggregate",
            }[shape]
            reasons.append(label)
    checks["required_shapes"] = shape_results

    # 6) alias sanity --------------------------------------------------------
    if scan["duplicates"]:
        score += _DUP_ALIAS
        dups = ", ".join(sorted({a for _, a in scan["duplicates"]}))
        reasons.append(f"duplicate table alias in the same scope: {dups}")
    if scan["undefined"]:
        score += _UNDEF_ALIAS
        reasons.append(f"undefined alias referenced: {', '.join(scan['undefined'])}")
    checks["duplicate_aliases"] = [a for _, a in scan["duplicates"]]
    checks["undefined_aliases"] = scan["undefined"]

    # 7) family guard verdict (family candidates only) ----------------------
    if candidate.family_info is not None and candidate.family_info.get("guard_valid") is False:
        score += _GUARD_INVALID
        reasons.append("family guard rejected this output: "
                       + "; ".join(candidate.family_info.get("guard_reasons") or []))
        fatal.append("family guard rejected this output")
    checks["guard_valid"] = (candidate.family_info or {}).get("guard_valid")

    # 8) bare CTE under comparison intent (Stage 1 hard check) ---------------
    bare_cte = _bare_cte_final(sql)
    if bare_cte and _any(q, _COMPARE_WORDS):
        score += _BARE_CTE
        reasons.append(f"question asks a comparison but the final SELECT just "
                       f"dumps CTE '{bare_cte}' without applying it")
        fatal.append(f"bare CTE '{bare_cte}' never applies the comparison")
    checks["bare_cte"] = bare_cte

    # 9) semantic-checklist alignment (Stage 2, strongest signal) ------------
    if checklist:
        try:
            delta, cl_reasons, cl_fatal, cl_checks = checklist_alignment(
                question, checklist, sql, idx, params=candidate.params)
            score += delta
            reasons.extend(cl_reasons)
            fatal.extend(cl_fatal)
            checks["checklist"] = {"delta": delta, **cl_checks}
        except Exception as exc:
            checks["checklist"] = {"error": f"{type(exc).__name__}: {exc}"}

    # 10) value grounding: literals not among a profiled column's values ------
    if value_profile:
        try:
            unseen = literal_check(sql, extraction, value_profile)
        except Exception:
            unseen = []
        for v in unseen[:2]:
            score += _UNSEEN_LITERAL
            reasons.append(
                f"literal '{v['literal']}' is not among the sampled values of "
                f"column '{v['column']}' (known: {v['known_values']})")
        checks["unseen_literals"] = unseen

    checks["fatal"] = fatal
    candidate.score = max(0.0, min(100.0, round(score, 1)))
    candidate.reasons = reasons
    candidate.validation = checks
    return candidate
