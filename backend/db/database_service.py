"""
database_service.py

Registration and retrieval for multi-table "database groups".

A *database* is a set of CSV files that together form one relational
SQLite database.  This module is the multi-table counterpart of
``dataset_service.py`` (which handles the legacy single-table path) and
deliberately leaves that module untouched.

Tables used (created in auth_db.init_auth_db):
    databases(id, user_id, conversation_id, name, db_path, created_at)
    database_tables(id, database_id, table_name, source_filename,
                    file_path, schema_text, row_count, created_at)
"""

import json
import sqlite3
from db.auth_db import DB_NAME


def create_database(user_id, name, conversation_id=None):
    """Create a new (empty) database group and return its id.

    The per-database SQLite file path (``db_path``) is set afterwards via
    ``set_database_path`` once the id is known.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO databases(user_id, conversation_id, name, db_path)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, conversation_id, name, None),
    )

    conn.commit()
    database_id = cursor.lastrowid
    conn.close()

    return database_id


def set_database_path(database_id, db_path):
    """Record the SQLite file path for a database group."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE databases SET db_path = ? WHERE id = ?",
        (db_path, database_id),
    )

    conn.commit()
    conn.close()


def add_database_table(
    database_id,
    table_name,
    source_filename,
    file_path,
    schema_text,
    row_count,
):
    """Register a single table (one CSV) inside a database group."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO database_tables(
            database_id,
            table_name,
            source_filename,
            file_path,
            schema_text,
            row_count
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            database_id,
            table_name,
            source_filename,
            file_path,
            schema_text,
            row_count,
        ),
    )

    conn.commit()
    table_id = cursor.lastrowid
    conn.close()

    return table_id


def get_database(database_id):
    """Return a single database group, or None."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, user_id, conversation_id, name, db_path, created_at
        FROM databases
        WHERE id = ?
        """,
        (database_id,),
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "database_id": row[0],
        "user_id": row[1],
        "conversation_id": row[2],
        "name": row[3],
        "db_path": row[4],
        "created_at": row[5],
    }


def get_database_tables(database_id):
    """Return all registered tables for a database group."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, table_name, source_filename, file_path, schema_text, row_count, created_at
        FROM database_tables
        WHERE database_id = ?
        ORDER BY created_at ASC
        """,
        (database_id,),
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "table_id": row[0],
            "table_name": row[1],
            "source_filename": row[2],
            "file_path": row[3],
            "schema_text": row[4],
            "row_count": row[5],
            "created_at": row[6],
        }
        for row in rows
    ]


def get_user_databases(user_id):
    """Return all database groups owned by a user (most recent first),
    each with its list of tables attached."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, name, db_path, conversation_id, created_at
        FROM databases
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,),
    )

    rows = cursor.fetchall()
    conn.close()

    databases = []
    for row in rows:
        databases.append(
            {
                "database_id": row[0],
                "name": row[1],
                "db_path": row[2],
                "conversation_id": row[3],
                "created_at": row[4],
                "tables": get_database_tables(row[0]),
            }
        )

    return databases


def get_latest_database_for_conversation(conversation_id):
    """Return the most recent database group for a conversation, or None."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, name, db_path, conversation_id, created_at
        FROM databases
        WHERE conversation_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (conversation_id,),
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "database_id": row[0],
        "name": row[1],
        "db_path": row[2],
        "conversation_id": row[3],
        "created_at": row[4],
        "tables": get_database_tables(row[0]),
    }


# ----------------------------------------------------------------------------
# Phase 3 — per-column schema metadata
# ----------------------------------------------------------------------------

def add_table_columns(table_id, columns):
    """Persist a list of per-column metadata dicts for one table.

    Each dict is expected to contain: column_name, data_type, ordinal,
    null_count, unique_count, sample_values (list), is_primary_key_candidate.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    for col in columns:
        cursor.execute(
            """
            INSERT INTO table_columns(
                table_id,
                column_name,
                data_type,
                ordinal,
                null_count,
                unique_count,
                sample_values,
                is_primary_key_candidate
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                table_id,
                col.get("column_name"),
                col.get("data_type"),
                col.get("ordinal"),
                col.get("null_count"),
                col.get("unique_count"),
                json.dumps(col.get("sample_values", [])),
                1 if col.get("is_primary_key_candidate") else 0,
            ),
        )

    conn.commit()
    conn.close()


def get_table_columns(table_id):
    """Return all column metadata for one table, ordered by column position."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, column_name, data_type, ordinal, null_count,
               unique_count, sample_values, is_primary_key_candidate
        FROM table_columns
        WHERE table_id = ?
        ORDER BY ordinal ASC
        """,
        (table_id,),
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "column_id": r[0],
            "column_name": r[1],
            "data_type": r[2],
            "ordinal": r[3],
            "null_count": r[4],
            "unique_count": r[5],
            "sample_values": json.loads(r[6]) if r[6] else [],
            "is_primary_key_candidate": bool(r[7]),
        }
        for r in rows
    ]


def get_database_schema(database_id):
    """Return a database with every table and its column metadata nested.

    This is the global, per-database schema representation that Phase 4
    (relationship detection) and Phase 5 (IR) will consume.
    """
    db = get_database(database_id)
    if not db:
        return None

    tables = get_database_tables(database_id)
    for table in tables:
        table["columns"] = get_table_columns(table["table_id"])

    db["tables"] = tables
    return db


# ----------------------------------------------------------------------------
# Phase 4 — detected relationships (schema-graph edges)
# ----------------------------------------------------------------------------

def add_relationships(database_id, edges):
    """Persist a list of detected relationship edge dicts."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    for edge in edges:
        cursor.execute(
            """
            INSERT INTO database_relationships(
                database_id,
                from_table,
                from_column,
                to_table,
                to_column,
                relationship_type,
                name_similarity,
                value_overlap,
                confidence,
                confirmed
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                database_id,
                edge.get("from_table"),
                edge.get("from_column"),
                edge.get("to_table"),
                edge.get("to_column"),
                edge.get("relationship_type"),
                edge.get("name_similarity"),
                edge.get("value_overlap"),
                edge.get("confidence"),
                1 if edge.get("confirmed") else 0,
            ),
        )

    conn.commit()
    conn.close()


def get_relationships(database_id):
    """Return all stored relationships for a database (highest confidence first)."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, from_table, from_column, to_table, to_column,
               relationship_type, name_similarity, value_overlap,
               confidence, confirmed
        FROM database_relationships
        WHERE database_id = ?
        ORDER BY confidence DESC
        """,
        (database_id,),
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "relationship_id": r[0],
            "from_table": r[1],
            "from_column": r[2],
            "to_table": r[3],
            "to_column": r[4],
            "relationship_type": r[5],
            "name_similarity": r[6],
            "value_overlap": r[7],
            "confidence": r[8],
            "confirmed": bool(r[9]),
        }
        for r in rows
    ]


def clear_relationships(database_id):
    """Remove all stored relationships for a database (used before re-detect)."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM database_relationships WHERE database_id = ?",
        (database_id,),
    )
    conn.commit()
    conn.close()


def get_database_graph(database_id):
    """Return the full schema graph: tables + columns (nodes) and detected
    relationships (edges).  This is what Phase 5 (IR) and Phase 6 (join-path
    discovery) will consume."""
    schema = get_database_schema(database_id)
    if not schema:
        return None
    schema["relationships"] = get_relationships(database_id)
    return schema


# ----------------------------------------------------------------------------
# Phase 8 — execution path resolution
# ----------------------------------------------------------------------------

def get_database_path(database_id):
    """Return the SQLite file path for a database group, or None.

    Small read-only helper for the execution layer: the SQL executor is given a
    db_path directly and never resolves it itself. Returns None when the
    database does not exist (or has no path recorded yet).
    """
    db = get_database(database_id)
    if not db:
        return None
    return db.get("db_path")