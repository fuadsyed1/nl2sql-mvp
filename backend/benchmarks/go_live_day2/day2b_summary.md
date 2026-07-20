# SpiderSQL Go-Live — Day 2B Summary

**Status: offline classification + safety-gated implementation done; live rerun PENDING** (MindRouter unreachable here). Containment work NOT started.

## Classification of the 21 remaining incorrect (trace-verified)
- correct_candidate_generated_but_not_selected: **2** (DB56 t51, DB54 t452)
- correct_candidate_generated_but_rejected: **1** (DB57 t50)
- no_correct_candidate_generated: **18**
Files: `day2b_failure_classification.csv`, `day2b_selection_loss_analysis.md`, `day2b_no_correct_candidate_analysis.md`.

## Selection-loss fix — attempted and REJECTED on safety
A generic pool-relative derived-expression "operand-only" penalty was implemented and
statically replayed over the 2,000 captured pools. It would change **38** protected-correct
best-scored winners while flipping only **10** incorrect selections, and did **not** recover
the two trace-verified loss cases (they were lost to consensus/RC grouping, not raw score).
It therefore FAILS the 0-protected-regression gate and is **left unwired**
(`day2b_selection_fix_safety_replay.json`).

## Validator / generation fixes
- Rejected-correct (1): a single-case validator edit could not be shown generic without a
  test-specific rule; deferred to live-verified review rather than risk hardcoding.
- No-correct (18): addressed by the Day 2 generic prompt/contract reminders already shipped;
  further gains need live regeneration to verify.

## Honest outcome
No production **selection** behavior was changed. The authorized generic scoring lever was
found UNSAFE by offline replay, so no additional recoveries are claimed. Additional recoveries,
protected regressions, and recovered-query regressions are **pending the local 64-query rerun**.

## Offline gates
Focused Day 2 tests **20 passed** · full backend suite **858 passed, 0 failed** ·
fatal-rule protected regressions **0** · no selector/consensus/containment change · no hardcoding.
