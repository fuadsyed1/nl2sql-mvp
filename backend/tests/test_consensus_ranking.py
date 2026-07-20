"""
Independent semantic consensus tests.

Consensus is computed from independent generator lineages grouped by a
normalized semantic fingerprint (+ result-signature guard), not raw candidate
count or result-only equality. It is a tie-breaker that never overrides a
semantically dominating candidate, and it falls back to the deterministic path
when there is no valid independent consensus.
"""
from sql_candidates.consensus_ranking import (
    semantic_fingerprint, generator_family, analyze_consensus, consensus_select)
from sql_candidates.candidate_scorer import LOW_SCORE_THRESHOLD
from sql_candidates.candidate_types import SqlCandidate
from sql_candidates.candidate_selector import select_best, _SOURCE_PRIORITY

Q1 = "SELECT c.customer_id FROM customers c JOIN sales_orders so ON c.customer_id = so.customer_id"
Q2 = "SELECT c.customer_id FROM customers c JOIN sales_orders so ON c.customer_id = so.customer_id WHERE so.status = 'x'"
QAGG1 = "SELECT cat, SUM(a - b) FROM t GROUP BY cat"
QAGG2 = "SELECT cat, SUM(a) FROM t GROUP BY cat"
QGRP1 = "SELECT p, COUNT(*) FROM t GROUP BY p"
QGRP2 = "SELECT p FROM t GROUP BY p HAVING COUNT(*) > 0"
QSET1 = "SELECT id FROM a INTERSECT SELECT id FROM b"
QSET2 = "SELECT id FROM a UNION SELECT id FROM b"


def _c(source, label, score, sql, rows, ob=None, ap=None):
    c = SqlCandidate(source=source, label=label, sql=sql,
                     execution={"executed": True, "columns": ["x"],
                                "rows": rows, "row_count": len(rows)})
    c.score = score
    if ob is not None:
        c._rc5_ob, c._rc5_ap = ob, ap
    return c


def _sel(pool):
    return consensus_select(pool, LOW_SCORE_THRESHOLD, _SOURCE_PRIORITY)


R = [[1], [2]]


# 1
def test_three_from_one_family_count_as_one_vote():
    pool = [_c("llm_sql_direct", "d", 90, Q1, R),
            _c("llm_sql_direct_grain", "g", 90, Q1, R),
            _c("llm_sql_direct_variant", "v", 90, Q1, R)]
    groups = analyze_consensus(pool, LOW_SCORE_THRESHOLD)
    assert len(groups) == 1 and groups[0].independent_lineage_count == 1
    pick, meta, members = _sel(pool)
    assert pick is None
    assert meta["consensus_rejection_reason"] == "single_generator_family"


# 2
def test_repair_does_not_create_new_vote():
    pool = [_c("llm_sql_direct", "d", 90, Q1, R),
            _c("llm_sql_repair", "r", 100, Q1, R)]
    groups = analyze_consensus(pool, LOW_SCORE_THRESHOLD)
    assert groups[0].independent_lineage_count == 1   # repair inherits direct
    assert _sel(pool)[0] is None


# 3
def test_two_independent_families_same_fingerprint_form_consensus():
    pool = [_c("llm_primary", "p", 80, Q1, R),
            _c("llm_sql_direct", "d", 82, Q1, R)]
    pick, meta, members = _sel(pool)
    assert pick is not None
    assert meta["consensus_independent_lineage_count"] == 2
    assert meta["consensus_eligible"] is True


# 4
def test_same_result_different_where_no_consensus():
    pool = [_c("llm_primary", "p", 80, Q1, R),
            _c("llm_sql_direct", "d", 82, Q2, R)]   # extra WHERE
    assert semantic_fingerprint(Q1) != semantic_fingerprint(Q2)
    assert _sel(pool)[0] is None


# 5
def test_same_result_different_formula_no_consensus():
    pool = [_c("llm_primary", "p", 80, QAGG1, R),
            _c("llm_sql_direct", "d", 82, QAGG2, R)]
    assert semantic_fingerprint(QAGG1) != semantic_fingerprint(QAGG2)
    assert _sel(pool)[0] is None


# 6
def test_same_result_different_grouping_no_consensus():
    pool = [_c("llm_primary", "p", 80, QGRP1, R),
            _c("llm_sql_direct", "d", 82, QGRP2, R)]
    assert semantic_fingerprint(QGRP1) != semantic_fingerprint(QGRP2)
    assert _sel(pool)[0] is None


# 7
def test_same_result_different_set_semantics_no_consensus():
    pool = [_c("llm_primary", "p", 80, QSET1, R),
            _c("llm_sql_direct", "d", 82, QSET2, R)]
    assert semantic_fingerprint(QSET1) != semantic_fingerprint(QSET2)
    assert _sel(pool)[0] is None


# 8 - a fatal candidate never reaches the consensus pool
def test_fatal_candidate_cannot_participate():
    good = _c("llm_primary", "p", 60, Q1, R)
    fatal = _c("llm_sql_direct", "d", 99, Q1, R)
    fatal.validation = {"fatal": ["illegal join"]}
    sel, meta = select_best([good, fatal], checklist={})
    assert sel is good


# 9 - an RC4-blocked candidate cannot return through consensus
def test_rc4_blocked_candidate_not_returned():
    ck = {"required_sql_shape": "group_by_having"}
    a1 = _c("llm_sql_direct", "d", 70, "SELECT cat, SUM(a - b) AS m FROM t GROUP BY cat", [["x", 5]])
    a2 = _c("llm_sql_direct_grain", "g", 70, "SELECT cat, SUM(a - b) AS m FROM t GROUP BY cat", [["x", 5]])
    wrong = _c("llm_sql_repair", "r", 100, "SELECT cat, SUM(a) AS m FROM t GROUP BY cat", [["y", 9]])
    sel, meta = select_best([a1, a2, wrong], checklist=ck)
    assert sel.label != "r"


# 10 - a stronger RC5 candidate beats a larger consensus group
def test_stronger_semantic_candidate_beats_consensus():
    from sql_candidates.rc5_ranking import RC5_ORDER
    weak = {k: True for k in RC5_ORDER}; weak["comparison_predicate"] = False
    strong = {k: True for k in RC5_ORDER}
    ap = {k: True for k in RC5_ORDER}
    # two-family consensus whose rep is weak; a single candidate is stronger
    rep1 = _c("llm_primary", "p", 80, Q1, R, ob=weak, ap=ap)
    rep2 = _c("llm_sql_direct", "d", 80, Q1, R, ob=weak, ap=ap)
    better = _c("llm_variant_1", "b", 60, Q2, [[9]], ob=strong, ap=ap)
    pick, meta, members = _sel([rep1, rep2, better])
    assert pick is None
    assert meta["consensus_rejection_reason"] == "stronger_semantic_candidate_exists"
    assert meta["stronger_semantic_candidate"] == "b"


# 11 - RC5.1 Test 437 behavior unchanged (entity-grouped candidate wins)
def test_rc51_437_unchanged():
    IDX = {"tables": {
        "products": [{"name": "product_id", "is_key": True}, {"name": "product_name", "is_key": False}],
        "sales_order_items": [{"name": "order_item_id", "is_key": True},
                              {"name": "order_id", "is_key": True}, {"name": "product_id", "is_key": True}],
    }}
    ck = {"required_sql_shape": "comparison_subquery", "group_by_entity": "products.product_id",
          "required_literal_groups": [{"column": "customers.loyalty_tier",
                                       "literals": ["gold", "platinum", "bronze"]}]}
    grouped = ("SELECT p.product_id, p.product_name FROM products p "
               "JOIN sales_order_items soi ON p.product_id = soi.product_id GROUP BY p.product_id, p.product_name")
    dup = ("SELECT p.product_id, p.product_name FROM products p "
           "JOIN sales_order_items soi ON p.product_id = soi.product_id")
    direct = _c("llm_sql_direct", "llm_sql_direct", 80, grouped, [[1, "A"], [2, "B"]])
    grain = _c("llm_sql_direct_grain", "llm_sql_direct_grain", 80, dup, [[1, "A"], [1, "A"], [2, "B"]])
    sel, meta = select_best([grain, direct], checklist=ck, idx=IDX,
                            question="List products sold to both Gold and Platinum but not Bronze")
    assert sel.label == "llm_sql_direct"


# 12 - deterministic regardless of candidate order
def test_consensus_deterministic_input_order():
    a = _c("llm_primary", "p", 80, Q1, R)
    b = _c("llm_sql_direct", "d", 82, Q1, R)
    c = _c("query_family", "q", 40, Q2, [[7]])
    p1 = _sel([a, b, c])[0]
    p2 = _sel([c, b, a])[0]
    assert (p1.label if p1 else None) == (p2.label if p2 else None)


# 13 - aliases / formatting normalize to the same fingerprint
def test_alias_and_formatting_normalize():
    s1 = 'SELECT "c"."customer_id" FROM "customers" AS c   JOIN "sales_orders" AS so ON "c"."customer_id" = "so"."customer_id"'
    s2 = "select customer_id from customers join sales_orders on customers.customer_id = sales_orders.customer_id"
    assert semantic_fingerprint(s1) == semantic_fingerprint(s2)


# 14 - one-family agreement falls back to the normal selector, not consensus_group
def test_one_family_agreement_falls_back():
    pool = [_c("llm_sql_direct", "d", 90, Q1, R),
            _c("llm_sql_direct_variant", "v", 90, Q1, R)]
    sel, meta = select_best(pool, checklist={})
    assert meta["selection_reason"] == "best_scored_executed"
    assert meta["consensus_rejection_reason"] == "single_generator_family"


# 15 - no source label gets an automatic preference: a 2-family consensus wins
#      over a higher-priority single direct candidate.
def test_no_source_preference():
    p = _c("llm_primary", "p", 70, Q1, R)
    v = _c("llm_variant_1", "v", 70, Q1, R)          # extraction family x1? no -> both extraction
    q = _c("query_family", "q", 70, Q1, R)           # add a second family
    lone_direct = _c("llm_sql_direct", "d", 95, Q2, [[9]])   # higher priority+score, alone
    pick, meta, members = _sel([p, v, q, lone_direct])
    assert pick is not None and pick.source in ("llm_primary", "llm_variant", "query_family")
    assert meta["consensus_independent_lineage_count"] >= 2
