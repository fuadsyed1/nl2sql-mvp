import sqlite3

DB_NAME = "app_data.db"


def get_connection():
    return sqlite3.connect(DB_NAME)


def init_auth_db():
    conn = get_connection()
    cursor = conn.cursor()

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    # ------------------------------------------------------------------
    # Conversations
    # ------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # ------------------------------------------------------------------
    # Datasets
    # ------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS datasets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            conversation_id INTEGER,
            name TEXT NOT NULL,
            schema_text TEXT,
            file_type TEXT,
            file_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(conversation_id) REFERENCES conversations(id)
        )
    """)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            conversation_id INTEGER,
            dataset_id INTEGER,
            question TEXT NOT NULL,
            clean_query TEXT,
            sql TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(conversation_id) REFERENCES conversations(id),
            FOREIGN KEY(dataset_id) REFERENCES datasets(id)
        )
    """)

    # ------------------------------------------------------------------
    # Chat State
    # ------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_state (
            user_id INTEGER PRIMARY KEY,
            pending_action TEXT,
            last_question TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()