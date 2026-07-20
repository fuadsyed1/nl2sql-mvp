# Day 2B — Selection-loss analysis (correct candidate generated but not selected)

_Trace-verified over the frozen Day 1 candidate pools. A fix candidate supplies the requested computation/structure the selected SQL lacks, executed cleanly, and adds no new day2 violation._

**Selection-loss cases: 2. Rejected-correct: 1.**

## DB56 test 51 — aggregation_or_formula_error (selected)

- **Question:** Show each department with the number of unused beds based on bed capacity minus current occupancy.
- **Audit reason:** Sums bed_capacity instead of calculating bed_capacity - current_occupancy.
- **Selected (wrong):** `llm_variant_1` score 80.0 — `SELECT "departments"."department_name", "departments"."bed_capacity", "departments"."current_occupancy", SUM("departments"."bed_capacity") AS "unused_beds" FROM "departments" GROUP`
- **Fix candidate:** `llm_sql_direct` score 88.0 — `SELECT      d.department_name,      d.bed_capacity,      d.current_occupancy,     (d.bed_capacity - d.current_occupancy) AS unused_beds FROM departments d GROUP BY d.department_id `
- **Why it lost:** a lower-precedence / consensus-grouped operand-only or mis-placed candidate outranked the computing candidate; a generic derived-expression / output penalty should let the computing candidate win.

## DB54 test 452 — wrong_filter_or_placement (selected)

- **Question:** List suppliers whose annual revenue is above the overall supplier average.
- **Audit reason:** Aggregates the entire supplier table with HAVING and does not compare each supplier's revenue with the overall average.
- **Selected (wrong):** `llm_variant_1` score 62.0 — `SELECT "suppliers"."supplier_name", "suppliers"."annual_revenue", AVG("suppliers"."annual_revenue") AS "avg_revenue" FROM "suppliers" HAVING "avg_revenue" < ?`
- **Fix candidate:** `llm_sql_direct` score 29.0 — `SELECT supplier_id, supplier_name, annual_revenue FROM suppliers WHERE annual_revenue > (SELECT AVG(annual_revenue) FROM suppliers) normalized_sql: SELECT supplier_id, supplier_nam`
- **Why it lost:** a lower-precedence / consensus-grouped operand-only or mis-placed candidate outranked the computing candidate; a generic derived-expression / output penalty should let the computing candidate win.

## DB57 test 50 — wrong_filter_or_placement (rejected)

- **Question:** How many active players have both a current contract and at least one completed transfer?
- **Audit reason:** Returns grouped player rows instead of one count and never requires transfer_status = 'completed'.
- **Selected (wrong):** `llm_variant_1` score 100.0 — `SELECT "players"."player_id", "players"."active_flag", "contracts"."contract_status", "players".*, COUNT("transfers"."transfer_id") AS "transfer_count" FROM "players" INNER JOIN "c`
- **Fix candidate:** `` score  — ``
- **Why it lost:** a lower-precedence / consensus-grouped operand-only or mis-placed candidate outranked the computing candidate; a generic derived-expression / output penalty should let the computing candidate win.

