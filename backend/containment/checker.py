"""
containment/checker.py

Live-database containment checking via SQL EXCEPT.

Given two already-generated, already-validated SELECT statements (and their
bound params), this module checks — on the CURRENT SQLite database only —
whether Query 1's result set is contained in Query 2's:

    SELECT * FROM (<SQL_1>) EXCEPT SELECT * FROM (<SQL_2>)   -- forward
    SELECT * FROM (<SQL_2>) EXCEPT SELECT * FROM (<SQL_1>)   -- reverse

Non-empty forward result  => Query 1 is NOT contained in Query 2 (counterexample).
Empty forward result      => contained on the current database.
Both empty               => equivalent on the current database.

This is a data-dependent check, not a symbolic proof: it can DISPROVE
containment with a real counterexample, but can only confirm containment for the
rows currently present. Randomized test DBs and symbolic proof come later.

The module never writes: it opens the DB read-only (file:...?mode=ro) exactly
like generation/sql_executor.py, binds params positionally (never interpolated),
and never raises SQLite errors to the caller.
"""

import re
import sqlite3

from db.database_service import get_database_path

__all__ = [
    "COUNTEREXAMPLE_ROW_LIMIT",
    "unsupported_shape",
    "check_live_containment",
    "build_key_comparison",
    "is_group_by",
    "build_group_key_comparison",
    "is_distinct",
    "build_distinct_key_comparison",
    "is_scalar_aggregate",
    "unsupported_containment_shape",
    "REASON_SETOP",
    "REASON_LIMIT",
    "REASON_SCALAR_AGG",
    "REASON_NO_COMMON_KEY",
]

# ---------------------------------------------------------------------------
# Step 4: centralized, deterministic refusal reasons for shapes we do NOT
# normalize yet. Kept as constants so the same wording is reused everywhere and
# is easy to assert in tests.
# ---------------------------------------------------------------------------
REASON_SETOP = "set operations are not supported for containment normalization"
REASON_LIMIT = "limit/top-k queries are not safe for containment normalization"
REASON_SCALAR_AGG = "scalar aggregate outputs are not safe for containment comparison"
REASON_NO_COMMON_KEY = "queries do not expose a common comparable key"

# Cap on counterexample rows returned for display.
COUNTEREXAMPLE_ROW_LIMIT = 20

# Any of these keywords => not a safe read-only single SELECT we will wrap.
_WRITE_OR_DDL_RE = re.compile(
    r"(?i)\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|"
    r"ATTACH|DETACH|PRAGMA|VACUUM|REINDEX|GRANT|REVOKE)\b"
)
# A top-level LIMIT (with or without ORDER BY) changes which rows are in the
# set, so wrapping it in EXCEPT would compare truncated/ordered subsets. Reject.
_LIMIT_RE = re.compile(r"(?i)\bLIMIT\b")


def _strip_trailing_semicolons(sql: str) -> str:
    """Remove trailing whitespace and semicolons so the SQL can be wrapped in a
    subquery. Only trailing ';' are stripped; an interior ';' means multiple
    statements and is rejected separately."""
    return re.sub(r"[;\s]+$", "", sql or "")


def sanitize(sql: str) -> tuple[str | None, str | None]:
    """Return (clean_sql, error). clean_sql is None when the SQL is rejected.

    Guarantees a single, read-only SELECT/WITH statement safe to wrap in a
    subquery. Rejects empty SQL, multiple statements, non-SELECT statements,
    and any write/DDL/PRAGMA keyword.
    """
    if not sql or not sql.strip():
        return None, "empty SQL text"

    clean = _strip_trailing_semicolons(sql.strip())
    if not clean:
        return None, "empty SQL text"

    # No interior statement separators — one statement only.
    if ";" in clean:
        return None, "multiple SQL statements are not allowed"

    head = clean.lstrip("(").lstrip()
    if not re.match(r"(?i)^(SELECT|WITH)\b", head):
        return None, "only SELECT / WITH ... SELECT statements are supported"

    if _WRITE_OR_DDL_RE.search(clean):
        return None, "write/DDL statements are not allowed"

    return clean, None


def unsupported_shape(sql: str) -> str | None:
    """Return a reason string if `sql` cannot be safely wrapped for EXCEPT, else
    None. Used by the service safety gate BEFORE any execution."""
    clean, err = sanitize(sql)
    if err:
        return err
    if _LIMIT_RE.search(clean):
        return "SQL uses LIMIT (and possibly ORDER BY); cannot be safely wrapped for containment"
    return None


def _wrap_except(sql_a: str, sql_b: str) -> str:
    """Build `SELECT * FROM (A) EXCEPT SELECT * FROM (B)` with the inner SQL
    unchanged. Placeholder order is preserved (A's params come before B's)."""
    return (
        f"SELECT * FROM (\n{sql_a}\n) AS __containment_a\n"
        f"EXCEPT\n"
        f"SELECT * FROM (\n{sql_b}\n) AS __containment_b"
    )


def _run_readonly(db_path: str, sql: str, params: list, row_limit: int) -> dict:
    """Execute one wrapped EXCEPT read-only. Never raises SQLite errors."""
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        return {"ok": False, "error": f"database unavailable: {exc}"}
    try:
        cursor = conn.cursor()
        cursor.execute(sql, list(params or []))
        columns = [d[0] for d in (cursor.description or [])]
        fetched = cursor.fetchmany(row_limit + 1)
        truncated = len(fetched) > row_limit
        rows = [list(r) for r in (fetched[:row_limit] if truncated else fetched)]
        return {"ok": True, "columns": columns, "rows": rows, "truncated": truncated}
    except sqlite3.Error as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        conn.close()


def check_live_containment(
    database_id: int,
    sql1: str,
    params1: list,
    sql2: str,
    params2: list,
    *,
    row_limit: int = COUNTEREXAMPLE_ROW_LIMIT,
) -> dict:
    """Run both EXCEPT directions on the current database.

    Returns a normalized dict (the service turns it into a verdict):
        {
          "ran": bool,               # True only if both directions executed
          "error": str | None,       # populated when ran is False
          "columns": [...],          # counterexample columns (forward direction)
          "forward_rows": [...],     # SQL1 EXCEPT SQL2 (capped)
          "forward_truncated": bool,
          "reverse_rows": [...],     # SQL2 EXCEPT SQL1 (capped)
          "reverse_truncated": bool,
        }
    Assumes the safety gate already confirmed both SQLs exist and their output
    columns match; still re-sanitizes defensively so it is safe standalone.
    """
    clean1, err1 = sanitize(sql1)
    if err1:
        return {"ran": False, "error": f"query1: {err1}"}
    clean2, err2 = sanitize(sql2)
    if err2:
        return {"ran": False, "error": f"query2: {err2}"}

    db_path = get_database_path(database_id)
    if not db_path:
        return {"ran": False, "error": "database path not found"}

    p1 = list(params1 or [])
    p2 = list(params2 or [])

    forward = _run_readonly(db_path, _wrap_except(clean1, clean2), p1 + p2, row_limit)
    if not forward["ok"]:
        return {"ran": False, "error": f"forward EXCEPT failed: {forward['error']}"}

    reverse = _run_readonly(db_path, _wrap_except(clean2, clean1), p2 + p1, row_limit)
    if not reverse["ok"]:
        return {"ran": False, "error": f"reverse EXCEPT failed: {reverse['error']}"}

    return {
        "ran": True,
        "error": None,
        "columns": forward["columns"],
        "forward_rows": forward["rows"],
        "forward_truncated": forward["truncated"],
        "reverse_rows": reverse["rows"],
        "reverse_truncated": reverse["truncated"],
    }


# ---------------------------------------------------------------------------
# Step 1: canonical-key projection for containment comparison ONLY.
#
# When two queries answer the same entity but project different columns
# (e.g. `club_id, club_name` vs `club_name`), a full-tuple EXCEPT refuses.
# build_key_comparison() derives a single canonical-key projection (e.g.
# `club_id`) that is used ONLY inside the EXCEPT comparison. It never rewrites
# the user's SQL for display or execution, and returns ok=False (=> unknown)
# whenever it cannot normalize safely.
# ---------------------------------------------------------------------------

_AGG_RE = re.compile(r"(?i)\b(SUM|COUNT|AVG|MIN|MAX|TOTAL|GROUP_CONCAT)\s*\(")
_GROUP_RE = re.compile(r"(?i)\bGROUP\s+BY\b")
_DISTINCT_RE = re.compile(r"(?i)\bSELECT\s+DISTINCT\b")
_SETOP_RE = re.compile(r"(?i)\b(UNION|INTERSECT|EXCEPT)\b")
_JOIN_RE = re.compile(r"(?i)\bJOIN\b")
_HAVING_RE = re.compile(r"(?i)\bHAVING\b")
# Top-k markers: LIMIT and its relatives change which rows are in the set.
_LIMIT_TOPK_RE = re.compile(r"(?i)\b(LIMIT|OFFSET|FETCH)\b")


def _connect_ro(db_path):
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def _schema_pk_map(db_path: str) -> dict:
    """Return {table_lower: {'pk': single_col_pk_or_None, 'cols': set(lower), 'name': orig}}."""
    info = {}
    try:
        conn = _connect_ro(db_path)
    except sqlite3.Error:
        return info
    try:
        cur = conn.cursor()
        tables = [r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        for t in tables:
            try:
                rows = cur.execute(f'PRAGMA table_info("{t}")').fetchall()
            except sqlite3.Error:
                continue
            cols = {r[1].lower() for r in rows}
            pks = [r[1] for r in rows if r[5]]  # r[5] = pk flag (0 or ordinal)
            info[t.lower()] = {
                "pk": pks[0] if len(pks) == 1 else None,
                "cols": cols,
                "name": t,
            }
    except sqlite3.Error:
        pass
    finally:
        conn.close()
    return info


def _single_base_table(sql: str):
    """Return (table, alias_or_None) when the query has exactly one base table
    and no JOIN / comma-join / subquery-in-FROM, else None."""
    if _JOIN_RE.search(sql):
        return None
    m = re.search(r"(?is)\bFROM\b\s+(.+?)(?:\bWHERE\b|\bGROUP\b|\bORDER\b|\bLIMIT\b|$)", sql)
    if not m:
        return None
    frm = m.group(1).strip()
    if "," in frm or frm.startswith("("):
        return None
    toks = re.sub(r"(?i)\bAS\b", " ", frm).split()
    strip = lambda s: s.strip('"`[]')
    if len(toks) == 1:
        return (strip(toks[0]), None)
    if len(toks) == 2:
        return (strip(toks[0]), strip(toks[1]))
    return None


def _convention_key(table: str, cols: set) -> str | None:
    """Best-effort canonical key when no single-column PK is declared."""
    t = table.lower()
    stem = t[:-1] if t.endswith("s") else t
    for cand in (f"{stem}_id", f"{t}_id"):
        if cand in cols:
            return cand
    if "geoid" in cols:
        return "geoid"
    return None


def _looks_like_key(col: str, pk_names: set) -> bool:
    c = col.lower()
    return c in pk_names or c == "geoid" or c.endswith("_id")


def _benchmark_canonical_key(db_path: str, table: str):
    """Registered answer-entity key columns for a table in a recognized local
    benchmark (e.g. Lahman Teams -> [teamid, yearid, lgid]), filtered to columns
    that actually exist. None when the DB is not a known benchmark. This resolves
    ambiguous multi-id tables that the generic id-like heuristic can't key."""
    if not db_path:
        return None
    try:
        from local_benchmarks.benchmark_relationships import canonical_keys
    except Exception:
        return None
    schema = _schema_pk_map(db_path)
    cks = canonical_keys(set(schema.keys()))
    key = cks.get(str(table).lower())
    if not key:
        return None
    cols = schema.get(str(table).lower(), {}).get("cols", set())
    filtered = [k for k in key if k in cols]
    return filtered or None


_JOIN_ALIAS_KW = {
    "on", "where", "group", "order", "having", "limit", "join", "inner",
    "left", "right", "outer", "cross", "full", "union", "using", "and", "or",
}


def _project_replace(sql: str, new_proj: str):
    """Replace the top-level projection: `SELECT <...> FROM` -> `SELECT
    <new_proj> FROM`, finding the FROM at paren depth 0 (so aggregates and
    scalar subqueries in the SELECT list are handled). Returns None when the
    projection cannot be located safely."""
    m = re.match(r"(?is)\s*SELECT\b", sql)
    if not m:
        return None
    i, depth, n = m.end(), 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                return None
            depth -= 1
        elif depth == 0 and re.match(r"(?i)FROM\b", sql[i:]) and (
                i == 0 or not (sql[i - 1].isalnum() or sql[i - 1] == "_")):
            return f"SELECT {new_proj} " + sql[i:]
        i += 1
    return None


def _join_tables(sql: str):
    """Ordered [(table, alias_or_None)] for the driving table + each JOIN.
    Subqueries in FROM (FROM (SELECT ...)) are skipped."""
    out = []
    for m in re.finditer(
            r"(?is)\b(?:FROM|JOIN)\s+([`\"\[]?[A-Za-z_]\w*[`\"\]]?)"
            r"(?:\s+(?:AS\s+)?([`\"\[]?[A-Za-z_]\w*[`\"\]]?))?", sql):
        t = m.group(1).strip('`"[]').lower()
        a = (m.group(2) or "").strip('`"[]')
        if a.lower() in _JOIN_ALIAS_KW:
            a = ""
        out.append((t, a or None))
    return out


def _benchmark_key_columns(db_path: str) -> set:
    """Union of all registered canonical-key column names for this DB's
    benchmark (empty for non-benchmark DBs)."""
    if not db_path:
        return set()
    try:
        from local_benchmarks.benchmark_relationships import canonical_keys
    except Exception:
        return set()
    schema = _schema_pk_map(db_path)
    cols = set()
    for v in canonical_keys(set(schema.keys())).values():
        cols |= {c.lower() for c in v}
    return cols


def _parse_group_by_exprs(sql: str):
    """[(bare_name_lower, raw_expr)] when every GROUP BY term is a simple
    column / table.column reference, else None. The raw_expr is projected in the
    comparison SQL (keeps the alias qualifier)."""
    m = re.search(
        r"(?is)\bGROUP\s+BY\b(.+?)(?:\bHAVING\b|\bORDER\s+BY\b|\bLIMIT\b|$)", sql)
    if not m:
        return None
    out = []
    for term in m.group(1).split(","):
        t = term.strip()
        if not t:
            return None
        mm = re.fullmatch(
            r"""[`"\[]?([A-Za-z_]\w*)[`"\]]?"""
            r"""(?:\s*\.\s*[`"\[]?([A-Za-z_]\w*)[`"\]]?)?""", t)
        if not mm:
            return None
        out.append(((mm.group(2) or mm.group(1)).lower(), t))
    return out or None


def build_key_comparison(database_id: int, sql: str, execution_columns: list) -> dict:
    """Build a single-column canonical-key projection of `sql`, used ONLY for
    the EXCEPT comparison. Returns:
        {"ok": True,  "key": "club_id", "comparison_sql": "...", "strategy": "..."}
        {"ok": False, "reason": "..."}
    Strategies:
      * key_in_output       — a canonical key is already an output column; wrap
                              and project it: SELECT key FROM (<sql>).
      * single_table_rewrite — the key is missing from the output but the query
                              reads one base table with a known key; re-select
                              the key: SELECT <key> FROM <same table/WHERE>.
    """
    clean, err = sanitize(sql)
    if err:
        return {"ok": False, "reason": err}

    db_path = get_database_path(database_id)
    if not db_path:
        return {"ok": False, "reason": "database path not found"}

    schema = _schema_pk_map(db_path)
    pk_names = {v["pk"].lower() for v in schema.values() if v["pk"]}
    out = list(execution_columns or [])

    # -- Path 1: a canonical key is already exposed in the output. Prefer a
    #    declared PK; otherwise accept exactly one id-like column (avoid picking
    #    among several *_id columns, which would be ambiguous).
    key = None
    pk_hits = [c for c in out if c.lower() in pk_names]
    if pk_hits:
        key = pk_hits[0]
    else:
        id_hits = [c for c in out if _looks_like_key(c, pk_names)]
        if len(id_hits) == 1:
            key = id_hits[0]
    if key is not None:
        return {
            "ok": True,
            "key": key.lower(),
            "comparison_sql": f"SELECT {key} FROM (\n{clean}\n) AS __proj",
            "strategy": "key_in_output",
        }

    # -- Benchmark canonical key (composite-aware): when the generic id-like
    #    detection is ambiguous (Teams has yearID/teamID/lgID), use the
    #    registered answer-entity key for a recognized benchmark schema.
    base = _single_base_table(clean)
    if base:
        bkey = _benchmark_canonical_key(db_path, base[0])
        if bkey:
            out_lower = {c.lower(): c for c in out}
            if all(k in out_lower for k in bkey):     # key already in output
                cols = [out_lower[k] for k in bkey]
                return {
                    "ok": True,
                    "key": ",".join(sorted(bkey)),
                    "comparison_sql": f"SELECT {', '.join(cols)} FROM (\n{clean}\n) AS __proj",
                    "strategy": "benchmark_key_in_output",
                }
            if not (_AGG_RE.search(clean) or _GROUP_RE.search(clean)
                    or _DISTINCT_RE.search(clean) or _SETOP_RE.search(clean)):
                table, alias = base
                proj = re.search(r"(?is)^\s*SELECT\b(.*?)\bFROM\b", clean)
                if proj and "(" not in proj.group(1) and not re.search(
                        r"(?i)\bSELECT\b", proj.group(1)):
                    refs = ", ".join((f"{alias}.{c}" if alias else c) for c in bkey)
                    comparison_sql = re.sub(
                        r"(?is)^\s*SELECT\b.*?\bFROM\b", f"SELECT {refs} FROM",
                        clean, count=1)
                    return {
                        "ok": True,
                        "key": ",".join(sorted(bkey)),
                        "comparison_sql": comparison_sql,
                        "strategy": "benchmark_single_table_rewrite",
                    }

    # -- Answer-entity canonical key for JOINED queries: recover the answer key
    #    from the FIRST joined table that has a registered benchmark key, even
    #    when there is no single base table (Case 5/9/10). The display SQL is
    #    unchanged; the comparison SQL projects the answer key. GROUP BY queries
    #    are handled by the grouped path, so skip them here.
    if not _GROUP_RE.search(clean) and not _SETOP_RE.search(clean):
        for (t, alias) in _join_tables(clean):
            bkey = _benchmark_canonical_key(db_path, t)
            if not bkey:
                continue
            qual = alias or t
            refs = ", ".join(f"{qual}.{c}" for c in bkey)
            comp = _project_replace(clean, refs)
            if comp:
                return {
                    "ok": True,
                    "key": ",".join(sorted(bkey)),
                    "comparison_sql": comp,
                    "strategy": "benchmark_answer_key",
                }
            break

    # -- Path 2: recover the key from a single base table. Only safe when the
    #    query is a plain single-table SELECT (no join / aggregate / group by /
    #    distinct / set-op / projection subquery).
    if (_AGG_RE.search(clean) or _GROUP_RE.search(clean)
            or _DISTINCT_RE.search(clean) or _SETOP_RE.search(clean)):
        return {"ok": False, "reason": "aggregate/group-by/distinct/set-op cannot be key-normalized"}

    base = _single_base_table(clean)
    if not base:
        return {"ok": False, "reason": "no single recoverable base table"}
    table, alias = base
    tinfo = schema.get(table.lower())
    if not tinfo:
        return {"ok": False, "reason": f"unknown base table '{table}'"}
    pk = tinfo["pk"] or _convention_key(table, tinfo["cols"])
    if not pk:
        return {"ok": False, "reason": f"no canonical key for table '{table}'"}

    proj = re.search(r"(?is)^\s*SELECT\b(.*?)\bFROM\b", clean)
    if not proj or "(" in proj.group(1) or re.search(r"(?i)\bSELECT\b", proj.group(1)):
        return {"ok": False, "reason": "projection not safely rewritable"}

    ref = f"{alias}.{pk}" if alias else pk
    comparison_sql = re.sub(
        r"(?is)^\s*SELECT\b.*?\bFROM\b", f"SELECT {ref} FROM", clean, count=1
    )
    return {
        "ok": True,
        "key": pk.lower(),
        "comparison_sql": comparison_sql,
        "strategy": "single_table_rewrite",
    }


def is_scalar_aggregate(sql: str) -> bool:
    """True when the SELECT projection contains an aggregate function and there
    is no GROUP BY — i.e. a scalar aggregate output (SELECT COUNT(*) FROM ...).
    Aggregates that appear only in WHERE/HAVING subqueries are NOT flagged,
    because the projection is inspected, not the whole statement."""
    if not sql or _GROUP_RE.search(sql):
        return False
    m = re.search(r"(?is)^\s*SELECT\b(.*?)\bFROM\b", sql)
    if not m:
        return False
    return _AGG_RE.search(m.group(1)) is not None


def unsupported_containment_shape(sql: str) -> str | None:
    """Step 4: single source of truth for the shapes we intentionally refuse to
    normalize (checked for EITHER query, before any Step 1-3 routing). Returns a
    deterministic reason string, or None when the shape is potentially
    normalizable. Unsafe/non-SELECT SQL is left to the caller's safety gate."""
    clean, err = sanitize(sql)
    if err:
        return None
    if _SETOP_RE.search(clean):
        return REASON_SETOP
    if _LIMIT_TOPK_RE.search(clean):
        return REASON_LIMIT
    if is_scalar_aggregate(clean):
        return REASON_SCALAR_AGG
    return None


# ---------------------------------------------------------------------------
# Step 2: safe GROUP BY containment — compare GROUP KEYS only (never aggregate
# values). For two grouped queries answering the same grouped entity, the group
# keys are projected out of each ORIGINAL grouped result (which already applied
# WHERE / GROUP BY / HAVING), and those key sets are compared with EXCEPT.
# Refuses (=> unknown) on LIMIT/top-k, set-ops, DISTINCT, complex GROUP BY
# expressions, or a group key that the query does not expose in its output.
# ---------------------------------------------------------------------------


def is_group_by(sql: str) -> bool:
    """True when the SQL has a GROUP BY clause (used to route the Step-2 path)."""
    return bool(sql) and _GROUP_RE.search(sql) is not None


def _parse_group_by_columns(sql: str):
    """Return the list of bare group-by column names when EVERY GROUP BY term is
    a simple `column` or `table.column` reference, else None (=> refuse)."""
    m = re.search(
        r"(?is)\bGROUP\s+BY\b(.+?)(?:\bHAVING\b|\bORDER\s+BY\b|\bLIMIT\b|$)", sql)
    if not m:
        return None
    cols = []
    for term in m.group(1).split(","):
        t = term.strip()
        if not t:
            return None
        mm = re.fullmatch(
            r"""[\'"`\[]?([A-Za-z_]\w*)[\'"`\]]?"""
            r"""(?:\s*\.\s*[\'"`\[]?([A-Za-z_]\w*)[\'"`\]]?)?""",
            t,
        )
        if not mm:
            return None
        cols.append(mm.group(2) or mm.group(1))  # last identifier
    return cols or None


def build_group_key_comparison(database_id: int, sql: str, execution_columns: list) -> dict:
    """Step 2: identify the group-key columns of a GROUP BY query so containment
    can be compared on the group keys only. Returns:
        {"ok": True, "clean_sql": ..., "group_key_bare": [names],
         "group_key_exprs": [raw exprs], "canonical_key": name|None,
         "canonical_expr": raw|None}
        {"ok": False, "reason": "..."}
    The group key does NOT need to be in the output: the caller rewrites the
    grouped query's projection to the GROUP BY expression(s) (WHERE/JOIN/GROUP
    BY/HAVING are preserved), so a career query grouped by playerID compares on
    playerID even when it only displays names + aggregates.
    """
    clean, err = sanitize(sql)
    if err:
        return {"ok": False, "reason": err}
    if not _GROUP_RE.search(clean):
        return {"ok": False, "reason": "not a GROUP BY query"}
    if _SETOP_RE.search(clean):
        return {"ok": False, "reason": REASON_SETOP}
    if _LIMIT_TOPK_RE.search(clean):
        return {"ok": False, "reason": REASON_LIMIT}
    if _DISTINCT_RE.search(clean):
        return {"ok": False, "reason": "SELECT DISTINCT grouped query is not normalized"}

    gbx = _parse_group_by_exprs(clean)
    if not gbx:
        return {"ok": False, "reason": "GROUP BY expression is not a simple column reference"}
    bare = [b for b, _ in gbx]
    exprs = [e for _, e in gbx]

    db_path = get_database_path(database_id)
    schema = _schema_pk_map(db_path) if db_path else {}
    pk_names = {v["pk"].lower() for v in schema.values() if v["pk"]}
    bench_cols = _benchmark_key_columns(db_path)

    # A single-column group key that is a real key (declared PK, id-like, or a
    # registered benchmark canonical column like playerID) lines up same-entity
    # groupings that use different-but-equivalent key columns.
    canonical_idx = None
    if len(gbx) == 1:
        b0 = bare[0]
        if b0 in pk_names or _looks_like_key(b0, pk_names) or b0 in bench_cols:
            canonical_idx = 0

    return {
        "ok": True,
        "clean_sql": clean,
        "group_key_bare": bare,
        "group_key_exprs": exprs,
        "canonical_key": bare[canonical_idx] if canonical_idx is not None else None,
        "canonical_expr": exprs[canonical_idx] if canonical_idx is not None else None,
    }


# ---------------------------------------------------------------------------
# Step 3: safe DISTINCT containment — compare the DISTINCT key set only.
# A SELECT DISTINCT query already returns a set of distinct tuples over its
# selected columns. When two DISTINCT queries answer the same entity, compare
# their key sets (a shared canonical key, or the exact same selected columns).
# WHERE/JOIN semantics are preserved by wrapping the ORIGINAL DISTINCT SQL.
# Refuses (=> unknown) on GROUP BY / aggregate / HAVING / LIMIT / set-ops.
# ---------------------------------------------------------------------------


def is_distinct(sql: str) -> bool:
    """True when the SQL is a SELECT DISTINCT query (routes the Step-3 path)."""
    return bool(sql) and _DISTINCT_RE.search(sql) is not None


def build_distinct_key_comparison(database_id: int, sql: str, execution_columns: list) -> dict:
    """Step 3: identify the DISTINCT key columns so containment can be compared
    on the distinct key set. Returns:
        {"ok": True, "clean_sql": ..., "distinct_key_cols": [out names],
         "canonical_key": "club_id"|None, "canonical_col": "club_id"|None}
        {"ok": False, "reason": "..."}
    The DISTINCT output columns ARE the key; the caller wraps clean_sql and
    projects the chosen key column(s). WHERE/JOIN are preserved by the wrap.
    """
    clean, err = sanitize(sql)
    if err:
        return {"ok": False, "reason": err}
    if not _DISTINCT_RE.search(clean):
        return {"ok": False, "reason": "not a SELECT DISTINCT query"}
    if _GROUP_RE.search(clean):
        return {"ok": False, "reason": "DISTINCT with GROUP BY is not normalized"}
    if _AGG_RE.search(clean):
        return {"ok": False, "reason": "DISTINCT with an aggregate function is not normalized"}
    if _HAVING_RE.search(clean):
        return {"ok": False, "reason": "DISTINCT with HAVING is not normalized"}
    if _SETOP_RE.search(clean):
        return {"ok": False, "reason": REASON_SETOP}
    if _LIMIT_TOPK_RE.search(clean):
        return {"ok": False, "reason": REASON_LIMIT}

    out = list(execution_columns or [])
    if not out:
        return {"ok": False, "reason": "DISTINCT query exposes no columns"}

    db_path = get_database_path(database_id)
    schema = _schema_pk_map(db_path) if db_path else {}
    pk_names = {v["pk"].lower() for v in schema.values() if v["pk"]}

    canonical = None
    pk_hits = [c for c in out if c.lower() in pk_names]
    if pk_hits:
        canonical = pk_hits[0]
    else:
        id_hits = [c for c in out if _looks_like_key(c, pk_names)]
        if len(id_hits) == 1:
            canonical = id_hits[0]

    return {
        "ok": True,
        "clean_sql": clean,
        "distinct_key_cols": out,
        "canonical_key": canonical.lower() if canonical else None,
        "canonical_col": canonical,
    }

# End of containment checker (Step 1 canonical-key, Step 2 GROUP BY, Step 3 DISTINCT).
