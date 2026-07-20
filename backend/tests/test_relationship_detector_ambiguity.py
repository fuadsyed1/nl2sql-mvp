"""
tests/test_relationship_detector_ambiguity.py

Dense-integer-key ambiguity (the DB52 failure mode):
  * a FK column with no name bridge (sales_rep_id) must NOT yield a confident
    mis-target when several PK ranges overlap equally -> it is dampened to a
    weak, flagged suggestion (or absent);
  * numeric non-key columns (reorder_point) are never FK sources;
  * a name-bridged FK (customer_id -> customers) is confident and undampened;
  * inference never grants authority: every edge is confirmed=0, source=inferred.
"""
import sqlite3
import schema.relationship_detector as rd


def _make_db(path):
    con = sqlite3.connect(path); cur = con.cursor()
    cur.execute("CREATE TABLE employees (employee_id INTEGER, department_id INTEGER)")
    cur.executemany("INSERT INTO employees VALUES (?,?)",
                    [(1, 1), (2, 1), (3, 2), (4, 2), (5, 3)])
    cur.execute("CREATE TABLE customers (customer_id INTEGER, city TEXT)")
    cur.executemany("INSERT INTO customers VALUES (?,?)",
                    [(1, "A"), (2, "B"), (3, "C")])
    cur.execute("CREATE TABLE sales_order_items (order_item_id INTEGER, order_id INTEGER)")
    cur.executemany("INSERT INTO sales_order_items VALUES (?,?)",
                    [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5)])
    cur.execute("CREATE TABLE sales_orders (order_id INTEGER, sales_rep_id INTEGER, "
                "customer_id INTEGER, reorder_point INTEGER)")
    cur.executemany("INSERT INTO sales_orders VALUES (?,?,?,?)", [
        (1, 1, 1, 1), (2, 2, 2, 2), (3, 3, 3, 3), (4, 1, 1, 4), (5, 2, 2, 5),
    ])
    con.commit(); con.close()


def _schema(db_path):
    def col(name, dtype, pk=False, ordinal=0):
        return {"column_name": name, "data_type": dtype,
                "is_primary_key_candidate": pk, "ordinal": ordinal}
    return {
        "db_path": str(db_path),
        "tables": [
            {"table_name": "employees", "columns": [
                col("employee_id", "INTEGER", True), col("department_id", "INTEGER")]},
            {"table_name": "customers", "columns": [
                col("customer_id", "INTEGER", True), col("city", "TEXT")]},
            {"table_name": "sales_order_items", "columns": [
                col("order_item_id", "INTEGER", True), col("order_id", "INTEGER")]},
            {"table_name": "sales_orders", "columns": [
                col("order_id", "INTEGER", True),
                col("sales_rep_id", "INTEGER"),
                col("customer_id", "INTEGER"),
                col("reorder_point", "INTEGER")]},
        ],
    }


def _detect(tmp_path, monkeypatch):
    db = tmp_path / "northstar.db"
    _make_db(str(db))
    monkeypatch.setattr(rd, "get_database_schema", lambda _id: _schema(db))
    return rd.detect_relationships(1)


def _edge(edges, ft, fc, tt, tc):
    return next((e for e in edges if (e["from_table"], e["from_column"],
                                      e["to_table"], e["to_column"])
                 == (ft, fc, tt, tc)), None)


def test_no_inferred_edge_grants_authority(tmp_path, monkeypatch):
    edges = _detect(tmp_path, monkeypatch)
    assert edges, "expected some inferred suggestions"
    for e in edges:
        assert e["confirmed"] == 0, e
        assert e["source"] == "inferred", e


def test_numeric_non_key_never_fk_source(tmp_path, monkeypatch):
    edges = _detect(tmp_path, monkeypatch)
    assert [e for e in edges if e["from_column"] == "reorder_point"] == []


def test_name_bridged_fk_is_confident(tmp_path, monkeypatch):
    edges = _detect(tmp_path, monkeypatch)
    cust = _edge(edges, "sales_orders", "customer_id", "customers", "customer_id")
    assert cust is not None
    assert cust["confidence"] > rd.AMBIGUOUS_CONFIDENCE_CAP
    assert not cust.get("ambiguous")


def test_ambiguous_no_bridge_fk_is_dampened_or_absent(tmp_path, monkeypatch):
    edges = _detect(tmp_path, monkeypatch)
    rep = [e for e in edges if e["from_column"] == "sales_rep_id"]
    for e in rep:
        assert e["confidence"] <= rd.AMBIGUOUS_CONFIDENCE_CAP, e
        assert e.get("ambiguous") is True, e
        assert e["confirmed"] == 0
