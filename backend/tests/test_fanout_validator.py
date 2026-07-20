"""Stage 2 — cardinality-aware fanout validator tests.

Generic header/detail and hub-with-two-children schemas; relationships are
child(from) -> parent(to), matching the repository's graph format. Fatal only
on provable inflation; unknown cardinality stays nonfatal.
"""

from validators.fanout_validator import validate_fanout

IDX = {
    "tables": {
        "headers": [{"name": "header_id"}, {"name": "amount"}],
        "details": [{"name": "detail_id"}, {"name": "header_id"},
                    {"name": "qty"}],
        "shops": [{"name": "shop_id"}, {"name": "city"}],
        "sales": [{"name": "sale_id"}, {"name": "shop_id"},
                  {"name": "amount"}, {"name": "fee"}],
        "visits": [{"name": "visit_id"}, {"name": "shop_id"},
                   {"name": "cost"}],
        "shop_details": [{"name": "shop_id"}, {"name": "opened"}],
    },
    "relationships": [
        {"from_table": "details", "from_column": "header_id",
         "to_table": "headers", "to_column": "header_id"},
        {"from_table": "sales", "from_column": "shop_id",
         "to_table": "shops", "to_column": "shop_id"},
        {"from_table": "visits", "from_column": "shop_id",
         "to_table": "shops", "to_column": "shop_id"},
    ],
}


# 1. header amount summed after joining details is inflation --------------------
def test_header_detail_inflation_fatal():
    sql = ("SELECT h.header_id, SUM(h.amount) FROM headers h "
           "JOIN details d ON d.header_id = h.header_id "
           "GROUP BY h.header_id")
    v = validate_fanout(sql, IDX)
    assert any("fanout violation" in f for f in v.fatal), v


# 2. one child's measure inflated by a sibling child ----------------------------
def test_sibling_child_inflation_fatal():
    sql = ("SELECT s.shop_id, SUM(s.amount) FROM shops sh "
           "JOIN sales s ON s.shop_id = sh.shop_id "
           "JOIN visits v ON v.shop_id = sh.shop_id "
           "GROUP BY s.shop_id")
    v = validate_fanout(sql, IDX)
    assert any("visits" in f for f in v.fatal), v


# 3. pairwise independent counts multiplied by each other ------------------------
def test_pairwise_counts_fatal():
    sql = ("SELECT sh.shop_id, COUNT(s.sale_id) AS n_sales, "
           "COUNT(v.visit_id) AS n_visits FROM shops sh "
           "JOIN sales s ON s.shop_id = sh.shop_id "
           "JOIN visits v ON v.shop_id = sh.shop_id "
           "GROUP BY sh.shop_id")
    v = validate_fanout(sql, IDX)
    assert len(v.fatal) >= 2, v          # both counts are inflated


# 4. pairwise independent sums multiplied by each other --------------------------
def test_pairwise_sums_fatal():
    sql = ("SELECT sh.shop_id, SUM(s.amount), SUM(v.cost) FROM shops sh "
           "JOIN sales s ON s.shop_id = sh.shop_id "
           "JOIN visits v ON v.shop_id = sh.shop_id "
           "GROUP BY sh.shop_id")
    v = validate_fanout(sql, IDX)
    assert len(v.fatal) >= 2, v


# 5. pre-aggregated CTEs joined afterwards are safe ------------------------------
def test_preaggregated_ctes_safe():
    sql = ("WITH s AS (SELECT shop_id, SUM(amount) AS total FROM sales "
           "GROUP BY shop_id), "
           "v AS (SELECT shop_id, COUNT(visit_id) AS visits FROM visits "
           "GROUP BY shop_id) "
           "SELECT sh.shop_id, s.total, v.visits FROM shops sh "
           "JOIN s ON s.shop_id = sh.shop_id "
           "JOIN v ON v.shop_id = sh.shop_id")
    v = validate_fanout(sql, IDX)
    assert v.fatal == [], v


# 6. EXISTS-based qualification is safe ------------------------------------------
def test_exists_qualification_safe():
    sql = ("SELECT s.shop_id, SUM(s.amount) FROM sales s "
           "WHERE EXISTS (SELECT 1 FROM visits v "
           "WHERE v.shop_id = s.shop_id) GROUP BY s.shop_id")
    v = validate_fanout(sql, IDX)
    assert v.fatal == [], v


# 7. COUNT(DISTINCT entity key) is safe -------------------------------------------
def test_count_distinct_safe():
    sql = ("SELECT sh.shop_id, COUNT(DISTINCT s.sale_id) FROM shops sh "
           "JOIN sales s ON s.shop_id = sh.shop_id "
           "JOIN visits v ON v.shop_id = sh.shop_id "
           "GROUP BY sh.shop_id")
    v = validate_fanout(sql, IDX)
    assert v.fatal == [], v


# 8. a one-to-one join does not multiply the measure -------------------------------
def test_one_to_one_join_safe():
    # shops<->shop_details has NO child->parent relationship entry, so no
    # provable many side exists on that edge
    sql = ("SELECT sh.shop_id, SUM(s.amount) FROM shops sh "
           "JOIN shop_details sd ON sd.shop_id = sh.shop_id "
           "JOIN sales s ON s.shop_id = sh.shop_id "
           "GROUP BY sh.shop_id")
    v = validate_fanout(sql, IDX)
    assert v.fatal == [], v


# 9. unknown cardinality stays nonfatal --------------------------------------------
def test_unknown_cardinality_nonfatal():
    no_rels = {"tables": IDX["tables"], "relationships": []}
    sql = ("SELECT h.header_id, SUM(h.amount) FROM headers h "
           "JOIN details d ON d.header_id = h.header_id "
           "GROUP BY h.header_id")
    v = validate_fanout(sql, no_rels)
    assert v.fatal == [] and v.skipped is not None
    v = validate_fanout(sql, None)
    assert v.fatal == []


# 10. compound derived measures are traced through arithmetic ----------------------
def test_compound_derived_measure_fatal():
    sql = ("SELECT s.shop_id, SUM(s.amount - s.fee) FROM sales s "
           "JOIN shops sh ON s.shop_id = sh.shop_id "
           "JOIN visits v ON v.shop_id = sh.shop_id "
           "GROUP BY s.shop_id")
    v = validate_fanout(sql, IDX)
    assert any("fanout violation" in f for f in v.fatal), v


# the measure's own many side is never an inflator ----------------------------------
def test_aggregating_the_many_side_is_safe():
    sql = ("SELECT h.header_id, SUM(d.qty) FROM headers h "
           "JOIN details d ON d.header_id = h.header_id "
           "GROUP BY h.header_id")
    v = validate_fanout(sql, IDX)
    assert v.fatal == [], v
