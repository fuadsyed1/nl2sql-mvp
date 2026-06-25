"""
assignment_parser.py

Mode B / Mode C - parse assignment text (from an uploaded document or pasted
into the input bar) into a structured schema-only spec.

This module is pure text -> structure. It performs NO database access, imports
nothing from the app, generates no SQL, and inserts no data. Its single job is
to turn assignment text such as

    Pets(PetID, Name, Age, Street#, City, ZipCode, State, TypeofPet)
    Owners(OID, LastName, Street#, City, ZipCode, State, Age, AnnualIncome)
    Owns(PetID, Year, OID, PetAgeatOwnership, PricePaid)

    Write SQL for:
    1. List all cats aged at least 2 and live in Idaho except Moscow.
    2. List all owners and their pets who own at least two pets.

into:

    {
      "tables": [{"name": "Pets", "columns": [...]}, ...],
      "relationships": [
        {"from_table": "Owns", "from_column": "PetID",
         "to_table": "Pets", "to_column": "PetID"}, ...
      ],
      "questions": ["List all cats ...", "List all owners ..."],
    }

Relationships are taken from explicit hints in the text when present
(``Owns.PetID -> Pets.PetID`` / ``references``) and otherwise inferred by key
naming, which mirrors the CSV-data relationship detector's *name* signal so the
empty-schema graph matches the data-backed one for the same tables.
"""

import re

__all__ = ["extract_assignment_spec", "looks_like_assignment"]


# ---------------------------------------------------------------------------
# Small name helpers (mirror the spirit of relationship_detector / csv loader)
# ---------------------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _singular(s: str) -> str:
    if s.endswith("ies") and len(s) > 3:
        return s[:-3] + "y"
    if s.endswith("s") and not s.endswith("ss") and len(s) > 1:
        return s[:-1]
    return s


def _clean_col_token(tok: str) -> str:
    """Strip decoration from a column token: trailing '#', PK markers like
    '*' or surrounding '_', and whitespace. Keeps the readable original case."""
    tok = tok.strip()
    tok = tok.strip("*")            # '*PetID' primary-key marker
    tok = tok.rstrip("#")           # 'Street#' -> 'Street'
    tok = tok.strip()
    # An underscore-wrapped token (_PetID_) sometimes marks a key; unwrap it
    # only when it wraps the whole token, never touching internal underscores.
    if len(tok) > 2 and tok.startswith("_") and tok.endswith("_"):
        tok = tok[1:-1].strip()
    return tok


# ---------------------------------------------------------------------------
# Region split: schema (table defs) vs. questions (numbered list)
# ---------------------------------------------------------------------------
_QUESTION_LINE = re.compile(r"^\s*(\d+)\s*[.)]\s+(.*\S)\s*$")
_DIRECTIVE = re.compile(
    r"write\s+(the\s+following\s+)?(sql|quer(y|ies))|generate\s+sql",
    re.IGNORECASE,
)
# A table definition occupying a whole line: Name( ... ).
_TABLE_DEF = re.compile(r"^\s*([A-Za-z_]\w*)\s*\(\s*(.+?)\s*\)\s*$")


def _split_regions(lines):
    """Return (schema_lines, question_region_start_index).

    The question region begins at the first numbered item or the first
    directive line ('Write SQL for:'). Everything before it is schema text,
    which keeps function calls like COUNT(petid) inside questions from being
    mistaken for table definitions.
    """
    start = len(lines)
    for i, ln in enumerate(lines):
        if _QUESTION_LINE.match(ln) or _DIRECTIVE.search(ln):
            start = i
            break
    return lines[:start], start


# ---------------------------------------------------------------------------
# Table definitions
# ---------------------------------------------------------------------------
def _parse_tables(schema_lines):
    tables = []
    for ln in schema_lines:
        m = _TABLE_DEF.match(ln)
        if not m:
            continue
        name = m.group(1).strip()
        cols = [_clean_col_token(c) for c in m.group(2).split(",")]
        cols = [c for c in cols if c]
        if cols:
            tables.append({"name": name, "columns": cols})
    return tables


# ---------------------------------------------------------------------------
# Relationships - explicit hints first, then key-name inference
# ---------------------------------------------------------------------------
_EXPLICIT = re.compile(
    r"([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)\s*"
    r"(?:->|→|references|refs|=>)\s*"
    r"([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)",
    re.IGNORECASE,
)


def _parse_explicit_relationships(text, tables):
    by_norm = {_norm(t["name"]): t for t in tables}
    out = []
    for ft, fc, tt, tc in _EXPLICIT.findall(text):
        a, b = by_norm.get(_norm(ft)), by_norm.get(_norm(tt))
        if not a or not b:
            continue
        out.append({
            "from_table": a["name"], "from_column": fc,
            "to_table": b["name"], "to_column": tc,
        })
    return out


def _col_lookup(table, col_norm):
    for c in table["columns"]:
        if _norm(c) == col_norm:
            return c
    return None


def _infer_relationships(tables):
    """Infer foreign keys from key naming, no data required.

    Home of a key column:
      1. name-match home  - a table U with norm(U)+id or singular(U)+id == col
         (resolves PetID->Pets, FoodID->Foods unambiguously, even when the
         column also sits first in a junction table like Owns).
      2. first-column home - the table where the column is the first column,
         used only when no name-match home exists (resolves OID->Owners, whose
         abbreviation no name rule would catch).
    Only 'keyish' columns (normalized name ending in 'id') are linked.
    """
    # 1) name-match homes
    name_home = {}
    for t in tables:
        nt, nts = _norm(t["name"]), _singular(_norm(t["name"]))
        for cand in {nt + "id", nts + "id"}:
            if _col_lookup(t, cand):
                name_home.setdefault(cand, set()).add(t["name"])
    name_home = {k: next(iter(v)) for k, v in name_home.items() if len(v) == 1}

    # 2) first-column homes (only for keys with no name-match home). When more
    # than one table opens with the same id column (e.g. OID heads both Owners
    # and the Purchases fact table), prefer the most entity-like table: the one
    # with the fewest id-like columns. An entity table has a single PK; a
    # junction/fact table carries several foreign keys.
    def _idlike_count(t):
        return sum(1 for c in t["columns"] if _norm(c).endswith("id"))

    first_candidates = {}
    for idx, t in enumerate(tables):
        if not t["columns"]:
            continue
        first = _norm(t["columns"][0])
        if first.endswith("id") and first not in name_home:
            first_candidates.setdefault(first, []).append(
                (_idlike_count(t), idx, t["name"])
            )
    first_home = {
        k: sorted(cands)[0][2] for k, cands in first_candidates.items()
    }

    def home_of(col_norm):
        if col_norm in name_home:
            return name_home[col_norm]
        return first_home.get(col_norm)

    by_name = {t["name"]: t for t in tables}
    edges = []
    for t in tables:
        for col in t["columns"]:
            cn = _norm(col)
            if not cn.endswith("id"):
                continue
            home = home_of(cn)
            if not home or home == t["name"]:
                continue
            to_col = _col_lookup(by_name[home], cn)
            if not to_col:
                continue
            edges.append({
                "from_table": t["name"], "from_column": col,
                "to_table": home, "to_column": to_col,
            })
    return edges


def _dedupe_relationships(rels):
    seen = set()
    out = []
    for r in rels:
        key = (
            _norm(r["from_table"]), _norm(r["from_column"]),
            _norm(r["to_table"]), _norm(r["to_column"]),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------
def _parse_questions(lines, start):
    questions = []
    current = None
    for ln in lines[start:]:
        m = _QUESTION_LINE.match(ln)
        if m:
            if current is not None:
                questions.append(current.strip())
            current = m.group(2)
        elif current is not None:
            s = ln.strip()
            # blank line or a new directive ends the current question
            if not s or _DIRECTIVE.search(s) or _TABLE_DEF.match(ln):
                questions.append(current.strip())
                current = None
            else:
                current += " " + s
    if current is not None:
        questions.append(current.strip())
    return [q for q in questions if q]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def extract_assignment_spec(text: str) -> dict:
    """Parse assignment text into {tables, relationships, questions}."""
    text = text or ""
    lines = text.splitlines()

    schema_lines, q_start = _split_regions(lines)
    tables = _parse_tables(schema_lines)

    explicit = _parse_explicit_relationships(text, tables)
    inferred = _infer_relationships(tables)
    relationships = _dedupe_relationships(explicit + inferred)

    questions = _parse_questions(lines, q_start)

    return {
        "tables": tables,
        "relationships": relationships,
        "questions": questions,
    }


def looks_like_assignment(text: str) -> bool:
    """Heuristic for routing input-bar text to the assignment parser instead of
    the normal single-question NL-to-SQL path.

    True when the text contains multiple table definitions, multiple numbered
    queries, or an explicit 'Write SQL'/'Generate SQL' directive.
    """
    text = text or ""
    lines = text.splitlines()

    table_defs = sum(1 for ln in lines if _TABLE_DEF.match(ln))
    numbered = sum(1 for ln in lines if _QUESTION_LINE.match(ln))
    directive = bool(_DIRECTIVE.search(text))

    return table_defs >= 2 or numbered >= 2 or directive
