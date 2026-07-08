"""
schema/hopf_relationship_evidence.py

Phase 1 — HoPF-style relationship EVIDENCE layer (foundation only).

This module does NOT replace the declared-FK metadata or the existing
value-overlap detector (schema/relationship_detector.py). It adds a separate,
self-contained way to SCORE a candidate child->parent link from multiple weak
signals and to record the evidence behind it, so a later join planner can pick
safer paths on big databases.

Signals combined (HoPF-style):
  * parent uniqueness / near-uniqueness  (a key is (near-)unique)
  * child->parent sampled value overlap  (child values are contained in parent)
  * column-name similarity               (plausible name match)
  * type compatibility                   (both numeric or both text)
  * null / repetition pattern            (child repeats -> many-to-one)
  * measure-column rejection             (amount/price/... are never keys)

Design rules honored here:
  - Declared FK relationships are kept as-is and always win (merge_relationships).
  - Only VERY high-confidence inferred links (>= USABLE_CONFIDENCE) are marked
    usable for join paths; everything else is stored as evidence only.
  - Big tables must be SAMPLED, never full-scanned (sample_column_stats /
    sampled_overlap use bounded LIMIT reads, read-only).
  - Schema-only databases (no rows) skip value-overlap evidence and produce
    weak, NON-usable schema-only candidates.

Everything is read-only and pure where possible; the scoring functions take
already-measured stats so they can be unit-tested without a database.
"""

import re
import sqlite3

__all__ = [
    "USABLE_CONFIDENCE",
    "is_measure_column",
    "name_similarity",
    "types_compatible",
    "score_relationship",
    "merge_relationships",
    "sample_column_stats",
    "sampled_overlap",
]

# Confidence at/above which an inferred link may be auto-used for join paths.
USABLE_CONFIDENCE = 0.92

# Schema-only (no value evidence) links are always weak — capped and never used.
_SCHEMA_ONLY_CAP = 0.60

_NUMERIC_TYPES = {"INTEGER", "REAL", "INT", "BIGINT", "SMALLINT", "NUMERIC",
                  "DECIMAL", "FLOAT", "DOUBLE", "REAL64", "INT64"}

# Generic numeric measure/value tokens — a column that IS one of these (or ends
# with one) is a measurement, never a relationship key. Kept database-agnostic:
# matched against underscore parts and as a name suffix, not hardcoded columns.
_MEASURE_TOKENS = {
    "amount", "amt", "price", "cost", "total", "subtotal", "score", "salary",
    "wage", "income", "revenue", "profit", "quantity", "qty", "rate", "ratio",
    "percent", "pct", "fee", "balance", "discount", "tax", "sum", "avg",
    "mean", "min", "max", "count", "weight", "height", "width", "length",
    "size", "capacity", "volume", "distance", "duration", "calories",
    "servings", "stock", "age", "temperature", "temp", "pressure", "value",
}
# compound measure names ("unit_price", "transaction_amt") collapse to these:
_MEASURE_SUFFIX_RE = re.compile(
    r"(amount|amt|price|cost|total|score|salary|quantity|qty|rate|percent"
    r"|pct|fee|balance|discount|tax|revenue|profit|value)$")


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _is_id_like(col):
    n = _norm(col)
    return n.endswith("id") or n == "id"


def is_measure_column(col):
    """True for numeric measure/value columns that must never be a key.
    Generic (token/suffix based); id-suffixed names are never measures."""
    name = str(col or "")
    if _is_id_like(name):
        return False
    parts = re.split(r"[^a-z0-9]+", name.lower())
    if any(p in _MEASURE_TOKENS for p in parts if p):
        return True
    return bool(_MEASURE_SUFFIX_RE.search(_norm(name)))


def types_compatible(t1, t2):
    def grp(t):
        return "num" if str(t or "TEXT").upper() in _NUMERIC_TYPES else "text"
    return grp(t1) == grp(t2)


def _singular(s):
    if s.endswith("ies") and len(s) > 3:
        return s[:-3] + "y"
    if s.endswith("s") and not s.endswith("ss") and len(s) > 1:
        return s[:-1]
    return s


def name_similarity(child_col, parent_col, parent_table):
    """Cheap name-plausibility score in [0,1] for child_col -> parent(table.col)."""
    import difflib
    nc, np = _norm(child_col), _norm(parent_col)
    nt, nts = _norm(parent_table), _singular(_norm(parent_table))
    scores = [1.0 if nc == np else 0.0]
    if nc in {nt + "id", nts + "id"}:
        scores.append(1.0)
    elif nc in {nt, nts}:
        scores.append(0.8)
    stem = _norm(re.sub(r"(_id|id)$", "", str(child_col or "").lower()))
    if stem and stem in {nt, nts}:
        scores.append(0.9)
    scores.append(difflib.SequenceMatcher(None, nc, np).ratio() * 0.8)
    return max(0.0, min(1.0, max(scores)))


# ---------------------------------------------------------------------------
# scoring (pure — takes already-measured stats, so it is DB-free to test)
# ---------------------------------------------------------------------------
# weights for the data-mode confidence (sum = 1.0)
_W_OVERLAP = 0.45
_W_PARENT_UNIQ = 0.25
_W_NAME = 0.20
_W_REPEAT = 0.10


def score_relationship(*, child_table, child_col, parent_table, parent_col,
                       child_type=None, parent_type=None,
                       parent_uniqueness=None, value_overlap=None,
                       child_repetition=None, child_null_ratio=0.0,
                       schema_only=False):
    """Score one candidate child_col -> parent_col link.

    Returns an evidence dict:
        {source:"hopf_inferred", confidence, usable, evidence:{...}}
    or None when the candidate is rejected outright (measure column on either
    side, or incompatible types).

    Numeric args are the measured signals in [0,1]:
      parent_uniqueness  distinct(parent_col)/rows(parent_col)   (~1 => key)
      value_overlap      fraction of child values found in parent (inclusion)
      child_repetition   1 - distinct(child)/rows(child)         (many-to-one)
    In schema_only mode value_overlap/child_repetition are ignored and the
    result is weak + never usable.
    """
    # measure-column rejection (either side) -----------------------------
    if is_measure_column(child_col) or is_measure_column(parent_col):
        return {
            "source": "hopf_inferred", "confidence": 0.0, "usable": False,
            "evidence": {"rejected": "measure_column",
                         "child": f"{child_table}.{child_col}",
                         "parent": f"{parent_table}.{parent_col}"},
        }
    # type compatibility (hard gate) -------------------------------------
    type_ok = types_compatible(child_type, parent_type)
    nsim = name_similarity(child_col, parent_col, parent_table)

    evidence = {
        "name_similarity": round(nsim, 3),
        "type_compatible": bool(type_ok),
        "parent_uniqueness": (None if parent_uniqueness is None
                              else round(parent_uniqueness, 3)),
        "value_overlap": (None if value_overlap is None
                          else round(value_overlap, 3)),
        "child_repetition": (None if child_repetition is None
                             else round(child_repetition, 3)),
        "child_null_ratio": round(child_null_ratio or 0.0, 3),
        "schema_only": bool(schema_only),
    }

    if not type_ok:
        return {"source": "hopf_inferred", "confidence": 0.0,
                "usable": False, "evidence": evidence}

    if schema_only or value_overlap is None:
        # weak schema evidence only: name + type. Never usable for join paths.
        conf = min(_SCHEMA_ONLY_CAP, nsim * _SCHEMA_ONLY_CAP)
        evidence["schema_only"] = True
        return {"source": "hopf_inferred", "confidence": round(conf, 3),
                "usable": False, "evidence": evidence}

    p_uniq = 0.0 if parent_uniqueness is None else max(0.0, min(1.0, parent_uniqueness))
    overlap = max(0.0, min(1.0, value_overlap))
    repeat = 0.0 if child_repetition is None else max(0.0, min(1.0, child_repetition))

    conf = (_W_OVERLAP * overlap + _W_PARENT_UNIQ * p_uniq
            + _W_NAME * nsim + _W_REPEAT * repeat)
    # a link into a non-unique "parent" is not a key relationship — damp hard.
    if p_uniq < 0.90:
        conf *= 0.6
    # heavy child nulls weaken the evidence slightly.
    conf *= (1.0 - 0.2 * max(0.0, min(1.0, child_null_ratio or 0.0)))
    conf = round(max(0.0, min(1.0, conf)), 3)

    return {"source": "hopf_inferred", "confidence": conf,
            "usable": conf >= USABLE_CONFIDENCE, "evidence": evidence}


# ---------------------------------------------------------------------------
# merge: declared FK (and existing confirmed) always win over inferred
# ---------------------------------------------------------------------------
def _pair_key(e):
    return frozenset({
        (str(e.get("from_table")).lower(), str(e.get("from_column")).lower()),
        (str(e.get("to_table")).lower(), str(e.get("to_column")).lower()),
    })


def merge_relationships(declared=None, inferred=None, confirmed=None):
    """Combine relationship sources into one safe edge list.

    Precedence (highest first): user-confirmed/perfect edges, declared FKs,
    then HoPF-inferred edges that are `usable` (>= USABLE_CONFIDENCE). An
    inferred edge for a pair already covered by a declared/confirmed edge is
    dropped. Declared edges get source="declared_fk", confidence 1.0; confirmed
    edges keep their own source/confidence. Non-usable inferred edges are NOT
    added to the graph (they live only as evidence)."""
    out = []
    seen = set()

    for e in (confirmed or []):
        k = _pair_key(e)
        if k in seen:
            continue
        seen.add(k)
        d = dict(e)
        d.setdefault("source", "confirmed")
        d.setdefault("confidence", 1.0)
        out.append(d)

    for e in (declared or []):
        k = _pair_key(e)
        if k in seen:
            continue
        seen.add(k)
        d = dict(e)
        d["source"] = "declared_fk"
        d["confidence"] = 1.0
        out.append(d)

    for e in (inferred or []):
        if not e.get("usable"):
            continue
        k = _pair_key(e)
        if k in seen:
            continue
        seen.add(k)
        d = dict(e)
        d.setdefault("source", "hopf_inferred")
        out.append(d)

    return out


# ---------------------------------------------------------------------------
# bounded sampling helpers (big tables: SAMPLE only, never full-scan; read-only)
# ---------------------------------------------------------------------------
def _q(name):
    return '"' + str(name).replace('"', '""') + '"'


def sample_column_stats(db_path, table, col, *, sample_limit=5000):
    """Read-only, bounded stats for one column from a LIMIT-sampled row block.

    Returns {rows, non_null, distinct, null_ratio, uniqueness, repetition,
    schema_only}. Never scans the whole table: it samples up to sample_limit
    rows via a subquery LIMIT. schema_only=True when the table has no rows."""
    stats = {"rows": 0, "non_null": 0, "distinct": 0, "null_ratio": 0.0,
             "uniqueness": 0.0, "repetition": 0.0, "schema_only": True}
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
    except sqlite3.Error:
        return stats
    try:
        cur = conn.cursor()
        sub = f"(SELECT {_q(col)} AS v FROM {_q(table)} LIMIT {int(sample_limit)})"
        cur.execute(f"SELECT COUNT(*), COUNT(v), COUNT(DISTINCT v) FROM {sub}")
        rows, non_null, distinct = cur.fetchone()
        rows = rows or 0
        non_null = non_null or 0
        distinct = distinct or 0
        stats.update({
            "rows": rows,
            "non_null": non_null,
            "distinct": distinct,
            "schema_only": rows == 0,
            "null_ratio": (0.0 if rows == 0 else round(1 - non_null / rows, 3)),
            "uniqueness": (0.0 if non_null == 0 else round(distinct / non_null, 3)),
            "repetition": (0.0 if non_null == 0
                           else round(1 - distinct / non_null, 3)),
        })
    except sqlite3.Error:
        pass
    finally:
        conn.close()
    return stats


def sampled_overlap(db_path, child_table, child_col, parent_table, parent_col,
                    *, sample_limit=5000):
    """Read-only inclusion ratio of a LIMIT-sampled block of child values that
    also appear in the parent column. Returns overlap in [0,1] or None on error
    / empty sample. Bounded on the child side; the parent membership test is an
    indexed-ish IN subquery."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3.0)
    except sqlite3.Error:
        return None
    try:
        cur = conn.cursor()
        sub = (f"(SELECT DISTINCT {_q(child_col)} AS v FROM {_q(child_table)} "
               f"WHERE {_q(child_col)} IS NOT NULL LIMIT {int(sample_limit)})")
        cur.execute(f"SELECT COUNT(*) FROM {sub}")
        denom = cur.fetchone()[0] or 0
        if denom == 0:
            return None
        cur.execute(
            f"SELECT COUNT(*) FROM {sub} WHERE v IN "
            f"(SELECT {_q(parent_col)} FROM {_q(parent_table)})")
        inter = cur.fetchone()[0] or 0
        return round(inter / denom, 3)
    except sqlite3.Error:
        return None
    finally:
        conn.close()
