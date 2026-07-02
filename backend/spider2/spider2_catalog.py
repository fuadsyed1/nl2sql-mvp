"""
spider2_catalog.py

Real-source-aware "Load from Spider 2.0" catalog.

Spider 2.0 (https://spider2-sql.github.io/, https://github.com/xlang-ai/Spider2)
ships task files (spider2-lite.jsonl / spider2-snow.jsonl) whose records carry an
``instance_id``, a ``db`` id, and a ``question`` — but NO inline schema. The
schema for each ``db`` lives locally under:

    <repo>/**/resource/databases/<dialect>/<db>/**/DDL.csv   (table_name, ddl)

This module reads those real files (no cloud, no network, no LLM): it indexes the
DDL.csv schemas, joins each task to its db's tables/columns, and marks an entry
``importable`` only when real schema was found. Importing builds an EMPTY SQLite
workspace from that schema (no rows). BigQuery/Snowflake dialects only affect
where the real *data* lives; the *schema* is local, so empty-schema import works.

Hardcoded dev samples are returned solely when ``include_samples=True``.
"""

import os
import re
import csv
import json
import glob

# Some Spider 2.0 DDL.csv rows contain very large DDL strings (wide BigQuery
# tables / nested STRUCTs) that exceed Python's default CSV field limit.
try:
    csv.field_size_limit(16 * 1024 * 1024)
except OverflowError:  # pragma: no cover - platform-dependent
    csv.field_size_limit(2**31 - 1)

__all__ = [
    "spider2_status",
    "list_catalog",
    "get_catalog_entry",
    "entry_is_importable",
    "entry_to_ddl",
    "entry_relationship_edges",
    "entry_inferred_edges",
]

# --- limits -----------------------------------------------------------------
_SCAN_MAX_FILES = 200
_MAX_ENTRIES = 800
_MAX_TABLES_PER_DB = 200
_DIALECTS = {"bigquery", "snowflake", "sqlite"}
_TASK_FILE_NAMES = ("spider2-lite.jsonl", "spider2-snow.jsonl")
_CONSTRAINT_KW = {"primary", "foreign", "unique", "check", "constraint", "key",
                  "partition", "cluster"}

_LOCAL_DEV_FALLBACK = r"C:\Datasets\Spider2"

# Dev-only samples (never returned unless include_samples=True).
SAMPLE_CATALOG = [
    {
        "spider2_id": "spider2_sample_university",
        "name": "Spider2 Sample University",
        "domain": "education",
        "description": "Developer sample only (not real Spider 2.0 data).",
        "source_type": "dev_sample",
        "availability": "LOCAL_SCHEMA_IMPORTABLE",
        "tables": [
            {"table_name": "students", "columns": [
                {"column_name": "student_id", "data_type": "INTEGER", "primary_key": True},
                {"column_name": "student_name", "data_type": "TEXT"},
                {"column_name": "department_id", "data_type": "INTEGER"}]},
            {"table_name": "departments", "columns": [
                {"column_name": "department_id", "data_type": "INTEGER", "primary_key": True},
                {"column_name": "department_name", "data_type": "TEXT"}]},
        ],
        "relationships": [
            {"from_table": "students", "from_column": "department_id",
             "to_table": "departments", "to_column": "department_id"},
        ],
    },
]


# ---------------------------------------------------------------------------
# Source configuration / detection
# ---------------------------------------------------------------------------
def _normalize(raw):
    if not raw:
        return ""
    s = str(raw).strip().strip('"').strip("'").strip()
    if not s:
        return ""
    s = os.path.expandvars(os.path.expanduser(s))
    try:
        return os.path.abspath(s)
    except (OSError, ValueError):
        return s


def _resolve_source():
    norm = _normalize(os.getenv("SPIDER2_DATA_DIR"))
    if norm and os.path.isdir(norm):
        return norm, "SPIDER2_DATA_DIR"
    fb = _normalize(_LOCAL_DEV_FALLBACK)
    if fb and os.path.isdir(fb):
        return fb, "local_dev_fallback"
    return None, None


def _data_dir():
    path, _ = _resolve_source()
    return path


def _detected_files(root):
    out, count = [], 0
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.lower().endswith((".json", ".jsonl", ".csv")):
                out.append(os.path.relpath(os.path.join(dirpath, f), root))
                count += 1
                if count >= _SCAN_MAX_FILES:
                    return out
    return out


def spider2_status():
    raw = os.getenv("SPIDER2_DATA_DIR")
    norm = _normalize(raw)
    path, configured_by = _resolve_source()
    configured = path is not None
    effective = path or norm
    print(
        f"[spider2/status] raw={raw!r} normalized={norm!r} "
        f"exists={os.path.exists(effective) if effective else False} "
        f"isdir={os.path.isdir(effective) if effective else False} "
        f"configured={configured} by={configured_by}"
    )
    status = {
        "configured": configured,
        "env_value": raw,
        "normalized_path": norm or None,
        "resolved_path": path,
        "path_exists": os.path.exists(effective) if effective else False,
        "is_dir": os.path.isdir(effective) if effective else False,
    }
    if configured:
        status["source"] = {
            "type": "local_repo",
            "path": path,
            "configured_by": configured_by,
            "detected_files": _detected_files(path),
        }
        status["message"] = f"Spider 2.0 local data source configured at {path}."
    else:
        status["source"] = None
        status["message"] = "Spider 2.0 local data source is not configured."
        status["expected_sources"] = [
            "local Spider2 repository clone",
            "downloaded Spider2-Lite metadata files",
            "future BigQuery/Snowflake connection",
        ]
    return status


# ---------------------------------------------------------------------------
# DDL parsing (BigQuery / Snowflake / SQLite dialects -> SQLite affinity)
# ---------------------------------------------------------------------------
def _map_type(t):
    t = (t or "").strip().lower()
    if re.match(r"^(int|integer|bigint|smallint|tinyint|int64)\b", t):
        return "INTEGER"
    if re.match(r"^(float|double|real|numeric|decimal|number|float64)\b", t):
        return "REAL"
    return "TEXT"


def _split_top_level(body):
    """Split a CREATE TABLE body on top-level commas, respecting () and <>."""
    parts, buf, depth = [], [], 0
    for ch in body:
        if ch in "(<":
            depth += 1
            buf.append(ch)
        elif ch in ")>":
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


def _parse_columns(ddl):
    i = ddl.find("(")
    j = ddl.rfind(")")
    if i < 0 or j <= i:
        return []
    cols = []
    for part in _split_top_level(ddl[i + 1:j]):
        toks = part.strip().split()
        if not toks:
            continue
        first = toks[0].strip('`"[]')
        if not first or first.lower() in _CONSTRAINT_KW:
            continue
        cols.append({
            "column_name": first,
            "data_type": _map_type(toks[1] if len(toks) > 1 else "TEXT"),
            "primary_key": False,
        })
    return cols


def _sanitize_ident(name):
    s = re.sub(r"\W", "_", str(name))
    if not s:
        s = "t"
    if s[0].isdigit():
        s = "t_" + s
    return s


def _is_reserved_table(name):
    """SQLite reserves any object name beginning with 'sqlite_' for internal use
    (e.g. sqlite_stat1, sqlite_sequence). Such tables cannot be created in our
    schema-only import and carry no user-relevant schema, so they are skipped."""
    return str(name or "").strip().lower().startswith("sqlite_")


# ---------------------------------------------------------------------------
# Real declared foreign-key parsing (constraint syntax only — NOT description
# prose). Quoted string literals (e.g. BigQuery OPTIONS(description="Foreign key
# to ...")) are blanked first so documentation text is never mistaken for a
# constraint. Returns edges; table names are sanitized to match how tables are
# registered, column names are kept as written (quote-stripped).
# ---------------------------------------------------------------------------
_STRING_LITERAL_RE = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"", re.S)
_FK_CONSTRAINT_RE = re.compile(
    r"FOREIGN\s+KEY\s*\(\s*([^)]+?)\s*\)\s*REFERENCES\s+"
    r"([`\"\[\]\w.]+)\s*(?:\(\s*([^)]+?)\s*\))?",
    re.I,
)
_INLINE_REF_RE = re.compile(
    r"REFERENCES\s+([`\"\[\]\w.]+)\s*(?:\(\s*([^)]+?)\s*\))?", re.I
)


def _strip_string_literals(text):
    return _STRING_LITERAL_RE.sub("''", text or "")


def _clean_ident(name):
    """Strip quoting/backticks; keep only the final dotted segment (drop db/schema
    qualifier)."""
    s = str(name or "").strip().strip('`"[]').strip()
    if "." in s:
        s = s.split(".")[-1].strip().strip('`"[]')
    return s


def _split_idents(s):
    return [_clean_ident(p) for p in str(s or "").split(",") if _clean_ident(p)]


def _parse_fk_edges(table_name, ddl):
    """Return real declared FK edges for one CREATE TABLE. Handles table-level
    `FOREIGN KEY (a) REFERENCES t (b)` and inline `col ... REFERENCES t (b)`.
    Description prose is excluded because string literals are stripped first."""
    clean = _strip_string_literals(ddl or "")
    src = _sanitize_ident(table_name)
    edges = []

    for m in _FK_CONSTRAINT_RE.finditer(clean):
        from_cols = _split_idents(m.group(1))
        ref_table = _sanitize_ident(_clean_ident(m.group(2)))
        to_cols = _split_idents(m.group(3)) if m.group(3) else from_cols
        if not from_cols or not ref_table:
            continue
        for i, fc in enumerate(from_cols):
            tc = to_cols[i] if i < len(to_cols) else (to_cols[-1] if to_cols else fc)
            edges.append({"from_table": src, "from_column": fc,
                          "to_table": ref_table, "to_column": tc})

    i, j = clean.find("("), clean.rfind(")")
    if i >= 0 and j > i:
        for seg in _split_top_level(clean[i + 1:j]):
            toks = seg.strip().split()
            if not toks:
                continue
            first = toks[0].strip('`"[]')
            if not first or first.lower() in _CONSTRAINT_KW:
                continue  # table-level constraints already handled above
            m = _INLINE_REF_RE.search(seg)
            if not m:
                continue
            ref_table = _sanitize_ident(_clean_ident(m.group(1)))
            to_col = _split_idents(m.group(2))[0] if m.group(2) else first
            if ref_table:
                edges.append({"from_table": src, "from_column": first,
                              "to_table": ref_table, "to_column": to_col})
    return edges


def _parse_ddl_csv(path):
    tables = []
    try:
        with open(path, encoding="utf-8", errors="replace", newline="") as fh:
            for row in csv.DictReader(fh):
                low = {(k or "").lower(): v for k, v in row.items()}
                tn = low.get("table_name")
                ddl = low.get("ddl")
                if not tn or not ddl:
                    continue
                cols = _parse_columns(ddl)
                if cols:
                    tables.append({"table_name": tn, "columns": cols,
                                   "fk_edges": _parse_fk_edges(tn, ddl)})
    except (OSError, UnicodeError, csv.Error):
        return []
    return tables


# ---------------------------------------------------------------------------
# Catalog build (cached per root)
# ---------------------------------------------------------------------------
_CATALOG_CACHE = {"root": None, "entries": None, "index": None}


def _build_schema_index(root):
    """Map db name (lowercased) -> {db, dialect, dirs:set(dataset folders)}.

    Uses bounded (non-recursive) globs for speed: a db's DDL.csv sits either one
    or two levels under the dialect folder. Each dataset folder also contains a
    per-table <table>.json, so table names come from cheap directory listings.
    """
    idx = {}
    patterns = [
        os.path.join(root, "*", "resource", "databases", "*", "*", "DDL.csv"),
        os.path.join(root, "*", "resource", "databases", "*", "*", "*", "DDL.csv"),
    ]
    for pat in patterns:
        for ddl in glob.glob(pat):
            parts = ddl.replace("\\", "/").split("/")
            for i, p in enumerate(parts):
                if p in _DIALECTS and i > 0 and parts[i - 1] == "databases":
                    if i + 1 < len(parts):
                        db = parts[i + 1]
                        e = idx.setdefault(
                            db.lower(), {"db": db, "dialect": p, "dirs": set()}
                        )
                        e["dirs"].add(os.path.dirname(ddl))
                    break
    return idx


def _dedup_sanitize(names):
    out, seen = [], set()
    for raw in names:
        name = _sanitize_ident(raw)
        base, n = name, 2
        while name in seen:
            name = f"{base}_{n}"
            n += 1
        seen.add(name)
        out.append(name)
        if len(out) >= _MAX_TABLES_PER_DB:
            break
    return out


def _db_table_names(index, db, cache):
    """Cheap: dialect + sanitized table names from per-table <table>.json
    filenames in the db's dataset folders (no file reads)."""
    key = (db or "").lower()
    if not key or key not in index:
        return None
    if key in cache:
        return cache[key]
    info = index[key]
    raw = []
    for d in info["dirs"]:
        for jf in glob.glob(os.path.join(d, "*.json")):
            name = os.path.splitext(os.path.basename(jf))[0]
            if _is_reserved_table(name):  # skip SQLite-reserved internal tables
                continue
            raw.append(name)
        if len(raw) >= _MAX_TABLES_PER_DB:
            break
    result = {"dialect": info["dialect"], "table_names": _dedup_sanitize(raw)}
    cache[key] = result
    return result


def _db_full_schema(index, db):
    """Heavy: dialect + tables with parsed columns (from DDL.csv). Import only."""
    key = (db or "").lower()
    if not key or key not in index:
        return None
    info = index[key]
    tables, seen, relationships = [], set(), []
    skipped_reserved = 0
    for d in info["dirs"]:
        for t in _parse_ddl_csv(os.path.join(d, "DDL.csv")):
            if _is_reserved_table(t["table_name"]):
                # SQLite-reserved internal table (sqlite_*) — cannot be created
                # in our schema-only import; skip it.
                skipped_reserved += 1
                continue
            name = _sanitize_ident(t["table_name"])
            base, n = name, 2
            while name in seen:
                name = f"{base}_{n}"
                n += 1
            seen.add(name)
            tables.append({"table_name": name, "columns": t["columns"]})
            relationships.extend(t.get("fk_edges") or [])
            if len(tables) >= _MAX_TABLES_PER_DB:
                break
        if len(tables) >= _MAX_TABLES_PER_DB:
            break
    # Keep only real declared FK edges whose endpoints are both registered tables.
    present = {tb["table_name"] for tb in tables}
    relationships = [
        e for e in relationships
        if e["from_table"] in present and e["to_table"] in present
    ]
    return {"dialect": info["dialect"], "tables": tables,
            "skipped_reserved": skipped_reserved,
            "relationships": relationships}


# ---------------------------------------------------------------------------
# Relationship-signal classification (lightweight; mirrors the diagnostic tool).
# Used to filter the catalog to schemas useful for complex SQL generation.
# ---------------------------------------------------------------------------
_PARTITION_RE = re.compile(r"^(.*)_(\d{6,8})$")        # <prefix>_YYYYMM(DD)
_FK_RE = re.compile(r"\bFOREIGN\s+KEY\b", re.IGNORECASE)
_CLASS_CONSTRAINT_KW = {"primary", "foreign", "unique", "check", "constraint",
                        "key", "partition", "cluster"}
_COLBODY_CAP = 50000  # cap column-body chars parsed per table (bounds STRUCTs)
_SUPPORTED_CLASSES = ("declared_fk_schema", "inferable_join_schema")


def _ddl_rows(dirs):
    rows = []
    for d in dirs:
        path = os.path.join(d, "DDL.csv")
        try:
            with open(path, encoding="utf-8", errors="replace", newline="") as fh:
                for row in csv.DictReader(fh):
                    low = {(k or "").lower(): v for k, v in row.items()}
                    tn = low.get("table_name")
                    if tn:
                        rows.append((tn, low.get("ddl") or ""))
        except (OSError, csv.Error, UnicodeError):
            continue
    return rows


def _column_names_only(ddl):
    """Cheap, bounded column-name extraction (names only)."""
    i = ddl.find("(")
    j = ddl.rfind(")")
    if i < 0 or j <= i:
        return []
    body = ddl[i + 1:j][:_COLBODY_CAP]
    names, buf, depth = [], [], 0

    def _flush():
        seg = "".join(buf).strip()
        if not seg:
            return
        toks = seg.split()
        first = toks[0].strip('`"[]') if toks else ""
        if first and first.lower() not in _CLASS_CONSTRAINT_KW:
            names.append(first)

    for ch in body:
        if ch in "(<":
            depth += 1
            buf.append(ch)
        elif ch in ")>":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == "," and depth == 0:
            _flush()
            buf = []
        else:
            buf.append(ch)
    _flush()
    return names


def _classify_db(index, db, cache):
    """Classify a db's join signal from its DDL (cached). Returns a dict with
    classification + counts. Partition families are collapsed to a single
    representative so cost stays bounded."""
    default = {"classification": "messy_or_no_join_signal", "declared_fk_count": 0,
               "inferred_join_candidate_count": 0, "partition_group_count": 0}
    key = (db or "").lower()
    if not key or key not in index:
        return default
    if key in cache:
        return cache[key]

    rows = _ddl_rows(index[key]["dirs"])
    table_count = len(rows)
    if table_count == 0:
        cache[key] = default
        return default

    # Count REAL declared FK constraints only (parsed from constraint syntax),
    # not the substring "FOREIGN KEY" appearing in column-description prose.
    declared_fk = sum(len(_parse_fk_edges(name, ddl)) for name, ddl in rows)

    fam = {}
    for tn, _ddl in rows:
        m = _PARTITION_RE.match(tn)
        if m:
            fam.setdefault(m.group(1), []).append(tn)
    families = {p: ms for p, ms in fam.items() if len(ms) >= 2}
    partition_group_count = len(families)
    partition_table_count = sum(len(ms) for ms in families.values())
    member_prefix = {m: p for p, ms in families.items() for m in ms}

    ddl_by_table = {tn: ddl for tn, ddl in rows}
    reps, seen_fam = [], set()
    for tn, _ddl in rows:
        p = member_prefix.get(tn)
        if p is not None:
            if p in seen_fam:
                continue
            seen_fam.add(p)
        reps.append(tn)

    col_to_tables = {}
    for tn in reps:
        for c in _column_names_only(ddl_by_table[tn]):
            lc = c.lower()
            if lc.endswith("_id") or lc == "id":
                col_to_tables.setdefault(lc, set()).add(tn)
    inferred = sum(len(ts) - 1 for ts in col_to_tables.values() if len(ts) >= 2)

    has_fk = declared_fk > 0
    partition_dominant = (
        partition_group_count >= 1
        and partition_table_count >= 0.5 * table_count
    )
    has_join = inferred > 0
    if has_fk:
        cls = "declared_fk_schema"
    elif partition_dominant and has_join:
        cls = "mixed"
    elif partition_dominant:
        cls = "partition_family_schema"
    elif has_join:
        cls = "inferable_join_schema"
    else:
        cls = "messy_or_no_join_signal"

    out = {
        "classification": cls,
        "declared_fk_count": declared_fk,
        "inferred_join_candidate_count": inferred,
        "partition_group_count": partition_group_count,
    }
    cache[key] = out
    return out


def _supported_signal(classification, inferred_join_candidate_count):
    if classification in _SUPPORTED_CLASSES:
        return True
    return classification == "mixed" and (inferred_join_candidate_count or 0) > 0


def _iter_task_records(root):
    seen_paths = set()
    for name in _TASK_FILE_NAMES:
        for pat in (
            os.path.join(root, name),
            os.path.join(root, "*", name),
            os.path.join(root, "*", "*", name),
        ):
            for path in glob.glob(pat):
                if path in seen_paths:
                    continue
                seen_paths.add(path)
                try:
                    with open(path, encoding="utf-8", errors="replace") as fh:
                        for line in fh:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                obj = json.loads(line)
                            except ValueError:
                                continue
                            if isinstance(obj, dict):
                                yield obj
                except (OSError, UnicodeError):
                    continue


def _build_catalog(root, index):
    names_cache = {}
    class_cache = {}
    entries = []
    for rec in _iter_task_records(root):
        sid = (rec.get("instance_id") or rec.get("spider2_id")
               or rec.get("db_id") or rec.get("database_id"))
        if not sid:
            continue
        sid = str(sid)
        db = rec.get("db") or rec.get("database")
        info = _db_table_names(index, db, names_cache) if db else None
        table_names = info["table_names"] if info else []
        dialect = info["dialect"] if info else None
        importable = bool(table_names)
        signal = _classify_db(index, db, class_cache) if db else {
            "classification": "messy_or_no_join_signal", "declared_fk_count": 0,
            "inferred_join_candidate_count": 0, "partition_group_count": 0,
        }
        entries.append({
            "spider2_id": sid,
            "name": sid,
            "db": db,
            "domain": db,
            "dialect": dialect,
            "question": rec.get("question"),
            "description": rec.get("external_knowledge") or rec.get("description"),
            "source_type": "local_spider2_metadata",
            "availability": "LOCAL_SCHEMA_IMPORTABLE" if importable
                            else "LOCAL_METADATA_ONLY",
            "importable": importable,
            "classification": signal["classification"],
            "declared_fk_count": signal["declared_fk_count"],
            "inferred_join_candidate_count": signal["inferred_join_candidate_count"],
            "partition_group_count": signal["partition_group_count"],
            "tables": [],  # columns parsed lazily at import time
            "table_names": table_names,
            "relationships": [],
        })
        if len(entries) >= _MAX_ENTRIES:
            break
    # Importable entries first, then by id (deterministic).
    entries.sort(key=lambda e: (not e["importable"], e["spider2_id"]))
    return entries


def _catalog(root):
    if _CATALOG_CACHE["root"] != root or _CATALOG_CACHE["entries"] is None:
        _CATALOG_CACHE["root"] = root
        _CATALOG_CACHE["index"] = _build_schema_index(root) if root else {}
        _CATALOG_CACHE["entries"] = (
            _build_catalog(root, _CATALOG_CACHE["index"]) if root else []
        )
    return _CATALOG_CACHE["entries"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def entry_is_importable(entry):
    tables = entry.get("tables") or []
    return bool(tables) and all(t.get("columns") for t in tables)


def _summarize(entry):
    tables = entry.get("tables") or []
    table_names = entry.get("table_names") or [t["table_name"] for t in tables]
    importable = entry.get("importable")
    if importable is None:
        importable = entry_is_importable(entry)
    return {
        "spider2_id": entry["spider2_id"],
        "name": entry.get("name") or entry["spider2_id"],
        "domain": entry.get("domain"),
        "dialect": entry.get("dialect"),
        "description": entry.get("description"),
        "question": entry.get("question"),
        "source_type": entry.get("source_type", "local_spider2_metadata"),
        "availability": entry.get("availability"),
        # Local Spider 2.0 imports build empty tables from the DDL — schema and
        # metadata only, no data rows. Surfaced so the UI can say so up front.
        "data_availability": "schema_only",
        "data_note": "Schema-only import. Local data rows are not included.",
        "table_count": len(table_names) or len(tables),
        "column_count": (sum(len(t.get("columns", [])) for t in tables)
                         if tables else None),
        "table_names": table_names[:12],
        "importable": bool(importable),
        # Relationship-signal classification (for filtering / display).
        "classification": entry.get("classification"),
        "declared_fk_count": entry.get("declared_fk_count", 0),
        "inferred_join_candidate_count": entry.get("inferred_join_candidate_count", 0),
        "partition_group_count": entry.get("partition_group_count", 0),
    }


def list_catalog(q=None, include_samples=False):
    """Return catalog items, filtered to schemas with usable join signal
    (declared_fk_schema / inferable_join_schema / mixed-with-joins). Partition-
    family and messy/no-join schemas are hidden. Dev samples are exempt."""
    root = _data_dir()
    entries = list(_catalog(root))
    if include_samples:
        entries = entries + SAMPLE_CATALOG

    items = [_summarize(e) for e in entries]

    # Keep only join-usable schemas (dev samples always pass through).
    items = [
        it for it in items
        if it.get("source_type") == "dev_sample"
        or _supported_signal(it.get("classification"),
                             it.get("inferred_join_candidate_count"))
    ]

    if q and str(q).strip():
        needle = str(q).strip().lower()
        items = [
            it for it in items
            if needle in " ".join([
                it["spider2_id"], str(it["name"] or ""), str(it["domain"] or ""),
                str(it["dialect"] or ""), str(it["description"] or ""),
                str(it["question"] or ""), " ".join(it["table_names"]),
            ]).lower()
        ]
    return items


def database_signal_counts():
    """Per-database counts (distinct dbs) of supported vs hidden schemas, for a
    small UI note. Computed from the full (unfiltered) catalog."""
    root = _data_dir()
    by_db = {}
    for e in _catalog(root):
        db = e.get("db")
        if db and db not in by_db:
            by_db[db] = (e.get("classification"),
                         e.get("inferred_join_candidate_count", 0))
    by_class = {}
    supported = 0
    for cls, inferred in by_db.values():
        by_class[cls] = by_class.get(cls, 0) + 1
        if _supported_signal(cls, inferred):
            supported += 1
    total = len(by_db)
    return {
        "total_databases": total,
        "supported_databases": supported,
        "hidden_databases": total - supported,
        "by_classification": by_class,
    }


def get_catalog_entry(spider2_id, include_samples=True):
    root = _data_dir()
    for e in _catalog(root):
        if e["spider2_id"] == spider2_id:
            # Parse full columns for this db lazily (only when importing).
            if not e.get("tables") and e.get("db"):
                index = _CATALOG_CACHE.get("index") or _build_schema_index(root)
                full = _db_full_schema(index, e["db"])
                if full:
                    e["tables"] = full["tables"]
                    e["skipped_reserved_tables"] = full.get("skipped_reserved", 0)
                    # Persist ONLY real declared FK relationships (A). Name-based
                    # inferred relationships are intentionally not added yet (B).
                    e["relationships"] = full.get("relationships", [])
            return e
    if include_samples:
        for e in SAMPLE_CATALOG:
            if e["spider2_id"] == spider2_id:
                return e
    return None


def _quote_ident(name):
    return '"' + str(name).replace('"', '""') + '"'


def entry_to_ddl(entry):
    stmts = []
    for table in entry.get("tables", []):
        cols = []
        for col in table.get("columns", []):
            piece = f"{_quote_ident(col['column_name'])} {col.get('data_type', 'TEXT')}"
            if col.get("primary_key"):
                piece += " PRIMARY KEY"
            cols.append(piece)
        if cols:
            stmts.append(
                f"CREATE TABLE {_quote_ident(_sanitize_ident(table['table_name']))} "
                f"( {', '.join(cols)} );"
            )
    return "\n".join(stmts)


def entry_relationship_edges(entry):
    edges = []
    for r in entry.get("relationships", []):
        if not isinstance(r, dict):
            continue
        if not (r.get("from_table") and r.get("from_column")
                and r.get("to_table") and r.get("to_column")):
            continue
        edges.append({
            "from_table": r["from_table"], "from_column": r["from_column"],
            "to_table": r["to_table"], "to_column": r["to_column"],
            "relationship_type": "spider2_catalog",
            "name_similarity": 1.0, "value_overlap": None,
            "confidence": 1.0, "confirmed": True,
        })
    return edges


# ---------------------------------------------------------------------------
# (B) Bounded, deterministic name-based relationship inference for Spider 2.0
# imports that carry a join signal but no real declared FK constraints. These
# are SUGGESTIONS (confirmed=False, confidence<1.0): a <entity>_id column is
# linked to the single OWNER table whose name matches <entity>, never to every
# table that merely shares the column — so the noisy fan-out is collapsed. No
# LLM, no data reads, no gold SQL.
# ---------------------------------------------------------------------------
_INFERRED_CAP = 200          # max suggested edges persisted per database
_SUPPORTED_INFER_CLASSES = ("inferable_join_schema", "mixed")


def _entity_base(name):
    """Lowercased table name with a trailing numeric version/partition suffix
    removed (e.g. molecule_dictionary_30 -> molecule_dictionary)."""
    return re.sub(r"_\d+$", "", str(name or "").strip().lower())


def _singular(s):
    s = str(s or "")
    if len(s) > 3 and s.endswith("ies"):
        return s[:-3] + "y"
    if len(s) > 3 and s.endswith("ses"):
        return s[:-2]            # statuses -> status
    if len(s) > 1 and s.endswith("s") and not s.endswith("ss"):
        return s[:-1]
    return s


def infer_name_based_edges(tables, cap=_INFERRED_CAP):
    """Return bounded, high-confidence <entity>_id -> owner-table edges.

    Rule: a column ``<e>_id`` in table A is linked to the one table B whose
    entity name matches ``<e>`` (singular/plural, version suffix ignored). The
    target column is B's matching ``<e>_id`` (confidence 0.9) or B's ``id``
    (0.8); if B has neither, the edge is skipped to avoid noise. A column that
    names its own table's key is not linked back to itself. Ranked by
    confidence then name, capped at ``cap``."""
    by_key = {}
    col_sets = {}
    for t in tables or []:
        name = t.get("table_name")
        if not name:
            continue
        col_sets[name] = {str(c.get("column_name", "")).lower()
                          for c in t.get("columns", [])}
        base = _entity_base(name)
        for k in {base, _singular(base)}:
            if k:
                by_key.setdefault(k, name)   # first table wins (deterministic)

    edges, seen = [], set()
    for t in tables or []:
        a = t.get("table_name")
        if not a:
            continue
        a_key = _singular(_entity_base(a))
        for c in t.get("columns", []):
            lc = str(c.get("column_name", "")).lower()
            if lc == "id" or not lc.endswith("_id"):
                continue
            prefix = lc[:-3]
            if not prefix or _singular(prefix) == a_key:
                continue                      # don't link a table to itself
            target = (by_key.get(prefix) or by_key.get(_singular(prefix))
                      or by_key.get(prefix + "s"))
            if not target or target == a:
                continue
            tcols = col_sets.get(target, set())
            if lc in tcols:
                tcol, conf = c.get("column_name"), 0.9
            elif "id" in tcols:
                tcol, conf = "id", 0.8
            else:
                continue                      # no plausible target key -> skip
            key = (a, c.get("column_name"), target, tcol)
            if key in seen:
                continue
            seen.add(key)
            edges.append({
                "from_table": a, "from_column": c.get("column_name"),
                "to_table": target, "to_column": tcol,
                "relationship_type": "inferred_foreign_key",
                "name_similarity": conf, "value_overlap": None,
                "confidence": conf, "confirmed": False,
            })

    edges.sort(key=lambda e: (-e["confidence"], e["from_table"],
                              str(e["from_column"])))
    return edges[:cap]


def entry_inferred_edges(entry, cap=_INFERRED_CAP):
    """Suggested name-based edges for an entry — ONLY when it has a join signal
    (inferable_join_schema / mixed) and no real declared FK constraints. Empty
    for partition_family_schema, messy_or_no_join_signal, or when real FKs exist
    (those are preferred and persisted instead)."""
    if entry.get("relationships"):
        return []                              # prefer real declared FKs (A)
    if entry.get("classification") not in _SUPPORTED_INFER_CLASSES:
        return []
    return infer_name_based_edges(entry.get("tables") or [], cap)
