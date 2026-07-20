# SpiderSQL Go-Live — Day 2 Summary (offline implementation)

**Status: offline implementation done; live 64-query rerun PENDING local run** (MindRouter unreachable from this environment).

## Frozen Day 1 baseline (untouched)
Semantic 1606/2000 (80.3%) · execution 1985/2000 · 394 failures (379 executed-wrong,
15 controlled) · protected 1606 · containment 705/1000 · target 1738 (gap 132).

## Production files modified
- `sql_candidates/day2_semantic_rules.py` (NEW) — generic NL obligations + 12 alias-insensitive validators + severity registry.
- `sql_candidates/direct_sql_enforcement.py` — wire only FATAL day2 rules into the existing single enforcement entry point.
- `semantic/llm_sql_direct.py` — generic reminders appended to all 3 direct-SQL prompts.
- `semantic/llm_sql_repair.py` — generic repair guidance + safety rails.

## Validator rules & severity (promotion gated by static replay)
- **FATAL (0 protected, 1 incorrect, precision 1.0):** `both_as_union` — the only Day 2 fatal rule.
- **WARNING:** aggregate_predicate_in_where (demoted from fatal: flagged 0/0, not
  discriminating), missing_requested_derived_expression, row_level_predicate_in_having,
  either_or_as_intersection, negative_existence_inner_join, unsafe_integer_division.
- **DIAGNOSTIC:** missing_required_output, missing_explicit_filter, unrequested_filter,
  independent_exists_collapsed, missing_zero_denominator_handling.

## Static protected replay (Task C — no LLM)
1606 protected + 394 incorrect. Fatal rules flag **0** protected (acceptance met).
Warning/diagnostic rules flag some protected → correctly kept non-blocking.
See `day2_validator_replay_summary.json` / `.csv`.

## Offline gates
Focused tests 17/17 pass · full backend suite **855 passed, 0 failed** ·
fatal-rule protected regressions **0** · no selector/consensus/containment change ·
no benchmark-specific hardcoding.

## Live (pending local run — NOT fabricated)
Live recoveries: **pending local run.** Live protected regressions: **pending local run.**
Run the preselected 64 queries locally (see day2_targeted_before_after.csv +
run_day2_targeted.py) in an environment with MindRouter access.
