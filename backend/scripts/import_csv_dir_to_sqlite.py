"""
scripts/import_csv_dir_to_sqlite.py

Import every CSV file in a directory into one SQLite database — one table per
CSV, table name = file stem, columns = CSV header. Column types are inferred
lightly (INTEGER / REAL / TEXT) from the data; empty strings become NULL.

It does NOT invent primary keys or foreign keys — Lahman/Baseball-Databank CSVs
carry none, so the imported DB has no declared constraints (relationships are
still inferable from shared keys like playerID). If you need declared keys, use
a source that ships them (e.g. lahmanlite's lahman.db).

Usage:
    python backend/scripts/import_csv_dir_to_sqlite.py \
        --csv-dir backend/local_benchmarks/relational_sample_dbs/raw/lahman \
        --db backend/local_benchmarks/relational_sample_dbs/sqlite/lahman.sqlite

Then profile it:
    python backend/scripts/profile_local_benchmark_db.py \
        --db backend/local_benchmarks/relational_sample_dbs/sqlite/lahman.sqlite \
        --name lahman
"""

import argparse
import csv
import glob
import os
import re
import sqlite3

_INT_RE = re.compile(r"^[+-]?\d+$")


def _sanitize(name: str) -> str:
    s = re.sub(r"[^0-9A-Za-z_]", "_", name.strip())
    if not s:
        s = "col"
    if s[0].isdigit():
        s = "_" + s
    return s


def _read_csv(path):
    """Return (header, rows) reading utf-8-sig, falling back to latin-1."""
    for enc in ("utf-8-sig", "latin-1"):
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
            if not rows:
                return [], []
            return rows[0], rows[1:]
        except UnicodeDecodeError:
            continue
    return [], []


def _infer_types(header, rows):
    """Per-column type: INTEGER if every non-empty value is an int, REAL if
    every non-empty value is a float, else TEXT."""
    n = len(header)
    could_int = [True] * n
    could_real = [True] * n
    seen = [False] * n
    for row in rows:
        for i in range(min(n, len(row))):
            v = (row[i] or "").strip()
            if v == "":
                continue
            seen[i] = True
            if could_int and not _INT_RE.match(v):
                could_int[i] = False
            if could_real[i]:
                try:
                    float(v)
                except ValueError:
                    could_real[i] = False
    types = []
    for i in range(n):
        if not seen[i]:
            types.append("TEXT")
        elif could_int[i]:
            types.append("INTEGER")
        elif could_real[i]:
            types.append("REAL")
        else:
            types.append("TEXT")
    return types


def _coerce(value, sqltype):
    v = (value or "").strip()
    if v == "":
        return None
    if sqltype == "INTEGER":
        try:
            return int(v)
        except ValueError:
            return v
    if sqltype == "REAL":
        try:
            return float(v)
        except ValueError:
            return v
    return v


def import_csv(conn, path, drop=False):
    """Import one CSV file into `conn`. Returns (table_name, row_count)."""
    header, rows = _read_csv(path)
    if not header:
        return None, 0
    table = _sanitize(os.path.splitext(os.path.basename(path))[0])
    cols = [_sanitize(h) for h in header]
    # de-duplicate column names
    seen = {}
    uniq = []
    for c in cols:
        if c in seen:
            seen[c] += 1
            uniq.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            uniq.append(c)
    cols = uniq
    types = _infer_types(header, rows)

    cur = conn.cursor()
    if drop:
        cur.execute(f'DROP TABLE IF EXISTS "{table}"')
    col_defs = ", ".join(f'"{c}" {t}' for c, t in zip(cols, types))
    cur.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({col_defs})')
    placeholders = ", ".join("?" for _ in cols)
    insert = f'INSERT INTO "{table}" VALUES ({placeholders})'
    ncol = len(cols)
    prepared = []
    for row in rows:
        row = list(row) + [""] * (ncol - len(row)) if len(row) < ncol else row[:ncol]
        prepared.append([_coerce(row[i], types[i]) for i in range(ncol)])
    cur.executemany(insert, prepared)
    conn.commit()
    return table, len(prepared)


def import_dir(csv_dir, db_path, drop=False, recursive=True):
    pattern = os.path.join(csv_dir, "**", "*.csv") if recursive \
        else os.path.join(csv_dir, "*.csv")
    files = sorted(glob.glob(pattern, recursive=recursive))
    if not files:
        raise FileNotFoundError(f"no .csv files under {csv_dir}")
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        results = []
        for path in files:
            table, count = import_csv(conn, path, drop=drop)
            if table is not None:
                results.append((table, count))
        return results
    finally:
        conn.close()


def main(argv=None):
    p = argparse.ArgumentParser(description="Import all CSVs in a dir into SQLite.")
    p.add_argument("--csv-dir", required=True)
    p.add_argument("--db", required=True)
    p.add_argument("--drop", action="store_true",
                   help="drop each table before importing")
    p.add_argument("--no-recursive", action="store_true",
                   help="only import CSVs directly in --csv-dir")
    args = p.parse_args(argv)

    results = import_dir(args.csv_dir, args.db, drop=args.drop,
                         recursive=not args.no_recursive)
    total = sum(c for _, c in results)
    print(f"Imported {len(results)} tables, {total} rows -> {args.db}")
    for table, count in results:
        print(f"  - {table}: {count} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
