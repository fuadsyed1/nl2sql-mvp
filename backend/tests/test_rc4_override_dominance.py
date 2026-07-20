"""
RC4 — validation-score-override semantic-dominance tests.

A higher validation score may NOT override the current selection on its own; the
proposed candidate must semantically DOMINATE it (preserve every obligation,
formula, set operator and filter, add no new defect, and make a strict
improvement). All logic under test is schema-generic; concrete schema names are
confined to these fixtures.
"""
from semantic.semantic_contract import GrainRequirement, SemanticContract
from sql_candidates.semantic_obligations import compute_profile, override_dominates
from sql_candidates.candidate_types import SqlCandidate
from sql_candidates.candidate_selector import select_best


def _p(sql, checklist=None, contract=None, validation=None):
    return compute_profile(sql, validation or {"fatal": []}, checklist, contract, None)


def _allowed(pb, pa):
    ok, why, _ = override_dominates(pb, pa)
    return ok, why


def _formula_contract():
    return SemanticContract(requirements=(GrainRequirement(
        measure_components=(("t", "a"), ("t", "b")), measure_operation="subtract"),))


# 1
def test_missing_requested_output_cannot_override():
    ck = {"output_columns": ["state_code", "address_count"]}
    A = _p("SELECT state_code, COUNT(*) AS address_count FROM t GROUP BY state_code", ck)
    B = _p("SELECT state_code FROM t GROUP BY state_code", ck)
    ok, why = _allowed(B, A); assert not ok and "output" in why

# 2
def test_wrong_formula_cannot_override():
    A = _p("SELECT SUM(a) / SUM(b) AS r FROM t")
    B = _p("SELECT SUM(a) AS r FROM t")
    ok, why = _allowed(B, A); assert not ok and "formula" in why

# 3
def test_missing_formula_operand_cannot_override():
    c = _formula_contract()
    A = _p("SELECT SUM(a - b) AS r FROM t", None, c)
    B = _p("SELECT SUM(a) AS r FROM t", None, c)
    ok, why = _allowed(B, A); assert not ok

# 4
def test_wrong_denominator_cannot_override():
    A = _p("SELECT SUM(a) / SUM(b) AS r FROM t")
    B = _p("SELECT SUM(a) / SUM(c) AS r FROM t")
    ok, why = _allowed(B, A); assert not ok and "formula" in why

# 5
def test_unrequested_having_cannot_override():
    A = _p("SELECT cat, COUNT(*) FROM t GROUP BY cat")
    B = _p("SELECT cat, COUNT(*) FROM t GROUP BY cat HAVING COUNT(*) > 5")
    ok, why = _allowed(B, A); assert not ok and "having" in why.lower()

# 6
def test_unrequested_limit_cannot_override():
    A = _p("SELECT cat, COUNT(*) FROM t GROUP BY cat")
    B = _p("SELECT cat, COUNT(*) FROM t GROUP BY cat LIMIT 5")
    ok, why = _allowed(B, A); assert not ok and "limit" in why.lower()

# 7
def test_changed_relationship_role_cannot_override():
    A = _p("SELECT a FROM t", validation={"fatal": [], "illegal_joins": []})
    B = _p("SELECT a FROM t", validation={"fatal": [], "illegal_joins": ["x~y"]})
    ok, why = _allowed(B, A); assert not ok

# 8
def test_join_cannot_replace_required_union():
    ck = {"required_sql_shape": "set_operation"}
    A = _p("SELECT city FROM a UNION SELECT city FROM b", ck)
    B = _p("SELECT a.city FROM a JOIN b ON a.id = b.id", ck)
    ok, why = _allowed(B, A); assert not ok and "set" in why

# 9
def test_or_cannot_replace_required_intersection():
    ck = {"required_sql_shape": "set_operation"}
    A = _p("SELECT id FROM a INTERSECT SELECT id FROM b", ck)
    B = _p("SELECT id FROM a WHERE x = 1 OR y = 2", ck)
    ok, why = _allowed(B, A); assert not ok

# 10
def test_positive_membership_cannot_replace_required_exclusion():
    ck = {"required_sql_shape": "set_operation"}
    A = _p("SELECT id FROM a EXCEPT SELECT id FROM b", ck)
    B = _p("SELECT id FROM a", ck)
    ok, why = _allowed(B, A); assert not ok

# 11
def test_lost_status_filter_cannot_override():
    A = _p("SELECT id FROM t WHERE status = 'settled'")
    B = _p("SELECT id FROM t")
    ok, why = _allowed(B, A); assert not ok and "filter" in why

# 12
def test_changed_requested_grain_cannot_override():
    ck = {"required_sql_shape": "count_distinct"}
    A = _p("SELECT COUNT(DISTINCT customer_id) FROM t", ck)
    B = _p("SELECT customer_id, COUNT(*) FROM t GROUP BY customer_id", ck)
    ok, why = _allowed(B, A); assert not ok

# 13
def test_introduced_fanout_cannot_override():
    A = _p("SELECT a FROM t", validation={"fatal": [], "fanout": {"warnings": []}})
    B = _p("SELECT a FROM t", validation={"fatal": [], "fanout": {"warnings": ["multiplies parent"]}})
    ok, why = _allowed(B, A); assert not ok

# 14
def test_strict_superset_may_override():
    ck = {"output_columns": ["state_code", "cnt"]}
    A = _p("SELECT state_code FROM t GROUP BY state_code", ck)
    B = _p("SELECT state_code, COUNT(*) AS cnt FROM t GROUP BY state_code", ck)
    ok, why = _allowed(B, A); assert ok

# 15
def test_fixing_missing_formula_may_override():
    c = _formula_contract()
    A = _p("SELECT SUM(a) AS r FROM t", None, c)
    B = _p("SELECT SUM(a - b) AS r FROM t", None, c)
    ok, why = _allowed(B, A); assert ok

# 16
def test_different_obligations_are_incomparable_blocked():
    ck = {"output_columns": ["state_code", "cnt"]}
    # A supplies the outputs but B (missing an output) also drops a filter:
    A = _p("SELECT state_code, COUNT(*) AS cnt FROM t WHERE status = 'x' GROUP BY state_code", ck)
    B = _p("SELECT state_code FROM t GROUP BY state_code", ck)
    ok, why = _allowed(B, A); assert not ok

# 17
def test_score_increase_alone_is_not_dominance():
    A = _p("SELECT COUNT(*) FROM t")
    B = _p("SELECT COUNT(*) FROM t")  # identical semantics
    ok, why = _allowed(B, A); assert not ok and "higher score alone" in why

# 18
def test_no_override_when_none_attempted():
    def _c(label, source, score, rows):
        c = SqlCandidate(source=source, label=label, sql="SELECT 1",
                         execution={"executed": True, "columns": ["a"],
                                    "rows": rows, "row_count": len(rows)})
        c.score = score
        return c
    a = _c("p", "llm_primary", 80, [["x"]])
    b = _c("v", "llm_variant", 78, [["x"]])
    selected, meta = select_best([a, b])
    assert meta.get("override_trace") is None
    assert meta.get("override_blocked") is not True
