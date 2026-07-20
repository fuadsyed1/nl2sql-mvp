# Day 2 — Root-Cause Sample (<=24 representative failures)

_Read-only analysis over frozen Day 1 artifacts. Balanced 6 per priority pattern, spread across databases and difficulties. Failure origin is inferred generically (not per-test)._

## wrong_filter_or_placement — DB54 test 452 (subquery_cte/easy)

- **Question:** List suppliers whose annual revenue is above the overall supplier average.
- **Audit reason:** Aggregates the entire supplier table with HAVING and does not compare each supplier's revenue with the overall average.
- **Selected SQL:** `SELECT "suppliers"."supplier_name", "suppliers"."annual_revenue", AVG("suppliers"."annual_revenue") AS "avg_revenue" FROM "suppliers" HAVING "avg_revenue" < ?`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 62.0): `SELECT "suppliers"."supplier_id", "suppliers"."supplier_name", "suppliers"."annual_revenue", AVG("suppliers"."annual_revenue") AS "avg_revenue" FROM "suppliers" HAVING "avg_revenue" < ? normalized_sql`
- **Plausible alt 2** (score 29.0): `SELECT supplier_id, supplier_name, annual_revenue FROM suppliers WHERE annual_revenue > (SELECT AVG(annual_revenue) FROM suppliers) normalized_sql: SELECT supplier_id, supplier_name, annual_revenue FR`

## wrong_filter_or_placement — DB55 test 314 (multi_table_join/easy)

- **Question:** Show each program with department name and number of active students.
- **Audit reason:** Counts all students in each program and never filters to active students.
- **Selected SQL:** `SELECT p.program_name, d.department_name, COUNT(DISTINCT s.student_id) AS student_count FROM programs p JOIN departments d ON p.department_id = d.department_id JOIN students s ON p.program_id = s.program_id GROUP BY p.program_id, p.program_name, d.department_name HAVING COUNT(DIS`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 52.0): `SELECT "programs"."program_id", "programs"."program_name", "departments"."department_name", "students"."student_id", COUNT(*) AS "active_student_count" FROM "programs" LEFT JOIN "departments" ON "prog`
- **Plausible alt 2** (score 52.0): `SELECT p.program_name, d.department_name, COUNT(s.student_id) AS student_count FROM programs p JOIN departments d ON p.department_id = d.department_id JOIN students s ON p.program_id = s.program_id GR`

## wrong_filter_or_placement — DB56 test 55 (derived_metric/easy)

- **Question:** Show each doctor with the number of years remaining until license expiration.
- **Audit reason:** Adds an unrequested active-doctor filter, so it does not show each doctor.
- **Selected SQL:** `SELECT      d.doctor_id,     d.first_name,     d.last_name,     d.license_expiration_date,     CAST((julianday(d.license_expiration_date) - julianday('now')) / 365.25 AS INTEGER) AS years_remaining FROM doctors d WHERE d.active_flag = '1' ORDER BY years_remaining ASC`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 83.0): `SELECT      d.doctor_id,     d.first_name,     d.last_name,     d.license_expiration_date,     CAST((julianday(d.license_expiration_date) - julianday('now')) / 365.25 AS INTEGER) AS years_remaining FR`
- **Plausible alt 2** (score 68.0): `SELECT "doctors"."doctor_id", "doctors"."first_name", "doctors"."last_name", "doctors"."license_expiration_date" FROM "doctors" normalized_sql: SELECT "doctors"."doctor_id", "doctors"."first_name", "d`

## wrong_filter_or_placement — DB54 test 291 (join/hard)

- **Question:** List order items whose unit price is lower than the product’s current sale price.
- **Audit reason:** Adds an unrequested discontinued_flag = 0 restriction.
- **Selected SQL:** `SELECT soi.order_item_id, soi.order_id, soi.product_id, soi.unit_price, p.sale_price FROM sales_order_items soi JOIN products p ON soi.product_id = p.product_id WHERE soi.unit_price < p.sale_price AND p.discontinued_flag = '0'`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 94.0): `SELECT "sales_order_items"."order_item_id", "sales_order_items"."order_id", "sales_order_items"."product_id", "sales_order_items"."unit_price", "products"."sale_price" FROM "sales_order_items" INNER J`
- **Plausible alt 2** (score 94.0): `SELECT soi.order_item_id, soi.order_id, soi.product_id, soi.unit_price, p.sale_price FROM sales_order_items soi JOIN products p ON soi.product_id = p.product_id WHERE soi.unit_price < p.sale_price nor`

## wrong_filter_or_placement — DB54 test 445 (set_operations/hard)

- **Question:** List product categories supplied by both high-risk and low-risk suppliers but not by medium-risk suppliers.
- **Audit reason:** Only excludes medium-risk suppliers; it never requires each category to have both high- and low-risk suppliers.
- **Selected SQL:** `SELECT DISTINCT "products"."category" FROM "products" INNER JOIN "suppliers" ON "products"."supplier_id" = "suppliers"."supplier_id" WHERE NOT EXISTS (SELECT 1 FROM "suppliers" WHERE "products"."supplier_id" = "suppliers"."supplier_id" AND "suppliers"."risk_level" = ?)`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 82.0): `SELECT DISTINCT "products"."category", COUNT("suppliers"."supplier_id") AS "high_low_count", COUNT("suppliers"."supplier_id") AS "medium_count" FROM "products" INNER JOIN "suppliers" ON "products"."su`
- **Plausible alt 2** (score 70.0): `SELECT p.category FROM products p JOIN suppliers s ON p.supplier_id = s.supplier_id GROUP BY p.category HAVING COUNT(DISTINCT CASE WHEN s.risk_level = 'high' THEN 1 END) > 0    AND COUNT(DISTINCT CASE`

## wrong_filter_or_placement — DB55 test 142 (distinct_count/hard)

- **Question:** How many distinct programs have students advised by instructors from the same department as the program?
- **Audit reason:** Adds an unrequested academic-advising appointment requirement, excluding otherwise qualifying assigned-advisor relationships.
- **Selected SQL:** `SELECT COUNT(DISTINCT p.program_id) FROM programs p JOIN students s ON p.program_id = s.program_id JOIN instructors i ON s.advisor_instructor_id = i.instructor_id JOIN departments d ON i.department_id = d.department_id JOIN academic_advising aa ON s.student_id = aa.student_id WHE`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 66.0): `SELECT DISTINCT "programs"."program_id" FROM "academic_advising" INNER JOIN "instructors" ON "academic_advising"."instructor_id" = "instructors"."instructor_id" INNER JOIN "programs" ON "academic_advi`

## missing_metric_or_output — DB54 test 52 (derived_metric/easy)

- **Question:** Show each product with the discount amount from list price to sale price.
- **Audit reason:** Returns list and sale prices but never calculates their difference.
- **Selected SQL:** `SELECT product_id, product_name, list_price, sale_price FROM products`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 73.0): `SELECT "products"."product_name", "products"."list_price", "products"."sale_price" FROM "products" normalized_sql: SELECT "products"."product_name", "products"."list_price", "products"."sale_price" FR`
- **Plausible alt 2** (score 73.0): `SELECT "products"."product_name", "products"."list_price", "products"."sale_price", "products"."list_price" AS "discount_amount" FROM "products" normalized_sql: SELECT "products"."product_name", "prod`

## missing_metric_or_output — DB54 test 211 (having/easy)

- **Question:** List product categories with an average markup percentage above 40 percent.
- **Audit reason:** Checks only average unit price > average unit cost; it never calculates or tests a 40% markup.
- **Selected SQL:** `SELECT "products"."category", AVG("sales_order_items"."unit_price") AS "avg_price", AVG("sales_order_items"."unit_cost") AS "avg_cost" FROM "products" INNER JOIN "sales_order_items" ON "products"."product_id" = "sales_order_items"."product_id" GROUP BY "products"."category" HAVIN`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 100.0): `SELECT p.category FROM products p JOIN sales_order_items soi ON p.product_id = soi.product_id GROUP BY p.category HAVING AVG((soi.unit_price - soi.unit_cost) * 100.0 / soi.unit_cost) > 40 normalized_s`
- **Plausible alt 2** (score 100.0): `SELECT p.category FROM products p JOIN sales_order_items soi ON p.product_id = soi.product_id GROUP BY p.category HAVING AVG((soi.unit_price - soi.unit_cost) / soi.unit_cost * 100) > 40 normalized_sql`

## missing_metric_or_output — DB55 test 52 (derived_metric/easy)

- **Question:** Show each department with its annual budget per enrolled department student.
- **Audit reason:** Returns annual budget and enrollment totals but never divides budget by enrolled students.
- **Selected SQL:** `SELECT "departments"."department_id", "departments"."department_name", "departments"."annual_budget", SUM("programs"."current_enrollment") AS "total_enrolled_students" FROM "departments" INNER JOIN "programs" ON "departments"."department_id" = "programs"."department_id" GROUP BY `
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 100.0): `SELECT d.department_name, d.annual_budget, d.student_count FROM departments d GROUP BY d.department_id HAVING d.student_count > 0 normalized_sql: SELECT d.department_name, d.annual_budget, d.student_c`
- **Plausible alt 2** (score 100.0): `SELECT d.department_name, d.annual_budget, d.student_count FROM departments d GROUP BY d.department_id, d.department_name, d.annual_budget, d.student_count HAVING d.student_count > 0 normalized_sql: S`

## missing_metric_or_output — DB55 test 59 (derived_metric/easy)

- **Question:** Show each student with the percentage of 120 credits they have completed.
- **Audit reason:** Labels raw credits as a percentage and never divides credits earned by 120.
- **Selected SQL:** `SELECT "students"."student_id", "students"."first_name", "students"."last_name", "students"."credits_earned", "students"."credits_earned" AS "percentage_of_120", SUM("enrollments"."credits_earned") AS "total_credits_earned" FROM "students" INNER JOIN "enrollments" ON "students"."`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 91.0): `SELECT "students"."student_id", "students"."first_name", "students"."last_name", "students"."credits_earned", "students"."credits_earned" AS "percentage_of_120", SUM("enrollments"."credits_earned") AS`
- **Plausible alt 2** (score 76.0): `SELECT "students"."student_id", "students"."first_name", "students"."last_name", "students"."credits_earned", "students"."credits_earned" AS "percentage_of_120" FROM "students" normalized_sql: SELECT `

## missing_metric_or_output — DB55 test 310 (multi_table_join/easy)

- **Question:** Show each course with prerequisite title and department name.
- **Audit reason:** Returns the current course title twice and omits the prerequisite title.
- **Selected SQL:** `SELECT c.course_title, c.course_title AS course_title, d.department_name FROM courses c JOIN departments d ON c.department_id = d.department_id JOIN courses p ON c.prerequisite_course_id = p.course_id`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 100.0): `SELECT "c"."course_title" AS "course_title", "c"."course_code" AS "course_code", "c"."course_id" AS "course_id", "c"."prerequisite_course_id" AS "prerequisite_course_id", "p"."course_title" AS "prereq`
- **Plausible alt 2** (score 100.0): `SELECT c.course_title, c.course_title AS course_title, d.department_name FROM courses c JOIN courses pc ON c.prerequisite_course_id = pc.course_id JOIN departments d ON c.department_id = d.department_`

## missing_metric_or_output — DB55 test 405 (set_operations/easy)

- **Question:** List course identifiers that appear either in enrollments or attendance records.
- **Audit reason:** Returns only courses present in linked enrollment-and-attendance rows instead of the union of both sources.
- **Selected SQL:** `SELECT DISTINCT "courses"."course_id", "courses"."course_title" FROM "attendance_records" INNER JOIN "courses" ON "attendance_records"."course_id" = "courses"."course_id" INNER JOIN "enrollments" ON "attendance_records"."enrollment_id" = "enrollments"."enrollment_id"`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 99.0): `SELECT DISTINCT c.course_id FROM courses c JOIN enrollments e ON c.course_id = e.course_id JOIN attendance_records ar ON c.course_id = ar.course_id normalized_sql: SELECT DISTINCT c.course_id FROM cou`
- **Plausible alt 2** (score 99.0): `SELECT DISTINCT c.course_id FROM courses c JOIN enrollments e ON c.course_id = e.course_id JOIN attendance_records a ON c.course_id = a.course_id normalized_sql: SELECT DISTINCT c.course_id FROM cours`

## aggregation_or_formula_error — DB54 test 460 (subquery_cte/easy)

- **Question:** List warehouses that have never fulfilled an order item.
- **Audit reason:** Treats any assigned order item as a fulfillment and does not check fulfillment_status.
- **Selected SQL:** `SELECT w.warehouse_id, w.warehouse_name FROM warehouses w WHERE NOT EXISTS ( SELECT 1 FROM sales_order_items soi WHERE soi.warehouse_id = w.warehouse_id )`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 64.0): `SELECT "warehouses"."warehouse_id" FROM "warehouses" WHERE NOT EXISTS (SELECT 1 FROM "sales_order_items" WHERE "sales_order_items"."warehouse_id" = "warehouses"."warehouse_id") normalized_sql: SELECT `
- **Plausible alt 2** (score 49.0): `SELECT "warehouses"."warehouse_id", "warehouses"."warehouse_name" FROM "warehouses" INNER JOIN "sales_order_items" ON "warehouses"."warehouse_id" = "sales_order_items"."warehouse_id" WHERE NOT EXISTS `

## aggregation_or_formula_error — DB55 test 51 (derived_metric/easy)

- **Question:** Show each department with the number of employees formed by adding its faculty count and staff count.
- **Audit reason:** Returns separate faculty and staff sums with the same alias instead of adding faculty_count and staff_count.
- **Selected SQL:** `SELECT "departments"."department_name", SUM("departments"."faculty_count") AS "total_employees", SUM("departments"."staff_count") AS "total_employees" FROM "departments" GROUP BY "departments"."department_name"`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 93.0): `SELECT department_name, faculty_count, staff_count FROM departments GROUP BY department_id normalized_sql: SELECT department_name, faculty_count, staff_count FROM departments GROUP BY department_id`
- **Plausible alt 2** (score 85.0): `SELECT "departments"."department_name", SUM("departments"."faculty_count") AS "total_employees", SUM("departments"."staff_count") AS "total_employees_add" FROM "departments" GROUP BY "departments"."de`

## aggregation_or_formula_error — DB56 test 51 (derived_metric/easy)

- **Question:** Show each department with the number of unused beds based on bed capacity minus current occupancy.
- **Audit reason:** Sums bed_capacity instead of calculating bed_capacity - current_occupancy.
- **Selected SQL:** `SELECT "departments"."department_name", "departments"."bed_capacity", "departments"."current_occupancy", SUM("departments"."bed_capacity") AS "unused_beds" FROM "departments" GROUP BY "departments"."department_name"`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 88.0): `SELECT      d.department_name,      d.bed_capacity,      d.current_occupancy,     (d.bed_capacity - d.current_occupancy) AS unused_beds FROM departments d GROUP BY d.department_id normalized_sql: SELE`
- **Plausible alt 2** (score 88.0): `SELECT department_name, bed_capacity, current_occupancy, (bed_capacity - current_occupancy) AS unused_beds FROM departments GROUP BY department_id normalized_sql: SELECT department_name, bed_capacity,`

## aggregation_or_formula_error — DB57 test 58 (derived_metric/easy)

- **Question:** Show each coach with total matches coached based on wins, losses, and draws.
- **Audit reason:** Returns separate sums of wins, losses, and draws instead of adding them into total matches coached.
- **Selected SQL:** `SELECT "coaches"."coach_id", "coaches"."first_name", "coaches"."last_name", SUM("coaches"."wins") AS "total_wins", SUM("coaches"."losses") AS "total_losses", SUM("coaches"."draws") AS "total_draws", SUM("coaches"."wins") AS "total_matches_coached", SUM("coaches"."losses") AS "tot`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 87.0): `SELECT "coaches"."coach_id", "coaches"."first_name", "coaches"."last_name", "coaches"."wins", "coaches"."losses", "coaches"."draws" FROM "coaches" GROUP BY "coaches"."coach_id", "coaches"."first_name"`
- **Plausible alt 2** (score 87.0): `SELECT   c.coach_id,   c.first_name,   c.last_name,   c.wins,   c.losses,   c.draws FROM coaches c GROUP BY c.coach_id normalized_sql: SELECT   c.coach_id,   c.first_name,   c.last_name,   c.wins,   c`

## aggregation_or_formula_error — DB54 test 37 (aggregation/hard)

- **Question:** What is the total shipped gross profit from products supplied by low-risk suppliers, fulfilled by open warehouses, and sold on delivered orders?
- **Audit reason:** The shipped-profit formula mixes full line revenue with shipped quantity and product standard cost.
- **Selected SQL:** `SELECT SUM(soi.line_total - soi.quantity_shipped * p.standard_cost) AS total_shipped_gross_profit FROM sales_order_items soi JOIN products p ON soi.product_id = p.product_id JOIN suppliers s ON p.supplier_id = s.supplier_id JOIN sales_orders so ON soi.order_id = so.order_id JOIN `
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 100.0): `SELECT SUM(soi.line_total - soi.quantity_shipped * p.standard_cost) AS total_shipped_gross_profit FROM sales_order_items soi JOIN products p ON soi.product_id = p.product_id JOIN sales_orders so ON so`
- **Plausible alt 2** (score 100.0): `SELECT SUM(s.line_total - s.quantity_shipped * p.standard_cost) AS total_shipped_gross_profit FROM sales_order_items s JOIN products p ON s.product_id = p.product_id JOIN sales_orders so ON s.order_id`

## aggregation_or_formula_error — DB54 test 90 (derived_metric/hard)

- **Question:** For each product category, calculate total gross profit divided by total line revenue.
- **Audit reason:** Uses line_total - line_subtotal as profit and divides by line_subtotal rather than line revenue.
- **Selected SQL:** `SELECT p.category, SUM(soi.line_total - soi.line_subtotal) * 1.0 / SUM(soi.line_subtotal) AS profit_margin FROM products p JOIN sales_order_items soi ON p.product_id = soi.product_id GROUP BY p.category`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 84.0): `SELECT "products"."category", SUM("sales_order_items"."line_total") AS "total_line_revenue", SUM("sales_order_items"."line_subtotal") AS "total_line_subtotal", SUM("sales_order_items"."tax_amount") AS`
- **Plausible alt 2** (score 84.0): `SELECT p.category, SUM(soi.line_total - soi.line_subtotal) * 1.0 / SUM(soi.line_subtotal) AS gross_profit_margin FROM products p JOIN sales_order_items soi ON p.product_id = soi.product_id GROUP BY p.`

## set_logic_error — DB54 test 462 (subquery_cte/easy)

- **Question:** List customers who have never placed a delivered order.
- **Audit reason:** The inner join excludes customers with no orders, although they also have never placed a delivered order.
- **Selected SQL:** `SELECT c.customer_id, c.first_name, c.last_name FROM customers c JOIN sales_orders so ON c.customer_id = so.customer_id WHERE NOT EXISTS ( SELECT 1 FROM sales_orders so2 WHERE so2.customer_id = c.customer_id AND so2.order_status = 'delivered' ) GROUP BY c.customer_id, c.first_nam`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 100.0): `SELECT c.customer_id, c.first_name, c.last_name FROM customers c WHERE NOT EXISTS (     SELECT 1     FROM sales_orders so     WHERE so.customer_id = c.customer_id       AND so.order_status = 'delivere`
- **Plausible alt 2** (score 55.0): `SELECT "customers"."customer_id", "customers"."first_name" FROM "customers" WHERE NOT EXISTS (SELECT 1 FROM "sales_orders" WHERE "sales_orders"."customer_id" = "customers"."customer_id") normalized_sq`

## set_logic_error — DB55 test 58 (derived_metric/easy)

- **Question:** Show each student with the number of credits still needed to reach 120 credits.
- **Audit reason:** Excludes students with 120 or more credits even though the request asks for each student.
- **Selected SQL:** `SELECT student_id, first_name, last_name, 120 - credits_earned AS credits_needed FROM students WHERE credits_earned < 120`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 70.0): `SELECT "students"."student_id", "students"."first_name", "students"."last_name", "students"."credits_earned", "students"."credits_earned" AS "credits_needed" FROM "students" normalized_sql: SELECT "st`

## set_logic_error — DB55 test 407 (set_operations/easy)

- **Question:** List program identifiers that appear either in student records or course records.
- **Audit reason:** Uses inner joins, returning programs present in both students and courses instead of either source.
- **Selected SQL:** `SELECT DISTINCT p.program_id FROM programs p JOIN students s ON p.program_id = s.program_id JOIN courses c ON p.program_id = c.program_id`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 89.0): `SELECT DISTINCT "students"."program_id", "courses"."program_id" FROM "students" INNER JOIN "programs" ON "students"."program_id" = "programs"."program_id" INNER JOIN "courses" ON "programs"."program_i`

## set_logic_error — DB56 test 401 (set_operations/easy)

- **Question:** List doctor identifiers that appear either as primary doctors or appointment doctors.
- **Audit reason:** Uses inner joins, returning doctors present in both sources instead of either source.
- **Selected SQL:** `SELECT DISTINCT d.doctor_id FROM doctors d JOIN patients p ON d.doctor_id = p.primary_doctor_id JOIN appointments a ON d.doctor_id = a.doctor_id`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 84.0): `SELECT DISTINCT "doctors"."doctor_id" FROM "appointments" INNER JOIN "doctors" ON "appointments"."doctor_id" = "doctors"."doctor_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."`
- **Plausible alt 2** (score 73.0): `SELECT DISTINCT "doctors"."doctor_id" FROM "doctors" INNER JOIN "appointments" ON "doctors"."doctor_id" = "appointments"."doctor_id" normalized_sql: SELECT DISTINCT "doctors"."doctor_id" FROM "doctors`

## set_logic_error — DB56 test 403 (set_operations/easy)

- **Question:** List patient identifiers that appear either in appointments or billing claims.
- **Audit reason:** Uses an appointment-to-claim inner join, returning only patients appearing in both sources.
- **Selected SQL:** `SELECT DISTINCT "patients"."patient_id", "patients"."first_name" FROM "appointments" INNER JOIN "billing_claims" ON "appointments"."appointment_id" = "billing_claims"."appointment_id" INNER JOIN "patients" ON "appointments"."patient_id" = "patients"."patient_id"`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 84.0): `SELECT DISTINCT p.patient_id FROM patients p JOIN appointments a ON p.patient_id = a.patient_id JOIN billing_claims b ON p.patient_id = b.patient_id normalized_sql: SELECT DISTINCT p.patient_id FROM p`

## set_logic_error — DB56 test 404 (set_operations/easy)

- **Question:** List appointment identifiers that appear either in diagnoses or lab tests.
- **Audit reason:** Uses inner joins, returning appointments present in both diagnoses and lab tests instead of either source.
- **Selected SQL:** `SELECT DISTINCT a.appointment_id FROM appointments a JOIN diagnoses d ON a.appointment_id = d.appointment_id JOIN lab_tests l ON a.appointment_id = l.appointment_id`
- **Likely origin:** selection/generation (a clean differing candidate existed)
- **Plausible alt 1** (score 93.0): `SELECT DISTINCT "diagnoses"."appointment_id", "lab_tests"."appointment_id" FROM "diagnoses" INNER JOIN "appointments" ON "diagnoses"."appointment_id" = "appointments"."appointment_id" INNER JOIN "lab_`
- **Plausible alt 2** (score 90.0): `SELECT DISTINCT "appointments"."appointment_id" FROM "appointments" INNER JOIN "diagnoses" ON "appointments"."appointment_id" = "diagnoses"."appointment_id" INNER JOIN "lab_tests" ON "appointments"."a`

