# Day 2 — Implementation Map (generation pipeline modification points)

_Read-only trace of the current NL→SQL path and the exact, existing layers each
Day 2 generic fix should modify. No second parallel pipeline is introduced; all
changes extend existing modules. Nothing here is DB- or test-specific._

## Current path (verified by reading the modules)

```
question
  → semantic/semantic_checklist.py   generate_checklist()  (LLM JSON: measure_column,
                                       required_sql_shape, row_grain, required_group_keys,
                                       grain_requirements[], required_literal_groups, comparison_logic)
  → semantic/semantic_contract.py    build_semantic_contract()/build_grain_contract()
                                       (GrainRequirement dataclass: measure_aggregation, distinct,
                                        comparison_constant, measure_operation add|subtract, …)
  → semantic/llm_sql_direct.py       generate_direct_sql / _grain / _variant  (_direct_prompt,
                                       _grain_prompt, _variant_prompt — direct-SQL generation)
  → semantic/ai_semantic_extractor.py + ir_* (IR family candidates)
  → sql_candidates/candidate_builder.py  assembles the candidate pool
  → validation: semantic_obligations.py, direct_sql_enforcement.py,
                semantic_sql_guards.py, ir_validator.py (fatal reasons)
  → semantic/llm_sql_repair.py       should_repair() + _repair_instructions()  (generic repair)
  → sql_candidates/candidate_selector.py (FROZEN — not touched Day 2)
  → final semantic enforcement (controlled-failure if all candidates fatal)
```

## Modification points by task (extend existing layers only)

| Task | Layer / file | Existing hook to extend |
|---|---|---|
| 3 Derived metrics & aggregation | `semantic_checklist.py` (`_checklist_prompt`, `_clean_checklist`) + `semantic_contract.py` (`GrainRequirement`, add a `DerivedMetricRequirement` sibling: metric_operation, numerator, denominator, aggregation_function, entity_grain, grouping_columns, required_output_alias, percentage_or_ratio, zero_denominator_behavior) | `grain_requirements[]` already carries `measure_operation`/`measure_expression`; add ratio/percentage fields alongside, not a new pipeline |
| 3 validation (missing derived expr / metric absent from SELECT / wrong grain) | `semantic_obligations.py` (obligation profile) + `direct_sql_enforcement.py` (`direct_sql_violations`) | add generic AST checks; alias-insensitive (do not fail on alias-only differences) |
| 4 Required-output completeness | `semantic_checklist.py` (add `required_outputs[]` concept list) + `semantic_obligations.py` | confirm each required output concept has a SELECT expression; allow equivalent expressions/aliases; ignore filter-only columns |
| 5 Explicit filter preservation & WHERE/HAVING placement | `semantic_checklist.py` (`required_literal_groups`, comparison_logic) + `semantic_sql_guards.py` / `semantic_obligations.py` | row-level→WHERE, aggregate→HAVING; NOT EXISTS for absence; preserve literals; validate all explicit conditions survive |
| 6 Set & existential logic | `semantic_checklist.py` (add `set_intent`) + `semantic_contract.py` + `llm_sql_direct.py` prompts (already mention NOT EXISTS) | map either/both/but-not/without/neither → UNION/INTERSECT/EXCEPT/NOT EXISTS or independent EXISTS; validate direction + independent-EXISTS not collapsed |
| 7 Repair safety | `llm_sql_repair.py` (`_repair_instructions`, `should_repair`) | may fix output/filter/placement/set/zero-safe division; must re-validate against full contract; must NOT change entity/tables/filters/denominator/collapse EXISTS |
| 8 Focused tests | new `tests/test_day2_*.py` | synthetic schemas only; no DB54–57 names |

## Enforcement-safety principle (0 protected regressions)

New validators must reject **only** on unambiguous, alias-insensitive evidence, and
every new fatal rule must be shown to flag **0** of the 1,606 protected-correct
captured SQLs before it is allowed to block. That safety check, and the recovery
measurement, both require live generation (see status/blocker in day2_summary.md).
