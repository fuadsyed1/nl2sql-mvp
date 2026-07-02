"""
query_families/query_family_router.py

Schema-aware router: natural-language question -> one relational query family +
slots + confidence. Deterministic keyword/structure signals (generic English
SQL-intent words, not database-specific) score each family; the best above a
threshold wins. `route_and_build` turns a confident, implemented family into an
extraction dict; otherwise it returns None so the caller falls back to the
existing LLM extractor.
"""

from query_families import family_types as ft
from query_families import slot_extractor as se
from query_families.builders import build_family

_THRESHOLD = 0.55


def _q(question):
    return " " + str(question or "").lower().strip() + " "


def _any(q, words):
    return any(w in q for w in words)


# Each scorer returns a (score, reason) for its family. Scores are calibrated so
# more specific patterns outrank more generic ones.
def _score_min_max(q, idx):
    has_min = _any(q, ("cheapest", "lowest", "minimum", "smallest", "least expensive", "least-expensive"))
    has_max = _any(q, ("most expensive", "highest", "maximum", "largest", "priciest", "greatest", "dearest"))
    if has_min and has_max and _any(q, ("same ", "both ")):
        s = 0.9 + (0.05 if _any(q, ("of that", "for each", "within", "per ", "of the same")) else 0.0)
        return s, "same entity has records at both the min and max within a group"
    return 0.0, ""


def _score_self_join_pair(q, idx):
    if _any(q, ("pairs of", "pair of", " pairs ", "each other")):
        return 0.9, "compares two rows of the same table (pairs)"
    if _any(q, ("same owner", "different owner", "same address", "different address",
               "same preferred brand", "two ")) and _any(q, ("same ", "different ")):
        return 0.6, "two rows of the same entity compared by an attribute"
    return 0.0, ""


def _score_set_division(q, idx):
    if _any(q, ("for all ", "for every ")) or (" all " in q and _any(q, ("have ", "has ", "contain", "represented"))):
        return 0.85, "has/contains ALL members of a set (count-distinct division)"
    return 0.0, ""


def _score_derived_aggregate(q, idx):
    agg = _any(q, ("total ", " sum ", "sum of", "average", " avg ", "mean "))
    per_group = _any(q, ("per ", "for each", "in each", "within their", "in their", "by city", "by "))
    compare = _any(q, ("above ", "below ", "greater than", "more than", "less than", "including ties", "highest total", "lowest total"))
    if agg and (per_group or compare):
        return 0.85, "per-entity aggregate total then ranked/compared (derived relation)"
    return 0.0, ""


def _score_count_distinct_comparison(q, idx):
    comparative = _any(q, ("more ", "fewer ", "less ", "greater")) and " than " in q
    distinct = _any(q, ("distinct", "different ", "number of different", "how many different"))
    atleast = ("at least" in q or "at most" in q) and _any(q, ("brand", "flavor", "type", "distinct", "different"))
    if comparative and _any(q, ("brand", "flavor", "type", "distinct", "different", "kind")):
        return 0.8, "more/fewer distinct X than Y"
    if distinct and comparative:
        return 0.8, "compare distinct counts"
    if atleast:
        return 0.65, "at least N distinct X"
    return 0.0, ""


def _score_outer_join_null(q, idx):
    if "outer join" in q or "left join" in q:
        return 0.9, "explicit outer join"
    if _any(q, ("without ", "even when", "even if", "still visible", "unmatched",
               "no matching record", "include unmatched", "with no matching")):
        return 0.75, "include unmatched rows via outer join + null test"
    return 0.0, ""


def _score_anti_exists(q, idx):
    if _any(q, ("never ", "not purchased", "not fed", "not bought", "no matching",
               "does not exist", "without matching", "has no ", "have no ", "not eaten")):
        return 0.8, "absence check (NOT EXISTS)"
    return 0.0, ""


def _score_universal(q, idx):
    if _any(q, ("for all",)):
        return 0.0, ""
    if _any(q, ("every ", "each ")) and _any(q, ("has ", "have ", "been ", "is ", "own")):
        return 0.82, "for-all via nested NOT EXISTS"
    if _any(q, ("every ", "each owner has", "all pets have", "only ")):
        return 0.6, "for-all / only via nested NOT EXISTS"
    return 0.0, ""


def _score_latest_earliest(q, idx):
    strong = _any(q, ("latest ", "most recent", "earliest ", "first "))
    if strong and _any(q, ("per ", "for each", "of each")):
        return 0.82, "latest/earliest per entity"
    if strong:
        return 0.72, "latest/earliest per entity (implicit)"
    return 0.0, ""


def _score_top_per_group(q, idx):
    if _any(q, ("second highest", "second lowest", "nth ")):
        return 0.82, "n-th within a group"
    if _any(q, ("highest", "lowest", "most expensive", "cheapest")) and _any(q, ("per ", "for each", "within", "of each")):
        return 0.82, "extremum of a raw column within a group"
    return 0.0, ""


def _score_mismatch(q, idx):
    if _any(q, ("do not own", "does not own", "different address", "incompatible",
               "does not match", "different brand", "do not live at the same",
               "not live at the same")):
        return 0.8, "column-to-column mismatch"
    if _any(q, ("not own", "mismatch")):
        return 0.6, "column-to-column mismatch"
    return 0.0, ""


_SCORERS = [
    (ft.MIN_MAX_SAME_ENTITY_PER_GROUP, _score_min_max),
    (ft.SELF_JOIN_PAIR, _score_self_join_pair),
    (ft.SET_DIVISION_COUNT_DISTINCT, _score_set_division),
    (ft.DERIVED_AGGREGATE_CTE, _score_derived_aggregate),
    (ft.COUNT_DISTINCT_COMPARISON, _score_count_distinct_comparison),
    (ft.OUTER_JOIN_NULL, _score_outer_join_null),
    (ft.ANTI_EXISTS, _score_anti_exists),
    (ft.UNIVERSAL_EVERY_ALL, _score_universal),
    (ft.LATEST_EARLIEST_PER_ENTITY, _score_latest_earliest),
    (ft.TOP_PER_GROUP, _score_top_per_group),
    (ft.MISMATCH_COMPARISON, _score_mismatch),
]


def route(question, graph):
    """Return the best {family, confidence, slots, reason}. Falls back to
    normal_join_filter_group when nothing scores above threshold."""
    idx = se.index_schema(graph)
    q = _q(question)
    best_family, best_score, best_reason = ft.NORMAL_JOIN_FILTER_GROUP, 0.0, \
        "no distinctive relational pattern detected"
    for family, scorer in _SCORERS:
        score, reason = scorer(q, idx)
        if score > best_score:
            best_family, best_score, best_reason = family, score, reason
    if best_score < _THRESHOLD:
        return ft.family_result(ft.NORMAL_JOIN_FILTER_GROUP, max(best_score, 0.3),
                                reason="no distinctive relational pattern; use base pipeline")
    return ft.family_result(best_family, best_score, reason=best_reason)


def route_and_build(question, graph):
    """Route, then build the extraction for a confident + implemented family.
    Returns (extraction_dict, decision) or (None, decision) to signal fallback
    to the existing LLM extractor."""
    decision = route(question, graph)
    family = decision["family"]
    if decision["confidence"] < _THRESHOLD or family not in ft.IMPLEMENTED_FAMILIES:
        return None, decision
    idx = se.index_schema(graph)
    extraction = build_family(family, question, idx)
    if extraction is None:
        return None, decision
    decision = dict(decision)
    decision["built"] = True
    return extraction, decision
