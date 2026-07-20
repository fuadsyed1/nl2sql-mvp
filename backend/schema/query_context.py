"""
schema/query_context.py

Mode-aware query-time schema selection, extracted verbatim from the
/database/{id}/execute_sql endpoint so it lives in one reusable place.

resolve_query_graph(database_id, question) returns (graph, tables_considered,
early):
  * small mode -> the full get_database_graph (unchanged),
  * large mode -> deterministic top-k table retrieval + the existing date guard,
    then a small sub-graph (so the pipeline never sees the full schema).

`early` is a ready-to-return response dict for an early exit (Database not found,
no_relevant_tables_found, requested_date_table_not_found) or None. Behavior is
identical to the previous inline logic — this is a refactor only. The
post-extraction guards (large-mode table fallback, redundant partition-date
filter removal, ambiguous_partitioned_table_query) stay in the endpoint because
they operate on the IR, not on schema selection.
"""

from db.database_service import (
    get_database_graph, get_database_path, get_database_tables,
    get_relationships,
)
from schema.lazy_loader import get_database_meta
from schema.subgraph_builder import build_subgraph
from schema.table_mention import explicit_table_mentions
from retrieval.table_retriever import retrieve_tables, requested_dates_satisfied
from retrieval.relationship_expansion import (
    physical_fk_edges, expand_tables_along_fks,
)

__all__ = ["resolve_query_graph"]

import re as _re
_WORD_SPLIT = _re.compile(r"[^a-z0-9]+")


def _name_tokens(s):
    return [t for t in _WORD_SPLIT.split(str(s or "").lower()) if t]


def _explicitly_named_tables(question, all_names):
    """Real table names the question EXPLICITLY references (separator-
    insensitive). A distinctive name (multi-token / digit / underscore / very
    long token) matches on a bare mention; a plain single-word name locks only
    with an explicit table cue ('customer table', 'from customer',
    'customer.id'), so an ordinary business noun cannot force a table. Delegates
    to the shared detector. Returns real-cased names."""
    return list(explicit_table_mentions(question, all_names))


def resolve_query_graph(database_id, question, meta=None):
    """Return (graph, tables_considered, early)."""
    if meta is None:
        meta = get_database_meta(database_id)
    if not meta:
        return None, None, {"success": False, "message": "Database not found"}

    tables_considered = None
    if meta["mode"] == "large":
        tables_considered = retrieve_tables(database_id, question, k=8)
        if not tables_considered:
            return None, [], {
                "success": False,
                "error": "no_relevant_tables_found",
                "message": "No relevant tables were found for this question.",
                "database_id": database_id,
                "question": question,
                "tables_considered": [],
            }

        # Date guard: if the question names a date but no retrieved table matches
        # that date partition, do not fall back to an unrelated table.
        req_date_tokens, dates_ok = requested_dates_satisfied(
            question, tables_considered
        )
        if not dates_ok:
            return None, tables_considered, {
                "success": False,
                "error": "requested_date_table_not_found",
                "message": "No table was found for the requested date.",
                "requested_date_tokens": req_date_tokens,
                "database_id": database_id,
                "question": question,
                "tables_considered": tables_considered,
            }

        # Relationship-aware closure: lexical retrieval returns only tables
        # whose NAMES match the question, so multi-hop join/measure/bridge
        # tables (SalesOrderHeader/Detail, EmployeePayHistory, PurchaseOrderHeader
        # ...) are missing and the join path cannot be built. Expand the seed set
        # along the database's REAL foreign keys to pull in bridge tables (on the
        # join path between seeds) and question-relevant neighbors, capped so the
        # graph stays focused. `tables_considered` (used by the date/table
        # fallback) is left as the original lexical seeds.
        seed_names = [t["table_name"] for t in tables_considered]
        try:
            # Table expansion derives adjacency from the FINALIZED STORED edges,
            # never a fresh physical-FK read. Table selection may vary per query
            # (retrieval); relationships do not.
            fk_edges = get_relationships(database_id)
            if fk_edges:
                all_names = [r["table_name"]
                             for r in get_database_tables(database_id)]
                expanded = expand_tables_along_fks(
                    seed_names, fk_edges, all_names, question)
                if expanded:
                    print(f"[FK EXPANSION] seeds={seed_names} -> {expanded}",
                          flush=True)
                    seed_names = expanded
        except Exception as exc:
            print(f"FK EXPANSION ERROR: {exc}", flush=True)
        graph = build_subgraph(database_id, seed_names)
    else:
        graph = get_database_graph(database_id)

    if not graph:
        return None, tables_considered, {
            "success": False,
            "message": "Database not found",
        }

    return graph, tables_considered, None
