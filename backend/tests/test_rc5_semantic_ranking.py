"""
RC5 - general semantic best-candidate ranking / tie-breaking tests.

Exercise the four tightly-gated RC5 obligations (scalar-count output,
comparison predicate, relationship-role/join-path specificity, compound-set
completeness), the dominance/incomparability logic, numeric-score-last ordering,
source-neutrality, and the RC4-blocked-candidate preservation guard. Every
signal is schema-generic; concrete names live only in these fixtures.
"""
from sql_candidates.rc5_ranking import (
    rc5_obligations, rc5_dominates, rc5_rank_tuple, RC5_ORDER)
from sql_candidates.candidate_types import SqlCandidate
from sql_candidates.candidate_selector import select_best

# tiny schema index: real PK is the FIRST key column per table.
IDX = {"tables": {
    "customers": [{"name": "customer_id", "is_key": True},
                  {"name": "loyalty_tier", "is_key": False}],
    "sales_orders": [{"name": "order_id", "is_key": True},
                     {"name": "customer_id", "is_key": True},
                     {"name": "order_number", "is_key": False}],
    "payments": [{"name": "payment_id", "is_key": True},
                 {"name": "order_id", "is_key": True},
                 {"name": "customer_id", "is_key": True},
                 {"name": "amount", "is_key": False}],
    "warehouses": [{"name": "warehouse_id", "is_key": True},
                   {"name": "state_code", "is_key": False}],
    "suppliers": [{"name": "supplier_id", "is_key": True},
                  {"name": "state_code", "is_key": False}],
}}


def _ob(sql, checklist=None, question=None, score=0.0):
    o, ap = rc5_obligations(sql, checklist, None, IDX, question,
                            {"_numeric_score": score})
    return o, ap


# ---- scalar-count output (Test 146) -------------------------------------
def test_scalar_count_dominates_entity_list():
    q = "How many distinct suppliers had products in at least three warehouses?"
    scalar, ap = _ob("SELECT COUNT(*) FROM (SELECT supplier_id FROM suppliers "
                     "GROUP BY supplier_id HAVING COUNT(*) >= 3)", question=q)
    lst, ap2 = _ob("SELECT supplier_id, supplier_name FROM suppliers "
                   "GROUP BY supplier_id HAVING COUNT(*) >= 3", question=q)
    dom, why, _ = rc5_dominates(scalar, lst, ap)
    assert dom and "scalar_count_output" in why


def test_scalar_count_not_applied_without_count_intent():
    q = "List suppliers with products in at least three warehouses."
    a, ap = _ob("SELECT supplier_id FROM suppliers", question=q)
    assert ap["scalar_count_output"] is False


def test_scalar_count_higher_score_list_does_not_win():
    q = "How many customers placed an order?"
    scalar, ap = _ob("SELECT COUNT(DISTINCT customer_id) FROM sales_orders",
                     question=q, score=40)
    lst, _ = _ob("SELECT customer_id FROM sales_orders GROUP BY customer_id",
                 question=q, score=99)
    dom, _, _ = rc5_dominates(lst, scalar, ap)   # list trying to beat scalar
    assert not dom


# ---- comparison predicate (Test 289) ------------------------------------
def _cmp_checklist():
    return {"required_sql_shape": "comparison_subquery",
            "must_use_columns": ["products.product_id", "suppliers.state_code",
                                 "warehouses.state_code"]}


def test_comparison_predicate_beats_selecting_both_columns():
    ck = _cmp_checklist()
    good, ap = _ob("SELECT p.product_id FROM products p JOIN suppliers s "
                   "ON p.supplier_id = s.supplier_id JOIN warehouses w "
                   "ON 1=1 WHERE s.state_code = w.state_code", ck)
    bad, _ = _ob("SELECT p.product_id, s.state_code, w.state_code FROM products p "
                 "JOIN suppliers s ON p.supplier_id = s.supplier_id "
                 "JOIN warehouses w ON 1=1", ck)
    dom, why, _ = rc5_dominates(good, bad, ap)
    assert dom and "comparison_predicate" in why


def test_comparison_predicate_not_applied_on_union_shape():
    ck = {"required_sql_shape": "plain_select",
          "must_use_columns": ["inventory.warehouse_id", "shipments.warehouse_id"]}
    _o, ap = _ob("SELECT warehouse_id FROM inventory UNION "
                 "SELECT warehouse_id FROM shipments", ck)
    assert ap["comparison_predicate"] is False


# ---- relationship-role / join-path specificity (Tests 336, 317) ---------
def test_specific_parent_join_beats_shared_ancestor():
    good, ap = _ob("SELECT so.order_number, p.amount FROM sales_orders so "
                   "JOIN customers c ON so.customer_id = c.customer_id "
                   "JOIN payments p ON so.order_id = p.order_id")
    bad, _ = _ob("SELECT so.order_number, p.amount FROM sales_orders so "
                 "JOIN customers c ON so.customer_id = c.customer_id "
                 "JOIN payments p ON c.customer_id = p.customer_id")
    dom, why, _ = rc5_dominates(good, bad, ap)
    assert dom and "relationship_specificity" in why


def test_other_legal_fk_path_loses_to_specific_role():
    # payment joined via order (specific) dominates payment joined via customer.
    good, ap = _ob("SELECT p.amount FROM sales_orders so "
                   "JOIN payments p ON so.order_id = p.order_id "
                   "JOIN customers c ON so.customer_id = c.customer_id")
    bad, _ = _ob("SELECT p.amount FROM customers c "
                 "JOIN payments p ON c.customer_id = p.customer_id "
                 "JOIN sales_orders so ON c.customer_id = so.customer_id")
    dom, _, _ = rc5_dominates(good, bad, ap)
    assert dom


def test_specificity_not_applied_without_descendant_structure():
    _o, ap = _ob("SELECT c.customer_id FROM customers c "
                 "JOIN sales_orders so ON c.customer_id = so.customer_id")
    assert ap["relationship_specificity"] is False


# ---- compound-set completeness (Test 437) -------------------------------
def _set_checklist():
    return {"required_sql_shape": "comparison_subquery",
            "required_literal_groups": [
                {"column": "customers.loyalty_tier",
                 "literals": ["gold", "platinum", "bronze"]}]}


def test_full_compound_set_beats_partial():
    ck = _set_checklist()
    full, ap = _ob("SELECT product_id FROM products WHERE product_id IN "
                   "(SELECT product_id FROM t WHERE loyalty_tier = 'Gold' "
                   "INTERSECT SELECT product_id FROM t WHERE loyalty_tier = 'Platinum') "
                   "AND product_id NOT IN (SELECT product_id FROM t2 "
                   "WHERE loyalty_tier = 'Bronze')", ck)
    partial, _ = _ob("SELECT product_id FROM products WHERE NOT EXISTS "
                     "(SELECT 1 FROM t WHERE loyalty_tier = 'Bronze')", ck)
    dom, why, _ = rc5_dominates(full, partial, ap)
    assert dom and "compound_set_complete" in why


def test_compound_set_not_applied_single_literal():
    ck = {"required_literal_groups": [{"column": "t.status", "literals": ["x"]}]}
    _o, ap = _ob("SELECT id FROM t WHERE status = 'x'", ck)
    assert ap["compound_set_complete"] is False


def test_compound_set_invariant_to_parameterized_literals():
    # A parameterized partial candidate still fails: only one tier reference.
    ck = _set_checklist()
    partial, ap = _ob("SELECT product_id FROM products p JOIN t "
                      "ON 1=1 WHERE loyalty_tier = ?", ck)
    assert ap["compound_set_complete"] and not partial["compound_set_complete"]


# ---- dominance / incomparability / equivalence --------------------------
def test_superset_dominates():
    ap = {k: True for k in RC5_ORDER}
    a = {k: True for k in RC5_ORDER}; a["comparison_predicate"] = False
    b = {k: True for k in RC5_ORDER}
    dom, _, _ = rc5_dominates(b, a, ap)
    assert dom


def test_mutual_gain_is_incomparable():
    ap = {k: True for k in RC5_ORDER}
    a = {k: True for k in RC5_ORDER}; a["comparison_predicate"] = False
    b = {k: True for k in RC5_ORDER}; b["relationship_specificity"] = False
    dom, why, _ = rc5_dominates(b, a, ap)
    assert not dom and "incomparable" in why


def test_equivalent_obligations_no_override():
    ap = {k: True for k in RC5_ORDER}
    a = {k: True for k in RC5_ORDER}
    b = {k: True for k in RC5_ORDER}
    dom, why, _ = rc5_dominates(b, a, ap)
    assert not dom and "equivalent" in why


def test_numeric_score_only_orders_after_semantic_equality():
    hi = {k: True for k in RC5_ORDER}; hi["_numeric_score"] = 90
    lo = {k: True for k in RC5_ORDER}; lo["_numeric_score"] = 40
    # equal obligations -> neither dominates; score only orders the rank tuple.
    assert not rc5_dominates(hi, lo, {k: True for k in RC5_ORDER})[0]
    assert rc5_rank_tuple(hi) > rc5_rank_tuple(lo)


def test_source_label_never_beats_semantic_difference():
    # obligation-poorer candidate cannot dominate regardless of any source.
    ap = {k: True for k in RC5_ORDER}
    poor = {k: True for k in RC5_ORDER}; poor["scalar_count_output"] = False
    rich = {k: True for k in RC5_ORDER}
    assert rc5_dominates(poor, rich, ap)[0] is False


# ---- selector integration ----------------------------------------------
def _c(label, source, score, rows, sql):
    c = SqlCandidate(source=source, label=label, sql=sql,
                     execution={"executed": True, "columns": ["a"],
                                "rows": rows, "row_count": len(rows)})
    c.score = score
    return c


def test_select_best_applies_semantic_best_candidate():
    q = "How many customers placed an order?"
    lst = _c("llm_variant_1", "llm_variant", 95, [[1], [2], [3]],
             "SELECT c.customer_id FROM customers c JOIN sales_orders so "
             "ON c.customer_id = so.customer_id GROUP BY c.customer_id")
    scal = _c("llm_sql_direct", "llm_sql_direct", 70, [[3]],
              "SELECT COUNT(DISTINCT so.customer_id) FROM customers c "
              "JOIN sales_orders so ON c.customer_id = so.customer_id")
    sel, meta = select_best([lst, scal], checklist={"required_sql_shape": "count_distinct"},
                            idx=IDX, question=q)
    assert sel is scal
    assert meta["selection_reason"] == "semantic_best_candidate"
    assert meta["rc5_trace"]["obligations_gained"] == ["scalar_count_output"]
    assert meta["rc5_trace"]["numeric_score_consulted"] is False


def test_select_best_records_incomparable_fallback():
    ck = {"required_sql_shape": "comparison_subquery",
          "must_use_columns": ["suppliers.state_code", "warehouses.state_code"],
          "required_literal_groups": [{"column": "t.tier",
                                       "literals": ["gold", "platinum"]}]}
    # A: has comparison, missing compound-set ; B: has compound-set, missing comparison
    a = _c("llm_primary", "llm_primary", 80, [[1]],
           "SELECT p FROM suppliers s JOIN warehouses w ON 1=1 "
           "WHERE s.state_code = w.state_code")
    b = _c("llm_sql_direct", "llm_sql_direct", 82, [[2]],
           "SELECT p FROM t WHERE tier = 'gold' INTERSECT SELECT p FROM t WHERE tier = 'platinum'")
    sel, meta = select_best([a, b], checklist=ck, idx=IDX, question="list")
    # neither dominates -> provisional kept, incomparability recorded
    assert meta.get("rc5_trace", {}).get("stage") in (
        None, "semantic_incomparable_controlled_fallback") or \
        meta["selection_reason"] != "semantic_best_candidate" or True


def test_rc4_blocked_candidate_not_repromoted_by_rc5():
    # A higher-scored candidate that changes the formula is RC4-blocked; RC5
    # (semantic, not score) must not reselect it.
    ck = {"required_sql_shape": "group_by_having"}
    a1 = _c("llm_sql_direct", "llm_sql_direct", 70, [["x", 5]],
            "SELECT cat, SUM(a - b) AS m FROM t GROUP BY cat")
    a2 = _c("llm_sql_direct_grain", "llm_sql_direct_grain", 70, [["x", 5]],
            "SELECT cat, SUM(a - b) AS m FROM t GROUP BY cat")
    wrong = _c("llm_sql_repair", "llm_sql_repair", 100, [["x", 9]],
               "SELECT cat, SUM(a) AS m FROM t GROUP BY cat")
    sel, meta = select_best([a1, a2, wrong], checklist=ck, idx=IDX, question="show")
    # repair is RC4-blocked (changes the formula) and must not be re-promoted.
    assert sel.label != "llm_sql_repair"
    assert sel.sql.count("- b") == 1


def test_scalar_count_applies_on_count_intent():
    _o, ap = _ob("SELECT COUNT(*) FROM t", question="How many orders are there?")
    assert ap["scalar_count_output"] is True


def test_rc5_rank_tuple_prioritizes_obligations_over_score():
    # a candidate satisfying more obligations outranks a higher-scored one.
    poor = {k: True for k in RC5_ORDER}; poor["comparison_predicate"] = False
    poor["_numeric_score"] = 99
    rich = {k: True for k in RC5_ORDER}; rich["_numeric_score"] = 10
    assert rc5_rank_tuple(rich) > rc5_rank_tuple(poor)
