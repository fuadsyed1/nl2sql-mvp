import os
import shutil
import sqlite3
from auth_db import DB_NAME


def create_conversation(user_id, title="New Chat"):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO conversations(user_id, title)
        VALUES (?, ?)
        """,
        (user_id, title)
    )

    conn.commit()
    conversation_id = cursor.lastrowid
    conn.close()

    return conversation_id


def get_user_conversations(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, title, created_at
        FROM conversations
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,)
    )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "conversation_id": row[0],
            "title": row[1],
            "created_at": row[2]
        }
        for row in rows
    ]


def delete_conversation(conversation_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM queries WHERE conversation_id = ?",
        (conversation_id,)
    )

    cursor.execute(
        "DELETE FROM datasets WHERE conversation_id = ?",
        (conversation_id,)
    )

    cursor.execute(
        "DELETE FROM conversations WHERE id = ?",
        (conversation_id,)
    )

    conn.commit()
    conn.close()

def update_conversation_title(conversation_id, title):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE conversations
        SET title = ?
        WHERE id = ?
        """,
        (title[:35], conversation_id)
    )

    conn.commit()
    conn.close()

def factory_reset_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM queries WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM datasets WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM chat_state WHERE user_id = ?", (user_id,))

    conn.commit()
    conn.close()

    user_upload_folder = f"uploads/user_{user_id}"

    if os.path.exists(user_upload_folder):
        shutil.rmtree(user_upload_folder)

    return {
        "success": True,
        "message": "Factory reset completed."
    }