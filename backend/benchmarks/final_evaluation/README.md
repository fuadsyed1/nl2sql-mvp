# SpiderSQL Final Evaluation Benchmarks

Two reproducible suites, frozen against databases 46 (appointments clinic),
49 (Lahman Baseball), and 50 (AdventureWorks CTU):

* **SQL benchmark** — 2,000 NL-to-SQL cases: 10 categories x 200 cases,
  each category 60 easy / 80 medium / 60 hard, 80 DB46 + 60 Lahman + 60 AW,
  >= 50 semantic templates per category, at most 4 paraphrases per
  reference-SQL structure.
* **Containment benchmark** — 240 groups: 12 categories x 20 groups,
  2-5 natural-language queries per group, expected relations computed from
  reference executions on the frozen data (**data-dependent evaluation,
  not symbolic proof**).

## Build (one-time, deterministic)

```
cd backend
python -m benchmarks.final_evaluation.generation.build_sql
python -m benchmarks.final_evaluation.generation.build_containment
python -m benchmarks.final_evaluation.generation.build_freeze
```

The build executes every reference SQL read-only, stores normalized result
hashes, enforces every protocol audit (counts, duplicates, template caps,
difficulty split, zero-row ceiling), and fails loudly otherwise. Rebuilding
produces identical manifests. `build_freeze` records git HEAD, dirty flag,
SHA-256 of the pipeline files and manifests, model provider/name, and the
database registry.

## Smoke test (backend + MindRouter must be running)

```
python -m benchmarks.final_evaluation.sql.runners.run_sql_benchmark \
    --smoke-per-category 2 --output-prefix smoke
python -m benchmarks.final_evaluation.containment.runners.run_containment_benchmark \
    --smoke-per-category 2 --output-prefix smoke
```

## Full runs (sequential; resumable after any interruption)

```
python -m benchmarks.final_evaluation.sql.runners.run_sql_benchmark \
    --output-prefix full --resume
python -m benchmarks.final_evaluation.containment.runners.run_containment_benchmark \
    --output-prefix full --resume
```

Results append per case/group to `*/results/<prefix>_results.jsonl`;
reports regenerate into `*/reports/` on every invocation. Existing result
files are never overwritten (a new `--output-prefix` or `--resume` is
required). See BENCHMARK_PROTOCOL.md for scoring rules and verdicts.
