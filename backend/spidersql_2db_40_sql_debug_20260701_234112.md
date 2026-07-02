# SpiderSQL 2-Database SQL Debug Results

## clinic_multiple_csv DB 29 Q01

**Question:** List patients whose latest appointment was cancelled but who have at least one unpaid invoice from an earlier appointment.

**Status:** EXEC_OK | rows=11 | source=llm | family=latest_earliest_per_entity | conf=0.72 | guard=None | time=20.957s

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

**GOLD: WRONG level=none gold_rows=3 gen_rows=11**

**Candidates:**
```text
SELECTED: llm_primary (reason=consensus_group, candidates=4)
  - llm_primary: score=87.0 executed=True rows=11 fatal=False
      note: checklist column 'invoices.payment_status' is never used
      note: literal 'unpaid' from the question is missing
  - llm_variant_1: score=86.0 executed=True rows=7 fatal=False
      note: checklist requires shape 'comparison_subquery' but the SQL lacks it
  - llm_variant_2: score=87.0 executed=True rows=11 fatal=False
      note: checklist column 'invoices.payment_status' is never used
      note: literal 'unpaid' from the question is missing
  - llm_sql_direct: score=100.0 executed=True rows=1 fatal=False
```

**SQL:**
```sql
SELECT DISTINCT "patients"."patient_id", "patients"."patient_name" FROM "appointments" INNER JOIN "invoices" ON "appointments"."appointment_id" = "invoices"."appointment_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id" WHERE NOT EXISTS (SELECT 1 FROM "invoices" WHERE "appointments"."appointment_id" = "invoices"."appointment_id" AND "appointments"."appointment_id" = "appointments"."appointment_id" AND "appointments"."status" = ?) AND NOT EXISTS (SELECT 1 FROM "appointments" AS "appointments__g0" WHERE "appointments__g0"."patient_id" = "appointments"."patient_id" AND "appointments__g0"."appointment_date" > "appointments"."appointment_date")
```

## clinic_multiple_csv DB 29 Q02

**Question:** Find doctors who treated patients from a different city and whose average invoice total is higher than the average invoice total for doctors in the same specialty.

**Status:** EXEC_OK | rows=3 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=35.562s

**Reason:** no distinctive relational pattern; use base pipeline

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

**GOLD: WRONG level=none gold_rows=0 gen_rows=3**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=best_scored_executed, candidates=3)
  - llm_primary: score=0.0 executed=False rows=None fatal=False
      note: no SQL produced (invalid IR / unresolved plan / generation failure)
      note: concept 'city' mentioned in the question but no matching column is used
  - llm_variant_2: score=57.0 executed=True rows=0 fatal=True
      FATAL: required concept 'doctors.clinic_city' named in the question is missing from the SQL
      FATAL: required concept 'patients.city' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: concept 'city' mentioned in the question but no matching column is used
      note: checklist requires shape 'comparison_subquery' but the SQL lacks it
  - llm_sql_direct: score=100.0 executed=True rows=3 fatal=False
```

**SQL:**
```sql
SELECT d.doctor_id, d.doctor_name
FROM doctors d
JOIN appointments a ON d.doctor_id = a.doctor_id
JOIN patients p ON a.patient_id = p.patient_id
JOIN invoices i ON a.appointment_id = i.appointment_id
WHERE p.city != d.clinic_city
GROUP BY d.doctor_id, d.doctor_name
HAVING AVG(i.total_amount) > (
    SELECT AVG(i2.total_amount)
    FROM doctors d2
    JOIN appointments a2 ON d2.doctor_id = a2.doctor_id
    JOIN invoices i2 ON a2.appointment_id = i2.appointment_id
    WHERE d2.specialty = d.specialty
)
```

## clinic_multiple_csv DB 29 Q03

**Question:** List patients who were prescribed a controlled substance but have no lab result marked high for the appointment where it was prescribed.

**Status:** EXEC_OK | rows=0 | source=llm | family=anti_exists | conf=0.8 | guard=False | time=17.572s

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

**GOLD: WRONG level=none gold_rows=7 gen_rows=0**

**Candidates:**
```text
SELECTED: llm_primary (reason=consensus_group, candidates=4)
  - query_family: score=20.0 executed=True rows=56 fatal=True
      FATAL: family guard rejected this output
      FATAL: required concept 'medications.controlled_substance' named in the question is missing from the SQL
      note: question names table 'lab_results' but the candidate never uses it
      note: family guard rejected this output: anti_exists is too shallow: mentioned table(s) ['lab_results'] not represented (positive evidence / absence concept ignored)
      note: checklist table 'prescriptions' is never used
  - llm_primary: score=100.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
  - llm_variant_1: score=100.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: literal 'high' from the question is missing
  - llm_sql_direct: score=73.0 executed=True rows=10 fatal=True
      FATAL: illegal join: patients.patient_id = prescriptions.appointment_id
      note: illegal join/correlation patients.patient_id = prescriptions.appointment_id (not a declared FK; e.g. key = measure)
```

**SQL:**
```sql
SELECT DISTINCT "patients"."patient_id", "patients"."patient_name" FROM "appointments" INNER JOIN "lab_results" ON "appointments"."appointment_id" = "lab_results"."appointment_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id" INNER JOIN "prescriptions" ON "appointments"."appointment_id" = "prescriptions"."appointment_id" INNER JOIN "medications" ON "prescriptions"."medication_id" = "medications"."medication_id" WHERE "medications"."controlled_substance" = ? AND NOT EXISTS (SELECT 1 FROM "lab_results" WHERE "appointments"."appointment_id" = "lab_results"."appointment_id" AND "appointments"."appointment_id" = "prescriptions"."appointment_id" AND "lab_results"."result_flag" = ?)
```

## clinic_multiple_csv DB 29 Q04

**Question:** Find visit types where the same doctor handled both the lowest base fee and the highest base fee appointment of that visit type.

**Status:** EXEC_OK | rows=20 | source=query_family | family=min_max_same_entity_per_group | conf=0.95 | guard=True | time=13.773s

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

**GOLD: WRONG level=none gold_rows=4 gen_rows=20**

**Candidates:**
```text
SELECTED: query_family (reason=best_scored_executed, candidates=3)
  - query_family: score=100.0 executed=True rows=20 fatal=False
  - llm_primary: score=72.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: question names table 'doctors' but the candidate never uses it
      note: checklist requires shape 'window_or_cte' but the SQL lacks it
  - llm_sql_direct: score=90.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: question names table 'doctors' but the candidate never uses it
```

**SQL:**
```sql
WITH "base_items" AS (SELECT "doctors"."doctor_id" AS "entity_id", "appointments"."visit_type" AS "group_col", "appointments"."base_fee" AS "value_col" FROM "doctors" INNER JOIN "appointments" ON "doctors"."doctor_id" = "appointments"."doctor_id"), "group_extremes" AS (SELECT "base_items"."group_col" AS "group_col", MIN("base_items"."value_col") AS "min_value", MAX("base_items"."value_col") AS "max_value" FROM "base_items" GROUP BY "base_items"."group_col") SELECT DISTINCT "low"."group_col" AS "group_col", "low"."entity_id" AS "entity_id" FROM "base_items" AS "low" INNER JOIN "base_items" AS "high" ON "low"."entity_id" = "high"."entity_id" AND "low"."group_col" = "high"."group_col" INNER JOIN "group_extremes" AS "g" ON "low"."group_col" = "g"."group_col" WHERE "low"."value_col" = "g"."min_value" AND "high"."value_col" = "g"."max_value"
```

## clinic_multiple_csv DB 29 Q05

**Question:** List medications that were prescribed to patients with chronic conditions but never prescribed during urgent visits.

**Status:** EXEC_OK | rows=14 | source=llm | family=anti_exists | conf=0.8 | guard=False | time=14.315s

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
  "has_not_exists": true,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**GOLD: OK level=gen_subset gold_rows=14 gen_rows=14**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=best_scored_executed, candidates=3)
  - query_family: score=15.0 executed=True rows=0 fatal=True
      FATAL: family guard rejected this output
      FATAL: required concept 'medications.medication_name' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: question names table 'patients' but the candidate never uses it
      note: family guard rejected this output: anti_exists is too shallow: mentioned table(s) ['patients'] not represented (positive evidence / absence concept ignored)
  - llm_primary: score=0.0 executed=False rows=None fatal=False
      note: no SQL produced (invalid IR / unresolved plan / generation failure)
      note: absence intent ('never/no/not ...') but no NOT EXISTS / NOT IN / LEFT JOIN+IS NULL
  - llm_sql_direct: score=100.0 executed=True rows=14 fatal=False
```

**SQL:**
```sql
SELECT DISTINCT m.medication_name
FROM medications m
JOIN prescriptions p ON m.medication_id = p.medication_id
JOIN appointments a ON p.appointment_id = a.appointment_id
JOIN patients pat ON a.patient_id = pat.patient_id
WHERE pat.chronic_condition = 'yes'
AND NOT EXISTS (
    SELECT 1
    FROM prescriptions p2
    JOIN appointments a2 ON p2.appointment_id = a2.appointment_id
    WHERE p2.medication_id = m.medication_id
    AND a2.visit_type = 'urgent'
)
```

## clinic_multiple_csv DB 29 Q06

**Question:** Find patients whose total unpaid invoice amount is greater than the total amount paid by insurance for their completed appointments.

**Status:** EXEC_OK | rows=14 | source=llm | family=derived_aggregate_cte | conf=0.85 | guard=None | time=19.469s

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

**GOLD: OK level=subset gold_rows=14 gen_rows=14**

**Candidates:**
```text
SELECTED: llm_primary (reason=consensus_group, candidates=3)
  - llm_primary: score=95.0 executed=True rows=14 fatal=False
      note: checklist requires shape 'comparison_subquery' but the SQL lacks it
  - llm_variant_1: score=95.0 executed=True rows=14 fatal=False
      note: checklist requires shape 'comparison_subquery' but the SQL lacks it
  - llm_sql_direct: score=100.0 executed=True rows=14 fatal=False
```

**SQL:**
```sql
SELECT "patients"."patient_id", "patients"."patient_name", SUM("invoices"."total_amount") AS "total_unpaid", SUM("invoices"."insurance_paid") AS "total_insurance_paid" FROM "appointments" INNER JOIN "invoices" ON "appointments"."appointment_id" = "invoices"."appointment_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id" WHERE "appointments"."status" = ? GROUP BY "patients"."patient_id", "patients"."patient_name" HAVING "total_unpaid" > "total_insurance_paid"
```

## clinic_multiple_csv DB 29 Q07

**Question:** List doctors who have appointments with every insurance provider represented in the patients table.

**Status:** EXEC_OK | rows=0 | source=llm | family=universal_every_all | conf=0.82 | guard=True | time=15.057s

**Reason:** for-all via nested NOT EXISTS

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

**GOLD: WRONG level=none gold_rows=5 gen_rows=0**

**Candidates:**
```text
SELECTED: llm_variant (reason=best_scored_executed, candidates=4)
  - query_family: score=72.0 executed=True rows=15 fatal=True
      FATAL: required concept 'patients.insurance_provider' named in the question is missing from the SQL
      note: checklist requires shape 'group_by_having' but the SQL lacks it
      note: checklist column 'patients.insurance_provider' is never used
  - llm_primary: score=91.0 executed=True rows=0 fatal=True
      FATAL: required concept 'patients.insurance_provider' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: checklist column 'patients.insurance_provider' is never used
  - llm_variant_1: score=100.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
  - llm_sql_direct: score=100.0 executed=True rows=5 fatal=False
```

**SQL:**
```sql
SELECT "doctors"."doctor_id", "doctors"."doctor_name", COUNT("patients"."insurance_provider") AS "ins_count" FROM "appointments" INNER JOIN "doctors" ON "appointments"."doctor_id" = "doctors"."doctor_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id" GROUP BY "doctors"."doctor_id", "doctors"."doctor_name" HAVING "ins_count" = ?
```

## clinic_multiple_csv DB 29 Q08

**Question:** Find patients whose prescription days_supply is higher than every other prescription for the same medication class.

**Status:** EXEC_OK | rows=7 | source=llm | family=universal_every_all | conf=0.82 | guard=None | time=17.711s

**Reason:** for-all via nested NOT EXISTS

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

**GOLD: WRONG level=none gold_rows=0 gen_rows=7**

**Candidates:**
```text
SELECTED: llm_variant (reason=best_scored_executed, candidates=4)
  - llm_primary: score=40.0 executed=False rows=None fatal=False
      note: execution failed: no such column: prescriptions__g0.medication_class
  - llm_variant_1: score=0.0 executed=False rows=None fatal=False
      note: no SQL produced (invalid IR / unresolved plan / generation failure)
      note: referenced column does not exist: prescriptions.patient_id
      note: question names table 'patients' but the candidate never uses it
  - llm_variant_2: score=42.0 executed=True rows=7 fatal=True
      FATAL: required concept 'prescriptions.days_supply' named in the question is missing from the SQL
      FATAL: required concept 'medications.medication_class' named in the question is missing from the SQL
      note: checklist requires shape 'comparison_subquery' but the SQL lacks it
      note: checklist measure column 'prescriptions.days_supply' is never used
      note: checklist column 'prescriptions.days_supply' is never used
  - llm_sql_direct: score=40.0 executed=False rows=None fatal=False
      note: execution failed: no such column: pr.patient_id
  WARNING: all executed candidates failed hard semantic checks; low confidence
  WARNING: selected candidate failed hard semantic checks: required concept 'prescriptions.days_supply' named in the question is missing from the SQL; required concept 'medications.medication_class' named in the question is missing from the SQL
```

**SQL:**
```sql
SELECT DISTINCT "patients"."patient_id", "patients"."patient_name" FROM "prescriptions" INNER JOIN "appointments" ON "prescriptions"."appointment_id" = "appointments"."appointment_id" INNER JOIN "medications" ON "prescriptions"."medication_id" = "medications"."medication_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id"
```

## clinic_multiple_csv DB 29 Q09

**Question:** List pairs of patients in the same city who saw the same doctor on different appointment dates.

**Status:** EXEC_OK | rows=50 | source=llm | family=self_join_pair | conf=0.9 | guard=True | time=22.619s

**Reason:** compares two rows of the same table (pairs)

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

**GOLD: WRONG level=none gold_rows=18 gen_rows=50**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=best_scored_executed, candidates=4)
  - query_family: score=71.0 executed=True rows=360 fatal=True
      FATAL: required concept 'appointments.appointment_date' named in the question is missing from the SQL
      note: question names table 'doctors' but the candidate never uses it
      note: checklist table 'doctors' is never used
      note: checklist column 'appointments.appointment_date' is never used
  - llm_primary: score=63.0 executed=True rows=140 fatal=True
      FATAL: required concept 'patients.city' named in the question is missing from the SQL
      note: question names table 'doctors' but the candidate never uses it
      note: concept 'city' mentioned in the question but no matching column is used
      note: checklist table 'doctors' is never used
  - llm_variant_1: score=57.0 executed=True rows=578 fatal=True
      FATAL: required concept 'appointments.doctor_id' named in the question is missing from the SQL
      FATAL: required concept 'appointments.appointment_date' named in the question is missing from the SQL
      note: checklist table 'appointments' is never used
      note: checklist table 'doctors' is never used
      note: checklist column 'appointments.doctor_id' is never used
  - llm_sql_direct: score=100.0 executed=True rows=50 fatal=False
```

**SQL:**
```sql
SELECT DISTINCT p1.patient_id, p1.patient_name, p1.city, d.doctor_name
FROM patients p1
JOIN patients p2 ON p1.city = p2.city AND p1.patient_id < p2.patient_id
JOIN appointments a1 ON p1.patient_id = a1.patient_id
JOIN appointments a2 ON p2.patient_id = a2.patient_id
JOIN doctors d ON a1.doctor_id = d.doctor_id
WHERE a1.doctor_id = a2.doctor_id
  AND a1.appointment_date != a2.appointment_date
```

## clinic_multiple_csv DB 29 Q10

**Question:** Find appointments where the patient city is different from the doctor clinic city and the invoice is unpaid.

**Status:** EXEC_OK | rows=34 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=16.588s

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

**GOLD: OK level=strict gold_rows=34 gen_rows=34**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=best_scored_executed, candidates=2)
  - llm_primary: score=83.0 executed=True rows=0 fatal=True
      FATAL: required concept 'doctors.clinic_city' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: checklist column 'doctors.clinic_city' is never used
  - llm_sql_direct: score=100.0 executed=True rows=34 fatal=False
```

**SQL:**
```sql
SELECT a.appointment_id
FROM appointments a
JOIN doctors d ON a.doctor_id = d.doctor_id
JOIN patients p ON a.patient_id = p.patient_id
JOIN invoices i ON a.appointment_id = i.appointment_id
WHERE p.city != d.clinic_city
  AND i.payment_status = 'unpaid'
```

## clinic_multiple_csv DB 29 Q11

**Question:** List medications where the most expensive medication in each class was never prescribed, but a cheaper medication from the same class was prescribed.

**Status:** EXEC_OK | rows=0 | source=llm | family=top_per_group | conf=0.82 | guard=False | time=25.387s

**Reason:** extremum of a raw column within a group

**Guard reasons:**
- absence intent but no anti_exists/universal/null structure

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": true,
  "has_having": false,
  "has_inner_join": false,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": true
}
```

**GOLD: OK level=subset gold_rows=0 gen_rows=0 (both empty — weak)**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=best_scored_executed, candidates=4)
  - query_family: score=57.0 executed=True rows=5 fatal=True
      FATAL: family guard rejected this output
      note: top-per-group intent but no window function / CTE / correlated aggregate
      note: family guard rejected this output: absence intent but no anti_exists/universal/null structure
      note: checklist requires shape 'window_or_cte' but the SQL lacks it
  - llm_primary: score=9.0 executed=True rows=100 fatal=True
      FATAL: required concept 'medications.medication_class' named in the question is missing from the SQL
      note: absence intent ('never/no/not ...') but no NOT EXISTS / NOT IN / LEFT JOIN+IS NULL
      note: top-per-group intent but no window function / CTE / correlated aggregate
      note: checklist requires shape 'window_or_cte' but the SQL lacks it
  - llm_variant_1: score=0.0 executed=False rows=None fatal=False
      note: no SQL produced (invalid IR / unresolved plan / generation failure)
      note: referenced column does not exist: medications.max_cost_in_class
      note: absence intent ('never/no/not ...') but no NOT EXISTS / NOT IN / LEFT JOIN+IS NULL
  - llm_sql_direct: score=100.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
```

**SQL:**
```sql
WITH prescribed_classes AS (
    SELECT DISTINCT m.medication_class
    FROM medications m
    JOIN prescriptions p ON m.medication_id = p.medication_id
),
max_costs AS (
    SELECT 
        m.medication_class,
        MAX(m.unit_cost) AS max_unit_cost
    FROM medications m
    JOIN prescribed_classes pc ON m.medication_class = pc.medication_class
    GROUP BY m.medication_class
),
cheaper_prescribed AS (
    SELECT DISTINCT m.medication_class
    FROM medications m
    JOIN prescriptions p ON m.medication_id = p.medication_id
    JOIN max_costs mc ON m.medication_class = mc.medication_class
    WHERE m.unit_cost < mc.max_unit_cost
),
most_expensive AS (
    SELECT m.medication_id, m.medication_name, m.medication_class, m.unit_cost
    FROM medications m
    JOIN max_costs mc ON m.medication_class = mc.medication_class AND m.unit_cost = mc.max_unit_cost
)
SELECT me.medication_id, me.medication_name, me.medication_class, me.unit_cost
FROM most_expensive me
WHERE me.medication_id NOT IN (
    SELECT p.medication_id
    FROM prescriptions p
)
AND me.medication_class IN (SELECT medication_class FROM cheaper_prescribed)
```

## clinic_multiple_csv DB 29 Q12

**Question:** Find patients who had a low lab result after receiving a prescription with refill allowed.

**Status:** EXEC_OK | rows=7 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=14.594s

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

**GOLD: OK level=strict gold_rows=7 gen_rows=7**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=consensus_group, candidates=3)
  - llm_primary: score=98.0 executed=True rows=7 fatal=False
  - llm_variant_2: score=86.0 executed=True rows=7 fatal=False
      note: literal 'true' is not among the sampled values of column 'refill_allowed' (known: ['no', 'yes'])
  - llm_sql_direct: score=98.0 executed=True rows=7 fatal=False
```

**SQL:**
```sql
SELECT DISTINCT p.patient_id, p.patient_name
FROM patients p
JOIN appointments a ON p.patient_id = a.patient_id
JOIN lab_results l ON a.appointment_id = l.appointment_id
JOIN prescriptions pr ON a.appointment_id = pr.appointment_id
WHERE l.result_flag = 'low'
  AND pr.refill_allowed = 'yes'
```

## clinic_multiple_csv DB 29 Q13

**Question:** List doctors whose patients had more distinct abnormal lab test names than the number of distinct medication classes they prescribed.

**Status:** EXEC_OK | rows=5 | source=llm | family=count_distinct_comparison | conf=0.8 | guard=True | time=16.753s

**Reason:** more/fewer distinct X than Y

**Flags:**
```json
{
  "has_count_distinct": true,
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

**GOLD: OK level=strict gold_rows=5 gen_rows=5**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=best_scored_executed, candidates=4)
  - query_family: score=51.0 executed=True rows=5 fatal=True
      FATAL: required concept 'medications.medication_class' named in the question is missing from the SQL
      note: question names table 'patients' but the candidate never uses it
      note: question names table 'medications' but the candidate never uses it
      note: checklist table 'medications' is never used
  - llm_primary: score=64.0 executed=True rows=5 fatal=False
      note: question names table 'patients' but the candidate never uses it
      note: checklist requires shape 'comparison_subquery' but the SQL lacks it
      note: literal 'high' from the question is missing
  - llm_variant_1: score=40.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: question names table 'patients' but the candidate never uses it
      note: distinct-count intent but no COUNT(DISTINCT)
  - llm_sql_direct: score=82.0 executed=True rows=5 fatal=False
      note: question names table 'patients' but the candidate never uses it
      note: checklist requires shape 'comparison_subquery' but the SQL lacks it
```

**SQL:**
```sql
SELECT d.doctor_id, d.doctor_name
FROM doctors d
JOIN appointments a ON d.doctor_id = a.doctor_id
JOIN lab_results l ON a.appointment_id = l.appointment_id
JOIN prescriptions p ON a.appointment_id = p.appointment_id
JOIN medications m ON p.medication_id = m.medication_id
WHERE l.result_flag IN ('high', 'low', 'critical')
GROUP BY d.doctor_id, d.doctor_name
HAVING COUNT(DISTINCT l.test_name) > COUNT(DISTINCT m.medication_class)
```

## clinic_multiple_csv DB 29 Q14

**Question:** Find patients who have appointments but have never received a prescription for any medication class marked controlled substance.

**Status:** EXEC_OK | rows=7 | source=llm | family=anti_exists | conf=0.8 | guard=False | time=14.991s

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
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**GOLD: WRONG level=none gold_rows=7 gen_rows=7**

**Candidates:**
```text
SELECTED: llm_primary (reason=consensus_group, candidates=4)
  - query_family: score=30.0 executed=True rows=56 fatal=True
      FATAL: family guard rejected this output
      FATAL: required concept 'medications.controlled_substance' named in the question is missing from the SQL
      note: question names table 'prescriptions' but the candidate never uses it
      note: question names table 'medications' but the candidate never uses it
      note: family guard rejected this output: anti_exists is too shallow: mentioned table(s) ['medications', 'prescriptions'] not represented (positive evidence / absence concept ignored)
  - llm_primary: score=100.0 executed=True rows=7 fatal=False
      note: literal 'yes' from the question is missing
  - llm_variant_1: score=100.0 executed=True rows=7 fatal=False
      note: literal 'yes' from the question is missing
  - llm_sql_direct: score=100.0 executed=True rows=7 fatal=False
```

**SQL:**
```sql
SELECT DISTINCT "patients"."patient_id", "patients"."patient_name" FROM "appointments" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id" INNER JOIN "prescriptions" ON "appointments"."appointment_id" = "prescriptions"."appointment_id" INNER JOIN "medications" ON "prescriptions"."medication_id" = "medications"."medication_id" WHERE NOT EXISTS (SELECT 1 FROM "prescriptions" INNER JOIN "medications" ON "prescriptions"."medication_id" = "medications"."medication_id" WHERE "appointments"."appointment_id" = "prescriptions"."appointment_id" AND "appointments"."patient_id" = "patients"."patient_id" AND "medications"."controlled_substance" = ?)
```

## clinic_multiple_csv DB 29 Q15

**Question:** List the highest total invoice patient for each city, including ties.

**Status:** EXEC_OK | rows=4 | source=llm | family=derived_aggregate_cte | conf=0.85 | guard=True | time=18.558s

**Reason:** per-entity aggregate total then ranked/compared (derived relation)

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": true,
  "has_having": false,
  "has_inner_join": false,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": true
}
```

**GOLD: OK level=subset gold_rows=4 gen_rows=4**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=best_scored_executed, candidates=4)
  - query_family: score=47.0 executed=True rows=20 fatal=True
      FATAL: required concept 'patients.city' named in the question is missing from the SQL
      FATAL: required concept 'invoices.total_amount' named in the question is missing from the SQL
      note: question names table 'patients' but the candidate never uses it
      note: checklist measure column 'invoices.total_amount' is never used
      note: checklist table 'patients' is never used
  - llm_primary: score=8.0 executed=False rows=None fatal=False
      note: execution failed: no such column: invoices__g0.city
      note: top-per-group intent but no window function / CTE / correlated aggregate
      note: checklist requires shape 'window_or_cte' but the SQL lacks it
  - llm_variant_1: score=8.0 executed=False rows=None fatal=False
      note: execution failed: no such column: patients__g0.total_amount
      note: top-per-group intent but no window function / CTE / correlated aggregate
      note: checklist requires shape 'window_or_cte' but the SQL lacks it
  - llm_sql_direct: score=100.0 executed=True rows=4 fatal=False
```

**SQL:**
```sql
WITH city_max AS (
  SELECT 
    p.city,
    p.patient_id,
    p.patient_name,
    SUM(i.total_amount) AS total_invoice_amount,
    MAX(SUM(i.total_amount)) OVER (PARTITION BY p.city) AS max_city_amount
  FROM patients p
  JOIN appointments a ON p.patient_id = a.patient_id
  JOIN invoices i ON a.appointment_id = i.appointment_id
  GROUP BY p.city, p.patient_id, p.patient_name
)
SELECT 
  city,
  patient_id,
  patient_name
FROM city_max
WHERE total_invoice_amount = max_city_amount
ORDER BY city, patient_id
```

## clinic_multiple_csv DB 29 Q16

**Question:** Find patients whose latest lab result was high and whose doctor for that appointment has less than five years of experience.

**Status:** EXEC_OK | rows=3 | source=llm | family=latest_earliest_per_entity | conf=0.72 | guard=None | time=23.941s

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

**GOLD: WRONG level=none gold_rows=0 gen_rows=3**

**Candidates:**
```text
SELECTED: llm_primary (reason=best_scored_executed, candidates=2)
  - llm_primary: score=92.0 executed=True rows=3 fatal=False
      note: checklist requires shape 'window_or_cte' but the SQL lacks it
  - llm_sql_direct: score=40.0 executed=False rows=None fatal=False
      note: execution failed: no such column: lr.patient_id
```

**SQL:**
```sql
SELECT DISTINCT "patients"."patient_id", "patients"."patient_name" FROM "appointments" INNER JOIN "doctors" ON "appointments"."doctor_id" = "doctors"."doctor_id" INNER JOIN "lab_results" ON "appointments"."appointment_id" = "lab_results"."appointment_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id" WHERE "lab_results"."result_flag" = ? AND "doctors"."years_experience" < ? AND NOT EXISTS (SELECT 1 FROM "lab_results" AS "lab_results__g0" WHERE "lab_results__g0"."appointment_id" = "lab_results"."appointment_id" AND "lab_results__g0"."result_date" > "lab_results"."result_date")
```

## clinic_multiple_csv DB 29 Q17

**Question:** List appointments with no prescription but with at least one lab result and an unpaid invoice.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=30.281s

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

**GOLD: OK level=subset gold_rows=0 gen_rows=0 (both empty — weak)**

**Candidates:**
```text
SELECTED: llm_primary (reason=best_scored_executed, candidates=3)
  - llm_primary: score=100.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
  - llm_variant_1: score=100.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
  - llm_sql_direct: score=100.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
```

**SQL:**
```sql
SELECT "appointments"."appointment_id", COUNT("lab_results"."lab_id") AS "lab_count" FROM "appointments" INNER JOIN "invoices" ON "appointments"."appointment_id" = "invoices"."appointment_id" INNER JOIN "lab_results" ON "appointments"."appointment_id" = "lab_results"."appointment_id" INNER JOIN "prescriptions" ON "appointments"."appointment_id" = "prescriptions"."appointment_id" WHERE "invoices"."payment_status" = ? AND NOT EXISTS (SELECT 1 FROM "prescriptions" WHERE "appointments"."appointment_id" = "prescriptions"."appointment_id") GROUP BY "appointments"."appointment_id" HAVING "lab_count" >= ?
```

## clinic_multiple_csv DB 29 Q18

**Question:** Find doctors who have treated all visit types represented in the appointments table.

**Status:** EXEC_OK | rows=5 | source=llm | family=set_division_count_distinct | conf=0.85 | guard=None | time=22.365s

**Reason:** has/contains ALL members of a set (count-distinct division)

**Flags:**
```json
{
  "has_count_distinct": true,
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

**GOLD: OK level=strict gold_rows=5 gen_rows=5**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=best_scored_executed, candidates=4)
  - llm_primary: score=88.0 executed=True rows=0 fatal=True
      FATAL: required concept 'appointments.visit_type' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: checklist column 'appointments.visit_type' is never used
  - llm_variant_1: score=88.0 executed=True rows=0 fatal=True
      FATAL: required concept 'appointments.visit_type' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: checklist column 'appointments.visit_type' is never used
  - llm_variant_2: score=69.0 executed=True rows=5 fatal=True
      FATAL: required concept 'appointments.visit_type' named in the question is missing from the SQL
      note: checklist requires shape 'group_by_having' but the SQL lacks it
      note: checklist column 'appointments.visit_type' is never used
  - llm_sql_direct: score=100.0 executed=True rows=5 fatal=False
```

**SQL:**
```sql
SELECT d.doctor_id, d.doctor_name
FROM doctors d
JOIN appointments a ON d.doctor_id = a.doctor_id
GROUP BY d.doctor_id, d.doctor_name
HAVING COUNT(DISTINCT a.visit_type) = (SELECT COUNT(DISTINCT visit_type) FROM appointments)
```

## clinic_multiple_csv DB 29 Q19

**Question:** List patients who were prescribed the same medication class by two different doctors.

**Status:** EXEC_OK | rows=35 | source=llm | family=self_join_pair | conf=0.6 | guard=None | time=26.226s

**Reason:** two rows of the same entity compared by an attribute

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

**GOLD: WRONG level=none gold_rows=0 gen_rows=35**

**Candidates:**
```text
SELECTED: llm_primary (reason=best_scored_executed, candidates=2)
  - llm_primary: score=84.0 executed=True rows=35 fatal=False
      note: question names table 'doctors' but the candidate never uses it
      note: checklist table 'doctors' is never used
  - llm_sql_direct: score=61.0 executed=True rows=0 fatal=True
      FATAL: illegal join: patients.patient_id = prescriptions.appointment_id
      note: executed but returned zero rows (weak signal)
      note: illegal join/correlation patients.patient_id = prescriptions.appointment_id (not a declared FK; e.g. key = measure)
```

**SQL:**
```sql
SELECT DISTINCT "medications"."medication_class", "patients"."patient_id", "patients"."patient_name", COUNT("appointments"."doctor_id") AS "doctor_count" FROM "prescriptions" INNER JOIN "appointments" ON "prescriptions"."appointment_id" = "appointments"."appointment_id" INNER JOIN "medications" ON "prescriptions"."medication_id" = "medications"."medication_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id" GROUP BY "patients"."patient_id", "patients"."patient_name", "medications"."medication_class" HAVING "doctor_count" >= ?
```

## clinic_multiple_csv DB 29 Q20

**Question:** Find medication classes where patients with chronic conditions received more prescriptions than patients without chronic conditions.

**Status:** EXEC_OK | rows=0 | source=llm | family=outer_join_null | conf=0.75 | guard=None | time=23.771s

**Reason:** include unmatched rows via outer join + null test

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

**GOLD: OK level=strict gold_rows=0 gen_rows=0 (both empty — weak)**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=best_scored_executed, candidates=3)
  - llm_primary: score=5.0 executed=False rows=None fatal=False
      note: no SQL produced (invalid IR / unresolved plan / generation failure)
  - llm_variant_1: score=52.0 executed=True rows=0 fatal=True
      FATAL: required concept 'patients.chronic_condition' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: checklist requires shape 'comparison_subquery' but the SQL lacks it
      note: checklist measure column 'prescriptions.prescription_id' is never used
  - llm_sql_direct: score=73.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: checklist requires shape 'comparison_subquery' but the SQL lacks it
      note: checklist measure column 'prescriptions.prescription_id' is never used
```

**SQL:**
```sql
SELECT m.medication_class
FROM medications m
JOIN prescriptions p ON m.medication_id = p.medication_id
JOIN appointments a ON p.appointment_id = a.appointment_id
JOIN patients pt ON a.patient_id = pt.patient_id
GROUP BY m.medication_class
HAVING SUM(CASE WHEN pt.chronic_condition = 'yes' THEN 1 ELSE 0 END) >
       SUM(CASE WHEN pt.chronic_condition = 'no' THEN 1 ELSE 0 END)
```

## cybersecurity_incidents_schema DB 30 Q01

**Question:** List employees whose devices have unresolved critical alerts but who have no passed security training record.

**Status:** EXEC_OK | rows=0 | source=llm | family=anti_exists | conf=0.8 | guard=False | time=14.842s

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
  "has_not_exists": true,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**GOLD: OK level=strict gold_rows=1 gen_rows=1**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=best_scored_executed, candidates=4)
  - query_family: score=0.0 executed=True rows=0 fatal=True
      FATAL: family guard rejected this output
      FATAL: required concept 'alerts.resolved' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: question names table 'alerts' but the candidate never uses it
      note: question names table 'incident_alerts' but the candidate never uses it
  - llm_primary: score=0.0 executed=False rows=None fatal=False
      note: no SQL produced (invalid IR / unresolved plan / generation failure)
      note: question names table 'incident_alerts' but the candidate never uses it
      note: absence intent ('never/no/not ...') but no NOT EXISTS / NOT IN / LEFT JOIN+IS NULL
  - llm_variant_1: score=0.0 executed=False rows=None fatal=False
      note: no SQL produced (invalid IR / unresolved plan / generation failure)
      note: question names table 'incident_alerts' but the candidate never uses it
      note: absence intent ('never/no/not ...') but no NOT EXISTS / NOT IN / LEFT JOIN+IS NULL
  - llm_sql_direct: score=98.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: question names table 'incident_alerts' but the candidate never uses it
```

**SQL:**
```sql
SELECT e.employee_id, e.employee_name
FROM employees e
WHERE EXISTS (
    SELECT 1
    FROM devices d
    JOIN alerts a ON d.device_id = a.device_id
    WHERE d.employee_id = e.employee_id
      AND a.severity = 'critical'
      AND a.resolved = 'no'
)
AND NOT EXISTS (
    SELECT 1
    FROM training_records t
    WHERE t.employee_id = e.employee_id
      AND t.passed = 'yes'
)
```

## cybersecurity_incidents_schema DB 30 Q02

**Question:** Find device types where the same employee owns both the most vulnerable and least vulnerable device of that type by vulnerability count.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=29.538s

**Reason:** no distinctive relational pattern; use base pipeline

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": true,
  "has_having": false,
  "has_inner_join": false,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": true
}
```

**GOLD: WRONG level=none gold_rows=1 gen_rows=4**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=best_scored_executed, candidates=3)
  - llm_primary: score=58.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: question names table 'employees' but the candidate never uses it
      note: question names table 'vulnerabilities' but the candidate never uses it
  - llm_variant_1: score=0.0 executed=False rows=None fatal=False
      note: no SQL produced (invalid IR / unresolved plan / generation failure)
      note: question names table 'employees' but the candidate never uses it
      note: question names table 'vulnerabilities' but the candidate never uses it
  - llm_sql_direct: score=90.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: question names table 'vulnerabilities' but the candidate never uses it
```

**SQL:**
```sql
WITH device_vuln_counts AS (
    SELECT 
        d.device_id,
        d.device_type,
        e.employee_id,
        COUNT(dv.vulnerability_id) AS vuln_count
    FROM devices d
    JOIN device_vulnerabilities dv ON d.device_id = dv.device_id
    JOIN employees e ON d.employee_id = e.employee_id
    GROUP BY d.device_id, d.device_type, e.employee_id
),
ranked_devices AS (
    SELECT 
        device_id,
        device_type,
        employee_id,
        vuln_count,
        ROW_NUMBER() OVER (PARTITION BY device_type, employee_id ORDER BY vuln_count DESC) AS rn_max,
        ROW_NUMBER() OVER (PARTITION BY device_type, employee_id ORDER BY vuln_count ASC) AS rn_min
    FROM device_vuln_counts
),
extremes AS (
    SELECT 
        device_type,
        employee_id,
        MAX(CASE WHEN rn_max = 1 THEN 1 ELSE 0 END) AS has_max,
        MAX(CASE WHEN rn_min = 1 THEN 1 ELSE 0 END) AS has_min
    FROM ranked_devices
    GROUP BY device_type, employee_id
)
SELECT DISTINCT device_type
FROM extremes
WHERE has_max = 1 AND has_min = 1
```

## cybersecurity_incidents_schema DB 30 Q03

**Question:** List devices with vulnerabilities that have an exploit available but no incident has been linked to any alert from that device.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=23.407s

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

**GOLD: WRONG level=none gold_rows=20 gen_rows=0**

**Candidates:**
```text
SELECTED: llm_variant (reason=consensus_group, candidates=4)
  - llm_primary: score=90.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: question names table 'incidents' but the candidate never uses it
      note: literal 'yes' from the question is missing
  - llm_variant_1: score=90.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: question names table 'incidents' but the candidate never uses it
      note: literal 'yes' from the question is missing
  - llm_variant_2: score=100.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: literal 'yes' from the question is missing
  - llm_sql_direct: score=90.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: question names table 'incidents' but the candidate never uses it
```

**SQL:**
```sql
SELECT DISTINCT "devices"."device_id", "devices"."hostname" FROM "devices" INNER JOIN "alerts" ON "devices"."device_id" = "alerts"."device_id" INNER JOIN "device_vulnerabilities" ON "devices"."device_id" = "device_vulnerabilities"."device_id" INNER JOIN "incident_alerts" ON "alerts"."alert_id" = "incident_alerts"."alert_id" INNER JOIN "incidents" ON "incident_alerts"."incident_id" = "incidents"."incident_id" INNER JOIN "vulnerabilities" ON "device_vulnerabilities"."vulnerability_id" = "vulnerabilities"."vulnerability_id" WHERE "vulnerabilities"."exploit_available" = ? AND NOT EXISTS (SELECT 1 FROM "incidents" INNER JOIN "alerts" ON "devices"."device_id" = "alerts"."device_id" INNER JOIN "incident_alerts" ON "alerts"."alert_id" = "incident_alerts"."alert_id" WHERE "incident_alerts"."incident_id" = "incidents"."incident_id" AND "devices"."device_id" = "devices"."device_id")
```

## cybersecurity_incidents_schema DB 30 Q04

**Question:** Find departments whose employees have devices affected by all severity levels represented in the vulnerabilities table.

**Status:** EXEC_OK | rows=0 | source=llm | family=set_division_count_distinct | conf=0.85 | guard=None | time=21.266s

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

**GOLD: WRONG level=none gold_rows=4 gen_rows=0**

**Candidates:**
```text
SELECTED: llm_primary (reason=consensus_group, candidates=4)
  - llm_primary: score=100.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
  - llm_variant_1: score=100.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
  - llm_variant_2: score=85.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: checklist requires shape 'group_by_having' but the SQL lacks it
  - llm_sql_direct: score=100.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
```

**SQL:**
```sql
SELECT "employees"."department", COUNT(DISTINCT "vulnerabilities"."severity") AS "dept_severity_count" FROM "devices" INNER JOIN "device_vulnerabilities" ON "devices"."device_id" = "device_vulnerabilities"."device_id" INNER JOIN "employees" ON "devices"."employee_id" = "employees"."employee_id" INNER JOIN "vulnerabilities" ON "device_vulnerabilities"."vulnerability_id" = "vulnerabilities"."vulnerability_id" GROUP BY "employees"."department" HAVING "dept_severity_count" = "total_severity_count"
```

## cybersecurity_incidents_schema DB 30 Q05

**Question:** List employees whose average device risk score is above the average risk score of employees in their own department.

**Status:** EXEC_OK | rows=0 | source=query_family | family=derived_aggregate_cte | conf=0.85 | guard=False | time=17.521s

**Reason:** per-entity aggregate total then ranked/compared (derived relation)

**Guard reasons:**
- derived_aggregate is a bare CTE (SELECT *) but the question asks a comparison/extremum

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

**GOLD: WRONG level=none gold_rows=17 gen_rows=90**

**Candidates:**
```text
SELECTED: query_family (reason=best_scored_executed, candidates=4)
  - query_family: score=67.0 executed=True rows=0 fatal=True
      FATAL: family guard rejected this output
      FATAL: bare CTE 'device_vulnerabilities_totals' never applies the comparison
      note: executed but returned zero rows (weak signal)
      note: family guard rejected this output: derived_aggregate is a bare CTE (SELECT *) but the question asks a comparison/extremum
      note: question asks a comparison but the final SELECT just dumps CTE 'device_vulnerabilities_totals' without applying it
  - llm_primary: score=0.0 executed=False rows=None fatal=False
      note: no SQL produced (invalid IR / unresolved plan / generation failure)
      note: referenced column does not exist: devices.risk_score
      note: question names table 'device_vulnerabilities' but the candidate never uses it
  - llm_variant_1: score=0.0 executed=False rows=None fatal=False
      note: no SQL produced (invalid IR / unresolved plan / generation failure)
      note: referenced column does not exist: devices.risk_score
      note: question names table 'device_vulnerabilities' but the candidate never uses it
  - llm_sql_direct: score=28.0 executed=False rows=None fatal=False
      note: execution failed: no such column: d2.risk_score
      note: question names table 'device_vulnerabilities' but the candidate never uses it
  WARNING: all executed candidates failed hard semantic checks; low confidence
  WARNING: selected candidate failed hard semantic checks: family guard rejected this output; bare CTE 'device_vulnerabilities_totals' never applies the comparison
```

**SQL:**
```sql
WITH "device_vulnerabilities_totals" AS (SELECT "device_vulnerabilities"."device_vulnerability_id" AS "entity_id", "employees"."department" AS "group_col", AVG("employees"."risk_score") AS "agg_value" FROM "device_vulnerabilities" INNER JOIN "devices" ON "device_vulnerabilities"."device_id" = "devices"."device_id" INNER JOIN "employees" ON "devices"."employee_id" = "employees"."employee_id" GROUP BY "device_vulnerabilities"."device_vulnerability_id", "employees"."department") SELECT * FROM "device_vulnerabilities_totals"
```

## cybersecurity_incidents_schema DB 30 Q06

**Question:** Find vulnerabilities that appear on more distinct operating system families than the number of distinct departments with trained employees.

**Status:** EXEC_OK | rows=0 | source=llm | family=count_distinct_comparison | conf=0.8 | guard=True | time=23.208s

**Reason:** more/fewer distinct X than Y

**Flags:**
```json
{
  "has_count_distinct": true,
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

**GOLD: OK level=strict gold_rows=0 gen_rows=0 (both empty — weak)**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=best_scored_executed, candidates=3)
  - query_family: score=40.0 executed=True rows=0 fatal=True
      FATAL: required concept 'employees.department' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: question names table 'vulnerabilities' but the candidate never uses it
      note: checklist table 'vulnerabilities' is never used
  - llm_primary: score=0.0 executed=False rows=None fatal=False
      note: no SQL produced (invalid IR / unresolved plan / generation failure)
      note: distinct-count intent but no COUNT(DISTINCT)
  - llm_sql_direct: score=100.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
```

**SQL:**
```sql
SELECT v.vulnerability_id, v.cve_code
FROM vulnerabilities v
JOIN device_vulnerabilities dv ON v.vulnerability_id = dv.vulnerability_id
JOIN devices d ON dv.device_id = d.device_id
JOIN employees e ON d.employee_id = e.employee_id
JOIN training_records tr ON e.employee_id = tr.employee_id
WHERE tr.passed = 'yes'
GROUP BY v.vulnerability_id, v.cve_code
HAVING COUNT(DISTINCT d.os_family) > (
    SELECT COUNT(DISTINCT e2.department)
    FROM employees e2
    JOIN training_records tr2 ON e2.employee_id = tr2.employee_id
    WHERE tr2.passed = 'yes'
)
```

## cybersecurity_incidents_schema DB 30 Q07

**Question:** List pairs of devices owned by different employees in the same office city that share the same CVE code.

**Status:** EXEC_OK | rows=0 | source=query_family | family=self_join_pair | conf=0.9 | guard=True | time=18.667s

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

**GOLD: WRONG level=none gold_rows=58 gen_rows=234**

**Candidates:**
```text
SELECTED: query_family (reason=best_scored_executed, candidates=3)
  - query_family: score=64.0 executed=True rows=0 fatal=True
      FATAL: required concept 'vulnerabilities.cve_code' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: checklist table 'device_vulnerabilities' is never used
      note: checklist table 'vulnerabilities' is never used
  - llm_primary: score=0.0 executed=False rows=None fatal=False
      note: no SQL produced (invalid IR / unresolved plan / generation failure)
      note: question names table 'employees' but the candidate never uses it
  - llm_sql_direct: score=27.0 executed=False rows=None fatal=False
      note: execution failed: no such column: d1.office_city
      note: question names table 'employees' but the candidate never uses it
  WARNING: all executed candidates failed hard semantic checks; low confidence
  WARNING: selected candidate failed hard semantic checks: required concept 'vulnerabilities.cve_code' named in the question is missing from the SQL
```

**SQL:**
```sql
SELECT "p1"."device_id" AS "id_1", "p2"."device_id" AS "id_2" FROM "devices" AS "p1" INNER JOIN "devices" AS "p2" ON "p1"."employee_id" != "p2"."employee_id" AND "p1"."device_id" < "p2"."device_id" INNER JOIN "employees" AS "l1_employees" ON "p1"."employee_id" = "l1_employees"."employee_id" INNER JOIN "employees" AS "l2_employees" ON "p2"."employee_id" = "l2_employees"."employee_id" WHERE "l1_employees"."office_city" = "l2_employees"."office_city"
```

## cybersecurity_incidents_schema DB 30 Q08

**Question:** Find employees who opened incidents after their device's last patch date but before their latest unresolved alert time.

**Status:** EXEC_OK | rows=0 | source=llm | family=latest_earliest_per_entity | conf=0.72 | guard=None | time=19.645s

**Reason:** latest/earliest per entity (implicit)

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

**GOLD: WRONG level=none gold_rows=7 gen_rows=6**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=best_scored_executed, candidates=4)
  - llm_primary: score=50.0 executed=True rows=0 fatal=True
      FATAL: required concept 'alerts.resolved' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: question names table 'device_vulnerabilities' but the candidate never uses it
      note: question names table 'incident_alerts' but the candidate never uses it
  - llm_variant_1: score=50.0 executed=True rows=0 fatal=True
      FATAL: required concept 'alerts.resolved' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: question names table 'device_vulnerabilities' but the candidate never uses it
      note: question names table 'incident_alerts' but the candidate never uses it
  - llm_variant_2: score=65.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: question names table 'device_vulnerabilities' but the candidate never uses it
      note: question names table 'incident_alerts' but the candidate never uses it
  - llm_sql_direct: score=78.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: question names table 'device_vulnerabilities' but the candidate never uses it
      note: question names table 'incident_alerts' but the candidate never uses it
```

**SQL:**
```sql
SELECT DISTINCT e.employee_id, e.employee_name
FROM employees e
JOIN incidents i ON e.employee_id = i.opened_by_employee_id
JOIN devices d ON e.employee_id = d.employee_id
JOIN alerts a ON d.device_id = a.device_id
WHERE i.opened_time > d.last_patch_date
  AND a.resolved = 'no'
  AND i.opened_time < (
    SELECT MAX(a2.alert_time)
    FROM alerts a2
    JOIN devices d2 ON a2.device_id = d2.device_id
    WHERE d2.employee_id = e.employee_id
      AND a2.resolved = 'no'
  )
```

## cybersecurity_incidents_schema DB 30 Q09

**Question:** List devices that have never had a false positive vulnerability record but have at least one unresolved alert.

**Status:** EXEC_OK | rows=0 | source=llm | family=anti_exists | conf=0.8 | guard=False | time=13.152s

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
  "has_not_exists": true,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**GOLD: OK level=strict gold_rows=25 gen_rows=25**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=best_scored_executed, candidates=4)
  - query_family: score=15.0 executed=True rows=0 fatal=True
      FATAL: family guard rejected this output
      FATAL: required concept 'device_vulnerabilities.false_positive' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: question names table 'vulnerabilities' but the candidate never uses it
      note: question names table 'training_records' but the candidate never uses it
  - llm_primary: score=0.0 executed=False rows=None fatal=False
      note: no SQL produced (invalid IR / unresolved plan / generation failure)
      note: question names table 'vulnerabilities' but the candidate never uses it
      note: question names table 'training_records' but the candidate never uses it
  - llm_variant_1: score=0.0 executed=False rows=None fatal=False
      note: no SQL produced (invalid IR / unresolved plan / generation failure)
      note: referenced column does not exist: device_vulnerabilities.true
      note: question names table 'vulnerabilities' but the candidate never uses it
  - llm_sql_direct: score=74.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: question names table 'vulnerabilities' but the candidate never uses it
      note: question names table 'training_records' but the candidate never uses it
```

**SQL:**
```sql
SELECT d.device_id, d.hostname
FROM devices d
WHERE NOT EXISTS (
    SELECT 1
    FROM device_vulnerabilities dv
    WHERE dv.device_id = d.device_id
      AND dv.false_positive = 'yes'
)
AND EXISTS (
    SELECT 1
    FROM alerts a
    WHERE a.device_id = d.device_id
      AND a.resolved = 'no'
)
```

## cybersecurity_incidents_schema DB 30 Q10

**Question:** Find incident types where the highest impact incident was opened by an employee with no encrypted device.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=26.581s

**Reason:** no distinctive relational pattern; use base pipeline

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": true,
  "has_having": false,
  "has_inner_join": false,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": false,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**GOLD: WRONG level=none gold_rows=2 gen_rows=3**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=best_scored_executed, candidates=4)
  - llm_primary: score=16.0 executed=False rows=None fatal=False
      note: execution failed: no such column: incidents.incident_type
      note: question names table 'incident_alerts' but the candidate never uses it
      note: question names table 'device_vulnerabilities' but the candidate never uses it
  - llm_variant_1: score=73.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: question names table 'incident_alerts' but the candidate never uses it
      note: question names table 'device_vulnerabilities' but the candidate never uses it
  - llm_variant_2: score=16.0 executed=False rows=None fatal=False
      note: execution failed: no such column: incidents.incident_type
      note: question names table 'incident_alerts' but the candidate never uses it
      note: question names table 'device_vulnerabilities' but the candidate never uses it
  - llm_sql_direct: score=78.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: question names table 'incident_alerts' but the candidate never uses it
      note: question names table 'device_vulnerabilities' but the candidate never uses it
```

**SQL:**
```sql
SELECT i.incident_type
FROM incidents i
JOIN employees e ON i.opened_by_employee_id = e.employee_id
WHERE i.business_impact = (
    SELECT MAX(i2.business_impact)
    FROM incidents i2
    WHERE i2.incident_type = i.incident_type
)
AND EXISTS (
    SELECT 1
    FROM devices d
    WHERE d.employee_id = e.employee_id
    AND d.encrypted = 'no'
)
GROUP BY i.incident_type
```

## cybersecurity_incidents_schema DB 30 Q11

**Question:** List employees whose manager has a lower risk score but whose devices have higher average CVSS score than the manager's devices.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=38.686s

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
  "has_null_filter": true,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**GOLD: WRONG level=none gold_rows=5 gen_rows=0**

**Candidates:**
```text
SELECTED: llm_variant (reason=best_scored_executed, candidates=3)
  - llm_primary: score=0.0 executed=False rows=None fatal=False
      note: no SQL produced (invalid IR / unresolved plan / generation failure)
      note: referenced column does not exist: device_vulnerabilities.cvss_score
  - llm_variant_1: score=90.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: checklist requires shape 'comparison_subquery' but the SQL lacks it
  - llm_sql_direct: score=62.0 executed=True rows=0 fatal=True
      FATAL: illegal join: devices.employee_id = employees.manager_id
      note: executed but returned zero rows (weak signal)
      note: illegal join/correlation devices.employee_id = employees.manager_id (not a declared FK; e.g. key = measure)
```

**SQL:**
```sql
SELECT "employees"."risk_score", "employees"."manager_id", "employees"."employee_id", "employees"."employee_name", AVG("vulnerabilities"."cvss_score") AS "emp_avg_cvss", AVG("vulnerabilities"."cvss_score") AS "mgr_avg_cvss" FROM "devices" INNER JOIN "device_vulnerabilities" ON "devices"."device_id" = "device_vulnerabilities"."device_id" INNER JOIN "employees" ON "devices"."employee_id" = "employees"."employee_id" INNER JOIN "vulnerabilities" ON "device_vulnerabilities"."vulnerability_id" = "vulnerabilities"."vulnerability_id" WHERE "employees"."manager_id" IS NOT NULL GROUP BY "employees"."employee_id", "employees"."employee_name", "employees"."risk_score", "employees"."manager_id" HAVING "emp_avg_cvss" > "mgr_avg_cvss"
```

## cybersecurity_incidents_schema DB 30 Q12

**Question:** Find devices whose latest alert is unresolved and whose vulnerability with the highest CVSS score has not been remediated.

**Status:** EXEC_OK | rows=0 | source=llm | family=latest_earliest_per_entity | conf=0.72 | guard=None | time=28.015s

**Reason:** latest/earliest per entity (implicit)

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": false,
  "has_having": false,
  "has_inner_join": false,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": true,
  "has_self_alias_hint": false,
  "has_with_cte": true
}
```

**GOLD: OK level=strict gold_rows=8 gen_rows=8**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=best_scored_executed, candidates=4)
  - llm_primary: score=14.0 executed=False rows=None fatal=False
      note: execution failed: no such column: device_vulnerabilities__g1.cvss_score
      note: question names table 'incident_alerts' but the candidate never uses it
      note: checklist requires shape 'window_or_cte' but the SQL lacks it
  - llm_variant_1: score=14.0 executed=False rows=None fatal=False
      note: execution failed: no such column: device_vulnerabilities__g1.cvss_score
      note: question names table 'incident_alerts' but the candidate never uses it
      note: checklist requires shape 'window_or_cte' but the SQL lacks it
  - llm_variant_2: score=14.0 executed=False rows=None fatal=False
      note: execution failed: no such column: device_vulnerabilities__g1.cvss_score
      note: question names table 'incident_alerts' but the candidate never uses it
      note: checklist requires shape 'window_or_cte' but the SQL lacks it
  - llm_sql_direct: score=90.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: question names table 'incident_alerts' but the candidate never uses it
      note: literal 'yes' from the question is missing
```

**SQL:**
```sql
WITH latest_alerts AS (
    SELECT 
        a.device_id,
        a.alert_id,
        a.alert_time,
        a.resolved,
        ROW_NUMBER() OVER (PARTITION BY a.device_id ORDER BY a.alert_time DESC) AS rn
    FROM alerts a
),
max_cvss_vulns AS (
    SELECT 
        dv.device_id,
        dv.vulnerability_id,
        v.cvss_score,
        dv.remediated_date,
        ROW_NUMBER() OVER (PARTITION BY dv.device_id ORDER BY v.cvss_score DESC, dv.vulnerability_id) AS rn
    FROM device_vulnerabilities dv
    JOIN vulnerabilities v ON dv.vulnerability_id = v.vulnerability_id
)
SELECT 
    d.device_id,
    d.hostname
FROM devices d
JOIN latest_alerts la ON d.device_id = la.device_id
JOIN max_cvss_vulns mcv ON d.device_id = mcv.device_id
WHERE la.rn = 1
  AND la.resolved = 'no'
  AND mcv.rn = 1
  AND mcv.remediated_date IS NULL
```

## cybersecurity_incidents_schema DB 30 Q13

**Question:** List employees who have devices with all vulnerability severities but have not passed every security training course.

**Status:** EXEC_OK | rows=0 | source=llm | family=set_division_count_distinct | conf=0.85 | guard=None | time=25.2s

**Reason:** has/contains ALL members of a set (count-distinct division)

**Flags:**
```json
{
  "has_count_distinct": true,
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

**GOLD: WRONG level=none gold_rows=5 gen_rows=2**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=validation_score_override, candidates=4)
  - llm_primary: score=57.0 executed=True rows=0 fatal=True
      FATAL: required concept 'training_records.passed' named in the question is missing from the SQL
      FATAL: required concept 'training_records.course_name' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: checklist column 'vulnerabilities.severity' is never used
      note: checklist column 'training_records.passed' is never used
  - llm_variant_1: score=72.0 executed=True rows=0 fatal=True
      FATAL: required concept 'training_records.passed' named in the question is missing from the SQL
      FATAL: required concept 'training_records.course_name' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: checklist column 'training_records.passed' is never used
      note: checklist column 'training_records.course_name' is never used
  - llm_variant_2: score=72.0 executed=True rows=0 fatal=True
      FATAL: required concept 'training_records.passed' named in the question is missing from the SQL
      FATAL: required concept 'training_records.course_name' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: checklist column 'training_records.passed' is never used
      note: checklist column 'training_records.course_name' is never used
  - llm_sql_direct: score=93.0 executed=True rows=0 fatal=True
      FATAL: required concept 'training_records.course_name' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: checklist column 'training_records.course_name' is never used
  WARNING: all executed candidates failed hard semantic checks; low confidence
  WARNING: selected candidate failed hard semantic checks: required concept 'training_records.course_name' named in the question is missing from the SQL
```

**SQL:**
```sql
SELECT e.employee_id, e.employee_name
FROM employees e
JOIN devices d ON e.employee_id = d.employee_id
JOIN device_vulnerabilities dv ON d.device_id = dv.device_id
JOIN vulnerabilities v ON dv.vulnerability_id = v.vulnerability_id
JOIN training_records tr ON e.employee_id = tr.employee_id
WHERE tr.passed = 'no'
GROUP BY e.employee_id, e.employee_name
HAVING COUNT(DISTINCT v.severity) = (SELECT COUNT(DISTINCT severity) FROM vulnerabilities)
```

## cybersecurity_incidents_schema DB 30 Q14

**Question:** Find office cities where every employee either has no device or has at least one encrypted device.

**Status:** EXEC_OK | rows=0 | source=llm | family=universal_every_all | conf=0.82 | guard=None | time=17.575s

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

**GOLD: WRONG level=none gold_rows=1 gen_rows=4**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=best_scored_executed, candidates=3)
  - llm_primary: score=51.0 executed=True rows=0 fatal=True
      FATAL: required concept 'devices.encrypted' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: question names table 'device_vulnerabilities' but the candidate never uses it
      note: absence intent ('never/no/not ...') but no NOT EXISTS / NOT IN / LEFT JOIN+IS NULL
  - llm_variant_2: score=51.0 executed=True rows=0 fatal=True
      FATAL: required concept 'devices.encrypted' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: question names table 'device_vulnerabilities' but the candidate never uses it
      note: absence intent ('never/no/not ...') but no NOT EXISTS / NOT IN / LEFT JOIN+IS NULL
  - llm_sql_direct: score=66.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: question names table 'device_vulnerabilities' but the candidate never uses it
      note: absence intent ('never/no/not ...') but no NOT EXISTS / NOT IN / LEFT JOIN+IS NULL
```

**SQL:**
```sql
SELECT e.office_city
FROM employees e
LEFT JOIN devices d ON e.employee_id = d.employee_id
GROUP BY e.office_city
HAVING COUNT(d.device_id) = 0 OR COUNT(CASE WHEN d.encrypted = 'yes' THEN 1 END) > 0
```

## cybersecurity_incidents_schema DB 30 Q15

**Question:** List CVE codes where the highest CVSS occurrence was never remediated but a lower CVSS occurrence was remediated.

**Status:** EXEC_OK | rows=0 | source=llm | family=anti_exists | conf=0.8 | guard=None | time=20.585s

**Reason:** absence check (NOT EXISTS)

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": true,
  "has_having": false,
  "has_inner_join": false,
  "has_left_join": false,
  "has_not_exists": false,
  "has_null_filter": true,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**GOLD: OK level=strict gold_rows=3 gen_rows=3**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=best_scored_executed, candidates=4)
  - llm_primary: score=0.0 executed=False rows=None fatal=False
      note: no SQL produced (invalid IR / unresolved plan / generation failure)
      note: referenced column does not exist: vulnerabilities.max_cvss
      note: absence intent ('never/no/not ...') but no NOT EXISTS / NOT IN / LEFT JOIN+IS NULL
  - llm_variant_1: score=0.0 executed=False rows=None fatal=False
      note: no SQL produced (invalid IR / unresolved plan / generation failure)
      note: absence intent ('never/no/not ...') but no NOT EXISTS / NOT IN / LEFT JOIN+IS NULL
  - llm_variant_2: score=0.0 executed=False rows=None fatal=False
      note: no SQL produced (invalid IR / unresolved plan / generation failure)
      note: absence intent ('never/no/not ...') but no NOT EXISTS / NOT IN / LEFT JOIN+IS NULL
  - llm_sql_direct: score=82.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: absence intent ('never/no/not ...') but no NOT EXISTS / NOT IN / LEFT JOIN+IS NULL
```

**SQL:**
```sql
SELECT v.cve_code
FROM vulnerabilities v
JOIN device_vulnerabilities dv ON v.vulnerability_id = dv.vulnerability_id
WHERE dv.remediated_date IS NULL
  AND v.cvss_score = (
    SELECT MAX(v2.cvss_score)
    FROM vulnerabilities v2
    JOIN device_vulnerabilities dv2 ON v2.vulnerability_id = dv2.vulnerability_id
    WHERE v2.cve_code = v.cve_code
      AND dv2.remediated_date IS NULL
  )
  AND EXISTS (
    SELECT 1
    FROM vulnerabilities v3
    JOIN device_vulnerabilities dv3 ON v3.vulnerability_id = dv3.vulnerability_id
    WHERE v3.cve_code = v.cve_code
      AND dv3.remediated_date IS NOT NULL
      AND v3.cvss_score < v.cvss_score
  )
GROUP BY v.cve_code
```

## cybersecurity_incidents_schema DB 30 Q16

**Question:** Find employees whose devices triggered more distinct alert types than the number of distinct courses they passed.

**Status:** EXEC_OK | rows=0 | source=llm | family=count_distinct_comparison | conf=0.8 | guard=True | time=12.997s

**Reason:** more/fewer distinct X than Y

**Flags:**
```json
{
  "has_count_distinct": true,
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

**GOLD: WRONG level=none gold_rows=13 gen_rows=10**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=best_scored_executed, candidates=3)
  - query_family: score=81.0 executed=True rows=0 fatal=True
      FATAL: required concept 'training_records.passed' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: question names table 'incident_alerts' but the candidate never uses it
      note: checklist column 'training_records.passed' is never used
  - llm_primary: score=38.0 executed=True rows=0 fatal=True
      FATAL: required concept 'training_records.passed' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: question names table 'incident_alerts' but the candidate never uses it
      note: distinct-count intent but no COUNT(DISTINCT)
  - llm_sql_direct: score=96.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: question names table 'incident_alerts' but the candidate never uses it
```

**SQL:**
```sql
SELECT e.employee_id, e.employee_name
FROM employees e
JOIN devices d ON e.employee_id = d.employee_id
JOIN alerts a ON d.device_id = a.device_id
JOIN training_records tr ON e.employee_id = tr.employee_id
WHERE tr.passed = 'yes'
GROUP BY e.employee_id, e.employee_name
HAVING COUNT(DISTINCT a.alert_type) > (
    SELECT COUNT(DISTINCT tr2.course_name)
    FROM training_records tr2
    WHERE tr2.employee_id = e.employee_id AND tr2.passed = 'yes'
)
```

## cybersecurity_incidents_schema DB 30 Q17

**Question:** List incidents whose alerts come from devices owned by employees in a different office city than the employee who opened the incident.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=22.184s

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

**GOLD: OK level=strict gold_rows=15 gen_rows=15**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=best_scored_executed, candidates=4)
  - llm_primary: score=0.0 executed=False rows=None fatal=False
      note: no SQL produced (invalid IR / unresolved plan / generation failure)
      note: literal 'employees.office_city' is not among the sampled values of column 'office_city' (known: ['Boise', 'Moscow', 'Pullman', 'Spokane'])
  - llm_variant_1: score=49.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: checklist requires shape 'comparison_subquery' but the SQL lacks it
      note: checklist table 'incidents' is never used
  - llm_variant_2: score=5.0 executed=False rows=None fatal=False
      note: no SQL produced (invalid IR / unresolved plan / generation failure)
  - llm_sql_direct: score=100.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
```

**SQL:**
```sql
SELECT DISTINCT i.incident_id
FROM incidents i
JOIN incident_alerts ia ON i.incident_id = ia.incident_id
JOIN alerts a ON ia.alert_id = a.alert_id
JOIN devices d ON a.device_id = d.device_id
JOIN employees e_device ON d.employee_id = e_device.employee_id
WHERE e_device.office_city != (
    SELECT e_opener.office_city
    FROM employees e_opener
    WHERE e_opener.employee_id = i.opened_by_employee_id
)
```

## cybersecurity_incidents_schema DB 30 Q18

**Question:** Find devices with no vulnerabilities but with at least one high severity alert.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=22.906s

**Reason:** no distinctive relational pattern; use base pipeline

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

**GOLD: OK level=strict gold_rows=1 gen_rows=1**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=consensus_group, candidates=3)
  - llm_primary: score=74.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: question names table 'vulnerabilities' but the candidate never uses it
      note: question names table 'incident_alerts' but the candidate never uses it
  - llm_variant_2: score=52.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: question names table 'vulnerabilities' but the candidate never uses it
      note: question names table 'incident_alerts' but the candidate never uses it
  - llm_sql_direct: score=74.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: question names table 'vulnerabilities' but the candidate never uses it
      note: question names table 'incident_alerts' but the candidate never uses it
```

**SQL:**
```sql
SELECT d.device_id, d.hostname
FROM devices d
WHERE NOT EXISTS (
    SELECT 1
    FROM device_vulnerabilities dv
    WHERE dv.device_id = d.device_id
)
AND EXISTS (
    SELECT 1
    FROM alerts a
    WHERE a.device_id = d.device_id
    AND a.severity = 'high'
)
```

## cybersecurity_incidents_schema DB 30 Q19

**Question:** List employees where every device they own has been patched after all vulnerabilities on that device were detected.

**Status:** EXEC_OK | rows=0 | source=llm | family=set_division_count_distinct | conf=0.85 | guard=None | time=25.161s

**Reason:** has/contains ALL members of a set (count-distinct division)

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

**GOLD: WRONG level=none gold_rows=5 gen_rows=14**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=best_scored_executed, candidates=4)
  - llm_primary: score=54.0 executed=True rows=0 fatal=True
      FATAL: required concept 'device_vulnerabilities.detected_date' named in the question is missing from the SQL
      FATAL: required concept 'devices.last_patch_date' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: checklist requires shape 'not_exists' but the SQL lacks it
      note: checklist column 'device_vulnerabilities.detected_date' is never used
  - llm_variant_1: score=54.0 executed=True rows=0 fatal=True
      FATAL: required concept 'device_vulnerabilities.detected_date' named in the question is missing from the SQL
      FATAL: required concept 'devices.last_patch_date' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: checklist requires shape 'not_exists' but the SQL lacks it
      note: checklist column 'device_vulnerabilities.detected_date' is never used
  - llm_variant_2: score=54.0 executed=True rows=0 fatal=True
      FATAL: required concept 'device_vulnerabilities.detected_date' named in the question is missing from the SQL
      FATAL: required concept 'devices.last_patch_date' named in the question is missing from the SQL
      note: executed but returned zero rows (weak signal)
      note: checklist requires shape 'not_exists' but the SQL lacks it
      note: checklist column 'device_vulnerabilities.detected_date' is never used
  - llm_sql_direct: score=86.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: question names table 'vulnerabilities' but the candidate never uses it
      note: checklist table 'vulnerabilities' is never used
```

**SQL:**
```sql
SELECT e.employee_id, e.employee_name
FROM employees e
WHERE NOT EXISTS (
    SELECT 1
    FROM devices d
    JOIN device_vulnerabilities dv ON d.device_id = dv.device_id
    WHERE d.employee_id = e.employee_id
      AND dv.false_positive = 'no'
      AND d.last_patch_date < dv.detected_date
)
```

## cybersecurity_incidents_schema DB 30 Q20

**Question:** Find departments where the same manager supervises both the highest risk and lowest risk employee in that department.

**Status:** EXEC_OK | rows=0 | source=llm | family=min_max_same_entity_per_group | conf=0.9 | guard=None | time=20.736s

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
  "has_with_cte": true
}
```

**GOLD: OK level=strict gold_rows=0 gen_rows=0 (both empty — weak)**

**Candidates:**
```text
SELECTED: llm_sql_direct (reason=validation_score_override, candidates=4)
  - llm_primary: score=84.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: checklist requires shape 'window_or_cte' but the SQL lacks it
  - llm_variant_1: score=84.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: checklist requires shape 'window_or_cte' but the SQL lacks it
  - llm_variant_2: score=84.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
      note: checklist requires shape 'window_or_cte' but the SQL lacks it
  - llm_sql_direct: score=100.0 executed=True rows=0 fatal=False
      note: executed but returned zero rows (weak signal)
```

**SQL:**
```sql
WITH ranked_employees AS (
    SELECT 
        department,
        manager_id,
        risk_score,
        ROW_NUMBER() OVER (PARTITION BY department ORDER BY risk_score DESC) AS rn_max,
        ROW_NUMBER() OVER (PARTITION BY department ORDER BY risk_score ASC) AS rn_min
    FROM employees
)
SELECT department
FROM ranked_employees
WHERE rn_max = 1 OR rn_min = 1
GROUP BY department
HAVING MAX(CASE WHEN rn_max = 1 THEN manager_id END) = MAX(CASE WHEN rn_min = 1 THEN manager_id END)
```
