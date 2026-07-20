"""
tests/test_relationship_persistence.py

Provenance + finality persistence: source is written/read, the finalized flag
round-trips (NULL -> False), user-declared CRUD works, and the declared filter
returns only authoritative edges. Uses a temp app_data.db via monkeypatched
DB_NAME; no app database is touched.
"""
import sqlite3
import importlib

import db.auth_db as auth_db
import db.database_service as dbs


def _fresh_db(tmp_path, monkeypatch):
    dbfile = str(tmp_path / "app_data_test.db")
    monkeypatch.setattr(auth_db, "DB_NAME", dbfile)
    monkeypatch.setattr(dbs, "DB_NAME", dbfile)
    auth_db.init_auth_db()
    # one databases row to attach relationships/finality to
    conn = sqlite3.connect(dbfile)
    conn.execute("INSERT INTO databases(id, user_id, name) VALUES (52, 1, 'x')")
    conn.commit(); conn.close()
    return dbfile


def test_source_written_and_read(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    dbs.add_relationships(52, [
        {"from_table": "a", "from_column": "b_id", "to_table": "b",
         "to_column": "id", "relationship_type": "foreign_key",
         "confidence": 0.8, "confirmed": 0, "source": "inferred"},
        {"from_table": "c", "from_column": "d_id", "to_table": "d",
         "to_column": "id", "relationship_type": "foreign_key",
         "confidence": 1.0, "confirmed": 1, "source": "declared_fk"},
    ])
    rels = dbs.get_relationships(52)
    by_from = {r["from_table"]: r for r in rels}
    assert by_from["a"]["source"] == "inferred"
    assert by_from["c"]["source"] == "declared_fk"


def test_finalized_flag_roundtrip_and_null_is_false(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    # freshly inserted databases row has NULL flag -> False
    assert dbs.get_relationships_finalized(52) is False
    dbs.set_relationships_finalized(52, True)
    assert dbs.get_relationships_finalized(52) is True
    dbs.set_relationships_finalized(52, False)
    assert dbs.get_relationships_finalized(52) is False
    # unknown database -> False, never raises
    assert dbs.get_relationships_finalized(9999) is False


def test_user_crud_and_declared_filter(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    dbs.add_relationships(52, [
        {"from_table": "a", "from_column": "b_id", "to_table": "b",
         "to_column": "id", "relationship_type": "foreign_key",
         "confidence": 0.8, "confirmed": 0, "source": "inferred"},
    ])
    rid = dbs.add_user_relationship(52, "sales_orders", "sales_rep_id",
                                    "employees", "employee_id")
    declared = dbs.get_declared_relationships(52)
    assert len(declared) == 1
    assert declared[0]["source"] == "user"
    assert declared[0]["from_column"] == "sales_rep_id"
    # Approval is separate from origin: a user row is unconfirmed until the
    # set is finalized (it still counts as declared by source).
    assert declared[0]["confirmed"] is False

    dbs.update_relationship(rid, to_column="emp_id")
    got = {r["relationship_id"]: r for r in dbs.get_relationships(52)}[rid]
    assert got["to_column"] == "emp_id"
    assert got["source"] == "user"

    dbs.delete_relationship(rid)
    assert dbs.get_declared_relationships(52) == []
