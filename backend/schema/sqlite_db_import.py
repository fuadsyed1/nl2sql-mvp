"""
schema/sqlite_db_import.py

Inspect an uploaded SQLite database file so it can be registered as a SpiderSQL
"database group" through the SAME metadata pipeline used by CSV / schema-only
imports. Read-only: it validates the file is a real SQLite database and returns
one spec per user table (name + CREATE statement + row count). Column
extraction and relationship detection are left to the existing
create_metadata() path — nothing new is invented here.

Generic: no table names or databases are hardcoded.
"""

import sqlite3

__all__ = ["is_sqlite_file", "inspect_sqlite_file"]

_SQLITE_MAGIC = b"SQLite format 3\x00"


def is_sqlite_file(path):
    """True when `path` begins with the SQLite file magic header."""
    try:
        with open(path, "rb") as fh:
            return fh.read(16) == _SQLITE_MAGIC
    except OSError:
        return False


def _q(name):
    return '"' + str(name).replace('"', '""') + '"'


def inspect_sqlite_file(db_path):
    """Return [{table_name, schema_text, row_count}] for every user table in the
    SQLite file at db_path. Raises ValueError with a clear message when the file
    is not a valid SQLite database or cannot be opened. `schema_text` is the
    table's real CREATE statement (falls back to the table name)."""
    if not is_sqlite_file(db_path):
        raise ValueError(
            "Uploaded file is not a valid SQLite database "
            "(missing 'SQLite format 3' header).")
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5.0)
    except sqlite3.Error as exc:
        raise ValueError(f"Could not open SQLite database: {exc}")
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
        rows = cur.fetchall()
        specs = []
        for name, create_sql in rows:
            try:
                row_count = cur.execute(
                    f"SELECT COUNT(*) FROM {_q(name)}").fetchone()[0]
            except sqlite3.Error:
                row_count = 0
            specs.append({
                "table_name": name,
                "schema_text": create_sql or name,
                "row_count": int(row_count or 0),
            })
        return specs
    except sqlite3.Error as exc:
        raise ValueError(f"Could not read SQLite schema: {exc}")
    finally:
        conn.close()
