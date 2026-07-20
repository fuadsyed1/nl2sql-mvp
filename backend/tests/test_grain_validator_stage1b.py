"""Stage 1B tests — structural two-level aggregation, measure scope, and
multi-requirement contracts (grain validator).

Generic parent/child toy schema; no benchmark SQL hardcoded. Covers the 14
mandated cases: raw-aggregate comparisons inside one grouped scope, alias
independence, population grouping/correlation, restricted lifetime measures
(LIMIT 1 / MAX-equality / latest-row CTE), qualifier-contaminated measure
scopes, multi-requirement contracts, and false-positive safety.
"""

from semantic.semantic_contract import build_semantic_contract
from validators.grain_validator import validate_grain

IDX = {
    "tables": {
        "patients": [{"name": "patient_id"}, {"name": "name"},
                     {"name": "insurance_provider"}, {"name": "city"}],
        "appointments": [{"name": "appointment_id"}, {"name": "patient_id"},
                         {"name": "status"}, {"name": "appointment_date"}],
        "invoices": [{"name": "invoice_id"}, {"name": "appointment_id"},
                     {"name": "patient_id"}, {"name": "amount"},
                     {"name": "created_at"}],
        "lab_results": [{"name": "lab_id"}, {"name": "appointment_id"},
                        {"name": "test_name"}, {"name": "result_value"},
                        {"name": "result_flag"}],
    },
    "relationships": [],
}


def _contract(**overrides):
    entry = {
        "measure_column": "invoices.amount",
        "aggregation": "sum",
        "entity_key": "patients.patient_id",
        "comparison_right_kind": "aggregate_of_entity_totals",
        "population_key": None,
        "measure_scope": None,
        "confidence": "high",
    }
    entry.update(overrides)
    return build_semantic_contract({"grain_requirements": [entry]}, IDX)


# 1. SUM(raw) vs AVG(raw) in the same entity group must fail -------------------
def test_sum_vs_avg_raw_same_group_fails():
    sql = ("SELECT p.patient_id FROM patients p JOIN invoices i "
           "ON i.patient_id = p.patient_id GROUP BY p.patient_id "
           "HAVING SUM(i.amount) > AVG(i.amount)")
    v = validate_grain(_contract(), sql, IDX)
    assert any("raw rows" in f for f in v.fatal), v


# 2. an alias such as avg_by_provider must not affect validation ---------------
def test_alias_name_does_not_launder_grain():
    sql = ("SELECT p.patient_id, SUM(i.amount) AS total_invoiced, "
           "AVG(i.amount) AS avg_by_provider "
           "FROM patients p JOIN invoices i ON i.patient_id = p.patient_id "
           "GROUP BY p.patient_id "
           "HAVING total_invoiced > avg_by_provider")
    v = validate_grain(
        _contract(population_key="patients.insurance_provider"), sql, IDX)
    assert any("raw rows" in f for f in v.fatal), v


# 3. inner SUM per entity + outer AVG grouped by population must pass ----------
def test_two_level_with_population_grouping_passes():
    sql = (
        "WITH pt AS (SELECT i.patient_id, p.insurance_provider, "
        "SUM(i.amount) AS total FROM invoices i JOIN patients p "
        "ON p.patient_id = i.patient_id "
        "GROUP BY i.patient_id, p.insurance_provider), "
        "pa AS (SELECT insurance_provider, AVG(total) AS avg_total FROM pt "
        "GROUP BY insurance_provider) "
        "SELECT pt.patient_id FROM pt JOIN pa "
        "ON pa.insurance_provider = pt.insurance_provider "
        "WHERE pt.total > pa.avg_total")
    v = validate_grain(
        _contract(population_key="patients.insurance_provider"), sql, IDX)
    assert v.fatal == [], v


# 4. inner SUM + ungrouped / wrong-population AVG must fail --------------------
def test_two_level_without_population_fails():
    ungrouped = (
        "WITH pt AS (SELECT patient_id, SUM(amount) AS total FROM invoices "
        "GROUP BY patient_id) "
        "SELECT p.name FROM patients p JOIN pt ON pt.patient_id = p.patient_id "
        "WHERE pt.total > (SELECT AVG(total) FROM pt)")
    v = validate_grain(
        _contract(population_key="patients.insurance_provider"), ungrouped, IDX)
    assert any("population" in f for f in v.fatal), v

    wrong_pop = (
        "WITH pt AS (SELECT patient_id, SUM(amount) AS total FROM invoices "
        "GROUP BY patient_id) "
        "SELECT p.name FROM patients p JOIN pt ON pt.patient_id = p.patient_id "
        "WHERE pt.total > (SELECT AVG(pt2.total) FROM pt pt2 "
        "JOIN patients px ON px.patient_id = pt2.patient_id "
        "WHERE px.city = p.city)")
    v = validate_grain(
        _contract(population_key="patients.insurance_provider"), wrong_pop, IDX)
    assert any("population" in f for f in v.fatal), v


# 5. a lifetime measure restricted to a latest-row source must fail ------------
def test_lifetime_measure_from_latest_row_cte_fails():
    sql = (
        "SELECT p.name FROM patients p WHERE "
        "(SELECT SUM(li.amount) FROM "
        " (SELECT i.amount FROM invoices i WHERE i.patient_id = p.patient_id "
        "  ORDER BY i.created_at DESC LIMIT 1) li) > 500")
    v = validate_grain(
        _contract(measure_scope="all_entity_rows",
                  comparison_right_kind="constant"), sql, IDX)
    assert any("restricted scope" in f for f in v.fatal), v


# 6. a lifetime measure restricted by MAX(date) equality must fail -------------
def test_lifetime_measure_restricted_by_max_date_equality_fails():
    sql = (
        "SELECT p.patient_id FROM patients p "
        "JOIN appointments a ON a.patient_id = p.patient_id "
        "AND a.appointment_date = (SELECT MAX(a2.appointment_date) "
        "  FROM appointments a2 WHERE a2.patient_id = p.patient_id) "
        "JOIN invoices i ON i.appointment_id = a.appointment_id "
        "GROUP BY p.patient_id "
        "HAVING SUM(i.amount) > (SELECT AVG(t.total) FROM "
        "  (SELECT patient_id, SUM(amount) AS total FROM invoices "
        "   GROUP BY patient_id) t)")
    v = validate_grain(_contract(measure_scope="all_entity_rows"), sql, IDX)
    assert any("restricted scope" in f for f in v.fatal), v


# 7. latest-event QUALIFIER separated from an all-row lifetime CTE must pass ---
def test_qualifier_separated_from_lifetime_total_passes():
    sql = (
        "WITH pt AS (SELECT patient_id, SUM(amount) AS total FROM invoices "
        "GROUP BY patient_id) "
        "SELECT p.name FROM patients p JOIN pt ON pt.patient_id = p.patient_id "
        "WHERE p.patient_id IN (SELECT a.patient_id FROM appointments a "
        "  WHERE a.status = 'completed' AND a.appointment_date = "
        "  (SELECT MAX(a2.appointment_date) FROM appointments a2 "
        "   WHERE a2.patient_id = a.patient_id)) "
        "AND pt.total > (SELECT AVG(total) FROM pt)")
    v = validate_grain(_contract(measure_scope="all_entity_rows"), sql, IDX)
    assert v.fatal == [], v


# 8. a contract can carry at least two independent grain requirements ----------
def test_contract_with_two_requirements():
    c = build_semantic_contract({"grain_requirements": [
        {"measure_column": "lab_results.result_value", "aggregation": "avg",
         "entity_key": "lab_results.test_name",
         "comparison_right_kind": "aggregate_of_rows", "confidence": "high"},
        {"measure_column": "invoices.amount", "aggregation": "sum",
         "entity_key": "patients.patient_id",
         "comparison_right_kind": "aggregate_of_entity_totals",
         "measure_scope": "all_entity_rows", "confidence": "high"},
    ]}, IDX)
    assert c is not None and len(c.requirements) == 2
    assert len(c.actionable_requirements) == 2


_TWO_REQ = {"grain_requirements": [
    {"measure_column": "lab_results.result_value", "aggregation": "avg",
     "entity_key": "lab_results.test_name",
     "comparison_right_kind": "aggregate_of_rows", "confidence": "high"},
    {"measure_column": "invoices.amount", "aggregation": "sum",
     "entity_key": "patients.patient_id",
     "comparison_right_kind": "aggregate_of_entity_totals",
     "confidence": "high"},
]}

# Q40-shaped: the per-test average is handled correctly, but the second
# requirement (per-patient total) is answered with a raw invoice value.
_Q40_SHAPE_SQL = (
    "SELECT lr.lab_id FROM lab_results lr "
    "JOIN appointments a ON a.appointment_id = lr.appointment_id "
    "JOIN invoices i ON i.appointment_id = a.appointment_id "
    "WHERE lr.result_value > (SELECT AVG(l2.result_value) FROM lab_results l2 "
    "  WHERE l2.test_name = lr.test_name) "
    "AND i.amount > (SELECT AVG(amount) FROM invoices)")


# 9. satisfying only one of two high-confidence requirements must fail ---------
def test_one_of_two_requirements_not_enough():
    c = build_semantic_contract(_TWO_REQ, IDX)
    v = validate_grain(c, _Q40_SHAPE_SQL, IDX)
    assert v.fatal, v
    assert all("requirement 2/2" in f for f in v.fatal), v


# 10. Q40-shape: correct test average + raw invoice comparison must fail -------
def test_q40_shape_raw_second_measure_fails():
    c = build_semantic_contract(_TWO_REQ, IDX)
    v = validate_grain(c, _Q40_SHAPE_SQL, IDX)
    assert any("raw row-level value invoices.amount" in f for f in v.fatal), v
    # the correct fix passes both requirements
    good = (
        "WITH pt AS (SELECT patient_id, SUM(amount) AS total FROM invoices "
        "GROUP BY patient_id) "
        "SELECT lr.lab_id FROM lab_results lr "
        "JOIN appointments a ON a.appointment_id = lr.appointment_id "
        "JOIN pt ON pt.patient_id = a.patient_id "
        "WHERE lr.result_value > (SELECT AVG(l2.result_value) FROM "
        "  lab_results l2 WHERE l2.test_name = lr.test_name) "
        "AND pt.total > (SELECT AVG(total) FROM pt)")
    v = validate_grain(c, good, IDX)
    assert v.fatal == [], v


# 11. all-entity measure inside a qualifier-filtered scope must fail -----------
def test_qualifier_filter_contaminates_lifetime_measure():
    sql = (
        "SELECT p.patient_id FROM patients p "
        "JOIN appointments a ON a.patient_id = p.patient_id "
        "JOIN lab_results l ON l.appointment_id = a.appointment_id "
        "JOIN invoices i ON i.appointment_id = a.appointment_id "
        "WHERE l.result_flag IN ('critical', 'high') "
        "GROUP BY p.patient_id "
        "HAVING COUNT(DISTINCT l.test_name) > 1 "
        "AND SUM(i.amount) > (SELECT AVG(t.total) FROM "
        "  (SELECT patient_id, SUM(amount) AS total FROM invoices "
        "   GROUP BY patient_id) t)")
    v = validate_grain(_contract(measure_scope="all_entity_rows"), sql, IDX)
    assert any("lab_results.result_flag" in f for f in v.fatal), v


# 12. low-confidence or missing scope information must remain nonfatal ---------
def test_uncertain_scope_information_is_nonfatal():
    sql = (
        "SELECT p.patient_id FROM patients p "
        "JOIN lab_results l ON 1 = 1 "
        "JOIN invoices i ON i.patient_id = p.patient_id "
        "WHERE l.result_flag IN ('critical', 'high') "
        "GROUP BY p.patient_id "
        "HAVING SUM(i.amount) > (SELECT AVG(amount) FROM invoices)")
    # same contaminated shape, but no measure_scope claim -> no scope fatal
    v = validate_grain(_contract(measure_scope=None,
                                 comparison_right_kind=None), sql, IDX)
    assert not any("restricted scope" in f for f in v.fatal), v
    # low confidence -> requirement not actionable -> fully skipped
    v = validate_grain(_contract(confidence="medium",
                                 measure_scope="all_entity_rows"), sql, IDX)
    assert v.fatal == [] and v.skipped is not None


# 13. correct two-level correlated aggregation must keep passing ---------------
def test_correlated_two_level_still_passes():
    sql = (
        "WITH pt AS (SELECT i.patient_id, p.insurance_provider, "
        "SUM(i.amount) AS total FROM invoices i JOIN patients p "
        "ON p.patient_id = i.patient_id GROUP BY i.patient_id, "
        "p.insurance_provider) "
        "SELECT p.name FROM patients p JOIN pt ON pt.patient_id = p.patient_id "
        "WHERE pt.total > (SELECT AVG(pt2.total) FROM pt pt2 "
        "WHERE pt2.insurance_provider = p.insurance_provider)")
    v = validate_grain(
        _contract(population_key="patients.insurance_provider",
                  measure_scope="all_entity_rows"), sql, IDX)
    assert v.fatal == [], v


# 14. row-grain and correlated-average queries are not falsely rejected --------
def test_row_grain_and_correlated_average_not_rejected():
    row_contract = _contract(aggregation="none", entity_key=None,
                             comparison_right_kind=None)
    v = validate_grain(
        row_contract, "SELECT amount FROM invoices WHERE amount > 100", IDX)
    assert v.fatal == []

    per_row = build_semantic_contract({"grain_requirements": [
        {"measure_column": "lab_results.result_value", "aggregation": "avg",
         "entity_key": "lab_results.test_name",
         "comparison_right_kind": "aggregate_of_rows",
         "confidence": "high"}]}, IDX)
    sql = ("SELECT lr.lab_id FROM lab_results lr WHERE lr.result_value > "
           "(SELECT AVG(l2.result_value) FROM lab_results l2 "
           " WHERE l2.test_name = lr.test_name)")
    v = validate_grain(per_row, sql, IDX)
    assert v.fatal == [], v
