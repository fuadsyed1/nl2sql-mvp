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
           "literal_check", "MAX_DISTINCT", "categorical_complement",
           "complement_value_satisfied"]

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
# categorical complement grounding (generic status negation)
#
# A question may name a category by its COMPLEMENT ("abnormal" = not "normal",
# "inactive" = not "active", "non-compliant", "unsuccessful"). When a
# low-cardinality status-like column has a value that is the lexical BASE of that
# complement concept, the grounded category is the bounded set of ALL OTHER known
# values — never a guessed boolean 0/1, never a single arbitrary category. When
# the complement WORD is itself a stored value (a binary normal/abnormal column),
# it grounds directly to that value with no enumeration. Everything is derived
# from the sampled value profile; no column/value/domain is hardcoded.
# ---------------------------------------------------------------------------
_NEG_PREFIXES = ("ab", "non", "un", "im", "ir", "dis", "in")


def _norm_word(w):
    return re.sub(r"[^a-z]", "", str(w).lower())


def categorical_complement(question, profile, tables=None):
    """Ground a complement/negation category concept in `question` to a bounded
    value set over some low-cardinality profiled column.

    Returns {table, column, mode, base, grounded_values, known_values} or None.
      * mode 'direct'     — the concept word IS a stored value -> grounded to it;
      * mode 'complement' — the concept is neg-prefix + a stored BASE value ->
                            grounded to every OTHER known value (base excluded).
    Neutral (None) when no unambiguous grounding exists, or the profile is too
    small (< 2 values) to enumerate a bounded complement safely."""
    if not profile or not question:
        return None
    qlow = " " + question.lower() + " "
    best = None

    def _concept_present(concept, base_lc):
        # a negation-shaped word (abnormal, inactive) as a whole word, OR a
        # 'non-'/'non '/'not ' separated negation of the base value.
        if re.search(r"\b" + re.escape(concept) + r"\b", qlow):
            return True
        if re.search(r"\bnon[-\s]?" + re.escape(base_lc) + r"\b", qlow):
            return True
        if re.search(r"\bnot\s+" + re.escape(base_lc) + r"\b", qlow):
            return True
        return False

    for t in sorted(profile):
        if tables is not None and t not in tables:
            continue
        for c in sorted(profile[t]):
            vals = [str(v).strip() for v in profile[t][c] if str(v).strip()]
            low = {}
            for v in vals:
                low.setdefault(v.lower(), v)
            if len(low) < 2:
                continue
            # A NEGATION-SHAPED concept: a whole question word == neg_prefix + a
            # stored BASE value (abnormal = ab+normal, inactive = in+active). Only
            # such words trigger grounding, so an ordinary filter value that
            # merely appears in the question (e.g. 'completed') is never mistaken
            # for a category concept, and no substring can false-match.
            for base_lc, base in low.items():
                for pref in _NEG_PREFIXES:
                    concept = pref + base_lc
                    if not _concept_present(concept, base_lc):
                        continue
                    if concept in low:
                        # DIRECT: the complement word itself is a stored value
                        # (a binary base/complement column) -> ground to it.
                        return {"table": t, "column": c, "mode": "direct",
                                "base": base, "grounded_values": [low[concept]],
                                "known_values": vals}
                    complement = [v for k, v in low.items() if k != base_lc]
                    if complement:
                        cand = {"table": t, "column": c, "mode": "complement",
                                "base": base, "grounded_values": complement,
                                "known_values": vals}
                        if best is None or len(complement) > len(
                                best["grounded_values"]):
                            best = cand
    return best


def complement_value_satisfied(sql, grounding):
    """True when `sql` restricts the grounded status column to EXACTLY the
    grounded category set: every grounded value present, the base value absent,
    and no unseen literal used (e.g. the boolean '1'). Used to reject a candidate
    that filters `flag = '1'`, or that names only one category when the grounded
    complement has several. Purely lexical over the SQL text; never raises."""
    if not grounding or not sql:
        return False
    low_sql = sql.lower()
    grounded = {str(v).strip().lower() for v in grounding.get("grounded_values") or []}
    base = (grounding.get("base") or "").strip().lower()
    if not grounded:
        return False
    present = {g for g in grounded if re.search(r"'" + re.escape(g) + r"'", low_sql)}
    if present != grounded:
        return False                       # incomplete complement (or none)
    if base and re.search(r"'" + re.escape(base) + r"'", low_sql):
        return False                       # base state wrongly included
    return True


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
