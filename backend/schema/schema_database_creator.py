"""
schema_database_creator.py

Deterministic creation of an EMPTY SQLite database from SQL DDL text. Only
CREATE TABLE statements are allowed; every other statement type (DROP, DELETE,
UPDATE, INSERT, ALTER, ATTACH, PRAGMA, TRIGGER, VIEW, CREATE TABLE ... AS
SELECT, etc.) is rejected. No rows are inserted and no LLM is involved.

The caller is responsible for the database record / metadata; this module only
parses + validates the DDL and executes the CREATE TABLE statements into a
fresh SQLite file, returning the created table names.
"""

import os
import re
import sqlite3

__all__ = [
    "create_empty_db_from_ddl",
    "parse_and_validate_ddl",
    "extract_declared_foreign_keys",
    "infer_schema_name_relationships",
    "SchemaDDLError",
]


class SchemaDDLError(Exception):
    """Raised when the supplied schema text is empty, malformed, or contains a
    statement that is not an allowed CREATE TABLE."""


def _strip_comments(text: str) -> str:
    text = re.sub(r"--[^\n]*", " ", text)          # -- line comments
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)  # /* block */
    return text


def split_statements(text: str):
    """Split on semicolons that are not inside parentheses or quotes."""
    stmts, buf = [], []
    depth = 0
    quote = None
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            buf.append(ch)
            continue
        if ch == "(":
            depth += 1
            buf.append(ch)
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
            continue
        if ch == ";" and depth == 0:
            s = "".join(buf).strip()
            if s:
                stmts.append(s)
            buf = []
            continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


_CREATE_TABLE = re.compile(
    r"^CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?([A-Za-z_]\w*)[`\"\]]?\s*\(",
    re.IGNORECASE,
)
_CTAS = re.compile(r"\bAS\b\s+SELECT\b", re.IGNORECASE)


def parse_and_validate_ddl(schema_text: str):
    """Return [(table_name, statement), ...] for valid CREATE TABLE statements,
    or raise SchemaDDLError. Any non-CREATE-TABLE statement is rejected, which
    inherently blocks DROP/DELETE/UPDATE/INSERT/ALTER/ATTACH/PRAGMA/TRIGGER/
    VIEW and multiple dangerous statements (each is split out and checked)."""
    if not schema_text or not schema_text.strip():
        raise SchemaDDLError("Schema text is empty.")

    statements = split_statements(_strip_comments(schema_text))
    if not statements:
        raise SchemaDDLError("No SQL statements found.")

    result = []
    for stmt in statements:
        m = _CREATE_TABLE.match(stmt)
        if not m:
            raise SchemaDDLError(
                "Only CREATE TABLE statements are allowed. Rejected: "
                f"{stmt[:60].strip()}…"
            )
        if _CTAS.search(stmt):
            raise SchemaDDLError("CREATE TABLE ... AS SELECT is not allowed.")
        result.append((m.group(1), stmt))

    if not result:
        raise SchemaDDLError("No CREATE TABLE statements found.")
    return result


def create_empty_db_from_ddl(schema_text: str, db_path: str):
    """Validate DDL and execute the CREATE TABLE statements into a fresh SQLite
    file inside a single transaction. Inserts no rows. Returns the ordered list
    of created table names (read back from sqlite_master)."""
    tables = parse_and_validate_ddl(schema_text)

    # Start from a guaranteed-fresh file. A new database_id can map onto a
    # leftover db_<id>/data.db from a previous session (e.g. after the metadata
    # DB was reset and the id counter restarted); reusing it would inherit
    # unrelated tables and rows. Remove any existing file so the schema database
    # contains ONLY the tables defined here, with no rows.
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("BEGIN")
        for _name, stmt in tables:
            cur.execute(stmt)  # single statement only (not executescript)
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        raise SchemaDDLError(f"Failed to create tables: {e}")
    finally:
        conn.close()

    conn = sqlite3.connect(db_path)
    try:
        names = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
            ).fetchall()
        ]
    finally:
        conn.close()
    return names


# ---------------------------------------------------------------------------
# Schema-only relationship detection (deterministic, no rows required)
# ---------------------------------------------------------------------------

_FK_TABLE = re.compile(
    r"FOREIGN\s+KEY\s*\(\s*([A-Za-z_]\w*)\s*\)\s*REFERENCES\s+"
    r"[`\"\[]?([A-Za-z_]\w*)[`\"\]]?\s*\(\s*([A-Za-z_]\w*)\s*\)",
    re.IGNORECASE,
)
_INLINE_REF = re.compile(
    r"REFERENCES\s+[`\"\[]?([A-Za-z_]\w*)[`\"\]]?\s*\(\s*([A-Za-z_]\w*)\s*\)",
    re.IGNORECASE,
)
_CONSTRAINT_KW = {"primary", "foreign", "unique", "check", "constraint", "key"}


def _table_body(stmt: str) -> str:
    i = stmt.find("(")
    j = stmt.rfind(")")
    if i == -1 or j == -1 or j <= i:
        return ""
    return stmt[i + 1 : j]


def _split_top_level(body: str):
    """Split a CREATE TABLE body into column/constraint defs on top-level commas."""
    parts, buf, depth = [], [], 0
    for ch in body:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == "," and depth == 0:
            s = "".join(buf).strip()
            if s:
                parts.append(s)
            buf = []
        else:
            buf.append(ch)
    s = "".join(buf).strip()
    if s:
        parts.append(s)
    return parts


def _fk_edge(ft, fc, tt, tc):
    return {
        "from_table": ft, "from_column": fc,
        "to_table": tt, "to_column": tc,
        "relationship_type": "foreign_key",
        "name_similarity": 1.0, "value_overlap": None,
        "confidence": 1.0, "confirmed": True,
    }


def extract_declared_foreign_keys(schema_text: str):
    """Return relationship edges for explicit FOREIGN KEY constraints (both
    table-level `FOREIGN KEY (c) REFERENCES t(c)` and inline column
    `c TYPE REFERENCES t(c)`). Deterministic; no rows needed."""
    edges, seen = [], set()
    for table_name, stmt in parse_and_validate_ddl(schema_text):
        body = _table_body(stmt)

        for m in _FK_TABLE.finditer(body):
            from_col, to_table, to_col = m.group(1), m.group(2), m.group(3)
            key = (table_name, from_col, to_table, to_col)
            if key not in seen:
                seen.add(key)
                edges.append(_fk_edge(table_name, from_col, to_table, to_col))

        for part in _split_top_level(body):
            tokens = part.split()
            first = tokens[0].strip('`"[]') if tokens else ""
            if not first or first.lower() in _CONSTRAINT_KW:
                continue
            m = _INLINE_REF.search(part)
            if not m:
                continue
            from_col, to_table, to_col = first, m.group(1), m.group(2)
            key = (table_name, from_col, to_table, to_col)
            if key not in seen:
                seen.add(key)
                edges.append(_fk_edge(table_name, from_col, to_table, to_col))

    return edges


def _table_columns(db_path: str):
    conn = sqlite3.connect(db_path)
    out = {}
    try:
        names = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        for t in names:
            qt = '"' + t.replace('"', '""') + '"'
            out[t] = [r[1] for r in conn.execute(f"PRAGMA table_info({qt})").fetchall()]
    finally:
        conn.close()
    return out


def _table_matches_base(table: str, base: str) -> bool:
    """Simple singular/plural match: base 'student' matches table 'students'."""
    t, b = table.lower(), base.lower()
    cands = {b, b + "s", b + "es"}
    if b.endswith("y"):
        cands.add(b[:-1] + "ies")
    if t in cands:
        return True
    if t.endswith("es") and t[:-2] == b:
        return True
    if t.endswith("s") and t[:-1] == b:
        return True
    return False


def infer_schema_name_relationships(db_path: str, table_names=None):
    """Conservative name-based fallback for empty schema tables: a column named
    `<base>_id` is linked to a table matching `<base>` (singular/plural) that has
    a column of the same name. No self-relationships. Deterministic."""
    cols_by_table = _table_columns(db_path)
    edges, seen = [], set()
    for table, cols in cols_by_table.items():
        for col in cols:
            lc = col.lower()
            if not lc.endswith("_id"):
                continue
            base = lc[:-3]
            if not base:
                continue
            for target, tcols in cols_by_table.items():
                if target == table:
                    continue  # no self-relationships
                if not _table_matches_base(target, base):
                    continue
                if col not in tcols:
                    continue  # prefer exact column-name match
                key = (table, col, target, col)
                if key in seen:
                    continue
                seen.add(key)
                edges.append({
                    "from_table": table, "from_column": col,
                    "to_table": target, "to_column": col,
                    "relationship_type": "suggested_foreign_key",
                    "name_similarity": 1.0, "value_overlap": None,
                    "confidence": 0.8, "confirmed": False,
                })
    return edges
