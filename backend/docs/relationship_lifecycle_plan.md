# SpiderSQL Relationship Lifecycle — Implementation Plan

Status: approved for implementation. No behavior is changed until each step is
implemented and its tests pass. Nothing is staged/committed until the full set
of planned changes and tests is complete.

## Goals / architecture

SpiderSQL supports databases with declared relationships and databases without.

1. Whenever a database is loaded, first check whether the user or the database
   has declared relationships. When declared relationships exist they are final
   and authoritative. Automatic inference must not override, replace, or add
   competing inferred relationships.
2. For a database with no declared relationships, inspect the schema (table and
   column names) and infer relationships generically, saved as an *unfinalized
   suggestion set* for review.
3. After relationships are reviewed/finalized and saved, every query uses ONLY
   the finalized stored relationship set. Query execution never rediscovers,
   regenerates, merges, or creates relationships. Running more queries never
   changes the graph.
4. Relationships change only when the user explicitly edits them or explicitly
   requests redetection.

### User-declared precedence (clarification)

If user-declared relationships exist, they are the final authoritative set.
Inference is NOT automatically added to supplement them. Inference runs only
when neither user-declared nor database-declared relationships exist, or when
the user explicitly requests redetection (which returns the set to review).

## Core model: origin vs finality

- **Origin** — per-edge `database_relationships.source`:
  `declared_fk` | `user` | `inferred` | `benchmark_trusted`.
  Origin never implies legality by itself.
- **Finality** — per-database `databases.relationships_finalized` (0/1).
  When 1, the stored rows ARE the authoritative graph and queries run on them.
  When 0, the query interface is disabled for that database.

An `inferred` edge begins as an unapproved suggestion (DB `finalized=0`); after
review/finalize the same rows (still `source='inferred'`) become authoritative.
Origin is preserved; only finality changes.

## Precedence (resolver)

`services/relationship_resolver.py :: resolve_and_store_relationships(database_id,
db_path=None, *, force_inference=False)`:

- Preserve existing `source='user'` edges (authoritative) at all times.
- Authoritative sources present (user OR declared_fk OR benchmark_trusted):
  store the union of authoritative edges, set `finalized=1`, DO NOT run inference.
- No authoritative source AND not an explicit redetect: run generic inference,
  store as `inferred`, set `finalized=0` (review required).
- `force_inference=True` (explicit redetect): preserve `user` edges, refresh
  declared/benchmark, re-run the fixed inference for the remainder, set
  `finalized=0` for re-review (unless the resulting set is entirely
  authoritative, in which case `finalized=1`).

## File-by-file plan

### Persistence + schema
- `db/auth_db.py` — add `relationships_finalized INTEGER DEFAULT 0` to
  `databases` (additive). One-time non-destructive backfill at init: set
  `finalized=1` for databases that already have a non-empty stored relationship
  set (preserves current behavior); `0` for empty-stored databases.
- `db/database_service.py` — write `source` in the `add_relationships` INSERT;
  add `set_relationships_finalized`, `get_relationships_finalized`,
  `add_user_relationship`, `update_relationship`, `delete_relationship`,
  `get_declared_relationships` (source in declared_fk/user).

### Detection (RC-A)
- `schema/relationship_detector.py` — fix mis-targeting under saturated
  value_overlap (tie-break by structural name evidence; ambiguous -> lower
  confidence); schema-driven measure/non-key exclusion (replace static
  `_MEASURE_RE`); emit `source='inferred'`; retire `AUTO_CONFIRM_*` (inference
  never sets authority/finality).

### Load / resolve / redetect
- `services/relationship_resolver.py` (new) — precedence above.
- `services/metadata_service.py` — route relationships through resolver; remove
  large-mode `rel_provider = lambda: []` so large DBs infer-and-store at load.
- `app.py` upload endpoints — pass through resolver.
- `app.py redetect_relationships` — `resolve_and_store_relationships(force_inference=True)`.
- `app.py POST /database/{id}/relationships/finalize` (new) — set finalized=1.

### User editing (authoritative)
- `app.py` — `POST/PATCH/DELETE /database/{id}/relationships[/{rel_id}]`,
  writing `source='user'`; edits set finalized=0 until re-finalized.

### Read-only query path + gate
- `app.py` query entrypoints (`execute_sql`, `check_containment`, plan/generate)
  — reject when `finalized=0` with `relationships_not_finalized`.
- `app.py run_nl_sql_pipeline` — delete `augment_local_benchmark_relationships`
  and `augment_graph_with_physical_fks`.
- `schema/subgraph_builder.py` — delete query-time name inference; stored edges
  filtered to selected tables only.
- `schema/query_context.py` — large-mode table expansion uses stored edges.

### Validators (membership, not label)
- `sql_candidates/semantic_relationship_verifier.py` — a join is legal iff a
  matching edge is present in the loaded finalized graph (either direction);
  remove `relationship_type=='foreign_key'` blanket acceptance.
- `validators/fanout_validator.py` — treat every edge in the finalized graph as
  a real relationship; drop type/confidence heuristic acceptance.

### Benchmark relationships (setup, not query)
- `app.py run_nl_sql_pipeline` — augmentation removed (above).
- resolver — import trusted benchmark edges at setup/redetect, store as
  `source='benchmark_trusted'`, authoritative, finalized. `local_benchmarks/
  benchmark_relationships.py` keeps the catalog but is not imported by queries.

### Table-mention (RC-B)
- `sql_candidates/candidate_scorer.py:442` and
  `query_families/builders/__init__.py` (5 sites) -> strict
  `schema/table_mention.explicit_table_mentions`.
- `query_families/slot_extractor.py::_forms` -> contiguous-phrase match for
  multi-token names + parent/child disambiguation.

## Testing order

1. Schema flag + backfill.
2. Persistence/provenance (source write; user add/edit/delete; declared filter).
3. Detector unit (dense-integer-key schema; naming-gap FK; numeric non-key).
4. Resolver unit (precedence incl. user-declared exclusivity of inference).
5. Query gate (finalized=0 rejects; finalize enables).
6. Read-only invariance (same query N times identical graph; no added edges).
7. Validator legality (membership-based; label-shaped absent join rejected).
8. Editing endpoints (CRUD + validation + authority across redetect).
9. Regression suites + PetShop 30.
10. DB52 deliberate redetect -> review -> finalize -> 500 diff.
11. Full 500.

## Rollout

No stored relationships modified; nothing auto-redetected. Backfill only marks
already-working databases finalized. Empty-stored databases (15 large `bq*`,
Lahman db49, TPC-DS db51) become query-disabled until explicitly detected and
finalized. DB52 keeps its current edges until the deliberate redetect.
