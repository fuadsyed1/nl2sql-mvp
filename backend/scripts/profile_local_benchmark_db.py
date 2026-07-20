"""
scripts/profile_local_benchmark_db.py

Profile a local benchmark SQLite database and emit metadata + a report so we can
decide whether it qualifies as a SpiderSQL relational benchmark (real data, not
schema-only; enough tables/columns).

Usage:
    python backend/scripts/profile_local_benchmark_db.py \
        --db backend/local_benchmarks/relational_sample_dbs/sqlite/<name>.sqlite \
        --name <name>

Outputs (written next to the sqlite/ folder, under the same benchmark root):
    metadata/<name>_schema.json         full per-table schema
    metadata/<name>_relationships.json  declared foreign keys
    reports/<name>_report.md            human-readable summary

It is READ-ONLY on the database (opens with mode=ro) and never touches the
NL-to-SQL pipeline. The profiling functions are pure and unit-testable.
"""

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone

# Quality thresholds (tables must be in [MIN_TABLES, MAX_TABLES]).
MIN_TABLES = 20
MAX_TABLES = 80
USABLE_COLUMNS = 150
STRONG_COLUMNS = 200


def quality_label(table_count: int, total_columns: int) -> str:
    """Classify a database:
      * "strong": 20-80 tables and >= 200 columns
      * "usable": 20-80 tables and >= 150 columns
      * "reject": anything else (too few/many tables, or too few columns)
    """
    in_range = MIN_TABLES <= table_count <= MAX_TABLES
    if in_range and total_columns >= STRONG_COLUMNS:
        return "strong"
    if in_range and total_columns >= USABLE_COLUMNS:
        return "usable"
    return "reject"


def _connect_ro(db_path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def profile_db(db_path: str) -> dict:
    """Read-only profile of a SQLite database. Returns a dict with counts and
    per-table detail. Raises FileNotFoundError if the database is missing."""
    if not db_path or not os.path.exists(db_path):
        raise FileNotFoundError(db_path)

    conn = _connect_ro(db_path)
    try:
        cur = conn.cursor()
        table_names = [
            r[0] for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name")
        ]

        tables = []
        relationships = []
        total_columns = 0
        total_rows = 0
        declared_pk_count = 0   # count of PK columns across all tables
        declared_fk_count = 0   # count of distinct FK constraints across tables

        for t in table_names:
            info = cur.execute(f"PRAGMA table_info({_quote(t)})").fetchall()
            columns = []
            primary_keys = []
            for (_cid, cname, ctype, notnull, _dflt, pk) in info:
                columns.append({
                    "name": cname,
                    "type": ctype or "",
                    "notnull": bool(notnull),
                    "pk": int(pk or 0),
                })
                if pk:
                    primary_keys.append(cname)
            declared_pk_count += len(primary_keys)

            try:
                row_count = cur.execute(
                    f"SELECT COUNT(*) FROM {_quote(t)}").fetchone()[0] or 0
            except sqlite3.Error:
                row_count = 0

            # Foreign keys: one PRAGMA row per FK column; group by constraint id.
            fk_rows = cur.execute(
                f"PRAGMA foreign_key_list({_quote(t)})").fetchall()
            fk_by_id = {}
            for row in fk_rows:
                # (id, seq, table, from, to, on_update, on_delete, match)
                fid, _seq, ref_table, from_col, to_col = row[0], row[1], row[2], row[3], row[4]
                entry = fk_by_id.setdefault(
                    fid, {"from_table": t, "to_table": ref_table,
                          "from_columns": [], "to_columns": []})
                entry["from_columns"].append(from_col)
                entry["to_columns"].append(to_col)
            declared_fk_count += len(fk_by_id)
            relationships.extend(fk_by_id.values())

            total_columns += len(columns)
            total_rows += row_count
            tables.append({
                "name": t,
                "column_count": len(columns),
                "row_count": row_count,
                "columns": columns,
                "primary_keys": primary_keys,
            })

        return {
            "db_path": os.path.abspath(db_path),
            "table_count": len(table_names),
            "total_columns": total_columns,
            "total_rows": total_rows,
            "declared_pk_count": declared_pk_count,
            "declared_fk_count": declared_fk_count,
            "tables": tables,
            "relationships": relationships,
        }
    finally:
        conn.close()


def build_schema_json(profile: dict, name: str) -> dict:
    return {
        "name": name,
        "db_path": profile["db_path"],
        "table_count": profile["table_count"],
        "total_columns": profile["total_columns"],
        "total_rows": profile["total_rows"],
        "tables": [
            {"name": t["name"], "column_count": t["column_count"],
             "row_count": t["row_count"], "primary_keys": t["primary_keys"],
             "columns": t["columns"]}
            for t in profile["tables"]
        ],
    }


def build_relationships_json(profile: dict, name: str) -> dict:
    return {
        "name": name,
        "declared_fk_count": profile["declared_fk_count"],
        "relationships": profile["relationships"],
    }


def build_markdown_report(profile: dict, name: str, label: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f"# Local benchmark profile: {name}",
        "",
        f"- Generated: {ts}",
        f"- Database: `{profile['db_path']}`",
        f"- **Quality label: {label.upper()}**",
        "",
        "## Totals",
        "",
        f"- Tables: {profile['table_count']}",
        f"- Total columns: {profile['total_columns']}",
        f"- Total rows: {profile['total_rows']}",
        f"- Declared primary-key columns: {profile['declared_pk_count']}",
        f"- Declared foreign keys: {profile['declared_fk_count']}",
        "",
        "## Quality rule",
        "",
        f"- reject: tables < {MIN_TABLES} or > {MAX_TABLES}, or columns < {USABLE_COLUMNS}",
        f"- usable: tables {MIN_TABLES}-{MAX_TABLES} and columns >= {USABLE_COLUMNS}",
        f"- strong: tables {MIN_TABLES}-{MAX_TABLES} and columns >= {STRONG_COLUMNS}",
        "",
        "## Per-table",
        "",
        "| Table | Columns | Rows | Primary key |",
        "| --- | ---: | ---: | --- |",
    ]
    for t in profile["tables"]:
        pk = ", ".join(t["primary_keys"]) if t["primary_keys"] else "-"
        lines.append(f"| {t['name']} | {t['column_count']} | {t['row_count']} | {pk} |")
    lines.append("")
    return "\n".join(lines)


def _benchmark_root(db_path: str) -> str:
    """Given .../relational_sample_dbs/sqlite/<name>.sqlite, return
    .../relational_sample_dbs so metadata/ and reports/ sit beside sqlite/."""
    sqlite_dir = os.path.dirname(os.path.abspath(db_path))
    return os.path.dirname(sqlite_dir)


def write_outputs(profile: dict, name: str, label: str, base_dir: str) -> dict:
    meta_dir = os.path.join(base_dir, "metadata")
    report_dir = os.path.join(base_dir, "reports")
    os.makedirs(meta_dir, exist_ok=True)
    os.makedirs(report_dir, exist_ok=True)

    schema_path = os.path.join(meta_dir, f"{name}_schema.json")
    rel_path = os.path.join(meta_dir, f"{name}_relationships.json")
    report_path = os.path.join(report_dir, f"{name}_report.md")

    with open(schema_path, "w", encoding="utf-8") as f:
        json.dump(build_schema_json(profile, name), f, indent=2, ensure_ascii=False)
    with open(rel_path, "w", encoding="utf-8") as f:
        json.dump(build_relationships_json(profile, name), f, indent=2, ensure_ascii=False)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(build_markdown_report(profile, name, label))

    return {"schema_json": schema_path, "relationships_json": rel_path,
            "report_md": report_path}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Profile a local benchmark SQLite database.")
    parser.add_argument("--db", required=True, help="path to the .sqlite file")
    parser.add_argument("--name", required=True, help="benchmark name (e.g. adventureworks)")
    parser.add_argument("--outdir", default=None,
                        help="benchmark root for metadata/ and reports/ "
                             "(default: inferred from --db)")
    args = parser.parse_args(argv)

    profile = profile_db(args.db)
    label = quality_label(profile["table_count"], profile["total_columns"])
    base_dir = args.outdir or _benchmark_root(args.db)
    outputs = write_outputs(profile, args.name, label, base_dir)

    print(f"Name:                 {args.name}")
    print(f"Tables:               {profile['table_count']}")
    print(f"Total columns:        {profile['total_columns']}")
    print(f"Total rows:           {profile['total_rows']}")
    print(f"Declared PK columns:  {profile['declared_pk_count']}")
    print(f"Declared FKs:         {profile['declared_fk_count']}")
    print(f"Quality label:        {label.upper()}")
    print("Per-table row counts:")
    for t in profile["tables"]:
        print(f"  - {t['name']}: {t['row_count']} rows, {t['column_count']} cols")
    print("Wrote:")
    for k, v in outputs.items():
        print(f"  - {k}: {v}")

    if label == "reject":
        print("RESULT: REJECT (does not meet table/column requirements).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
