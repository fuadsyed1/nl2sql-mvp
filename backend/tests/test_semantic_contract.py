"""Stage 0 tests — semantic/semantic_contract.py + checklist typed fields.

Covers: contract building from complete / partial typed fields, old-format
checklist compatibility, and no-behavior-change guarantees when the contract
is incomplete. Generic toy schema only.
"""

from semantic.semantic_contract import (
    SemanticContract, build_grain_contract, build_semantic_contract,
    contract_to_dict,
)
from semantic.semantic_checklist import (
    _clean_checklist, checklist_alignment, grain_alignment,
)

IDX = {
    "tables": {
        "patients": [{"name": "patient_id"}, {"name": "name"},
                     {"name": "insurance_provider"}],
        "invoices": [{"name": "invoice_id"}, {"name": "patient_id"},
                     {"name": "amount"}, {"name": "balance"}],
    },
    "relationships": [],
}

_TYPED = {
    "measure_column": "invoices.amount",
    "measure_aggregation": "sum",
    "measure_entity_key": "patients.patient_id",
    "comparison_right_kind": "aggregate_of_entity_totals",
    "grain_confidence": "high",
}


# 7. contract builder handles complete typed fields ---------------------------
def test_contract_from_complete_typed_fields():
    c = build_grain_contract(dict(_TYPED), IDX)
    assert isinstance(c, SemanticContract) and len(c.requirements) == 1
    r = c.requirements[0]
    assert r.measure_table == "invoices" and r.measure_column == "amount"
    assert r.measure_aggregation == "sum"
    assert r.entity_table == "patients" and r.entity_key_column == "patient_id"
    assert r.comparison_right_kind == "aggregate_of_entity_totals"
    assert r.confidence == "high"
    assert r.is_actionable is True and c.is_actionable is True
    d = contract_to_dict(c)
    assert d["actionable"] is True
    assert d["requirements"][0]["measure_table"] == "invoices"


# 8. contract builder handles missing optional fields -------------------------
def test_contract_with_missing_optional_fields():
    # no right-kind: still buildable, still actionable
    data = dict(_TYPED)
    data.pop("comparison_right_kind")
    c = build_grain_contract(data, IDX)
    assert c is not None and c.requirements[0].comparison_right_kind is None
    assert c.is_actionable is True

    # missing entity key: complete=False -> low confidence, not actionable
    data = dict(_TYPED)
    data.pop("measure_entity_key")
    c = build_grain_contract(data, IDX)
    assert c is not None and c.requirements[0].confidence == "low"
    assert c.is_actionable is False

    # low model confidence caps final confidence below high
    data = dict(_TYPED, grain_confidence="low")
    c = build_grain_contract(data, IDX)
    assert c.requirements[0].confidence != "high"
    assert c.is_actionable is False

    # malformed values are dropped, never raise
    data = dict(_TYPED, measure_aggregation="sums!", grain_confidence=42,
                measure_entity_key=["nope"])
    c = build_grain_contract(data, IDX)
    assert c is not None and c.is_actionable is False

    # unknown measure column dropped
    data = dict(_TYPED, measure_column="invoices.no_such")
    c = build_grain_contract(data, IDX)
    assert c is not None and c.requirements[0].measure_column is None
    assert c.is_actionable is False


# 9. old checklist format remains valid ---------------------------------------
def test_old_checklist_format_still_valid():
    legacy = {
        "target_entity": "patients",
        "output_columns": ["patients.name"],
        "must_use_tables": ["patients", "invoices"],
        "must_use_columns": ["invoices.amount"],
        "measure_column": "invoices.amount",
        "group_by_entity": "patients.patient_id",
        "comparison_logic": "total above average",
        "required_sql_shape": "comparison_subquery",
        "literals": [],
        "row_grain": "one row per patient",
        "universe": None,
        "required_group_keys": ["patients.patient_id"],
        "forbidden_hardcoded_universe": False,
    }
    cleaned = _clean_checklist(dict(legacy), IDX)
    for key, val in legacy.items():
        assert cleaned[key] == val, key
    # typed fields default to None/[] and no contract is built
    for key in ("measure_aggregation", "measure_entity_key",
                "comparison_right_kind", "grain_confidence"):
        assert cleaned[key] is None
    assert cleaned["grain_requirements"] == []
    assert build_grain_contract(cleaned, IDX) is None
    # non-dict / None input handled as before
    assert build_grain_contract(None, IDX) is None
    assert _clean_checklist("nonsense", IDX) is None


def test_clean_checklist_validates_typed_fields():
    raw = dict(_TYPED, target_entity="patients",
               must_use_tables=["patients", "invoices"])
    cleaned = _clean_checklist(raw, IDX)
    assert cleaned["measure_aggregation"] == "sum"
    assert cleaned["measure_entity_key"] == "patients.patient_id"
    assert cleaned["comparison_right_kind"] == "aggregate_of_entity_totals"
    assert cleaned["grain_confidence"] == "high"
    # invalid enum values are dropped to None
    bad = _clean_checklist(dict(raw, measure_aggregation="median",
                                comparison_right_kind="whatever",
                                grain_confidence="sure",
                                measure_entity_key="ghost.col"), IDX)
    assert bad["measure_aggregation"] is None
    assert bad["comparison_right_kind"] is None
    assert bad["grain_confidence"] is None
    assert bad["measure_entity_key"] is None


# 10. no behavior change when contract is incomplete ---------------------------
def test_no_scoring_behavior_change_from_typed_fields():
    question = "patients whose total invoiced amount is above average"
    sql = ("SELECT p.name FROM patients p JOIN invoices i "
           "ON i.patient_id = p.patient_id WHERE i.amount > 100")
    legacy = _clean_checklist({
        "target_entity": "patients",
        "must_use_tables": ["patients", "invoices"],
        "must_use_columns": ["invoices.amount"],
        "measure_column": "invoices.amount",
        "required_sql_shape": "comparison_subquery",
    }, IDX)
    typed = dict(legacy, **{k: _TYPED[k] for k in (
        "measure_aggregation", "measure_entity_key",
        "comparison_right_kind", "grain_confidence")})
    # the existing alignment scorers must produce IDENTICAL output whether
    # the typed fields are present or not (Stage 0: no behavior change)
    assert checklist_alignment(question, legacy, sql, IDX) \
        == checklist_alignment(question, typed, sql, IDX)
    assert grain_alignment(legacy, sql, IDX) == grain_alignment(typed, sql, IDX)
