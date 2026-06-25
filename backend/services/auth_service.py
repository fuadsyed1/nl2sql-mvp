import sqlite3
from db.auth_db import DB_NAME


def create_user(username, password):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO users(username, password)
            VALUES (?, ?)
            """,
            (username, password)
        )

        conn.commit()
        return {"success": True}

    except sqlite3.IntegrityError:
        return {
            "success": False,
            "message": "Username already exists"
        }

    finally:
        conn.close()


def login_user(username, password):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, username
        FROM users
        WHERE username = ? AND password = ?
        """,
        (username, password)
    )

    row = cursor.fetchone()

    conn.close()

    if row:
        return {
            "success": True,
            "user_id": row[0],
            "username": row[1]
        }

    return {
        "success": False,
        "message": "Invalid credentials"
    }