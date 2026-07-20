"""
semantic/semantic_contract.py

Typed GRAIN contract (semantic-contract Stage 0/1, extended in Stage 1B).

A small, backend-independent, machine-checkable view of the checklist's
optional grain fields. Stage 1B: one contract carries a LIST of independent
GrainRequirement entries (a question can compare several measures — every
high-confidence requirement must hold), and each requirement adds:

  measure_scope    which rows of the entity may feed the aggregate
                   (all_entity_rows = lifetime/overall; a qualifying-event
                   condition must not narrow it)
  population_key   the column the comparison group is formed within
                   ("same insurance provider" -> that column) — the minimum
                   population structure two-level grain validation needs

Contains NO raw SQL and NO validation policy. Building the contract can
never fail a request: any missing / malformed / unresolvable field lowers
that requirement's confidence, and the validator treats anything below HIGH
confidence as advisory-only.

Checklist input (all optional):
  grain_requirements: [{measure_column, aggregation, entity_key,
                        measure_scope, comparison_right_kind,
                        population_key, confidence}, ...]
Backward compatibility: when the list is absent, the legacy single typed
fields (measure_aggregation, measure_entity_key, comparison_right_kind,
grain_confidence + the existing measure_column) build ONE requirement.
A checklist with no typed fields at all yields None (old behavior).
"""

from dataclasses import dataclass, field

from query_families import slot_extractor as se

__all__ = [
    "AGGREGATIONS", "RIGHT_KINDS", "CONFIDENCES", "MEASURE_SCOPES",
    "DIRECTIONS", "QUALIFIER_TIMINGS",
    "GrainRequirement", "TemporalRequirement", "SemanticContract",
    "build_semantic_contract", "build_grain_contract", "contract_to_dict",
]

AGGREGATIONS = ("sum", "count", "avg", "min", "max", "none")
RIGHT_KINDS = ("aggregate_of_entity_totals", "aggregate_of_rows", "constant")
CONFIDENCES = ("high", "medium", "low")
MEASURE_SCOPES = ("all_entity_rows", "filtered_entity_rows", "current_event",
                  "latest_event", "qualifying_event_only")

# aggregations that mean "the measure must be rolled up per entity"
_ENTITY_AGGS = ("sum", "count", "avg", "min", "max")

DIRECTIONS = ("latest", "earliest")
QUALIFIER_TIMINGS = ("after_extremum", "before_extremum")


@dataclass(frozen=True)
class TemporalRequirement:
    """Latest/earliest-event qualification (final temporal patch).

    after_extremum: "whose most recent X was Y" — select the extremum event
    across ALL of the entity's events FIRST, then test the qualifier on that
    selected event. The qualifier must NOT restrict the extremum's input.

    before_extremum: "most recent Y X" — filtering to qualifying events
    before taking the extremum is the intended meaning (never validated)."""
    event_table: str | None = None
    entity_table: str | None = None
    entity_key_column: str | None = None
    order_table: str | None = None
    order_column: str | None = None
    direction: str | None = None            # latest | earliest
    qualifier_table: str | None = None
    qualifier_column: str | None = None
    qualifier_values: tuple = field(default_factory=tuple)
    qualifier_timing: str | None = None     # after_extremum | before_extremum
    confidence: str = "low"
    model_confidence: str | None = None
    evidence: tuple = field(default_factory=tuple)

    @property
    def is_actionable(self) -> bool:
        """Only high-confidence after_extremum requirements with a resolved
        event/order/qualifier are ever validated (anything else: skip)."""
        return (self.confidence == "high"
                and self.qualifier_timing == "after_extremum"
                and bool(self.event_table and self.order_column
                         and self.qualifier_column))


@dataclass(frozen=True)
class GrainRequirement:
    """One independent grain requirement. Lowercase schema names throughout."""
    measure_table: str | None = None
    measure_column: str | None = None
    measure_aggregation: str | None = None       # required per-entity agg
    entity_table: str | None = None              # entity the measure belongs to
    entity_key_column: str | None = None         # its key column
    comparison_right_kind: str | None = None
    population_table: str | None = None          # comparison population key
    population_column: str | None = None
    measure_scope: str | None = None             # see MEASURE_SCOPES
    # final stabilization (Parts C/D) — all optional; None = not required:
    distinct: bool | None = None                 # COUNT(DISTINCT ...) required
    comparison_operator: str | None = None       # > >= < <= = !=
    comparison_constant: float | None = None     # required comparison constant
    measure_components: tuple = field(default_factory=tuple)
    # ^ derived ADDITIVE measure ((table, column), ...): e.g. outstanding
    #   balance = total_amount - insurance_paid. SUM(x - y) and
    #   SUM(x) - SUM(y) are grain-equivalent over these components.
    measure_operation: str | None = None         # "subtract" | "add" | None
    confidence: str = "low"                      # derived — high|medium|low
    model_confidence: str | None = None          # what the LLM claimed
    evidence: tuple = field(default_factory=tuple)

    @property
    def requires_entity_aggregation(self) -> bool:
        return self.measure_aggregation in _ENTITY_AGGS

    @property
    def is_actionable(self) -> bool:
        """True only when every field the grain validator needs is resolved
        AND confidence is high. Anything else => advisory/skip, never fatal."""
        return (self.confidence == "high"
                and self.requires_entity_aggregation
                and bool(self.measure_table and self.measure_column)
                and bool(self.entity_table and self.entity_key_column))


@dataclass(frozen=True)
class SemanticContract:
    """The full typed contract: independent grain requirements plus optional
    temporal (latest-event qualification) requirements. Every actionable
    requirement must be satisfied by a candidate."""
    requirements: tuple = field(default_factory=tuple)
    temporal: tuple = field(default_factory=tuple)
    evidence: tuple = field(default_factory=tuple)

    @property
    def actionable_requirements(self):
        return [r for r in self.requirements if r.is_actionable]

    @property
    def actionable_temporal(self):
        return [t for t in self.temporal if t.is_actionable]

    @property
    def is_actionable(self) -> bool:
        return bool(self.actionable_requirements or self.actionable_temporal)


def _req_to_dict(r: GrainRequirement) -> dict:
    return {
        "measure_table": r.measure_table,
        "measure_column": r.measure_column,
        "measure_aggregation": r.measure_aggregation,
        "entity_table": r.entity_table,
        "entity_key_column": r.entity_key_column,
        "comparison_right_kind": r.comparison_right_kind,
        "population_table": r.population_table,
        "population_column": r.population_column,
        "measure_scope": r.measure_scope,
        "distinct": r.distinct,
        "comparison_operator": r.comparison_operator,
        "comparison_constant": r.comparison_constant,
        "measure_components": [list(c) for c in r.measure_components],
        "measure_operation": r.measure_operation,
        "confidence": r.confidence,
        "model_confidence": r.model_confidence,
        "actionable": r.is_actionable,
        "evidence": list(r.evidence),
    }


def _temporal_to_dict(t: TemporalRequirement) -> dict:
    return {
        "event_table": t.event_table,
        "entity_table": t.entity_table,
        "entity_key_column": t.entity_key_column,
        "order_table": t.order_table,
        "order_column": t.order_column,
        "direction": t.direction,
        "qualifier_table": t.qualifier_table,
        "qualifier_column": t.qualifier_column,
        "qualifier_values": list(t.qualifier_values),
        "qualifier_timing": t.qualifier_timing,
        "confidence": t.confidence,
        "model_confidence": t.model_confidence,
        "actionable": t.is_actionable,
        "evidence": list(t.evidence),
    }


def contract_to_dict(contract: SemanticContract | None) -> dict | None:
    if contract is None:
        return None
    return {
        "requirements": [_req_to_dict(r) for r in contract.requirements],
        "temporal": [_temporal_to_dict(t) for t in contract.temporal],
        "actionable": contract.is_actionable,
        "evidence": list(contract.evidence),
    }


# ---------------------------------------------------------------------------
# builder
# ---------------------------------------------------------------------------
def _split_spec(spec):
    """'table.column' -> (table, column); bare 'column' -> (None, column)."""
    if not isinstance(spec, str) or not spec.strip():
        return None, None
    s = spec.strip().lower().replace('"', "")
    if "." in s:
        t, c = s.split(".", 1)
        return (t or None), (c or None)
    return None, s


def _column_exists(idx, table, column):
    cols = (idx.get("tables") or {}).get(table) or []
    return any(c.get("name") == column for c in cols)


def _owning_tables(idx, column):
    return [t for t, cols in (idx.get("tables") or {}).items()
            if any(c.get("name") == column for c in cols)]


def _resolve_col(idx, spec, label, evidence):
    """Resolve a 'table.column' / 'column' spec against the schema.
    Returns (table, column, certain)."""
    t, c = _split_spec(spec)
    certain = True
    if c and not t:
        owners = _owning_tables(idx, c)
        if len(owners) == 1:
            t = owners[0]
            evidence.append(f"{label} table resolved uniquely: {t}")
        else:
            evidence.append(
                f"{label} column '{c}' owned by {len(owners)} tables — unresolved")
            certain = False
    if t and c and not _column_exists(idx, t, c):
        evidence.append(f"{label} {t}.{c} not in schema — dropped")
        t = c = None
        certain = False
    return t, c, certain


def _build_requirement(data: dict, idx) -> GrainRequirement:
    """Build one requirement from a (possibly raw) dict. Never raises."""
    evidence = []
    certain = True

    agg = data.get("aggregation", data.get("measure_aggregation"))
    agg = agg.strip().lower() if isinstance(agg, str) else None
    if agg not in AGGREGATIONS:
        if agg is not None:
            evidence.append(f"unknown aggregation '{agg}' ignored")
        agg = None
        certain = False

    kind = data.get("comparison_right_kind")
    kind = kind.strip().lower() if isinstance(kind, str) else None
    if kind is not None and kind not in RIGHT_KINDS:
        evidence.append(f"unknown comparison_right_kind '{kind}' ignored")
        kind = None                      # optional — does not flip `certain`

    scope = data.get("measure_scope")
    scope = scope.strip().lower() if isinstance(scope, str) else None
    if scope is not None and scope not in MEASURE_SCOPES:
        evidence.append(f"unknown measure_scope '{scope}' ignored")
        scope = None                     # optional — scope checks just skip

    model_conf = data.get("confidence", data.get("grain_confidence"))
    model_conf = (model_conf.strip().lower()
                  if isinstance(model_conf, str) else None)
    if model_conf not in CONFIDENCES:
        model_conf = None
        certain = False

    # optional distinct / comparison fields (Part C) — invalid values drop
    # to None and never affect confidence (validation just skips them)
    distinct = data.get("distinct")
    distinct = bool(distinct) if isinstance(distinct, bool) else None

    op = data.get("comparison_operator")
    op = str(op).strip() if op is not None else None
    if op == "<>":
        op = "!="
    if op not in (">", ">=", "<", "<=", "=", "!="):
        op = None
    const = data.get("comparison_constant")
    try:
        const = float(const) if const is not None else None
    except (TypeError, ValueError):
        const = None

    # optional derived additive measure (Part D):
    #   measure_expression: {"operation": "subtract"|"add",
    #                        "components": ["t.colA", "t.colB", ...]}
    m_components, m_operation = [], None
    expr = data.get("measure_expression")
    if isinstance(expr, dict):
        oper = str(expr.get("operation") or "").strip().lower()
        if oper in ("subtract", "add"):
            comps = []
            for spec in (expr.get("components") or [])[:4]:
                ct, cc, ok = _resolve_col(idx, spec, "measure component",
                                          evidence)
                if ct and cc:
                    comps.append((ct, cc))
            if len(comps) >= 2:
                m_components, m_operation = comps, oper
            elif comps or expr.get("components"):
                evidence.append("measure_expression incomplete — ignored")

    m_table, m_col, ok = _resolve_col(
        idx, data.get("measure_column"), "measure", evidence)
    certain = certain and (ok or bool(m_components))
    # derived-measure stability (Q04): when the model omits/loses the single
    # measure column but a resolved derived expression exists, its FIRST
    # component is the primary measure — the requirement stays actionable
    if (not m_table or not m_col) and m_components:
        m_table, m_col = m_components[0]
        evidence.append(
            f"measure resolved from derived expression: {m_table}.{m_col}")
    e_table, e_col, ok = _resolve_col(
        idx, data.get("entity_key", data.get("measure_entity_key")),
        "entity key", evidence)
    certain = certain and ok
    p_table, p_col, ok = _resolve_col(
        idx, data.get("population_key"), "population key", evidence)
    if not ok:
        p_table = p_col = None           # optional — pop check just skips

    complete = bool(agg and m_table and m_col
                    and (agg == "none" or (e_table and e_col)))

    if model_conf == "high" and certain and complete:
        confidence = "high"
    elif complete:
        confidence = "medium"
    else:
        confidence = "low"

    return GrainRequirement(
        measure_table=m_table, measure_column=m_col, measure_aggregation=agg,
        entity_table=e_table, entity_key_column=e_col,
        comparison_right_kind=kind,
        population_table=p_table, population_column=p_col,
        measure_scope=scope,
        distinct=distinct, comparison_operator=op, comparison_constant=const,
        measure_components=tuple(m_components), measure_operation=m_operation,
        confidence=confidence, model_confidence=model_conf,
        evidence=tuple(evidence),
    )


def _build_temporal(data: dict, idx) -> TemporalRequirement:
    """Build one temporal requirement from a (possibly raw) dict. Never
    raises; anything unresolved lowers confidence (validation then skips)."""
    evidence = []
    certain = True

    event = str(data.get("event_table") or "").strip().lower() or None
    if event and event not in (idx.get("tables") or {}):
        evidence.append(f"event table '{event}' not in schema — dropped")
        event, certain = None, False

    def _col(spec, label):
        nonlocal certain
        t, c, ok = _resolve_col(idx, spec, label, evidence)
        if c and not t and event:
            # bare column: default to the event table when it owns it
            if _column_exists(idx, event, c):
                t = event
        if not ok:
            certain = False
        return t, c

    e_table, e_col = _col(data.get("entity_key"), "temporal entity key")
    o_table, o_col = _col(data.get("order_column"), "order column")
    q_table, q_col = _col(data.get("qualifier_column"), "qualifier column")

    direction = str(data.get("direction") or "").strip().lower() or None
    if direction is not None and direction not in DIRECTIONS:
        evidence.append(f"unknown direction '{direction}' ignored")
        direction = None
    timing = str(data.get("qualifier_timing") or "").strip().lower() or None
    if timing is not None and timing not in QUALIFIER_TIMINGS:
        evidence.append(f"unknown qualifier_timing '{timing}' ignored")
        timing, certain = None, False
    values = tuple(str(x) for x in (data.get("qualifier_values") or [])[:4]
                   if isinstance(x, (str, int, float)) and str(x).strip())

    model_conf = data.get("confidence")
    model_conf = (model_conf.strip().lower()
                  if isinstance(model_conf, str) else None)
    if model_conf not in CONFIDENCES:
        model_conf, certain = None, False

    complete = bool(event and o_col and q_col and timing)
    if model_conf == "high" and certain and complete:
        confidence = "high"
    elif complete:
        confidence = "medium"
    else:
        confidence = "low"

    return TemporalRequirement(
        event_table=event, entity_table=e_table, entity_key_column=e_col,
        order_table=o_table or event, order_column=o_col,
        direction=direction,
        qualifier_table=q_table or event, qualifier_column=q_col,
        qualifier_values=values, qualifier_timing=timing,
        confidence=confidence, model_confidence=model_conf,
        evidence=tuple(evidence),
    )


def build_semantic_contract(checklist, graph_or_idx) -> SemanticContract | None:
    """Build the typed contract from a checklist. Returns None when no typed
    grain OR temporal information is present (old-format checklist) — callers
    then skip contract validation entirely. Never raises on malformed
    input."""
    if not isinstance(checklist, dict):
        return None
    try:
        idx = (graph_or_idx if isinstance(graph_or_idx, dict)
               and isinstance(graph_or_idx.get("tables"), dict)
               else se.index_schema(graph_or_idx))
    except Exception:
        return None

    t_reqs = [
        _build_temporal(entry, idx)
        for entry in (checklist.get("temporal_requirements") or [])[:2]
        if isinstance(entry, dict)
    ]

    reqs = []
    raw_list = checklist.get("grain_requirements")
    if isinstance(raw_list, list) and raw_list:
        for entry in raw_list[:4]:
            if isinstance(entry, dict):
                # each entry falls back to the checklist's measure_column
                # when it names none of its own
                if not entry.get("measure_column"):
                    entry = dict(entry,
                                 measure_column=checklist.get("measure_column"))
                reqs.append(_build_requirement(entry, idx))
    else:
        # legacy single typed fields -> one requirement (old behavior)
        legacy_present = any(
            checklist.get(k) is not None
            for k in ("measure_aggregation", "measure_entity_key",
                      "comparison_right_kind", "grain_confidence"))
        if legacy_present:
            reqs.append(_build_requirement({
                "measure_column": checklist.get("measure_column"),
                "aggregation": checklist.get("measure_aggregation"),
                "entity_key": checklist.get("measure_entity_key"),
                "comparison_right_kind": checklist.get("comparison_right_kind"),
                "confidence": checklist.get("grain_confidence"),
            }, idx))

    if not reqs and not t_reqs:
        return None
    return SemanticContract(requirements=tuple(reqs), temporal=tuple(t_reqs))


# Backward-compatible alias (app.py / older callers import this name).
build_grain_contract = build_semantic_contract
