# SpiderSQL — Semantic Contract Layer: Research Review & Implementation Plan

Scope: close the gap between *executable* SQL (49/50 on the DB46 clinic benchmark)
and *semantically correct* SQL (23/50). The failure is no longer table/relationship
discovery — it is loss of **grain, fanout control, quantifier scope, comparison
population, and temporal meaning** between the question, the checklist/IR, SQL
generation, and scoring. No code is changed until this plan is approved.

---

## 1. Current pipeline flow (what exists today)

```
question
 └─ LAYER 1  table-picking      resolve_query_graph → FK expansion → force_named_tables
 └─ LAYER 2  checklist          generate_checklist  (1 LLM call → validated dict)
                                 correct_checklist_tables (schema-linker)
 └─ LAYER 3  IR extraction      extract_multitable_ir_extraction (+2 variants)
 └─ LAYER 4  SQL writing        generate_direct_sql / _grain / _variant  (free-form LLM SQL)
                                 build_candidate (IR→plan→SQL) for family/primary/variant
 └─ LAYER 5  scoring            score_candidate → checklist_alignment, grain_alignment,
                                 semantic_sql_guards (Stage A), verify_shape, probes
 └─ LAYER 5b enforcement        direct_sql_violations (explicit-table lock)
 └─ LAYER 6  selection          select_best (fatal candidates disqualified) → repair → execute
```

The candidate that usually wins on hard questions is a **direct-SQL** candidate
(Layer 4), scored purely on its SQL text vs. the checklist. The IR path (Layer 3)
carries more structure (`anti_exists`, `top_per_group`, `universal`, `set_division`)
but is frequently not the winner, so its structure does not protect the answer.

### The checklist today (the only semantic contract that exists)
`{target_entity, output_columns, must_use_tables, must_use_columns,
measure_column, group_by_entity, comparison_logic(free text), required_sql_shape,
literals, row_grain(free text), universe(free text), required_group_keys,
forbidden_hardcoded_universe}`

Critical gaps in this contract:
- `measure_column` is a **bare column** — no aggregation function, **no grain**.
- `comparison_logic`, `row_grain`, `universe` are **free text**, not machine-checkable.
- **No** representation of: measure grain vs. comparison grain, comparison
  **population** (zero-match inclusion), **quantifier** type (∀/∃/coverage/both/none/
  same-event), **fanout/cardinality** safety, **temporal** semantics, or **semantic
  types** for feasibility.

### The scorer today (why wrong meaning still wins)
`checklist_alignment` rewards **ingredient presence**: is the measure column *name*
in the SQL, are the table/column *names* present, is a shape *keyword* present, are
literals present. `grain_alignment` (advisory, penalty-only) only checks that
`required_group_keys` appear in GROUP BY and that an every/all query doesn't hardcode
a universe count. `semantic_sql_guards` (Stage A) is fatal but only for Cartesian
joins, uncorrelated NOT EXISTS, constant-as-measure, and ranking-by-id. **Nothing
validates aggregate grain, join fanout, quantifier scope, comparison population,
temporal frame, or type feasibility.** This is Root Cause 6, and it is the meta-cause:
because scoring checks ingredients, and self-consistency across candidates shares the
same grain error, wrong-meaning SQL is selected as a normal success.

---

## 2. Files involved (by layer)

| Layer | File(s) |
|---|---|
| Checklist | `semantic/semantic_checklist.py` (prompt, `_clean_checklist`, `checklist_alignment`, `grain_alignment`) |
| Schema linking | `semantic/schema_linker.py`, `schema/table_mention.py` |
| IR | `semantic/ai_semantic_extractor.py`, `semantic/ir_builder.py`, `semantic/semantic_ir.py`, `query_families/slot_extractor.py` |
| Direct SQL | `semantic/llm_sql_direct.py`, `generation/multitable_sql_generator.py` |
| Scoring | `sql_candidates/candidate_scorer.py`, `sql_candidates/semantic_sql_guards.py`, `sql_candidates/shape_verifier.py`, `sql_candidates/semantic_relationship_verifier.py` |
| Relationships/keys | `retrieval/relationship_expansion.py`, `local_benchmarks/benchmark_relationships.py`, `query_families/slot_extractor.py` (PK/unique/FK, `is_legal_edge`) |
| Selection/repair | `sql_candidates/candidate_selector.py`, `sql_candidates/*repair*`, `app.py` (`run_nl_sql_pipeline`, controlled-failure gate) |

---

## 3. Root cause → where information is lost / could be preserved / could be validated

| RC | Lost at | Preserve at | Validate at |
|---|---|---|---|
| **1 Entity/measure grain** (Q02,04,13,40,48) | Checklist: `measure_column` has no aggregation or grain; direct-SQL prompt gets only free text | Add typed `measures[]` (expression, aggregation, source_grain, measure_grain) + `comparison{left_grain,right_measure,population}` to contract; pass to generator | AST: the aggregate’s argument grain must equal the target/comparison grain; comparing a per-row value to an AVG of per-row values is a fatal grain mismatch |
| **2 Fanout** (Q10,24,41,42,43,49,50) | Not represented anywhere; scorer has no cardinality model | Contract records measure source table + its key; PK/unique/FK give the one-vs-many side | AST + cardinality: measure on the “one” side, joined to a “many” table, aggregated after the join, with no pre-aggregation/DISTINCT-key/EXISTS → fatal |
| **3 Quantifiers/scope** (Q07,23,28,29,30,47) | Checklist collapses “both/every/none/same-event” to `required_sql_shape` + filters | Add typed `quantifiers[]` (type ∀/∃/coverage/none, subject_grain, child_grain, requirement, require_nonempty) and `existence_rules[]` | AST: `IN(A,B)` ≠ coverage of both; `COUNT(col)` ≠ count of true; ∀ needs anti-exists of a violating child **and** a non-empty subject set; “same X” must reuse the same key |
| **4 Comparison population** (Q08) | Checklist has no population concept; generator counts only matching rows | Add `comparison_populations[]` (entity, grouping, include_zero_match) inferred from “average <entity>” wording | AST: when include_zero_match, the group base must be the full parent entity via LEFT JOIN + conditional agg + COALESCE(0), not an inner-join-filtered set |
| **5 Temporal** (Q33,36,37) | Only shape-checked (has window/LAG); calendar vs. available-row distinction lost | Add `temporal_rules` (time_grain, ordering_col, cumulative vs period, prev-available vs prev-calendar, consecutive-run, gap policy, frame, partition, tiebreak) | AST: “cumulative” needs a running frame (UNBOUNDED PRECEDING→CURRENT); “previous month” needs calendar adjacency (spine or month arithmetic), not bare LAG; “two consecutive increases” needs 3 adjacent period totals before filtering |
| **6 Ingredient scoring** (Q03,30,36,47) | Scoring = keyword/ingredient presence; self-consistency shares the same error | Introduce a typed **semantic contract** as the object of validation | Contract validators (RC1–5,7) produce fatal/penalty independent of the LLM; score is subordinate to semantic validity; all-fatal → `no_semantically_valid_sql` |
| **7 Schema feasibility** (Q21) | No semantic-type check; text-compatible ≠ concept-compatible | Add `semantic_types` per referenced column (state/city/date/amount/id-of-entity) | AST + types: both sides of a comparison must be the same semantic concept; missing concept → controlled `unsupported_semantic_comparison` |

---

## 4. Paper review

Format: mechanism → applicability (**directly applicable** / **adaptable** / **not sufficient**) → limitation → proposed SpiderSQL adaptation.

| # | Paper / system | Mechanism | Applicability | Limitation | Proposed adaptation |
|---|---|---|---|---|---|
| 1 | **HoPF** (holistic PK/FK) | PK/FK + cardinality evidence | Adaptable | Discovery only | Feed one-vs-many cardinality into the **fanout validator** (RC2) |
| 2 | **LLM-FK** (multi-agent FK) | Semantic FK validation | Not sufficient | Relationship correctness only | N/A to grain; already have FK layer |
| 3 | **Metanome** (profiling, UCC/IND) | Uniqueness, inclusion deps, cardinality | Directly applicable | Offline profiling | Uniqueness/IND → detect one-to-many + measure source grain (RC1/2) |
| 4 | **WarpGate** / 5 **Aurum** | Semantic join / discovery graph | Not sufficient | Join discovery, already solved | Keep for retrieval; irrelevant to grain |
| 6 | **Self-consistency** | Multi-candidate consensus | **Not sufficient — this is the trap** | All candidates share the same grain error → consensus is confidently wrong (exactly DB46) | Replace “consensus = correct” with an **independent contract oracle** |
| 7 | **RAT-SQL** | Relation-aware schema encoding/linking | Adaptable | Linking, not grain | Reuse for **semantic types** (RC7 feasibility) |
| 8 | **IRNet / SemQL** (EMNLP’19) | Typed IR that abstracts away JOIN/GROUP BY, inferred at synthesis | **Adaptable (concept)** | Full SemQL is a learned grammar decoder | Adopt the *idea*: a **typed contract** above SQL that fixes grain/aggregation before SQL text |
| 9 | **NatSQL** (2021) | Simplified SQL IR closer to NL (drops GROUP BY/HAVING/set-ops) | **Adaptable** | Still no grain/fanout/quantifier semantics; needs schema converter | Use its “commit to NL meaning first” framing as the contract’s shape; not a generation target |
| 10 | **PICARD** (EMNLP’21) | Constrained incremental decoding (grammar/schema-valid) | **Not sufficient / not applicable** | Syntax + schema validity only; cannot enforce grain/fanout/quantifier; we don’t control the MindRouter decoder | Do **not** adopt; validate post-hoc instead |
| 11 | **BRIDGE** | Value/cell schema linking | Adaptable | Linking/value grounding | Feed value profiles into **semantic types** + literal coverage |
| 12 | **QPL — Semantic Decomposition** (Eyal et al., Findings-EMNLP’23) | Modular, **grain-explicit** query-plan IR; decompose SQL into executable sub-plans; human alignment 67% vs 34% for SQL | **Directly applicable (concept)** | Full QPL is a parsing target with a SQL↔QPL translator | Model the contract’s **aggregation scopes / grain per step** on QPL; validate that each aggregate’s grain matches its plan step |
| 13 | **Break / QDMR** (Wolfson et al., TACL’20) | Question Decomposition Meaning Representation with typed operators (select/filter/project/aggregate/group/**comparative**/**superlative**/union/intersection) | **Adaptable** | Not SQL-specific; needs mapping to schema | Basis for the **quantifier + comparison-population** representation (RC3/4) |
| 14 | **Test-suite semantic evaluation** (Zhong, Yu, Klein, EMNLP’20) | Denotation on a distilled set of DB states = tight upper bound on **semantic** accuracy; catches errors execution-accuracy misses | **Adaptable (strongest oracle idea)** | Needs a gold/reference query | Adopt as **property-based execution probes** on synthetic DB states (duplicate-row probe for fanout, zero-entity probe for population, vacuous-truth probe for ∀) — a reference-free approximation |
| 15 | **Cosette** (CIDR’17) / **VeriEQL** (2024) | Bounded SQL **equivalence** with counterexamples; K-relations/multiplicity model exposes the **COUNT/fanout bug** | **Adaptable (insight, not solver)** | Runtime solver is heavy; needs a reference query | Use the *multiplicity insight* to justify the fanout validator; optionally VeriEQL-style bounded check between a candidate and a pre-aggregated rewrite as a probe |
| 16 | **Execution-guided decoding** (Wang et al., 2018) | Prune candidates that error / produce invalid partials at decode time | **Adaptable** | We generate whole SQL, not token-by-token | Extend existing `execution_probes` with grain/fanout/population **property probes** |
| 17 | **DIN-SQL** (Pourreza & Rafiei, NeurIPS’23) | Decompose generation into sub-problems + **self-correction** | **Adaptable** | Prompting recipe, not a validator | Drive the **repair** stage from specific contract violations (targeted self-correction), preserving contract on repair |

**Net finding:** No single paper solves grain+fanout+quantifier+population+temporal. The
convergent, credible direction is: a **typed intermediate contract** (SemQL/NatSQL/QPL
lineage) + **decomposition-style operators** for quantifiers/comparisons (QDMR) +
**independent semantic validation** by AST analysis and property-based execution
(test-suite / Cosette-VeriEQL insight / execution-guided), replacing self-consistency as
the arbiter of correctness. PICARD is explicitly *not* adopted.

---

## 5. Proposed architecture (extension, not rewrite)

Add a **typed semantic contract** between checklist and validation, plus modular
AST-based validators consumed by the existing scorer/selector fatal machinery. No
pipeline is replaced; the direct/IR/family candidate generation stays.

```
question → retrieval → checklist ──┐
                                   ├─► SEMANTIC CONTRACT (typed)  ← schema inference (PK/unique/FK, semantic types)
generator prompt ◄─ contract hints ┘
candidates → SQL AST analysis (sqlglot) → CONTRACT VALIDATORS → fatal/penalty → selection
                                                              └─ property execution probes
all candidates fatal → no_semantically_valid_sql   (already wired in app.py)
```

New modules (small, focused — one concern each):
- `semantic/semantic_contract.py` — typed contract dataclass + builder (from checklist + schema inference). Backend-independent, **no raw SQL**.
- `semantic/contract_fields.py` — extend the checklist LLM prompt with typed fields (measures w/ aggregation+grain, comparison population, quantifiers, existence rules, temporal rules, semantic types), validated against schema like today.
- `sql_analysis/ast_tools.py` — **sqlglot** wrappers: parse (SQLite dialect), qualify aliases, extract aggregate args + their grain, join graph + one/many sides, correlated subqueries, window frames, GROUP BY keys, output projection grain. (Requirement #3: prefer AST over regex.)
- `schema/semantic_types.py` — infer per-column semantic type (state/city/date/amount/id-of-entity) from name + value profile (reuses `value_profiler`).
- `validators/grain_validator.py`, `fanout_validator.py`, `quantifier_validator.py`, `population_validator.py`, `temporal_validator.py`, `feasibility_validator.py` — each returns `(fatal[], penalty, reasons[])`.
- `semantic/contract_validation.py` — orchestrator; single entry called from `candidate_scorer` (fatal → existing selector disqualification + `no_semantically_valid_sql`).

Wiring points (minimal edits to existing files): `semantic_checklist.py` (typed fields), `candidate_scorer.py` (call orchestrator; append fatals), `llm_sql_direct.py` generator prompt (contract hints), repair generator (preserve contract), `app.py` (already returns controlled failure when all fatal).

**Dependency decision:** `sqlglot` (pure-Python, MIT, SQLite dialect, proper AST + scope/qualify). Nothing comparable is installed. Alternative = regex (rejected by requirement #3 for aliases/aggregates/correlation/windows). Needs `pip install sqlglot` + add to `requirements.txt`.

---

## 6. Staged implementation (smallest safe increments; approval-gated)

- **Stage 0 — AST + contract foundation:** add `sqlglot`; `ast_tools.py`; `semantic_contract.py` + typed checklist fields; `semantic_types.py`. No behavior change yet (contract built and logged only).
- **Stage 1 — Grain + feasibility (RC1, RC7):** grain_validator (aggregate-arg grain vs target/comparison grain) + feasibility_validator (type-compatible comparisons; missing concept → controlled failure). Fatal.
- **Stage 2 — Fanout (RC2):** cardinality-aware fanout_validator (one-side measure aggregated after many-join without pre-agg/DISTINCT/EXISTS). Fatal. Generator hint: pre-aggregate per grain / EXISTS / COUNT(DISTINCT key).
- **Stage 3 — Quantifiers + population (RC3, RC4):** quantifier_validator (both/every/none/same-event, non-vacuous ∀, COUNT(col) vs true-value) + population_validator (include-zero-match). Fatal/penalty.
- **Stage 4 — Temporal (RC5):** temporal_validator (cumulative running frame, previous-calendar-period, consecutive-run adjacency). Fatal/penalty.
- **Stage 5 — Generator + repair + selection integration (RC6):** contract hints in generator prompt; DIN-SQL-style targeted repair from violations; score subordinate to semantic validity; confirm `no_semantically_valid_sql` when all fatal.

Each stage ships with tests and a regression run before the next.

---

## 7. Acceptance-test mapping (generic small schemas, not DB46)

| Bench group | Validator | Generic test |
|---|---|---|
| A entity aggregation | grain | invoice-row value must not satisfy a patient-total request; AVG(invoice) ≠ AVG(patient total) |
| B fanout | fanout | header amount × many details not summed; parent×child not duplicated; pair comparison pre-aggregates each side |
| C quantifiers | quantifier | both-A-and-B requires both; one violating child fails ∀; non-empty subject prevents vacuous truth; boolean text vs non-null; same-event key |
| D population | population | group average includes zero-match entities when “all entities in the group” |
| E time | temporal | cumulative needs running frame; previous calendar month ≠ previous available row; two consecutive increases keep month adjacency |
| F feasibility | feasibility | state vs city rejected; missing concept → controlled failure |
| G regression | — | Lahman suite, 5 AdventureWorks manual Qs, explicit-table, relationship-expansion, containment |

After approved implementation: rerun the clinic 50-query benchmark and report execution
successes, fully-correct / partial / wrong / controlled-failure, per-root-cause deltas,
and before/after semantic accuracy. Target = shrink the 49→23 execution↔semantic gap.

---

## Sources
- QPL / Semantic Decomposition — https://aclanthology.org/2023.findings-emnlp.910/ , https://arxiv.org/abs/2310.13575
- Test-suite semantic evaluation — https://aclanthology.org/2020.emnlp-main.29/ , https://arxiv.org/abs/2010.02840
- Cosette — https://dl.acm.org/doi/10.1145/3035918.3058728 ; VeriEQL — https://arxiv.org/pdf/2403.03193
- DIN-SQL — https://proceedings.neurips.cc/paper_files/paper/2023/hash/72223cc66f63ca1aa59edaec1b3670e6-Abstract-Conference.html
- (Prior knowledge) IRNet/SemQL (ACL’19), NatSQL (2021), PICARD (EMNLP’21), RAT-SQL (ACL’20), Break/QDMR (TACL’20), Execution-guided decoding (2018)
