"""
test_get_database_path.py — offline test for Phase 8 step 3.

Verifies get_database_path against a temporary metadata DB (the same `databases`
table schema created in auth_db.init_auth_db). No server, no LLM, no pytest:

    python test_get_database_path.py
"""

import os
import sqlite3
import tempfile

import database_service as ds


def build_metadata_db(path):
    """Create just the `databases` table and seed one row."""
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE databases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            conversation_id INTEGER,
            name TEXT,
            db_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "INSERT INTO databases (user_id, conversation_id, name, db_path) VALUES (?,?,?,?)",
        (1, None, "PetShop", "/data/uploads/user_1/databases/db_1/data.db"),
    )
    # a second database group with no path recorded yet
    conn.execute(
        "INSERT INTO databases (user_id, conversation_id, name, db_path) VALUES (?,?,?,?)",
        (1, None, "Pending", None),
    )
    conn.commit()
    conn.close()


def main():
    with tempfile.TemporaryDirectory() as tmp:
        meta = os.path.join(tmp, "meta.db")
        build_metadata_db(meta)

        original = ds.DB_NAME
        ds.DB_NAME = meta  # point the read-only helpers at the temp metadata DB
        try:
            # existing database -> its recorded path
            assert ds.get_database_path(1) == "/data/uploads/user_1/databases/db_1/data.db"
            print("[1] existing database -> db_path -> OK")

            # database exists but no path recorded -> None
            assert ds.get_database_path(2) is None
            print("[2] database with no path recorded -> None -> OK")

            # missing database id -> None
            assert ds.get_database_path(9999) is None
            print("[3] missing database id -> None -> OK")

            # existing functions still present / unbroken
            assert ds.get_database(1)["name"] == "PetShop"
            assert ds.get_database(9999) is None
            print("[4] existing get_database still works (preserved) -> OK")
        finally:
            ds.DB_NAME = original

    print("\nRESULT: 4/4 passed — get_database_path verified")


if __name__ == "__main__":
    main()