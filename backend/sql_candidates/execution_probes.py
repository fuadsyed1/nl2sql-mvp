"""
sql_candidates/execution_probes.py

Option A — execution-guided sanity probes (advisory only).

After a candidate has been executed and scored, two read-only probes look for
logical mistakes that are executable but wrong. They NEVER mark a candidate
fatal and NEVER reject a candidate merely for returning no rows: they add a
human-readable warning and a small score penalty, and record what they saw in
candidate.validation["probes"]. Every probe is read-only, bounded by a small
wall-clock timeout, and can never raise to the caller — on any failure or
timeout the probe is silently skipped and normal behavior is preserved.

  1. Contradiction probe (only for SQL that returned ZERO rows and contains a
     NOT EXISTS or HAVING): build a conservative relaxed variant (blank the
     first NOT EXISTS predicate, or drop one HAVING condition). If the relaxed
     query returns rows, the constraints were probably fighting each other ->
     "possible contradictory constraint".

  2. Fanout probe (only for aggregate SQL with GROUP BY, 2+ joins, and a plain
     COUNT(*) or SUM(...) with no DISTINCT): compare COUNT(*) against
     COUNT(DISTINCT <driver row>) over the same joined relation. If COUNT(*)
     is much larger, the joins are duplicating the driving entity's rows ->
     "possible join fanout aggregate inflation".
"""

import re
import sqlite3
import threading

__all__ = [
    "probe_candidate",
    "annotate_with_probes",
    "CONTRADICTION_PENALTY",
    "FANOUT_PENALTY",
    "FANOUT_RATIO",
    "DEFAULT_TIMEOUT_S",
    "CONTRADICTION_WARNING",
    "FANOUT_WARNING",
]

CONTRADICTION_PENALTY = 12.0
FANOUT_PENALTY = 10.0
FANOUT_RATIO = 1.5            # COUNT(*) >= FANOUT_RATIO * COUNT(DISTINCT driver)
DEFAULT_TIMEOUT_S = 1.5

CONTRADICTION_WARNING = "possible contradictory constraint"
FANOUT_WARNING = "possible join fanout aggregate inflation"

_NOT_EXISTS_RE = re.compile(r"\bNOT\s+EXISTS\b", re.IGNORECASE)
_HAVING_RE = re.compile(r"\bHAVING\b", re.IGNORECASE)
_JOIN_RE = re.compile(r"\bJOIN\b", re.IGNORECASE)
_GROUP_BY_RE = re.compile(r"\bGROUP\s+BY\b", re.IGNORECASE)
_FROM_RE = re.compile(r"\bFROM\b", re.IGNORECASE)
_COUNT_STAR_RE = re.compile(r"\bCOUNT\s*\(\s*\*\s*\)", re.IGNORECASE)
_SUM_RE = re.compile(r"\bSUM\s*\(", re.IGNORECASE)
_HAVING_TAIL_RE = re.compile(r"\b(ORDER\s+BY|LIMIT|UNION|WINDOW)\b", re.IGNORECASE)

# words that would follow the driving table when there is NO alias
_NON_ALIAS = {
    "join", "inner", "left", "right", "cross", "full", "outer", "natural",
    "where", "group", "order", "limit", "on", "using", "having", "union",
}


# ---------------------------------------------------------------------------
# read-only execution with a wall-clock timeout
# ---------------------------------------------------------------------------
def _exec_ro(db_path, sql, timeout_s, limit=2):
    """Run `sql` read-only against db_path, aborting after timeout_s seconds.
    Returns a list of up to `limit` rows, or None on ANY error/timeout."""
    uri = f"file:{db_path}?mode=ro"
    conn = None
    timer = None
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=timeout_s)
        timer = threading.Timer(timeout_s, conn.interrupt)
        timer.start()
        cur = conn.cursor()
        cur.execute(sql)
        return cur.fetchmany(limit)
    except Exception:
        return None
    finally:
        if timer is not None:
            timer.cancel()
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# conservative SQL relaxation (contradiction probe)
# ---------------------------------------------------------------------------
def _match_paren(sql, open_idx):
    """Index of the ')' matching the '(' at open_idx, or -1."""
    depth = 0
    j = open_idx
    while j < len(sql):
        ch = sql[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


def _blank_first_not_exists(sql):
    """Replace the first `NOT EXISTS (...)` predicate with `1=1`, or None."""
    m = _NOT_EXISTS_RE.search(sql)
    if not m:
        return None
    open_idx = sql.find("(", m.end())
    if open_idx == -1:
        return None
    close_idx = _match_paren(sql, open_idx)
    if close_idx == -1:
        return None
    return sql[:m.start()] + "1=1" + sql[close_idx + 1:]


def _split_top_and(clause):
    """Split a boolean clause on top-level ` AND ` (paren depth 0)."""
    parts = []
    depth = 0
    last = 0
    i = 0
    n = len(clause)
    while i < n:
        ch = clause[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and clause[i:i + 5].upper() == " AND ":
            parts.append(clause[last:i])
            last = i + 5
            i += 5
            continue
        i += 1
    parts.append(clause[last:])
    return [p for p in parts if p.strip()]


def _relax_having(sql):
    """Drop one HAVING condition (the last top-level AND term); if there is a
    single condition, neutralize the whole HAVING. Returns new SQL or None."""
    m = _HAVING_RE.search(sql)
    if not m:
        return None
    start = m.end()
    depth = 0
    end = len(sql)
    k = start
    while k < len(sql):
        ch = sql[k]
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                end = k
                break
            depth -= 1
        elif depth == 0 and _HAVING_TAIL_RE.match(sql, k):
            end = k
            break
        k += 1
    clause = sql[start:end]
    parts = _split_top_and(clause)
    if len(parts) <= 1:
        new_clause = " 1=1 "
    else:
        new_clause = " " + " AND ".join(p.strip() for p in parts[:-1]) + " "
    return sql[:start] + new_clause + sql[end:]


def _contradiction_probe(cand, db_path, timeout_s):
    """Advisory: a zero-row query whose relaxed form returns rows is probably
    over-constrained. Only for SQL with NOT EXISTS or HAVING."""
    if not cand.executed_ok or (cand.row_count or 0) != 0:
        return None
    sql = (cand.sql or "").strip()
    if not sql:
        return None
    relaxed = None
    if _NOT_EXISTS_RE.search(sql):
        relaxed = _blank_first_not_exists(sql)
    elif _HAVING_RE.search(sql):
        relaxed = _relax_having(sql)
    if not relaxed or relaxed.strip() == sql:
        return None
    rows = _exec_ro(db_path, relaxed, timeout_s, limit=1)
    if rows is None:                       # probe failed -> ignore
        return None
    if len(rows) > 0:
        return {"warning": CONTRADICTION_WARNING,
                "penalty": CONTRADICTION_PENALTY,
                "check": {"ran": True, "relaxed_returned_rows": True}}
    return {"check": {"ran": True, "relaxed_returned_rows": False},
            "penalty": 0.0}


# ---------------------------------------------------------------------------
# fanout probe
# ---------------------------------------------------------------------------
def _has_plain_sum(sql):
    for m in _SUM_RE.finditer(sql):
        rest = sql[m.end():].lstrip()
        if not rest[:8].upper().startswith("DISTINCT"):
            return True
    return False


def _core_relation(sql):
    """The `FROM ... [WHERE ...]` slice up to the first GROUP BY, or None."""
    fm = _FROM_RE.search(sql)
    if not fm:
        return None
    gm = _GROUP_BY_RE.search(sql, fm.end())
    end = gm.start() if gm else len(sql)
    core = sql[fm.start():end].strip()
    return core or None


def _driver_alias(sql):
    """Alias (or table name) of the first table after FROM, or None."""
    m = re.search(
        r"\bFROM\s+[`\"\[]?([A-Za-z_]\w*)[`\"\]]?"
        r"(?:\s+(?:AS\s+)?([A-Za-z_]\w*))?",
        sql, re.IGNORECASE)
    if not m:
        return None
    table, alias = m.group(1), m.group(2)
    if alias and alias.lower() not in _NON_ALIAS:
        return alias
    return table


def _fanout_probe(cand, db_path, timeout_s):
    """Advisory: a GROUP BY aggregate over 2+ joins using plain COUNT(*)/SUM()
    may be double-counting the driving entity through the joins."""
    if not cand.executed_ok:
        return None
    sql = (cand.sql or "").strip()
    if not sql or not _GROUP_BY_RE.search(sql):
        return None
    if len(_JOIN_RE.findall(sql)) < 2:
        return None
    if not (_COUNT_STAR_RE.search(sql) or _has_plain_sum(sql)):
        return None
    core = _core_relation(sql)
    driver = _driver_alias(sql)
    if not core or not driver:
        return None
    probe_sql = (f"SELECT COUNT(*) AS c, "
                 f"COUNT(DISTINCT {driver}.rowid) AS d {core}")
    rows = _exec_ro(db_path, probe_sql, timeout_s, limit=1)
    if not rows:
        return None
    try:
        c, d = rows[0][0], rows[0][1]
    except (IndexError, TypeError):
        return None
    if c is None or d is None or d <= 0:
        return None
    check = {"ran": True, "count_star": c, "count_distinct_driver": d,
             "driver": driver}
    if c >= d * FANOUT_RATIO:
        return {"warning": FANOUT_WARNING, "penalty": FANOUT_PENALTY,
                "check": check}
    return {"check": check, "penalty": 0.0}


# ---------------------------------------------------------------------------
# public entry points
# ---------------------------------------------------------------------------
def probe_candidate(cand, db_path, *, timeout_s=DEFAULT_TIMEOUT_S):
    """Run both probes on an executed candidate. Returns
    {"warnings": [...], "penalty": float, "checks": {...}}. Never raises."""
    warnings = []
    penalty = 0.0
    checks = {}
    try:
        cp = _contradiction_probe(cand, db_path, timeout_s)
        if cp is not None:
            checks["contradiction"] = cp.get("check")
            if cp.get("warning"):
                warnings.append(cp["warning"])
                penalty += cp.get("penalty", 0.0)
    except Exception as exc:
        checks["contradiction_error"] = f"{type(exc).__name__}: {exc}"
    try:
        fp = _fanout_probe(cand, db_path, timeout_s)
        if fp is not None:
            checks["fanout"] = fp.get("check")
            if fp.get("warning"):
                warnings.append(fp["warning"])
                penalty += fp.get("penalty", 0.0)
    except Exception as exc:
        checks["fanout_error"] = f"{type(exc).__name__}: {exc}"
    return {"warnings": warnings, "penalty": penalty, "checks": checks}


def annotate_with_probes(cand, db_path, *, timeout_s=DEFAULT_TIMEOUT_S):
    """Probe an executed candidate and fold the outcome into its score /
    reasons / validation IN PLACE (advisory penalty only, never fatal).
    Non-executed candidates are left untouched. Never raises."""
    result = {"warnings": [], "penalty": 0.0, "checks": {}}
    try:
        if not getattr(cand, "executed_ok", False):
            return result
        result = probe_candidate(cand, db_path, timeout_s=timeout_s)
        if result["warnings"]:
            cand.reasons = list(cand.reasons or []) + list(result["warnings"])
            cand.score = max(0.0, round((cand.score or 0.0)
                                        - result["penalty"], 1))
        val = cand.validation if isinstance(cand.validation, dict) else {}
        val["probes"] = result
        cand.validation = val
    except Exception as exc:
        print(f"EXECUTION PROBE ERROR ({getattr(cand, 'label', '?')}): {exc}",
              flush=True)
    return result
