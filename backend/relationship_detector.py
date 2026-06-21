"""
relationship_detector.py

Phase 4 — relationship (foreign-key) detection.

Two signals, combined, with value overlap as the decider:

  * name similarity  — proposes links (owns.petid looks like it targets pets)
  * value overlap    — confirms them (owns.petid values are a subset of
                       pets.petid values)

A strong name match with no value overlap produces NO edge.  Foreign-key
*targets* are drawn from the candidate primary keys already flagged in
table_columns (Phase 3).

This module performs detection and scoring only.  It writes nothing itself
(persistence lives in database_service) and it does not touch the /query
pipeline or generate any JOIN SQL.
"""

import re
import sqlite3
import difflib

from database_service import get_database_schema

# ---------------------------------------------------------------------------
# Tunable thresholds (config constants)
# ---------------------------------------------------------------------------
VALUE_OVERLAP_FLOOR = 0.60      # below this -> not a relationship at all
AUTO_CONFIRM_CONFIDENCE = 0.85  # confirmed=1 requires confidence >= this ...
AUTO_CONFIRM_OVERLAP = 0.90     # ... AND value_overlap >= this

W_OVERLAP = 0.70                # confidence = W_OVERLAP*overlap + W_NAME*name
W_NAME = 0.30

MAX_PK_TARGETS_PER_TABLE = 5    # cap ranked PK candidates tested per table

NUMERIC_TYPES = {"INTEGER", "REAL"}


# ---------------------------------------------------------------------------
# Name helpers
# ---------------------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _singular(s: str) -> str:
    if s.endswith("ies") and len(s) > 3:
        return s[:-3] + "y"
    if s.endswith("s") and not s.endswith("ss") and len(s) > 1:
        return s[:-1]
    return s


def _strip_id(col: str) -> str:
    low = (col or "").lower()
    for suffix in ("_id", "id"):
        if low.endswith(suffix) and len(low) > len(suffix):
            return low[: -len(suffix)]
    return low


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _is_id_like(col: str, table: str) -> bool:
    nc = _norm(col)
    nt = _norm(table)
    nts = _singular(nt)
    return (
        nc.endswith("id")
        or nc in {nt + "id", nts + "id", nt, nts}
    )


def _key_home(col: str, table: str) -> bool:
    """True if the column is named after THIS table (i.e. the table 'owns'
    the key). Used to resolve FK direction when both sides look unique on
    small data: the side that owns the key by name is the PK (to) side."""
    nc = _norm(col)
    nt = _norm(table)
    nts = _singular(nt)
    return nc in {nt + "id", nts + "id", nt, nts}


def _name_similarity(a_col: str, b_col: str, b_table: str) -> float:
    na, nb = _norm(a_col), _norm(b_col)
    nt = _norm(b_table)
    nts = _singular(nt)

    scores = []

    # Exact normalized column-name equality (owns.petid == pets.petid).
    scores.append(1.0 if na == nb else 0.0)

    # A's column matches B's table-name + id pattern.
    if na in {nt + "id", nts + "id"}:
        scores.append(1.0)
    elif na in {nt, nts}:
        scores.append(0.8)

    # Affix match: strip id suffix from A, compare stem to B's table name.
    a_stem = _norm(_strip_id(a_col))
    if a_stem and a_stem in {nt, nts}:
        scores.append(0.9)

    # Fuzzy fallback (scaled so it can't dominate the exact signals).
    scores.append(difflib.SequenceMatcher(None, na, nb).ratio() * 0.8)
    if a_stem:
        scores.append(difflib.SequenceMatcher(None, a_stem, nts).ratio() * 0.8)

    return max(0.0, min(1.0, max(scores)))


# ---------------------------------------------------------------------------
# Type + value helpers
# ---------------------------------------------------------------------------
def _type_group(t: str) -> str:
    return "num" if (t or "TEXT").upper() in NUMERIC_TYPES else "text"


def _types_compatible(t1: str, t2: str) -> bool:
    return _type_group(t1) == _type_group(t2)


def _value_overlap(db_path, a_table, a_col, b_table, b_col):
    """Inclusion ratio: fraction of A.col's distinct non-null values that
    also appear in B.col.  Returns (overlap, distinct_count_of_A_col)."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    qa_t, qa_c = _quote_ident(a_table), _quote_ident(a_col)
    qb_t, qb_c = _quote_ident(b_table), _quote_ident(b_col)

    cursor.execute(
        f"SELECT COUNT(DISTINCT {qa_c}) FROM {qa_t} WHERE {qa_c} IS NOT NULL"
    )
    denom = cursor.fetchone()[0]

    if not denom:
        conn.close()
        return 0.0, 0

    cursor.execute(
        f"""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT {qa_c} AS v FROM {qa_t} WHERE {qa_c} IS NOT NULL
        ) WHERE v IN (SELECT {qb_c} FROM {qb_t})
        """
    )
    inter = cursor.fetchone()[0]
    conn.close()

    return inter / denom, denom


# ---------------------------------------------------------------------------
# Ranking + classification
# ---------------------------------------------------------------------------
def _rank_pk_candidates(table):
    candidates = [c for c in table["columns"] if c.get("is_primary_key_candidate")]

    def score(col):
        s = 0
        if _is_id_like(col["column_name"], table["table_name"]):
            s += 3
        if _norm(col["column_name"]).endswith("id"):
            s += 2
        if _type_group(col.get("data_type")) == "num":
            s += 1
        return (s, -col.get("ordinal", 0))

    candidates.sort(key=score, reverse=True)
    return candidates[:MAX_PK_TARGETS_PER_TABLE]


def _classify(b_col, b_table) -> str:
    return "foreign_key" if _is_id_like(b_col["column_name"], b_table) else "shared_identifier"


def _dedupe(candidates):
    # Keep the single best target per source column.
    best_src = {}
    for c in candidates:
        key = (c["from_table"], c["from_column"])
        cur = best_src.get(key)
        if cur is None or (c["confidence"], c["dir_pref"]) > (cur["confidence"], cur["dir_pref"]):
            best_src[key] = c

    # Drop reverse duplicates of the same logical link; when confidence ties
    # (common on small data where both sides look unique), the orientation
    # whose to-side owns the key by name wins.
    best_pair = {}
    for c in best_src.values():
        key = frozenset({
            (c["from_table"], c["from_column"]),
            (c["to_table"], c["to_column"]),
        })
        cur = best_pair.get(key)
        if cur is None or (c["confidence"], c["dir_pref"]) > (cur["confidence"], cur["dir_pref"]):
            best_pair[key] = c

    edges = list(best_pair.values())
    for e in edges:
        e.pop("dir_pref", None)
    return edges


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def detect_relationships(database_id):
    """Detect relationships across all tables in one database.

    Returns a list of edge dicts:
        from_table, from_column, to_table, to_column,
        relationship_type, name_similarity, value_overlap,
        confidence, confirmed
    """
    schema = get_database_schema(database_id)
    if not schema or not schema.get("tables"):
        return []

    db_path = schema["db_path"]
    tables = schema["tables"]
    pk_targets = {t["table_name"]: _rank_pk_candidates(t) for t in tables}

    candidates = []

    for a in tables:
        for b in tables:
            if a["table_name"] == b["table_name"]:
                continue

            for b_col in pk_targets[b["table_name"]]:
                for a_col in a["columns"]:
                    if not _types_compatible(a_col.get("data_type"), b_col.get("data_type")):
                        continue

                    overlap, denom = _value_overlap(
                        db_path,
                        a["table_name"], a_col["column_name"],
                        b["table_name"], b_col["column_name"],
                    )
                    if denom == 0 or overlap < VALUE_OVERLAP_FLOOR:
                        continue

                    name_sim = _name_similarity(
                        a_col["column_name"], b_col["column_name"], b["table_name"]
                    )
                    confidence = min(1.0, W_OVERLAP * overlap + W_NAME * name_sim)

                    # Direction preference: +1 if the to-side owns the key by
                    # name, -1 if the from-side does (wrong orientation).
                    dir_pref = (
                        (1 if _key_home(b_col["column_name"], b["table_name"]) else 0)
                        - (1 if _key_home(a_col["column_name"], a["table_name"]) else 0)
                    )

                    candidates.append({
                        "from_table": a["table_name"],
                        "from_column": a_col["column_name"],
                        "to_table": b["table_name"],
                        "to_column": b_col["column_name"],
                        "relationship_type": _classify(b_col, b["table_name"]),
                        "name_similarity": round(name_sim, 3),
                        "value_overlap": round(overlap, 3),
                        "confidence": round(confidence, 3),
                        "dir_pref": dir_pref,
                    })

    edges = _dedupe(candidates)

    for edge in edges:
        edge["confirmed"] = (
            1
            if edge["confidence"] >= AUTO_CONFIRM_CONFIDENCE
            and edge["value_overlap"] >= AUTO_CONFIRM_OVERLAP
            else 0
        )

    return edges
