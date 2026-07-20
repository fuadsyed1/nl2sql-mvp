"""
tests/test_relationship_resolver.py

Resolver precedence under the finalized lifecycle:
  * small + no declared -> inference suggestions, status 'review', never final;
  * declared PK/FK present -> pk_fk edges, NO inference, status 'review';
  * large + no declared + no user rows -> REJECTED (nothing stored);
  * large + no declared + user rows -> usable (user rows), status 'review';
  * user rows preserved on explicit redetect (force_inference).
Uses a temp app_data.db; pure-computation inputs monkeypatched.
"""
import sqlite3

import db.auth_db as auth_db
import db.database_service as dbs
import services.relationship_resolver as rr


def _fresh(tmp_path, monkeypatch, mode="small"):
    dbfile = str(tmp_path / "app_data.db")
    monkeypatch.setattr(auth_db, "DB_NAME", dbfile)
    monkeypatch.setattr(dbs, "DB_NAME", dbfile)
    auth_db.init_auth_db()
    conn = sqlite3.connect(dbfile)
    conn.execute("INSERT INTO databases(id, user_id, name, db_path) "
                 "VALUES (1, 1, 'x', '/tmp/x.db')")
    conn.commit(); conn.close()
    monkeypatch.setattr(rr, "get_database_meta", lambda _id: {"mode": mode})
    monkeypatch.setattr(rr, "_benchmark_edges", lambda _id: [])
    monkeypatch.setattr(rr, "extract_foreign_keys", lambda _p: [])
    return dbfile


_INFERRED = [{"from_table": "a", "from_column": "b_id", "to_table": "b",
              "to_column": "id", "relationship_type": "foreign_key",
              "confidence": 0.55}]
_DECLARED = [{"from_table": "orders", "from_column": "customer_id",
              "to_table": "customers", "to_column": "id",
              "relationship_type": "declared_foreign_key", "confidence": 1.0,
              "confirmed": True, "source": "pk_fk"}]


def test_small_no_declared_infers_review(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, mode="small")
    monkeypatch.setattr(rr, "detect_relationships", lambda _id: [dict(e) for e in _INFERRED])
    res = rr.resolve_and_store_relationships(1, db_path="/tmp/x.db")
    assert res["rejected"] is False and res["status"] == "review"
    assert res["edges"] and res["edges"][0]["source"] == "inferred"
    assert dbs.get_relationship_status(1) == "review"
    assert dbs.get_relationships_finalized(1) is False


def test_declared_pkfk_no_inference_review(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, mode="small")
    monkeypatch.setattr(rr, "extract_foreign_keys", lambda _p: [dict(e) for e in _DECLARED])
    called = {"infer": False}
    monkeypatch.setattr(rr, "detect_relationships",
                        lambda _id: called.__setitem__("infer", True) or [])
    res = rr.resolve_and_store_relationships(1, db_path="/tmp/x.db")
    assert called["infer"] is False
    assert res["status"] == "review"
    assert all(e["source"] == "pk_fk" for e in res["edges"])
    assert dbs.get_relationships_finalized(1) is False   # declared still needs approval


def test_large_no_declared_no_user_rejected(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, mode="large")
    monkeypatch.setattr(rr, "detect_relationships", lambda _id: [dict(e) for e in _INFERRED])
    res = rr.resolve_and_store_relationships(1, db_path="/tmp/x.db")
    assert res["rejected"] is True
    assert res["reason"] == "large_database_requires_relationships"
    assert dbs.get_relationships(1) == []   # nothing stored


def test_large_no_declared_with_user_ok(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, mode="large")
    dbs.add_user_relationship(1, "t1", "c1", "t2", "c2")
    monkeypatch.setattr(rr, "detect_relationships", lambda _id: [dict(e) for e in _INFERRED])
    res = rr.resolve_and_store_relationships(1, db_path="/tmp/x.db")
    assert res["rejected"] is False and res["status"] == "review"
    assert all(e["source"] == "user" for e in res["edges"])


def test_user_preserved_on_redetect(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, mode="small")
    dbs.add_user_relationship(1, "sales_orders", "sales_rep_id", "employees", "employee_id")
    monkeypatch.setattr(rr, "detect_relationships", lambda _id: [dict(e) for e in _INFERRED])
    res = rr.resolve_and_store_relationships(1, db_path="/tmp/x.db", force_inference=True)
    srcs = {e["source"] for e in res["edges"]}
    assert "user" in srcs and "inferred" in srcs
    assert res["status"] == "review"
