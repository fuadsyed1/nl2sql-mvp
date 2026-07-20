import sqlite3

DB_NAME = "app_data.db"


def get_connection():
    return sqlite3.connect(DB_NAME)


def _ensure_column(cursor, table, column, decl):
    """Idempotently add a column to an existing table. SQLite's ALTER TABLE ADD
    COLUMN sets existing rows to the column's DEFAULT, so this is a safe, repeat-
    able migration that never rewrites or drops data."""
    cursor.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cursor.fetchall()}
    if column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


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

    # ------------------------------------------------------------------
    # Phase 0 migration — large-database support (idempotent, non-breaking)
    #
    # Existing databases default to small mode with columns already loaded, so
    # the current small-DB flow is unchanged. Large mode is opt-in (Phase 2).
    # ------------------------------------------------------------------
    _ensure_column(cursor, "databases", "mode", "TEXT DEFAULT 'small'")
    _ensure_column(cursor, "databases", "table_count", "INTEGER DEFAULT 0")
    _ensure_column(cursor, "database_tables", "columns_loaded", "INTEGER DEFAULT 1")
    _ensure_column(cursor, "database_relationships", "source", "TEXT")
    # Relationship finality flag (origin vs finality). NULL for pre-existing
    # rows so the one-time backfill below can classify them; the resolver
    # sets it explicitly (1 authoritative/declared, 0 unfinalized suggestions)
    # for every database it processes thereafter.
    _ensure_column(cursor, "databases", "relationships_finalized", "INTEGER")
    # Relationship review state: 'review' (unfinalized suggestions/declared
    # set awaiting approval) or 'finalized' (authoritative; querying enabled).
    _ensure_column(cursor, "databases", "relationship_status", "TEXT")

    # Backfill table_count for existing databases (safe to re-run).
    cursor.execute(
        """
        UPDATE databases
        SET table_count = (
            SELECT COUNT(*) FROM database_tables
            WHERE database_tables.database_id = databases.id
        )
        WHERE table_count IS NULL OR table_count = 0
        """
    )

    # One-time relationship migration (idempotent; only touches rows/columns still
    # NULL, i.e. databases/rows that predate these columns). SAFE by design:
    #  * No existing database is auto-finalized. Every legacy database enters
    #    'review' and must be explicitly approved ("Review and approve existing
    #    relationships") before querying — its stored set was never reviewed.
    #  * Legacy relationship rows of unknown origin (source IS NULL) are preserved
    #    as 'legacy_unknown' (never guessed as 'inferred', never deleted or
    #    redetected). They are shown to the user for review.
    cursor.execute(
        "UPDATE databases SET relationship_status = 'review' "
        "WHERE relationship_status IS NULL"
    )
    cursor.execute(
        "UPDATE databases SET relationships_finalized = 0 "
        "WHERE relationships_finalized IS NULL"
    )
    cursor.execute(
        "UPDATE database_relationships SET source = 'legacy_unknown' "
        "WHERE source IS NULL"
    )

    # Invariant sync (idempotent): a FINALIZED database's relationship rows must
    # all be confirmed (approved). Earlier builds set databases.relationship_status
    # to 'finalized' without marking the rows, so finalized sets rendered as
    # "suggested". Enforce it here without reverting any database's status.
    cursor.execute(
        "UPDATE database_relationships SET confirmed = 1 "
        "WHERE confirmed = 0 AND database_id IN ("
        "  SELECT id FROM databases WHERE relationship_status = 'finalized')"
    )

    conn.commit()
    conn.close()
