# SpiderSQL 2-Database SQL Debug Results

## clinic_multiple_csv DB 29 Q01

**Question:** List patients whose latest appointment was cancelled but who have at least one unpaid invoice from an earlier appointment.

**Status:** EXEC_OK | rows=14 | source=llm | family=latest_earliest_per_entity | conf=0.72 | guard=None | time=9.274s

**Reason:** latest/earliest per entity (implicit)

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": false,
  "has_having": false,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT DISTINCT "patients"."patient_id", "patients"."patient_name" FROM "appointments" INNER JOIN "invoices" ON "appointments"."appointment_id" = "invoices"."appointment_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id"
```

## clinic_multiple_csv DB 29 Q02

**Question:** Find doctors who treated patients from a different city and whose average invoice total is higher than the average invoice total for doctors in the same specialty.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=5.137s

**Reason:** no distinctive relational pattern; use base pipeline

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": true,
  "has_having": true,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT "doctors"."specialty", "doctors"."doctor_id", "doctors"."doctor_name", AVG("invoices"."total_amount") AS "avg_invoice" FROM "appointments" INNER JOIN "doctors" ON "appointments"."doctor_id" = "doctors"."doctor_id" INNER JOIN "invoices" ON "appointments"."appointment_id" = "invoices"."appointment_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id" WHERE "patients"."city" != ? GROUP BY "doctors"."doctor_id", "doctors"."doctor_name", "doctors"."specialty" HAVING "avg_invoice" > "specialty_avg_invoice"
```

## clinic_multiple_csv DB 29 Q03

**Question:** List patients who were prescribed a controlled substance but have no lab result marked high for the appointment where it was prescribed.

**Status:** EXEC_OK | rows=0 | source=llm | family=anti_exists | conf=0.8 | guard=False | time=3.058s

**Reason:** absence check (NOT EXISTS)

**Guard reasons:**
- anti_exists is too shallow: mentioned table(s) ['lab_results'] not represented (positive evidence / absence concept ignored)

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": false,
  "has_having": false,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": true,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT DISTINCT "patients"."patient_id", "patients"."patient_name" FROM "appointments" INNER JOIN "lab_results" ON "appointments"."appointment_id" = "lab_results"."appointment_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id" INNER JOIN "prescriptions" ON "appointments"."appointment_id" = "prescriptions"."appointment_id" INNER JOIN "medications" ON "prescriptions"."medication_id" = "medications"."medication_id" WHERE "medications"."controlled_substance" = ? AND NOT EXISTS (SELECT 1 FROM "lab_results" WHERE "appointments"."appointment_id" = "lab_results"."appointment_id" AND "medications"."medication_id" = "prescriptions"."medication_id" AND "prescriptions"."appointment_id" = "appointments"."appointment_id" AND "lab_results"."result_flag" = ?)
```

## clinic_multiple_csv DB 29 Q04

**Question:** Find visit types where the same doctor handled both the lowest base fee and the highest base fee appointment of that visit type.

**Status:** EXEC_OK | rows=20 | source=query_family | family=min_max_same_entity_per_group | conf=0.95 | guard=True | time=0.019s

**Reason:** same entity has records at both the min and max within a group

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": true,
  "has_having": false,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": true
}
```

**SQL:**
```sql
WITH "base_items" AS (SELECT "doctors"."doctor_id" AS "entity_id", "appointments"."visit_type" AS "group_col", "appointments"."base_fee" AS "value_col" FROM "doctors" INNER JOIN "appointments" ON "doctors"."doctor_id" = "appointments"."doctor_id"), "group_extremes" AS (SELECT "base_items"."group_col" AS "group_col", MIN("base_items"."value_col") AS "min_value", MAX("base_items"."value_col") AS "max_value" FROM "base_items" GROUP BY "base_items"."group_col") SELECT DISTINCT "low"."group_col" AS "group_col", "low"."entity_id" AS "entity_id" FROM "base_items" AS "low" INNER JOIN "base_items" AS "high" ON "low"."entity_id" = "high"."entity_id" AND "low"."group_col" = "high"."group_col" INNER JOIN "group_extremes" AS "g" ON "low"."group_col" = "g"."group_col" WHERE "low"."value_col" = "g"."min_value" AND "high"."value_col" = "g"."max_value"
```

## clinic_multiple_csv DB 29 Q05

**Question:** List medications that were prescribed to patients with chronic conditions but never prescribed during urgent visits.

**Status:** EXEC_FAIL | rows=None | source=llm | family=anti_exists | conf=0.8 | guard=False | time=4.068s

**Reason:** absence check (NOT EXISTS)

**Guard reasons:**
- anti_exists is too shallow: mentioned table(s) ['patients'] not represented (positive evidence / absence concept ignored)

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": false,
  "has_having": false,
  "has_inner_join": false,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**Error:** success=false but no explicit error field found

**SQL:**
```sql
-- NO SQL GENERATED
```

## clinic_multiple_csv DB 29 Q06

**Question:** Find patients whose total unpaid invoice amount is greater than the total amount paid by insurance for their completed appointments.

**Status:** EXEC_OK | rows=14 | source=llm | family=derived_aggregate_cte | conf=0.85 | guard=None | time=4.479s

**Reason:** per-entity aggregate total then ranked/compared (derived relation)

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": true,
  "has_having": true,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT "patients"."patient_id", "patients"."patient_name", SUM("invoices"."total_amount") AS "total_unpaid", SUM("invoices"."insurance_paid") AS "total_insurance_paid" FROM "appointments" INNER JOIN "invoices" ON "appointments"."appointment_id" = "invoices"."appointment_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id" WHERE "appointments"."status" = ? GROUP BY "patients"."patient_id", "patients"."patient_name" HAVING "total_unpaid" > "total_insurance_paid"
```

## clinic_multiple_csv DB 29 Q07

**Question:** List doctors who have appointments with every insurance provider represented in the patients table.

**Status:** EXEC_OK | rows=15 | source=query_family | family=universal_every_all | conf=0.82 | guard=True | time=0.018s

**Reason:** for-all via nested NOT EXISTS

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": false,
  "has_having": false,
  "has_inner_join": false,
  "has_left_join": false,
  "has_not_exists": true,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT DISTINCT "doctors"."doctor_id" FROM "doctors" WHERE NOT EXISTS (SELECT 1 FROM "appointments" WHERE "appointments"."doctor_id" = "doctors"."doctor_id" AND NOT EXISTS (SELECT 1 FROM "patients" WHERE "patients"."patient_id" = "appointments"."patient_id"))
```

## clinic_multiple_csv DB 29 Q08

**Question:** Find patients whose prescription days_supply is higher than every other prescription for the same medication class.

**Status:** EXEC_FAIL | rows=0 | source=llm | family=universal_every_all | conf=0.82 | guard=None | time=3.358s

**Reason:** for-all via nested NOT EXISTS

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": false,
  "has_having": false,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": true,
  "has_null_filter": false,
  "has_self_alias_hint": true,
  "has_with_cte": false
}
```

**Error:** no such column: prescriptions__g0.medication_class

**SQL:**
```sql
SELECT "patients"."patient_id", "patients"."patient_name" FROM "prescriptions" INNER JOIN "appointments" ON "prescriptions"."appointment_id" = "appointments"."appointment_id" INNER JOIN "medications" ON "prescriptions"."medication_id" = "medications"."medication_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id" WHERE NOT EXISTS (SELECT 1 FROM "prescriptions" AS "prescriptions__g0" WHERE "prescriptions__g0"."medication_class" = "medications"."medication_class" AND "prescriptions__g0"."days_supply" > "prescriptions"."days_supply")
```

## clinic_multiple_csv DB 29 Q09

**Question:** List pairs of patients in the same city who saw the same doctor on different appointment dates.

**Status:** EXEC_OK | rows=360 | source=query_family | family=self_join_pair | conf=0.9 | guard=True | time=0.017s

**Reason:** compares two rows of the same table (pairs)

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": false,
  "has_having": false,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": true,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT "p1"."patient_id" AS "id_1", "p2"."patient_id" AS "id_2" FROM "patients" AS "p1" INNER JOIN "patients" AS "p2" ON "p1"."city" = "p2"."city" AND "p1"."patient_id" < "p2"."patient_id" INNER JOIN "appointments" AS "l1_appointments" ON "p1"."patient_id" = "l1_appointments"."patient_id" INNER JOIN "appointments" AS "l2_appointments" ON "p2"."patient_id" = "l2_appointments"."patient_id" WHERE "l1_appointments"."doctor_id" = "l2_appointments"."doctor_id" AND "l1_appointments"."appointment_id" != "l2_appointments"."appointment_id"
```

## clinic_multiple_csv DB 29 Q10

**Question:** Find appointments where the patient city is different from the doctor clinic city and the invoice is unpaid.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=3.471s

**Reason:** no distinctive relational pattern; use base pipeline

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": false,
  "has_having": false,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT "appointments"."appointment_id" FROM "appointments" INNER JOIN "doctors" ON "appointments"."doctor_id" = "doctors"."doctor_id" INNER JOIN "invoices" ON "appointments"."appointment_id" = "invoices"."appointment_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id" WHERE "patients"."city" != ? AND "invoices"."payment_status" = ?
```

## clinic_multiple_csv DB 29 Q11

**Question:** List medications where the most expensive medication in each class was never prescribed, but a cheaper medication from the same class was prescribed.

**Status:** EXEC_OK | rows=5 | source=llm | family=top_per_group | conf=0.82 | guard=False | time=5.612s

**Reason:** extremum of a raw column within a group

**Guard reasons:**
- absence intent but no anti_exists/universal/null structure

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": true,
  "has_having": true,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": true,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT "medications"."medication_class", "medications"."medication_name", MAX("medications"."unit_cost") AS "max_cost", MIN("medications"."unit_cost") AS "min_cost" FROM "medications" INNER JOIN "prescriptions" ON "medications"."medication_id" = "prescriptions"."medication_id" WHERE NOT EXISTS (SELECT 1 FROM "prescriptions" WHERE "medications"."medication_id" = "prescriptions"."medication_id" AND "medications"."medication_class" = "medications"."medication_class" AND "medications"."unit_cost" = ?) GROUP BY "medications"."medication_class" HAVING "max_cost" > "min_cost"
```

## clinic_multiple_csv DB 29 Q12

**Question:** Find patients who had a low lab result after receiving a prescription with refill allowed.

**Status:** EXEC_OK | rows=7 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=3.681s

**Reason:** no distinctive relational pattern; use base pipeline

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": false,
  "has_having": false,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT DISTINCT "patients"."patient_id", "patients"."patient_name" FROM "appointments" INNER JOIN "lab_results" ON "appointments"."appointment_id" = "lab_results"."appointment_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id" INNER JOIN "prescriptions" ON "appointments"."appointment_id" = "prescriptions"."appointment_id" WHERE "lab_results"."result_flag" = ? AND "prescriptions"."refill_allowed" = ?
```

## clinic_multiple_csv DB 29 Q13

**Question:** List doctors whose patients had more distinct abnormal lab test names than the number of distinct medication classes they prescribed.

**Status:** EXEC_OK | rows=5 | source=query_family | family=count_distinct_comparison | conf=0.8 | guard=True | time=0.018s

**Reason:** more/fewer distinct X than Y

**Flags:**
```json
{
  "has_count_distinct": true,
  "has_group_by": true,
  "has_having": false,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": true
}
```

**SQL:**
```sql
WITH "count_a" AS (SELECT "doctors"."doctor_id" AS "entity_id", COUNT(DISTINCT "lab_results"."test_name") AS "count_a" FROM "doctors" INNER JOIN "appointments" ON "doctors"."doctor_id" = "appointments"."doctor_id" INNER JOIN "lab_results" ON "appointments"."appointment_id" = "lab_results"."appointment_id" GROUP BY "doctors"."doctor_id"), "count_b" AS (SELECT "doctors"."doctor_id" AS "entity_id", COUNT(DISTINCT "lab_results"."test_name") AS "count_b" FROM "doctors" INNER JOIN "appointments" ON "doctors"."doctor_id" = "appointments"."doctor_id" INNER JOIN "prescriptions" ON "appointments"."appointment_id" = "prescriptions"."appointment_id" INNER JOIN "lab_results" ON "prescriptions"."days_supply" = "lab_results"."lab_id" GROUP BY "doctors"."doctor_id") SELECT "count_a"."entity_id" FROM "count_a" INNER JOIN "count_b" ON "count_a"."entity_id" = "count_b"."entity_id" WHERE "count_a"."count_a" > "count_b"."count_b"
```

## clinic_multiple_csv DB 29 Q14

**Question:** Find patients who have appointments but have never received a prescription for any medication class marked controlled substance.

**Status:** EXEC_OK | rows=7 | source=llm | family=anti_exists | conf=0.8 | guard=False | time=6.693s

**Reason:** absence check (NOT EXISTS)

**Guard reasons:**
- anti_exists is too shallow: mentioned table(s) ['medications', 'prescriptions'] not represented (positive evidence / absence concept ignored)

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": false,
  "has_having": false,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": true,
  "has_null_filter": true,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT DISTINCT "patients"."patient_id", "patients"."patient_name" FROM "appointments" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id" INNER JOIN "prescriptions" ON "appointments"."appointment_id" = "prescriptions"."appointment_id" INNER JOIN "medications" ON "prescriptions"."medication_id" = "medications"."medication_id" WHERE "appointments"."patient_id" IS NOT NULL AND NOT EXISTS (SELECT 1 FROM "prescriptions" INNER JOIN "medications" ON "prescriptions"."medication_id" = "medications"."medication_id" WHERE "appointments"."appointment_id" = "prescriptions"."appointment_id" AND "appointments"."patient_id" = "patients"."patient_id" AND "medications"."controlled_substance" = ?)
```

## clinic_multiple_csv DB 29 Q15

**Question:** List the highest total invoice patient for each city, including ties.

**Status:** EXEC_OK | rows=20 | source=query_family | family=derived_aggregate_cte | conf=0.85 | guard=True | time=0.019s

**Reason:** per-entity aggregate total then ranked/compared (derived relation)

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": true,
  "has_having": false,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": true,
  "has_null_filter": false,
  "has_self_alias_hint": true,
  "has_with_cte": true
}
```

**SQL:**
```sql
WITH "invoices_totals" AS (SELECT "invoices"."invoice_id" AS "entity_id", "doctors"."clinic_city" AS "group_col", SUM("appointments"."base_fee") AS "agg_value" FROM "invoices" INNER JOIN "appointments" ON "invoices"."appointment_id" = "appointments"."appointment_id" INNER JOIN "doctors" ON "appointments"."doctor_id" = "doctors"."doctor_id" GROUP BY "invoices"."invoice_id", "doctors"."clinic_city") SELECT * FROM "invoices_totals" WHERE NOT EXISTS (SELECT 1 FROM "invoices_totals" AS "invoices_totals__g0" WHERE "invoices_totals__g0"."group_col" = "invoices_totals"."group_col" AND "invoices_totals__g0"."agg_value" > "invoices_totals"."agg_value")
```

## clinic_multiple_csv DB 29 Q16

**Question:** Find patients whose latest lab result was high and whose doctor for that appointment has less than five years of experience.

**Status:** EXEC_OK | rows=3 | source=llm | family=latest_earliest_per_entity | conf=0.72 | guard=None | time=5.509s

**Reason:** latest/earliest per entity (implicit)

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": false,
  "has_having": false,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": true,
  "has_null_filter": false,
  "has_self_alias_hint": true,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT DISTINCT "patients"."patient_id", "patients"."patient_name" FROM "appointments" INNER JOIN "doctors" ON "appointments"."doctor_id" = "doctors"."doctor_id" INNER JOIN "lab_results" ON "appointments"."appointment_id" = "lab_results"."appointment_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id" WHERE "lab_results"."result_flag" = ? AND "doctors"."years_experience" < ? AND NOT EXISTS (SELECT 1 FROM "lab_results" AS "lab_results__g0" WHERE "lab_results__g0"."appointment_id" = "lab_results"."appointment_id" AND "lab_results__g0"."result_date" > "lab_results"."result_date")
```

## clinic_multiple_csv DB 29 Q17

**Question:** List appointments with no prescription but with at least one lab result and an unpaid invoice.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=6.504s

**Reason:** no distinctive relational pattern; use base pipeline

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": true,
  "has_having": true,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": true,
  "has_null_filter": true,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT "appointments"."appointment_id", COUNT(*) AS "prescription_count" FROM "appointments" INNER JOIN "invoices" ON "appointments"."appointment_id" = "invoices"."appointment_id" INNER JOIN "lab_results" ON "appointments"."appointment_id" = "lab_results"."appointment_id" INNER JOIN "prescriptions" ON "appointments"."appointment_id" = "prescriptions"."appointment_id" WHERE "lab_results"."appointment_id" IS NOT NULL AND "invoices"."payment_status" = ? AND NOT EXISTS (SELECT 1 FROM "prescriptions" WHERE "appointments"."appointment_id" = "prescriptions"."appointment_id") GROUP BY "appointments"."appointment_id" HAVING "prescription_count" = ?
```

## clinic_multiple_csv DB 29 Q18

**Question:** Find doctors who have treated all visit types represented in the appointments table.

**Status:** EXEC_OK | rows=0 | source=llm | family=set_division_count_distinct | conf=0.85 | guard=None | time=6.337s

**Reason:** has/contains ALL members of a set (count-distinct division)

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": true,
  "has_having": true,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT "doctors"."doctor_id", "doctors"."doctor_name", COUNT(*) AS "visit_type_count" FROM "appointments" INNER JOIN "doctors" ON "appointments"."doctor_id" = "doctors"."doctor_id" GROUP BY "doctors"."doctor_id", "doctors"."doctor_name" HAVING "visit_type_count" = "total_visit_types"
```

## clinic_multiple_csv DB 29 Q19

**Question:** List patients who were prescribed the same medication class by two different doctors.

**Status:** EXEC_OK | rows=0 | source=llm | family=self_join_pair | conf=0.6 | guard=None | time=5.152s

**Reason:** two rows of the same entity compared by an attribute

**Flags:**
```json
{
  "has_count_distinct": true,
  "has_group_by": true,
  "has_having": true,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT "medications"."medication_class", "patients"."patient_id", "patients"."patient_name", COUNT(DISTINCT "doctors"."doctor_id") AS "doctor_count" FROM "appointments" INNER JOIN "doctors" ON "appointments"."doctor_id" = "doctors"."doctor_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id" INNER JOIN "prescriptions" ON "appointments"."appointment_id" = "prescriptions"."appointment_id" INNER JOIN "medications" ON "prescriptions"."medication_id" = "medications"."medication_id" GROUP BY "patients"."patient_id", "patients"."patient_name", "medications"."medication_class" HAVING "doctor_count" >= ?
```

## clinic_multiple_csv DB 29 Q20

**Question:** Find medication classes where patients with chronic conditions received more prescriptions than patients without chronic conditions.

**Status:** EXEC_FAIL | rows=None | source=llm | family=outer_join_null | conf=0.75 | guard=None | time=12.734s

**Reason:** include unmatched rows via outer join + null test

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": false,
  "has_having": false,
  "has_inner_join": false,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**Error:** success=false but no explicit error field found

**SQL:**
```sql
-- NO SQL GENERATED
```

## cybersecurity_incidents_schema DB 30 Q01

**Question:** List employees whose devices have unresolved critical alerts but who have no passed security training record.

**Status:** EXEC_FAIL | rows=None | source=llm | family=anti_exists | conf=0.8 | guard=False | time=7.602s

**Reason:** absence check (NOT EXISTS)

**Guard reasons:**
- anti_exists is too shallow: mentioned table(s) ['alerts', 'training_records'] not represented (positive evidence / absence concept ignored)

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": false,
  "has_having": false,
  "has_inner_join": false,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**Error:** success=false but no explicit error field found

**SQL:**
```sql
-- NO SQL GENERATED
```

## cybersecurity_incidents_schema DB 30 Q02

**Question:** Find device types where the same employee owns both the most vulnerable and least vulnerable device of that type by vulnerability count.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=3.971s

**Reason:** no distinctive relational pattern; use base pipeline

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": true,
  "has_having": false,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": true,
  "has_null_filter": false,
  "has_self_alias_hint": true,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT "devices"."employee_id", "devices"."device_type", COUNT(*) AS "vuln_count" FROM "devices" INNER JOIN "device_vulnerabilities" ON "devices"."device_id" = "device_vulnerabilities"."device_id" WHERE NOT EXISTS (SELECT 1 FROM "devices" AS "devices__g0" WHERE "devices__g0"."device_type" = "devices"."device_type" AND "devices__g0"."device_type" < "devices"."device_type") GROUP BY "devices"."device_type", "devices"."employee_id"
```

## cybersecurity_incidents_schema DB 30 Q03

**Question:** List devices with vulnerabilities that have an exploit available but no incident has been linked to any alert from that device.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=4.676s

**Reason:** no distinctive relational pattern; use base pipeline

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": false,
  "has_having": false,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": true,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT DISTINCT "devices"."device_id", "devices"."hostname" FROM "devices" INNER JOIN "alerts" ON "devices"."device_id" = "alerts"."device_id" INNER JOIN "device_vulnerabilities" ON "devices"."device_id" = "device_vulnerabilities"."device_id" INNER JOIN "incident_alerts" ON "alerts"."alert_id" = "incident_alerts"."alert_id" INNER JOIN "incidents" ON "incident_alerts"."incident_id" = "incidents"."incident_id" INNER JOIN "vulnerabilities" ON "device_vulnerabilities"."vulnerability_id" = "vulnerabilities"."vulnerability_id" WHERE "vulnerabilities"."exploit_available" = ? AND NOT EXISTS (SELECT 1 FROM "incidents" INNER JOIN "alerts" ON "devices"."device_id" = "alerts"."device_id" INNER JOIN "incident_alerts" ON "alerts"."alert_id" = "incident_alerts"."alert_id" WHERE "incident_alerts"."incident_id" = "incidents"."incident_id")
```

## cybersecurity_incidents_schema DB 30 Q04

**Question:** Find departments whose employees have devices affected by all severity levels represented in the vulnerabilities table.

**Status:** EXEC_OK | rows=0 | source=llm | family=set_division_count_distinct | conf=0.85 | guard=None | time=5.186s

**Reason:** has/contains ALL members of a set (count-distinct division)

**Flags:**
```json
{
  "has_count_distinct": true,
  "has_group_by": true,
  "has_having": true,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT "employees"."department", COUNT(DISTINCT "vulnerabilities"."severity") AS "dept_severity_count" FROM "devices" INNER JOIN "device_vulnerabilities" ON "devices"."device_id" = "device_vulnerabilities"."device_id" INNER JOIN "employees" ON "devices"."employee_id" = "employees"."employee_id" INNER JOIN "vulnerabilities" ON "device_vulnerabilities"."vulnerability_id" = "vulnerabilities"."vulnerability_id" GROUP BY "employees"."department" HAVING "dept_severity_count" = "total_severity_count"
```

## cybersecurity_incidents_schema DB 30 Q05

**Question:** List employees whose average device risk score is above the average risk score of employees in their own department.

**Status:** EXEC_FAIL | rows=None | source=llm | family=derived_aggregate_cte | conf=0.85 | guard=False | time=9.728s

**Reason:** per-entity aggregate total then ranked/compared (derived relation)

**Guard reasons:**
- derived_aggregate is a bare CTE (SELECT *) but the question asks a comparison/extremum

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": false,
  "has_having": false,
  "has_inner_join": false,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**Error:** success=false but no explicit error field found

**SQL:**
```sql
-- NO SQL GENERATED
```

## cybersecurity_incidents_schema DB 30 Q06

**Question:** Find vulnerabilities that appear on more distinct operating system families than the number of distinct departments with trained employees.

**Status:** EXEC_OK | rows=0 | source=query_family | family=count_distinct_comparison | conf=0.8 | guard=True | time=0.019s

**Reason:** more/fewer distinct X than Y

**Flags:**
```json
{
  "has_count_distinct": true,
  "has_group_by": true,
  "has_having": false,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": true
}
```

**SQL:**
```sql
WITH "count_a" AS (SELECT "device_vulnerabilities"."device_vulnerability_id" AS "entity_id", COUNT(DISTINCT "devices"."os_family") AS "count_a" FROM "device_vulnerabilities" INNER JOIN "devices" ON "device_vulnerabilities"."device_id" = "devices"."device_id" INNER JOIN "employees" ON "devices"."employee_id" = "employees"."employee_id" GROUP BY "device_vulnerabilities"."device_vulnerability_id"), "count_b" AS (SELECT "device_vulnerabilities"."device_vulnerability_id" AS "entity_id", COUNT(DISTINCT "devices"."os_family") AS "count_b" FROM "device_vulnerabilities" INNER JOIN "devices" ON "device_vulnerabilities"."device_id" = "devices"."device_id" INNER JOIN "alerts" ON "devices"."device_id" = "alerts"."device_id" GROUP BY "device_vulnerabilities"."device_vulnerability_id") SELECT "count_a"."entity_id" FROM "count_a" INNER JOIN "count_b" ON "count_a"."entity_id" = "count_b"."entity_id" WHERE "count_a"."count_a" > "count_b"."count_b"
```

## cybersecurity_incidents_schema DB 30 Q07

**Question:** List pairs of devices owned by different employees in the same office city that share the same CVE code.

**Status:** EXEC_OK | rows=0 | source=query_family | family=self_join_pair | conf=0.9 | guard=True | time=0.027s

**Reason:** compares two rows of the same table (pairs)

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": false,
  "has_having": false,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": true,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT "p1"."device_id" AS "id_1", "p2"."device_id" AS "id_2" FROM "devices" AS "p1" INNER JOIN "devices" AS "p2" ON "p1"."employee_id" != "p2"."employee_id" AND "p1"."device_id" < "p2"."device_id" INNER JOIN "employees" AS "l1_employees" ON "p1"."employee_id" = "l1_employees"."employee_id" INNER JOIN "employees" AS "l2_employees" ON "p2"."employee_id" = "l2_employees"."employee_id" WHERE "l1_employees"."office_city" = "l2_employees"."office_city"
```

## cybersecurity_incidents_schema DB 30 Q08

**Question:** Find employees who opened incidents after their device's last patch date but before their latest unresolved alert time.

**Status:** EXEC_OK | rows=0 | source=llm | family=latest_earliest_per_entity | conf=0.72 | guard=None | time=5.331s

**Reason:** latest/earliest per entity (implicit)

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": true,
  "has_having": false,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT DISTINCT "employees"."employee_id", "employees"."employee_name", MAX("alerts"."alert_time") AS "latest_unresolved_alert_time" FROM "employees" INNER JOIN "devices" ON "employees"."employee_id" = "devices"."employee_id" INNER JOIN "alerts" ON "devices"."device_id" = "alerts"."device_id" INNER JOIN "incidents" ON "employees"."employee_id" = "incidents"."opened_by_employee_id" WHERE "incidents"."opened_time" > "devices"."last_patch_date" AND "incidents"."opened_time" < ? GROUP BY "employees"."employee_id", "employees"."employee_name"
```

## cybersecurity_incidents_schema DB 30 Q09

**Question:** List devices that have never had a false positive vulnerability record but have at least one unresolved alert.

**Status:** EXEC_FAIL | rows=None | source=llm | family=anti_exists | conf=0.8 | guard=False | time=5.277s

**Reason:** absence check (NOT EXISTS)

**Guard reasons:**
- anti_exists is too shallow: mentioned table(s) ['vulnerabilities', 'alerts'] not represented (positive evidence / absence concept ignored)

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": false,
  "has_having": false,
  "has_inner_join": false,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**Error:** success=false but no explicit error field found

**SQL:**
```sql
-- NO SQL GENERATED
```

## cybersecurity_incidents_schema DB 30 Q10

**Question:** Find incident types where the highest impact incident was opened by an employee with no encrypted device.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=7.12s

**Reason:** no distinctive relational pattern; use base pipeline

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": true,
  "has_having": false,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": true,
  "has_null_filter": false,
  "has_self_alias_hint": true,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT DISTINCT "incidents"."incident_type", MAX("incidents"."business_impact") AS "max_impact" FROM "employees" INNER JOIN "devices" ON "employees"."employee_id" = "devices"."employee_id" INNER JOIN "incidents" ON "employees"."employee_id" = "incidents"."opened_by_employee_id" WHERE "employees"."employee_id" = ? AND "devices"."employee_id" = ? AND "devices"."encrypted" = ? AND NOT EXISTS (SELECT 1 FROM "incidents" AS "incidents__g0" WHERE "incidents__g0"."incident_type" = "incidents"."incident_type" AND "incidents__g0"."business_impact" > "incidents"."business_impact") GROUP BY "incidents"."incident_type"
```

## cybersecurity_incidents_schema DB 30 Q11

**Question:** List employees whose manager has a lower risk score but whose devices have higher average CVSS score than the manager's devices.

**Status:** EXEC_FAIL | rows=None | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=11.032s

**Reason:** no distinctive relational pattern; use base pipeline

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": false,
  "has_having": false,
  "has_inner_join": false,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**Error:** success=false but no explicit error field found

**SQL:**
```sql
-- NO SQL GENERATED
```

## cybersecurity_incidents_schema DB 30 Q12

**Question:** Find devices whose latest alert is unresolved and whose vulnerability with the highest CVSS score has not been remediated.

**Status:** EXEC_FAIL | rows=0 | source=llm | family=latest_earliest_per_entity | conf=0.72 | guard=None | time=10.069s

**Reason:** latest/earliest per entity (implicit)

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": true,
  "has_having": true,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": true,
  "has_null_filter": true,
  "has_self_alias_hint": true,
  "has_with_cte": false
}
```

**Error:** no such column: device_vulnerabilities__g1.cvss_score

**SQL:**
```sql
SELECT "devices"."device_id", "devices"."hostname", MAX("vulnerabilities"."cvss_score") AS "max_cvss" FROM "devices" INNER JOIN "alerts" ON "devices"."device_id" = "alerts"."device_id" INNER JOIN "device_vulnerabilities" ON "devices"."device_id" = "device_vulnerabilities"."device_id" INNER JOIN "vulnerabilities" ON "device_vulnerabilities"."vulnerability_id" = "vulnerabilities"."vulnerability_id" WHERE "alerts"."resolved" = ? AND NOT EXISTS (SELECT 1 FROM "device_vulnerabilities" WHERE "devices"."device_id" = "device_vulnerabilities"."device_id" AND "device_vulnerabilities"."remediated_date" IS NOT NULL) AND NOT EXISTS (SELECT 1 FROM "alerts" AS "alerts__g0" WHERE "alerts__g0"."device_id" = "devices"."device_id" AND "alerts__g0"."alert_time" > "alerts"."alert_time") AND NOT EXISTS (SELECT 1 FROM "device_vulnerabilities" AS "device_vulnerabilities__g1" WHERE "device_vulnerabilities__g1"."device_id" = "devices"."device_id" AND "device_vulnerabilities__g1"."cvss_score" > "vulnerabilities"."cvss_score") GROUP BY "devices"."device_id", "devices"."hostname" HAVING "max_cvss" IS NOT NULL
```

## cybersecurity_incidents_schema DB 30 Q13

**Question:** List employees who have devices with all vulnerability severities but have not passed every security training course.

**Status:** EXEC_OK | rows=0 | source=llm | family=set_division_count_distinct | conf=0.85 | guard=None | time=8.039s

**Reason:** has/contains ALL members of a set (count-distinct division)

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": true,
  "has_having": true,
  "has_inner_join": false,
  "has_left_join": true,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT "employees"."employee_id", "employees"."employee_name", COUNT("vulnerabilities"."vulnerability_id") AS "distinct_severities", COUNT("training_records"."training_id") AS "passed_courses", COUNT("training_records"."training_id") AS "total_courses" FROM "employees" LEFT JOIN "devices" ON "employees"."employee_id" = "devices"."employee_id" LEFT JOIN "device_vulnerabilities" ON "devices"."device_id" = "device_vulnerabilities"."device_id" LEFT JOIN "training_records" ON "employees"."employee_id" = "training_records"."employee_id" LEFT JOIN "vulnerabilities" ON "device_vulnerabilities"."vulnerability_id" = "vulnerabilities"."vulnerability_id" GROUP BY "employees"."employee_id", "employees"."employee_name" HAVING "distinct_severities" = "total_severities" AND "passed_courses" < "total_courses"
```

## cybersecurity_incidents_schema DB 30 Q14

**Question:** Find office cities where every employee either has no device or has at least one encrypted device.

**Status:** EXEC_OK | rows=0 | source=llm | family=universal_every_all | conf=0.82 | guard=None | time=4.266s

**Reason:** for-all via nested NOT EXISTS

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": true,
  "has_having": true,
  "has_inner_join": false,
  "has_left_join": true,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT DISTINCT "employees"."office_city", COUNT(*) AS "total_devices", COUNT("devices"."device_id") AS "encrypted_devices" FROM "employees" LEFT JOIN "devices" ON "employees"."employee_id" = "devices"."employee_id" GROUP BY "employees"."office_city" HAVING "total_devices" = "encrypted_devices"
```

## cybersecurity_incidents_schema DB 30 Q15

**Question:** List CVE codes where the highest CVSS occurrence was never remediated but a lower CVSS occurrence was remediated.

**Status:** EXEC_FAIL | rows=None | source=llm | family=anti_exists | conf=0.8 | guard=None | time=6.938s

**Reason:** absence check (NOT EXISTS)

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": false,
  "has_having": false,
  "has_inner_join": false,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**Error:** success=false but no explicit error field found

**SQL:**
```sql
-- NO SQL GENERATED
```

## cybersecurity_incidents_schema DB 30 Q16

**Question:** Find employees whose devices triggered more distinct alert types than the number of distinct courses they passed.

**Status:** EXEC_OK | rows=0 | source=query_family | family=count_distinct_comparison | conf=0.8 | guard=True | time=0.019s

**Reason:** more/fewer distinct X than Y

**Flags:**
```json
{
  "has_count_distinct": true,
  "has_group_by": true,
  "has_having": false,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": true
}
```

**SQL:**
```sql
WITH "count_a" AS (SELECT "employees"."employee_id" AS "entity_id", COUNT(DISTINCT "alerts"."alert_type") AS "count_a" FROM "employees" INNER JOIN "devices" ON "employees"."employee_id" = "devices"."employee_id" INNER JOIN "alerts" ON "devices"."device_id" = "alerts"."device_id" GROUP BY "employees"."employee_id"), "count_b" AS (SELECT "employees"."employee_id" AS "entity_id", COUNT(DISTINCT "training_records"."course_name") AS "count_b" FROM "employees" INNER JOIN "training_records" ON "employees"."employee_id" = "training_records"."employee_id" GROUP BY "employees"."employee_id") SELECT "count_a"."entity_id" FROM "count_a" INNER JOIN "count_b" ON "count_a"."entity_id" = "count_b"."entity_id" WHERE "count_a"."count_a" > "count_b"."count_b"
```

## cybersecurity_incidents_schema DB 30 Q17

**Question:** List incidents whose alerts come from devices owned by employees in a different office city than the employee who opened the incident.

**Status:** EXEC_FAIL | rows=None | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=5.264s

**Reason:** no distinctive relational pattern; use base pipeline

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": false,
  "has_having": false,
  "has_inner_join": false,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**Error:** success=false but no explicit error field found

**SQL:**
```sql
-- NO SQL GENERATED
```

## cybersecurity_incidents_schema DB 30 Q18

**Question:** Find devices with no vulnerabilities but with at least one high severity alert.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=5.724s

**Reason:** no distinctive relational pattern; use base pipeline

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": true,
  "has_having": true,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": true,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT "devices"."device_id", "devices"."hostname", COUNT(*) AS "vuln_count", COUNT(*) AS "alert_count" FROM "devices" INNER JOIN "alerts" ON "devices"."device_id" = "alerts"."device_id" INNER JOIN "device_vulnerabilities" ON "devices"."device_id" = "device_vulnerabilities"."device_id" WHERE "alerts"."severity" = ? AND NOT EXISTS (SELECT 1 FROM "device_vulnerabilities" WHERE "devices"."device_id" = "device_vulnerabilities"."device_id") GROUP BY "devices"."device_id", "devices"."hostname" HAVING "vuln_count" = ? AND "alert_count" >= ?
```

## cybersecurity_incidents_schema DB 30 Q19

**Question:** List employees where every device they own has been patched after all vulnerabilities on that device were detected.

**Status:** EXEC_OK | rows=0 | source=llm | family=set_division_count_distinct | conf=0.85 | guard=None | time=4.75s

**Reason:** has/contains ALL members of a set (count-distinct division)

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": false,
  "has_having": false,
  "has_inner_join": true,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT DISTINCT "employees"."employee_id", "employees"."employee_name" FROM "devices" INNER JOIN "device_vulnerabilities" ON "devices"."device_id" = "device_vulnerabilities"."device_id" INNER JOIN "employees" ON "devices"."employee_id" = "employees"."employee_id" INNER JOIN "vulnerabilities" ON "device_vulnerabilities"."vulnerability_id" = "vulnerabilities"."vulnerability_id"
```

## cybersecurity_incidents_schema DB 30 Q20

**Question:** Find departments where the same manager supervises both the highest risk and lowest risk employee in that department.

**Status:** EXEC_OK | rows=0 | source=llm | family=min_max_same_entity_per_group | conf=0.9 | guard=None | time=4.337s

**Reason:** same entity has records at both the min and max within a group

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": true,
  "has_having": true,
  "has_inner_join": false,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT "employees"."department", MAX("employees"."risk_score") AS "max_risk", MIN("employees"."risk_score") AS "min_risk", MAX("employees"."manager_id") AS "max_risk_manager", MIN("employees"."manager_id") AS "min_risk_manager" FROM "employees" GROUP BY "employees"."department" HAVING "max_risk_manager" = "min_risk_manager"
```
