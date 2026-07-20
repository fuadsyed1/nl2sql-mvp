"""
services/relationship_resolver.py

Single authority for computing + persisting a database instance's relationship
set at SETUP and on explicit REDETECTION (never at query time).

Rules (docs/relationship_lifecycle_plan.md):
  * Database-declared PK/FK constraints, when present, are the ONLY auto-source
    (source='pk_fk', 100% confidence); heuristic inference is NOT run to compete.
  * A SMALL database with no declared PK/FK may receive generic value-overlap
    inference (source='inferred', with confidence).
  * A LARGE database with no declared PK/FK and no user-supplied relationships is
    REJECTED (nothing is stored; the caller rolls back the instance).
  * Every produced set enters 'review' — nothing is auto-finalized. Approval is a
    separate explicit step (the finalize endpoint).
  * Existing user-declared rows are preserved as ordinary members of the single
    set (not a competing authority layer).

Returns a dict: {"edges": [...], "status": "review"|None, "rejected": bool,
                 "reason": str}.
"""

from db.database_service import (
    get_relationships,
    add_relationships,
    clear_relationships,
    set_relationship_status,
    get_database_path,
    get_database_graph,
)
from schema.key_extractor import extract_foreign_keys
from schema.relationship_detector import detect_relationships
from schema.lazy_loader import get_database_meta
from local_benchmarks.benchmark_relationships import trusted_relationships

__all__ = ["resolve_and_store_relationships"]


def _pair(e):
    return frozenset({
        (str(e.get("from_table")).lower(), str(e.get("from_column")).lower()),
        (str(e.get("to_table")).lower(), str(e.get("to_column")).lower()),
    })


_PRIORITY = {"user": 3, "pk_fk": 2, "benchmark_trusted": 1, "inferred": 0,
             "legacy_unknown": 0}


def _dedupe(edges):
    best = {}
    for e in edges:
        k = _pair(e)
        cur = best.get(k)
        if cur is None or _PRIORITY.get(e.get("source"), 0) > \
                _PRIORITY.get(cur.get("source"), 0):
            best[k] = e
    return list(best.values())


def _stamp(edges, source, confirmed):
    out = []
    for e in edges or []:
        e = dict(e)
        e["source"] = source
        e["confirmed"] = 1 if confirmed else 0
        if confirmed and e.get("confidence") is None:
            e["confidence"] = 1.0
        out.append(e)
    return out


def _declared_fk_edges(db_path):
    # extract_foreign_keys already stamps source='pk_fk', confidence 1.0.
    return list(extract_foreign_keys(db_path) or [])


def _benchmark_edges(database_id):
    try:
        graph = get_database_graph(database_id)
    except Exception:
        graph = None
    if not graph:
        return []
    return _stamp(trusted_relationships(graph), "benchmark_trusted", confirmed=1)


def _is_large(database_id):
    try:
        meta = get_database_meta(database_id)
    except Exception:
        meta = None
    return bool(meta and meta.get("mode") == "large")


def _result(edges=None, status=None, rejected=False, reason=""):
    return {"edges": edges or [], "status": status,
            "rejected": rejected, "reason": reason}


def resolve_and_store_relationships(database_id, db_path=None, *,
                                    force_inference=False):
    if db_path is None:
        db_path = get_database_path(database_id)

    existing = get_relationships(database_id)
    user_edges = [dict(e) for e in existing if e.get("source") == "user"]

    declared = _declared_fk_edges(db_path)
    benchmark = _benchmark_edges(database_id) if not declared else []
    db_declared = declared + benchmark

    if db_declared:
        final = _dedupe(user_edges + db_declared)
    elif _is_large(database_id):
        # Large database with no declared PK/FK: only a user-supplied set can
        # make it usable. With none, REJECT (store nothing; caller rolls back).
        if not user_edges:
            return _result(
                rejected=True,
                reason="large_database_requires_relationships")
        final = _dedupe(user_edges)
    else:
        # Small database, no declared PK/FK -> generic inference suggestions.
        inferred = _stamp(detect_relationships(database_id), "inferred",
                          confirmed=0)
        final = _dedupe(user_edges + inferred) if user_edges else inferred

    clear_relationships(database_id)
    add_relationships(database_id, final)
    # Every set requires explicit review + approval; never auto-finalized.
    set_relationship_status(database_id, "review")
    return _result(edges=final, status="review")
