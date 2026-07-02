"""
test_family_guard.py

Guard tests: good family outputs must PASS (not be over-blocked), clearly-wrong
ones must FAIL. Pure — schema graph + extraction structure + family name in,
{valid, reasons} out. No DB, no model, no SQL generation.

Petfood cases use the shared GRAPH; two synthetic clinic/cyber graphs show the
guard is schema-generic (no hardcoded names).

Run:  python -m tests.test_family_guard
"""

from query_families.family_guard import validate_family_output
from query_families import family_types as ft
from tests.test_query_family_router import GRAPH, _col


def V(question, family, extraction, graph=GRAPH):
    return validate_family_output(question, family, extraction, {}, graph)


CLINIC = {
    "tables": [
        {"table_name": "patients", "columns": [
            _col("patient_id", "INTEGER", True), _col("patient_name"), _col("city")]},
        {"table_name": "doctors", "columns": [
            _col("doctor_id", "INTEGER", True), _col("doctor_name"), _col("specialty")]},
        {"table_name": "appointments", "columns": [
            _col("appointment_id", "INTEGER", True), _col("patient_id", "INTEGER"),
            _col("doctor_id", "INTEGER"), _col("visit_type"), _col("base_fee", "REAL"),
            _col("appt_date", "DATE")]},
        {"table_name": "prescriptions", "columns": [
            _col("prescription_id", "INTEGER", True), _col("appointment_id", "INTEGER"),
            _col("days_supply", "INTEGER")]},
        {"table_name": "lab_results", "columns": [
            _col("lab_id", "INTEGER", True), _col("appointment_id", "INTEGER"),
            _col("test_name"), _col("result_flag")]},
        {"table_name": "invoices", "columns": [
            _col("invoice_id", "INTEGER", True), _col("patient_id", "INTEGER"),
            _col("total", "REAL")]},
    ],
    "relationships": [
        {"from_table": "appointments", "from_column": "patient_id", "to_table": "patients", "to_column": "patient_id"},
        {"from_table": "appointments", "from_column": "doctor_id", "to_table": "doctors", "to_column": "doctor_id"},
        {"from_table": "prescriptions", "from_column": "appointment_id", "to_table": "appointments", "to_column": "appointment_id"},
        {"from_table": "lab_results", "from_column": "appointment_id", "to_table": "appointments", "to_column": "appointment_id"},
        {"from_table": "invoices", "from_column": "patient_id", "to_table": "patients", "to_column": "patient_id"},
    ],
}

CYBER = {
    "tables": [
        {"table_name": "devices", "columns": [
            _col("device_id", "INTEGER", True), _col("device_name"), _col("risk_score", "INTEGER")]},
        {"table_name": "alerts", "columns": [
            _col("alert_id", "INTEGER", True), _col("device_id", "INTEGER"), _col("alert_type")]},
    ],
    "relationships": [
        {"from_table": "alerts", "from_column": "device_id", "to_table": "devices", "to_column": "device_id"},
    ],
}

CYBER_TRAIN = {
    "tables": [
        {"table_name": "employees", "columns": [
            _col("employee_id", "INTEGER", True), _col("employee_name"), _col("department")]},
        {"table_name": "devices", "columns": [
            _col("device_id", "INTEGER", True), _col("employee_id", "INTEGER")]},
        {"table_name": "alerts", "columns": [
            _col("alert_id", "INTEGER", True), _col("device_id", "INTEGER"), _col("alert_type")]},
        {"table_name": "training_records", "columns": [
            _col("training_id", "INTEGER", True), _col("employee_id", "INTEGER"),
            _col("course_name"), _col("passed")]},
    ],
    "relationships": [
        {"from_table": "devices", "from_column": "employee_id", "to_table": "employees", "to_column": "employee_id"},
        {"from_table": "alerts", "from_column": "device_id", "to_table": "devices", "to_column": "device_id"},
        {"from_table": "training_records", "from_column": "employee_id", "to_table": "employees", "to_column": "employee_id"},
    ],
}


# ---------------------------------------------------------------------------
# SHOULD PASS
# ---------------------------------------------------------------------------
def test_pass_top_per_group():
    ex = {"tables": ["foods"],
          "select": [{"table": "foods", "column": "food_id"},
                     {"table": "foods", "column": "brand"},
                     {"table": "foods", "column": "price"}],
          "top_per_group": [{"table": "foods",
                             "partition_by": [{"table": "foods", "column": "brand"}],
                             "order_by": {"table": "foods", "column": "price", "direction": "desc"},
                             "rank": 1}]}
    r = V("List the highest priced food for each brand.", ft.TOP_PER_GROUP, ex)
    assert r["valid"], r
    print("[P1] Q5 top_per_group -> accepted")


def test_pass_count_distinct():
    cte = lambda n, a: {"name": n, "from_table": "owners",
                        "joins": [{"from_table": "owners", "from_column": "owner_id",
                                   "to_table": "purchases", "to_column": "owner_id"},
                                  {"from_table": "purchases", "from_column": "food_id",
                                   "to_table": "foods", "to_column": "food_id"}],
                        "select": [{"table": "owners", "column": "owner_id", "alias": "entity_id"}],
                        "aggregations": [{"function": "COUNT", "distinct": True,
                                          "table": "foods", "column": "brand", "alias": a}],
                        "group_by": [{"table": "owners", "column": "owner_id"}]}
    ex = {"derived_relations": [cte("count_a", "count_a"), cte("count_b", "count_b")],
          "select": [{"table": "count_a", "column": "entity_id"}],
          "explicit_joins": [{"join_type": "inner", "from_table": "count_a", "to_table": "count_b",
                              "conditions": [{"left": {"table": "count_a", "column": "entity_id"}, "op": "=",
                                              "right": {"table": "count_b", "column": "entity_id"}}]}],
          "filters": [{"table": "count_a", "column": "count_a", "op": ">",
                       "value_ref": {"table": "count_b", "column": "count_b"}}]}
    r = V("owners whose pets consumed more distinct brands than the owner purchased.",
          ft.COUNT_DISTINCT_COMPARISON, ex)
    assert r["valid"], r
    print("[P2] Q17 count_distinct comparison -> accepted")


def test_pass_derived_aggregate():
    cte = {"name": "owners_totals", "from_table": "owners",
           "joins": [{"from_table": "owners", "from_column": "owner_id",
                      "to_table": "purchases", "to_column": "owner_id"}],
           "select": [{"table": "owners", "column": "owner_id", "alias": "entity_id"},
                      {"table": "owners", "column": "city", "alias": "group_col"}],
           "aggregations": [{"function": "SUM", "table": "purchases", "column": "quantity", "alias": "agg_value"}],
           "group_by": [{"table": "owners", "column": "owner_id"}, {"table": "owners", "column": "city"}]}
    ex = {"derived_relations": [cte], "main_from": "owners_totals",
          "top_per_group": [{"table": "owners_totals",
                             "partition_by": [{"table": "owners_totals", "column": "group_col"}],
                             "order_by": {"table": "owners_totals", "column": "agg_value", "direction": "desc"},
                             "rank": 1}]}
    r = V("owners with the highest total quantity for each city including ties.",
          ft.DERIVED_AGGREGATE_CTE, ex)
    assert r["valid"], r
    print("[P3] Q20 derived_aggregate CTE + top_per_group -> accepted")


def test_pass_set_division():
    ex = {"tables": ["foods"],
          "select": [{"table": "foods", "column": "brand"}],
          "set_division": [{"group_by": [{"table": "foods", "column": "brand"}],
                            "left": {"function": "COUNT", "distinct": True, "table": "foods", "column": "species_target"},
                            "op": "=",
                            "right_subquery": {"function": "COUNT", "distinct": True, "table": "pets", "column": "species"}}]}
    r = V("Find brands that have food for all species represented in pets.",
          ft.SET_DIVISION_COUNT_DISTINCT, ex)
    assert r["valid"], r
    print("[P4] Q23 set_division (species coverage) -> accepted")


def test_pass_self_join_pairs():
    ex = {"aliases": [{"alias": "p1", "table": "pets"}, {"alias": "p2", "table": "pets"},
                      {"alias": "l1", "table": "pet_likes"}, {"alias": "l2", "table": "pet_likes"}],
          "alias_joins": [{"from": {"alias": "p1", "column": "pet_address"}, "op": "=",
                           "to": {"alias": "p2", "column": "pet_address"}},
                          {"from": {"alias": "p1", "column": "owner_id"}, "op": "<>",
                           "to": {"alias": "p2", "column": "owner_id"}},
                          {"from": {"alias": "p1", "column": "pet_id"}, "op": "<",
                           "to": {"alias": "p2", "column": "pet_id"}}],
          "alias_filters": [{"left": {"alias": "l1", "column": "preferred_brand"}, "op": "=",
                             "right": {"alias": "l2", "column": "preferred_brand"}}],
          "alias_select": [{"alias": "p1", "column": "pet_id"}, {"alias": "p2", "column": "pet_id"}]}
    r = V("pairs of pets from different owners with the same address and same preferred brand.",
          ft.SELF_JOIN_PAIR, ex)
    assert r["valid"], r
    print("[P5] Q43 self_join pairs (pets, address+brand) -> accepted")


def test_pass_min_max():
    base = {"name": "base_items", "from_table": "owners",
            "joins": [{"from_table": "owners", "from_column": "owner_id", "to_table": "purchases", "to_column": "owner_id"},
                      {"from_table": "purchases", "from_column": "food_id", "to_table": "foods", "to_column": "food_id"}],
            "select": [{"table": "owners", "column": "owner_id", "alias": "entity_id"},
                       {"table": "foods", "column": "food_type", "alias": "group_col"},
                       {"table": "foods", "column": "price", "alias": "value_col"}],
            "aggregations": [], "group_by": []}
    ex = {"derived_relations": [base], "aliases": [{"alias": "low", "table": "base_items"}], "distinct": True}
    r = V("Find food types where the same owner both purchased the cheapest and the most expensive food of that type.",
          ft.MIN_MAX_SAME_ENTITY_PER_GROUP, ex)
    assert r["valid"], r
    print("[P6] Q49 min_max (purchases path) -> accepted")


def test_pass_clinic_pairs():
    ex = {"aliases": [{"alias": "p1", "table": "patients"}, {"alias": "p2", "table": "patients"},
                      {"alias": "a1", "table": "appointments"}, {"alias": "a2", "table": "appointments"}],
          "alias_joins": [{"from": {"alias": "p1", "column": "city"}, "op": "=", "to": {"alias": "p2", "column": "city"}},
                          {"from": {"alias": "p1", "column": "patient_id"}, "op": "<", "to": {"alias": "p2", "column": "patient_id"}}],
          "alias_filters": [{"left": {"alias": "a1", "column": "doctor_id"}, "op": "=", "right": {"alias": "a2", "column": "doctor_id"}},
                            {"left": {"alias": "a1", "column": "appt_date"}, "op": "<>", "right": {"alias": "a2", "column": "appt_date"}}],
          "alias_select": [{"alias": "p1", "column": "patient_id"}, {"alias": "p2", "column": "patient_id"}]}
    r = V("pairs of patients in the same city who saw the same doctor on different appointment dates.",
          ft.SELF_JOIN_PAIR, ex, CLINIC)
    assert r["valid"], r  # 'different dates' must NOT demand COUNT(DISTINCT)
    print("[P7] Clinic pairs (same doctor, different dates) -> accepted (not count-distinct)")


# ---------------------------------------------------------------------------
# SHOULD FAIL
# ---------------------------------------------------------------------------
def test_fail_wrong_outer_join():
    ex = {"select": [{"table": "pet_likes", "column": "like_id"}],
          "explicit_joins": [{"join_type": "left", "from_table": "pet_likes", "to_table": "pets",
                              "conditions": [{"left": {"table": "pet_likes", "column": "pet_id"}, "op": "=",
                                              "right": {"table": "pets", "column": "pet_id"}}]}]}
    r = V("List all pet owners and their pets who do not live at the same address, "
          "using an outer join so owners without pets are still visible.",
          ft.OUTER_JOIN_NULL, ex)
    assert not r["valid"], r
    print("[F1] Q2 wrong outer join -> rejected:", r["reasons"][:2])


def test_fail_wrong_mismatch():
    ex = {"tables": ["owners", "purchases", "foods", "pets"],
          "select": [{"table": "owners", "column": "owner_id"}],
          "filters": [{"table": "foods", "column": "food_type", "op": "!=",
                       "value_ref": {"table": "pet_likes", "column": "food_type"}}]}
    r = V("Find owners who bought food for a species they do not own.", ft.MISMATCH_COMPARISON, ex)
    assert not r["valid"] and any("species" in x for x in r["reasons"]), r
    print("[F2] Q6 mismatch on food_type not species -> rejected")


def test_fail_wrong_pairs():
    ex = {"aliases": [{"alias": "l1", "table": "pet_likes"}, {"alias": "l2", "table": "pet_likes"}],
          "alias_joins": [{"from": {"alias": "l1", "column": "flavor"}, "op": "=", "to": {"alias": "l2", "column": "flavor"}}],
          "alias_select": [{"alias": "l1", "column": "like_id"}]}
    r = V("List pet-food pairs where the pet loves the food's flavor and food_type.", ft.SELF_JOIN_PAIR, ex)
    assert not r["valid"] and any("pair" in x.lower() for x in r["reasons"]), r
    print("[F3] Q22 pairs aliased over pet_likes not pets -> rejected")


def test_fail_shallow_outer_join():
    ex = {"select": [{"table": "owners", "column": "owner_id"}, {"table": "pets", "column": "pet_id"}],
          "explicit_joins": [{"join_type": "left", "from_table": "owners", "to_table": "pets",
                              "conditions": [{"left": {"table": "owners", "column": "owner_id"}, "op": "=",
                                              "right": {"table": "pets", "column": "owner_id"}}]}]}
    r = V("List owners, pets, and loved food profiles where an outer join shows no "
          "matching purchased food by brand, food_type, and flavor.", ft.OUTER_JOIN_NULL, ex)
    assert not r["valid"] and any("brand" in x or "flavor" in x for x in r["reasons"]), r
    print("[F4] Q50 shallow outer join (brand/type/flavor absent) -> rejected")


def test_fail_clinic_top_missing_absence():
    ex = {"tables": ["invoices"],
          "select": [{"table": "invoices", "column": "patient_id"}],
          "top_per_group": [{"table": "invoices",
                             "partition_by": [{"table": "invoices", "column": "invoice_id"}],
                             "order_by": {"table": "invoices", "column": "total", "direction": "desc"},
                             "rank": 1}]}
    r = V("patient with the highest total invoice who was never prescribed a medication.",
          ft.TOP_PER_GROUP, ex, CLINIC)
    assert not r["valid"] and any("absence" in x for x in r["reasons"]), r
    print("[F5] Clinic top-per-group missing 'never prescribed' NOT EXISTS -> rejected")


def test_fail_cyber_pairs_no_aliases():
    ex = {"tables": ["devices"], "select": [{"table": "devices", "column": "device_id"}]}
    r = V("List pairs of devices with the same risk score.", ft.SELF_JOIN_PAIR, ex, CYBER)
    assert not r["valid"] and any("alias" in x for x in r["reasons"]), r
    print("[F6] Cyber pairs of devices but no aliases -> rejected")


def test_fail_illegal_join_id_measure():
    # count_distinct CTE joins pets.pet_id = purchases.quantity (key = measure)
    ex = {"derived_relations": [{"name": "c", "from_table": "pets",
            "joins": [{"from_table": "pets", "from_column": "pet_id",
                       "to_table": "purchases", "to_column": "quantity"}],
            "select": [{"table": "pets", "column": "pet_id", "alias": "entity_id"}],
            "aggregations": [{"function": "COUNT", "distinct": True, "table": "foods",
                              "column": "brand", "alias": "c"}],
            "group_by": [{"table": "pets", "column": "pet_id"}]}],
          "select": [{"table": "c", "column": "entity_id"}]}
    r = V("count distinct brands per pet", ft.COUNT_DISTINCT_COMPARISON, ex)
    assert not r["valid"] and any("illegal join" in x for x in r["reasons"]), r
    print("[F7] illegal join pets.pet_id = purchases.quantity -> rejected")


def test_fail_illegal_join_days_supply_lab():
    ex = {"derived_relations": [{"name": "c", "from_table": "doctors",
            "joins": [{"from_table": "prescriptions", "from_column": "days_supply",
                       "to_table": "lab_results", "to_column": "lab_id"}],
            "select": [{"table": "doctors", "column": "doctor_id", "alias": "entity_id"}],
            "aggregations": [{"function": "COUNT", "distinct": True, "table": "lab_results",
                              "column": "test_name", "alias": "c"}],
            "group_by": [{"table": "doctors", "column": "doctor_id"}]}],
          "select": [{"table": "c", "column": "entity_id"}]}
    r = V("count distinct tests", ft.COUNT_DISTINCT_COMPARISON, ex, CLINIC)
    assert not r["valid"] and any("illegal join" in x for x in r["reasons"]), r
    print("[F8] illegal join prescriptions.days_supply = lab_results.lab_id -> rejected")


def test_fail_illegal_correlation_measure_key():
    # universal correlation owners.annual_income = pets.pet_id (measure = key)
    ex = {"tables": ["owners"], "select": [{"table": "owners", "column": "owner_id"}],
          "universal": [{"domain_table": "pets",
                         "domain_filters": [{"left": {"table": "owners", "column": "annual_income"},
                                             "op": "=", "right": {"table": "pets", "column": "pet_id"}}],
                         "must_exist": {"target_table": "feeding_history",
                                        "where": [{"left": {"table": "feeding_history", "column": "pet_id"},
                                                   "op": "=", "right": {"table": "pets", "column": "pet_id"}}]}}]}
    r = V("every pet ...", ft.UNIVERSAL_EVERY_ALL, ex)
    assert not r["valid"] and any("illegal join" in x for x in r["reasons"]), r
    print("[F9] illegal correlation owners.annual_income = pets.pet_id -> rejected")


def test_fail_shallow_anti_exists():
    ex = {"tables": ["patients"], "select": [{"table": "patients", "column": "patient_id"}],
          "anti_exists": [{"target_table": "appointments",
                           "where": [{"left": {"table": "appointments", "column": "patient_id"},
                                      "op": "=", "right": {"table": "patients", "column": "patient_id"}}]}]}
    r = V("patients prescribed a controlled substance but with no lab result marked high.",
          ft.ANTI_EXISTS, ex, CLINIC)
    assert not r["valid"] and any("shallow" in x for x in r["reasons"]), r
    print("[F10] shallow anti_exists (ignores lab_results) -> rejected")


def test_fail_bare_derived_cte():
    cte = {"name": "owners_totals", "from_table": "owners",
           "joins": [{"from_table": "owners", "from_column": "owner_id",
                      "to_table": "purchases", "to_column": "owner_id"}],
           "select": [{"table": "owners", "column": "owner_id", "alias": "entity_id"},
                      {"table": "owners", "column": "city", "alias": "group_col"}],
           "aggregations": [{"function": "SUM", "table": "purchases", "column": "quantity", "alias": "agg_value"}],
           "group_by": [{"table": "owners", "column": "owner_id"}, {"table": "owners", "column": "city"}]}
    ex = {"derived_relations": [cte], "main_from": "owners_totals"}   # bare SELECT *
    r = V("owners whose total spending is above the average spending in their city.",
          ft.DERIVED_AGGREGATE_CTE, ex)
    assert not r["valid"] and any("bare CTE" in x for x in r["reasons"]), r
    print("[F11] bare derived CTE (no comparison/top) -> rejected")


def test_fail_two_concept_counted_same():
    # question names alert types vs courses; both sides count alert_type
    ex = {"derived_relations": [
        {"name": "count_a", "from_table": "employees",
         "joins": [{"from_table": "employees", "from_column": "employee_id", "to_table": "devices", "to_column": "employee_id"},
                   {"from_table": "devices", "from_column": "device_id", "to_table": "alerts", "to_column": "device_id"}],
         "select": [{"table": "employees", "column": "employee_id", "alias": "entity_id"}],
         "aggregations": [{"function": "COUNT", "distinct": True, "table": "alerts", "column": "alert_type", "alias": "count_a"}],
         "group_by": [{"table": "employees", "column": "employee_id"}]},
        {"name": "count_b", "from_table": "employees",
         "joins": [{"from_table": "employees", "from_column": "employee_id", "to_table": "devices", "to_column": "employee_id"},
                   {"from_table": "devices", "from_column": "device_id", "to_table": "alerts", "to_column": "device_id"}],
         "select": [{"table": "employees", "column": "employee_id", "alias": "entity_id"}],
         "aggregations": [{"function": "COUNT", "distinct": True, "table": "alerts", "column": "alert_type", "alias": "count_b"}],
         "group_by": [{"table": "employees", "column": "employee_id"}]}],
        "select": [{"table": "count_a", "column": "entity_id"}],
        "explicit_joins": [{"join_type": "inner", "from_table": "count_a", "to_table": "count_b",
                            "conditions": [{"left": {"table": "count_a", "column": "entity_id"}, "op": "=",
                                            "right": {"table": "count_b", "column": "entity_id"}}]}],
        "filters": [{"table": "count_a", "column": "count_a", "op": ">", "value_ref": {"table": "count_b", "column": "count_b"}}]}
    r = V("employees whose devices triggered more distinct alert types than the number "
          "of distinct courses they passed.", ft.COUNT_DISTINCT_COMPARISON, ex, CYBER_TRAIN)
    assert not r["valid"] and any("two distinct concepts" in x for x in r["reasons"]), r
    print("[F12] two concepts (alert types vs courses) counted the same -> rejected")


def main():
    tests = [
        test_pass_top_per_group, test_pass_count_distinct, test_pass_derived_aggregate,
        test_pass_set_division, test_pass_self_join_pairs, test_pass_min_max,
        test_pass_clinic_pairs,
        test_fail_wrong_outer_join, test_fail_wrong_mismatch, test_fail_wrong_pairs,
        test_fail_shallow_outer_join, test_fail_clinic_top_missing_absence,
        test_fail_cyber_pairs_no_aliases,
        test_fail_illegal_join_id_measure, test_fail_illegal_join_days_supply_lab,
        test_fail_illegal_correlation_measure_key, test_fail_shallow_anti_exists,
        test_fail_bare_derived_cte, test_fail_two_concept_counted_same,
    ]
    passed = 0
    for t in tests:
        t(); passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed -- family_guard verified")


if __name__ == "__main__":
    main()
