"""
schema_extractor.py

Phase 3 — rich per-column schema extraction.

For each table loaded into a database group's SQLite file, compute:
    - column name
    - inferred data type (the affinity load_csv_to_sqlite already assigned)
    - null count
    - unique (distinct, non-null) count
    - a handful of sample values
    - whether the column is a candidate primary key

Extraction reads the ALREADY-LOADED SQLite table rather than re-parsing the
CSV, so it reuses the loader's type inference and value cleaning instead of
duplicating that logic.  It performs no cross-table reasoning — relationship
detection is Phase 4.
"""

import sqlite3


def _quote_ident(name: str) -> str:
    """Double-quote an identifier, escaping embedded quotes, for safe SQL use."""
    return '"' + str(name).replace('"', '""') + '"'


def extract_table_columns(db_path: str, table_name: str, sample_size: int = 5):
    """Return per-column metadata for a single loaded table.

    Each entry is a dict:
        column_name, data_type, ordinal, null_count, unique_count,
        sample_values (list), is_primary_key_candidate (bool)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    qtable = _quote_ident(table_name)

    # Total rows — needed for the primary-key-candidate test.
    cursor.execute(f"SELECT COUNT(*) FROM {qtable}")
    row_count = cursor.fetchone()[0]

    # Column list, declared types, and positions.
    # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
    cursor.execute(f"PRAGMA table_info({qtable})")
    pragma_rows = cursor.fetchall()

    columns = []

    for cid, name, decl_type, _notnull, _dflt, _pk in pragma_rows:
        qcol = _quote_ident(name)

        # Null count = total rows minus non-null count (COUNT(col) skips NULLs).
        cursor.execute(f"SELECT COUNT(*) - COUNT({qcol}) FROM {qtable}")
        null_count = cursor.fetchone()[0]

        # Distinct non-null values.
        cursor.execute(f"SELECT COUNT(DISTINCT {qcol}) FROM {qtable}")
        unique_count = cursor.fetchone()[0]

        # A few distinct sample values for downstream reasoning / display.
        cursor.execute(
            f"SELECT DISTINCT {qcol} FROM {qtable} "
            f"WHERE {qcol} IS NOT NULL LIMIT ?",
            (sample_size,),
        )
        sample_values = [r[0] for r in cursor.fetchall()]

        # Candidate PK: every row has a distinct, non-null value.
        is_pk_candidate = (
            row_count > 0
            and null_count == 0
            and unique_count == row_count
        )

        columns.append({
            "column_name": name,
            "data_type": decl_type or "TEXT",
            "ordinal": cid,
            "null_count": null_count,
            "unique_count": unique_count,
            "sample_values": sample_values,
            "is_primary_key_candidate": bool(is_pk_candidate),
        })

    conn.close()
    return columns
