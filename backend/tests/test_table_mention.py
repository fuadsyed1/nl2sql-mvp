"""Explicit-table-mention detector: a bare business noun must not lock its
table; an explicit cue (or a distinctive/underscored name) must."""

from schema.table_mention import explicit_table_mentions as E

_NAMES = ["Customer", "Employee", "Department", "Vendor", "Product",
          "SalesOrderHeader", "census_tracts_new_york", "indiv20"]


def test_bare_common_noun_does_not_lock():
    assert E("orders higher than the average total due for the same customer",
             _NAMES) == set()
    assert E("employees assigned to a department but with no pay-rate change",
             _NAMES) == set()


def test_plural_noun_does_not_lock():
    assert E("find customers who bought products from three categories",
             _NAMES) == set()


def test_explicit_cue_locks_single_word():
    assert "Customer" in E("list rows from the Customer table", _NAMES)
    assert "Employee" in E("using Employee, count records", _NAMES)
    assert {"Employee", "Department"} <= E("from Employee join Department", _NAMES)
    assert "Customer" in E("select customer.customerid from data", _NAMES)


def test_distinctive_names_lock_without_cue():
    got = E("Using indiv20 and census_tracts_new_york, report values", _NAMES)
    assert {"indiv20", "census_tracts_new_york"} <= got


def test_separator_insensitive_distinctive():
    got = E("using census tracts new york", _NAMES)
    assert "census_tracts_new_york" in got


def test_never_raises_on_garbage():
    assert E(None, None) == set()
    assert E("x", []) == set()
