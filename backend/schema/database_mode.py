"""
schema/database_mode.py

Single source of truth for a database's size "mode". A database is "large" when
it has more than LARGE_DB_TABLE_THRESHOLD tables; otherwise "small". Mode is set
once at creation/import time and read back via /database/{id}/meta.

Small mode preserves the current eager behavior (full column extraction +
relationship detection + finalize flow). Large mode skips expensive global
detection and defers column loading.
"""

from db.auth_db import get_connection

__all__ = [
    "LARGE_DB_TABLE_THRESHOLD",
    "is_large_database",
    "determine_database_mode",
    "update_database_mode",
    "set_table_columns_loaded",
]

# Tune here. Databases with more than this many tables import as "large".
LARGE_DB_TABLE_THRESHOLD = 40


def is_large_database(table_count):
    return (table_count or 0) > LARGE_DB_TABLE_THRESHOLD


def determine_database_mode(table_count):
    return "large" if is_large_database(table_count) else "small"


def update_database_mode(database_id, table_count, mode=None):
    """Persist a database's mode + table_count. If mode is omitted it is derived
    from table_count. Returns the mode that was written."""
    mode = mode or determine_database_mode(table_count)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE databases SET mode = ?, table_count = ? WHERE id = ?",
        (mode, table_count, database_id),
    )
    conn.commit()
    conn.close()
    return mode


def set_table_columns_loaded(table_id, loaded):
    """Mark a registered table's columns as loaded (1) or not-yet-loaded (0)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE database_tables SET columns_loaded = ? WHERE id = ?",
        (1 if loaded else 0, table_id),
    )
    conn.commit()
    conn.close()
