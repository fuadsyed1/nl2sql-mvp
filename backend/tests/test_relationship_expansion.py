"""Relationship-aware retrieval closure + physical-FK graph augmentation."""

import sqlite3

from retrieval.relationship_expansion import (
    physical_fk_edges, expand_tables_along_fks, augment_graph_with_physical_fks,
)


def _db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE Customer(CustomerID INTEGER PRIMARY KEY);"
        "CREATE TABLE Product(ProductID INTEGER PRIMARY KEY, "
        " ProductSubcategoryID INTEGER REFERENCES ProductSubcategory(ProductSubcategoryID));"
        "CREATE TABLE ProductSubcategory(ProductSubcategoryID INTEGER PRIMARY KEY, "
        " ProductCategoryID INTEGER REFERENCES ProductCategory(ProductCategoryID));"
        "CREATE TABLE ProductCategory(ProductCategoryID INTEGER PRIMARY KEY);"
        "CREATE TABLE SalesOrderHeader(SalesOrderID INTEGER PRIMARY KEY, "
        " CustomerID INTEGER REFERENCES Customer(CustomerID));"
        "CREATE TABLE SalesOrderDetail(SalesOrderDetailID INTEGER PRIMARY KEY, "
        " SalesOrderID INTEGER REFERENCES SalesOrderHeader(SalesOrderID), "
        " ProductID INTEGER REFERENCES Product(ProductID));"
        "CREATE TABLE Vendor(BusinessEntityID INTEGER PRIMARY KEY);"
        "CREATE TABLE PurchaseOrderHeader(PurchaseOrderID INTEGER PRIMARY KEY, "
        " VendorID INTEGER REFERENCES Vendor(BusinessEntityID), TotalDue REAL);"
    )
    conn.commit()
    conn.close()


_ALL = ["Customer", "Product", "ProductSubcategory", "ProductCategory",
        "SalesOrderHeader", "SalesOrderDetail", "Vendor", "PurchaseOrderHeader"]


def test_physical_fk_edges(tmp_path):
    p = str(tmp_path / "t.db")
    _db(p)
    pairs = {(e["from_table"], e["to_table"]) for e in physical_fk_edges(p)}
    assert ("SalesOrderHeader", "Customer") in pairs
    assert ("PurchaseOrderHeader", "Vendor") in pairs


def test_expansion_pulls_bridge_and_category(tmp_path):
    p = str(tmp_path / "t.db")
    _db(p)
    edges = physical_fk_edges(p)
    exp = [t.lower() for t in expand_tables_along_fks(
        ["Customer", "Product"], edges, _ALL,
        "customers who bought products from three different categories")]
    # bridge path between the two seeds
    assert "salesorderheader" in exp and "salesorderdetail" in exp
    # the lexically-relevant category table + its connector
    assert "productcategory" in exp and "productsubcategory" in exp


def test_expansion_single_seed_measure(tmp_path):
    p = str(tmp_path / "t.db")
    _db(p)
    edges = physical_fk_edges(p)
    exp = [t.lower() for t in expand_tables_along_fks(
        ["Vendor"], edges, _ALL,
        "running total of purchase order spending per vendor")]
    assert "purchaseorderheader" in exp


def test_augment_graph_adds_physical_fk_edges(tmp_path):
    p = str(tmp_path / "t.db")
    _db(p)
    graph = {"tables": [{"table_name": "Customer", "columns": []},
                        {"table_name": "SalesOrderHeader", "columns": []}],
             "relationships": []}
    out = augment_graph_with_physical_fks(graph, p)
    assert any(r["from_table"] == "SalesOrderHeader" and r["to_table"] == "Customer"
               for r in out["relationships"])
    # source graph untouched
    assert graph["relationships"] == []


def test_augment_non_fk_db_is_noop(tmp_path):
    p = str(tmp_path / "e.db")
    conn = sqlite3.connect(p)
    conn.executescript("CREATE TABLE a(x INTEGER); CREATE TABLE b(y INTEGER);")
    conn.commit()
    conn.close()
    g = {"tables": [{"table_name": "a", "columns": []}], "relationships": []}
    assert augment_graph_with_physical_fks(g, p) is g
