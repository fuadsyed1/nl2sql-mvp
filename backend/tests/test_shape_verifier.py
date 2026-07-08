"""
tests/test_shape_verifier.py

SQL semantic-shape verifier contract:
  * FATAL: unresolved predicate identifiers, self-comparisons (direct or via
    duplicate aliases) — with legitimate twins that must NOT fire;
  * ACTIVE penalties: weak universal COUNT logic, fake distinct alias,
    incomplete pair query — each with a clean counterpart;
  * P3/P5 are report-only: recorded, zero score effect.
"""

from sql_candidates.shape_verifier import verify_shape

IDX = {"tables": {
    "owners": [
        {"name": "owner_id", "type": "INTEGER", "samples": [], "is_date": False,
         "is_numeric": True, "is_key": True},
        {"name": "city", "type": "TEXT", "samples": [], "is_date": False,
         "is_numeric": False, "is_key": False},
    ],
    "foods": [
        {"name": "food_id", "type": "INTEGER", "samples": [], "is_date": False,
         "is_numeric": True, "is_key": True},
        {"name": "brand", "type": "TEXT", "samples": [], "is_date": False,
         "is_numeric": False, "is_key": False},
        {"name": "price", "type": "REAL", "samples": [], "is_date": False,
         "is_numeric": True, "is_key": False},
    ],
    "purchases": [
        {"name": "purchase_id", "type": "INTEGER", "samples": [], "is_date": False,
         "is_numeric": True, "is_key": True},
        {"name": "owner_id", "type": "INTEGER", "samples": [], "is_date": False,
         "is_numeric": True, "is_key": True},
        {"name": "food_id", "type": "INTEGER", "samples": [], "is_date": False,
         "is_numeric": True, "is_key": True},
        {"name": "purchase_date", "type": "TEXT", "samples": [], "is_date": True,
         "is_numeric": False, "is_key": False},
    ],
}}


def _run(question, sql):
    return verify_shape(question, sql, IDX)


# ---------------------------------------------------------------- F1 fatal
def test_unresolved_having_alias_is_fatal():
    delta, reasons, fatal, checks = _run(
        "Which foods cost more than 100?",
        "SELECT brand FROM foods GROUP BY brand HAVING product_price > 100")
    assert any("product_price" in f for f in fatal)


def test_unresolved_where_placeholder_is_fatal():
    _, _, fatal, _ = _run(
        "List foods", "SELECT brand FROM foods WHERE catalog_price > 5")
    assert any("catalog_price" in f for f in fatal)


def test_defined_alias_is_not_fatal():
    _, _, fatal, _ = _run(
        "Count foods per brand",
        "SELECT brand, COUNT(food_id) AS n FROM foods GROUP BY brand HAVING n > 2")
    assert not fatal


def test_cte_column_is_not_fatal():
    _, _, fatal, _ = _run(
        "Totals per owner",
        "WITH t (oid, total) AS (SELECT owner_id, COUNT(*) FROM purchases "
        "GROUP BY owner_id) SELECT oid FROM t WHERE total > 3")
    assert not fatal


# ---------------------------------------------------------------- F2 fatal
def test_direct_self_comparison_is_fatal():
    _, _, fatal, _ = _run(
        "List foods", "SELECT brand FROM foods WHERE price = price")
    assert any("self-comparison" in f for f in fatal)


def test_count_star_equals_count_star_is_fatal():
    _, _, fatal, _ = _run(
        "Owners who bought every food",
        "SELECT owner_id FROM purchases GROUP BY owner_id "
        "HAVING COUNT(*) = COUNT(*)")
    assert any("self-comparison" in f for f in fatal)


def test_duplicate_alias_comparison_is_fatal():
    _, _, fatal, _ = _run(
        "Owners who bought every food",
        "SELECT owner_id, COUNT(food_id) AS a, COUNT(food_id) AS b "
        "FROM purchases GROUP BY owner_id HAVING a = b")
    assert any("same expression" in f for f in fatal)


def test_count_vs_count_distinct_is_not_fatal():
    _, _, fatal, _ = _run(
        "Owners who bought every food",
        "SELECT owner_id FROM purchases GROUP BY owner_id "
        "HAVING COUNT(food_id) = COUNT(DISTINCT food_id)")
    assert not fatal


# ---------------------------------------------------------------- P1
def test_weak_universal_count_penalized():
    delta, reasons, fatal, checks = _run(
        "Find owners who bought all brands",
        "SELECT owner_id FROM purchases JOIN foods ON foods.food_id = "
        "purchases.food_id GROUP BY owner_id "
        "HAVING COUNT(brand) = COUNT(food_id)")
    assert any(p["code"] == "P1" for p in checks["penalties"])
    assert delta <= -15


def test_universal_with_subquery_universe_not_penalized():
    delta, _, _, checks = _run(
        "Find owners who bought all brands",
        "SELECT owner_id FROM purchases JOIN foods ON foods.food_id = "
        "purchases.food_id GROUP BY owner_id "
        "HAVING COUNT(DISTINCT brand) = (SELECT COUNT(DISTINCT brand) FROM foods)")
    assert not any(p["code"] == "P1" for p in checks["penalties"])


# ---------------------------------------------------------------- P2
def test_fake_distinct_alias_penalized():
    delta, _, _, checks = _run(
        "How many distinct brands per owner?",
        "SELECT owner_id, COUNT(brand) AS distinct_brands FROM purchases "
        "JOIN foods ON foods.food_id = purchases.food_id GROUP BY owner_id")
    assert any(p["code"] == "P2" for p in checks["penalties"])


def test_real_distinct_alias_not_penalized():
    _, _, _, checks = _run(
        "How many distinct brands per owner?",
        "SELECT owner_id, COUNT(DISTINCT brand) AS distinct_brands "
        "FROM purchases JOIN foods ON foods.food_id = purchases.food_id "
        "GROUP BY owner_id")
    assert not any(p["code"] == "P2" for p in checks["penalties"])


# ---------------------------------------------------------------- P4
def test_pair_without_inequality_penalized():
    _, _, _, checks = _run(
        "List pairs of owners in the same city",
        "SELECT a.owner_id, b.owner_id FROM owners a "
        "JOIN owners b ON a.city = b.city")
    assert any(p["code"] == "P4" for p in checks["penalties"])


def test_pair_with_inequality_not_penalized():
    _, _, _, checks = _run(
        "List pairs of owners in the same city",
        "SELECT a.owner_id, b.owner_id FROM owners a "
        "JOIN owners b ON a.city = b.city AND a.owner_id < b.owner_id")
    assert not any(p["code"] == "P4" for p in checks["penalties"])


# ---------------------------------------------------------------- P3/P5
def test_report_only_checks_do_not_change_score():
    delta, reasons, fatal, checks = _run(
        "Find the latest purchase per owner",
        "SELECT * FROM (SELECT owner_id, ROW_NUMBER() OVER "
        "(PARTITION BY price ORDER BY purchase_date DESC) rn "
        "FROM purchases JOIN foods ON foods.food_id = purchases.food_id) "
        "WHERE rn = 1")
    assert any(r["code"] == "P3" for r in checks["report_only"])
    assert delta == 0.0 and not fatal


def test_clean_sql_untouched():
    delta, reasons, fatal, checks = _run(
        "List owners in Moscow",
        "SELECT owner_id, city FROM owners WHERE city = 'Moscow'")
    assert delta == 0.0 and not fatal and not checks["penalties"]
