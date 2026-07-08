"""sql_candidates — multi-candidate SQL generation, scoring, and selection.

Instead of trusting a single path (query family OR LLM fallback), the
endpoint generates several SQL candidates, scores each against the question
and schema, executes them, and selects the best via execution
self-consistency + validation score. Wrong-but-executable SQL scores low.
"""

from sql_candidates.candidate_types import SqlCandidate, to_dict, to_public_dict
from sql_candidates.candidate_builder import build_candidate, build_direct_sql_candidate
from sql_candidates.candidate_scorer import score_candidate, LOW_SCORE_THRESHOLD
from sql_candidates.candidate_selector import select_best
from sql_candidates.result_equivalence import result_signature, group_candidates
from sql_candidates.execution_probes import probe_candidate, annotate_with_probes

__all__ = [
    "SqlCandidate", "to_dict", "to_public_dict",
    "build_candidate", "build_direct_sql_candidate", "score_candidate",
    "select_best", "result_signature", "group_candidates",
    "LOW_SCORE_THRESHOLD", "probe_candidate", "annotate_with_probes",
]
