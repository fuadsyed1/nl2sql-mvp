"""
schema/key_extractor.py

Code-based extraction of REAL declared foreign keys from a SQLite database via
`PRAGMA foreign_key_list`. No LLM, no value scans — pure metadata. Used to give
clean databases their true relationships (confidence 1.0, confirmed) instead of
relying on inference.

`PRAGMA foreign_key_list(<table>)` returns rows of:
    (id, seq, parent_table, from_column, to_column, on_update, on_delete, match)
where the queried table is the child (the side that holds the FK). When
`to_column` is NULL (the FK references the parent's primary key implicitly), we
resolve it to the parent's primary-key column.
"""

import sqlite3

__all__ = ["extract_foreign_keys"]


def _qi(name):
    return '"' + str(name).replace('"', '""') + '"'


def _pk_columns(conn, table):
    """Primary-key column names of a table, in key order (from PRAGMA table_info)."""
    cols = []
    try:
        for row in conn.execute(f"PRAGMA table_info({_qi(table)})").fetchall():
            # cid, name, type, notnull, dflt_value, pk
            pk = row[5]
            if pk and int(pk) > 0:
                cols.append((int(pk), row[1]))
    except sqlite3.Error:
        return []
    cols.sort()
    return [c[1] for c in cols]


def extract_foreign_keys(db_path):
    """Return real declared foreign-key edges for every table in the SQLite file:
    [{from_table, from_column, to_table, to_column, relationship_type,
      name_similarity, value_overlap, confidence, confirmed}]. Empty list when the
    database has no declared foreign keys (or cannot be read)."""
    if not db_path:
        return []
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error:
        return []

    edges, seen = [], set()
    try:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        for t in tables:
            try:
                rows = conn.execute(f"PRAGMA foreign_key_list({_qi(t)})").fetchall()
            except sqlite3.Error:
                continue
            for row in rows:
                parent, from_col, to_col = row[2], row[3], row[4]
                if not (from_col and parent):
                    continue
                if not to_col:
                    pks = _pk_columns(conn, parent)
                    to_col = pks[0] if pks else from_col
                key = (t, from_col, parent, to_col)
                if key in seen:
                    continue
                seen.add(key)
                edges.append({
                    "from_table": t,
                    "from_column": from_col,
                    "to_table": parent,
                    "to_column": to_col,
                    "relationship_type": "declared_foreign_key",
                    "name_similarity": 1.0,
                    "value_overlap": None,
                    "confidence": 1.0,
                    "confirmed": True,
                    "source": "pk_fk",
                })
    finally:
        conn.close()
    return edges
