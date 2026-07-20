"""Schema-prefix normalizer: flatten confirmed `Schema.Table` -> `Table`
without mangling qualified column references."""

from sql_candidates.name_normalizer import normalize_schema_prefixes as N

_TABLES = ["Vendor", "PurchaseOrderHeader", "SalesOrderHeader", "Product"]


def test_from_join_prefix_flattened():
    sql = ("SELECT * FROM Vendor v JOIN Purchasing.PurchaseOrderHeader po "
           "ON v.BusinessEntityID = po.VendorID")
    out = N(sql, _TABLES)
    assert "Purchasing.PurchaseOrderHeader" not in out
    assert "JOIN PurchaseOrderHeader po" in out


def test_column_reference_not_touched():
    # alias.column where the column name coincides with a real table name must
    # NOT be rewritten (it is not in FROM/JOIN position).
    sql = "SELECT po.Product FROM PurchaseOrderHeader po"
    assert N(sql, _TABLES) == sql


def test_unknown_prefix_kept_when_flat_missing():
    sql = "SELECT * FROM Foo.Bar b"
    assert N(sql, _TABLES) == sql


def test_three_part_flattened():
    sql = "SELECT Sales.SalesOrderHeader.OrderDate FROM Sales.SalesOrderHeader"
    out = N(sql, _TABLES)
    assert "Sales.SalesOrderHeader" not in out
    assert "SalesOrderHeader.OrderDate" in out


def test_no_tables_is_noop():
    sql = "SELECT * FROM Purchasing.PurchaseOrderHeader"
    assert N(sql, []) == sql
