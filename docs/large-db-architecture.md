# SpiderSQL — Large-Database (Spider 2.0-scale) Architecture Plan

Goal: support databases with **100–1000+ tables** (Spider 2.0 / BigQuery /
Snowflake style) **without** breaking the existing small-database flow. The
system becomes **dual-mode**: `small` (current behavior) and `large` (lazy,
query-first). Mode is a per-database property; everything else branches on it.

The guiding principle: **never materialize the whole schema graph or send it to
the LLM**. For large DBs we load metadata only, retrieve a small relevant table
subset per query, and build a throwaway sub-graph for that query.

---

## 0. Core idea in one paragraph

A large database stores only **table names + row counts** up front. Columns are
loaded **lazily** (on table click, or when a query selects the table) and cached.
At query time a **retriever** picks the **top-k relevant tables**, we ensure
their columns are loaded, build a **sub-graph** of just those tables (with
relationships inferred among them), and feed *only that sub-graph* to the
existing IR → plan → SQL pipeline. Relationship review becomes optional.

---

## 1. Backend architecture changes

Current pipeline (unchanged at the core):
`extract_multitable_ir_extraction(question, graph)` → `build_from_extraction` →
`validate_ir` → `resolve_plan(ir, graph)` → `generate_sql` → `execute_sql`.

The key insight: **these functions already take a `graph` argument.** We do not
rewrite them. We change *what graph we hand them*:

- **Small mode:** full graph from `get_database_graph(database_id)` (today's path).
- **Large mode:** a **sub-graph** built from only the retrieved tables.

New backend modules (all in the existing layered layout):

- `schema/lazy_loader.py`
  - `ensure_table_columns(database_id, table_name)` — if a table's columns aren't
    loaded yet, run `extract_table_columns(db_path, table)` and persist via
    `add_table_columns`, set `columns_loaded=1`. Idempotent + cached.
  - `list_tables(database_id, q=None, limit=50, offset=0)` — paginated table
    names + `row_count` + `columns_loaded` (no columns).

- `retrieval/table_retriever.py`
  - `build_table_index(database_id)` — builds/refreshes an FTS5 index of
    `(table_name, column_names, description, sample_values)` per table. Uses
    SQLite **FTS5** (built into `sqlite3`, no new dependency). Deterministic.
  - `retrieve_tables(database_id, question, k=8)` — FTS5 `MATCH` + bm25 ranking,
    plus a deterministic boost when a table/column name appears literally in the
    question. Returns `[(table_name, score)]`. No LLM, no full scan.
  - Pluggable interface so an embedding retriever can be added later behind the
    same signature.

- `schema/subgraph_builder.py`
  - `build_subgraph(database_id, table_names)` — returns the **same graph dict
    shape** `get_database_graph` returns, but limited to `table_names`:
    1. `ensure_table_columns` for each selected table,
    2. include **explicit** relationships among the selected set (Level 1),
    3. compute **query-time** relationships among the selected set (Level 3) and
       attach them (ephemeral — not persisted).
  - Because the shape matches, `resolve_plan` / `generate_sql` consume it as-is.

- `relationships/relationship_levels.py` (refactor of today's detection)
  - `extract_foreign_keys(database_id)` — Level 1, cheap: `PRAGMA
    foreign_key_list(<table>)` per table on the SQLite file (metadata only, no row
    scan) + DDL-declared FKs (schema/Spider2 path already does this). Persist
    `relationship_type="foreign_key"`, `confidence=1.0`, `confirmed=1`.
  - `suggest_relationships_for(database_id, table_names)` — Level 2, name-based
    inference (`customer_id → customers.customer_id`) limited to a **set** of
    tables. Persist with `confidence<1.0`, `confirmed=0` (or return ephemeral).
  - `infer_query_time_relationships(subgraph_tables)` — Level 3, FK + name-based
    among the selected tables only; **never stored**.

Mode detection:

- `LARGE_DB_TABLE_THRESHOLD = 40` (tunable). At creation, count tables; if above
  threshold → `mode="large"`, else `"small"`.

---

## 2. Frontend changes

All branches on `database.mode` (fetched from a new `/database/{id}/meta`).

- **`DatabaseSummaryCard.jsx`**
  - Small mode: unchanged (chips + lazy preview via `/graph`).
  - Large mode: show `table_count`, a **search box** + **paginated/virtualized**
    table list backed by `GET /database/{id}/tables?q=&limit=&offset=`. Clicking a
    table calls `GET /database/{id}/table/{table}/columns` (lazy). No `/graph`
    call (never build the full graph for large DBs).

- **`RelationshipReviewCard.jsx`**
  - Small mode: unchanged (load `/relationships`, finalize required).
  - Large mode: becomes an **optional** panel. It does **not** block querying.
    When opened it shows explicit FKs immediately and offers "suggest
    relationships for these tables" scoped to a chosen/searched subset, not the
    whole DB.

- **`ConversionPage.jsx` / `App.jsx`** — gating change:
  - Today: `canQuery = activeDatabaseId && relationshipsFinalized`.
  - New: `canQuery = activeDatabaseId && (mode === "large" || relationshipsFinalized)`.
  - Large DBs are **query-first**: the input appears as soon as the DB is active.
    The setup/summary message still appears, just without a forced finalize step.

- **`DatabaseWorkspaceCard.jsx`** — already creates DBs via `onDatabaseCreated`;
  add a small "Large database — query-first" note when `mode==="large"`. The
  Spider 2.0 importer already produces large schemas, so this is where it shows.

- Add lightweight list **virtualization** (windowing) for the table list so
  1000 chips never render at once.

---

## 3. How schema should be stored

Reuse `app_data.db` metadata tables; add a few columns (idempotent migration):

- `databases`: add `mode TEXT DEFAULT 'small'`, `table_count INTEGER DEFAULT 0`.
- `database_tables`: add `columns_loaded INTEGER DEFAULT 0`.
- `database_relationships`: already has `relationship_type`, `confidence`,
  `confirmed`. Add `source TEXT` (`explicit_fk` | `suggested_name`) to make the
  level explicit. Query-time (Level 3) relationships are **not stored**.
- New FTS5 table (one per process, keyed by database_id) for retrieval:
  `table_docs USING fts5(database_id UNINDEXED, table_name UNINDEXED, doc)`.

The per-database SQLite file (`db_N/data.db`) is unchanged — it remains the
source of truth for actual table/column structure; `extract_table_columns`
already reads it lazily per table.

Small DBs keep eager loading (columns for all tables at import). Large DBs store
table rows with `columns_loaded=0` and populate columns on demand.

---

## 4. How retrieval should work (query-time table selection)

Per query (large mode only):

1. **Index (once, cached):** `build_table_index(database_id)` writes one FTS5 doc
   per table = `table_name + column names (+ description/sample values if loaded)`.
   For a brand-new large DB, columns may not be loaded yet, so the initial doc is
   `table_name` + any DDL column names we already have (Spider2/DDL import gives
   us column names cheaply even before full extraction).
2. **Retrieve:** `retrieve_tables(database_id, question, k)`:
   - FTS5 `MATCH` over the question tokens, ranked by `bm25`,
   - deterministic boosts: exact table-name / column-name hits in the question,
   - return top-k (default k=8, configurable; cap to keep LLM context small).
3. **Hydrate:** `ensure_table_columns` for the selected tables.
4. **Sub-graph:** `build_subgraph(database_id, selected)` (Level 1 + Level 3
   relationships among the selected set).
5. **Generate:** run the existing IR → plan → SQL pipeline on the sub-graph only.

This guarantees the LLM/extraction step sees **only k tables**, regardless of DB
size. Retrieval is deterministic and dependency-free; embeddings can be layered
in later behind `retrieve_tables` without changing callers.

---

## 5. How the relationship system is redesigned (3 levels)

- **Level 1 — Explicit (stored, confidence 1.0, confirmed).** From SQLite
  `PRAGMA foreign_key_list` and DDL-declared FKs. Cheap (metadata only) → compute
  at import even for large DBs.
- **Level 2 — Suggested (stored, confidence <1.0, unconfirmed).** Name-based
  inference. For **small** DBs compute globally at import (today's behavior). For
  **large** DBs do **not** precompute globally; compute on demand for a table
  subset (relationship panel) or lazily.
- **Level 3 — Query-time (never stored).** Inferred among the retrieved top-k
  tables at query time (FK + name-based), attached to the sub-graph only.

Review is **mandatory in small mode** (preserves current UX) and **optional in
large mode** (query-first). Value-overlap detection (the expensive row-scanning
detector) is **only** used in small mode; large mode relies on FK + name-based +
query-time, none of which scan rows.

---

## 6. How SQL generation should change

Minimal: the generator/planner are unchanged. Only the **graph they receive**
changes.

- Add a single branch in the `execute_sql` / `generate_sql` handlers:
  - `mode == "small"` → `graph = get_database_graph(id)` (today).
  - `mode == "large"` → `selected = retrieve_tables(id, question, k)`;
    `graph = build_subgraph(id, selected)`.
- Everything downstream (`extract_multitable_ir_extraction`,
  `build_from_extraction`, `resolve_plan`, `generate_sql`, `relational_algebra`)
  consumes the sub-graph exactly as it consumes the full graph today.
- Add a "tables considered" field to the response (the retrieved set + scores) so
  the UI can show *why* those tables were used and let the user pin/adjust.

Optional later: if retrieval misses a needed table, allow the user to add a table
to the query context manually (re-run with an augmented `selected` set).

---

## 7. Endpoints to add / change

Add:
- `GET  /database/{id}/meta` → `{ mode, table_count, query_ready }`.
- `GET  /database/{id}/tables?q=&limit=&offset=` → paginated names + row_count +
  columns_loaded.
- `GET  /database/{id}/table/{table}/columns` → lazy columns (load + persist if
  needed).
- `POST /database/{id}/retrieve` `{ question, k }` → top-k tables + scores
  (preview/debug; also used internally by execute).
- `GET  /database/{id}/subgraph?tables=a,b,c` → sub-graph for an explicit set
  (used by lazy preview / manual context editing).

Change:
- `POST /database/{id}/execute_sql` → retrieval-first for large mode (small mode
  unchanged).
- `GET  /database/{id}/graph` → keep for small mode; for large mode either return
  metadata-only (no columns/relationships) or require a `tables=` param so it can
  never build the whole graph.
- `POST /upload-database`, `/create-database-from-schema`, `/spider2/import` →
  set `mode` + `table_count`; for large mode skip eager column extraction and
  skip global value-overlap relationship detection (do cheap FK only).

Unchanged: `/databases/{user}`, `/conversation/*`, auth, etc.

---

## 8. What to remove / gate behind small mode

Nothing is deleted outright (don't break small DBs). These become **small-mode
only**:

- Eager `add_table_columns` for **all** tables at import.
- Global `detect_relationships` value-overlap scan at import.
- Forced relationship **finalize** before querying.
- Frontend `/graph` full-graph fetch for the summary/preview.
- Sending the full schema to the LLM (replaced by sub-graph for large mode; small
  mode already fits).

---

## 9. Step-by-step migration plan (safe, non-breaking)

Each phase is independently shippable and gated by `mode`; small DBs always take
the existing path, so nothing breaks mid-migration.

- **Phase 0 — Schema migration (no behavior change).** Add `mode`,
  `table_count`, `columns_loaded`, `source` columns via an idempotent migration
  in DB init. Existing rows default to `mode='small'`, `columns_loaded=1`.
- **Phase 1 — Lazy columns + table listing.** Add `lazy_loader`, `/tables`,
  `/table/{t}/columns`, `/meta`. Frontend summary uses `/tables` for large mode
  only. Small mode untouched.
- **Phase 2 — Mode detection at import.** Set `mode`/`table_count` on create;
  large mode skips eager column extraction + value-overlap detection (cheap FK
  only). Spider 2.0 imports now land as `large`.
- **Phase 3 — Retrieval + sub-graph + query-first.** Add `table_retriever`
  (FTS5) and `subgraph_builder`; branch `execute_sql` for large mode; flip
  `canQuery` to query-first for large mode. **This is the load-bearing phase.**
- **Phase 4 — Relationship levels + optional review.** Refactor detection into
  Levels 1/2/3; make review optional/scoped for large mode; keep small-mode
  review mandatory.
- **Phase 5 — Polish.** List virtualization, "tables considered" UI with manual
  pin/add, retrieval tuning (k, boosts), optional embedding retriever.

Rollback at any phase: large-mode code is **additive** and gated; setting the
threshold very high makes everything `small` (existing path), though the small
path is not meant to scale — so the real safety is that small DBs never touch the
new code.

---

## Performance budget (targets)

- Import of a 1000-table DB: O(tables) metadata inserts + cheap FK PRAGMA; **no**
  column extraction, **no** row scans. Seconds, not minutes.
- Table list: paginated (50/page) + FTS search → constant-time UI.
- Per query: retrieve k≈8 tables (FTS, ms) + hydrate k tables' columns (cached
  after first use) + sub-graph build → LLM sees ≤k tables. Bounded regardless of
  DB size.
- Frontend: virtualized lists; never render 1000 chips; never fetch the full
  graph.

---

## Risks / decisions to confirm

1. **Threshold value** (40?) for small vs large — confirm or make it a setting.
2. **k** (default 8) and whether to expose a "add table to context" control.
3. **Retriever**: FTS5-only now (deterministic, zero-dep) vs. add embeddings
   later — recommend FTS5 first.
4. **Relationship persistence for large DBs**: store suggested (Level 2) lazily
   vs. always ephemeral — recommend lazy-store on first review.
