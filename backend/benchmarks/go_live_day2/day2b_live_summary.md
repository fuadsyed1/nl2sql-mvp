# Day 2B LIVE — Trace-verified classification summary

Source of truth: the EXACT Day 2 live rerun candidate pools in `benchmarks/results/day2_targeted_full_trace_db54..57.txt`. The prior `classify_day2b_failures.py` classified against the FROZEN Day 1 traces (`ia['sql_trace_files']`), which do not contain the candidates the Day 2 rerun actually generated — that is the bug this redo corrects.

## Category counts (21 remaining-incorrect queries)

- A correct_candidate_generated_but_not_selected: **9**
- B correct_candidate_generated_but_rejected: **0**
- C no_correct_candidate_generated: **12**

## Classifications changed vs the prior Day1-pool run

8 of 21 changed:

- DB55 t51: no_correct_candidate_generated → correct_candidate_generated_but_not_selected
- DB55 t52: no_correct_candidate_generated → correct_candidate_generated_but_not_selected
- DB54 t211: no_correct_candidate_generated → correct_candidate_generated_but_not_selected
- DB56 t55: no_correct_candidate_generated → correct_candidate_generated_but_not_selected
- DB55 t142: no_correct_candidate_generated → correct_candidate_generated_but_not_selected
- DB54 t434: no_correct_candidate_generated → correct_candidate_generated_but_not_selected
- DB56 t403: no_correct_candidate_generated → correct_candidate_generated_but_not_selected
- DB57 t50: correct_candidate_generated_but_rejected → no_correct_candidate_generated

## Dominant remaining root cause

Selection, not generation. In 9/21 the Day 2 pipeline DID generate a semantically correct candidate that executed cleanly, but the consensus/selector+scorer did not choose it — frequently because the correct and the wrong candidate are indistinguishable on the existing semantic dimensions (confirmed by docs/consensus_selection_limitation.md), or because a derived-metric/set/output signal is not rewarded (or a grain false-positive penalises the correct row-level comparison). The remaining 12/21 are genuine generation gaps (denominator population, completed/active filters, set 'either' UNION, paraphrased arithmetic).

## Safest generic next production step (NOT implemented here)

Add a generic, schema-independent *derived-obligation & set/output discriminator* to the candidate PROFILE (scorer input) so a candidate that satisfies a detected obligation — a 'per' ratio, an additive/subtractive/percentage formula, a UNION 'either' set, an all-rows population — is ranked above an executable candidate that omits it, and the reverse grain false-positive on raw-value comparisons is relaxed. This directly targets the 9 selection-loss cases without a consensus-only change (which the limitation doc shows is unsafe) and without any test-id/DB-specific logic. Do not implement in this task.
