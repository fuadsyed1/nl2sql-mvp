import sqlite3
from auth_db import DB_NAME


def save_schema_dataset(user_id, name, schema_text):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO datasets(user_id, name, schema_text, file_type, file_path)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, name, schema_text, "schema", None)
    )

    conn.commit()
    dataset_id = cursor.lastrowid
    conn.close()

    return {
        "success": True,
        "dataset_id": dataset_id,
        "name": name,
        "schema_text": schema_text
    }


def get_latest_dataset(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, name, schema_text, file_type, file_path
        FROM datasets
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (user_id,)
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "dataset_id": row[0],
        "name": row[1],
        "schema_text": row[2],
        "file_type": row[3],
        "file_path": row[4]
    }

def save_query(user_id, dataset_id, question, clean_query, sql):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO queries(user_id, dataset_id, question, clean_query, sql)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, dataset_id, question, clean_query, sql)
    )

    conn.commit()
    query_id = cursor.lastrowid
    conn.close()

    return query_id

def get_user_queries(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, dataset_id, question, clean_query, sql, created_at
        FROM queries
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,)
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "query_id": row[0],
            "dataset_id": row[1],
            "question": row[2],
            "clean_query": row[3],
            "sql": row[4],
            "created_at": row[5]
        }
        for row in rows
    ]

def save_chat_state(user_id, pending_action, last_question):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR REPLACE INTO chat_state(user_id, pending_action, last_question)
        VALUES (?, ?, ?)
        """,
        (user_id, pending_action, last_question)
    )

    conn.commit()
    conn.close()


def get_chat_state(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT pending_action, last_question
        FROM chat_state
        WHERE user_id = ?
        """,
        (user_id,)
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "pending_action": row[0],
        "last_question": row[1]
    }


def clear_chat_state(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM chat_state
        WHERE user_id = ?
        """,
        (user_id,)
    )

    conn.commit()
    conn.close()