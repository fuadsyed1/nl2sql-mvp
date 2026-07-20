# Consensus-only selector fix — research finding (documented limitation)

**Status:** consensus refactor reverted to the last green state (v1 independent
semantic consensus with the deterministic result-equivalence fallback). RC3,
RC4, RC5, RC5.1 remain active. This document preserves the Option C analysis
that justifies stopping; it contains **no production logic**.

## Question
Can the selector's correlated-majority consensus be replaced by an
independent-lineage + pairwise-semantic mechanism (no result-majority, no raw
candidate count, no source preference, no correlated-agreement, and no new
semantic obligation) **without** regressing manually-verified-correct selections?

## Authoritative oracle
The current DB53 500-run, manually audited one query at a time:
- `spidersql_db53_500_trace_candidate_audit_20260717.csv` (113 non-fully-correct
  cases with the verified correct candidate label; the remaining 387 are fully
  correct),
- `northstar_500_db53_rc51_rerun.txt` (test-id → question),
- `trace_full_trace_db53_20260716_234559.txt` (500-run occurrences only,
  REQUEST START ≥ 2026-07-17T00:13:51; earlier smoke-run duplicates ignored).

The captured 500-run candidate pools were replayed through the candidate
selector (no LLM regeneration).

## Result
Strict consensus using **only existing evidence** (RC4 `override_dominates`,
RC5/RC5.1 `rc5_dominates`, checklist missing tables/columns/literals):

- **Authoritative protected replay: 339/387 — 48 regressions.**
- Of the breaks, **52 of 53 are indistinguishable by any existing pairwise
  semantic evidence**; exactly 1 is distinguishable.

Output-shape heuristics were tried and rejected as unreliable: checklist output
arity is itself wrong in several audited-correct cases (e.g. 51, 401), so it
makes the wrong candidate dominate; an "arbitrary ungrouped column" SQL-validity
check did not close the gap (347/387).

## Why
For ~52 of the manually-verified-correct 500-run selections, the correct
candidate and the wrong candidate are **identical on every existing semantic
dimension** — RC4, RC5/RC5.1, checklist completeness, fatal status. The only
signal that ever distinguished them was that the direct generator family
produced the correct answer with several correlated candidates (a result
majority / correlated agreement). Removing that signal (the purpose of the
refactor) therefore removes the only available discriminator for those cases.

The same conclusion holds against the historical 373 offline baseline (44
regressions there), confirming it is a property of the candidate pools, not an
artifact of a stale oracle.

## Finding
A **consensus-only** change cannot safely improve the selector with the semantic
evidence currently available:
- Correlated agreement causes some wrong selections (the motivation to remove it).
- It also remains the **only** distinguishing signal for many correct selections.
- Safely removing it requires **stronger formula, filter, set, grain, output,
  literal, and relationship semantics** in the candidate profile — improvements
  outside the narrow consensus-only scope.

## Decision
Reverted to the last green production state (full offline suite 785 passing;
historical protected replay 373/373; RC5.1 active; Test 437 preserved in its
verified case). The bounded-correlated-agreement tie-break and the
accept-regressions options were both declined: the former restores the very
signal the refactor set out to remove without evidence it preserves more than it
breaks; the latter regresses 48 authoritative-correct cases.
