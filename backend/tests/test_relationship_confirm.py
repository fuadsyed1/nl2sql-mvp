"""
tests/test_relationship_confirm.py

Approval (confirmed) is separate from origin (source):
  * finalize marks every current row confirmed=1 (renders Confirmed);
  * saving/editing returns the set to unconfirmed (renders Suggested);
  * migration enforces finalized-database => rows confirmed (fixes legacy
    finalized sets that rendered as Suggested), without reverting status;
  * replacing the set drops removed rows and keeps added ones;
  * origin is preserved across edits.
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


def _db(dbfile, dbid=1, status="review"):
    conn = sqlite3.connect(dbfile)
    conn.execute("INSERT INTO databases(id, user_id, name, relationship_status) "
                 "VALUES (?, 1, 'x', ?)", (dbid, status))
    conn.commit(); conn.close()


def _infedge(ft, fc, tt, tc):
    return {"from_table": ft, "from_column": fc, "to_table": tt, "to_column": tc,
            "relationship_type": "foreign_key", "confidence": 0.55,
            "confirmed": 0, "source": "inferred"}


def test_finalize_confirms_all_rows(tmp_path, monkeypatch):
    dbfile = _init(tmp_path, monkeypatch); _db(dbfile)
    dbs.add_relationships(1, [_infedge("a", "b_id", "b", "id"),
                              _infedge("c", "d_id", "d", "id")])
    assert all(r["confirmed"] is False for r in dbs.get_relationships(1))
    # simulate finalize endpoint
    dbs.set_all_relationships_confirmed(1, True)
    dbs.set_relationship_status(1, "finalized")
    rels = dbs.get_relationships(1)
    assert all(r["confirmed"] is True for r in rels)
    assert all(r["source"] == "inferred" for r in rels)   # origin preserved
    assert dbs.get_relationship_status(1) == "finalized"


def test_edit_returns_to_review_unconfirmed(tmp_path, monkeypatch):
    dbfile = _init(tmp_path, monkeypatch); _db(dbfile, status="finalized")
    dbs.add_relationships(1, [_infedge("a", "b_id", "b", "id")])
    dbs.set_all_relationships_confirmed(1, True)
    # simulate an edit endpoint
    dbs.set_all_relationships_confirmed(1, False)
    dbs.set_relationship_status(1, "review")
    assert all(r["confirmed"] is False for r in dbs.get_relationships(1))
    assert dbs.get_relationship_status(1) == "review"


def test_migration_syncs_finalized_confirmed(tmp_path, monkeypatch):
    dbfile = _init(tmp_path, monkeypatch)
    # a legacy FINALIZED db whose rows are (wrongly) confirmed=0
    _db(dbfile, dbid=53, status="finalized")
    _db(dbfile, dbid=54, status="review")
    conn = sqlite3.connect(dbfile)
    for did in (53, 54):
        conn.execute("INSERT INTO database_relationships(database_id, from_table, "
                     "from_column, to_table, to_column, source, confirmed) "
                     "VALUES (?, 'a', 'b_id', 'b', 'id', 'inferred', 0)", (did,))
    conn.commit(); conn.close()
    auth_db.init_auth_db()   # migration
    assert all(r["confirmed"] is True for r in dbs.get_relationships(53))   # fixed
    assert all(r["confirmed"] is False for r in dbs.get_relationships(54))  # untouched


def test_replace_drops_removed_keeps_added(tmp_path, monkeypatch):
    dbfile = _init(tmp_path, monkeypatch); _db(dbfile)
    dbs.add_relationships(1, [_infedge("old", "x_id", "y", "id")])
    # simulate PUT replace: clear + add the reviewed set (removed 'old', added new)
    dbs.clear_relationships(1)
    dbs.add_relationships(1, [_infedge("new", "z_id", "w", "id")])
    fts = {r["from_table"] for r in dbs.get_relationships(1)}
    assert "old" not in fts and "new" in fts


def test_add_user_unconfirmed_and_update_preserves_source(tmp_path, monkeypatch):
    dbfile = _init(tmp_path, monkeypatch); _db(dbfile)
    dbs.add_relationships(1, [_infedge("sales_orders", "sales_rep_id",
                                       "employees", "employee_id")])
    rid = dbs.get_relationships(1)[0]["relationship_id"]
    dbs.update_relationship(rid, to_column="emp_id")
    row = dbs.get_relationships(1)[0]
    assert row["to_column"] == "emp_id"
    assert row["source"] == "inferred"     # origin preserved on edit
    assert row["confirmed"] is False       # edit leaves it unapproved
    uid = dbs.add_user_relationship(1, "t", "c", "t2", "c2")
    urow = {r["relationship_id"]: r for r in dbs.get_relationships(1)}[uid]
    assert urow["source"] == "user" and urow["confirmed"] is False


def test_backend_status_is_authoritative_gate(tmp_path, monkeypatch):
    """Frontend/chat state is never trusted for query readiness. The server-side
    gate (get_relationships_finalized, checked by execute_sql) reflects the
    database's true backend status: a 'review' database stays query-disabled even
    if a client believes it is finalized."""
    dbfile = _init(tmp_path, monkeypatch); _db(dbfile, dbid=1, status="review")
    dbs.add_relationships(1, [_infedge("a", "b_id", "b", "id")])
    # Backend says review -> gate closed regardless of any client claim.
    assert dbs.get_relationship_status(1) == "review"
    assert dbs.get_relationships_finalized(1) is False
    # Only a genuine backend finalize opens the gate.
    dbs.set_all_relationships_confirmed(1, True)
    dbs.set_relationship_status(1, "finalized")
    assert dbs.get_relationship_status(1) == "finalized"
    assert dbs.get_relationships_finalized(1) is True
