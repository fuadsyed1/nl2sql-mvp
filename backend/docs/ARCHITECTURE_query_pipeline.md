# SpiderSQL — End‑to‑End Query Pipeline (NL → SQL → Results)

A reference for a new developer. Every claim below is taken from the actual
codebase under `C:\Projects\nl2sql-mvp`. File and function names are exact.

The one route that matters for "user types a question and gets SQL/results" is:

```
POST /database/{database_id}/execute_sql        (backend/app.py :: execute_sql_endpoint)
```

Everything else in this document hangs off that call.

---

## 1. Frontend flow

**Component that owns the query send:** `frontend/src/App.jsx`.
The text box itself is `frontend/src/components/InputBar.jsx` (an auto‑resizing
`<textarea>` used for uploads *and* queries), but the **send logic lives in
`App.jsx`** (the `handleSend`‑style function around line 552). `InputBar` just
raises the input up to `App`.

**Endpoint called:** for an active database it always calls
`` `${API_BASE}/database/${currentDatabaseId}/execute_sql` `` (App.jsx ~line 567).
There is a legacy `/query` path in the code, but `App.jsx` explicitly does **not**
fall back to it ("Do NOT fall back to the legacy /query schema-generation
path", ~line 601).

**Request body** (App.jsx ~line 572):

```json
{ "question": "<the user's natural-language text>", "database_id": <id> }
```

If the user pastes multiple numbered questions, `splitNumberedQuestions` splits
them and each is POSTed **separately**, one at a time.

**Display.** The JSON response is passed to `buildQueryResult(data, label)`
(App.jsx line 465), which pulls:

- `data.generated_sql.sql` → the SQL string
- `data.relational_algebra` → relational‑algebra text
- `data.execution.columns`, `data.execution.rows`, `data.execution.row_count`

and hands them to **`frontend/src/components/QueryResultCard.jsx`**, which renders
the SQL block, the relational‑algebra block, and a rows/columns table. On failure
it shows `execution.error`/`reason` or `plan.reason`.

---

## 2. Backend entry point

**Route/function:** `backend/app.py` → `@app.post("/database/{database_id}/execute_sql")`
→ `def execute_sql_endpoint(database_id: int, body: IRRequest)`.
`body.question` is the NL text.

**What is loaded first, in order:**

1. `get_database_meta(database_id)` (`schema/lazy_loader.py`) — mode (`small`/`large`) + name. 404s early if missing.
2. `resolve_query_graph(database_id, body.question, meta)` (`schema/query_context.py`) — the **schema graph** (full or a sub‑graph). Returns `(graph, tables_considered, early)`; `early` is a ready response for "no relevant tables", "requested date table not found", or "database not found".
3. `force_named_tables(graph, body.question, database_id)` (`schema/named_table_forcing.py`) — injects any table the question **names verbatim** even if retrieval or metadata dropped it (prints the `[GRAPH FORCE]` / `[GRAPH]` debug logs).
4. `get_database_path(database_id)` — the physical SQLite file used for execution.
5. `grounding_profile(database_id, db_path)` (`schema/value_profiler.py`) — sampled enum‑like column values → `value_hints`.
6. `generate_checklist(body.question, graph, value_hints)` (`semantic/semantic_checklist.py`) — the semantic contract (**1 LLM call**).
7. `correct_checklist_tables(body.question, checklist, graph)` (`semantic/schema_linker.py`) — deterministic correction of `must_use_tables`.

Chat state is **not** used on this route (it belongs to the legacy `/query`
endpoint). This route is stateless per request.

---

## 3. Schema / table selection layer

**File:** `schema/query_context.py` → `resolve_query_graph`.

- **Small mode** (`meta["mode"] == "small"`): `graph = get_database_graph(database_id)` — the **full** schema graph. No retrieval.
- **Large mode**: `tables_considered = retrieve_tables(database_id, question, k=8)` (`retrieval/table_retriever.py`), then a **date guard** `requested_dates_satisfied(...)`, then `build_subgraph(database_id, [names])` (`schema/subgraph_builder.py`) so the pipeline never sees the full 100–200 table schema.

`is_large_database(...)` (in `schema/...`) decides the mode at build time based on table count.

**Table scoring** — `retrieval/table_retriever.py :: retrieve_tables`. Deterministic:
SQLite **FTS5 bm25** over `table_name + column names`, plus explicit boosts:
`+5` when the full table name appears in the question (`table_name_in_question`),
`+1` for a token overlap, `+6` for a normalized date match in the table name,
`+2` for a column name present in the question. Top‑`k` (default 8) win.

**Table locking / fallback (query time):**

- `schema/named_table_forcing.py :: force_named_tables` — the strongest guarantee. It reads **metadata (`get_database_tables`) ∪ the physical SQLite file (`physical_tables` via `sqlite_master`/`PRAGMA table_info`)**, detects tables the question names verbatim (`_explicitly_named_tables`, separator‑insensitive), and **injects** any that are missing into the graph (rebuilding via `build_subgraph`, or directly from the physical schema when a table is absent from metadata). Emits `[METADATA]` when a physically‑present table is missing from `database_tables`.
- `semantic/schema_linker.py :: correct_checklist_tables` — forces exactly‑named tables into `must_use_tables`, disambiguates same‑family siblings by question tokens (e.g. keeps `census_tracts_new_york`, drops `census_tracts_california`), adds a zip↔tract bridge table, and adds a real metric table (e.g. one containing `median_income`).
- `semantic/llm_sql_direct.py :: _relevant_tables` — builds the **focused schema** shown to the direct‑SQL LLM: `must_use_tables ∪ verbatim‑named tables + their FK neighbors`. Large or un‑focused schemas fall back to the full set.

**How irrelevant tables are kept out:** the focused schema limits what the LLM sees;
the schema‑linker prunes wrong siblings; and at scoring time
`sql_candidates/explicit_table_lock.py :: table_lock_penalty` heavily penalizes SQL
that uses a sibling/unmentioned table or ignores named tables, while
`sql_candidates/direct_sql_enforcement.py :: direct_sql_violations` **rejects**
(does not append) a direct candidate that omits an explicitly‑named table.

---

## 4. Natural‑language / semantic extraction layer (IR)

Yes — the NL question is converted into a JSON **Intermediate Representation (IR)**.

**File/function:** `semantic/ai_semantic_extractor.py`:

- `extract_multitable_ir_extraction(question, graph)` (line 425) — the **primary** extraction. Builds the prompt with `_primary_ir_prompt`, calls `_call_ir_model(prompt, 700, temperature=0)` (the LLM call at line 406), normalizes via `_normalize_ir_extraction`. If the first response is empty it **retries once** with `_fallback_ir_prompt` at `num_predict=500`.
- `extract_multitable_ir_extraction_variant(question, graph, variant=1|2)` (line 479) — a **reframed prompt at a mild temperature** (`_VARIANT_TEMPERATURES`, ~0.3–0.4) for candidate diversity. Uses the same `_call_ir_model`.
- `extract_semantics(question, schema_text)` (line 56) — the **legacy single‑table** extractor (LLM at line 146). Not used by `execute_sql`.

**Fields extracted** (the canonical shape, `_empty_ir_extraction`, line 246):
`tables, select, filters, aggregations, group_by, having, order_by, limit,
distinct, anti_exists, top_per_group, universal, set_division, aliases,
alias_joins, alias_filters, alias_select, explicit_joins, null_filters,
compound_filters, derived_relations, main_from`.

**Where it can fail / return empty:** any provider error, empty JSON, or invalid
JSON returns `_empty_ir_extraction()` (a safe empty IR — never `None`, never a
crash). Anything the model names that is not in the schema is dropped during
normalization.

---

## 5. Relationship / join discovery layer

There are **four** research‑backed pieces plus the classic upload‑time detector.

### Upload‑time relationship detection
`schema/relationship_detector.py :: detect_relationships` (value‑overlap + name
similarity) and declared FK reading in `services/metadata_service.py`
(`extract_foreign_keys` via PRAGMA). These run **at upload/import time** and are
stored in `database_tables`/relationships; they are what the graph carries at query
time.

### Phase 1 — HoPF‑style relationship *evidence* layer
**File:** `schema/hopf_relationship_evidence.py` (`score_relationship`,
`merge_relationships`, `sample_column_stats`, `sampled_overlap`,
`is_measure_column`, `USABLE_CONFIDENCE = 0.92`).
**Evidence:** parent (near‑)uniqueness, child→parent sampled value overlap,
column‑name similarity, type compatibility, null/repetition pattern, and
measure‑column rejection. It scores a candidate child→parent link and marks it
`usable` only at confidence ≥ 0.92; schema‑only DBs get weak, non‑usable evidence.
**Effect on join‑path selection:** it is the **foundation** layer — a scoring
library. Its confidence threshold is reused by Phase 2/3 (`_rel_supported`), but
the module does **not** currently write `hopf_inferred` edges into the live graph,
so in practice it influences selection only insofar as the graph already carries
such edges. See *Weaknesses*.
**When it runs:** designed for query time (bounded sampling), but not wired into
the runtime graph‑building path.

### Phase 2 — LLM‑FK / semantic FK verifier
**File:** `sql_candidates/semantic_relationship_verifier.py ::
verify_semantic_relationships`. Called from the scorer (`candidate_scorer.py`,
"section 9c"). **No extra LLM call** — it reuses the checklist, schema index,
Phase‑1 confidence, and the already‑parsed join edges.
**Evidence / checks:** unsupported key↔key joins (e.g. `zip_code = tract_ce`) not
backed by a declared FK / confirmed / high‑confidence HoPF link / same‑named key;
wrong same‑shaped table choice (question↔table token match); ignoring most
`must_use_tables`; and dummy/generic SQL (`WHERE 0>0`, `SELECT *` fallback, no
aggregation when structure is required).
**Effect:** small advisory penalties into the candidate score (a strong penalty
only for dummy / generic‑fallback SQL). **Runs at query time.**

### Phase 3 — Aurum/WarpGate‑style semantic join discovery
**File:** `sql_candidates/semantic_join_discovery.py ::
discover_semantic_join_issues`. Called from the scorer ("section 9d").
**Evidence:** geo‑granularity concept families (zip/tract/county/state), bridge/
mapping‑table detection, table‑purpose families (individual/committee/candidate/
expenditure/geography), and cross‑concept join support.
**Effect:** it can **reward *or* penalize** — rewards using the right bridge/
mapping table and the correct table‑purpose path (so selection is pulled toward a
semantically correct candidate), penalizes direct cross‑granularity joins that
bypass a bridge, wrong same‑family tables, and purpose mismatches. Clamped to
`[-24, +8]`. **Runs at query time.**

### Phase 4 — semantic join‑path *candidate generator* (DISABLED by default)
**File:** `sql_candidates/semantic_join_path_candidate.py`
(`plan_semantic_join_path` deterministic planner + `build_semantic_join_path_sql`,
one constrained LLM call). It builds a safe `source → bridge → geography/census`
path and asks the LLM to write SQL constrained to it. **Gated off** in `app.py`
behind `ENABLE_SEMANTIC_JOIN_PATH` (default OFF). It made bq023 worse, so it is
retained but not used at runtime.

---

## 6. SQL generation layer

Two distinct generation styles feed one candidate pool.

**A. Deterministic IR → plan → SQL** (used by `query_family`, `llm_primary`,
`llm_variant`). `sql_candidates/candidate_builder.py :: build_candidate` runs the
exact production pipeline:
`build_from_extraction` (`semantic/ir_builder.py`) → `validate_ir`
(`semantic/ir_validator.py`) → `resolve_plan` (`planning/plan_resolver.py`) →
`apply_left_join_for_each` (`planning/plan_postprocess.py`) → `generate_sql`
(`generation/multitable_sql_generator.py`) → `execute_sql`
(`generation/sql_executor.py`). Here the **LLM produces the IR/extraction; the SQL
text is generated deterministically** from the resolved plan. Relational algebra
comes from `generation/relational_algebra.py`.

**B. Direct LLM SQL** (`llm_sql_direct`, `_grain`, `_variant`, and repair). These
skip the IR pipeline and ask the model for SQL text directly, then run it through
`sql_candidates/candidate_builder.py :: build_direct_sql_candidate` (execute‑only,
no IR).

**Candidate sources and how many** (assembled in `execute_sql_endpoint`,
`sql_candidates/candidate_types.py :: SOURCES`):

| source | how it's made | LLM? |
|---|---|---|
| `query_family` | deterministic family builder → IR pipeline; only if confidence ≥ threshold and IR valid | no (routing is deterministic) |
| `llm_primary` | primary IR extraction → IR pipeline | 1 (IR) |
| `llm_variant` | reframed IR extraction (1 variant if a family fired, else 2) → IR pipeline | 1–2 (IR) |
| `semantic_join_path` | Phase‑4 planner + constrained SQL — **disabled by default** | 0 (gated) |
| `llm_sql_direct` | direct question→SQL, temperature 0 | 1 |
| `llm_sql_direct_grain` | direct SQL, "fix the row grain first" prompt, temp 0 | 1 |
| `llm_sql_direct_variant` | direct SQL, reworded prompt, temp ~0.35 | 1 |
| `llm_sql_repair` | one‑shot correction of the selected SQL, only if it looks unreliable | 0–1 |

So a normal query produces roughly **4–7 candidates**. Each direct candidate is
passed through `direct_sql_violations` (see §8) and **dropped** if it violates the
explicit‑table/bridge rules.

Differences in one line each:
`llm_primary` = temp‑0 IR → deterministic SQL;
`llm_variant` = reframed/temperature IR → deterministic SQL;
`llm_sql_direct` = temp‑0 free‑form SQL;
`llm_sql_direct_grain` = grain‑aware free‑form SQL;
`llm_sql_direct_variant` = reworded, mild‑temperature free‑form SQL;
`llm_sql_repair` = one corrective free‑form SQL built from all candidates' diagnostics.

---

## 7. Every LLM call

Provider is resolved by `llm/factory.py :: get_provider`, configured from env by
`llm/config.py`. Your setup (`LLM_PROVIDER=mindrouter`,
`LLM_BASE_URL=https://mindrouter.uidaho.edu`, `LLM_MODEL_NAME=qwen/qwen3.5-122b`,
`LLM_API_STYLE=ollama`) selects `llm/providers/mindrouter_provider.py ::
MindRouterProvider`, which **extends** `llm/providers/ollama_provider.py` and posts
to the Ollama‑style `POST /api/generate` with `Authorization: Bearer <LLM_API_KEY>`
(required; missing key → `ProviderAuthError` before any HTTP). All calls go through
`get_provider().generate(prompt, options={...})` where `options` map to
`temperature`, `num_predict`, `think`.

Per single `execute_sql` request, the LLM is called here:

1. **`semantic/semantic_checklist.py :: generate_checklist`** (line ~169).
   Purpose: build the semantic checklist. Input: one JSON‑only prompt (tables,
   FK edges, value hints, question). Output: **validated checklist JSON**
   (target_entity, must_use_tables/columns, measure_column, group_by_entity,
   required_sql_shape, literals, row_grain, universe, required_group_keys,
   forbidden_hardcoded_universe). Options: `temperature 0, num_predict 400, think False`.

2. **`semantic/ai_semantic_extractor.py :: _call_ir_model`** (line ~406), invoked by
   `extract_multitable_ir_extraction`. Purpose: NL → **IR JSON** (primary).
   Options: `temperature 0, num_predict 700, think False`; one retry at 500 on empty.

3. **`_call_ir_model`** again, invoked by `extract_multitable_ir_extraction_variant`
   (1–2 times). Purpose: **IR JSON** at a reframed prompt + mild temperature.

4. **`semantic/llm_sql_direct.py :: generate_direct_sql`** (line ~248). Purpose:
   direct **SQL text**. Options: `temperature 0, num_predict 700, think False`.

5. **`semantic/llm_sql_direct.py :: _run_direct`** (line ~274) via
   `generate_direct_sql_grain`. Purpose: grain‑aware **SQL text** (temp 0).

6. **`_run_direct`** via `generate_direct_sql_variant`. Purpose: reworded **SQL
   text** at temperature ≈ 0.35.

7. **`semantic/llm_sql_repair.py :: generate_repair_sql`** (line ~129), only when
   `should_repair(...)` fires. Purpose: one corrected **SQL text**. Options:
   `temperature 0, num_predict 700, think False`.

Also present but **not** on this path by default:
`sql_candidates/semantic_join_path_candidate.py :: build_semantic_join_path_sql`
(line ~212) — SQL text, gated OFF; and `extract_semantics` (line ~146) — the
legacy single‑table extractor used only by `/query`.

Upper bound per query ≈ **7–8 LLM calls** (checklist + primary IR + 1–2 variant IR
+ direct + grain + variant + optional repair). None of the scoring/relationship
layers (Phases 2/3, probes, verifier) make LLM calls.

---

## 8. Candidate validation / scoring

**Scorer:** `sql_candidates/candidate_scorer.py :: score_candidate` (base score 50,
clamped 0–100). It parses the SQL once with `_scan_sql` (alias resolution + join
edges) and applies, in sections:

- **execution** — executed (+25), execution failed (−40), no SQL (−45), no output columns (−10), zero rows (−3 weak signal).
- **illegal join** — `_scan_sql` edges checked by `query_families/slot_extractor.py :: is_legal_edge` (rejects key=measure and unrelated key=key). **fatal** + −40.
- **required shape / concept** — from the checklist (`semantic/semantic_checklist.py :: checklist_alignment`): missing required SQL shape, missing measure/table/column; a question‑anchored missing column is **fatal**.
- **aliases** — duplicate alias in the same scope (−25) and undefined alias (−25).
- **bare CTE** — `WITH ... SELECT * FROM cte` under a comparison intent: **fatal** + −20.
- **grain alignment** (§ "9b", `semantic_checklist.py :: grain_alignment`) — GROUP BY vs `row_grain`, missing `required_group_keys`, hardcoded universe count.
- **semantic relationship verifier** ("9c", Phase 2) and **semantic join discovery** ("9d", Phase 3) — §5 above.
- **explicit table lock** ("9e", `explicit_table_lock.py :: table_lock_penalty`) — sibling/unmentioned tables, ignoring named tables, `SELECT *` fallback.
- **value grounding** — literals not among a profiled column's sampled values (−12 each).
- **shape verifier** — `sql_candidates/shape_verifier.py :: verify_shape`: **fatal** F1 = unresolved bare identifier in WHERE/HAVING/ON, **fatal** F2 = self‑comparison (`x=x`, `COUNT(*)=COUNT(*)`); penalties for weak universal, fake distinct alias, incomplete pair.

Detection map:
- **missing tables / extra‑irrelevant tables** → checklist `must_use_tables` miss + `table_lock_penalty` + Phase‑2 table‑family check.
- **unknown columns** → checklist `must_use_columns` + shape verifier F1.
- **illegal joins** → `is_legal_edge` (fatal); cross‑granularity joins → Phase 3.
- **duplicate / undefined aliases** → `_scan_sql` in the scorer.
- **self‑comparisons** → shape verifier F2 (fatal).
- **low confidence** → selector sets `low_confidence` when the winner is fatal or scores `< LOW_SCORE_THRESHOLD (40)`.
- **zero‑row weak signal** → −3 in the scorer, and `execution_probes.py` (contradiction probe) can flag over‑constrained zero‑row SQL.

**Execution‑guided probes:** `sql_candidates/execution_probes.py ::
annotate_with_probes` runs read‑only, bounded probes after scoring: a
**contradiction probe** (a zero‑row query whose relaxed form returns rows → small
penalty) and a **fanout probe** (`COUNT(*)`/`SUM` over 2+ joins that duplicates the
driving entity → small penalty). Advisory only.

**Selector:** `sql_candidates/candidate_selector.py :: select_best`. Rules in order:
(0) **fatal disqualification** — fatal candidates cannot win while any non‑fatal
executed candidate exists; (1) **consensus** — group executed candidates by
result‑set equivalence (`result_equivalence.py`), heaviest group wins; (2)
**validation‑score override** (`OVERRIDE_MARGIN 15`); (2b) **direct/repair
preference** (`DIRECT_OVERRIDE_MARGIN 10`); (3) least‑bad with warning if nothing
executed; (4) low‑confidence warning if best `< 40`. Ties break by source
priority `query_family > llm_sql_repair > llm_sql_direct(/grain/variant/
semantic_join_path) > llm_primary > llm_variant`.

**Rejection gates (outside the scorer):**
- `sql_candidates/direct_sql_enforcement.py :: direct_sql_violations` — a direct candidate that omits an explicitly‑named required table, or joins ZIP directly to a tract/geo id when a bridge is required, is **not appended**.
- A **global pre‑selection filter** and a **`[FINAL ENFORCE]`** post‑repair gate in `app.py` remove any candidate (any source) that violates those rules; if all violate, the endpoint returns **no SQL** rather than a wrong answer.

**What makes a candidate win:** it executed, it is not fatal, it agrees with other
candidates (or clearly out‑scores them), it satisfies the checklist shape/tables/
columns, and it passes the explicit‑table/bridge enforcement.

---

## 9. SQL execution layer

**Function:** `generation/sql_executor.py :: execute_sql(generated_sql, db_path,
row_limit=DEFAULT_ROW_LIMIT)`.

- Opens the DB **read‑only** via `sqlite3.connect("file:{db_path}?mode=ro", uri=True)` — it can never write.
- **Parameters** are bound, never string‑interpolated: `cursor.execute(sql, params)`.
- Fetches `row_limit + 1` rows to detect truncation; returns `columns` + `rows`.
- **Errors** are converted to typed results, never raised: `not_generated` (nothing to run), `db_unavailable` (file can't open), `sql_error` (any `sqlite3.Error`). Results are wrapped by `generation/execution_result.py` (`success_result`/`failure_result` → `to_dict`).

---

## 10. Final API response

Built at the end of `execute_sql_endpoint` (the `base` dict + `select_best`'s
`selection_meta` + `repair_meta` + `value_grounding`). Key fields:

- **`success`** — `selected.executed_ok` (the chosen SQL ran).
- **`generated_sql`** — `{generated, sql, params}` of the winner (the frontend reads `.sql`).
- **`execution`** — `{executed, columns, rows, row_count, truncated, error?, reason?}`.
- **`relational_algebra`** — RA text (only for IR‑pipeline winners; empty for direct SQL).
- **`extraction`**, **`ir`**, **`plan`**, **`validation`** — the winner's IR‑pipeline artifacts (null for direct SQL).
- **`extraction_source`** — legacy grouping: `"query_family"` if the winner is the family builder, else `"llm"`.
- **`query_family`** (+ `query_family_confidence`, `query_family_reason`, `family_guard_valid`, `family_guard_reasons`) — routing verdict.
- **`semantic_checklist`** — the corrected checklist used for scoring.
- **`selected_candidate_source`** / **`selected_candidate_label`** — which candidate won.
- **`selected_candidate_score`** and **`selected_candidate_validation`** — the winner's numeric score and its full `validation` dict (checklist/grain/semantic/shape/table_lock/probes/fatal).
- **`candidate_scores`** — one compact row per candidate `{source, label, score, executed, row_count, fatal, fatal_reasons}`.
- **`candidate_reasons`** — human‑readable scoring notes per candidate label.
- **`rejected_candidates`** — compact dicts for the non‑winners.
- **`warnings`** — selection + value‑grounding + enforcement warnings.
- **`low_confidence`** — true when the winner is fatal or scores `< 40`.
- **`repair_meta`** — `{repair_attempted, repair_triggers, repair_executed, repair_score, repair_selected, selected_source_before_repair}`.
- **`value_grounding`** — `{profiled_columns, grounded_from_eval_copy}`.
- **`tables_considered`** — the tables the sub‑graph used (large mode).

---

## 11. Two worked examples

> These are structural traces of how the current code behaves, not captured live
> runs. Assume a QCEW‑style wages table, e.g.
> `wages(area, industry, year, quarter, avg_weekly_wage)`, in **small mode**
> (full graph, no retrieval). The exact SQL depends on the model, but the
> **pipeline path and validation** are exact.

### Example 1 — single‑table filter
*"Which areas had agriculture, forestry, fishing, and hunting weekly wages above 500 in the first quarter of 1991?"*

- **Frontend request:** `POST /database/{id}/execute_sql` body `{"question": "...", "database_id": id}`.
- **Backend route:** `execute_sql_endpoint`.
- **Table selection:** small mode → full graph; `force_named_tables` finds no verbatim table name (the question names an industry *value*, not a table) → graph unchanged; `[GRAPH]` lists the wages table.
- **Checklist (`generate_checklist`):** `target_entity=wages`, `must_use_tables=[wages]`, `must_use_columns≈[wages.area, wages.industry, wages.year, wages.quarter, wages.avg_weekly_wage]`, `measure_column=wages.avg_weekly_wage`, `required_sql_shape=plain_select`, `literals=[500, 1991, 1, "Agriculture, Forestry, Fishing and Hunting"]`. `correct_checklist_tables` keeps `[wages]`.
- **IR / extraction:** `llm_primary` → `filters` for industry/year/quarter and a `>` filter on `avg_weekly_wage`, `select=[wages.area]`; deterministic SQL from the plan. `llm_variant` similar.
- **LLM calls:** checklist (1) + primary IR (1) + variant IR (1–2) + direct (1) + grain (1) + variant (1) = ~6.
- **Candidate SQLs:** all resolve to `SELECT area FROM wages WHERE industry = '...' AND year = 1991 AND quarter = 1 AND avg_weekly_wage > 500` (direct candidates likely identical; IR path builds the same via plan).
- **Validation/scoring:** all execute → +25; no joins (no illegal‑join/fatal risk); checklist shape `plain_select` satisfied; value grounding checks the literal `'Agriculture…'` against sampled `industry` values; Phases 2/3 inactive (no bridge/geo tokens, no cross‑domain join); explicit‑table‑lock inactive (no named tables).
- **Selected SQL:** the consensus group (identical result set) wins; source is typically `llm_sql_direct` or `query_family`/`llm_primary` depending on ties.
- **Execution output:** `execution = {executed:true, columns:["area"], rows:[["…"],…], row_count:N}`.
- **Response shape:** `success:true`, `generated_sql.sql`, `execution`, `semantic_checklist`, `candidate_scores` (all similar), `selected_candidate_source`, `low_confidence:false`.

### Example 2 — multi‑table / time comparison (self‑join)
*"Which areas had higher agriculture, forestry, fishing, and hunting weekly wages in the first quarter of 1994 than in the first quarter of 1990, and how much did wages increase?"*

- **Frontend request / route:** same as above.
- **Table selection:** small mode → full graph; still a single physical table, but the answer needs a **self‑join** of `wages` to itself on `area` (+ industry).
- **Checklist:** `measure_column=wages.avg_weekly_wage`, `comparison_logic ≈ "1994 Q1 value greater than 1990 Q1 value"`, `required_sql_shape=self_join` (or `comparison_subquery`), `literals=[1994,1,1990,1,"Agriculture…"]`, `output_columns≈[area, increase]`.
- **IR / extraction:** `llm_primary`/`llm_variant` may populate `aliases`, `alias_joins`, `alias_filters`, `alias_select`, or `explicit_joins`/`derived_relations`/`main_from` to express the two‑period self‑join and the difference. This is where the IR path most often struggles (see Weaknesses); the **direct** candidates usually express the self‑join more reliably.
- **LLM calls:** same ~6 (checklist + IRs + 3 direct); optional **repair** (1) if the winner is weak, e.g. it returned zero rows or missed the `increase` column.
- **Candidate SQLs:** the intended shape is a self‑join:
  `SELECT a.area, a.avg_weekly_wage - b.avg_weekly_wage AS increase
   FROM wages a JOIN wages b ON a.area = b.area AND a.industry = b.industry
   WHERE a.industry = '…' AND a.year = 1994 AND a.quarter = 1
     AND b.year = 1990 AND b.quarter = 1
     AND a.avg_weekly_wage > b.avg_weekly_wage;`
- **Validation/scoring:** the self‑join `a.area = b.area` is a **same‑named key join** → legal (`is_legal_edge`); shape verifier F2 guards against accidental `x=x` self‑comparison; the scorer rewards the `self_join`/`comparison_subquery` shape from the checklist; a candidate that drops the `increase` output or uses a bare `WHERE`‑less join scores lower; execution‑guided **fanout probe** watches for row inflation if any extra join is added.
- **Selected SQL:** the executed, non‑fatal candidate matching the checklist shape and returning both `area` and `increase`; consensus between a direct candidate and the IR/repair candidate strengthens the pick.
- **Execution output:** `columns:["area","increase"]`, `rows:[["…", 123.0], …]`.
- **Response shape:** as in Example 1, plus a populated **`repair_meta`** if repair ran, and `selected_candidate_validation.shape` showing the self‑join check.

---

## Current weaknesses / confusing parts

1. **Phase‑1 HoPF is a library, not yet a wired data source.** `hopf_relationship_evidence.py` computes evidence and a `usable` flag, and Phases 2/3 *check* graph relationships for `source == "hopf_inferred"` with confidence ≥ 0.92 — but nothing currently **writes** `hopf_inferred` edges into the graph the endpoint uses. So HoPF's influence at runtime is mostly latent. This is the biggest gap between "documented research layer" and "live behavior."
2. **Two overlapping enforcement mechanisms.** The explicit‑table/bridge rules are enforced both as scorer penalties (`explicit_table_lock`, Phases 2/3) *and* as hard candidate rejection (`direct_sql_enforcement` + the `[ENFORCE]`/`[FINAL ENFORCE]` gates in `app.py`). They mostly agree, but the split (advisory vs. hard reject) is easy to misread; a candidate can be penalized in the score yet still survive, or be dropped entirely before scoring.
3. **Schema graph vs. physical DB vs. metadata can disagree.** `force_named_tables` exists precisely because `database_tables` metadata can be missing tables that are physically present (the db38 case). Large‑mode retrieval, metadata, and the physical file are three sources of truth that must be reconciled per request; the `[GRAPH FORCE]`/`[METADATA]` logs are the way to see mismatches.
4. **IR path is weaker than direct SQL on complex shapes.** Self‑joins, time comparisons, per‑group extrema, set‑division, and anti‑joins depend on many IR fields (`aliases`, `alias_joins`, `derived_relations`, `main_from`, `set_division`, `top_per_group`). When the LLM under‑fills these, the deterministic generator produces flat SQL; the direct‑SQL candidates and the one‑shot repair are what usually rescue these queries.
5. **Query families are narrow.** `route_and_build` only fires for the shapes it was built for (petshop‑style). For arbitrary benchmark schemas it usually declines, so most real queries are decided among the LLM candidates.
6. **Candidate count and LLM cost.** A single question can trigger ~6–8 LLM calls (checklist, 2–3 IR extractions, 3 direct samples, optional repair). On a remote provider this is the dominant latency; there is no caching of identical prompts within a request.
7. **`success` reflects execution, not correctness.** `success:true` only means the winning SQL executed. A wrong‑but‑executable query still returns `success:true`; `low_confidence`, `warnings`, `candidate_scores`, and `selected_candidate_validation` are where correctness signals live.
8. **Legacy `/query` path still exists.** It uses the single‑table `extract_semantics` and chat state and is intentionally unused by the workspace UI, but it can confuse readers grepping for "the query endpoint."
