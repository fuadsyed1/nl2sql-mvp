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

from db.database_service import get_database_graph
from schema.lazy_loader import get_database_meta
from schema.subgraph_builder import build_subgraph
from retrieval.table_retriever import retrieve_tables, requested_dates_satisfied

__all__ = ["resolve_query_graph"]

import re as _re
_WORD_SPLIT = _re.compile(r"[^a-z0-9]+")


def _name_tokens(s):
    return [t for t in _WORD_SPLIT.split(str(s or "").lower()) if t]


def _explicitly_named_tables(question, all_names):
    """Real table names that appear in the question, matched
    separator-INSENSITIVELY (underscores/spaces/hyphens equivalent).
    Only distinctive names (multi-token / digit / long) can match, so a
    plain common word cannot force a table. Returns real-cased names."""
    qn = " " + " ".join(_name_tokens(question)) + " "
    found = []
    for name in all_names:
        toks = _name_tokens(name)
        if not toks:
            continue
        distinctive = (len(toks) >= 2 or any(ch.isdigit() for ch in str(name))
                       or len(str(name)) >= 8)
        if not distinctive:
            continue
        pat = (r"(?<![a-z0-9])" + r"\s+".join(_re.escape(tk) for tk in toks)
               + r"(?![a-z0-9])")
        if _re.search(pat, qn):
            found.append(name)
    return found


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

        graph = build_subgraph(
            database_id, [t["table_name"] for t in tables_considered]
        )
    else:
        graph = get_database_graph(database_id)

    if not graph:
        return None, tables_considered, {
            "success": False,
            "message": "Database not found",
        }

    return graph, tables_considered, None
