"""
scripts/fetch_ctu_dataset.py

Copy a CTU Relational Repository dataset (public MariaDB) directly into a local
SQLite file, preserving declared PRIMARY KEY and FOREIGN KEY constraints (CTU
provides them; we do NOT invent any). RUN THIS LOCALLY (needs network access):

    pip install pymysql
    python backend/scripts/fetch_ctu_dataset.py --database AdventureWorks2014 \
        --db backend/local_benchmarks/relational_sample_dbs/sqlite/adventureworks.sqlite

Defaults connect to the CTU guest server:
    host relational.fel.cvut.cz  port 3306  user guest  password ctu-relational

Then profile:
    python backend/scripts/profile_local_benchmark_db.py \
        --db backend/local_benchmarks/relational_sample_dbs/sqlite/adventureworks.sqlite \
        --name adventureworks

Notes:
  * Types are mapped MySQL -> SQLite affinity (INTEGER / REAL / TEXT / BLOB).
  * PK/FK are read from information_schema (real declared constraints, not
    invented). Use --no-fk to skip foreign keys if a source has messy refs.
  * Foreign-key enforcement is OFF during bulk load; tables are created with
    their FK clauses so the declarations persist in the schema.
"""

import argparse
import datetime
import os
import sqlite3
import sys
from decimal import Decimal


def map_type(mysql_type: str) -> str:
    t = (mysql_type or "").lower()
    if "int" in t:                       # int, bigint, smallint, tinyint, mediumint
        return "INTEGER"
    if any(k in t for k in ("decimal", "numeric", "float", "double", "real")):
        return "REAL"
    if any(k in t for k in ("blob", "binary", "image")):
        return "BLOB"
    return "TEXT"


def coerce(v):
    if v is None or isinstance(v, (int, float, str, bytes, bytearray)):
        return v
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime.date, datetime.datetime, datetime.time)):
        return v.isoformat(sep=" ") if isinstance(v, datetime.datetime) else v.isoformat()
    if isinstance(v, datetime.timedelta):
        return str(v)
    return str(v)


def _pk_columns(cur, schema, table):
    cur.execute(
        "SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND CONSTRAINT_NAME='PRIMARY' "
        "ORDER BY ORDINAL_POSITION", (schema, table))
    return [r[0] for r in cur.fetchall()]


def _foreign_keys(cur, schema, table):
    """Return list of (constraint, [from_cols], ref_table, [ref_cols])."""
    cur.execute(
        "SELECT CONSTRAINT_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME "
        "FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND REFERENCED_TABLE_NAME IS NOT NULL "
        "ORDER BY CONSTRAINT_NAME, ORDINAL_POSITION", (schema, table))
    fks = {}
    for cname, col, ref_table, ref_col in cur.fetchall():
        e = fks.setdefault(cname, {"from": [], "ref_table": ref_table, "ref": []})
        e["from"].append(col)
        e["ref"].append(ref_col)
    return [(c, e["from"], e["ref_table"], e["ref"]) for c, e in fks.items()]


def _columns(cur, schema, table):
    cur.execute(
        "SELECT COLUMN_NAME, DATA_TYPE FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION",
        (schema, table))
    return [(r[0], r[1]) for r in cur.fetchall()]


def _create_sql(table, cols, pk, fks, with_fk):
    q = lambda n: '"' + str(n).replace('"', '""') + '"'
    parts = [f'{q(c)} {map_type(t)}' for c, t in cols]
    if pk:
        parts.append(f'PRIMARY KEY ({", ".join(q(c) for c in pk)})')
    if with_fk:
        for _cname, from_cols, ref_table, ref_cols in fks:
            parts.append(
                f'FOREIGN KEY ({", ".join(q(c) for c in from_cols)}) '
                f'REFERENCES {q(ref_table)} ({", ".join(q(c) for c in ref_cols)})')
    return f'CREATE TABLE {q(table)} ({", ".join(parts)})'


def main(argv=None):
    p = argparse.ArgumentParser(description="Copy a CTU MySQL dataset into SQLite.")
    p.add_argument("--host", default="relational.fel.cvut.cz")
    p.add_argument("--port", type=int, default=3306)
    p.add_argument("--user", default="guest")
    p.add_argument("--password", default="ctu-relational")
    p.add_argument("--database", required=True, help="e.g. AdventureWorks2014")
    p.add_argument("--db", required=True, help="output sqlite path")
    p.add_argument("--no-fk", action="store_true", help="skip foreign keys")
    p.add_argument("--batch", type=int, default=5000)
    args = p.parse_args(argv)

    try:
        import pymysql  # pip install pymysql
    except ImportError:
        print("Missing dependency. Run: pip install pymysql", file=sys.stderr)
        return 2

    conn = pymysql.connect(host=args.host, port=args.port, user=args.user,
                           password=args.password, database=args.database)
    mcur = conn.cursor()
    mcur.execute(
        "SELECT TABLE_NAME FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME",
        (args.database,))
    tables = [r[0] for r in mcur.fetchall()]
    print(f"{args.database}: {len(tables)} tables")

    os.makedirs(os.path.dirname(os.path.abspath(args.db)), exist_ok=True)
    if os.path.exists(args.db):
        os.remove(args.db)
    s = sqlite3.connect(args.db)
    s.execute("PRAGMA foreign_keys=OFF")
    try:
        total = 0
        for t in tables:
            cols = _columns(mcur, args.database, t)
            pk = _pk_columns(mcur, args.database, t)
            fks = [] if args.no_fk else _foreign_keys(mcur, args.database, t)
            try:
                s.execute(_create_sql(t, cols, pk, fks, with_fk=not args.no_fk))
            except sqlite3.Error:
                # fall back to no-constraint create if FK/PK clause is rejected
                s.execute(_create_sql(t, cols, [], [], with_fk=False))

            colnames = [c for c, _ in cols]
            ph = ",".join("?" for _ in colnames)
            ins = f'INSERT INTO "{t}" VALUES ({ph})'
            mcur.execute(f'SELECT * FROM `{t}`')
            n = 0
            while True:
                rows = mcur.fetchmany(args.batch)
                if not rows:
                    break
                s.executemany(ins, [[coerce(v) for v in row] for row in rows])
                n += len(rows)
            s.commit()
            total += n
            print(f"  - {t}: {n} rows, {len(colnames)} cols, pk={pk or '-'}, fks={len(fks)}")
        print(f"Wrote {args.db} ({total} rows across {len(tables)} tables)")
    finally:
        s.close()
        conn.close()

    print("\nNext: profile it")
    print("  python backend/scripts/profile_local_benchmark_db.py "
          f"--db {args.db} --name adventureworks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
