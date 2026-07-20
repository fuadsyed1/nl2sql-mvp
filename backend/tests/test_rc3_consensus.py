"""
RC3 — repair-candidate consensus / semantic-obligation tests.

These tests pin the RC3 behaviour: a candidate that is provably semantically
INCOMPLETE (misses a requested output aggregate, a derived-formula operand, or a
required set operator) is demoted below complete candidates, correlated
generation lineages are identified, and semantically-equivalent SQL shares one
canonical signature. All logic under test is schema-generic and contract-driven;
the concrete schema names below live only in the test fixtures.
"""
from semantic.semantic_contract import GrainRequirement, SemanticContract
from sql_candidates.semantic_obligations import (
    compute_profile, canonical_signature, lineage_family, is_eligible, dominates)
from sql_candidates.candidate_selector import select_best


def _prof(sql, contract=None, checklist=None, fatal=None):
    return compute_profile(sql, {"fatal": fatal or []}, checklist, contract, None)


def _out_agg_contract():
    # count requested as an OUTPUT (no comparison threshold).
    return SemanticContract(requirements=(GrainRequirement(
        measure_table="shipments", measure_column="shipment_id",
        measure_aggregation="count"),))


def _filter_contract():
    # count used as a HAVING threshold filter (comparison present).
    return SemanticContract(requirements=(GrainRequirement(
        measure_table="customers", measure_column="customer_id",
        measure_aggregation="count",
        comparison_operator=">", comparison_constant=50.0),))


# --------------------------------------------------------------------------
# generation lineage
# --------------------------------------------------------------------------
def test_lineage_direct_family_shared():
    fam = {lineage_family(s) for s in
           ("llm_sql_direct", "llm_sql_direct_grain",
            "llm_sql_direct_variant", "llm_sql_repair")}
    assert fam == {"direct"}


def test_lineage_extraction_family_shared():
    assert lineage_family("llm_primary") == "extraction"
    assert lineage_family("llm_variant_1") == "extraction"
    assert lineage_family("llm_variant_2") == "extraction"
    assert lineage_family("query_family") == "family"


# --------------------------------------------------------------------------
# canonical signature (semantic duplicate detection)
# --------------------------------------------------------------------------
def test_signature_equivalent_formatting_matches():
    a = 'SELECT "a"."state_code", COUNT(*) FROM "addresses" AS a GROUP BY "a"."state_code"'
    b = "select state_code, count(*)  from addresses group by state_code"
    assert canonical_signature(a) == canonical_signature(b)


def test_signature_different_meaning_differs():
    a = "SELECT state_code, COUNT(*) FROM addresses GROUP BY state_code"
    b = "SELECT state_code FROM addresses GROUP BY state_code"
    assert canonical_signature(a) != canonical_signature(b)


def test_signature_where_order_insensitive():
    a = "SELECT id FROM t WHERE x = 1 AND y = 2"
    b = "SELECT id FROM t WHERE y = 2 AND x = 1"
    assert canonical_signature(a) == canonical_signature(b)


# --------------------------------------------------------------------------
# output-aggregate obligation (contract-driven)
# --------------------------------------------------------------------------
def test_output_aggregate_missing_is_incomplete():
    # count requested as output, but candidate projects only the key.
    sql = "SELECT state_code FROM shipments GROUP BY state_code HAVING COUNT(*) > 0"
    p = _prof(sql, _out_agg_contract())
    assert p["required_output_aggregate_satisfied"] is False
    assert p["eligibility"] == "incomplete"


def test_output_aggregate_present_is_eligible():
    sql = "SELECT state_code, COUNT(*) FROM shipments GROUP BY state_code"
    p = _prof(sql, _out_agg_contract())
    assert p["required_output_aggregate_satisfied"] is True
    assert is_eligible(p)


def test_threshold_filter_not_treated_as_output_aggregate():
    # count is a HAVING threshold (a filter) — key-only projection is correct.
    sql = ("SELECT loyalty_tier FROM customers GROUP BY loyalty_tier "
           "HAVING COUNT(customer_id) > 50")
    p = _prof(sql, _filter_contract())
    assert p["required_output_aggregate_satisfied"] is True
    assert is_eligible(p)


def test_order_by_limit_ranking_aggregate_not_required_in_projection():
    # top-k ranking: the aggregate is the ORDER BY key, need not be projected.
    sql = ("SELECT state_code FROM shipments GROUP BY state_code "
           "ORDER BY COUNT(shipment_id) DESC LIMIT 5")
    checklist = {"required_sql_shape": "order_by_limit"}
    p = _prof(sql, _out_agg_contract(), checklist)
    assert p["required_output_aggregate_satisfied"] is True
    assert is_eligible(p)


# --------------------------------------------------------------------------
# bare-key grouping (AST-only, no contract) — narrow high-precision signal
# --------------------------------------------------------------------------
def test_bare_key_single_table_vacuous_having_is_incomplete():
    sql = "SELECT category FROM products GROUP BY category HAVING COUNT(*) > 0"
    p = _prof(sql)  # no contract at all
    assert p["required_output_aggregate_satisfied"] is False
    assert p["eligibility"] == "incomplete"


def test_set_membership_grouping_not_flagged():
    # joins + WHERE + real existence HAVING => grouping does set-membership work;
    # only the entity keys are requested, so this must stay eligible.
    sql = ("SELECT c.customer_id, c.first_name FROM customers c "
           "JOIN sales_orders so ON c.customer_id = so.customer_id "
           "JOIN payments p ON c.customer_id = p.customer_id "
           "WHERE so.order_status = 'delivered' AND p.payment_status = 'settled' "
           "GROUP BY c.customer_id, c.first_name "
           "HAVING COUNT(DISTINCT so.order_id) > 0 AND COUNT(DISTINCT p.payment_id) > 0")
    p = _prof(sql)
    assert p["required_output_aggregate_satisfied"] is True
    assert is_eligible(p)


# --------------------------------------------------------------------------
# derived-formula obligation
# --------------------------------------------------------------------------
def _formula_contract():
    return SemanticContract(requirements=(GrainRequirement(
        measure_components=(("items", "line_total"), ("items", "line_subtotal")),
        measure_operation="subtract"),))


def test_formula_missing_operand_is_incomplete():
    sql = "SELECT product_id, SUM(line_total) FROM items GROUP BY product_id"
    p = _prof(sql, _formula_contract())
    assert p["required_formula_satisfied"] is False
    assert p["eligibility"] == "incomplete"


def test_formula_all_operands_present_is_eligible():
    sql = ("SELECT product_id, SUM(line_total - line_subtotal) "
           "FROM items GROUP BY product_id")
    p = _prof(sql, _formula_contract())
    assert p["required_formula_satisfied"] is True
    assert is_eligible(p)


# --------------------------------------------------------------------------
# set-operation obligation
# --------------------------------------------------------------------------
def test_set_operation_missing_operator_is_incomplete():
    checklist = {"required_sql_shape": "set_operation"}
    sql = "SELECT product_id FROM sales_2024"
    p = _prof(sql, None, checklist)
    assert p["required_set_conditions_satisfied"] is False
    assert p["eligibility"] == "incomplete"


def test_set_operation_operator_present_is_eligible():
    checklist = {"required_sql_shape": "set_operation"}
    sql = "SELECT product_id FROM sales_2024 INTERSECT SELECT product_id FROM sales_2025"
    p = _prof(sql, None, checklist)
    assert p["required_set_conditions_satisfied"] is True
    assert is_eligible(p)


# --------------------------------------------------------------------------
# eligibility tiers + dominance
# --------------------------------------------------------------------------
def test_fatal_candidate_is_not_eligible():
    p = _prof("SELECT 1", None, None, fatal=["illegal join"])
    assert p["eligibility"] == "fatal"
    assert not is_eligible(p)


def test_dominance_superset_beats_subset():
    complete = _prof("SELECT state_code, COUNT(*) FROM shipments GROUP BY state_code",
                     _out_agg_contract())
    incomplete = _prof("SELECT state_code FROM shipments GROUP BY state_code HAVING COUNT(*) > 0",
                       _out_agg_contract())
    assert dominates(complete, incomplete)
    assert not dominates(incomplete, complete)


# --------------------------------------------------------------------------
# selector integration: incomplete correlated candidate is demoted
# --------------------------------------------------------------------------
class _C:
    def __init__(self, source, label, score, rows):
        self.source, self.label, self.score = source, label, score
        self.executed_ok = True
        self.row_count = len(rows)
        self.sql = ("SELECT state_code, COUNT(*) FROM shipments GROUP BY state_code"
                    if label == "good"
                    else "SELECT state_code FROM shipments GROUP BY state_code HAVING COUNT(*) > 0")
        self.execution = {"executed": True, "rows": rows,
                          "columns": ["state_code", "c"] if label == "good" else ["state_code"]}
        self.validation = {"fatal": []}
        self.reasons = []


def test_incomplete_correlated_candidates_do_not_bury_complete_answer():
    # three correlated direct-family candidates omit the count (incomplete);
    # one complete candidate projects it. The complete one must be selected.
    good = _C("llm_primary", "good", 70, [["WA", 3], ["CA", 5]])
    b1 = _C("llm_sql_direct", "bad1", 95, [["WA"], ["CA"]])
    b2 = _C("llm_sql_direct_grain", "bad2", 95, [["WA"], ["CA"]])
    b3 = _C("llm_sql_direct_variant", "bad3", 95, [["WA"], ["CA"]])
    contract = _out_agg_contract()
    checklist = {"required_sql_shape": "group_by_having",
                 "required_group_keys": ["shipments.state_code"]}
    selected, meta = select_best([good, b1, b2, b3],
                                 checklist=checklist, contract=contract)
    assert selected is good
    assert meta["semantic_eligible_count"] == 1
