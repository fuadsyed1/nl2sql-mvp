# Day 2B — No-correct-candidate analysis

_Cases where NO generated candidate supplies the requested computation/structure. These need a semantic-contract / generation-prompt improvement for the recurring pattern, not a selection change._

**No-correct cases: 18** — by pattern {'aggregation_or_formula_error': 6, 'missing_metric_or_output': 3, 'wrong_filter_or_placement': 4, 'set_logic_error': 5}

## aggregation_or_formula_error (6)

- DB55 t51 — Returns separate faculty and staff sums with the same alias instead of adding faculty_count and staff_count.
- DB57 t58 — Returns separate sums of wins, losses, and draws instead of adding them into total matches coached.
- DB54 t37 — The shipped-profit formula mixes full line revenue with shipped quantity and product standard cost.
- DB55 t44 — Averages per-student averages equally instead of averaging the numeric-grade records belonging to high-risk students.
- DB56 t92 — Divides by completed appointments that have prescriptions, not all completed appointments of each type.
- DB57 t91 — The inner injury join makes the denominator include only active players who have injuries, not all active players on the team.

## missing_metric_or_output (3)

- DB55 t52 — Returns annual budget and enrollment totals but never divides budget by enrolled students.
- DB54 t211 — Checks only average unit price > average unit cost; it never calculates or tests a 40% markup.
- DB55 t59 — Labels raw credits as a percentage and never divides credits earned by 120.

## wrong_filter_or_placement (4)

- DB55 t314 — Counts all students in each program and never filters to active students.
- DB56 t55 — Adds an unrequested active-doctor filter, so it does not show each doctor.
- DB57 t49 — Counts every match in active seasons and never filters matches to completed status.
- DB55 t142 — Adds an unrequested academic-advising appointment requirement, excluding otherwise qualifying assigned-advisor relationships.

## set_logic_error (5)

- DB54 t462 — The inner join excludes customers with no orders, although they also have never placed a delivered order.
- DB55 t58 — Excludes students with 120 or more credits even though the request asks for each student.
- DB54 t434 — Excludes products sold in 2024 rather than excluding categories that were sold in 2024.
- DB55 t407 — Uses inner joins, returning programs present in both students and courses instead of either source.
- DB56 t403 — Uses an appointment-to-claim inner join, returning only patients appearing in both sources.

## Recurring generation gaps

- Derived expressions (difference/profit/ratio/add) not emitted even with reminders — strengthen the derived-metric contract obligation.
- Set / anti-join intent (never/without, but-not, either/both) not structurally realized — strengthen set-intent contract + prompt.
- Explicit filter placement (WHERE vs HAVING) and preserved literals — strengthen explicit-condition obligation.
