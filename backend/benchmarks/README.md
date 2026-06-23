# SpiderSQL Benchmarks

Phase 9, Step 1 — the benchmark **foundation**. This directory holds the
question sets used to measure SpiderSQL's accuracy and performance across the
full pipeline (extraction → IR build → validation → join resolution → SQL
generation → execution).

**No runner exists yet.** This step ships only the dataset and this document.
A runner that executes these questions against the pipeline and scores the
results is a later step.

## Purpose

Give SpiderSQL a fixed, versioned set of natural-language questions with
known-good expectations, so that:

- **Accuracy** can be measured per category (e.g. how often a bridge-table join
  resolves correctly, how often a failure case is correctly rejected).
- **Performance** can be measured later (per-question latency, end to end).
- **Regressions** are caught when a change to extraction, resolution, or SQL
  generation alters previously-correct output.
- **Provider comparisons** are possible (local Ollama vs. MindRouter) on an
  identical question set.

## Schema (PetShop)

The benchmark targets the canonical PetShop database used throughout
development:

| Table  | Columns                  | Role            |
|--------|--------------------------|-----------------|
| owners | oid, lastname, city      | entity          |
| pets   | petid, name, species     | entity          |
| owns   | oid, petid               | junction/bridge |

Relationships:

- `owns.oid  -> owners.oid`
- `owns.petid -> pets.petid`

`owners` and `pets` are only connected **through** `owns`, so any owners↔pets
question must bridge through the junction table. The verified end-to-end example
("Which owners have dogs?") returns Smith (Moscow) and Lee (Pullman).

## Files

- `benchmark_queries_petshop.json` — 30 questions across 10 categories:
  simple select, single-table filter, two-table join, bridge-table join through
  `owns`, aggregation, group by, order by, limit, distinct, and failure/edge
  cases.
- `run_petshop_benchmark.py` — the runner (Phase 9 Step 2). Standard library
  only; it changes no application code.
- `results/` — timestamped JSON result files written by the runner.

### Item shape

Each entry in `queries[]` contains:

| Field                     | Meaning |
|---------------------------|---------|
| `id`                      | Stable identifier (e.g. `petshop_010`). |
| `category`                | One of the 10 categories above. |
| `question`                | The natural-language input. |
| `expected_tables`         | IR/plan tables the user asked about (excludes bridges). |
| `expected_bridge_tables`  | Tables traversal must add (e.g. `owns`). |
| `expected_sql_contains`   | Substrings the generated SQL must contain (quoted, table-qualified form). |
| `expected_params`         | Bound parameter values, in order. LIMIT is inlined and never a param. |
| `expected_result_contains`| Values expected somewhere in the rows (when deterministic and seed-dependent). |
| `notes`                   | Rationale, caveats, and what a grader should tolerate. |

## How these will be used later (no runner yet)

When the runner is built, it is expected to, per question:

1. Call the pipeline (e.g. the read-only inspection endpoints
   `/database/{id}/ir`, `/resolve`, `/generate_sql`, `/execute_sql`, or the
   functions directly).
2. Grade **structurally** rather than on exact string equality, because the
   extraction step (LLM) is the only nondeterministic link:
   - `expected_tables` / `expected_bridge_tables` vs. the resolved plan.
   - each `expected_sql_contains` fragment present in the generated SQL.
   - `expected_params` vs. the generated parameter list.
   - `expected_result_contains` present in the returned rows.
3. For **failure/edge cases**, assert the pipeline *correctly declines*:
   `validation.valid == false`, or `plan.resolved == false`, or
   `generated_sql.generated == false` — and that **no SQL is generated**. These
   are scored as passes when the system rejects the unanswerable question.
4. Aggregate pass/fail by category and overall, and (optionally) record latency.

### Grading guidance baked into the data

- SQL fragments use the **exact quoted, table-qualified** form the Phase 7
  generator emits (e.g. `"pets"."species" = ?`), so substring checks are stable.
- `expected_params` reflects parameterization: filter/having values are bound
  (`?`); `LIMIT` is an inline integer literal and must **not** appear in params.
- Some items intentionally leave `expected_result_contains` empty where row
  contents depend on seed data that may differ between environments; those are
  graded on SQL/plan shape only.
- Item `petshop_028` ("Show owners, pets, and cities") is a **known extractor
  pitfall** that should be *correctly rejected* by the validator — it is an
  accepted correct-rejection case, not a bug to fix.

## Running the benchmark

Prerequisites:

1. The SpiderSQL backend is running (default `http://localhost:8000`).
2. The PetShop database is uploaded and registered as the target `database_id`
   (default `1`) with the owners/pets/owns schema above.
3. The LLM provider is configured (local Ollama or MindRouter via `.env`). The
   runner records `LLM_PROVIDER` / `LLM_MODEL_NAME` from its own environment for
   provenance.

Commands (run from the `backend/` directory):

```
python benchmarks/run_petshop_benchmark.py
python benchmarks/run_petshop_benchmark.py --database-id 1
python benchmarks/run_petshop_benchmark.py --base-url http://localhost:8000
# optional: --timeout 180   (per-request seconds; raise it for large remote models)
```

For each question the runner POSTs `{"question": "..."}` to
`/database/{database_id}/execute_sql`, measures latency, captures the full
response, and grades it structurally:

- **Normal cases** pass only when `validation.valid`, `plan.resolved`,
  `generated_sql.generated`, and `execution.executed` are all true, AND the
  `expected_tables` appear in `ir.tables`/`plan.tables_used`, the
  `expected_bridge_tables` appear in `plan.bridge_tables`, every
  `expected_sql_contains` fragment is in `generated_sql.sql`, `expected_params`
  equals `generated_sql.params`, and every `expected_result_contains` value
  appears in `execution.rows`.
- **Failure/edge cases** pass when the pipeline *correctly declines*
  (`validation.valid == false` OR `plan.resolved == false` OR
  `generated_sql.generated == false`) and `execution` is null or
  `executed == false` — i.e. no SQL is run on an unanswerable question.

### Output

- Per-question `PASS`/`FAIL` lines (with the failure reason and latency).
- A per-category summary (`passed/total`).
- An overall summary: total, passed, failed, pass rate, average latency.
- A JSON result file at `benchmarks/results/petshop_benchmark_<timestamp>.json`
  containing the timestamp, base URL, database id, provider/model (from
  environment), the summary and category breakdown, and the full per-question
  responses + grading details.

Because the extraction step (LLM) is nondeterministic, grading is structural,
not exact-string — pass rates reflect real pipeline accuracy and can be compared
across providers (Ollama vs. MindRouter) on the identical question set.

## Scope and rules

- Step 1 added the dataset + docs; Step 2 adds the runner. Neither changes
  `app.py`, the provider layer, the extractor, or any Phase 5/6/7/8 logic.
- The dataset is versioned (`"version": "1.0"`); changes to questions or
  expectations should bump the version so historical results stay comparable.