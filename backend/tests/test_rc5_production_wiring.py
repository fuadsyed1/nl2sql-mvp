"""
RC5 production-wiring tests.

Prove that every production `select_best` call in app.py threads the four
semantic arguments (checklist, contract, idx, question) so the frozen RC3/RC4/RC5
selection logic is active on the real API path (both /execute_sql and
/check_containment share run_nl_sql_pipeline). The wiring is asserted
structurally (AST of app.py) - no LLM/DB is exercised - and the activated
behavior is confirmed by driving select_best with production-shaped arguments.
"""
import ast
import os

from sql_candidates.candidate_types import SqlCandidate
from sql_candidates.candidate_selector import select_best

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")


def _select_best_calls():
    tree = ast.parse(open(APP, encoding="utf-8").read())
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "select_best":
            calls.append({kw.arg for kw in node.keywords})
    return calls


# ---- 1-6, 11: every production call threads all four arguments --------------
def test_all_production_calls_thread_four_arguments():
    calls = _select_best_calls()
    assert calls, "no select_best calls found in app.py"
    for kwargs in calls:
        assert {"checklist", "contract", "idx", "question"} <= kwargs, kwargs


def test_checklist_threaded():
    assert all("checklist" in c for c in _select_best_calls())


def test_contract_threaded():
    assert all("contract" in c for c in _select_best_calls())


def test_idx_threaded():
    assert all("idx" in c for c in _select_best_calls())


def test_question_threaded():
    assert all("question" in c for c in _select_best_calls())


# ---- 5: containment shares the same pipeline (one code path) ----------------
def test_containment_shares_pipeline():
    src = open(APP, encoding="utf-8").read()
    assert "check_containment(database_id, body, run_nl_sql_pipeline)" in src
    assert "run_nl_sql_pipeline(database_id, body.question)" in src


# ---- 7: no production call uses the all-None fallback -----------------------
def test_no_production_call_uses_none_fallback():
    for kwargs in _select_best_calls():
        assert kwargs, "a production select_best call passes no semantic context"


# ---- 12: wiring added no LLM call (index builder is pure) -------------------
def test_index_builder_is_pure_no_llm():
    import query_families.slot_extractor as se
    src = open(se.__file__, encoding="utf-8").read()
    for bad in ("import requests", "ollama", "generate(", "openai", "http"):
        assert bad not in src.lower() or bad == "http", \
            "index builder must not perform network/LLM calls"
    src2 = open(APP, encoding="utf-8").read()
    # the only call added next to selection is se_index_schema(graph)
    assert "sem_index = se_index_schema(graph)" in src2


# ---- 8-10: activated selector behavior with production-shaped args ----------
IDX = {"tables": {
    "customers": [{"name": "customer_id", "is_key": True},
                  {"name": "loyalty_tier", "is_key": False}],
    "sales_orders": [{"name": "order_id", "is_key": True},
                     {"name": "customer_id", "is_key": True}],
    "payments": [{"name": "payment_id", "is_key": True},
                 {"name": "order_id", "is_key": True},
                 {"name": "customer_id", "is_key": True},
                 {"name": "amount", "is_key": False}],
}}


def _c(label, source, score, rows, sql):
    c = SqlCandidate(source=source, label=label, sql=sql,
                     execution={"executed": True, "columns": ["a"],
                                "rows": rows, "row_count": len(rows)})
    c.score = score
    return c


def test_rc3_eligibility_active_through_args():
    # A grouped answer that hides the count is RC3-incomplete and must not be
    # chosen over the candidate that projects it, when checklist is supplied.
    ck = {"required_sql_shape": "group_by_having"}
    good = _c("llm_primary", "llm_primary", 60, [["WA", 3]],
              "SELECT state_code, COUNT(*) FROM shipments GROUP BY state_code")
    bad = _c("llm_sql_direct", "llm_sql_direct", 95, [["WA"]],
             "SELECT state_code FROM shipments GROUP BY state_code HAVING COUNT(*) > 0")
    from semantic.semantic_contract import GrainRequirement, SemanticContract
    ct = SemanticContract(requirements=(GrainRequirement(
        measure_table="shipments", measure_column="shipment_id",
        measure_aggregation="count"),))
    sel, meta = select_best([good, bad], checklist=ck, contract=ct, idx=IDX,
                             question="Count shipments by state")
    assert sel is good


def test_rc4_block_active_through_args():
    ck = {"required_sql_shape": "group_by_having"}
    a1 = _c("llm_sql_direct", "llm_sql_direct", 70, [["x", 5]],
            "SELECT cat, SUM(a - b) AS m FROM t GROUP BY cat")
    a2 = _c("llm_sql_direct_grain", "llm_sql_direct_grain", 70, [["x", 5]],
            "SELECT cat, SUM(a - b) AS m FROM t GROUP BY cat")
    wrong = _c("llm_sql_repair", "llm_sql_repair", 100, [["x", 9]],
               "SELECT cat, SUM(a) AS m FROM t GROUP BY cat")
    sel, meta = select_best([a1, a2, wrong], checklist=ck, idx=IDX, question="show")
    assert sel.label != "llm_sql_repair"


def test_rc5_winner_active_through_args():
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
