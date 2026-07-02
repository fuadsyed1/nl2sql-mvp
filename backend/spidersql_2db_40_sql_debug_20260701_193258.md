# SpiderSQL 2-Database SQL Debug Results

## clinic_multiple_csv DB 29 Q01

**Question:** List patients whose latest appointment was cancelled but who have at least one unpaid invoice from an earlier appointment.

**Status:** EXEC_OK | rows=9 | source=llm | family=latest_earliest_per_entity | conf=0.72 | guard=None | time=29.966s

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
SELECT DISTINCT "patients"."patient_id", "patients"."patient_name" FROM "appointments" INNER JOIN "invoices" ON "appointments"."appointment_id" = "invoices"."appointment_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id" WHERE NOT EXISTS (SELECT 1 FROM "invoices" WHERE "appointments"."appointment_id" = "invoices"."appointment_id" AND "appointments"."status" = "appointments"."status" AND "invoices"."payment_status" = ?) AND NOT EXISTS (SELECT 1 FROM "appointments" AS "appointments__g0" WHERE "appointments__g0"."patient_id" = "appointments"."patient_id" AND "appointments__g0"."appointment_date" > "appointments"."appointment_date")
```

## clinic_multiple_csv DB 29 Q02

**Question:** Find doctors who treated patients from a different city and whose average invoice total is higher than the average invoice total for doctors in the same specialty.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=32.466s

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

**SQL:**
```sql
WITH specialty_avg AS (
    SELECT 
        d.specialty,
        AVG(i.total_amount) AS avg_specialty_amount
    FROM doctors d
    JOIN appointments a ON d.doctor_id = a.doctor_id
    JOIN invoices i ON a.appointment_id = i.appointment_id
    JOIN patients p ON a.patient_id = p.patient_id
    WHERE p.city != d.clinic_city
    GROUP BY d.specialty
),
doctor_avg AS (
    SELECT 
        d.doctor_id,
        d.doctor_name,
        d.specialty,
        AVG(i.total_amount) AS avg_doctor_amount
    FROM doctors d
    JOIN appointments a ON d.doctor_id = a.doctor_id
    JOIN invoices i ON a.appointment_id = i.appointment_id
    JOIN patients p ON a.patient_id = p.patient_id
    WHERE p.city != d.clinic_city
    GROUP BY d.doctor_id, d.doctor_name, d.specialty
)
SELECT 
    da.doctor_id,
    da.doctor_name
FROM doctor_avg da
JOIN specialty_avg sa ON da.specialty = sa.specialty
WHERE da.avg_doctor_amount > sa.avg_specialty_amount
```

## clinic_multiple_csv DB 29 Q03

**Question:** List patients who were prescribed a controlled substance but have no lab result marked high for the appointment where it was prescribed.

**Status:** EXEC_OK | rows=0 | source=llm | family=anti_exists | conf=0.8 | guard=False | time=15.879s

**Reason:** absence check (NOT EXISTS)

**Guard reasons:**
- anti_exists is too shallow: mentioned table(s) ['lab_results'] not represented (positive evidence / absence concept ignored)

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
SELECT DISTINCT p.patient_id, p.patient_name
FROM patients p
JOIN appointments a ON p.patient_id = a.patient_id
JOIN prescriptions pr ON a.appointment_id = pr.appointment_id
JOIN medications m ON pr.medication_id = m.medication_id
WHERE m.controlled_substance = '1'
AND NOT EXISTS (
    SELECT 1
    FROM lab_results lr
    WHERE lr.appointment_id = a.appointment_id
    AND lr.result_flag = 'high'
)
```

## clinic_multiple_csv DB 29 Q04

**Question:** Find visit types where the same doctor handled both the lowest base fee and the highest base fee appointment of that visit type.

**Status:** EXEC_OK | rows=20 | source=query_family | family=min_max_same_entity_per_group | conf=0.95 | guard=True | time=13.951s

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

**Status:** EXEC_OK | rows=30 | source=llm | family=anti_exists | conf=0.8 | guard=False | time=15.909s

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
  "has_null_filter": true,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT DISTINCT m.medication_name
FROM medications m
JOIN prescriptions p ON m.medication_id = p.medication_id
JOIN appointments a ON p.appointment_id = a.appointment_id
JOIN patients pat ON a.patient_id = pat.patient_id
WHERE pat.chronic_condition IS NOT NULL
  AND pat.chronic_condition != ''
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

**Status:** EXEC_OK | rows=14 | source=llm | family=derived_aggregate_cte | conf=0.85 | guard=None | time=20.734s

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

**Status:** EXEC_OK | rows=0 | source=llm | family=universal_every_all | conf=0.82 | guard=True | time=19.445s

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

**SQL:**
```sql
SELECT "doctors"."doctor_id", "doctors"."doctor_name", COUNT("patients"."insurance_provider") AS "insurance_count" FROM "appointments" INNER JOIN "doctors" ON "appointments"."doctor_id" = "doctors"."doctor_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id" GROUP BY "doctors"."doctor_id", "doctors"."doctor_name" HAVING "insurance_count" = ?
```

## clinic_multiple_csv DB 29 Q08

**Question:** Find patients whose prescription days_supply is higher than every other prescription for the same medication class.

**Status:** EXEC_OK | rows=5 | source=llm | family=universal_every_all | conf=0.82 | guard=None | time=18.386s

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

**SQL:**
```sql
SELECT "medications"."medication_class", "prescriptions"."appointment_id", "prescriptions"."days_supply", MAX("prescriptions"."days_supply") AS "max_days_supply" FROM "prescriptions" INNER JOIN "medications" ON "prescriptions"."medication_id" = "medications"."medication_id" GROUP BY "medications"."medication_class" HAVING "max_days_supply" = "max_days_supply"
```

## clinic_multiple_csv DB 29 Q09

**Question:** List pairs of patients in the same city who saw the same doctor on different appointment dates.

**Status:** EXEC_OK | rows=360 | source=llm | family=self_join_pair | conf=0.9 | guard=True | time=27.79s

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

**SQL:**
```sql
SELECT p1.patient_name, p1.city, d.doctor_name, a1.appointment_date
FROM patients p1
JOIN appointments a1 ON p1.patient_id = a1.patient_id
JOIN doctors d ON a1.doctor_id = d.doctor_id
JOIN patients p2 ON p1.city = p2.city AND p1.patient_id != p2.patient_id
JOIN appointments a2 ON p2.patient_id = a2.patient_id AND a1.doctor_id = a2.doctor_id AND a1.appointment_date != a2.appointment_date
WHERE p1.patient_id < p2.patient_id
```

## clinic_multiple_csv DB 29 Q10

**Question:** Find appointments where the patient city is different from the doctor clinic city and the invoice is unpaid.

**Status:** EXEC_OK | rows=34 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=18.313s

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

**Status:** EXEC_OK | rows=0 | source=llm | family=top_per_group | conf=0.82 | guard=False | time=22.09s

**Reason:** extremum of a raw column within a group

**Guard reasons:**
- absence intent but no anti_exists/universal/null structure

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

**SQL:**
```sql
SELECT m.medication_id, m.medication_name, m.medication_class, m.unit_cost
FROM medications m
WHERE m.medication_id NOT IN (
    SELECT DISTINCT p.medication_id
    FROM prescriptions p
)
AND EXISTS (
    SELECT 1
    FROM medications m2
    JOIN prescriptions p2 ON m2.medication_id = p2.medication_id
    WHERE m2.medication_class = m.medication_class
    AND m2.unit_cost < m.unit_cost
)
AND m.unit_cost = (
    SELECT MAX(m3.unit_cost)
    FROM medications m3
    WHERE m3.medication_class = m.medication_class
)
```

## clinic_multiple_csv DB 29 Q12

**Question:** Find patients who had a low lab result after receiving a prescription with refill allowed.

**Status:** EXEC_OK | rows=7 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=19.149s

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
SELECT DISTINCT "patients"."patient_id", "patients"."patient_name" FROM "appointments" INNER JOIN "lab_results" ON "appointments"."appointment_id" = "lab_results"."appointment_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id" INNER JOIN "prescriptions" ON "appointments"."appointment_id" = "prescriptions"."appointment_id" WHERE "prescriptions"."refill_allowed" = ? AND "lab_results"."result_flag" = ?
```

## clinic_multiple_csv DB 29 Q13

**Question:** List doctors whose patients had more distinct abnormal lab test names than the number of distinct medication classes they prescribed.

**Status:** EXEC_OK | rows=0 | source=llm | family=count_distinct_comparison | conf=0.8 | guard=True | time=46.95s

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

**SQL:**
```sql
SELECT d.doctor_id, d.doctor_name
FROM doctors d
JOIN appointments a ON d.doctor_id = a.doctor_id
JOIN lab_results l ON a.appointment_id = l.appointment_id
JOIN prescriptions p ON a.appointment_id = p.appointment_id
JOIN medications m ON p.medication_id = m.medication_id
WHERE l.result_flag = 'abnormal'
GROUP BY d.doctor_id, d.doctor_name
HAVING COUNT(DISTINCT l.test_name) > (
    SELECT COUNT(DISTINCT m2.medication_class)
    FROM appointments a2
    JOIN prescriptions p2 ON a2.appointment_id = p2.appointment_id
    JOIN medications m2 ON p2.medication_id = m2.medication_id
    WHERE a2.doctor_id = d.doctor_id
)
```

## clinic_multiple_csv DB 29 Q14

**Question:** Find patients who have appointments but have never received a prescription for any medication class marked controlled substance.

**Status:** EXEC_OK | rows=7 | source=llm | family=anti_exists | conf=0.8 | guard=False | time=17.141s

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

**Status:** EXEC_OK | rows=10 | source=llm | family=derived_aggregate_cte | conf=0.85 | guard=True | time=14.655s

**Reason:** per-entity aggregate total then ranked/compared (derived relation)

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
  "has_with_cte": true
}
```

**SQL:**
```sql
WITH city_max AS (
  SELECT 
    p.city,
    p.patient_name,
    i.total_amount,
    MAX(i.total_amount) OVER (PARTITION BY p.city) AS max_amount
  FROM patients p
  JOIN appointments a ON p.patient_id = a.patient_id
  JOIN invoices i ON a.appointment_id = i.appointment_id
)
SELECT 
  city,
  patient_name,
  total_amount
FROM city_max
WHERE total_amount = max_amount
```

## clinic_multiple_csv DB 29 Q16

**Question:** Find patients whose latest lab result was high and whose doctor for that appointment has less than five years of experience.

**Status:** EXEC_OK | rows=3 | source=llm | family=latest_earliest_per_entity | conf=0.72 | guard=None | time=22.171s

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
  "has_with_cte": true
}
```

**SQL:**
```sql
WITH latest_lab AS (
    SELECT 
        lr.appointment_id,
        lr.result_flag,
        lr.result_date,
        ROW_NUMBER() OVER (PARTITION BY lr.appointment_id ORDER BY lr.result_date DESC) AS rn
    FROM lab_results lr
)
SELECT 
    p.patient_id,
    p.patient_name
FROM patients p
JOIN appointments a ON p.patient_id = a.patient_id
JOIN doctors d ON a.doctor_id = d.doctor_id
JOIN latest_lab ll ON a.appointment_id = ll.appointment_id
WHERE ll.rn = 1
  AND ll.result_flag = 'high'
  AND d.years_experience < 5
```

## clinic_multiple_csv DB 29 Q17

**Question:** List appointments with no prescription but with at least one lab result and an unpaid invoice.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=36.246s

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
  "has_null_filter": true,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT "appointments"."appointment_id" FROM "appointments" INNER JOIN "lab_results" ON "appointments"."appointment_id" = "lab_results"."appointment_id" INNER JOIN "invoices" ON "appointments"."appointment_id" = "invoices"."appointment_id" WHERE "lab_results"."appointment_id" IS NOT NULL AND "invoices"."payment_status" = ? AND NOT EXISTS (SELECT 1 FROM "prescriptions" WHERE "appointments"."appointment_id" = "prescriptions"."appointment_id")
```

## clinic_multiple_csv DB 29 Q18

**Question:** Find doctors who have treated all visit types represented in the appointments table.

**Status:** EXEC_OK | rows=5 | source=llm | family=set_division_count_distinct | conf=0.85 | guard=None | time=20.152s

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

**Status:** EXEC_OK | rows=35 | source=llm | family=self_join_pair | conf=0.6 | guard=None | time=25.63s

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

**SQL:**
```sql
SELECT DISTINCT "medications"."medication_class", "patients"."patient_id", "patients"."patient_name", COUNT("doctors"."doctor_id") AS "doctor_count" FROM "appointments" INNER JOIN "doctors" ON "appointments"."doctor_id" = "doctors"."doctor_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id" INNER JOIN "prescriptions" ON "appointments"."appointment_id" = "prescriptions"."appointment_id" INNER JOIN "medications" ON "prescriptions"."medication_id" = "medications"."medication_id" GROUP BY "patients"."patient_id", "patients"."patient_name", "medications"."medication_class" HAVING "doctor_count" >= ?
```

## clinic_multiple_csv DB 29 Q20

**Question:** Find medication classes where patients with chronic conditions received more prescriptions than patients without chronic conditions.

**Status:** EXEC_OK | rows=5 | source=llm | family=outer_join_null | conf=0.75 | guard=None | time=44.568s

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
  "has_null_filter": true,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT m.medication_class
FROM medications m
JOIN prescriptions p ON m.medication_id = p.medication_id
JOIN appointments a ON p.appointment_id = a.appointment_id
JOIN patients pt ON a.patient_id = pt.patient_id
GROUP BY m.medication_class
HAVING SUM(CASE WHEN pt.chronic_condition IS NOT NULL AND pt.chronic_condition != '' THEN 1 ELSE 0 END) >
       SUM(CASE WHEN pt.chronic_condition IS NULL OR pt.chronic_condition = '' THEN 1 ELSE 0 END)
```

## cybersecurity_incidents_schema DB 30 Q01

**Question:** List employees whose devices have unresolved critical alerts but who have no passed security training record.

**Status:** EXEC_OK | rows=0 | source=llm | family=anti_exists | conf=0.8 | guard=False | time=14.654s

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
      AND a.resolved = 'resolved'
)
AND NOT EXISTS (
    SELECT 1
    FROM training_records tr
    WHERE tr.employee_id = e.employee_id
      AND tr.passed = 'passed'
)
```

## cybersecurity_incidents_schema DB 30 Q02

**Question:** Find device types where the same employee owns both the most vulnerable and least vulnerable device of that type by vulnerability count.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=27.17s

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

**SQL:**
```sql
WITH device_vuln_counts AS (
    SELECT 
        d.device_id,
        d.device_type,
        d.employee_id,
        COUNT(dv.vulnerability_id) AS vuln_count
    FROM devices d
    JOIN device_vulnerabilities dv ON d.device_id = dv.device_id
    GROUP BY d.device_id, d.device_type, d.employee_id
),
ranked_devices AS (
    SELECT 
        device_id,
        device_type,
        employee_id,
        vuln_count,
        ROW_NUMBER() OVER (PARTITION BY device_type ORDER BY vuln_count DESC) AS rn_max,
        ROW_NUMBER() OVER (PARTITION BY device_type ORDER BY vuln_count ASC) AS rn_min
    FROM device_vuln_counts
),
extremes AS (
    SELECT 
        device_type,
        MAX(CASE WHEN rn_max = 1 THEN employee_id END) AS max_vuln_employee,
        MAX(CASE WHEN rn_min = 1 THEN employee_id END) AS min_vuln_employee
    FROM ranked_devices
    GROUP BY device_type
)
SELECT device_type
FROM extremes
WHERE max_vuln_employee = min_vuln_employee
```

## cybersecurity_incidents_schema DB 30 Q03

**Question:** List devices with vulnerabilities that have an exploit available but no incident has been linked to any alert from that device.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=23.309s

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

**Status:** EXEC_OK | rows=0 | source=llm | family=set_division_count_distinct | conf=0.85 | guard=None | time=19.168s

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

**Status:** EXEC_OK | rows=0 | source=query_family | family=derived_aggregate_cte | conf=0.85 | guard=False | time=26.015s

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

**SQL:**
```sql
WITH "device_vulnerabilities_totals" AS (SELECT "device_vulnerabilities"."device_vulnerability_id" AS "entity_id", "employees"."department" AS "group_col", AVG("employees"."risk_score") AS "agg_value" FROM "device_vulnerabilities" INNER JOIN "devices" ON "device_vulnerabilities"."device_id" = "devices"."device_id" INNER JOIN "employees" ON "devices"."employee_id" = "employees"."employee_id" GROUP BY "device_vulnerabilities"."device_vulnerability_id", "employees"."department") SELECT * FROM "device_vulnerabilities_totals"
```

## cybersecurity_incidents_schema DB 30 Q06

**Question:** Find vulnerabilities that appear on more distinct operating system families than the number of distinct departments with trained employees.

**Status:** EXEC_OK | rows=0 | source=llm | family=count_distinct_comparison | conf=0.8 | guard=True | time=30.293s

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

**SQL:**
```sql
SELECT v.vulnerability_id, v.cve_code
FROM vulnerabilities v
JOIN device_vulnerabilities dv ON v.vulnerability_id = dv.vulnerability_id
JOIN devices d ON dv.device_id = d.device_id
GROUP BY v.vulnerability_id, v.cve_code
HAVING COUNT(DISTINCT d.os_family) > (
    SELECT COUNT(DISTINCT e.department)
    FROM employees e
    JOIN training_records tr ON e.employee_id = tr.employee_id
)
```

## cybersecurity_incidents_schema DB 30 Q07

**Question:** List pairs of devices owned by different employees in the same office city that share the same CVE code.

**Status:** EXEC_OK | rows=0 | source=llm | family=self_join_pair | conf=0.9 | guard=True | time=19.398s

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

**SQL:**
```sql
SELECT d1.device_id, d1.hostname, v.cve_code
FROM devices d1
JOIN employees e1 ON d1.employee_id = e1.employee_id
JOIN device_vulnerabilities dv1 ON d1.device_id = dv1.device_id
JOIN vulnerabilities v ON dv1.vulnerability_id = v.vulnerability_id
JOIN device_vulnerabilities dv2 ON v.vulnerability_id = dv2.vulnerability_id
JOIN devices d2 ON dv2.device_id = d2.device_id
JOIN employees e2 ON d2.employee_id = e2.employee_id
WHERE e1.office_city = e2.office_city
  AND e1.employee_id != e2.employee_id
  AND d1.device_id < d2.device_id
```

## cybersecurity_incidents_schema DB 30 Q08

**Question:** Find employees who opened incidents after their device's last patch date but before their latest unresolved alert time.

**Status:** EXEC_OK | rows=0 | source=llm | family=latest_earliest_per_entity | conf=0.72 | guard=None | time=20.675s

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

**SQL:**
```sql
SELECT DISTINCT e.employee_id, e.employee_name
FROM employees e
JOIN incidents i ON e.employee_id = i.opened_by_employee_id
JOIN devices d ON e.employee_id = d.employee_id
JOIN alerts a ON d.device_id = a.device_id
WHERE i.opened_time > d.last_patch_date
  AND a.resolved = 'false'
  AND i.opened_time < (
    SELECT MAX(a2.alert_time)
    FROM alerts a2
    JOIN devices d2 ON a2.device_id = d2.device_id
    WHERE d2.employee_id = e.employee_id
      AND a2.resolved = 'false'
  )
```

## cybersecurity_incidents_schema DB 30 Q09

**Question:** List devices that have never had a false positive vulnerability record but have at least one unresolved alert.

**Status:** EXEC_OK | rows=0 | source=llm | family=anti_exists | conf=0.8 | guard=False | time=17.657s

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

**SQL:**
```sql
SELECT d.device_id, d.hostname
FROM devices d
WHERE NOT EXISTS (
    SELECT 1
    FROM device_vulnerabilities dv
    WHERE dv.device_id = d.device_id
      AND dv.false_positive = 'false_positive'
)
AND EXISTS (
    SELECT 1
    FROM alerts a
    WHERE a.device_id = d.device_id
      AND a.resolved = 'unresolved'
)
```

## cybersecurity_incidents_schema DB 30 Q10

**Question:** Find incident types where the highest impact incident was opened by an employee with no encrypted device.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=23.075s

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

**SQL:**
```sql
SELECT i.incident_type
FROM incidents i
JOIN employees e ON i.opened_by_employee_id = e.employee_id
JOIN devices d ON e.employee_id = d.employee_id
WHERE d.encrypted = 'false'
GROUP BY i.incident_type
HAVING MAX(i.business_impact) = (
    SELECT MAX(i2.business_impact)
    FROM incidents i2
    JOIN employees e2 ON i2.opened_by_employee_id = e2.employee_id
    JOIN devices d2 ON e2.employee_id = d2.employee_id
    WHERE d2.encrypted = 'false'
)
```

## cybersecurity_incidents_schema DB 30 Q11

**Question:** List employees whose manager has a lower risk score but whose devices have higher average CVSS score than the manager's devices.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=41.629s

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
  "has_null_filter": true,
  "has_self_alias_hint": false,
  "has_with_cte": false
}
```

**SQL:**
```sql
SELECT e.employee_id, e.employee_name
FROM employees e
JOIN devices d ON e.employee_id = d.employee_id
JOIN device_vulnerabilities dv ON d.device_id = dv.device_id
JOIN vulnerabilities v ON dv.vulnerability_id = v.vulnerability_id
WHERE e.manager_id IS NOT NULL
  AND e.risk_score > (SELECT risk_score FROM employees WHERE employee_id = e.manager_id)
  AND (
    SELECT AVG(v2.cvss_score)
    FROM devices d2
    JOIN device_vulnerabilities dv2 ON d2.device_id = dv2.device_id
    JOIN vulnerabilities v2 ON dv2.vulnerability_id = v2.vulnerability_id
    WHERE d2.employee_id = e.employee_id
  ) > (
    SELECT AVG(v3.cvss_score)
    FROM devices d3
    JOIN device_vulnerabilities dv3 ON d3.device_id = dv3.device_id
    JOIN vulnerabilities v3 ON dv3.vulnerability_id = v3.vulnerability_id
    WHERE d3.employee_id = e.manager_id
  )
GROUP BY e.employee_id, e.employee_name
```

## cybersecurity_incidents_schema DB 30 Q12

**Question:** Find devices whose latest alert is unresolved and whose vulnerability with the highest CVSS score has not been remediated.

**Status:** EXEC_OK | rows=0 | source=llm | family=latest_earliest_per_entity | conf=0.72 | guard=None | time=36.321s

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

**SQL:**
```sql
WITH ranked_alerts AS (
    SELECT 
        a.device_id,
        a.resolved,
        ROW_NUMBER() OVER (PARTITION BY a.device_id ORDER BY a.alert_time DESC) AS rn
    FROM alerts a
),
max_vuln AS (
    SELECT 
        dv.device_id,
        dv.remediated_date,
        v.cvss_score,
        ROW_NUMBER() OVER (PARTITION BY dv.device_id ORDER BY v.cvss_score DESC) AS rn
    FROM device_vulnerabilities dv
    JOIN vulnerabilities v ON dv.vulnerability_id = v.vulnerability_id
)
SELECT 
    d.device_id,
    d.hostname
FROM devices d
JOIN ranked_alerts ra ON d.device_id = ra.device_id
JOIN max_vuln mv ON d.device_id = mv.device_id
WHERE ra.rn = 1
  AND ra.resolved = '0'
  AND mv.rn = 1
  AND mv.remediated_date IS NULL
```

## cybersecurity_incidents_schema DB 30 Q13

**Question:** List employees who have devices with all vulnerability severities but have not passed every security training course.

**Status:** EXEC_OK | rows=0 | source=llm | family=set_division_count_distinct | conf=0.85 | guard=None | time=30.287s

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

**SQL:**
```sql
SELECT e.employee_id, e.employee_name
FROM employees e
JOIN devices d ON e.employee_id = d.employee_id
JOIN device_vulnerabilities dv ON d.device_id = dv.device_id
JOIN vulnerabilities v ON dv.vulnerability_id = v.vulnerability_id
JOIN training_records tr ON e.employee_id = tr.employee_id
GROUP BY e.employee_id, e.employee_name
HAVING COUNT(DISTINCT v.severity) = (SELECT COUNT(DISTINCT severity) FROM vulnerabilities)
   AND MAX(CASE WHEN tr.passed = 'false' THEN 1 ELSE 0 END) = 1
```

## cybersecurity_incidents_schema DB 30 Q14

**Question:** Find office cities where every employee either has no device or has at least one encrypted device.

**Status:** EXEC_OK | rows=0 | source=llm | family=universal_every_all | conf=0.82 | guard=None | time=29.652s

**Reason:** for-all via nested NOT EXISTS

**Flags:**
```json
{
  "has_count_distinct": false,
  "has_group_by": true,
  "has_having": true,
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
SELECT office_city
FROM employees
GROUP BY office_city
HAVING COUNT(*) = SUM(
    CASE
        WHEN NOT EXISTS (
            SELECT 1
            FROM devices
            WHERE devices.employee_id = employees.employee_id
        ) THEN 1
        WHEN EXISTS (
            SELECT 1
            FROM devices
            WHERE devices.employee_id = employees.employee_id
              AND devices.encrypted = 'yes'
        ) THEN 1
        ELSE 0
    END
)
```

## cybersecurity_incidents_schema DB 30 Q15

**Question:** List CVE codes where the highest CVSS occurrence was never remediated but a lower CVSS occurrence was remediated.

**Status:** EXEC_OK | rows=0 | source=llm | family=anti_exists | conf=0.8 | guard=None | time=24.865s

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
  )
  AND EXISTS (
    SELECT 1
    FROM vulnerabilities v3
    JOIN device_vulnerabilities dv3 ON v3.vulnerability_id = dv3.vulnerability_id
    WHERE v3.cve_code = v.cve_code
      AND v3.cvss_score < v.cvss_score
      AND dv3.remediated_date IS NOT NULL
  )
GROUP BY v.cve_code
```

## cybersecurity_incidents_schema DB 30 Q16

**Question:** Find employees whose devices triggered more distinct alert types than the number of distinct courses they passed.

**Status:** EXEC_OK | rows=0 | source=llm | family=count_distinct_comparison | conf=0.8 | guard=True | time=16.554s

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

**SQL:**
```sql
SELECT e.employee_id, e.employee_name
FROM employees e
JOIN devices d ON e.employee_id = d.employee_id
JOIN alerts a ON d.device_id = a.device_id
JOIN training_records tr ON e.employee_id = tr.employee_id
WHERE tr.passed = 'true'
GROUP BY e.employee_id, e.employee_name
HAVING COUNT(DISTINCT a.alert_type) > (
    SELECT COUNT(DISTINCT tr2.course_name)
    FROM training_records tr2
    WHERE tr2.employee_id = e.employee_id AND tr2.passed = 'true'
)
```

## cybersecurity_incidents_schema DB 30 Q17

**Question:** List incidents whose alerts come from devices owned by employees in a different office city than the employee who opened the incident.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=33.505s

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

**SQL:**
```sql
SELECT i.incident_id, i.incident_type, i.opened_time
FROM incidents i
JOIN incident_alerts ia ON i.incident_id = ia.incident_id
JOIN alerts a ON ia.alert_id = a.alert_id
JOIN devices d ON a.device_id = d.device_id
JOIN employees e_open ON i.opened_by_employee_id = e_open.employee_id
JOIN employees e_device ON d.employee_id = e_device.employee_id
WHERE e_open.office_city != e_device.office_city
```

## cybersecurity_incidents_schema DB 30 Q18

**Question:** Find devices with no vulnerabilities but with at least one high severity alert.

**Status:** EXEC_OK | rows=0 | source=llm | family=normal_join_filter_group | conf=0.3 | guard=None | time=22.169s

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

**Status:** EXEC_OK | rows=0 | source=llm | family=set_division_count_distinct | conf=0.85 | guard=None | time=26.628s

**Reason:** has/contains ALL members of a set (count-distinct division)

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
SELECT e.employee_id, e.employee_name
FROM employees e
JOIN devices d ON e.employee_id = d.employee_id
JOIN device_vulnerabilities dv ON d.device_id = dv.device_id
JOIN vulnerabilities v ON dv.vulnerability_id = v.vulnerability_id
GROUP BY e.employee_id, e.employee_name
HAVING MIN(d.last_patch_date) >= MAX(dv.detected_date)
```

## cybersecurity_incidents_schema DB 30 Q20

**Question:** Find departments where the same manager supervises both the highest risk and lowest risk employee in that department.

**Status:** EXEC_OK | rows=0 | source=llm | family=min_max_same_entity_per_group | conf=0.9 | guard=None | time=16.499s

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
