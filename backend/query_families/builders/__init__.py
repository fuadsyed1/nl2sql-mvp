"""
query_families/builders

Deterministic family builders. Each `build_*(question, idx)` returns an
extraction dict (the same shape the LLM extractor produces, consumed by
semantic.ir_builder.build_from_extraction) or None when the required slots
can't be resolved from the schema. Nothing here hardcodes table/column names —
slots come from query_families.slot_extractor.
"""

import re

from query_families import slot_extractor as se
from query_families import family_types as ft

__all__ = ["build_family"]


# ---------------------------------------------------------------------------
# 11. min_max_same_entity_per_group  (fully implemented — headline family)
# ---------------------------------------------------------------------------
def build_min_max_same_entity_per_group(question, idx):
    value = se.find_value_column(question, idx, list(idx["tables"]))
    group = se.find_group_column(question, idx, list(idx["tables"]))
    if not value or not group:
        return None
    value_table, value_col = value
    group_table, group_col = group
    entity_table = se.find_entity_table(question, idx, exclude={value_table, group_table})
    if not entity_table:
        return None
    entity_key = se.key_column(idx, entity_table)
    if not entity_key:
        return None

    # base relation: entity joined out to the value/group tables, choosing the
    # path whose action table matches the question verb (purchased -> purchases,
    # fed -> feeding, ...) rather than an arbitrary shortest path.
    joins = se.find_action_path(entity_table, value_table, question, idx) or []
    present = {entity_table} | {j["to_table"] for j in joins}
    if group_table not in present:
        for j in se.find_action_path(entity_table, group_table, question, idx) or []:
            if j["to_table"] not in present:
                joins.append(j)
                present.add(j["to_table"])
    if value_table not in present or group_table not in present:
        return None

    base = {
        "name": "base_items", "from_table": entity_table, "joins": joins,
        "select": [
            {"table": entity_table, "column": entity_key, "alias": "entity_id"},
            {"table": group_table, "column": group_col, "alias": "group_col"},
            {"table": value_table, "column": value_col, "alias": "value_col"},
        ],
        "aggregations": [], "group_by": [],
    }
    extremes = {
        "name": "group_extremes", "from_table": "base_items", "joins": [],
        "select": [{"table": "base_items", "column": "group_col", "alias": "group_col"}],
        "aggregations": [
            {"function": "MIN", "table": "base_items", "column": "value_col", "alias": "min_value"},
            {"function": "MAX", "table": "base_items", "column": "value_col", "alias": "max_value"},
        ],
        "group_by": [{"table": "base_items", "column": "group_col"}],
    }
    return {
        "derived_relations": [base, extremes],
        "aliases": [
            {"alias": "low", "table": "base_items"},
            {"alias": "high", "table": "base_items"},
            {"alias": "g", "table": "group_extremes"},
        ],
        "alias_joins": [
            {"from": {"alias": "low", "column": "entity_id"},
             "to": {"alias": "high", "column": "entity_id"}, "op": "="},
            {"from": {"alias": "low", "column": "group_col"},
             "to": {"alias": "high", "column": "group_col"}, "op": "="},
            {"from": {"alias": "low", "column": "group_col"},
             "to": {"alias": "g", "column": "group_col"}, "op": "="},
        ],
        "alias_filters": [
            {"left": {"alias": "low", "column": "value_col"}, "op": "=",
             "right": {"alias": "g", "column": "min_value"}},
            {"left": {"alias": "high", "column": "value_col"}, "op": "=",
             "right": {"alias": "g", "column": "max_value"}},
        ],
        "alias_select": [
            {"alias": "low", "column": "group_col", "as": "group_col"},
            {"alias": "low", "column": "entity_id", "as": "entity_id"},
        ],
        "distinct": True,
    }


# ---------------------------------------------------------------------------
# 9. derived_aggregate_cte  (fully implemented — aggregate top-per-group)
# ---------------------------------------------------------------------------
def _agg_function(q):
    q = " " + q.lower() + " "
    if any(w in q for w in ("average", " avg ", " mean ")):
        return "AVG"
    if any(w in q for w in ("total", " sum ", "sum of")):
        return "SUM"
    if any(w in q for w in ("count", "number of", "how many")):
        return "COUNT"
    return "SUM"


def build_derived_aggregate_cte(question, idx):
    value = se.find_value_column(question, idx, list(idx["tables"]))
    group = se.find_group_column(question, idx, list(idx["tables"]))
    if not value or not group:
        return None
    value_table, value_col = value
    group_table, group_col = group
    entity_table = se.find_entity_table(question, idx, exclude={value_table})
    if not entity_table:
        return None
    entity_key = se.key_column(idx, entity_table)
    joins = se.find_path(entity_table, value_table, idx) or []
    present = {entity_table} | {j["to_table"] for j in joins}
    if group_table not in present:
        for j in se.find_path(entity_table, group_table, idx) or []:
            if j["to_table"] not in present:
                joins.append(j)
                present.add(j["to_table"])
    if value_table not in present:
        return None

    fn = _agg_function(question)
    cte_name = entity_table + "_totals"
    cte = {
        "name": cte_name, "from_table": entity_table, "joins": joins,
        "select": [
            {"table": entity_table, "column": entity_key, "alias": "entity_id"},
            {"table": group_table, "column": group_col, "alias": "group_col"},
        ],
        "aggregations": [{"function": fn, "table": value_table, "column": value_col,
                          "alias": "agg_value"}],
        "group_by": [{"table": entity_table, "column": entity_key},
                     {"table": group_table, "column": group_col}],
    }
    extraction = {"derived_relations": [cte], "main_from": cte_name}
    q = " " + question.lower() + " "
    if any(w in q for w in ("highest", "most", "largest", "top", "maximum", "greatest")):
        direction = "desc"
    elif any(w in q for w in ("lowest", "least", "smallest", "minimum", "fewest")):
        direction = "asc"
    else:
        direction = None
    if direction:
        extraction["top_per_group"] = [{
            "table": cte_name,
            "partition_by": [{"table": cte_name, "column": "group_col"}],
            "order_by": {"table": cte_name, "column": "agg_value", "direction": direction},
            "rank": 1, "include_ties": True,
        }]
    return extraction


# ---------------------------------------------------------------------------
# 8. count_distinct_comparison  (fully implemented — two independent counts)
# ---------------------------------------------------------------------------
def _dedup_path(entity_table, joins):
    """Drop any join whose target table is already present (a table is never
    joined twice unaliased). Returns (deduped_joins, present_tables)."""
    present = {entity_table}
    out = []
    for j in joins or []:
        to = str(j.get("to_table") or "").lower()
        if not to or to in present:
            continue
        out.append(j)
        present.add(to)
    return out, present


def _count_cte(name, alias, entity_table, entity_key, path, count_table, count_col, idx):
    """A COUNT(DISTINCT count_table.count_col) CTE grouped by the entity, over a
    de-duplicated join path. Returns None if the path is empty/invalid or does
    not reach the counted table."""
    joins, present = _dedup_path(entity_table, path or [])
    if count_table not in present and count_table != entity_table:
        return None
    return {
        "name": name, "from_table": entity_table, "joins": joins,
        "select": [{"table": entity_table, "column": entity_key, "alias": "entity_id"}],
        "aggregations": [{"function": "COUNT", "distinct": True,
                          "table": count_table, "column": count_col, "alias": alias}],
        "group_by": [{"table": entity_table, "column": entity_key}],
    }


def build_count_distinct_comparison(question, idx):
    entity_table = se.find_entity_table(question, idx)
    if not entity_table:
        return None
    entity_key = se.key_column(idx, entity_table)
    op = ">" if any(w in (" " + question.lower() + " ")
                    for w in ("more", "greater", "higher")) else "<"

    # Two DIFFERENT concept nouns ("alert types" vs "courses") -> count each on
    # its own path. Same concept ("brands" both sides) -> two action bridges.
    ca, cb = se.two_concept_columns(question, idx)
    if ca and cb and ca != cb:
        (ta, cca), (tb, ccb) = ca, cb
        left = _count_cte("count_a", "count_a", entity_table, entity_key,
                          se.find_path(entity_table, ta, idx), ta, cca, idx)
        right = _count_cte("count_b", "count_b", entity_table, entity_key,
                           se.find_path(entity_table, tb, idx), tb, ccb, idx)
    else:
        target = se.find_distinct_attribute(question, idx, list(idx["tables"]))
        if not target:
            return None
        target_table, target_col = target
        bridges = []
        for r in idx["relationships"]:
            ft, tt = str(r.get("from_table") or "").lower(), str(r.get("to_table") or "").lower()
            for x, y in ((ft, tt), (tt, ft)):
                if y == target_table and x not in (entity_table, target_table):
                    if se.find_path(entity_table, x, idx) is not None and x not in bridges:
                        bridges.append(x)
        if len(bridges) < 2:
            return None
        a, b = bridges[0], bridges[1]
        left = _count_cte("count_a", "count_a", entity_table, entity_key,
                          (se.find_path(entity_table, a, idx) or [])
                          + (se.find_path(a, target_table, idx) or []),
                          target_table, target_col, idx)
        right = _count_cte("count_b", "count_b", entity_table, entity_key,
                           (se.find_path(entity_table, b, idx) or [])
                           + (se.find_path(b, target_table, idx) or []),
                           target_table, target_col, idx)

    if left is None or right is None:
        return None
    return {
        "derived_relations": [left, right],
        "select": [{"table": "count_a", "column": "entity_id"}],
        "explicit_joins": [{
            "join_type": "inner", "from_table": "count_a", "to_table": "count_b",
            "conditions": [{"left": {"table": "count_a", "column": "entity_id"}, "op": "=",
                            "right": {"table": "count_b", "column": "entity_id"}}],
        }],
        "filters": [{"table": "count_a", "column": "count_a", "op": op,
                     "value_ref": {"table": "count_b", "column": "count_b"}}],
    }


# ---------------------------------------------------------------------------
# 10. self_join_pair  (fully implemented)
# ---------------------------------------------------------------------------
def build_self_join_pair(question, idx):
    tables = se.mentioned_tables(question, idx)
    if not tables:
        return None
    pair_table = tables[0]
    pair_key = se.key_column(idx, pair_table)
    aliases = [{"alias": "p1", "table": pair_table}, {"alias": "p2", "table": pair_table}]
    alias_joins = []
    alias_filters = []
    q = " " + question.lower() + " "

    rel_aliases = {}        # related_table -> (a1, a2): joined ONCE, reused
    seen_self = set()       # pair-table self-comparisons already added

    # "same/different <attr>" cues -> equality/inequality between the two rows.
    for cue, op in (("same ", "="), ("different ", "<>")):
        for m in _iter_after(q, cue):
            attr = se._singular(m)
            # attribute on the pair table itself?
            col = _find_col(idx, pair_table, attr)
            if col:
                key = (col, op)
                if key in seen_self:
                    continue
                seen_self.add(key)
                alias_joins.append({"from": {"alias": "p1", "column": col}, "op": op,
                                    "to": {"alias": "p2", "column": col}})
                continue
            # attribute on a related table reachable in one hop
            rel = _related_with_col(idx, pair_table, attr)
            if rel:
                rt, rcol, fk_pair, fk_rel = rel
                if rt not in rel_aliases:      # join the related table only once
                    a1, a2 = "l1_" + rt, "l2_" + rt
                    rel_aliases[rt] = (a1, a2)
                    aliases.extend([{"alias": a1, "table": rt}, {"alias": a2, "table": rt}])
                    alias_joins.append({"from": {"alias": "p1", "column": fk_pair}, "op": "=",
                                        "to": {"alias": a1, "column": fk_rel}})
                    alias_joins.append({"from": {"alias": "p2", "column": fk_pair}, "op": "=",
                                        "to": {"alias": a2, "column": fk_rel}})
                a1, a2 = rel_aliases[rt]
                alias_filters.append({"left": {"alias": a1, "column": rcol}, "op": op,
                                      "right": {"alias": a2, "column": rcol}})

    # duplicate-pair guard on the pair key (< for pairs).
    if pair_key:
        alias_joins.append({"from": {"alias": "p1", "column": pair_key}, "op": "<",
                            "to": {"alias": "p2", "column": pair_key}})
    if not alias_joins:
        return None
    return {
        "aliases": aliases,
        "alias_joins": alias_joins,
        "alias_filters": alias_filters,
        "alias_select": [
            {"alias": "p1", "column": pair_key, "as": "id_1"},
            {"alias": "p2", "column": pair_key, "as": "id_2"},
        ],
    }


# ---------------------------------------------------------------------------
# 3. outer_join_null  (fully implemented)
# ---------------------------------------------------------------------------
def build_outer_join_null(question, idx):
    tables = se.mentioned_tables(question, idx)
    if len(tables) < 2:
        return None
    left, right = tables[0], tables[1]
    path = se.find_path(left, right, idx)
    if not path or len(path) != 1:
        return None
    step = path[0]
    left_key = se.key_column(idx, left)
    right_key = se.key_column(idx, right)
    extraction = {
        "select": [
            {"table": left, "column": left_key},
            {"table": right, "column": right_key},
        ],
        "explicit_joins": [{
            "join_type": "left", "from_table": left, "to_table": right,
            "conditions": [{"left": {"table": step["from_table"], "column": step["from_column"]},
                            "op": "=",
                            "right": {"table": step["to_table"], "column": step["to_column"]}}],
        }],
    }
    q = " " + question.lower() + " "
    wants_null = any(w in q for w in ("without ", "no matching", "have no", "with no",
                                      "unmatched", "is null", "not have"))
    if wants_null:
        extraction["null_filters"] = [{"table": right, "column": right_key, "op": "IS NULL"}]
    return extraction


# ---------------------------------------------------------------------------
# 2. anti_exists  (fully implemented)
# ---------------------------------------------------------------------------
def build_anti_exists(question, idx):
    tables = se.mentioned_tables(question, idx)
    if not tables:
        return None
    subject = tables[0]                       # the entity being listed
    # The absence/action table is usually a VERB ("purchased" -> purchases), not
    # a mentioned table, so resolve it from the relationship graph.
    action = se.find_action_table(subject, question, idx)
    if not action:
        return None
    action_table, fk_on_action, key_on_subject = action
    subject_key = se.key_column(idx, subject)
    nm = se.name_column(idx, subject)
    select = [{"table": subject, "column": subject_key}]
    if nm and nm != subject_key:
        select.append({"table": subject, "column": nm})
    return {
        "tables": [subject],
        "select": [s for s in select if s["column"]],
        "anti_exists": [{
            "target_table": action_table,
            "where": [{"left": {"table": action_table, "column": fk_on_action},
                       "op": "=",
                       "right": {"table": subject, "column": key_on_subject}}],
        }],
    }


# ---------------------------------------------------------------------------
# 4. top_per_group  (fully implemented)
# ---------------------------------------------------------------------------
def build_top_per_group(question, idx):
    value = se.find_value_column(question, idx, list(idx["tables"]))
    group = se.find_group_column(question, idx, list(idx["tables"]))
    if not value or not group:
        return None
    vt, vc = value
    gt, gc = group
    if vt != gt:              # a correlated rank needs value + group on one base table
        return None
    table = vt
    q = " " + question.lower() + " "
    rank = 2 if "second" in q else (3 if "third" in q else 1)
    direction = "asc" if any(w in q for w in (
        "lowest", "least", "cheapest", "smallest", "minimum", "fewest", "earliest")) else "desc"
    sel = [{"table": table, "column": se.key_column(idx, table)},
           {"table": table, "column": gc},
           {"table": table, "column": vc}]
    nm = se.name_column(idx, table)
    if nm and nm not in (gc, vc):
        sel.append({"table": table, "column": nm})
    return {
        "tables": [table],
        "select": [s for s in sel if s["column"]],
        "top_per_group": [{
            "table": table,
            "partition_by": [{"table": table, "column": gc}],
            "order_by": {"table": table, "column": vc, "direction": direction},
            "rank": rank, "include_ties": True,
        }],
    }


# ---------------------------------------------------------------------------
# 5. latest_earliest_per_entity  (fully implemented — top_per_group over a date)
# ---------------------------------------------------------------------------
def build_latest_earliest_per_entity(question, idx):
    entity = se.find_entity_table(question, idx)
    rec = se.find_date_record_table(entity, question, idx) if entity else None
    if not rec:
        for t in se.mentioned_tables(question, idx):
            dc = se.date_columns(idx, t)
            if dc:
                rec = (t, se.key_column(idx, t), dc[0])
                break
    if not rec:
        return None
    record_table, fk_to_entity, date_col = rec
    if not fk_to_entity:
        return None
    q = " " + question.lower() + " "
    direction = "asc" if any(w in q for w in ("first ", "earliest", "oldest")) else "desc"
    return {
        "tables": [record_table],
        "select": [],
        "top_per_group": [{
            "table": record_table,
            "partition_by": [{"table": record_table, "column": fk_to_entity}],
            "order_by": {"table": record_table, "column": date_col, "direction": direction},
            "rank": 1, "include_ties": True,
        }],
    }


# ---------------------------------------------------------------------------
# 12. mismatch_comparison  (fully implemented — value_ref column comparison)
# ---------------------------------------------------------------------------
def build_mismatch_comparison(question, idx):
    pair = se.find_comparable_pair(question, idx, list(idx["tables"]))
    if not pair:
        return None
    (t1, c1), (t2, c2) = pair
    entity = se.find_entity_table(question, idx) or t1
    q = " " + question.lower() + " "
    op = "=" if (" same " in q and " not " not in q and "different" not in q) else "!="
    needed = {entity, t1, t2}
    for tgt in (t1, t2):
        for j in se.find_path(entity, tgt, idx) or []:
            needed.add(j["from_table"])
            needed.add(j["to_table"])
    ek, nm = se.key_column(idx, entity), se.name_column(idx, entity)
    select = [{"table": entity, "column": ek}]
    if nm:
        select.append({"table": entity, "column": nm})
    return {
        "tables": sorted(needed),
        "select": [s for s in select if s["column"]],
        "filters": [{"table": t1, "column": c1, "op": op,
                     "value_ref": {"table": t2, "column": c2}}],
        "distinct": True,
    }


# ---------------------------------------------------------------------------
# 6. universal_every_all  (fully implemented — double NOT EXISTS)
# ---------------------------------------------------------------------------
def build_universal_every_all(question, idx):
    q = " " + question.lower() + " "
    entity = se.find_entity_table(question, idx)
    domain = None
    for cue in ("every ", "each ", "all "):
        m = re.search(re.escape(cue) + r"([a-z_]+)", q)
        if m:
            sw = se._singular(m.group(1))
            for name in idx["tables"]:
                if sw in se._forms(name) or se._singular(name) == sw:
                    domain = name
                    break
        if domain:
            break
    if not domain:
        for t in se.mentioned_tables(question, idx):
            if t != entity:
                domain = t
                break
    if not entity or not domain or domain == entity:
        return None
    corr = se.find_path(domain, entity, idx)
    if not corr or len(corr) != 1:
        return None
    step = corr[0]
    domain_filters = [{"left": {"table": step["from_table"], "column": step["from_column"]},
                       "op": "=",
                       "right": {"table": step["to_table"], "column": step["to_column"]}}]

    must = None
    pair = se.find_comparable_pair(question, idx, list(idx["tables"]))
    if pair:
        (t1, c1), (t2, c2) = pair
        if t1 == domain:
            dom_col, other_t, other_c = c1, t2, c2
        elif t2 == domain:
            dom_col, other_t, other_c = c2, t1, c1
        else:
            dom_col = other_t = other_c = None
        if other_t:
            path = se.find_path(domain, other_t, idx)
            if path:
                first = path[0]
                must = {
                    "target_table": first["to_table"],
                    "joins": path[1:],
                    "where": [
                        {"left": {"table": first["to_table"], "column": first["to_column"]},
                         "op": "=",
                         "right": {"table": first["from_table"], "column": first["from_column"]}},
                        {"left": {"table": other_t, "column": other_c}, "op": "=",
                         "right": {"table": domain, "column": dom_col}},
                    ],
                }
    if must is None:
        for nb, (nb_col, dom_col) in se.neighbors(domain, idx).items():
            if nb != entity:
                must = {"target_table": nb, "joins": [],
                        "where": [{"left": {"table": nb, "column": nb_col}, "op": "=",
                                   "right": {"table": domain, "column": dom_col}}]}
                break
    if must is None:
        return None
    ek, nm = se.key_column(idx, entity), se.name_column(idx, entity)
    select = [{"table": entity, "column": ek}]
    if nm:
        select.append({"table": entity, "column": nm})
    return {
        "tables": [entity],
        "select": [s for s in select if s["column"]],
        "universal": [{"domain_table": domain, "domain_filters": domain_filters,
                       "must_exist": must}],
        "distinct": True,
    }


# ---------------------------------------------------------------------------
# 7. set_division_count_distinct  (fully implemented)
# ---------------------------------------------------------------------------
def build_set_division_count_distinct(question, idx):
    q = " " + question.lower() + " "
    set_word = None
    for cue in ("for all ", "for every ", " all "):
        m = re.search(re.escape(cue) + r"([a-z_]+)", q)
        if m:
            set_word = m.group(1)
            break
    if not set_word:
        return None
    pair = se.find_comparable_pair(question, idx, list(idx["tables"]))
    if not pair:
        return None
    (t1, c1), (t2, c2) = pair
    subj = se.subject_noun(question)

    def _group_col(t, skip):
        if not subj:
            return None
        sw = se._singular(subj)
        for c in se.columns_of(idx, t):
            if c["is_numeric"] or c["is_date"] or c["is_key"] or c["name"] in skip:
                continue
            if sw in c["name"]:
                return c["name"]
        return None

    g1, g2 = _group_col(t1, {c1, c2}), _group_col(t2, {c1, c2})
    if g1:
        group_table, cover_col, gcol, set_table, set_col = t1, c1, g1, t2, c2
    elif g2:
        group_table, cover_col, gcol, set_table, set_col = t2, c2, g2, t1, c1
    else:
        return None
    return {
        "tables": [group_table],
        "select": [{"table": group_table, "column": gcol}],
        "set_division": [{
            "group_by": [{"table": group_table, "column": gcol}],
            "left": {"function": "COUNT", "distinct": True, "table": group_table, "column": cover_col},
            "op": "=",
            "right_subquery": {"function": "COUNT", "distinct": True, "table": set_table, "column": set_col},
        }],
    }


# ---------------------------------------------------------------------------
# 1. normal_join_filter_group  (conservative — defer to the LLM)
# ---------------------------------------------------------------------------
def build_normal_join_filter_group(question, idx):
    return None


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _iter_after(q, cue):
    import re
    return [m.group(1) for m in re.finditer(re.escape(cue) + r"([a-z_]+)", q)]


def _find_col(idx, table, attr):
    for c in se.columns_of(idx, table):
        if attr and attr in c["name"]:
            return c["name"]
    return None


def _related_with_col(idx, table, attr):
    """Return (related_table, attr_col, fk_on_pair, fk_on_related) for a one-hop
    related table that has a column matching `attr`, or None."""
    for r in idx["relationships"]:
        ft, fc = str(r.get("from_table") or "").lower(), str(r.get("from_column") or "").lower()
        tt, tc = str(r.get("to_table") or "").lower(), str(r.get("to_column") or "").lower()
        for pair_t, pair_c, rel_t, rel_c in ((ft, fc, tt, tc), (tt, tc, ft, fc)):
            if pair_t == table and rel_t != table:
                col = _find_col(idx, rel_t, attr)
                if col:
                    return (rel_t, col, pair_c, rel_c)
    return None


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------
_BUILDERS = {
    ft.MIN_MAX_SAME_ENTITY_PER_GROUP: build_min_max_same_entity_per_group,
    ft.DERIVED_AGGREGATE_CTE: build_derived_aggregate_cte,
    ft.COUNT_DISTINCT_COMPARISON: build_count_distinct_comparison,
    ft.SELF_JOIN_PAIR: build_self_join_pair,
    ft.OUTER_JOIN_NULL: build_outer_join_null,
    ft.ANTI_EXISTS: build_anti_exists,
    ft.TOP_PER_GROUP: build_top_per_group,
    ft.LATEST_EARLIEST_PER_ENTITY: build_latest_earliest_per_entity,
    ft.MISMATCH_COMPARISON: build_mismatch_comparison,
    ft.UNIVERSAL_EVERY_ALL: build_universal_every_all,
    ft.SET_DIVISION_COUNT_DISTINCT: build_set_division_count_distinct,
    ft.NORMAL_JOIN_FILTER_GROUP: build_normal_join_filter_group,
}


def build_family(family, question, idx):
    """Return an extraction dict for `family`, or None (skeleton / unbuildable)."""
    builder = _BUILDERS.get(family)
    return builder(question, idx) if builder else None
