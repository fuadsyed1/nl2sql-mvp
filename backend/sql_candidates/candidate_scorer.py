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
from schema.table_mention import explicit_table_mentions
from query_families.family_guard import (
    _join_edges,
    _collect,
    _wants_count_distinct,
    _COLUMN_CONCEPTS,
)
from semantic.semantic_checklist import (checklist_alignment, grain_alignment,
                                          literal_group_violations)
from sql_candidates.semantic_relationship_verifier import (
    verify_semantic_relationships,
)
from sql_candidates.semantic_join_discovery import (
    discover_semantic_join_issues,
)
from sql_candidates.explicit_table_lock import table_lock_penalty
from schema.value_profiler import literal_check
from sql_candidates.shape_verifier import verify_shape
from sql_candidates.semantic_sql_guards import sql_guard_violations
from validators.grain_validator import validate_grain
from validators.fanout_validator import validate_fanout
from validators.temporal_validator import validate_temporal

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
_OUTSIDE_TABLE = -18        # per schema table joined outside must_use_tables, max 3
_SEMANTIC_GUARD = -35       # per fatal semantic-guard violation (Cartesian, etc.)
_GRAIN_VIOLATION = -35      # per provable typed-contract grain violation

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


_SETOP_WORDS = ("union", "intersect", "except")


def _scope_ids(sql: str):
    """Per-character scope id. Each '(' opens a NEW id (sibling subqueries get
    different ids), ')' returns to the parent. Each branch of a set operation
    (UNION / UNION ALL / INTERSECT / EXCEPT) is ALSO a separate scope even when
    the branches are not parenthesized: a set-op keyword rotates the current
    scope id so the SELECT that follows it is a distinct scope. This makes alias
    reuse across independent UNION branches legal (reusing `p` in each branch is
    valid SQL — the branches never share a namespace), while alias reuse inside
    ONE scope (a real self-join with the same alias twice) is still detected."""
    ids, stack, next_id = [], [0], 1
    low = sql.lower()
    n = len(sql)
    prev_word_char = False
    for i, ch in enumerate(sql):
        if not prev_word_char:
            for kw in _SETOP_WORDS:
                if low.startswith(kw, i):
                    end = i + len(kw)
                    if end >= n or not (low[end].isalnum() or low[end] == "_"):
                        stack[-1] = next_id      # rotate current-level scope
                        next_id += 1
                        break
        if ch == "(":
            stack.append(next_id)
            next_id += 1
        ids.append(stack[-1])
        if ch == ")" and len(stack) > 1:
            stack.pop()
        prev_word_char = ch.isalnum() or ch == "_"
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


def _fk_reachable(allowed, idx, max_hops=3):
    """Tables reachable from `allowed` along the graph's relationship edges
    (undirected), within max_hops. These are legitimate join-path / bridge /
    measure tables, so using them is NOT 'outside' the intended scope."""
    adj = {}
    for r in (idx.get("relationships") or []):
        a = str(r.get("from_table") or "").lower()
        b = str(r.get("to_table") or "").lower()
        if not a or not b or a == b:
            continue
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    reach = set(allowed)
    frontier = set(allowed)
    for _ in range(max_hops):
        nxt = set()
        for t in frontier:
            nxt |= adj.get(t, set())
        nxt -= reach
        if not nxt:
            break
        reach |= nxt
        frontier = nxt
    return reach


def _sql_schema_tables(sql, idx):
    """Set of real schema tables referenced in FROM/JOIN (CTE/alias names that
    are not schema tables are ignored)."""
    tables = set()
    if not sql:
        return tables
    text = _strip_strings(sql)
    schema_tables = set(idx["tables"])
    for m in _DEF_RE.finditer(text):
        t = m.group(2).lower()
        if t in schema_tables:
            tables.add(t)
    return tables


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
                    value_profile=None, contract=None):
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
    # Only penalize omission of tables the question EXPLICITLY names (schema-like
    # name or an explicit table cue), not ordinary business nouns or a child
    # table matched through a parent concept. Uses the strict shared detector.
    missing_tables = []
    for t in explicit_table_mentions(question, list(idx["tables"].keys())):
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

    # 9b) Option C row-grain / universe alignment (advisory, penalty-only;
    #     NEVER fatal). Wrong GROUP BY grain, a missing required group key,
    #     or an every/all query hardcoding the universe size each subtract
    #     a few points and leave a reason the repair prompt can read.
    if checklist:
        try:
            g_delta, g_reasons, g_checks = grain_alignment(checklist, sql, idx)
            score += g_delta
            reasons.extend(g_reasons)
            checks["grain"] = {"delta": g_delta, **g_checks}
        except Exception as exc:
            checks["grain"] = {"error": f"{type(exc).__name__}: {exc}"}

    # 9c) Phase 2 semantic relationship / table-choice verifier
    #     (advisory, penalty-only; NEVER fatal). Penalizes unsupported
    #     key<->key joins, wrong same-shaped table choice, and dummy SQL,
    #     reusing the checklist, schema (declared FK / confirmed / HoPF
    #     evidence), and the already-parsed join edges. Reasons flow into
    #     candidate.reasons so repair can use them.
    try:
        v_delta, v_reasons, v_checks = verify_semantic_relationships(
            question, checklist, sql, idx, sql_edges=scan["sql_edges"])
        score += v_delta
        reasons.extend(v_reasons)
        checks["semantic_rel"] = v_checks
    except Exception as exc:
        checks["semantic_rel"] = {"error": f"{type(exc).__name__}: {exc}"}

    # 9d) Phase 3 semantic join discovery (advisory; reward OR penalty,
    #     NEVER fatal). Prefers candidates that take the right bridge/
    #     mapping table and table-purpose path; penalizes wrong-family
    #     tables and direct cross-granularity joins. Reasons flow to
    #     candidate.reasons for repair hints.
    try:
        j_delta, j_reasons, j_checks = discover_semantic_join_issues(
            question, checklist, sql, idx, sql_edges=scan["sql_edges"])
        score += j_delta
        reasons.extend(j_reasons)
        checks["semantic_join"] = j_checks
    except Exception as exc:
        checks["semantic_join"] = {"error": f"{type(exc).__name__}: {exc}"}

    # 9e) Explicit table lock (emergency fix; advisory but HEAVY, never
    #     fatal). When the question names real schema tables verbatim,
    #     penalize a candidate that swaps in a sibling/unmentioned table,
    #     ignores most named tables, or falls back to SELECT *.
    try:
        l_delta, l_reasons, l_checks = table_lock_penalty(question, sql, idx)
        score += l_delta
        reasons.extend(l_reasons)
        checks["table_lock"] = l_checks
    except Exception as exc:
        checks["table_lock"] = {"error": f"{type(exc).__name__}: {exc}"}

    # 9f) focused-table lock (fatal): on big / local-benchmark schemas a
    #     candidate must not join in schema tables OUTSIDE the checklist's
    #     must_use_tables. Shared keys (playerID, teamID, ...) otherwise invite
    #     huge, wrong, timeout-prone joins. Any table used beyond must_use_tables
    #     is penalized heavily and marked fatal — so a People-only query that
    #     JOINs another table is rejected.
    if checklist and (checklist.get("must_use_tables") or []):
        allowed = {str(t).lower() for t in checklist.get("must_use_tables") or []}
        # FK-reachable tables (bridges / measure / lookup on the join path) are
        # legitimate, not "outside": a query about Customer+Product may correctly
        # traverse SalesOrderHeader/Detail. Only a table with NO relationship path
        # to must_use_tables is a genuine out-of-scope join.
        reachable = _fk_reachable(allowed, idx)
        used = _sql_schema_tables(sql, idx)
        extra = sorted(t for t in used if t not in reachable)
        for t in extra[:3]:
            score += _OUTSIDE_TABLE
            reasons.append(
                f"joins table '{t}' with no relationship path to must_use_tables "
                f"{sorted(allowed)} — unnecessary for the requested columns")
        if extra:
            fatal.append(f"joins tables outside must_use_tables: {extra}")
        checks["outside_tables"] = extra
        checks["outside_tables_allowed_reachable"] = sorted(reachable - allowed)

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

    # 11) SQL semantic-shape verification (fatal: unresolved alias /
    #     self-comparison; penalties: weak universal, fake distinct,
    #     incomplete pair; report-only: latest-partition + grain notes) ------
    try:
        s_delta, s_reasons, s_fatal, s_checks = verify_shape(question, sql, idx)
    except Exception as exc:
        s_delta, s_reasons, s_fatal = 0.0, [], []
        s_checks = {"error": f"{type(exc).__name__}: {exc}"}
    score += s_delta
    reasons.extend(s_reasons)
    fatal.extend(s_fatal)
    checks["shape"] = s_checks

    # 12) generic FATAL semantic guards (Cartesian join, uncorrelated absence
    #     NOT EXISTS, constant used as a monetary measure, ranking by an id /
    #     metadata date when a value ranking was asked). These catch
    #     executes-but-nonsense candidates the shape/execution scores reward.
    try:
        guard_reasons = sql_guard_violations(question, sql, checklist, idx)
    except Exception as exc:
        guard_reasons = []
        checks["semantic_guards_error"] = f"{type(exc).__name__}: {exc}"
    for gr in guard_reasons:
        score += _SEMANTIC_GUARD
        reasons.append(gr)
        fatal.append(gr)
    checks["semantic_guards"] = guard_reasons

    # 12a) categorical literal completeness (final stabilization, Part E,
    #      FATAL): a high-confidence resolved literal group ("abnormal" ->
    #      ['high','low','critical']) must be applied; substituting the
    #      unresolved category word as a literal is provably wrong.
    try:
        lg_reasons = literal_group_violations(checklist, sql,
                                              params=candidate.params)
    except Exception as exc:
        lg_reasons = []
        checks["literal_groups_error"] = f"{type(exc).__name__}: {exc}"
    for gr in lg_reasons:
        score += _SEMANTIC_GUARD
        reasons.append(gr)
        fatal.append(gr)
    checks["literal_groups"] = lg_reasons

    # 12b) BOUNDED-SUBSET RATIO population alignment (FATAL). When the question is
    #      a bounded 0-100 subset percentage ("<subset> as a percentage of
    #      <population>"), a candidate whose denominator restricts to a
    #      sub-population that the numerator does NOT share is provably wrong (it
    #      can exceed 100%). High-confidence + high-precision: fires only when the
    #      SQL actually contains a ratio and the alignment check fails, so it can
    #      never touch an unbounded ratio (growth / vs-budget) or a non-ratio.
    try:
        from sql_candidates.semantic_obligations import (
            question_bounded_subset_ratio, ratio_population_aligned,
            _percent_values_out_of_bounds, _parse as _so_parse)
        _ratio_viol = None
        if question_bounded_subset_ratio(question):
            _rt = _so_parse(sql)
            # STRUCTURAL misalignment is the fatal signal (high precision: it
            # only fires when the denominator carries a population filter the
            # numerator lacks, which no correct subset candidate does).
            if not ratio_population_aligned(_rt):
                _ratio_viol = ("bounded-subset percentage: the denominator "
                               "population filter does not also constrain the "
                               "numerator, so the ratio can exceed 100%")
            # Execution plausibility is ADVISORY only (supplements, never
            # replaces the structural check) — a legitimately-unbounded ratio
            # mis-detected as bounded could exceed 100% for valid reasons, so an
            # out-of-range value is recorded as a warning, not a fatal.
            _oob = _percent_values_out_of_bounds(candidate.execution)
            if _oob is not None:
                reasons.append(
                    f"advisory: bounded percentage produced an out-of-range "
                    f"value ({_oob}) — check numerator/denominator population "
                    f"alignment")
                checks["ratio_percentage_out_of_bounds"] = _oob
        if _ratio_viol:
            score += _SEMANTIC_GUARD
            reasons.append(_ratio_viol)
            fatal.append(_ratio_viol)
        checks["ratio_population_aligned"] = _ratio_viol is None
    except Exception as exc:
        checks["ratio_population_error"] = f"{type(exc).__name__}: {exc}"

    # 12c) Stage 2 — cardinality-aware FANOUT validation (FATAL only on
    #      provable inflation: a measure aggregated in a scope where a
    #      one-to-many join multiplies its source rows, with no DISTINCT /
    #      preaggregation protection; unknown cardinality is never fatal).
    try:
        f = validate_fanout(sql, idx)
        for gr in f.fatal:
            score += _GRAIN_VIOLATION
            reasons.append(gr)
            fatal.append(gr)
        reasons.extend(f.warnings)
        checks["fanout"] = {"fatal": f.fatal, "warnings": f.warnings,
                            **f.checks}
    except Exception as exc:
        checks["fanout"] = {"error": f"{type(exc).__name__}: {exc}"}

    # 12b) typed-contract GRAIN validation (semantic-contract Stage 1).
    #      sqlglot AST analysis vs the typed GrainContract. FATAL only for
    #      provable, high-confidence grain violations (raw child-row value
    #      where a per-entity total was required; aggregate over raw rows
    #      where an aggregate of entity totals was required; bare child
    #      measure under entity grouping). A missing / low-confidence
    #      contract, parse failure, or any uncertain finding is skip/warning
    #      only — prior behavior is fully preserved in those cases.
    try:
        g = validate_grain(contract, sql, idx)
        for gr in g.fatal:
            score += _GRAIN_VIOLATION
            reasons.append(gr)
            fatal.append(gr)
        reasons.extend(g.warnings)
        checks["grain_contract"] = {"fatal": g.fatal, "warnings": g.warnings,
                                    "skipped": g.skipped, **g.checks}
    except Exception as exc:
        checks["grain_contract"] = {"error": f"{type(exc).__name__}: {exc}"}

    # 12e) temporal latest-event qualification (final temporal patch, FATAL
    #      only for provable, high-confidence after_extremum violations: the
    #      qualifier filters the rows the extremum is computed from).
    try:
        tv = validate_temporal(contract, sql, idx)
        for gr in tv.fatal:
            score += _GRAIN_VIOLATION
            reasons.append(gr)
            fatal.append(gr)
        reasons.extend(tv.warnings)
        checks["temporal_contract"] = {"fatal": tv.fatal,
                                       "warnings": tv.warnings,
                                       "skipped": tv.skipped, **tv.checks}
    except Exception as exc:
        checks["temporal_contract"] = {"error": f"{type(exc).__name__}: {exc}"}

    checks["fatal"] = fatal
    candidate.score = max(0.0, min(100.0, round(score, 1)))
    candidate.reasons = reasons
    candidate.validation = checks
    return candidate
