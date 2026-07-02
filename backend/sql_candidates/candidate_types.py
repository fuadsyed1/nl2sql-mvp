"""
sql_candidates/candidate_types.py

The SqlCandidate data shape for multi-candidate SQL selection.

A candidate is one complete attempt at answering a question: an extraction
(from the query-family builder or the LLM extractor), plus everything the
pipeline derived from it (IR, plan, SQL, execution result), plus the
validation score assigned by candidate_scorer. This module is pure data —
no scoring, no execution, no selection logic.

Sources:
  * "query_family"    deterministic family-builder output
  * "llm_primary"     normal LLM extractor output (temperature 0)
  * "llm_variant"     LLM extractor with a variant prompt / higher temperature
  * "llm_sql_direct"  direct question->SQL LLM call (no IR pipeline)
  * "repair"          reserved for a future execution-guided repair loop
"""

from dataclasses import dataclass, field

SOURCES = ("query_family", "llm_primary", "llm_variant", "llm_sql_direct",
           "llm_sql_repair", "repair")

__all__ = ["SOURCES", "SqlCandidate", "to_dict", "to_public_dict"]


@dataclass
class SqlCandidate:
    source: str                                # one of SOURCES
    label: str                                 # unique per request, e.g. "llm_variant_2"
    sql: str | None = None
    params: list = field(default_factory=list)
    extraction: dict | None = None
    ir: dict | None = None                     # serialized IR (ir_to_dict)
    ir_validation: dict | None = None          # validate_ir output
    plan: dict | None = None                   # plan_to_dict output
    generated_sql: dict | None = None          # sql_to_dict output
    relational_algebra: object = None
    execution: dict | None = None              # execution_to_dict output
    validation: dict = field(default_factory=dict)   # scorer check results
    score: float = 0.0
    reasons: list = field(default_factory=list)      # human-readable scoring reasons
    family_info: dict | None = None            # {family, confidence, guard_valid, guard_reasons}
    diagnostics: dict = field(default_factory=dict)  # large-mode/partition/pipeline notes

    @property
    def executed_ok(self) -> bool:
        return bool(self.execution and self.execution.get("executed"))

    @property
    def row_count(self):
        if self.execution and self.execution.get("executed"):
            return self.execution.get("row_count")
        return None


def to_dict(cand: SqlCandidate) -> dict:
    """Full serialization (debug / benchmark JSON)."""
    return {
        "source": cand.source,
        "label": cand.label,
        "sql": cand.sql,
        "params": cand.params,
        "extraction": cand.extraction,
        "ir": cand.ir,
        "ir_validation": cand.ir_validation,
        "plan": cand.plan,
        "generated_sql": cand.generated_sql,
        "execution": cand.execution,
        "validation": cand.validation,
        "score": cand.score,
        "reasons": cand.reasons,
        "family_info": cand.family_info,
        "diagnostics": cand.diagnostics,
    }


def to_public_dict(cand: SqlCandidate) -> dict:
    """Compact serialization for API response metadata (no IR/plan dumps)."""
    return {
        "source": cand.source,
        "label": cand.label,
        "sql": cand.sql,
        "score": cand.score,
        "executed": cand.executed_ok,
        "row_count": cand.row_count,
        "reasons": cand.reasons,
    }
