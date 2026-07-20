"""
final_evaluation/generation/genlib.py

Template DSL + case instantiation for the final SQL benchmark.

One `T(...)` declares a TEMPLATE FAMILY:
  * `variants` — a list of STRUCTURAL parameter dicts. Each variant is one
    semantic query template (different tables/columns/measures/operators =
    different meaning), identified as `<base_id>_v<n>`.
  * `q`        — 1-4 natural-language paraphrase format strings.
  * `vals`     — optional VALUE parameter dicts (literals only), cycled so
    the 4 cases of a variant differ in wording and/or literals.
Every variant emits exactly CASES_PER_TEMPLATE cases (paraphrase k%len(q),
value (k//len(q))%len(vals)), which enforces the protocol cap of at most 4
paraphrases per reference-SQL structure by construction.

`build_cases` instantiates everything, EXECUTES every reference SQL
read-only on its frozen database, stores normalized hashes, and rejects any
failing reference. No randomness anywhere — rebuilding yields byte-identical
manifests.
"""

from benchmarks.final_evaluation.common import db as bdb
from benchmarks.final_evaluation.common import scoring

CASES_PER_TEMPLATE = 4


class T:
    def __init__(self, base_id, category, database_id, difficulty, mode,
                 tags, sql, q, variants=None, vals=None, notes=""):
        assert isinstance(q, (list, tuple)) and 1 <= len(q) <= 4
        self.base_id = base_id
        self.category = category
        self.database_id = database_id
        self.difficulty = difficulty
        self.mode = mode
        self.tags = list(tags)
        self.sql = sql
        self.q = list(q)
        self.variants = list(variants or [{}])
        self.vals = list(vals or [{}])
        self.notes = notes
        if len(self.q) * len(self.vals) < CASES_PER_TEMPLATE:
            raise ValueError(f"{base_id}: q x vals must cover "
                             f"{CASES_PER_TEMPLATE} distinct cases")

    def instantiate(self):
        """Yield raw case dicts (without reference execution fields)."""
        for vi, variant in enumerate(self.variants, start=1):
            tid = f"{self.base_id}_v{vi}"
            for k in range(CASES_PER_TEMPLATE):
                params = dict(variant)
                params.update(self.vals[(k // len(self.q)) % len(self.vals)])
                question = self.q[k % len(self.q)].format(**params)
                sql = self.sql.format(**params)
                yield {
                    "category": self.category,
                    "difficulty": self.difficulty,
                    "database_id": self.database_id,
                    "database_name": bdb.db_name(self.database_id),
                    "question": question,
                    "reference_sql": " ".join(sql.split()),
                    "reference_params": [],
                    "comparison_mode": self.mode,
                    "numeric_tolerance": scoring.DEFAULT_TOLERANCE,
                    "semantic_template_id": tid,
                    "paraphrase_id": (k % len(self.q)) + 1,
                    "tags": list(self.tags) + list(params.get("_tags", [])),
                    "notes": self.notes,
                }


def template_counts(templates):
    """{(category, database_id, difficulty): number_of_variants}"""
    out = {}
    for t in templates:
        key = (t.category, t.database_id, t.difficulty)
        out[key] = out.get(key, 0) + len(t.variants)
    return out


def build_cases(templates, execute=True):
    """Instantiate all templates -> validated, reference-executed cases.
    Returns (cases, failures). Case IDs are assigned per category in
    deterministic instantiation order: <category>_0001..."""
    per_cat = {}
    cases, failures = [], []
    for t in templates:
        for raw in t.instantiate():
            cat = raw["category"]
            per_cat[cat] = per_cat.get(cat, 0) + 1
            raw["case_id"] = f"{cat}_{per_cat[cat]:04d}"
            if execute:
                ref = bdb.execute_readonly(raw["database_id"],
                                           raw["reference_sql"])
                if not ref["ok"]:
                    failures.append({"case_id": raw["case_id"],
                                     "template": raw["semantic_template_id"],
                                     "sql": raw["reference_sql"],
                                     "error": ref["error"]})
                    continue
                raw["expected_columns"] = ref["columns"]
                raw["expected_row_count"] = ref["row_count"]
                raw["expected_result_hash"] = scoring.result_hash(
                    ref["rows"], raw["comparison_mode"])
                raw["reference_execution_ms"] = ref["elapsed_ms"]
                raw["_reference_rows"] = ref["rows"]     # split out later
            cases.append(raw)
    return cases, failures
