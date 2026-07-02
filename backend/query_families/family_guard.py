"""
query_families/family_guard.py

A generic, family-specific guard for query-family output. It accepts a family
extraction when the family's core construct is present and the concepts/shape
the question demands are represented; it rejects only clear mismatches, so a
confident-wrong family output falls back to the LLM.

validate_family_output(question, family, extraction, ir, graph) -> {valid, reasons}

Design principles (deliberately NOT a single global "every mentioned table must
appear" rule, which over-blocked good CTE/alias outputs):
  * per-family validators check that family's own structure;
  * shared checks apply only by question KEYWORD (absence/outer/for-all shape,
    column concepts, and count-distinct — the last scoped so "different address"
    is NOT treated as COUNT(DISTINCT));
  * when unsure, reject (LLM fallback), but bias toward accepting good builders.
Nothing hardcodes a database; petfood is only an example.
"""

import re

from query_families import slot_extractor as se
from query_families import family_types as ft

__all__ = ["validate_family_output"]


# ---------------------------------------------------------------------------
# collect real tables + columns referenced anywhere in an extraction
# ---------------------------------------------------------------------------
_TABLE_KEYS = ("table", "from_table", "to_table", "target_table", "domain_table",
               "group_table")
_COLUMN_KEYS = ("column", "from_column", "to_column")


def _walk(obj, tables, cols, flags):
    if isinstance(obj, dict):
        if "value_ref" in obj and isinstance(obj["value_ref"], dict):
            flags["value_ref"] = True
        if obj.get("distinct"):
            flags["distinct"] = True
        for k, v in obj.items():
            if k in _TABLE_KEYS and isinstance(v, str):
                tables.add(v.lower())
            elif k in _COLUMN_KEYS and isinstance(v, str):
                cols.add(v.lower())
            else:
                _walk(v, tables, cols, flags)
    elif isinstance(obj, list):
        for x in obj:
            _walk(x, tables, cols, flags)


def _collect(extraction, idx):
    raw, cols = set(), set()
    flags = {"distinct": False, "value_ref": False}
    alias_map, cte_names, cte_real = {}, set(), {}
    for a in extraction.get("aliases") or []:
        if isinstance(a, dict) and a.get("alias") and a.get("table"):
            alias_map[str(a["alias"]).lower()] = str(a["table"]).lower()
    for r in extraction.get("derived_relations") or []:
        if isinstance(r, dict) and r.get("name"):
            name = str(r["name"]).lower()
            cte_names.add(name)
            rt = set()
            if r.get("from_table"):
                rt.add(str(r["from_table"]).lower())
            for j in r.get("joins") or []:
                for kk in ("from_table", "to_table"):
                    if j.get(kk):
                        rt.add(str(j[kk]).lower())
            cte_real[name] = rt
    _walk(extraction, raw, cols, flags)
    for t in extraction.get("tables") or []:
        if isinstance(t, str):
            raw.add(t.lower())
    if extraction.get("main_from"):
        raw.add(str(extraction["main_from"]).lower())

    real = set()
    for t in raw:
        if t in alias_map:
            t = alias_map[t]
        if t in cte_names:
            real |= cte_real[t]
        else:
            real.add(t)
    for rt in cte_real.values():
        real |= rt
    schema = set(idx["tables"])
    real = {t for t in real if t in schema}
    return real, cols, flags


# ---------------------------------------------------------------------------
# small shared helpers
# ---------------------------------------------------------------------------
def _q(question):
    return " " + str(question or "").lower().strip() + " "


def _any(q, words):
    return any(w in q for w in words)


def _table_in_group(table, group):
    toks = [t for t in re.split(r"[_\s]", str(table).lower()) if len(t) > 2]
    return any(se._stem_eq(tok, g) for tok in toks for g in group)


def _col_has(cols, subs):
    return any(any(s in c for s in subs) for c in cols)


def _alias_base_tables(extraction):
    return {str(a["table"]).lower() for a in extraction.get("aliases") or []
            if isinstance(a, dict) and a.get("table")}


_AUX_HINTS = ("like", "profile", "history", "log", "preference", "event")


def _clearly_mentioned(question, idx):
    q = se._norm(question)
    out = []
    for name in idx["tables"]:
        base = name.lower()
        forms = {base, base.replace("_", " "), se._singular(base),
                 se._singular(base.replace("_", " "))}
        if any(se._contains_word(q, f) for f in forms):
            out.append(name)
    return out


def _pair_entity(question, idx, mentioned):
    q = se._norm(question)
    m = re.search(r"pairs? of ([a-z_]+)", q)
    if m:
        sw = se._singular(m.group(1))
        for name in idx["tables"]:
            if sw in se._forms(name) or se._singular(name) == sw:
                return name
    for t in mentioned:
        if not any(h in t for h in _AUX_HINTS):
            return t
    return mentioned[0] if mentioned else None


# concept -> (trigger phrases, satisfying column substrings)
_COLUMN_CONCEPTS = [
    ("species", ("species",), ("species",)),
    ("brand", ("brand",), ("brand",)),
    ("flavor", ("flavor", "flavour"), ("flavor", "flavour")),
    ("food type", ("food type", "food_type", "food types"), ("type",)),
    ("address", ("address",), ("address",)),
    ("city", ("city", "cities"), ("city",)),
    ("state", (" state ",), ("state",)),
    ("location", ("location",), ("location",)),
]

# count-distinct must be required ONLY for these — never for "different
# address/owners/dates/city" (those are column comparisons).
_CONCEPT_NOUNS = ("brand", "flavor", "type", "class", "severity", "course",
                  "species", "kind", "category", "alert")


def _wants_count_distinct(q):
    if _any(q, ("distinct ", "number of different", "count of different",
                "more distinct", "fewer distinct", "less distinct")):
        return True
    return re.search(r"(more|fewer|less|greater)\s+[a-z_ ]{0,20}(" +
                     "|".join(_CONCEPT_NOUNS) + r")", q) is not None


# ---------------------------------------------------------------------------
# shared, keyword-gated shape + concept checks (apply to every family)
# ---------------------------------------------------------------------------
def _shared_reasons(q, extraction, used_cols, flags):
    r = []
    outer = (_any(q, ("outer join", "left join", "include unmatched",
                      "still visible", "unmatched", "no matching record"))
             or ("without " in q and "without matching" not in q
                 and "without a match" not in q))
    if outer and not (extraction.get("explicit_joins") or extraction.get("null_filters")
                      or extraction.get("compound_filters")):
        r.append("outer-join intent but no explicit_joins/null/compound structure")

    if _any(q, ("never ", "no matching", "not purchased", "not fed", "not bought",
                "without matching", "has no ", "have no ", "does not exist",
                "not eaten", "not prescribed")):
        if not (extraction.get("anti_exists") or extraction.get("universal")
                or extraction.get("null_filters") or extraction.get("compound_filters")):
            r.append("absence intent but no anti_exists/universal/null structure")

    if _any(q, ("every ", "for all", "for every")):
        if not (extraction.get("universal") or extraction.get("set_division")
                or extraction.get("anti_exists")):
            r.append("for-all intent but no universal/set_division/NOT EXISTS")

    for name, triggers, subs in _COLUMN_CONCEPTS:
        if _any(q, triggers) and not _col_has(used_cols, subs):
            r.append(f"concept '{name}' mentioned but no matching column is used")

    if _wants_count_distinct(q) and not flags["distinct"]:
        r.append("distinct-count intent but no COUNT(DISTINCT ...)")
    return r


# ---------------------------------------------------------------------------
# Join-legality: collect every join / correlation / column-comparison equality
# and reject any that is not structurally sound against the schema FK graph.
# ---------------------------------------------------------------------------
def _join_edges(extraction):
    edges = []
    am = {str(a["alias"]).lower(): str(a["table"]).lower()
          for a in extraction.get("aliases") or []
          if isinstance(a, dict) and a.get("alias") and a.get("table")}

    def add(t1, c1, t2, c2):
        if t1 and c1 and t2 and c2:
            edges.append((str(t1).lower(), str(c1).lower(), str(t2).lower(), str(c2).lower()))

    def add_pred(p):
        l, r = p.get("left"), p.get("right")
        if isinstance(l, dict) and isinstance(r, dict) and l.get("column") and r.get("column"):
            add(l.get("table"), l.get("column"), r.get("table"), r.get("column"))

    def add_alias_pred(p):
        for a, b in (("from", "to"), ("left", "right")):
            x, y = p.get(a), p.get(b)
            if isinstance(x, dict) and isinstance(y, dict) and x.get("column") and y.get("column"):
                xt = am.get(str(x.get("alias")).lower(), x.get("alias"))
                yt = am.get(str(y.get("alias")).lower(), y.get("alias"))
                add(xt, x.get("column"), yt, y.get("column"))

    def sub_edges(spec):
        for j in spec.get("joins") or []:
            if isinstance(j, dict):
                add(j.get("from_table"), j.get("from_column"), j.get("to_table"), j.get("to_column"))
        for key in ("where", "join_conditions", "filters"):
            for p in spec.get(key) or []:
                if isinstance(p, dict):
                    add_pred(p)

    for r in extraction.get("derived_relations") or []:
        for j in r.get("joins") or []:
            if isinstance(j, dict):
                add(j.get("from_table"), j.get("from_column"), j.get("to_table"), j.get("to_column"))
    for ej in extraction.get("explicit_joins") or []:
        for c in ej.get("conditions") or []:
            if isinstance(c, dict):
                add_pred(c)
    for f in extraction.get("filters") or []:
        if isinstance(f, dict) and isinstance(f.get("value_ref"), dict):
            add(f.get("table"), f.get("column"),
                f["value_ref"].get("table"), f["value_ref"].get("column"))
    for a in extraction.get("anti_exists") or []:
        if isinstance(a, dict):
            sub_edges(a)
    for u in extraction.get("universal") or []:
        for p in u.get("domain_filters") or []:
            if isinstance(p, dict):
                add_pred(p)
        if isinstance(u.get("must_exist"), dict):
            sub_edges(u["must_exist"])
        if isinstance(u.get("bad_match"), dict):
            sub_edges(u["bad_match"])
        for cond in u.get("inner") or []:
            if isinstance(cond, dict):
                for kk in ("exists", "not_exists"):
                    if isinstance(cond.get(kk), dict):
                        sub_edges(cond[kk])
                if isinstance(cond.get("left"), dict):
                    add_pred(cond)
    for j in extraction.get("alias_joins") or []:
        if isinstance(j, dict):
            add_alias_pred(j)
    for f in extraction.get("alias_filters") or []:
        if isinstance(f, dict):
            add_alias_pred(f)
    for sd in extraction.get("set_division") or []:
        if isinstance(sd.get("right_subquery"), dict):
            sub_edges(sd["right_subquery"])
    return edges


def _validate_joins(extraction, idx):
    reasons = []
    for (t1, c1, t2, c2) in _join_edges(extraction):
        if not se.is_legal_edge(idx, t1, c1, t2, c2):
            reasons.append(f"illegal join/correlation {t1}.{c1} = {t2}.{c2} "
                           "(not a declared FK; e.g. key = measure)")
    return list(dict.fromkeys(reasons))


# ---------------------------------------------------------------------------
# per-family validators — check the family's OWN core structure (permissive)
# ---------------------------------------------------------------------------
def _v_top_per_group(question, ex, used, cols, idx):
    if not ex.get("top_per_group"):
        return ["top_per_group family produced no top_per_group"]
    return []


def _v_derived_aggregate(question, ex, used, cols, idx):
    if not ex.get("derived_relations"):
        return ["derived_aggregate family produced no derived_relations"]
    # completeness: a comparison/extremum question must actually compare/rank,
    # not just SELECT * from the CTE.
    q = _q(question)
    comparison = _any(q, ("above ", "below ", "more than", "less than", "greater than",
                          "higher than", "lower than", "including ties", "highest",
                          "lowest", "most ", "least ", "top "))
    if comparison and not (ex.get("top_per_group") or ex.get("filters")
                           or ex.get("having") or ex.get("set_division")):
        return ["derived_aggregate is a bare CTE (SELECT *) but the question asks "
                "a comparison/extremum"]
    return []


def _v_count_distinct(question, ex, used, cols, idx):
    _, _, flags = _collect(ex, idx)
    if not flags["distinct"]:
        return ["count_distinct family produced no COUNT(DISTINCT)"]
    # two-concept correctness: if the question names two DIFFERENT concept nouns,
    # the two sides must count those two columns (not the same one twice).
    ca, cb = se.two_concept_columns(question, idx)
    if ca and cb and ca != cb:
        agg = []
        for r in ex.get("derived_relations") or []:
            for a in r.get("aggregations") or []:
                if isinstance(a, dict) and a.get("distinct") and a.get("column"):
                    agg.append((str(a.get("table")).lower(), str(a.get("column")).lower()))
        want = {ca, cb}
        if not want.issubset(set(agg)):
            return [f"question names two distinct concepts {sorted(want)} but the "
                    f"COUNT(DISTINCT) columns are {sorted(set(agg))}"]
    return []


def _v_set_division(question, ex, used, cols, idx):
    if not ex.get("set_division"):
        return ["set_division family produced no set_division"]
    return []


def _v_min_max(question, ex, used, cols, idx):
    if not ex.get("derived_relations"):
        return ["min_max family produced no derived_relations"]
    return []


def _v_self_join(question, ex, used, cols, idx):
    if not ex.get("aliases"):
        return ["self_join family produced no aliases"]
    mentioned = _clearly_mentioned(question, idx)
    pe = _pair_entity(question, idx, mentioned)
    if pe and pe not in _alias_base_tables(ex):
        return [f"pairs intent but aliases are not over the pair entity '{pe}'"]
    return []


def _v_outer_join(question, ex, used, cols, idx):
    ej = ex.get("explicit_joins") or []
    if not any(str(j.get("join_type")).lower() == "left" for j in ej if isinstance(j, dict)):
        return ["outer_join family produced no LEFT JOIN"]
    if not (ex.get("null_filters") or ex.get("compound_filters")):
        return ["outer_join family produced no null/compound filter"]
    mentioned = _clearly_mentioned(question, idx)
    if mentioned and isinstance(ej[0], dict):
        root = str(ej[0].get("from_table") or "").lower()
        main = mentioned[0]
        if root and root != main and main not in used:
            return [f"outer_join root '{root}' is not the main entity '{main}'"]
    return []


def _v_universal(question, ex, used, cols, idx):
    if not (ex.get("universal") or ex.get("set_division")):
        return ["universal family produced no universal/set_division"]
    return []


def _v_anti_exists(question, ex, used, cols, idx):
    ax = ex.get("anti_exists") or []
    if not ax:
        return ["anti_exists family produced no anti_exists"]
    q = _q(question)
    qwords = set(re.findall(r"[a-z]+", q))
    targets = {str(a.get("target_table") or "").lower() for a in ax if isinstance(a, dict)}
    for group in se._ACTION_GROUPS:
        if any(w in group for w in qwords):
            if not any(_table_in_group(t, group) for t in targets):
                return ["anti_exists target does not match the question's action verb"]
    # completeness: shallow subject-only anti_exists (e.g. 'patients WHERE NOT
    # EXISTS appointments') that ignores the other content tables the question
    # clearly names is rejected -> LLM fallback.
    missing = [t for t in _clearly_mentioned(question, idx) if t not in used]
    if missing:
        return [f"anti_exists is too shallow: mentioned table(s) {missing} not "
                "represented (positive evidence / absence concept ignored)"]
    return []


def _v_mismatch(question, ex, used, cols, idx):
    _, _, flags = _collect(ex, idx)
    if not flags["value_ref"]:
        return ["mismatch family produced no column-to-column (value_ref) comparison"]
    return []


def _v_default(question, ex, used, cols, idx):
    return ["no family-specific validator (conservative reject)"]


_VALIDATORS = {
    ft.TOP_PER_GROUP: _v_top_per_group,
    ft.DERIVED_AGGREGATE_CTE: _v_derived_aggregate,
    ft.COUNT_DISTINCT_COMPARISON: _v_count_distinct,
    ft.SET_DIVISION_COUNT_DISTINCT: _v_set_division,
    ft.MIN_MAX_SAME_ENTITY_PER_GROUP: _v_min_max,
    ft.SELF_JOIN_PAIR: _v_self_join,
    ft.OUTER_JOIN_NULL: _v_outer_join,
    ft.UNIVERSAL_EVERY_ALL: _v_universal,
    ft.ANTI_EXISTS: _v_anti_exists,
    ft.MISMATCH_COMPARISON: _v_mismatch,
}


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def validate_family_output(question, family, extraction, ir, graph):
    if not isinstance(extraction, dict):
        return {"valid": False, "reasons": ["extraction is not a dict"]}
    idx = se.index_schema(graph)
    q = _q(question)
    used_tables, used_cols, flags = _collect(extraction, idx)

    reasons = list(_VALIDATORS.get(family, _v_default)(
        question, extraction, used_tables, used_cols, idx))
    reasons += _shared_reasons(q, extraction, used_cols, flags)
    reasons += _validate_joins(extraction, idx)     # illegal-join rejection (all families)

    # de-duplicate, preserve order
    reasons = list(dict.fromkeys(reasons))
    return {"valid": len(reasons) == 0, "reasons": reasons}
