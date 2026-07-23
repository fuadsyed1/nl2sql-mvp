# Day 2B LIVE — No-correct-candidate (C)

_Trace-verified against the EXACT Day 2 live rerun traces (day2_targeted_full_trace_db54..57). Candidate semantics judged manually per query. Totals: A(not-selected)=9, B(rejected)=0, C(no-correct)=12._

**12 cases.** No candidate in the exact Day 2 trace fully satisfies the question (executable SQL is not automatically correct; each was checked for formula, filters, grouping grain, set logic, distinctness, and population).

By pattern: aggregation_or_formula_error=5, missing_metric_or_output=1, wrong_filter_or_placement=3, set_logic_error=3

### DB57 test 58 — aggregation_or_formula_error
- **Question:** Show each coach with total matches coached based on wins, losses, and draws.
- **Day 2 selected (wrong):** `llm_sql_direct_grain` score 72.0 — Selected candidate lists wins, losses, draws separately and never adds them.
  - `SELECT coach_id, first_name, last_name, wins, losses, draws FROM coaches`
- **Why no Day 2 candidate is correct:** No Day 2 candidate computes wins + losses + draws; the paraphrased-addition obligation ('total matches ... based on wins, losses, and draws') was never generated.
- **Audit finding:** Returns separate sums of wins, losses, and draws instead of adding them into total matches coached.
- **Likely generic fix layer:** generation / semantic contract
- **Prior Day1-pool label:** no_correct_candidate_generated  (unchanged)

### DB54 test 37 — aggregation_or_formula_error
- **Question:** What is the total shipped gross profit from products supplied by low-risk suppliers, fulfilled by open warehouses, and sold on delivered orders?
- **Day 2 selected (wrong):** `llm_sql_direct_variant` score 100.0 — Selected shipped-profit formula subtracts shipped-quantity cost from the FULL line_total revenue (mismatched basis).
  - `SELECT SUM(soi.line_total - (soi.quantity_shipped * p.standard_cost)) AS total_shipped_gross_profit FROM sales_order_items soi JOIN products p ON soi.product_id = p.product_id JOIN suppliers s ON p.supplier_id = s.supplier_id JOIN sales_orders so ON soi.order_id = so.order_id JOI`
- **Why no Day 2 candidate is correct:** Every candidate uses full line_total (or line_subtotal) as revenue; none compute a shipped-revenue basis, so no candidate matches shipped gross profit.
- **Audit finding:** The shipped-profit formula mixes full line revenue with shipped quantity and product standard cost.
- **Likely generic fix layer:** generation / semantic contract
- **Prior Day1-pool label:** no_correct_candidate_generated  (unchanged)

### DB55 test 44 — aggregation_or_formula_error
- **Question:** What is the average numeric grade for students whose advising risk level is high?
- **Day 2 selected (wrong):** `llm_sql_repair` score 91.0 — Selected repair averages per-student averages equally instead of averaging the qualifying numeric-grade records.
  - `WITH high_risk_students AS ( SELECT DISTINCT student_id FROM academic_advising WHERE academic_risk_level = 'high' ), student_grades AS ( SELECT e.student_id, AVG(e.numeric_grade) AS avg_grade FROM enrollments e GROUP BY e.student_id ) SELECT AVG(sg.avg_grade) FROM student_grades `
- **Why no Day 2 candidate is correct:** Qualifying candidates JOIN academic_advising and fanout-inflate the average (fatal), and the repair changes the grain; none compute a flat AVG over high-risk students' enrollment rows via EXISTS/IN.
- **Audit finding:** Averages per-student averages equally instead of averaging the numeric-grade records belonging to high-risk students.
- **Likely generic fix layer:** generation (EXISTS-qualified aggregation)
- **Prior Day1-pool label:** no_correct_candidate_generated  (unchanged)

### DB56 test 92 — aggregation_or_formula_error
- **Question:** For each appointment type, calculate prescription cost per completed appointment.
- **Day 2 selected (wrong):** `llm_primary` score 92.0 — Selected divides prescription cost by a denominator that is not the count of all completed appointments of the type.
  - `SELECT "appointments"."appointment_type", SUM("prescriptions"."estimated_cost") AS "total_prescription_cost", COUNT(*) AS "completed_appointment_count" FROM "appointments" LEFT JOIN "prescriptions" ON "appointments"."appointment_id" = "prescriptions"."appointment_id" WHERE "appoi`
- **Why no Day 2 candidate is correct:** Ratio candidates INNER JOIN prescriptions (denominator = completed appointments that HAVE prescriptions) or use COUNT(*) over a LEFT JOIN; none divide by COUNT(DISTINCT all completed appointments).
- **Audit finding:** Divides by completed appointments that have prescriptions, not all completed appointments of each type.
- **Likely generic fix layer:** generation (denominator population)
- **Prior Day1-pool label:** no_correct_candidate_generated  (unchanged)

### DB57 test 91 — aggregation_or_formula_error
- **Question:** For each team, calculate injury games missed per active player.
- **Day 2 selected (wrong):** `llm_variant_2` score 100.0 — Selected returns separate totals; the inner injuries join makes any per-player denominator cover only injured active players.
  - `SELECT "teams"."team_id", "teams"."team_name", SUM("injuries"."games_missed") AS "total_games_missed", COUNT(*) AS "active_player_count" FROM "injuries" INNER JOIN "players" ON "injuries"."player_id" = "players"."player_id" INNER JOIN "teams" ON "injuries"."team_id" = "teams"."te`
- **Why no Day 2 candidate is correct:** The ratio candidates (cand4/5/6) INNER JOIN injuries, so the denominator counts only active players who have injuries, not all active players on the team; no candidate counts the full active roster.
- **Audit finding:** The inner injury join makes the denominator include only active players who have injuries, not all active players on the team.
- **Likely generic fix layer:** generation (denominator population)
- **Prior Day1-pool label:** no_correct_candidate_generated  (unchanged)

### DB55 test 59 — missing_metric_or_output
- **Question:** Show each student with the percentage of 120 credits they have completed.
- **Day 2 selected (wrong):** `llm_sql_direct_variant` score 100.0 — Selected divides a SUM of enrollment credits by 120 over a reduced population (INNER JOIN enrollments + HAVING SUM>0).
  - `SELECT s.student_id, s.first_name, s.last_name, CAST(SUM(e.credits_earned) AS REAL) * 100.0 / 120.0 AS percentage_completed FROM students s JOIN enrollments e ON s.student_id = e.student_id GROUP BY s.student_id, s.first_name, s.last_name HAVING SUM(e.credits_earned) > 0`
- **Why no Day 2 candidate is correct:** Computing candidates use SUM(enrollments.credits_earned)/120 for only 55-69 of 100 students; non-computing candidates label raw credits. No candidate computes students.credits_earned/120 for every student. (Near-miss.)
- **Audit finding:** Labels raw credits as a percentage and never divides credits earned by 120.
- **Likely generic fix layer:** generation / semantic contract
- **Prior Day1-pool label:** no_correct_candidate_generated  (unchanged)

### DB55 test 314 — wrong_filter_or_placement
- **Question:** Show each program with department name and number of active students.
- **Day 2 selected (wrong):** `llm_sql_repair` score 99.0 — Selected repair counts all students per program and never filters to active students.
  - `SELECT p.program_name, d.department_name, COUNT(DISTINCT s.student_id) AS student_count FROM programs p JOIN departments d ON p.department_id = d.department_id JOIN students s ON p.program_id = s.program_id GROUP BY p.program_id HAVING COUNT(DISTINCT s.student_id) > 0`
- **Why no Day 2 candidate is correct:** The only candidates carrying the active-status filter (cand1/cand2) are malformed (stray raw student_id column, grain violation); the clean COUNT candidates omit the active filter. No candidate is both filtered and well-formed.
- **Audit finding:** Counts all students in each program and never filters to active students.
- **Likely generic fix layer:** generation (filter + clean count)
- **Prior Day1-pool label:** no_correct_candidate_generated  (unchanged)

### DB57 test 49 — wrong_filter_or_placement
- **Question:** What is the average number of completed matches per active season?
- **Day 2 selected (wrong):** `llm_sql_direct_variant` score 100.0 — Selected counts every match in active seasons and never restricts matches to completed status.
  - `SELECT AVG(match_count) AS average_matches_per_season FROM ( SELECT s.season_id, COUNT(m.match_id) AS match_count FROM seasons s JOIN matches m ON s.season_id = m.season_id GROUP BY s.season_id HAVING s.season_id IN ( SELECT season_id FROM seasons WHERE season_status = 'active' )`
- **Why no Day 2 candidate is correct:** No Day 2 candidate adds a match-completed predicate; the completed-match filter was never generated.
- **Audit finding:** Counts every match in active seasons and never filters matches to completed status.
- **Likely generic fix layer:** generation / semantic contract
- **Prior Day1-pool label:** no_correct_candidate_generated  (unchanged)

### DB57 test 50 — wrong_filter_or_placement
- **Question:** How many active players have both a current contract and at least one completed transfer?
- **Day 2 selected (wrong):** `llm_sql_repair` score 100.0 — Selected counts distinct active players with a current contract but only requires ANY transfer, not a completed transfer.
  - `SELECT COUNT(DISTINCT p.player_id) FROM players p JOIN contracts c ON p.player_id = c.player_id JOIN transfers t ON p.player_id = t.player_id WHERE p.active_flag = '1' AND c.contract_status = 'active' AND t.transfer_id IS NOT NULL`
- **Why no Day 2 candidate is correct:** No candidate combines COUNT(DISTINCT active player) with a transfer_status='completed' requirement; the one candidate carrying a transfer_status filter (cand2) is malformed (COUNT(*), no GROUP BY, stray column). Reclassified from the old Day1-pool label B: in the Day 2 pool no correct candidate exists.
- **Audit finding:** Returns grouped player rows instead of one count and never requires transfer_status = 'completed'.
- **Likely generic fix layer:** generation
- **Prior Day1-pool label:** correct_candidate_generated_but_rejected  (CHANGED)

### DB54 test 462 — set_logic_error
- **Question:** List customers who have never placed a delivered order.
- **Day 2 selected (wrong):** `llm_sql_direct_variant` score 100.0 — Selected anti-joins for delivered orders but the outer INNER JOIN sales_orders drops customers who have no orders.
  - `SELECT c.customer_id, c.first_name, c.last_name FROM customers c JOIN sales_orders so ON c.customer_id = so.customer_id WHERE NOT EXISTS ( SELECT 1 FROM sales_orders so2 WHERE so2.customer_id = c.customer_id AND so2.order_status = 'delivered' ) GROUP BY c.customer_id, c.first_nam`
- **Why no Day 2 candidate is correct:** Near-miss split: cand4/5/6 hold the correct NOT EXISTS(delivered) but the spurious outer join; cand1 has the correct customers-only scope but omits the delivered predicate. No candidate combines both.
- **Audit finding:** The inner join excludes customers with no orders, although they also have never placed a delivered order.
- **Likely generic fix layer:** generation (anti-join scope + predicate)
- **Prior Day1-pool label:** no_correct_candidate_generated  (unchanged)

### DB55 test 58 — set_logic_error
- **Question:** Show each student with the number of credits still needed to reach 120 credits.
- **Day 2 selected (wrong):** `llm_sql_direct_variant` score 76.0 — Selected computes 120 - credits_earned but adds WHERE credits_earned < 120, dropping students at or above 120.
  - `SELECT students.student_id, students.first_name, students.last_name, students.credits_earned, 120 - students.credits_earned AS credits_needed FROM students WHERE students.credits_earned < 120`
- **Why no Day 2 candidate is correct:** Near-miss split: the subtracting candidates all add the <120 exclusion; the all-student candidates omit the subtraction. No candidate shows every student WITH the computed remainder.
- **Audit finding:** Excludes students with 120 or more credits even though the request asks for each student.
- **Likely generic fix layer:** generation (drop exclusion filter)
- **Prior Day1-pool label:** no_correct_candidate_generated  (unchanged)

### DB55 test 407 — set_logic_error
- **Question:** List program identifiers that appear either in student records or course records.
- **Day 2 selected (wrong):** `llm_sql_direct_variant` score 99.0 — Selected INNER-joins students and courses, returning programs present in BOTH instead of either.
  - `SELECT DISTINCT p.program_id FROM programs p JOIN students s ON p.program_id = s.program_id JOIN courses c ON p.program_id = c.program_id`
- **Why no Day 2 candidate is correct:** Every Day 2 candidate uses INNER joins; none use UNION/OR to realise the 'either source' set semantics.
- **Audit finding:** Uses inner joins, returning programs present in both students and courses instead of either source.
- **Likely generic fix layer:** generation / set-semantics
- **Prior Day1-pool label:** no_correct_candidate_generated  (unchanged)
