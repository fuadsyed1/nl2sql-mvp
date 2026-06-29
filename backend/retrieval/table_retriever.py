"""
retrieval/table_retriever.py

Query-time table retrieval for large databases. Given a question, return the
top-k most relevant tables so only a small sub-schema is sent into the IR / SQL
pipeline — never the full 100–200 table schema.

Deterministic and dependency-free: ranking uses SQLite **FTS5** (built into the
stdlib `sqlite3`) with bm25, plus deterministic boosts for exact table-name and
column-name hits. If FTS5 is unavailable, it degrades gracefully to the boosts
alone (still deterministic). No embeddings, no network, no LLM.

A table's searchable document is `table_name + column names` (columns are
included only when already loaded; for not-yet-hydrated large-DB tables the doc
is the table name only, which is enough for name-based matching).
"""

import re
import sqlite3

from db.database_service import get_database_tables, get_table_columns

__all__ = ["build_table_index", "retrieve_tables"]

# Per-process cache of built docs, keyed by database_id.
_INDEX_CACHE = {}

_STOPWORDS = {
    "show", "list", "get", "find", "all", "rows", "row", "from", "the", "of",
    "in", "on", "by", "a", "an", "and", "or", "to", "for", "with", "me", "give",
    "what", "which", "how", "many", "is", "are", "count", "number",
}


def _tokenize(text):
    toks = re.split(r"[^A-Za-z0-9]+", (text or "").lower())
    return [t for t in toks if len(t) >= 2 and t not in _STOPWORDS]


def build_table_index(database_id):
    """Build (and cache) one searchable document per table:
    (table_name, doc_text, column_names). Rebuild to pick up newly loaded
    columns. Returns the list of docs."""
    docs = []
    for t in get_database_tables(database_id):
        cols = [c["column_name"] for c in get_table_columns(t["table_id"])]
        doc = " ".join([t["table_name"]] + cols)
        docs.append((t["table_name"], doc, cols))
    _INDEX_CACHE[database_id] = docs
    return docs


def _table_docs(database_id):
    if database_id not in _INDEX_CACHE:
        build_table_index(database_id)
    return _INDEX_CACHE[database_id]


def _fts_rank(docs, question):
    """Return {table_name: positive_score} for FTS5 matches (higher = better),
    or {} when FTS5 is unavailable or nothing matches."""
    terms = _tokenize(question)
    if not terms:
        return {}
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE VIRTUAL TABLE fts USING fts5(table_name UNINDEXED, doc)"
        )
        conn.executemany(
            "INSERT INTO fts(table_name, doc) VALUES (?, ?)",
            [(name, doc) for (name, doc, _cols) in docs],
        )
        match = " OR ".join(f'"{t}"' for t in terms)
        rows = conn.execute(
            "SELECT table_name, bm25(fts) FROM fts WHERE fts MATCH ? "
            "ORDER BY bm25(fts)",
            (match,),
        ).fetchall()
        conn.close()
        # bm25 returns smaller (more negative) = better; flip so higher = better.
        return {name: -float(b) for name, b in rows}
    except sqlite3.OperationalError:
        return {}  # FTS5 not compiled in — fall back to boosts only.


def retrieve_tables(database_id, question, k=8):
    """Return the top-k relevant tables for a question:
    [{table_name, score, reason}], best first. Deterministic."""
    docs = _table_docs(database_id)
    if not docs:
        return []

    fts = _fts_rank(docs, question)
    qlow = (question or "").lower()
    qtokens = set(_tokenize(question))

    results = []
    for table_name, _doc, cols in docs:
        score = 0.0
        reasons = []

        if table_name in fts:
            score += fts[table_name]
            reasons.append("fts")

        tnl = table_name.lower()
        if tnl and tnl in qlow:
            score += 5.0
            reasons.append("table_name_in_question")
        elif qtokens & set(_tokenize(table_name)):
            score += 1.0
            reasons.append("table_token")

        for c in cols:
            if c and c.lower() in qlow:
                score += 2.0
                reasons.append(f"column:{c}")
                break

        if score > 0:
            results.append({
                "table_name": table_name,
                "score": round(score, 4),
                "reason": ",".join(reasons) or "fts",
            })

    # Deterministic ordering: score desc, then name asc.
    results.sort(key=lambda r: (-r["score"], r["table_name"]))
    return results[: max(1, int(k or 8))]
