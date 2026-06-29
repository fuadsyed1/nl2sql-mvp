"""
schema/lazy_loader.py

Phase 1 lazy-schema utilities for large-database support. These power the new
metadata/table-listing/lazy-column endpoints WITHOUT changing query execution,
SQL generation, or relationship logic. Small-mode databases are unaffected:
their tables already have columns_loaded=1, so ensure_table_columns is a no-op
that simply returns the existing columns.

No new dependencies; reads the same app_data.db metadata and the per-database
SQLite file via the existing helpers.
"""

from db.auth_db import get_connection
from db.database_service import get_table_columns, add_table_columns
from schema.schema_extractor import extract_table_columns
from schema.database_mode import LARGE_DB_TABLE_THRESHOLD

__all__ = [
    "LARGE_DB_TABLE_THRESHOLD",
    "get_database_meta",
    "list_tables",
    "ensure_table_columns",
]


def get_database_meta(database_id):
    """Return lightweight metadata for a database, or None if not found.

    Shape: {database_id, name, mode, table_count, query_ready}. query_ready is a
    convenience hint (large DBs are query-first); the frontend still applies its
    own gating for small mode (relationship finalize)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, mode, table_count FROM databases WHERE id = ?",
        (database_id,),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    table_count = row[3]
    if not table_count:
        cur.execute(
            "SELECT COUNT(*) FROM database_tables WHERE database_id = ?",
            (database_id,),
        )
        table_count = cur.fetchone()[0]
    conn.close()

    mode = row[2] or "small"
    return {
        "database_id": row[0],
        "name": row[1],
        "mode": mode,
        "table_count": table_count,
        "query_ready": mode == "large",
    }


def list_tables(database_id, q=None, limit=50, offset=0):
    """Return a paginated, optionally filtered list of a database's tables
    (names + row_count + columns_loaded only — no column data)."""
    try:
        limit = max(1, min(int(limit or 50), 500))
    except (TypeError, ValueError):
        limit = 50
    try:
        offset = max(0, int(offset or 0))
    except (TypeError, ValueError):
        offset = 0

    where = "WHERE database_id = ?"
    params = [database_id]
    if q and str(q).strip():
        where += " AND table_name LIKE ?"
        params.append(f"%{str(q).strip()}%")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM database_tables {where}", params)
    total = cur.fetchone()[0]
    cur.execute(
        f"""
        SELECT id, table_name, row_count, columns_loaded
        FROM database_tables
        {where}
        ORDER BY table_name ASC
        LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    )
    rows = cur.fetchall()
    conn.close()

    return {
        "tables": [
            {
                "table_id": r[0],
                "table_name": r[1],
                "row_count": r[2],
                "columns_loaded": bool(r[3]),
            }
            for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def ensure_table_columns(database_id, table_name):
    """Return a table's columns, extracting + persisting them on first access if
    they were not loaded yet (large mode). For already-loaded tables (all small-
    mode tables today) this just returns the stored columns. Returns None if the
    database or table is unknown."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT db_path FROM databases WHERE id = ?", (database_id,))
    drow = cur.fetchone()
    if not drow:
        conn.close()
        return None
    db_path = drow[0]
    cur.execute(
        "SELECT id, columns_loaded FROM database_tables "
        "WHERE database_id = ? AND table_name = ?",
        (database_id, table_name),
    )
    trow = cur.fetchone()
    conn.close()
    if not trow:
        return None

    table_id, loaded = trow[0], trow[1]

    if not loaded:
        # Extract column metadata from the per-database SQLite file (the table
        # exists there even when empty), persist it, then mark loaded.
        try:
            meta = extract_table_columns(db_path, table_name)
        except Exception:
            meta = []
        if meta:
            add_table_columns(table_id, meta)
        conn2 = get_connection()
        c2 = conn2.cursor()
        c2.execute(
            "UPDATE database_tables SET columns_loaded = 1 WHERE id = ?",
            (table_id,),
        )
        conn2.commit()
        conn2.close()

    return {
        "table_id": table_id,
        "table_name": table_name,
        "columns": get_table_columns(table_id),
    }
