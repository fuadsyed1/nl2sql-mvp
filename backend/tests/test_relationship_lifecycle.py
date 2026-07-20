"""
tests/test_relationship_lifecycle.py

Migration safety, ownership enforcement, delete/rollback, and status semantics.
"""
import sqlite3
import db.auth_db as auth_db
import db.database_service as dbs


def _init(tmp_path, monkeypatch):
    dbfile = str(tmp_path / "app_data.db")
    monkeypatch.setattr(auth_db, "DB_NAME", dbfile)
    monkeypatch.setattr(dbs, "DB_NAME", dbfile)
    auth_db.init_auth_db()
    return dbfile


def test_migration_preserves_legacy_as_unknown_and_review(tmp_path, monkeypatch):
    dbfile = _init(tmp_path, monkeypatch)
    conn = sqlite3.connect(dbfile)
    # simulate a legacy database + relationship row (source NULL, status NULL)
    conn.execute("INSERT INTO databases(id, user_id, name, relationship_status, "
                 "relationships_finalized) VALUES (7, 1, 'legacy', NULL, NULL)")
    conn.execute("INSERT INTO database_relationships(database_id, from_table, "
                 "from_column, to_table, to_column, source) "
                 "VALUES (7, 'a', 'b_id', 'b', 'id', NULL)")
    conn.commit(); conn.close()
    # re-run migration
    auth_db.init_auth_db()
    assert dbs.get_relationship_status(7) == "review"       # never auto-finalized
    assert dbs.get_relationships_finalized(7) is False
    rels = dbs.get_relationships(7)
    assert len(rels) == 1 and rels[0]["source"] == "legacy_unknown"  # not deleted, not 'inferred'


def test_status_roundtrip(tmp_path, monkeypatch):
    dbfile = _init(tmp_path, monkeypatch)
    conn = sqlite3.connect(dbfile)
    conn.execute("INSERT INTO databases(id, user_id, name) VALUES (3, 1, 'x')")
    conn.commit(); conn.close()
    dbs.set_relationship_status(3, "finalized")
    assert dbs.get_relationships_finalized(3) is True
    dbs.set_relationship_status(3, "review")
    assert dbs.get_relationships_finalized(3) is False


def test_delete_database_rollback(tmp_path, monkeypatch):
    dbfile = _init(tmp_path, monkeypatch)
    conn = sqlite3.connect(dbfile)
    conn.execute("INSERT INTO databases(id, user_id, name, db_path) "
                 "VALUES (9, 1, 'x', 'uploads/user_1/databases/db_9/data.db')")
    conn.execute("INSERT INTO database_tables(id, database_id, table_name) "
                 "VALUES (100, 9, 't')")
    conn.execute("INSERT INTO database_relationships(database_id, from_table) "
                 "VALUES (9, 't')")
    conn.commit(); conn.close()
    path = dbs.delete_database(9)
    assert path.endswith("db_9/data.db")
    assert dbs.get_relationships(9) == []
    conn = sqlite3.connect(dbfile)
    assert conn.execute("SELECT COUNT(*) FROM databases WHERE id=9").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM database_tables WHERE database_id=9").fetchone()[0] == 0
    conn.close()


def test_ownership_chain(tmp_path, monkeypatch):
    dbfile = _init(tmp_path, monkeypatch)
    conn = sqlite3.connect(dbfile)
    conn.execute("INSERT INTO users(id, username, password) VALUES (1,'alice','p')")
    conn.execute("INSERT INTO users(id, username, password) VALUES (2,'bob','p')")
    conn.execute("INSERT INTO conversations(id, user_id, title) VALUES (10,1,'A')")
    conn.execute("INSERT INTO conversations(id, user_id, title) VALUES (20,2,'B')")
    conn.execute("INSERT INTO databases(id, user_id, conversation_id, name) "
                 "VALUES (5, 1, 10, 'x')")
    conn.commit(); conn.close()

    ok, _ = dbs.verify_database_access(1, "alice", 10, 5)
    assert ok is True
    # wrong user
    assert dbs.verify_database_access(2, "bob", 20, 5)[0] is False
    # right user, wrong username pair
    assert dbs.verify_database_access(1, "bob", 10, 5)[0] is False
    # right user, wrong conversation
    assert dbs.verify_database_access(1, "alice", 20, 5)[0] is False
    # bare user_id with no username
    assert dbs.verify_database_access(1, None, 10, 5)[0] is False
