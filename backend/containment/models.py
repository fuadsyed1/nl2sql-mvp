"""
containment/models.py

Pydantic request/response models for POST /database/{id}/check_containment.

These shapes are intentionally flat and UI-friendly: the frontend (added in a
later step) can render both generated SQLs, their confidence signals, and the
containment verdict without reaching into the full execute_sql payload.
"""

from pydantic import BaseModel, Field


class ContainmentRequest(BaseModel):
    """Two natural-language questions to compare for containment."""
    query1: str
    query2: str


class ContainmentQueryResult(BaseModel):
    """Per-question outcome of the shared NL->SQL pipeline, projected down to
    the fields the containment layer needs. Missing/failed pipeline fields
    degrade to safe defaults so the endpoint never raises."""
    question: str
    success: bool = False
    sql: str | None = None
    # Bound parameters for `sql` (may contain ? placeholders). Preserved so the
    # EXCEPT checker can bind them positionally; never string-interpolated.
    params: list = Field(default_factory=list)
    selected_candidate_source: str | None = None
    selected_candidate_score: float | None = None
    low_confidence: bool = False
    # True when the selected candidate's validation carries fatal items.
    has_fatal_validation: bool = False
    warnings: list[str] = Field(default_factory=list)
    execution_columns: list[str] = Field(default_factory=list)
    row_count: int = 0


class ContainmentResponse(BaseModel):
    """Top-level response.

    containment_result is one of:
      * "contained_on_current_database"  — SQL1 EXCEPT SQL2 returned no rows.
      * "equivalent_on_current_database" — both EXCEPT directions returned no rows.
      * "not_contained"                  — SQL1 EXCEPT SQL2 returned rows
        (a real counterexample on the current database).
      * "unknown"                        — the safety gate blocked the check (a
        query failed/low-confidence/no SQL, fatal validation, mismatched or
        differently-counted columns, or an unsupported SQL shape), or the
        EXCEPT itself errored.

    A "contained"/"equivalent" verdict holds only for the data currently in the
    database — it is NOT a general or symbolic proof. Only "not_contained" is
    backed by a concrete counterexample.
    """
    success: bool
    database_id: int
    query1_result: ContainmentQueryResult
    query2_result: ContainmentQueryResult
    containment_result: str
    explanation: str
    warnings: list[str] = Field(default_factory=list)

    # -- Live-database EXCEPT evidence (populated only when the check runs) -----
    counterexample_columns: list[str] = Field(default_factory=list)
    # Rows in Query 1 but not in Query 2 (SQL1 EXCEPT SQL2), capped for display.
    counterexample_rows: list[list] = Field(default_factory=list)
    # Rows in Query 2 but not in Query 1 (SQL2 EXCEPT SQL1), for transparency.
    reverse_counterexample_rows: list[list] = Field(default_factory=list)
    checked_on_current_database: bool = False
    proof_type: str | None = None
    limitations: str | None = None


# ---------------------------------------------------------------------------
# Batch containment (N queries, pairwise both-direction comparison)
# ---------------------------------------------------------------------------


class ContainmentBatchRequest(BaseModel):
    """A list of natural-language questions (one per line in the UI). At least
    two non-empty questions are required."""
    queries: list[str]


class BatchQueryResult(ContainmentQueryResult):
    """One query in a batch: the projected NL->SQL result plus a 1-based id, an
    empty-result flag, and whether it passed the per-query safety gate."""
    query_id: int
    empty_result: bool = False
    safe: bool = True
    safety_reason: str | None = None


class PairwiseRelationship(BaseModel):
    """The both-direction containment relationship between two queries.

    relationship is one of:
      * "query_a_contained_in_query_b"
      * "query_b_contained_in_query_a"
      * "equivalent_on_current_database"
      * "incomparable_on_current_database"
      * "unknown"                          (unsafe / mismatched columns / errored)
    """
    query_a: int
    query_b: int
    relationship: str
    explanation: str
    # Qa EXCEPT Qb (rows in A missing from B) and Qb EXCEPT Qa, capped.
    a_minus_b_rows: list[list] = Field(default_factory=list)
    b_minus_a_rows: list[list] = Field(default_factory=list)
    # How the pair was compared: "output_columns" (full tuple), or
    # "canonical_key:<col>" when Step-1 projection normalization was used.
    # None when the pair could not be compared (unknown).
    compared_on: str | None = None


class QuerySummary(BaseModel):
    """Per-query rollup across all pairwise comparisons. No single query is
    declared the 'main' one — each query lists its relationships to the others."""
    query_id: int
    contained_in: list[int] = Field(default_factory=list)
    contains: list[int] = Field(default_factory=list)
    equivalent_to: list[int] = Field(default_factory=list)
    incomparable_with: list[int] = Field(default_factory=list)
    unknown_with: list[int] = Field(default_factory=list)
    status: str = "no_containment_relationship"
    empty_result: bool = False


class ContainmentBatchResponse(BaseModel):
    """Top-level batch response. Contained/equivalent verdicts hold only on the
    current database; not-contained/incomparable are backed by counterexample
    rows. Never a symbolic proof."""
    success: bool
    database_id: int
    query_results: list[BatchQueryResult] = Field(default_factory=list)
    pairwise_relationships: list[PairwiseRelationship] = Field(default_factory=list)
    query_summaries: list[QuerySummary] = Field(default_factory=list)
    checked_on_current_database: bool = False
    proof_type: str | None = None
    limitations: str | None = None
    warnings: list[str] = Field(default_factory=list)
