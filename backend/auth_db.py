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
    # Datasets  (legacy single-table path — unchanged)
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
    # Databases  (NEW — a logical multi-table database / "database group")
    #
    # One row per uploaded relational dataset (a set of CSVs that together
    # form one SQLite database).  Each database owns its own SQLite file at
    # ``db_path`` so its tables never collide with app_data.db or with the
    # tables of other databases.
    # ------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS databases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            conversation_id INTEGER,
            name TEXT NOT NULL,
            db_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(conversation_id) REFERENCES conversations(id)
        )
    """)

    # ------------------------------------------------------------------
    # Database tables  (NEW — one row per CSV/table inside a database)
    #
    # Stores per-table metadata: the real SQLite table name, the source
    # CSV, the per-table schema string, and the inserted row count.  This
    # is the metadata foundation that Phase 3+ (rich schema extraction and
    # relationship detection) will build on.
    # ------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS database_tables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            database_id INTEGER NOT NULL,
            table_name TEXT NOT NULL,
            source_filename TEXT,
            file_path TEXT,
            schema_text TEXT,
            row_count INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(database_id) REFERENCES databases(id)
        )
    """)

    # ------------------------------------------------------------------
    # Table columns  (NEW — Phase 3: rich per-column schema metadata)
    #
    # One row per column of a loaded table.  Holds the inferred type plus
    # null/unique counts, sample values, and a candidate-primary-key flag.
    # This is per-table (single-table) metadata only; cross-table
    # relationship detection (Phase 4) lives in its own future table.
    # ------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS table_columns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_id INTEGER NOT NULL,
            column_name TEXT NOT NULL,
            data_type TEXT,
            ordinal INTEGER,
            null_count INTEGER,
            unique_count INTEGER,
            sample_values TEXT,
            is_primary_key_candidate INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(table_id) REFERENCES database_tables(id)
        )
    """)

    # ------------------------------------------------------------------
    # Database relationships  (NEW — Phase 4: detected foreign-key edges)
    #
    # One row per detected relationship.  Direction: from_* is the foreign
    # key (many) side, to_* is the primary key (one) side.  name_similarity
    # and value_overlap are stored alongside the blended confidence so the
    # scoring stays auditable and tunable.  confirmed is set automatically
    # by the confidence bands (no UI confirmation step yet).
    # ------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS database_relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            database_id INTEGER NOT NULL,
            from_table TEXT,
            from_column TEXT,
            to_table TEXT,
            to_column TEXT,
            relationship_type TEXT,
            name_similarity REAL,
            value_overlap REAL,
            confidence REAL,
            confirmed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(database_id) REFERENCES databases(id)
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
