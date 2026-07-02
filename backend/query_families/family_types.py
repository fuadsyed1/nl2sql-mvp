"""
query_families/family_types.py

The catalog of reusable relational query families. Each family names a recurring
relational-algebra pattern; the router maps a natural-language question to one
family + slots, and a deterministic builder turns that into IR (the same
extraction dict the LLM extractor would produce) for the existing SQL generator.

This is a generic relational pattern layer — it is NOT tied to any specific
database. Nothing here hardcodes table or column names.
"""

# Family name constants (stable identifiers).
NORMAL_JOIN_FILTER_GROUP = "normal_join_filter_group"
ANTI_EXISTS = "anti_exists"
OUTER_JOIN_NULL = "outer_join_null"
TOP_PER_GROUP = "top_per_group"
LATEST_EARLIEST_PER_ENTITY = "latest_earliest_per_entity"
UNIVERSAL_EVERY_ALL = "universal_every_all"
SET_DIVISION_COUNT_DISTINCT = "set_division_count_distinct"
COUNT_DISTINCT_COMPARISON = "count_distinct_comparison"
DERIVED_AGGREGATE_CTE = "derived_aggregate_cte"
SELF_JOIN_PAIR = "self_join_pair"
MIN_MAX_SAME_ENTITY_PER_GROUP = "min_max_same_entity_per_group"
MISMATCH_COMPARISON = "mismatch_comparison"

# Ordered list of all families.
FAMILIES = [
    NORMAL_JOIN_FILTER_GROUP,
    ANTI_EXISTS,
    OUTER_JOIN_NULL,
    TOP_PER_GROUP,
    LATEST_EARLIEST_PER_ENTITY,
    UNIVERSAL_EVERY_ALL,
    SET_DIVISION_COUNT_DISTINCT,
    COUNT_DISTINCT_COMPARISON,
    DERIVED_AGGREGATE_CTE,
    SELF_JOIN_PAIR,
    MIN_MAX_SAME_ENTITY_PER_GROUP,
    MISMATCH_COMPARISON,
]

# One-line purpose per family (for docs / router `reason` text).
FAMILY_PURPOSE = {
    NORMAL_JOIN_FILTER_GROUP:
        "Basic SELECT / JOIN / WHERE / GROUP BY / HAVING / ORDER BY / LIMIT.",
    ANTI_EXISTS:
        "Absence checks: never / no matching / not purchased / without matching.",
    OUTER_JOIN_NULL:
        "Include unmatched rows: outer join + IS NULL / null-or-mismatch groups.",
    TOP_PER_GROUP:
        "Extrema / N-th within a group over a raw column (highest/lowest/second per group).",
    LATEST_EARLIEST_PER_ENTITY:
        "Latest/earliest record per entity (dates), optionally via a derived relation.",
    UNIVERSAL_EVERY_ALL:
        "For-all / every / only, via nested NOT EXISTS or set division.",
    SET_DIVISION_COUNT_DISTINCT:
        "Has/contains ALL members of a set, via COUNT(DISTINCT) division.",
    COUNT_DISTINCT_COMPARISON:
        "More/fewer distinct X than Y; at least N distinct X.",
    DERIVED_AGGREGATE_CTE:
        "Per-entity aggregate totals then compared/ranked (CTE + top_per_group / comparison).",
    SELF_JOIN_PAIR:
        "Pairs / two rows of the same table (same or different owner/address/brand).",
    MIN_MAX_SAME_ENTITY_PER_GROUP:
        "Same entity has records at both the MIN and MAX of a value within a group.",
    MISMATCH_COMPARISON:
        "Column-to-column mismatch (do-not-own, different address, incompatible species).",
}

# Families that currently have a full deterministic builder. (normal_join_filter_group
# is intentionally conservative — its builder returns None so the LLM handles basics.)
IMPLEMENTED_FAMILIES = frozenset({
    MIN_MAX_SAME_ENTITY_PER_GROUP,
    DERIVED_AGGREGATE_CTE,
    COUNT_DISTINCT_COMPARISON,
    SELF_JOIN_PAIR,
    OUTER_JOIN_NULL,
    ANTI_EXISTS,
    TOP_PER_GROUP,
    LATEST_EARLIEST_PER_ENTITY,
    MISMATCH_COMPARISON,
    UNIVERSAL_EVERY_ALL,
    SET_DIVISION_COUNT_DISTINCT,
})


def family_result(family, confidence, slots=None, reason=""):
    """Uniform router result."""
    return {
        "family": family,
        "confidence": round(float(confidence), 3),
        "slots": slots or {},
        "reason": reason,
    }
