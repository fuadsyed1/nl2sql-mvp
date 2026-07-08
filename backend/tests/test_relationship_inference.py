"""
tests/test_relationship_inference.py

Relationship-inference rules on a retail-style schema:
  * self-references are detected (categories.parent_category_id ->
    categories.category_id, employees.manager_id -> employees.employee_id);
  * numeric measure columns (unit_price) never become relationships;
  * shared_identifier edges require ID/key-like columns on BOTH sides and are
    never fully confident (< 1.0, not auto-confirmed).

Builds a tiny sqlite database in tmp_path and monkeypatches
get_database_schema, so no app database is involved.

Run:  python -m pytest tests/test_relationship_inference.py -q
"""

import sqlite3

import schema.relationship_detector as rd


def _make_db(path):
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.execute("CREATE TABLE categories (category_id INTEGER, "
                "parent_category_id INTEGER, category_name TEXT)")
    cur.executemany("INSERT INTO categories VALUES (?,?,?)", [
        (1, None, "root"), (2, 1, "food"), (3, 1, "toys"), (4, 2, "dry food"),
    ])
    cur.execute("CREATE TABLE employees (employee_id INTEGER, "
                "manager_id INTEGER, employee_name TEXT)")
    cur.executemany("INSERT INTO employees VALUES (?,?,?)", [
        (1, None, "boss"), (2, 1, "ann"), (3, 1, "bob"), (4, 2, "cat"),
    ])
    cur.execute("CREATE TABLE products (product_id INTEGER, category_id INTEGER, "
                "unit_price REAL, product_name TEXT)")
    cur.executemany("INSERT INTO products VALUES (?,?,?,?)", [
        (1, 2, 9.5, "kibble"), (2, 3, 4.25, "ball"), (3, 4, 12.0, "premium"),
    ])
    cur.execute("CREATE TABLE order_items (order_item_id INTEGER, "
                "product_id INTEGER, unit_price REAL, quantity INTEGER)")
    cur.executemany("INSERT INTO order_items VALUES (?,?,?,?)", [
        (1, 1, 9.5, 2), (2, 2, 4.25, 1), (3, 3, 12.0, 4),
    ])
    con.commit()
    con.close()


def _schema(db_path):
    def col(name, dtype, pk=False, ordinal=0):
        return {"column_name": name, "data_type": dtype,
                "is_primary_key_candidate": pk, "ordinal": ordinal}
    return {
        "db_path": str(db_path),
        "tables": [
            {"table_name": "categories", "columns": [
                col("category_id", "INTEGER", True),
                col("parent_category_id", "INTEGER"),
                col("category_name", "TEXT", True)]},
            {"table_name": "employees", "columns": [
                col("employee_id", "INTEGER", True),
                col("manager_id", "INTEGER"),
                col("employee_name", "TEXT", True)]},
            {"table_name": "products", "columns": [
                col("product_id", "INTEGER", True),
                col("category_id", "INTEGER"),
                # unique in this data -> would be flagged a PK candidate
                col("unit_price", "REAL", True),
                col("product_name", "TEXT", True)]},
            {"table_name": "order_items", "columns": [
                col("order_item_id", "INTEGER", True),
                col("product_id", "INTEGER"),
                col("unit_price", "REAL", True),
                col("quantity", "INTEGER")]},
        ],
    }


def _detect(tmp_path, monkeypatch):
    db = tmp_path / "retail.db"
    _make_db(str(db))
    monkeypatch.setattr(rd, "get_database_schema", lambda _id: _schema(db))
    return rd.detect_relationships(1)


def _edge(edges, ft, fc, tt, tc):
    return next((e for e in edges if (e["from_table"], e["from_column"],
                                      e["to_table"], e["to_column"])
                 == (ft, fc, tt, tc)), None)


def test_parent_category_self_reference_detected(tmp_path, monkeypatch):
    edges = _detect(tmp_path, monkeypatch)
    e = _edge(edges, "categories", "parent_category_id",
              "categories", "category_id")
    assert e is not None
    assert e["relationship_type"] == "foreign_key"


def test_manager_self_reference_detected(tmp_path, monkeypatch):
    edges = _detect(tmp_path, monkeypatch)
    e = _edge(edges, "employees", "manager_id", "employees", "employee_id")
    assert e is not None
    assert e["relationship_type"] == "foreign_key"


def test_unit_price_shared_values_rejected(tmp_path, monkeypatch):
    edges = _detect(tmp_path, monkeypatch)
    assert _edge(edges, "order_items", "unit_price",
                 "products", "unit_price") is None
    assert _edge(edges, "products", "unit_price",
                 "order_items", "unit_price") is None


def test_measure_columns_never_relationship_endpoints(tmp_path, monkeypatch):
    edges = _detect(tmp_path, monkeypatch)
    for e in edges:
        assert e["from_column"] != "unit_price", e
        assert e["to_column"] != "unit_price", e
    # unit_price is treated as a measure, not a key
    assert rd._is_measure("unit_price")
    assert rd._is_measure("total_amount")
    assert rd._is_measure("risk_score")
    assert not rd._is_measure("product_id")


def test_real_fk_still_detected_and_shared_identifier_capped(tmp_path, monkeypatch):
    edges = _detect(tmp_path, monkeypatch)
    fk = _edge(edges, "order_items", "product_id", "products", "product_id")
    assert fk is not None and fk["relationship_type"] == "foreign_key"
    for e in edges:
        if e["relationship_type"] == "shared_identifier":
            assert e["confidence"] <= rd.SHARED_IDENTIFIER_CONFIDENCE_CAP
            assert e["confirmed"] == 0
