"""
sql_candidates/consensus_ranking.py

Independent semantic consensus (replaces raw execution-result majority).

The old consensus treated a large execution-result group as evidence of
correctness. That is unsafe: several correlated candidates from ONE generator
family (llm_sql_direct / _grain / _variant, plus a repair derived from one of
them) can manufacture a majority, and candidates can return the same rows by
coincidence while using materially different predicates, formulas, grouping,
joins, or output grain. Execution-result equality is not semantic equivalence.

This module computes consensus from INDEPENDENT generator lineages grouped by a
normalized SEMANTIC FINGERPRINT (the parsed-AST shape) plus a supporting
result-signature guard:

  * one vote per independent generator family / lineage (a repair inherits the
    lineage it repairs and casts no new vote; correlated same-family variants
    count once);
  * a group is a valid consensus only with >= 2 independent lineages that share
    the same semantic fingerprint AND the same executed result;
  * consensus is a TIE-BREAKER, never primary correctness: it may not select a
    candidate that another eligible candidate semantically dominates (existing
    RC5 obligation profile), and when there is no valid independent consensus it
    does not manufacture a winner - the caller continues on its existing
    deterministic path and the reason is recorded.

Everything is schema-generic and derived from existing candidate metadata + the
existing SQL parser/validator signals. No database id, table, column, literal,
question text, query id, or generator-source preference is hardcoded.
"""
import hashlib
from collections import defaultdict

from sqlglot import exp

from sql_candidates.semantic_obligations import (
    canonical_signature, lineage_family, _parse, _select_scopes)
from sql_candidates.rc5_ranking import rc5_dominates
from sql_candidates.result_equivalence import result_signature

__all__ = ["semantic_fingerprint", "generator_family", "analyze_consensus",
           "consensus_select", "fingerprint_digest"]


def generator_family(source):
    """Independent generator family. Reuses the frozen lineage map: the
    direct-SQL family (direct / grain / variant / repair) is ONE lineage, the
    IR/extraction family (primary / variant_n) another, query_family a third.
    A repair therefore never adds a vote to an answer its own family produced."""
    return lineage_family(source)


def _order_limit_signature(tree):
    if tree is None:
        return ()
    parts = []
    for sel in _select_scopes(tree):
        order = sel.args.get("order")
        okeys = ()
        if order is not None:
            okeys = tuple((" ".join(str(o.this).lower().split()),
                           bool(o.args.get("desc")))
                          for o in order.find_all(exp.Ordered))
        lim = sel.args.get("limit")
        lval = None
        if lim is not None:
            try:
                lval = int(lim.text("expression") or lim.this.name)
            except Exception:
                lval = "?"
        parts.append((okeys, lval))
    return tuple(parts)


def _exists_signature(tree):
    if tree is None:
        return ()
    ex = sum(1 for _ in tree.find_all(exp.Exists))
    notex = 0
    for n in tree.find_all(exp.Not):
        if next(iter(n.find_all(exp.Exists)), None) is not None:
            notex += 1
    return (ex, notex)


def semantic_fingerprint(sql):
    """Deterministic meaning-level fingerprint. Built on the frozen canonical AST
    signature (output columns/expressions, aggregate + DISTINCT usage, tables,
    typed join edges, WHERE column/operator/literal triples, GROUP BY, HAVING,
    DISTINCT, set operators, subquery structure) plus ORDER BY / LIMIT and
    EXISTS / NOT EXISTS. Aliases, whitespace, quoting and commutative ordering
    are normalized away; two candidates share a fingerprint only when they are
    structurally the same query, not merely when their results coincide."""
    tree = _parse(sql)
    return (canonical_signature(sql),
            _order_limit_signature(tree),
            _exists_signature(tree))


def fingerprint_digest(fp):
    """Stable, human-readable digest (never a Python object id)."""
    try:
        return "fp:" + hashlib.sha1(repr(fp).encode("utf-8")).hexdigest()[:16]
    except Exception:
        return "fp:unhashable"


class _Group:
    __slots__ = ("fingerprint", "members", "families", "raw_count",
                 "independent_lineage_count", "has_rows", "strong")

    def __init__(self, fp, members, low_threshold):
        self.fingerprint = fp
        self.members = members
        self.families = sorted({m._cons_family for m in members})
        self.raw_count = len(members)
        self.independent_lineage_count = len(self.families)
        self.has_rows = any((m.row_count or 0) > 0 for m in members)
        self.strong = max(m.score for m in members) >= low_threshold


def _rank_key(c, source_priority):
    return (c.score, source_priority.get(c.source, 0), c.label)


def analyze_consensus(pool, low_threshold):
    """Attach provenance (_cons_family, _cons_fp) and group by fingerprint.
    Deterministic ordering (independent lineages, then raw count)."""
    for c in pool:
        c._cons_family = generator_family(c.source)
        try:
            c._cons_fp = semantic_fingerprint(c.sql)
        except Exception:
            c._cons_fp = ("unparsed", (c.sql or ""))
        try:
            c._cons_result = result_signature(getattr(c, "execution", None))
        except Exception:
            c._cons_result = None
    buckets = defaultdict(list)
    for c in pool:
        # A consensus group = structurally-the-same query (fingerprint) whose
        # members ALSO agree on the executed answer (result signature). The
        # fingerprint is the primary key; result agreement is a supporting guard
        # so structurally-identical candidates that somehow disagree do not vote
        # together, and coincidental result matches across different structures
        # never group.
        buckets[(c._cons_fp, c._cons_result)].append(c)
    groups = [_Group(fp, mem, low_threshold) for fp, mem in buckets.items()]
    groups.sort(key=lambda g: (g.independent_lineage_count, g.raw_count),
                reverse=True)
    return groups


def consensus_select(pool, low_threshold, source_priority):
    """Return (provisional_pick_or_None, meta, group_members_or_None).

    A provisional consensus pick is returned only when a valid independent
    semantic consensus exists (>= 2 independent lineages sharing one fingerprint,
    with rows and a strong score) AND no OTHER eligible candidate semantically
    dominates its representative (RC5 obligation profile). Otherwise (None, meta,
    None) is returned with a recorded rejection reason. Each pool member is
    expected to carry `_rc5_ob` / `_rc5_ap` (RC5 obligation profile + applies)."""
    meta = {
        "consensus_raw_group_size": 0,
        "consensus_independent_lineage_count": 0,
        "consensus_generator_families": [],
        "consensus_lineage_ids": [],
        "consensus_collapsed_correlated_candidates": 0,
        "consensus_semantic_fingerprint": None,
        "consensus_result_signature": None,
        "consensus_eligible": False,
        "consensus_rejection_reason": None,
        "consensus_provisional_pick": None,
        "stronger_semantic_candidate": None,
    }
    if not pool:
        meta["consensus_rejection_reason"] = "no_consensus_eligible_group"
        return None, meta, None

    groups = analyze_consensus(pool, low_threshold)
    valid = [g for g in groups
             if g.independent_lineage_count >= 2 and g.has_rows and g.strong]

    if not valid:
        if any(g.raw_count >= 2 for g in groups):
            meta["consensus_rejection_reason"] = "single_generator_family"
        else:
            meta["consensus_rejection_reason"] = "insufficient_independent_lineages"
        top = groups[0]
        meta.update({
            "consensus_raw_group_size": top.raw_count,
            "consensus_independent_lineage_count": top.independent_lineage_count,
            "consensus_generator_families": top.families,
            "consensus_lineage_ids": top.families,
            "consensus_collapsed_correlated_candidates":
                top.raw_count - top.independent_lineage_count,
            "consensus_semantic_fingerprint": fingerprint_digest(top.fingerprint),
        })
        return None, meta, None

    def _gkey(g):
        return (g.independent_lineage_count,
                sum(1 + m.score / 100.0 for m in g.members),
                max(m.score for m in g.members))

    best = max(valid, key=_gkey)
    rep = max(best.members, key=lambda c: _rank_key(c, source_priority))

    stronger = None
    rep_prof = getattr(rep, "_rc5_ob", None)
    for c in pool:
        if c in best.members:
            continue
        cprof = getattr(c, "_rc5_ob", None)
        ap = getattr(c, "_rc5_ap", None)
        if rep_prof is not None and cprof is not None and ap is not None:
            dom, _why, _d = rc5_dominates(cprof, rep_prof, ap)
            if dom:
                stronger = c
                break

    meta.update({
        "consensus_raw_group_size": best.raw_count,
        "consensus_independent_lineage_count": best.independent_lineage_count,
        "consensus_generator_families": best.families,
        "consensus_lineage_ids": best.families,
        "consensus_collapsed_correlated_candidates":
            best.raw_count - best.independent_lineage_count,
        "consensus_semantic_fingerprint": fingerprint_digest(best.fingerprint),
    })

    if stronger is not None:
        meta["consensus_rejection_reason"] = "stronger_semantic_candidate_exists"
        meta["stronger_semantic_candidate"] = stronger.label
        return None, meta, None

    meta["consensus_eligible"] = True
    meta["consensus_provisional_pick"] = rep.label
    return rep, meta, best.members
