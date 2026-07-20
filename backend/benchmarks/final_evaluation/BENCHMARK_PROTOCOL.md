# Final Evaluation Protocol (frozen)

## Code freeze
`benchmark_freeze.json` records git HEAD, working-tree dirtiness, SHA-256 of
the 14 pipeline files, model provider/name, database IDs, and manifest
hashes. The pipeline must not be modified between freeze and reported runs;
benchmark failures are evaluation evidence, never grounds for tuning.
Only benchmark-infrastructure defects (invalid reference SQL, wrong expected
hashes, runner resume bugs, malformed manifests, scorer bugs) may be fixed,
and each such fix must be noted.

## SQL scoring (execution results, never SQL text)
Modes: `scalar` (single value, numeric tolerance 1e-6), `ordered_rows`
(values + order), `multiset_rows` (order-free, duplicates preserved),
`set_rows` (order-free, duplicates collapsed — only where the question asks
for a set). Column aliases may differ; extra or missing output columns are
wrong (`wrong_columns`). Normalization: NULL marker, int/decimal
unification, float tolerance bucketing, ISO dates as stored, text
whitespace-trimmed only.

Verdicts: `correct`, `wrong_result`, `wrong_columns`, `execution_error`,
`controlled_failure`, `timeout`, `invalid_reference`,
`manual_review_required` (e.g. truncated actual results).

Two headline numbers, always reported separately:
* strict accuracy = correct / all
* safety accuracy = (correct + controlled failures) / all
A controlled failure is NEVER counted as correct.

## Containment scoring
Data-dependent containment on the frozen databases (bidirectional EXCEPT in
the product; set-comparison of reference results in the benchmark) — not a
symbolic proof. Expected relations per ordered pair: `contains`,
`contained_in`, `equivalent`, `incomparable`, plus `unknown` for
column-count-mismatched projections (unsupported comparison keys, by
design). A pair is correct only when the reported relation matches; a group
hierarchy is correct only when every pair matches AND the reported
broadest (maximal) and narrowest (minimal) sets match. Counterexample rows
are valid only when present in the claimed left reference result and absent
from the right one on the canonical comparison columns; rows compared on a
service-chosen key that cannot be matched count as unverified.

## Runner discipline
Sequential requests only (MindRouter rate limits). Results are flushed
after every case/group; `--resume` skips completed IDs; existing result
files are never overwritten. Timeouts and retry counts are CLI-controlled
and recorded in the output.

## Known limitations
* Containment expectations are valid only for the frozen database contents.
* `>` vs `>=` boundary groups may legitimately be equivalent when no row
  sits on the boundary; expectations are computed, not assumed.
* Reference results larger than 20,000 rows are truncated at build time and
  excluded by construction (none in the shipped manifests).
* The SQL benchmark accepts any semantically-equivalent candidate SQL; it
  cannot detect a right-answer-for-the-wrong-reason query beyond result
  equality on the frozen data.
