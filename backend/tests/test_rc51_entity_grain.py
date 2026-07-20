"""
RC5.1 - output-grain / duplicate-set selection tests.

When the request asks for one row per entity (checklist group_by_entity names
the entity key), a candidate that GUARANTEES entity-level uniqueness (GROUP BY
the entity key, SELECT DISTINCT, or no many-side join) must semantically
dominate an otherwise-equivalent duplicate-prone candidate that joins a
one-to-many path without a uniqueness guarantee. DISTINCT is never required
globally - the obligation only fires when an entity grain is requested.
"""
from sql_candidates.rc5_ranking import rc5_obligations, rc5_dominates, RC5_ORDER
from sql_candidates.candidate_types import SqlCandidate
from sql_candidates.candidate_selector import select_best

IDX = {"tables": {
    "products": [{"name": "product_id", "is_key": True},
                 {"name": "product_name", "is_key": False},
                 {"name": "supplier_id", "is_key": True}],
    "sales_order_items": [{"name": "order_item_id", "is_key": True},
                          {"name": "order_id", "is_key": True},
                          {"name": "product_id", "is_key": True}],
    "sales_orders": [{"name": "order_id", "is_key": True},
                     {"name": "customer_id", "is_key": True}],
    "customers": [{"name": "customer_id", "is_key": True},
                  {"name": "loyalty_tier", "is_key": False}],
}}

ENTITY_CK = {"required_sql_shape": "comparison_subquery",
             "group_by_entity": "products.product_id",
             "required_group_keys": ["products.product_id"],
             "row_grain": "one row per product"}

GROUPED = ("SELECT p.product_id, p.product_name FROM products p "
           "JOIN sales_order_items soi ON p.product_id = soi.product_id "
           "GROUP BY p.product_id, p.product_name")
DUP = ("SELECT p.product_id, p.product_name FROM products p "
       "JOIN sales_order_items soi ON p.product_id = soi.product_id")
DISTINCT = ("SELECT DISTINCT p.product_id, p.product_name FROM products p "
            "JOIN sales_order_items soi ON p.product_id = soi.product_id")


def _ob(sql, ck, question="list products", score=0.0):
    return rc5_obligations(sql, ck, None, IDX, question, {"_numeric_score": score})


# 1
def test_entity_grouped_beats_duplicate_prone_many_side_join():
    good, ap = _ob(GROUPED, ENTITY_CK)
    bad, _ = _ob(DUP, ENTITY_CK)
    assert good["entity_grain_unique"] and not bad["entity_grain_unique"]
    dom, why, _ = rc5_dominates(good, bad, ap)
    assert dom and "entity_grain_unique" in why


# 2
def test_distinct_entity_list_beats_duplicate_prone_list():
    good, ap = _ob(DISTINCT, ENTITY_CK)
    bad, _ = _ob(DUP, ENTITY_CK)
    assert good["entity_grain_unique"] and not bad["entity_grain_unique"]
    assert rc5_dominates(good, bad, ap)[0]


# 3 - obligation does NOT apply without a requested entity grain
def test_no_distinct_preference_when_duplicates_requested():
    ck = {"required_sql_shape": "plain_select"}  # no group_by_entity
    _o, ap = _ob(DUP, ck)
    assert ap["entity_grain_unique"] is False


# 4 - detail-grain query keeps legitimate repeated rows (per-item grain)
def test_detail_query_preserves_repeated_rows():
    ck = {"required_sql_shape": "plain_select",
          "group_by_entity": "sales_order_items.order_item_id",
          "row_grain": "one row per order item"}
    detail = ("SELECT soi.order_item_id, p.product_name FROM sales_order_items soi "
              "JOIN products p ON soi.product_id = p.product_id")
    o, ap = _ob(detail, ck)
    # order_item_id is the grain and there is no many-side child of it -> guaranteed,
    # so no false demotion of a legitimate detail query.
    assert o["entity_grain_unique"] is True


# 5 - existing compound-set handling unaffected
def test_compound_set_still_works():
    ck = {"required_sql_shape": "comparison_subquery",
          "required_literal_groups": [{"column": "customers.loyalty_tier",
                                       "literals": ["gold", "platinum", "bronze"]}]}
    full, ap = _ob("SELECT product_id FROM products WHERE product_id IN "
                   "(SELECT product_id FROM t WHERE loyalty_tier = 'Gold' "
                   "INTERSECT SELECT product_id FROM t WHERE loyalty_tier = 'Platinum') "
                   "AND product_id NOT IN (SELECT product_id FROM t2 WHERE loyalty_tier = 'Bronze')", ck)
    partial, _ = _ob("SELECT product_id FROM products WHERE NOT EXISTS "
                     "(SELECT 1 FROM t WHERE loyalty_tier = 'Bronze')", ck)
    assert rc5_dominates(full, partial, ap)[0]


def _c(label, source, score, rows, sql):
    c = SqlCandidate(source=source, label=label, sql=sql,
                     execution={"executed": True, "columns": ["product_id", "product_name"],
                                "rows": rows, "row_count": len(rows)})
    c.score = score
    return c


# full compound-set + entity grain for 437-style integration
_SET = ("SELECT p.product_id, p.product_name FROM products p "
        "JOIN sales_order_items soi ON p.product_id = soi.product_id "
        "JOIN sales_orders so ON soi.order_id = so.order_id "
        "JOIN customers c ON so.customer_id = c.customer_id "
        "WHERE p.product_id IN (SELECT product_id FROM sales_order_items i2 "
        "JOIN sales_orders o2 ON i2.order_id = o2.order_id "
        "JOIN customers c2 ON o2.customer_id = c2.customer_id WHERE c2.loyalty_tier = 'Gold' "
        "INTERSECT SELECT product_id FROM sales_order_items i3 "
        "JOIN sales_orders o3 ON i3.order_id = o3.order_id "
        "JOIN customers c3 ON o3.customer_id = c3.customer_id WHERE c3.loyalty_tier = 'Platinum') "
        "AND p.product_id NOT IN (SELECT product_id FROM sales_order_items i4 "
        "JOIN sales_orders o4 ON i4.order_id = o4.order_id "
        "JOIN customers c4 ON o4.customer_id = c4.customer_id WHERE c4.loyalty_tier = 'Bronze')")
_SET_GROUPED = _SET + " GROUP BY p.product_id, p.product_name"

CK437 = {"required_sql_shape": "comparison_subquery",
         "group_by_entity": "products.product_id",
         "required_group_keys": ["products.product_id"],
         "row_grain": "one row per product",
         "required_literal_groups": [{"column": "customers.loyalty_tier",
                                      "literals": ["gold", "platinum", "bronze"]}]}


# 6 - an RC4-blocked candidate cannot be returned by RC5.1
def test_rc4_blocked_candidate_not_returned():
    ck = {"required_sql_shape": "group_by_having"}
    a1 = _c("llm_sql_direct", "llm_sql_direct", 70, [["x", "m"]],
            "SELECT cat, SUM(a - b) AS m FROM t GROUP BY cat")
    a2 = _c("llm_sql_direct_grain", "llm_sql_direct_grain", 70, [["x", "m"]],
            "SELECT cat, SUM(a - b) AS m FROM t GROUP BY cat")
    wrong = _c("llm_sql_repair", "llm_sql_repair", 100, [["y", "n"]],
               "SELECT cat, SUM(a) AS m FROM t GROUP BY cat")
    sel, meta = select_best([a1, a2, wrong], checklist=ck, idx=IDX, question="show")
    assert sel.label != "llm_sql_repair"


# 7 - 437-style: grouped/unique candidate selected over duplicate-prone ones
def test_437_selects_entity_unique_candidate():
    direct = _c("llm_sql_direct", "llm_sql_direct", 80, [[1, "A"], [2, "B"]], _SET_GROUPED)
    grain = _c("llm_sql_direct_grain", "llm_sql_direct_grain", 80,
               [[1, "A"], [1, "A"], [2, "B"]], _SET)          # duplicate rows
    variant = _c("llm_sql_direct_variant", "llm_sql_direct_variant", 80,
                 [[1, "A"], [1, "A"], [2, "B"]], _SET)        # duplicate rows
    sel, meta = select_best([grain, variant, direct], checklist=CK437, idx=IDX,
                            question="List products sold to both Gold and Platinum but not Bronze")
    assert sel.label == "llm_sql_direct"
    assert meta["selection_reason"] == "semantic_best_candidate"
    assert "entity_grain_unique" in (meta.get("rc5_trace") or {}).get("obligations_gained", [])


# 8 - the selected candidate returns one row per product (unique entity grain)
def test_437_selected_returns_one_row_per_product():
    direct = _c("llm_sql_direct", "llm_sql_direct", 80, [[1, "A"], [2, "B"]], _SET_GROUPED)
    grain = _c("llm_sql_direct_grain", "llm_sql_direct_grain", 80,
               [[1, "A"], [1, "A"], [2, "B"]], _SET)
    sel, meta = select_best([grain, direct], checklist=CK437, idx=IDX,
                            question="List products sold to both Gold and Platinum but not Bronze")
    ids = [r[0] for r in sel.execution["rows"]]
    assert len(ids) == len(set(ids))   # one row per product
    assert sel.label == "llm_sql_direct"
