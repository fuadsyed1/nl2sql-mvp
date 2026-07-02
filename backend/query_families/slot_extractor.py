"""
query_families/slot_extractor.py

Schema-aware slot extraction. Every helper keys off the schema graph — table
names, column names, data types, and relationship metadata — never off any
specific database's identifiers. Question words are matched to schema
identifiers; generic column ROLES (entity key, group column, value column, date
column, comparison column) are inferred from metadata, not hardcoded.
"""

import re
from collections import deque

_WORD = re.compile(r"[a-z0-9_]+")
_MIN_WORDS = ("cheapest", "lowest", "minimum", "smallest", "least expensive", "min ")
_MAX_WORDS = ("most expensive", "highest", "maximum", "largest", "priciest",
              "greatest", "dearest", "max ")
_NUMERIC_TYPES = ("INT", "REAL", "NUM", "DEC", "FLOAT", "DOUBLE", "MONEY")
_DATE_HINT = re.compile(r"^\s*\d{4}-\d{2}-\d{2}")
_GROUP_CUES = ("of that ", "for each ", "within their ", "within each ",
               "within ", "in each ", "per ", "by their ", "of the same ",
               "of each ", "same ")


# ---------------------------------------------------------------------------
# Schema index
# ---------------------------------------------------------------------------
def index_schema(graph):
    g = graph.get("database") if isinstance(graph, dict) and isinstance(graph.get("database"), dict) else graph
    tables = {}
    for t in (g.get("tables") if isinstance(g, dict) else None) or []:
        if not isinstance(t, dict):
            continue
        name = str(t.get("table_name") or "").strip().lower()
        cols = []
        for c in t.get("columns") or []:
            if not isinstance(c, dict) or c.get("column_name") is None:
                continue
            cname = str(c["column_name"]).strip().lower()
            dtype = str(c.get("data_type") or "").upper()
            samples = c.get("sample_values") or []
            is_date = any(x in dtype for x in ("DATE", "TIME")) or any(
                s is not None and _DATE_HINT.match(str(s)) for s in samples)
            is_num = any(x in dtype for x in _NUMERIC_TYPES) and not is_date
            is_key = bool(c.get("is_primary_key_candidate")) or cname.endswith("_id") or cname == "id"
            cols.append({"name": cname, "type": dtype, "samples": samples,
                         "is_date": is_date, "is_numeric": is_num, "is_key": is_key})
        if name:
            tables[name] = cols
    rels = [r for r in ((g.get("relationships") if isinstance(g, dict) else None) or [])
            if isinstance(r, dict)]
    return {"tables": tables, "relationships": rels}


# ---------------------------------------------------------------------------
# Word / identifier matching
# ---------------------------------------------------------------------------
def _norm(q):
    return " " + str(q or "").lower().strip() + " "


def _singular(w):
    w = str(w or "")
    if len(w) > 3 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("ses"):
        return w[:-2]
    if len(w) > 1 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _forms(name):
    """Surface forms of an identifier to look for in text: the name, spaced,
    singular, and each word."""
    base = str(name or "").lower()
    spaced = base.replace("_", " ")
    forms = {base, spaced, _singular(base), _singular(spaced)}
    for w in spaced.split():
        if len(w) > 2:
            forms.add(w)
            forms.add(_singular(w))
    return {f for f in forms if f}


def _contains_word(q, phrase):
    """True if `phrase` appears as a word/phrase in normalized q."""
    p = str(phrase or "").lower().strip()
    if not p:
        return False
    if " " in p:
        return p in q
    return re.search(r"(?<![a-z0-9_])" + re.escape(p) + r"(?![a-z0-9_])", q) is not None


def mentioned_tables(question, idx):
    """Tables whose name/singular/plural appears in the question, first-seen order."""
    q = _norm(question)
    hits = []
    for name in idx["tables"]:
        for form in _forms(name):
            if _contains_word(q, form):
                pos = q.find(form)
                hits.append((pos, name))
                break
    hits.sort()
    seen, out = set(), []
    for _, n in hits:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def columns_of(idx, table):
    return idx["tables"].get(table, [])


def key_column(idx, table):
    """The identity column of a table: a PK-candidate, else <singular>_id / id,
    else the first *_id, else the first column."""
    cols = columns_of(idx, table)
    want = _singular(table) + "_id"
    for c in cols:
        if c["name"] == want:
            return c["name"]
    for c in cols:
        if c["is_key"] and (c["name"] == "id" or c["name"].endswith("_id")):
            return c["name"]
    for c in cols:
        if c["is_key"]:
            return c["name"]
    return cols[0]["name"] if cols else None


def numeric_columns(idx, table):
    return [c["name"] for c in columns_of(idx, table) if c["is_numeric"] and not c["is_key"]]


def date_columns(idx, table):
    return [c["name"] for c in columns_of(idx, table) if c["is_date"]]


def categorical_columns(idx, table):
    return [c["name"] for c in columns_of(idx, table)
            if not c["is_numeric"] and not c["is_date"] and not c["is_key"]]


def find_column_in_question(question, idx, tables):
    """First (table, column) whose column name/word appears in the question."""
    q = _norm(question)
    for t in tables:
        for c in columns_of(idx, t):
            for form in _forms(c["name"]):
                if len(form) > 2 and _contains_word(q, form):
                    return (t, c["name"])
    return None


def _word_after(q, cue):
    m = re.search(re.escape(cue) + r"([a-z_]+)", q)
    return m.group(1) if m else None


def find_group_column(question, idx, tables):
    """A categorical column implied by a grouping cue ('per X', 'for each X',
    'of that X', 'within X', 'same X')."""
    q = _norm(question)
    for cue in _GROUP_CUES:
        w = _word_after(q, cue)
        if not w:
            continue
        sw = _singular(w)
        for t in tables:
            for c in columns_of(idx, t):
                if c["is_numeric"] or c["is_date"]:
                    continue
                if sw and sw in c["name"]:
                    return (t, c["name"])
    # fallback: a categorical column whose word appears in the question
    hit = find_column_in_question(question, idx,
                                  [t for t in tables])
    if hit:
        t, col = hit
        meta = next((c for c in columns_of(idx, t) if c["name"] == col), None)
        if meta and not meta["is_numeric"] and not meta["is_date"] and not meta["is_key"]:
            return hit
    return None


def find_value_column(question, idx, tables):
    """A numeric column implied by a magnitude/aggregate word. Prefer a column
    whose name appears in the question, else the first numeric non-key column."""
    q = _norm(question)
    # explicit column-name mention
    for t in tables:
        for c in columns_of(idx, t):
            if c["is_numeric"] and _contains_word(q, c["name"].replace("_", " ")):
                return (t, c["name"])
    def _by_keys(keys):
        # key-major search: try each key across all tables (most specific first)
        for key in keys:
            for t in tables:
                for c in columns_of(idx, t):
                    if c["is_numeric"] and key in c["name"]:
                        return (t, c["name"])
        return None

    # money/price hints -> a numeric column whose name suggests money
    if any(w in q for w in ("expensive", "cheap", "price", "cost", "spend", "spending", "amount")):
        hit = _by_keys(("price", "cost", "amount", "spend", "total", "income", "fee"))
        if hit:
            return hit
    # quantity hints
    if any(w in q for w in ("quantity", "servings", "count of", "number of")):
        hit = _by_keys(("quantity", "servings", "amount", "count"))
        if hit:
            return hit
    for t in tables:
        nums = numeric_columns(idx, t)
        if nums:
            return (t, nums[0])
    return None


def find_distinct_attribute(question, idx, tables):
    """Column to COUNT(DISTINCT ...) for 'distinct/different/more/fewer X'.
    Never an entity key. Priority: (1) the NOUN named in a
    'distinct/different/more/fewer <noun>' phrase mapped to a non-key column
    (brand/flavor/type/species/...); (2) any non-key categorical column whose
    name-word is mentioned; (3) any categorical column; (4) an *_id key only as a
    last resort (e.g. 'number of distinct owners')."""
    q = _norm(question)

    def _match_noun(noun):
        noun = _singular(noun)
        if len(noun) < 3:
            return None
        for t in tables:
            for c in columns_of(idx, t):
                if c["is_key"] or c["is_numeric"] or c["is_date"]:
                    continue
                if noun in c["name"]:
                    return (t, c["name"])
        return None

    def _exact(noun):
        noun = _singular(noun)
        if len(noun) < 3:
            return None
        for t in tables:
            for c in columns_of(idx, t):
                if not (c["is_key"] or c["is_numeric"] or c["is_date"]) and c["name"] == noun:
                    return (t, c["name"])
        return None

    # 1. the noun(s) after a "<comparator> ..." phrase — prefer an EXACT column
    # name (so "distinct food brands" -> brand, not food_type), then a substring.
    for cue in ("distinct ", "different ", "number of different ",
                "how many different ", "more ", "fewer ", "less "):
        m = re.search(re.escape(cue) + r"([a-z_ ]{0,40})", q)
        if not m:
            continue
        words = [w for w in m.group(1).split() if len(w) > 2]
        for w in words:
            hit = _exact(w)
            if hit:
                return hit
        for w in words:
            hit = _match_noun(w)
            if hit:
                return hit
    # 2. a non-key categorical column whose name-word is mentioned
    for t in tables:
        for c in columns_of(idx, t):
            if c["is_key"] or c["is_numeric"] or c["is_date"]:
                continue
            for form in _forms(c["name"]):
                if len(form) > 2 and _contains_word(q, form):
                    return (t, c["name"])
    # 3. any categorical column
    for t in tables:
        cats = categorical_columns(idx, t)
        if cats:
            return (t, cats[0])
    # 4. last resort: a key column
    for t in tables:
        k = key_column(idx, t)
        if k:
            return (t, k)
    return None


def find_entity_table(question, idx, exclude=()):
    """The subject/entity table — the noun after 'same', else the first
    mentioned table not excluded."""
    q = _norm(question)
    w = _word_after(q, "same ")
    if w:
        sw = _singular(w)
        for name in idx["tables"]:
            if sw in _forms(name) or _singular(name) == sw:
                return name
    for t in mentioned_tables(question, idx):
        if t not in exclude:
            return t
    return None


# ---------------------------------------------------------------------------
# Relationship path finding (undirected BFS over FK metadata)
# ---------------------------------------------------------------------------
def find_path(a, b, idx):
    """Return a list of join dicts linking table `a` to table `b`, or None."""
    a, b = str(a).lower(), str(b).lower()
    if a == b:
        return []
    adj = {}
    for r in idx["relationships"]:
        ft, fc = str(r.get("from_table") or "").lower(), str(r.get("from_column") or "").lower()
        tt, tc = str(r.get("to_table") or "").lower(), str(r.get("to_column") or "").lower()
        if not (ft and fc and tt and tc):
            continue
        adj.setdefault(ft, []).append((tt, fc, tc))
        adj.setdefault(tt, []).append((ft, tc, fc))
    q = deque([(a, [])])
    seen = {a}
    while q:
        node, path = q.popleft()
        for (nb, this_col, nb_col) in adj.get(node, []):
            if nb in seen:
                continue
            step = {"from_table": node, "from_column": this_col,
                    "to_table": nb, "to_column": nb_col, "join_type": "inner"}
            if nb == b:
                return path + [step]
            seen.add(nb)
            q.append((nb, path + [step]))
    return None


# ---------------------------------------------------------------------------
# Action-aware path selection: among all valid entity->target relationship paths,
# prefer the one whose intermediate tables match the ACTION verb in the question
# (purchased -> purchases, fed/ate -> feeding, liked -> likes). Falls back to the
# shortest path on a tie. Generic — action synonym GROUPS, not table names.
# ---------------------------------------------------------------------------
_ACTION_GROUPS = [
    {"purchase", "purchased", "purchases", "buy", "buys", "buying", "bought",
     "order", "orders", "ordered", "transaction", "transactions", "sale", "sales",
     "spend", "spent"},
    {"feed", "fed", "feeding", "feeds", "eat", "eaten", "ate", "consume",
     "consumed", "consumption", "serve", "served", "serving", "history", "log",
     "event"},
    {"like", "liked", "likes", "love", "loved", "prefer", "preferred", "preference",
     "preferences", "profile", "profiles", "favorite", "favourite"},
]


def _stem_eq(a, b):
    a, b = str(a).lower(), str(b).lower()
    if a == b or _singular(a) == _singular(b):
        return True
    return len(a) >= 4 and len(b) >= 4 and a[:4] == b[:4]


def _table_action_score(question, table):
    """Score a single table against the question: action-synonym alignment plus
    direct table-name/word overlap."""
    qwords = set(re.findall(r"[a-z]+", _norm(question)))
    toks = [t for t in re.split(r"[_\s]", str(table).lower()) if len(t) > 2]
    score = 0
    for group in _ACTION_GROUPS:
        table_in = any(_stem_eq(tok, g) for tok in toks for g in group)
        q_in = any(w in group for w in qwords)
        if table_in and q_in:
            score += 3
    for tok in toks:
        if any(_stem_eq(tok, w) for w in qwords):
            score += 1
    return score


def _all_paths(a, b, idx, max_len=4):
    a, b = str(a).lower(), str(b).lower()
    adj = {}
    for r in idx["relationships"]:
        ft, fc = str(r.get("from_table") or "").lower(), str(r.get("from_column") or "").lower()
        tt, tc = str(r.get("to_table") or "").lower(), str(r.get("to_column") or "").lower()
        if not (ft and fc and tt and tc):
            continue
        adj.setdefault(ft, []).append((tt, fc, tc))
        adj.setdefault(tt, []).append((ft, tc, fc))
    results = []

    def dfs(node, path, visited):
        if len(path) > max_len:
            return
        if node == b and path:
            results.append(path)
            return
        for nb, this_col, nb_col in adj.get(node, []):
            if nb in visited:
                continue
            step = {"from_table": node, "from_column": this_col,
                    "to_table": nb, "to_column": nb_col, "join_type": "inner"}
            dfs(nb, path + [step], visited | {nb})

    dfs(a, [], {a})
    return results


def find_action_path(entity, target, question, idx):
    """Best entity->target relationship path for the question's action verb, or
    the plain shortest path if nothing scores. Returns a list of join steps or
    None."""
    if str(entity).lower() == str(target).lower():
        return []
    paths = _all_paths(entity, target, idx)
    if not paths:
        return None

    def _score(path):
        tables = {str(entity).lower()} | {s["to_table"] for s in path}
        return sum(_table_action_score(question, t) for t in tables)

    paths.sort(key=lambda p: (-_score(p), len(p)))
    return paths[0]


# ---------------------------------------------------------------------------
# Join legality against the declared FK graph (used by the guard + builders to
# reject nonsense joins like id = measure or unrelated key = key).
# ---------------------------------------------------------------------------
def is_key(idx, table, col):
    for c in columns_of(idx, str(table).lower()):
        if c["name"] == str(col).lower():
            return c["is_key"]
    return str(col).lower().endswith("_id") or str(col).lower() == "id"


def declared_fk_edges(idx):
    edges = set()
    for r in idx["relationships"]:
        ft, fc = str(r.get("from_table") or "").lower(), str(r.get("from_column") or "").lower()
        tt, tc = str(r.get("to_table") or "").lower(), str(r.get("to_column") or "").lower()
        if ft and fc and tt and tc:
            edges.add((ft, fc, tt, tc))
            edges.add((tt, tc, ft, fc))
    return edges


def is_legal_edge(idx, t1, c1, t2, c2):
    """True when an equality join/correlation between t1.c1 and t2.c2 is
    structurally sound: a self-comparison (same base table), a declared FK edge,
    a same-named key join, or a content (non-key = non-key) comparison. Rejects
    the garbage patterns: key = measure, or unrelated key = key."""
    t1, c1, t2, c2 = (str(t1).lower(), str(c1).lower(), str(t2).lower(), str(c2).lower())
    if t1 == t2:
        return True
    schema = idx["tables"]
    if t1 not in schema or t2 not in schema:   # CTE/alias names — not our concern here
        return True
    if (t1, c1, t2, c2) in declared_fk_edges(idx):
        return True
    k1, k2 = is_key(idx, t1, c1), is_key(idx, t2, c2)
    if k1 and k2:
        return c1 == c2            # same-named key join ok; unrelated key=key not
    if k1 != k2:
        return False               # key = measure/attribute -> nonsense
    return True                    # both non-key -> content comparison, allowed


# concept nouns (ordered specific->generic) used to identify a COUNT(DISTINCT)
# target from a phrase, without matching entity names like 'owner'.
_CONCEPT_NOUNS = ("brand", "flavor", "flavour", "species", "severity", "course",
                  "alert", "specialty", "category", "class", "type", "kind")


def _side_concept_col(text, idx):
    """A non-key categorical column implied by a concept noun in `text`."""
    q = _norm(text)
    for noun in _CONCEPT_NOUNS:
        if _contains_word(q, noun) or (noun + " ") in q or (noun + "s ") in q:
            for t in idx["tables"]:
                for c in columns_of(idx, t):
                    if c["is_key"] or c["is_numeric"] or c["is_date"]:
                        continue
                    if noun in c["name"]:
                        return (t, c["name"])
    return None


def two_concept_columns(question, idx):
    """For 'more/fewer distinct A than B', return (colA, colB) from the concept
    noun on each side of 'than' (each (table,column) or None). Same concept on
    both sides (e.g. brands via two paths) yields equal cols, not a mismatch."""
    import re as _re
    q = _norm(question)
    m = _re.search(r"\bthan\b", q)
    if not m:
        return (None, None)
    return (_side_concept_col(q[:m.start()], idx), _side_concept_col(q[m.end():], idx))


def bridge_table(a, b, idx):
    """A single table B that links tables `a` and `b` via FKs to both (a common
    junction), or None. Used to attribute an action (purchase/feed) to an entity."""
    a, b = str(a).lower(), str(b).lower()
    neigh_a, neigh_b = set(), set()
    for r in idx["relationships"]:
        ft, tt = str(r.get("from_table") or "").lower(), str(r.get("to_table") or "").lower()
        if ft == a:
            neigh_a.add(tt)
        if tt == a:
            neigh_a.add(ft)
        if ft == b:
            neigh_b.add(tt)
        if tt == b:
            neigh_b.add(ft)
    common = (neigh_a & neigh_b) - {a, b}
    return sorted(common)[0] if common else None


def neighbors(table, idx):
    """Map neighbor_table -> (col_on_neighbor, col_on_table) for one-hop FKs."""
    table = str(table).lower()
    out = {}
    for r in idx["relationships"]:
        ft, fc = str(r.get("from_table") or "").lower(), str(r.get("from_column") or "").lower()
        tt, tc = str(r.get("to_table") or "").lower(), str(r.get("to_column") or "").lower()
        if ft == table and tt:
            out.setdefault(tt, (tc, fc))
        if tt == table and ft:
            out.setdefault(ft, (fc, tc))
    return out


def name_column(idx, table):
    """A descriptive '<...>name' column, if any."""
    for c in columns_of(idx, table):
        if "name" in c["name"] and not c["is_key"]:
            return c["name"]
    return None


def subject_noun(question):
    """The grouped/subject noun after a lead verb ('find brands ...' -> brands)."""
    q = _norm(question)
    for cue in ("find ", "list ", "which ", "identify ", "show ", "get ", "return ", "count "):
        w = _word_after(q, cue)
        if w:
            return w
    return None


def find_comparable_pair(question, idx, tables):
    """Two categorical columns on DIFFERENT tables that share a name token which
    also appears in the question (e.g. foods.species_target vs pets.species).
    Returns ((t1,c1),(t2,c2)) with the longer/derived column name first, or None."""
    q = _norm(question)
    by_token = {}
    for t in tables:
        for c in columns_of(idx, t):
            if c["is_key"] or c["is_numeric"] or c["is_date"]:
                continue
            for tok in c["name"].split("_"):
                if len(tok) > 3 and _contains_word(q, tok):
                    by_token.setdefault(tok, {}).setdefault(t, c["name"])
    for tok, tmap in by_token.items():
        if len(tmap) >= 2:
            items = sorted(tmap.items(), key=lambda kv: -len(kv[1]))
            (t1, c1), (t2, c2) = items[0], items[1]
            return (t1, c1), (t2, c2)
    return None


def find_date_record_table(entity_table, question, idx):
    """A one-hop table off `entity_table` that carries a date column (the record
    stream). Returns (record_table, fk_to_entity, date_col) or None. Prefers a
    table whose name appears in the question."""
    q = _norm(question)
    best = None
    for nb, (nb_col, _ent_col) in neighbors(entity_table, idx).items():
        dcols = date_columns(idx, nb)
        if not dcols:
            continue
        score = 1 if any(_contains_word(q, f) for f in _forms(nb)) else 0
        if best is None or score > best[0]:
            best = (score, nb, nb_col, dcols[0])
    return (best[1], best[2], best[3]) if best else None


def find_action_table(subject, question, idx):
    """A one-hop neighbor of `subject` that stands for the action/relationship in
    an absence check (e.g. subject=foods, verb 'purchased' -> purchases). Prefers
    a neighbor whose name shares a 5+ char prefix with a question word (so
    'purchased' matches 'purchases'); else uses the single neighbor. Returns
    (action_table, fk_col_on_action, key_col_on_subject) or None when ambiguous /
    unrelated. No hardcoded names."""
    if not subject:
        return None
    q = _norm(question)
    words = [w for w in re.findall(r"[a-z]+", q) if len(w) >= 4]
    neigh = neighbors(subject, idx)
    if not neigh:
        return None
    for nb, (nb_col, subj_col) in neigh.items():
        forms = _forms(nb)
        for form in forms:
            if len(form) < 5:
                continue
            for w in words:
                if len(w) >= 5 and form[:5] == w[:5]:
                    return (nb, nb_col, subj_col)
                if _singular(w) == _singular(form):
                    return (nb, nb_col, subj_col)
    if len(neigh) == 1:
        nb, (nb_col, subj_col) = next(iter(neigh.items()))
        return (nb, nb_col, subj_col)
    return None


# end of slot_extractor
