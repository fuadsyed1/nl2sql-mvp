# SpiderSQL Go-Live — Day 1 Baseline Score Report

_Generated 2026-07-19T22:16:52 · config day1.v2_

## NL-to-SQL

- Execution successes: **1985 / 2000** (target ≥ 1985) → MEETS
- **Semantic-correct: 1606 / 2000 = 80.3%** (engineering target ≥ 1738) → BELOW (gap 132)
- Target reconciliation: Presented-accuracy target is internally inconsistent: a category rollup implies 1737 correct while a per-database percentage rollup implies 1738. Engineering target is fixed at 1738. Measured semantic-correct counts are taken verbatim from the audit files and never adjusted to hit this number.
- Category rollup of correct = 1606 (equals DB total 1606: measured data is internally consistent)
- Semantic failures: **394** ({'executed_semantically_wrong': 379, 'controlled_no_sql': 15}); patterns {'grain_mismatch': 30, 'aggregation_or_formula_error': 43, 'needs_manual_review': 116, 'controlled_no_sql': 15, 'wrong_entity_or_role': 29, 'missing_metric_or_output': 61, 'wrong_filter_or_placement': 62, 'set_logic_error': 38}
- Candidate-oracle rows: 2265 across 394 failed queries (379 executed-wrong + 15 no_selected_sql)
- Selected-candidate coverage: 379/379 (100.0%)
- Query dispositions (heuristic; see manual-review CSV): {'only_selected_candidate_available': 1, 'plausible_clean_alternative_available': 358, 'no_clean_different_alternative': 20, 'unresolved_manual_review': 0}

### Semantic accuracy by database

| DB | correct | total | accuracy |
|----|--------|-------|----------|
| 54 | 439 | 500 | 87.8% |
| 55 | 407 | 500 | 81.4% |
| 56 | 368 | 500 | 73.6% |
| 57 | 392 | 500 | 78.4% |

## Containment (designed-edge recovery)

- Weighted: **705 / 1000 = 70.5%** (target 795 = 79.5%) → BELOW
- Unweighted DB average: 71.2%
- Detailed failure causes: {'definite_wrong_relationship': 44, 'distinct_groupby_normalization': 14, 'group_key_mismatch': 64, 'sql_generation_failure': 13, 'canonical_key_failure': 47, 'base_entity_recovery': 104, 'limit_orderby_normalization': 5, 'aggregate_normalization': 4}
- Required causes present: ['aggregate_normalization', 'base_entity_recovery', 'canonical_key_failure', 'definite_wrong_relationship', 'distinct_groupby_normalization', 'group_key_mismatch', 'sql_generation_failure']; missing: []

## Data availability

- Missing artifacts: none (all obtained)
- Warnings: 0
