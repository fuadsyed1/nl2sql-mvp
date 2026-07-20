"""Stage 1 tests — validators/grain_validator.py + scorer integration.

Generic parent/child toy schema (no benchmark SQL hardcoded). Covers the ten
required grain cases: raw value vs per-entity total, AVG(rows) vs
AVG(entity totals), correct two-level aggregation, bare measure under
grouping, correct correlated comparison, low-confidence / missing contract,
parse failure, plain row-grain retrieval, and subquery false-positive safety.
"""

from semantic.semantic_contract import build_grain_contract
from validators.grain_validator import validate_grain
from sql_candidates.candidate_types import SqlCandidate
from sql_candidates.candidate_scorer import score_candidate

IDX = {
    "tables": {
        "patients": [{"name": "patient_id"}, {"name": "name"},
                     {"name": "insurance_provider"}],
        "invoices": [{"name": "invoice_id"}, {"name": "patient_id"},
                     {"name": "amount"}, {"name": "balance"},
                     {"name": "created_at"}],
    },
    "relationships": [
        {"from_table": "invoices", "from_column": "patient_id",
         "to_table": "patients", "to_column": "patient_id"},
    ],
}

CONTRACT = build_grain_contract({
    "measure_column": "invoices.amount",
    "measure_aggregation": "sum",
    "measure_entity_key": "patients.patient_id",
    "comparison_right_kind": "aggregate_of_entity_totals",
    "grain_confidence": "high",
}, IDX)
assert CONTRACT is not None and CONTRACT.is_actionable


# 1. raw invoice value must not satisfy a per-patient total request ------------
def test_raw_row_value_fails_per_entity_total():
    sql = ("SELECT p.name FROM patients p JOIN invoices i "
           "ON i.patient_id = p.patient_id WHERE i.amount > "
           "(SELECT AVG(i2.amount) FROM invoices i2)")
    v = validate_grain(CONTRACT, sql, IDX)
    assert v.fatal, v
    assert v.skipped is None


# 2. AVG(rows) must not satisfy AVG(per-entity totals) -------------------------
def test_avg_of_rows_fails_avg_of_entity_totals():
    # left side even computes the correct per-patient SUM — the raw-rows AVG
    # on the right is still a provable violation (F2)
    sql = ("SELECT p.patient_id FROM patients p JOIN invoices i "
           "ON i.patient_id = p.patient_id GROUP BY p.patient_id "
           "HAVING SUM(i.amount) > (SELECT AVG(i2.amount) FROM invoices i2)")
    v = validate_grain(CONTRACT, sql, IDX)
    assert any("raw rows" in f for f in v.fatal), v


# 3. correct two-level aggregation must pass -----------------------------------
def test_two_level_aggregation_passes():
    sql = (
        "WITH pt AS (SELECT patient_id, SUM(amount) AS total FROM invoices "
        "GROUP BY patient_id) "
        "SELECT p.name FROM patients p JOIN pt ON pt.patient_id = p.patient_id "
        "WHERE pt.total > (SELECT AVG(total) FROM pt)")
    v = validate_grain(CONTRACT, sql, IDX)
    assert v.fatal == [], v
    assert v.checks["requirement_1"].get("required_aggregate_found") is True


# 4. grouped query with a nonaggregated child measure must fail ----------------
def test_grouped_bare_child_measure_fails():
    sql = ("SELECT p.patient_id, i.balance FROM patients p JOIN invoices i "
           "ON i.patient_id = p.patient_id GROUP BY p.patient_id "
           "HAVING COUNT(i.invoice_id) > 1")
    contract = build_grain_contract({
        "measure_column": "invoices.balance",
        "measure_aggregation": "sum",
        "measure_entity_key": "patients.patient_id",
        "grain_confidence": "high",
    }, IDX)
    v = validate_grain(contract, sql, IDX)
    assert any("nonaggregated" in f for f in v.fatal), v


# 5. correct correlated comparison at the required entity grain must pass ------
def test_correct_correlated_entity_grain_passes():
    sql = (
        "WITH pt AS (SELECT patient_id, SUM(amount) AS total FROM invoices "
        "GROUP BY patient_id) "
        "SELECT p.name FROM patients p JOIN pt ON pt.patient_id = p.patient_id "
        "WHERE pt.total > (SELECT AVG(pt2.total) FROM pt pt2 "
        "JOIN patients p2 ON p2.patient_id = pt2.patient_id "
        "WHERE p2.insurance_provider = p.insurance_provider)")
    v = validate_grain(CONTRACT, sql, IDX)
    assert v.fatal == [], v


# 6. low-confidence contract must not create a fatal violation -----------------
def test_low_confidence_contract_never_fatal():
    bad_sql = ("SELECT p.name FROM patients p JOIN invoices i "
               "ON i.patient_id = p.patient_id WHERE i.amount > "
               "(SELECT AVG(i2.amount) FROM invoices i2)")
    for conf in ("medium", "low", None):
        contract = build_grain_contract({
            "measure_column": "invoices.amount",
            "measure_aggregation": "sum",
            "measure_entity_key": "patients.patient_id",
            "grain_confidence": conf,
        }, IDX)
        v = validate_grain(contract, bad_sql, IDX)
        assert v.fatal == [], (conf, v)
        assert v.skipped is not None


# 7. missing contract must preserve prior behavior ------------------------------
def test_missing_contract_is_noop():
    v = validate_grain(None, "SELECT 1", IDX)
    assert v.fatal == [] and v.warnings == [] and v.skipped


# 8. SQL parse failure must not crash scoring -----------------------------------
def test_parse_failure_is_nonfatal_and_never_raises():
    v = validate_grain(CONTRACT, "SELEC amount FRM invoices", IDX)
    assert v.fatal == [] and v.skipped and "not analyzable" in v.skipped
    v = validate_grain(CONTRACT, "", IDX)
    assert v.fatal == []


# 9. simple row-grain retrieval with no aggregation must not be rejected --------
def test_row_grain_retrieval_not_rejected():
    contract = build_grain_contract({
        "measure_column": "invoices.amount",
        "measure_aggregation": "none",
        "grain_confidence": "high",
    }, IDX)
    v = validate_grain(
        contract, "SELECT amount FROM invoices WHERE amount > 100", IDX)
    assert v.fatal == []


# 10. correct queries with subqueries must not be falsely rejected --------------
def test_subqueries_alone_do_not_reject():
    sql = (
        "SELECT p.name FROM patients p WHERE p.patient_id IN "
        "(SELECT i.patient_id FROM invoices i GROUP BY i.patient_id "
        " HAVING SUM(i.amount) > 500)")
    v = validate_grain(CONTRACT, sql, IDX)
    assert v.fatal == [], v


# latest-row restriction (Q13 shape, generic): LIMIT 1 note ---------------------
def test_limit_one_single_event_is_flagged():
    sql = (
        "SELECT p.name FROM patients p WHERE "
        "(SELECT i.amount FROM invoices i WHERE i.patient_id = p.patient_id "
        " ORDER BY i.created_at DESC LIMIT 1) > "
        "(SELECT AVG(i2.amount) FROM invoices i2)")
    v = validate_grain(CONTRACT, sql, IDX)
    assert any("LIMIT 1" in f for f in v.fatal), v


# scorer integration -------------------------------------------------------------
GRAPH = {
    "tables": [
        {"table_name": "patients", "columns": [
            {"column_name": "patient_id", "data_type": "INTEGER",
             "is_primary_key_candidate": True},
            {"column_name": "name", "data_type": "TEXT"},
            {"column_name": "insurance_provider", "data_type": "TEXT"}]},
        {"table_name": "invoices", "columns": [
            {"column_name": "invoice_id", "data_type": "INTEGER",
             "is_primary_key_candidate": True},
            {"column_name": "patient_id", "data_type": "INTEGER"},
            {"column_name": "amount", "data_type": "REAL"},
            {"column_name": "balance", "data_type": "REAL"},
            {"column_name": "created_at", "data_type": "TEXT"}]},
    ],
    "relationships": [
        {"from_table": "invoices", "from_column": "patient_id",
         "to_table": "patients", "to_column": "patient_id"},
    ],
}


def _cand(sql):
    return SqlCandidate(
        source="llm_sql_direct", label="llm_sql_direct", sql=sql,
        execution={"executed": True, "columns": ["name"], "rows": [["x"]],
                   "row_count": 1, "truncated": False, "diagnostics": {}})


def test_scorer_marks_grain_violation_fatal():
    question = "patients whose total invoiced amount is above the average"
    bad = _cand("SELECT p.name FROM patients p JOIN invoices i "
                "ON i.patient_id = p.patient_id WHERE i.amount > "
                "(SELECT AVG(i2.amount) FROM invoices i2)")
    score_candidate(question, bad, GRAPH, contract=CONTRACT)
    assert any("grain violation" in f for f in bad.validation["fatal"])

    good = _cand(
        "WITH pt AS (SELECT patient_id, SUM(amount) AS total FROM invoices "
        "GROUP BY patient_id) "
        "SELECT p.name FROM patients p JOIN pt ON pt.patient_id = p.patient_id "
        "WHERE pt.total > (SELECT AVG(total) FROM pt)")
    score_candidate(question, good, GRAPH, contract=CONTRACT)
    assert not any("grain violation" in f for f in good.validation["fatal"])


def test_scorer_without_contract_unchanged():
    question = "patients whose total invoiced amount is above the average"
    sql = ("SELECT p.name FROM patients p JOIN invoices i "
           "ON i.patient_id = p.patient_id WHERE i.amount > "
           "(SELECT AVG(i2.amount) FROM invoices i2)")
    a, b = _cand(sql), _cand(sql)
    score_candidate(question, a, GRAPH)                      # no contract
    score_candidate(question, b, GRAPH, contract=None)       # explicit None
    assert a.score == b.score
    assert not any("grain violation" in f for f in a.validation["fatal"])
    assert a.validation["grain_contract"]["skipped"]


def test_scorer_survives_garbage_sql_with_contract():
    cand = _cand("SELEC nonsense FRM nowhere")
    cand.execution = {"executed": False, "error": "syntax error"}
    score_candidate("anything", cand, GRAPH, contract=CONTRACT)
    assert not any("grain violation" in f
                   for f in cand.validation.get("fatal") or [])
