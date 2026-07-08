"""
sql_candidates/explicit_table_lock.py

Emergency fix — explicit table lock.

When the natural-language question NAMES real schema tables verbatim (e.g.
"using indiv20, zipcode_to_census_tracts, census_tracts_new_york ..."), the
answer must use THOSE tables — not a similarly-named sibling
(census_tracts_california) and not a SELECT * fallback. This module detects the
explicitly-mentioned tables generically (exact, word-boundary match against the
real schema names — no hardcoded names) and scores a candidate's table choices
against that lock. Advisory but heavy; never fatal, never raises.
"""

import re

try:
    from sql_candidates.semantic_relationship_verifier import _tables_used
except Exception:  # pragma: no cover
    def _tables_used(sql, idx):
        low = " " + sql.lower() + " "
        return {t for t in idx["tables"]
                if re.search(r"(?<![a-z0-9_])" + re.escape(t) + r"(?![a-z0-9_])", low)}

__all__ = ["detect_locked_tables", "table_lock_penalty",
           "SIBLING_PENALTY", "MISSING_LOCKED_PENALTY", "FALLBACK_PENALTY",
           "UNMENTIONED_PENALTY"]

SIBLING_PENALTY = -20.0        # per wrong sibling of a locked table (max 2)
UNMENTIONED_PENALTY = -6.0     # per unmentioned, non-bridge table (max 2)
MISSING_LOCKED_PENALTY = -15.0 # SQL ignores most of the locked tables
FALLBACK_PENALTY = -20.0       # SELECT * / bare scan while tables are locked
_DELTA_FLOOR = -60.0

_NAME_RE = re.compile(r"[a-z0-9]+")
_SELECT_STAR_RE = re.compile(r"^\s*select\s+\*\s+from\b", re.I)


def _toks(name):
    return {t for t in _NAME_RE.findall(str(name or "").lower()) if len(t) >= 4}


def _distinctive(name):
    """A table name specific enough that an explicit mention is intentional:
    contains an underscore or a digit, or is reasonably long."""
    n = str(name or "")
    return ("_" in n) or any(ch.isdigit() for ch in n) or len(n) >= 6


def detect_locked_tables(question, table_names):
    """Real schema table names mentioned verbatim (word-boundary) in the
    question. Generic: matches against the given names only, nothing hardcoded."""
    q = " " + str(question or "").lower() + " "
    locked = []
    for t in table_names:
        tl = str(t).lower()
        if len(tl) < 3 or not _distinctive(tl):
            continue
        if re.search(r"(?<![a-z0-9_])" + re.escape(tl) + r"(?![a-z0-9_])", q):
            locked.append(tl)
    return locked


def _family_tokens(table_names):
    tok_tables = {}
    for t in table_names:
        for tok in _toks(t):
            tok_tables.setdefault(tok, set()).add(str(t).lower())
    return {tok for tok, ts in tok_tables.items() if len(ts) >= 2}


def _fk_connected(idx, u, locked):
    lset = set(locked)
    for r in idx.get("relationships", []):
        ft = str(r.get("from_table") or "").lower()
        tt = str(r.get("to_table") or "").lower()
        if (ft == u and tt in lset) or (tt == u and ft in lset):
            return True
    return False


def table_lock_penalty(question, sql, idx, locked=None):
    """Return (delta, reasons, checks). Heavy advisory penalties; never fatal."""
    delta, reasons, checks = 0.0, [], {}
    try:
        if not sql or not idx or not idx.get("tables"):
            return 0.0, reasons, checks
        names = set(idx["tables"])
        if locked is None:
            locked = detect_locked_tables(question, names)
        if not locked:
            return 0.0, reasons, checks
        checks["locked_tables"] = sorted(locked)
        used = _tables_used(sql, idx)
        family = _family_tokens(names)
        locked_family = set().union(*[_toks(t) & family for t in locked]) \
            if locked else set()

        # wrong sibling / unmentioned tables ---------------------------------
        siblings, unmentioned = [], []
        for u in used:
            if u in locked or _fk_connected(idx, u, locked):
                continue
            if _toks(u) & locked_family:      # shares a family token with a lock
                siblings.append(u)
            else:
                unmentioned.append(u)
        for u in siblings[:2]:
            delta += SIBLING_PENALTY
            reasons.append(f"SQL uses '{u}', a sibling of an explicitly named "
                           f"table; the question locks {sorted(locked)}")
        for u in unmentioned[:2]:
            delta += UNMENTIONED_PENALTY
            reasons.append(f"SQL uses unmentioned table '{u}' while the question "
                           f"names specific tables {sorted(locked)}")
        if siblings:
            checks["wrong_sibling_tables"] = siblings
        if unmentioned:
            checks["unmentioned_tables"] = unmentioned

        # ignores most locked tables -----------------------------------------
        missing = [t for t in locked if t not in used]
        if len(locked) >= 2 and len(missing) > len(locked) / 2:
            delta += MISSING_LOCKED_PENALTY
            reasons.append(f"SQL ignores most explicitly named tables "
                           f"(missing: {sorted(missing)})")
            checks["missing_locked"] = sorted(missing)

        # SELECT * / bare scan while tables are locked -----------------------
        if _SELECT_STAR_RE.search(sql) and " join " not in sql.lower():
            delta += FALLBACK_PENALTY
            reasons.append("SELECT * fallback while the question explicitly "
                           "names tables to use")
            checks["select_star_fallback"] = True

        delta = max(_DELTA_FLOOR, round(delta, 1))
        checks["delta"] = delta
        return delta, reasons, checks
    except Exception as exc:  # advisory: never break scoring
        return 0.0, reasons, {"error": f"{type(exc).__name__}: {exc}"}
