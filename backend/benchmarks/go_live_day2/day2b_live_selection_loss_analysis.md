# Day 2B LIVE — Selection-loss (A: correct candidate generated but not selected)

_Trace-verified against the EXACT Day 2 live rerun traces (day2_targeted_full_trace_db54..57). Candidate semantics judged manually per query. Totals: A(not-selected)=9, B(rejected)=0, C(no-correct)=12._

**9 cases.** A semantically correct candidate is present in the Day 2 trace, executed cleanly, and was not selected.

### DB55 test 51 — aggregation_or_formula_error (easy)
- **Question:** Show each department with the number of employees formed by adding its faculty count and staff count.
- **Day 2 selected (wrong):** `llm_primary` score 85.0 — Selected llm_primary sums faculty_count and staff_count into two columns sharing one alias; it never adds them.
  - `SELECT "departments"."department_name", SUM("departments"."faculty_count") AS "total_employees", SUM("departments"."staff_count") AS "total_employees" FROM "departments" GROUP BY "departments"."department_name"`
- **Correct Day 2 candidate:** `llm_sql_direct_variant` score 93.0
  - `SELECT department_name, faculty_count, staff_count, faculty_count + staff_count AS number_of_employees FROM departments GROUP BY department_id`
- **Fatal/rejection state:** none (executed clean, fatal_count=0, not selected)
- **Why the correct candidate lost:** cand6 computes faculty_count + staff_count (score 93, ABOVE the selected 85) and executed cleanly, but the correlated 3-member llm_primary/variant family won consensus and the direct family's effective score was its base (78), so the computing candidate was not chosen.
- **Likely generic fix layer:** consensus / selector
- **Prior Day1-pool label:** no_correct_candidate_generated  (CHANGED)

### DB56 test 51 — aggregation_or_formula_error (easy)
- **Question:** Show each department with the number of unused beds based on bed capacity minus current occupancy.
- **Day 2 selected (wrong):** `llm_sql_direct` score 73.0 — Selected llm_sql_direct returns bed_capacity and current_occupancy as plain columns (score 73); it never subtracts.
  - `SELECT department_name, bed_capacity, current_occupancy FROM departments`
- **Correct Day 2 candidate:** `llm_sql_direct_grain` score 88.0
  - `SELECT department_name, bed_capacity, current_occupancy, (bed_capacity - current_occupancy) AS unused_beds FROM departments GROUP BY department_id`
- **Fatal/rejection state:** none (executed clean, fatal_count=0, not selected)
- **Why the correct candidate lost:** cand4/5/6 compute (bed_capacity - current_occupancy) AS unused_beds (score 88) and repair also reached 88, yet best_scored_executed kept the lower-scored plain-column direct candidate.
- **Likely generic fix layer:** selector / scorer
- **Prior Day1-pool label:** correct_candidate_generated_but_not_selected  (unchanged)

### DB55 test 52 — missing_metric_or_output (easy)
- **Question:** Show each department with its annual budget per enrolled department student.
- **Day 2 selected (wrong):** `llm_sql_repair` score 100.0 — Selected llm_sql_repair returns annual_budget and student_count but the final projection performs no division (score 100).
  - `WITH dept_agg AS ( SELECT department_id, SUM(annual_budget) AS total_annual_budget, SUM(student_count) AS total_student_count FROM departments GROUP BY department_id ) SELECT d.department_name, d.annual_budget, d.student_count FROM departments d JOIN dept_agg da ON d.department_i`
- **Correct Day 2 candidate:** `llm_sql_direct` score 82.0
  - `SELECT d.department_name, d.annual_budget, d.student_count, CAST(d.annual_budget AS REAL) / NULLIF(d.student_count, 0) AS annual_budget_per_student FROM departments d GROUP BY d.department_id, d.department_name, d.annual_budget, d.student_count`
- **Fatal/rejection state:** none (executed clean, fatal_count=0, not selected)
- **Why the correct candidate lost:** cand4/5/6 compute CAST(annual_budget AS REAL)/NULLIF(student_count,0) (score 82); the repair candidate was over-rewarded to 100 while the ratio candidates were under-scored, so the dividing candidate lost. (Denominator column student_count is a defensible reading of 'enrolled department student'.)
- **Likely generic fix layer:** scorer / repair
- **Prior Day1-pool label:** no_correct_candidate_generated  (CHANGED)

### DB54 test 211 — missing_metric_or_output (easy)
- **Question:** List product categories with an average markup percentage above 40 percent.
- **Day 2 selected (wrong):** `llm_variant_2` score 100.0 — Selected llm_variant tests AVG(unit_price) > threshold and never computes or tests a markup percentage (score 100).
  - `SELECT "products"."category", AVG("sales_order_items"."unit_price") AS "avg_price", AVG("sales_order_items"."unit_cost") AS "avg_cost" FROM "products" INNER JOIN "sales_order_items" ON "products"."product_id" = "sales_order_items"."product_id" GROUP BY "products"."category" HAVIN`
- **Correct Day 2 candidate:** `llm_sql_direct` score 100.0
  - `SELECT p.category FROM products p JOIN sales_order_items soi ON p.product_id = soi.product_id GROUP BY p.category HAVING AVG((CAST(soi.unit_price AS REAL) - CAST(soi.unit_cost AS REAL)) / NULLIF(CAST(soi.unit_cost AS REAL), 0)) * 100 > 40`
- **Fatal/rejection state:** none (executed clean, fatal_count=0, not selected)
- **Why the correct candidate lost:** cand4/5/6 compute HAVING AVG((unit_price-unit_cost)/unit_cost)*100 > 40 (score 100, TIED with the wrong candidate); the tie-break/order selected the non-computing candidate because the scorer cannot separate them.
- **Likely generic fix layer:** scorer / selector
- **Prior Day1-pool label:** no_correct_candidate_generated  (CHANGED)

### DB54 test 452 — wrong_filter_or_placement (easy)
- **Question:** List suppliers whose annual revenue is above the overall supplier average.
- **Day 2 selected (wrong):** `llm_variant_1` score 62.0 — Selected llm_variant aggregates the whole table with AVG in HAVING and returns 0 rows (score 62).
  - `SELECT "suppliers"."supplier_name", AVG("suppliers"."annual_revenue") AS "avg_revenue" FROM "suppliers" HAVING "avg_revenue" > ?`
- **Correct Day 2 candidate:** `llm_sql_direct` score 29.0
  - `SELECT s.supplier_id, s.supplier_name, s.annual_revenue FROM suppliers s WHERE s.annual_revenue > (SELECT AVG(annual_revenue) FROM suppliers)`
- **Fatal/rejection state:** soft-rejected (scored, not fatal): grain violation: contract requires SUM(suppliers.annual_revenue) per suppliers.supplier_id, but the SQL compares the raw row-level value suppliers.annual_revenue and never computes SUM(annual_revenue) | grain violation: the comparison uses AVG(suppliers.annual_revenue) over raw rows where a SUM of per-entity totals per suppliers.supplier_id is required — an average of raw rows is a different scale than a total of per-entity SUMs
- **Why the correct candidate lost:** cand4-7 use WHERE annual_revenue > (SELECT AVG(annual_revenue) FROM suppliers) (31 rows) but a grain semantic-contract false-positive ('requires SUM(annual_revenue) per supplier_id') penalised every correct candidate to score 29, so the wrong aggregate outranked them.
- **Likely generic fix layer:** semantic contract / scorer
- **Prior Day1-pool label:** correct_candidate_generated_but_not_selected  (unchanged)

### DB56 test 55 — wrong_filter_or_placement (easy)
- **Question:** Show each doctor with the number of years remaining until license expiration.
- **Day 2 selected (wrong):** `llm_sql_repair` score 68.0 — Selected llm_sql_repair (via consensus_group) returns doctor columns with NO years_remaining expression (score 68).
  - `SELECT doctor_id, first_name, last_name, license_expiration_date FROM doctors`
- **Correct Day 2 candidate:** `llm_sql_direct_grain` score 68.0
  - `SELECT doctor_id, first_name, last_name, license_expiration_date, CAST((julianday(license_expiration_date) - julianday('now')) / 365.25 AS INTEGER) AS years_remaining FROM doctors`
- **Fatal/rejection state:** none (executed clean, fatal_count=0, not selected)
- **Why the correct candidate lost:** cand3/cand4 compute (julianday(license_expiration_date)-julianday('now'))/365.25 for all 80 doctors (score 68, tied); consensus_group chose the no-computation repair over the computing candidates.
- **Likely generic fix layer:** consensus / selector
- **Prior Day1-pool label:** no_correct_candidate_generated  (CHANGED)

### DB55 test 142 — wrong_filter_or_placement (hard)
- **Question:** How many distinct programs have students advised by instructors from the same department as the program?
- **Day 2 selected (wrong):** `llm_sql_direct_grain` score 100.0 — Selected llm_sql_direct_grain adds an INNER JOIN academic_advising, imposing an unrequested advising-appointment restriction (score 100).
  - `SELECT COUNT(DISTINCT p.program_id) FROM programs p JOIN students s ON p.program_id = s.program_id JOIN instructors i ON s.advisor_instructor_id = i.instructor_id JOIN departments d ON i.department_id = d.department_id JOIN academic_advising aa ON s.student_id = aa.student_id WHE`
- **Correct Day 2 candidate:** `llm_sql_direct_variant` score 100.0
  - `SELECT COUNT(DISTINCT p.program_id) FROM programs p JOIN students s ON p.program_id = s.program_id JOIN instructors i ON s.advisor_instructor_id = i.instructor_id JOIN departments dp ON i.department_id = dp.department_id JOIN departments dp2 ON p.department_id = dp2.department_id`
- **Fatal/rejection state:** none (executed clean, fatal_count=0, not selected)
- **Why the correct candidate lost:** cand6 links student->advisor via students.advisor_instructor_id with no academic_advising join (score 100, tied); the scorer cannot penalise the spurious join, so the restricted variant was selected.
- **Likely generic fix layer:** scorer / semantic contract
- **Prior Day1-pool label:** no_correct_candidate_generated  (CHANGED)

### DB54 test 434 — set_logic_error (moderate)
- **Question:** List product categories sold in 2025 but not in 2024.
- **Day 2 selected (wrong):** `llm_sql_direct` score 100.0 — Selected llm_sql_direct anti-joins at PRODUCT grain (NOT EXISTS same product_id in 2024), so a category still appears via its other products (score 100).
  - `SELECT DISTINCT p.category FROM products p JOIN sales_order_items soi ON p.product_id = soi.product_id JOIN sales_orders so ON soi.order_id = so.order_id WHERE strftime('%Y', so.order_date) = '2025' AND NOT EXISTS ( SELECT 1 FROM sales_order_items soi2 JOIN sales_orders so2 ON so`
- **Correct Day 2 candidate:** `llm_sql_direct_variant` score 88.0
  - `SELECT p.category FROM products p JOIN sales_order_items soi ON p.product_id = soi.product_id JOIN sales_orders so ON soi.order_id = so.order_id WHERE p.category IS NOT NULL GROUP BY p.category HAVING NOT EXISTS ( SELECT 1 FROM sales_order_items soi2 JOIN sales_orders so2 ON soi2`
- **Fatal/rejection state:** none (executed clean, fatal_count=0, not selected)
- **Why the correct candidate lost:** cand6 anti-joins at CATEGORY grain (p2.category = p.category), the correct EXCEPT semantics, but returned 0 rows; the empty-result penalty dropped it to score 88, below the wrong product-grain candidate at 100. (Empty result is a data-dependent caveat; the set logic is correct.)
- **Likely generic fix layer:** scorer
- **Prior Day1-pool label:** no_correct_candidate_generated  (CHANGED)

### DB56 test 403 — set_logic_error (easy)
- **Question:** List patient identifiers that appear either in appointments or billing claims.
- **Day 2 selected (wrong):** `llm_primary` score 84.0 — Selected llm_primary INNER JOINs appointments to billing_claims, returning only patients in BOTH sources (score 84).
  - `SELECT DISTINCT "patients"."patient_id", "patients"."first_name" FROM "appointments" INNER JOIN "billing_claims" ON "appointments"."appointment_id" = "billing_claims"."appointment_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id"`
- **Correct Day 2 candidate:** `llm_sql_direct` score 59.0
  - `SELECT DISTINCT p.patient_id FROM patients p JOIN appointments a ON p.patient_id = a.patient_id UNION SELECT DISTINCT p.patient_id FROM patients p JOIN billing_claims b ON p.patient_id = b.patient_id`
- **Fatal/rejection state:** none (executed clean, fatal_count=0, not selected)
- **Why the correct candidate lost:** cand2/cand4 use UNION of the two sources ('either'), 62 rows, but were scored only 59; the scorer under-valued the UNION set semantics versus the wrong INNER join.
- **Likely generic fix layer:** scorer / set-semantics
- **Prior Day1-pool label:** no_correct_candidate_generated  (CHANGED)
