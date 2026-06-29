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
                    tables.append({"table_name": tn, "columns": cols})
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
            raw.append(os.path.splitext(os.path.basename(jf))[0])
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
    tables, seen = [], set()
    for d in info["dirs"]:
        for t in _parse_ddl_csv(os.path.join(d, "DDL.csv")):
            name = _sanitize_ident(t["table_name"])
            base, n = name, 2
            while name in seen:
                name = f"{base}_{n}"
                n += 1
            seen.add(name)
            tables.append({"table_name": name, "columns": t["columns"]})
            if len(tables) >= _MAX_TABLES_PER_DB:
                break
        if len(tables) >= _MAX_TABLES_PER_DB:
            break
    return {"dialect": info["dialect"], "tables": tables}


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
        "table_count": len(table_names) or len(tables),
        "column_count": (sum(len(t.get("columns", [])) for t in tables)
                         if tables else None),
        "table_names": table_names[:12],
        "importable": bool(importable),
    }


def list_catalog(q=None, include_samples=False):
    root = _data_dir()
    entries = list(_catalog(root))
    if include_samples:
        entries = entries + SAMPLE_CATALOG

    items = [_summarize(e) for e in entries]
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
