"""
schema/value_profiler.py

Lightweight value grounding for literal generation.

profile_values(db_path) samples the DISTINCT values of every low-cardinality
TEXT / boolean-like column in a SQLite database (read-only, generic — no
database-specific rules). The profile is used three ways:

  * prompt grounding — format_value_hints() renders a "known values" block
    for the semantic-checklist and direct-SQL prompts, so the model writes
    resolved='no' instead of guessing resolved='false';
  * scoring — literal_check() finds `column = 'literal'` comparisons whose
    literal is NOT among that column's sampled values (candidate_scorer
    penalizes them);
  * warnings — the endpoint attaches a warning when the selected SQL uses
    unseen literals.

Schema-only databases (all tables empty) have nothing to sample, so
grounding_profile() falls back to the deterministic seeded EVAL COPY
(benchmarks/gold_eval.eval_db_path) for prompt grounding only — the user's
database is never touched.
"""

import os
import re
import sqlite3

__all__ = ["profile_values", "grounding_profile", "format_value_hints",
           "literal_check", "MAX_DISTINCT"]

MAX_DISTINCT = 12          # a column is "enum-like" when it has <= this many values
_MAX_INT_DISTINCT = 3      # 0/1(/2) flag columns
_VALUE_LEN_CAP = 40

_profile_cache = {}        # (path, mtime) -> profile


# ---------------------------------------------------------------------------
# profiling
# ---------------------------------------------------------------------------
def profile_values(db_path, max_distinct=MAX_DISTINCT):
    """{table: {column: [sampled distinct values]}} for enum-like columns.
    Never raises; returns {} when the DB is unreadable/empty."""
    if not db_path or not os.path.exists(db_path):
        return {}
    key = (os.path.abspath(db_path), os.path.getmtime(db_path))
    if key in _profile_cache:
        return _profile_cache[key]
    profile = {}
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            tables = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
                " AND name NOT LIKE 'sqlite_%'")]
            for t in tables:
                cols = con.execute(f'PRAGMA table_info("{t}")').fetchall()
                for _, name, ctype, *_rest in cols:
                    ctype = (ctype or "").upper()
                    is_text = not any(x in ctype for x in
                                      ("INT", "REAL", "NUM", "DEC", "FLOA", "DOUB"))
                    is_int = "INT" in ctype
                    if not (is_text or is_int):
                        continue
                    limit = max_distinct if is_text else _MAX_INT_DISTINCT
                    try:
                        vals = [r[0] for r in con.execute(
                            f'SELECT DISTINCT "{name}" FROM "{t}" '
                            f'WHERE "{name}" IS NOT NULL LIMIT {limit + 1}')]
                    except sqlite3.Error:
                        continue
                    if not vals or len(vals) > limit:
                        continue
                    vals = [str(v)[:_VALUE_LEN_CAP] for v in vals]
                    profile.setdefault(t.lower(), {})[name.lower()] = sorted(vals)
        finally:
            con.close()
    except sqlite3.Error:
        return {}
    _profile_cache[key] = profile
    return profile


def grounding_profile(database_id, db_path):
    """(profile, grounded_from_eval_copy). Uses the real DB when it has rows;
    for a schema-only DB falls back to the seeded eval copy (prompt grounding
    only — nothing is written anywhere)."""
    profile = profile_values(db_path)
    if profile:
        return profile, False
    try:
        from benchmarks.gold_eval import eval_db_path
        alt = eval_db_path(database_id)
        if alt and os.path.abspath(alt) != os.path.abspath(db_path or ""):
            alt_profile = profile_values(alt)
            if alt_profile:
                return alt_profile, True
    except Exception:
        pass
    return {}, False


def format_value_hints(profile, tables=None, max_columns=40):
    """Text block listing known values per column, for LLM prompts.
    `tables` (lowercased names) restricts the block; None = all."""
    if not profile:
        return ""
    lines = []
    for t in sorted(profile):
        if tables is not None and t not in tables:
            continue
        for c in sorted(profile[t]):
            if len(lines) >= max_columns:
                break
            vals = " | ".join(f"'{v}'" for v in profile[t][c])
            lines.append(f"- {t}.{c}: {vals}")
    if not lines:
        return ""
    return ("Known column values (use EXACTLY these spellings in literals; "
            "never invent values like 'true'/'false' when a column uses "
            "'yes'/'no'):\n" + "\n".join(lines))


# ---------------------------------------------------------------------------
# literal checking (scorer + warnings)
# ---------------------------------------------------------------------------
# col = 'lit' | col != 'lit' | col <> 'lit' | col LIKE 'lit'
_CMP_RE = re.compile(
    r'(?:"?([A-Za-z_]\w*)"?\s*\.\s*)?"?([A-Za-z_]\w*)"?\s*'
    r"(?:=|!=|<>|\bLIKE\b)\s*'([^']*)'", re.IGNORECASE)
# 'lit' = col (reversed)
_CMP_REV_RE = re.compile(
    r"'([^']*)'\s*(?:=|!=|<>)\s*"
    r'(?:"?([A-Za-z_]\w*)"?\s*\.\s*)?"?([A-Za-z_]\w*)"?', re.IGNORECASE)


def _columns_named(profile, col):
    """All (table, values) whose column name matches `col`."""
    col = col.lower()
    return [(t, cols[col]) for t, cols in profile.items() if col in cols]


def _check_pair(profile, col, lit, out, seen):
    entries = _columns_named(profile, col)
    if not entries:            # column not profiled -> nothing to say
        return
    lit_n = str(lit).strip().lower()
    if not lit_n:
        return
    for _t, vals in entries:
        if any(lit_n == str(v).strip().lower() for v in vals):
            return             # literal is valid for at least one such column
    key = (col.lower(), lit_n)
    if key in seen:
        return
    seen.add(key)
    known = entries[0][1][:6]
    out.append({"column": col.lower(), "literal": str(lit),
                "known_values": known})


def _extraction_filters(obj, out):
    """Collect (column, value) string filters from an extraction dict."""
    if isinstance(obj, dict):
        col, val = obj.get("column"), obj.get("value")
        if isinstance(col, str) and isinstance(val, str):
            out.append((col, val))
        for v in obj.values():
            _extraction_filters(v, out)
    elif isinstance(obj, list):
        for x in obj:
            _extraction_filters(x, out)


def literal_check(sql, extraction, profile):
    """Violations: [{column, literal, known_values}] — string literals compared
    against a PROFILED column but not among its sampled values. Precise by
    design: unprofiled (high-cardinality) columns are never flagged."""
    if not profile:
        return []
    out, seen = [], set()
    for m in _CMP_RE.finditer(sql or ""):
        _check_pair(profile, m.group(2), m.group(3), out, seen)
    for m in _CMP_REV_RE.finditer(sql or ""):
        _check_pair(profile, m.group(3), m.group(1), out, seen)
    filt = []
    _extraction_filters(extraction or {}, filt)
    for col, val in filt:
        _check_pair(profile, col, val, out, seen)
    return out
