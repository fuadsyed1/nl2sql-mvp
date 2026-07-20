"""
sql_candidates/rc5_ranking.py

RC5 - general semantic best-candidate ranking + equal-score tie-breaking.

Runs AFTER the provisional selection (consensus / best-score / RC4 override) is
established. Among the eligible, fatal-free, RC3-eligible candidates it compares
candidates by request OBLIGATION IDENTITY in a fixed priority order - never by a
single weighted score and never by generator source. A candidate replaces the
provisional pick only when it semantically DOMINATES it: it satisfies a superset
of the applicable mandatory obligations with none lost. Numeric score is
consulted only to order candidates already semantically equal, and a candidate
blocked by the RC4 override-dominance gate is never re-promoted here.

Everything is schema-generic and derived from the checklist / contract / parsed
AST / schema index - no database id, table, column, literal, question text, or
source preference is hardcoded, and every signal is invariant to whether a
candidate inlines literals or uses '?' parameters (so it can never favour one
generator's SQL style). The one linguistic cue (a generic count-of-entities
interrogative such as "how many" / "number of") is a language-level pattern
applicable to any schema, not a benchmark literal.

Four precise, tightly-gated obligations are compared (each fires only in the
structural situation it targets, so it cannot misfire on unrelated queries):

  * scalar_count_output   - a "how many ..." request must return one scalar
                            aggregate, not a row per qualifying entity.
  * comparison_predicate  - a comparison-subquery request that names the same
                            column on two tables must actually compare them.
  * relationship_specificity - a table with foreign keys to two in-query
                            entities, one a descendant of the other, must be
                            joined to the nearer (descendant) parent.
  * compound_set_complete - a compound membership request ("both A and B but
                            not C") must express every membership branch.
"""
import re as _re
from collections import defaultdict

from sqlglot import exp
from sql_candidates.semantic_obligations import (
    _parse, _select_scopes, _output_expressions, _has_aggregate)

__all__ = ["rc5_obligations", "rc5_dominates", "rc5_rank_tuple", "RC5_ORDER"]

RC5_ORDER = (
    "scalar_count_output",
    "comparison_predicate",
    "relationship_specificity",
    "compound_set_complete",
    "entity_grain_unique",
)

_COUNT_INTENT = _re.compile(
    r"\b(how many|number of|count of|count the|total number of)\b", _re.I)


def _colname(c):
    return (c.name or "").lower()


def _alias_map(tree):
    amap = {}
    for t in (tree.find_all(exp.Table) if tree is not None else []):
        real = (t.name or "").lower()
        amap[real] = real
        al = t.args.get("alias")
        if al is not None:
            an = getattr(al, "name", None)
            if an:
                amap[str(an).lower()] = real
    return amap


def _table_columns(idx):
    out = {}
    for t, cols in ((idx or {}).get("tables") or {}).items():
        out[t.lower()] = {c["name"].lower(): c for c in cols}
    return out


def _eq_col_joins(tree, amap):
    joins = []
    for cmp in tree.find_all(exp.EQ):
        l, r = cmp.this, cmp.expression
        if isinstance(l, exp.Column) and isinstance(r, exp.Column):
            lt = amap.get((l.table or "").lower(), (l.table or "").lower())
            rt = amap.get((r.table or "").lower(), (r.table or "").lower())
            joins.append((lt, _colname(l), rt, _colname(r)))
    return joins


def _scalar_count_applies(question):
    return bool(question and _COUNT_INTENT.search(question))


def _returns_scalar_aggregate(selects):
    if not selects:
        return False
    outer = selects[0]
    exprs = _output_expressions(outer)
    if not exprs or outer.args.get("group"):
        return False
    return all(_has_aggregate(e) for e in exprs)


def _comparison_pair(checklist):
    byname = defaultdict(set)
    for c in (checklist or {}).get("must_use_columns") or []:
        parts = str(c).split(".")
        if len(parts) == 2:
            byname[parts[1].lower()].add(parts[0].lower())
    for name, tbls in byname.items():
        if len(tbls) >= 2:
            return name
    return None


def _has_column_comparison(tree, colname):
    if tree is None:
        return False
    for cmp in tree.find_all((exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)):
        l, r = cmp.this, cmp.expression
        if isinstance(l, exp.Column) and isinstance(r, exp.Column) \
                and _colname(l) == colname and _colname(r) == colname \
                and (l.table or "").lower() != (r.table or "").lower():
            return True
    return False


def _pk_map(idx):
    """Real primary key per table = the FIRST key column in definition order
    (a table's own id is declared first; the over-inclusive is_key flag marks
    every *_id column, so position disambiguates the true PK from its FKs)."""
    pk = {}
    for t, cols in ((idx or {}).get("tables") or {}).items():
        for c in cols:
            if c.get("is_key"):
                pk[t.lower()] = c["name"].lower()
                break
    return pk


def _fk_parents(table, tcols, pkmap):
    """{parent_table: fk_col} - a column of `table` that equals another table's
    real primary key is an inferred foreign key to that table."""
    out = {}
    for cn in tcols.get(table, {}):
        if not cn.endswith("_id"):
            continue
        for other, opk in pkmap.items():
            if other != table and opk == cn:
                out[other] = cn
    return out


def _relationship_specificity(tree, tcols, pkmap, amap):
    if tree is None:
        return (False, True)
    qtables = {(t.name or "").lower() for t in tree.find_all(exp.Table)}
    joins = _eq_col_joins(tree, amap)
    applies = False
    ok = True
    for T in qtables:
        fks = _fk_parents(T, tcols, pkmap)
        parents = [p for p in fks if p in qtables]
        for p1 in parents:
            for p2 in parents:
                if p1 == p2:
                    continue
                if p2 in _fk_parents(p1, tcols, pkmap):
                    applies = True
                    fkcol = fks[p1]
                    joined = any(
                        (a == T and c == p1 and c1 == fkcol) or
                        (c == T and a == p1 and c2 == fkcol)
                        for (a, c1, c, c2) in joins)
                    if not joined:
                        ok = False
    return (applies, ok)


def _compound_set(checklist, tree):
    col = None
    n = 0
    for grp in (checklist or {}).get("required_literal_groups") or []:
        lits = [l for l in (grp.get("literals") or []) if str(l).strip()]
        if len(lits) >= 2 and grp.get("column"):
            col = str(grp["column"]).split(".")[-1].lower()
            n = len(set(str(l).strip().lower() for l in lits))
            break
    if not col or n < 2 or tree is None:
        return (False, True)
    refs = sum(1 for c in tree.find_all(exp.Column) if _colname(c) == col)
    return (True, refs >= n)


def _outer_from_tables(outer):
    """Real tables referenced by the OUTER query's FROM + JOINs (not subqueries),
    so a one-to-many join in the output path is distinguished from membership
    subqueries."""
    tabs = set()
    frm = outer.args.get("from")
    if frm is not None:
        for t in frm.find_all(exp.Table):
            tabs.add((t.name or "").lower())
    for j in (outer.args.get("joins") or []):
        node = j.this if hasattr(j, "this") else j
        if isinstance(node, exp.Table):
            tabs.add((node.name or "").lower())
        else:
            for t in j.find_all(exp.Table):
                tabs.add((t.name or "").lower())
    return tabs


def _entity_grain_unique(checklist, tree, tcols):
    """RC5.1 - when the request asks for ONE ROW PER ENTITY (checklist
    group_by_entity names the output entity key), a candidate must guarantee
    entity-level uniqueness: GROUP BY covering the entity key, SELECT DISTINCT,
    or no many-side (child) join that could repeat the entity. A candidate that
    joins a one-to-many path without such a guarantee is duplicate-prone.
    Returns (applies, detail). Never requires DISTINCT globally: it only fires
    when an entity grain is explicitly requested."""
    ge = (checklist or {}).get("group_by_entity")
    detail = {"requested_entity_key": ge, "output_grouped_by_entity_key": None,
              "output_distinct_on_entity": None, "many_side_duplicate_risk": None,
              "entity_uniqueness_guaranteed": True}
    if not ge or tree is None:
        return (False, detail)
    parts = str(ge).split(".")
    if len(parts) != 2:
        return (False, detail)
    ent_table, ent_key = parts[0].lower(), parts[1].lower()
    selects = _select_scopes(tree)
    if not selects:
        return (False, detail)
    outer = selects[0]
    grp = outer.args.get("group")
    grouped = bool(grp) and ent_key in {
        _colname(c) for c in grp.find_all(exp.Column)}
    distinct = bool(outer.args.get("distinct"))
    outer_tabs = _outer_from_tables(outer)
    many_side = any(T != ent_table and ent_key in tcols.get(T, {})
                    for T in outer_tabs)
    guaranteed = grouped or distinct or (not many_side)
    detail.update({"output_grouped_by_entity_key": grouped,
                   "output_distinct_on_entity": distinct,
                   "many_side_duplicate_risk": many_side,
                   "entity_uniqueness_guaranteed": guaranteed})
    return (True, detail)


def _duplicate_entity_rows_observed(base_profile, ge):
    """Supporting evidence only (never the primary signal): does the executed
    result show more rows than distinct entity-key values?"""
    if not ge:
        return None
    ex = (base_profile or {}).get("_execution") or {}
    cols = [str(c).lower() for c in (ex.get("columns") or [])]
    rows = ex.get("rows")
    key = str(ge).split(".")[-1].lower()
    if not isinstance(rows, list) or not rows or key not in cols:
        return None
    ki = cols.index(key)
    try:
        seen = [r[ki] for r in rows if len(r) > ki]
        return len(seen) > len(set(map(str, seen)))
    except Exception:
        return None


def rc5_obligations(sql, checklist, contract, idx, question, base_profile):
    tree = _parse(sql)
    selects = _select_scopes(tree)
    tcols = _table_columns(idx)
    pkmap = _pk_map(idx)
    amap = _alias_map(tree)
    shape = ((checklist or {}).get("required_sql_shape") or "").lower()

    scalar_ap = _scalar_count_applies(question)
    pair = _comparison_pair(checklist)
    pair_ap = bool(pair) and shape == "comparison_subquery"
    spec_ap, spec_ok = _relationship_specificity(tree, tcols, pkmap, amap)
    comp_ap, comp_ok = _compound_set(checklist, tree)
    grain_ap, grain_detail = _entity_grain_unique(checklist, tree, tcols)

    o = {
        "scalar_count_output": _returns_scalar_aggregate(selects) if scalar_ap else True,
        "comparison_predicate": _has_column_comparison(tree, pair) if pair_ap else True,
        "relationship_specificity": spec_ok,
        "compound_set_complete": comp_ok,
        "entity_grain_unique": grain_detail["entity_uniqueness_guaranteed"],
        # RC5.1 advisory profile fields (trace only; not compared directly):
        "requested_entity_key": grain_detail["requested_entity_key"],
        "entity_uniqueness_guaranteed": grain_detail["entity_uniqueness_guaranteed"],
        "output_grouped_by_entity_key": grain_detail["output_grouped_by_entity_key"],
        "output_distinct_on_entity": grain_detail["output_distinct_on_entity"],
        "many_side_duplicate_risk": grain_detail["many_side_duplicate_risk"],
        "duplicate_entity_rows_observed": _duplicate_entity_rows_observed(
            base_profile, checklist.get("group_by_entity") if checklist else None),
        "_numeric_score": float((base_profile or {}).get("_numeric_score", 0.0) or 0.0),
    }
    applies = {
        "scalar_count_output": scalar_ap,
        "comparison_predicate": pair_ap,
        "relationship_specificity": spec_ap,
        "compound_set_complete": comp_ap,
        "entity_grain_unique": grain_ap,
    }
    return o, applies


def rc5_rank_tuple(obligations):
    return tuple(1 if obligations.get(k) else 0 for k in RC5_ORDER) + \
        (obligations.get("_numeric_score", 0.0),)


def rc5_dominates(ob, oa, applies):
    lost = [o for o in RC5_ORDER if applies.get(o) and oa.get(o) and not ob.get(o)]
    gained = [o for o in RC5_ORDER if applies.get(o) and ob.get(o) and not oa.get(o)]
    detail = {"obligations_gained": gained, "obligations_lost": lost}
    if lost and gained:
        return False, "semantically incomparable (each satisfies a different obligation)", detail
    if lost:
        return False, "proposed candidate loses %s" % lost[0], detail
    if not gained:
        return False, "semantically equivalent on mandatory obligations", detail
    return True, "semantic dominance via %s" % gained[0], detail
