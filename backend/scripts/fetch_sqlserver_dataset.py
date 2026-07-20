"""
scripts/fetch_sqlserver_dataset.py

Copy a SQL Server database (e.g. WideWorldImporters) into a local SQLite file,
preserving declared PRIMARY KEY and FOREIGN KEY constraints (read from
INFORMATION_SCHEMA; not invented). RUN THIS LOCALLY.

Typical WideWorldImporters flow (Docker + SQL Server):
    # 1) run SQL Server and restore the sample .bak (one-time)
    docker run -e "ACCEPT_EULA=Y" -e "MSSQL_SA_PASSWORD=Your_password123" \
        -p 1433:1433 -d mcr.microsoft.com/mssql/server:2022-latest
    #    download WideWorldImporters-Full.bak, copy into the container, then:
    #    RESTORE DATABASE WideWorldImporters FROM DISK='/var/opt/mssql/WideWorldImporters-Full.bak'
    #    WITH MOVE ... (see Microsoft docs).
    # 2) copy it into SQLite
    pip install pyodbc
    python backend/scripts/fetch_sqlserver_dataset.py \
        --server localhost,1433 --user sa --password Your_password123 \
        --database WideWorldImporters \
        --db backend/local_benchmarks/relational_sample_dbs/sqlite/wideworldimporters.sqlite

Then profile:
    python backend/scripts/profile_local_benchmark_db.py \
        --db backend/local_benchmarks/relational_sample_dbs/sqlite/wideworldimporters.sqlite \
        --name wideworldimporters

Notes:
  * Spatial (geography/geometry) columns are converted to WKT text; hierarchyid
    to its string form, so pyodbc can read them and SQLite can store them.
  * Types map to SQLite affinity (INTEGER / REAL / TEXT / BLOB).
  * SQLite table name = "<schema>_<table>" to avoid cross-schema collisions;
    FK references are remapped to the same naming.
"""

import argparse
import datetime
import os
import sqlite3
import sys
from decimal import Decimal

_SPATIAL = {"geography", "geometry"}


def map_type(sqltype: str) -> str:
    t = (sqltype or "").lower()
    if t in _SPATIAL or t == "hierarchyid":
        return "TEXT"          # converted to text in the SELECT
    if "int" in t or t == "bit":
        return "INTEGER"
    if any(k in t for k in ("decimal", "numeric", "money", "float", "real")):
        return "REAL"
    if any(k in t for k in ("binary", "image")):
        return "BLOB"
    return "TEXT"


def coerce(v):
    if v is None or isinstance(v, (int, float, str, bytes, bytearray)):
        return v
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime.date, datetime.datetime, datetime.time)):
        return v.isoformat(sep=" ") if isinstance(v, datetime.datetime) else v.isoformat()
    return str(v)


def sqlname(schema, table):
    return f"{schema}_{table}"


def select_expr(col, sqltype):
    """SELECT expression: convert spatial/hierarchyid to text, else pass through."""
    t = (sqltype or "").lower()
    if t in _SPATIAL:
        return f"[{col}].STAsText() AS [{col}]"
    if t == "hierarchyid":
        return f"[{col}].ToString() AS [{col}]"
    return f"[{col}]"


def create_sql(table_name, cols, pk, fks, with_fk):
    q = lambda n: '"' + str(n).replace('"', '""') + '"'
    parts = [f"{q(c)} {map_type(t)}" for c, t in cols]
    if pk:
        parts.append(f'PRIMARY KEY ({", ".join(q(c) for c in pk)})')
    if with_fk:
        for _c, from_cols, ref_table, ref_cols in fks:
            parts.append(
                f'FOREIGN KEY ({", ".join(q(c) for c in from_cols)}) '
                f'REFERENCES {q(ref_table)} ({", ".join(q(c) for c in ref_cols)})')
    return f'CREATE TABLE {q(table_name)} ({", ".join(parts)})'


def main(argv=None):
    p = argparse.ArgumentParser(description="Copy a SQL Server database into SQLite.")
    p.add_argument("--server", required=True, help="host,port e.g. localhost,1433")
    p.add_argument("--database", required=True)
    p.add_argument("--user", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--driver", default="ODBC Driver 18 for SQL Server")
    p.add_argument("--db", required=True, help="output sqlite path")
    p.add_argument("--no-fk", action="store_true")
    p.add_argument("--batch", type=int, default=5000)
    args = p.parse_args(argv)

    try:
        import pyodbc
    except ImportError:
        print("Missing dependency. Run: pip install pyodbc", file=sys.stderr)
        return 2

    cs = (f"DRIVER={{{args.driver}}};SERVER={args.server};DATABASE={args.database};"
          f"UID={args.user};PWD={args.password};TrustServerCertificate=yes")
    conn = pyodbc.connect(cs)
    cur = conn.cursor()

    cur.execute(
        "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_TYPE='BASE TABLE' AND TABLE_SCHEMA <> 'sys' "
        "ORDER BY TABLE_SCHEMA, TABLE_NAME")
    tables = [(r[0], r[1]) for r in cur.fetchall()]
    print(f"{args.database}: {len(tables)} base tables")

    os.makedirs(os.path.dirname(os.path.abspath(args.db)), exist_ok=True)
    if os.path.exists(args.db):
        os.remove(args.db)
    s = sqlite3.connect(args.db)
    s.execute("PRAGMA foreign_keys=OFF")
    try:
        total = 0
        for schema, table in tables:
            cur.execute(
                "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA=? AND TABLE_NAME=? ORDER BY ORDINAL_POSITION",
                schema, table)
            cols = [(r[0], r[1]) for r in cur.fetchall()]

            cur.execute(
                "SELECT kcu.COLUMN_NAME FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc "
                "JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu "
                "  ON tc.CONSTRAINT_NAME=kcu.CONSTRAINT_NAME AND tc.TABLE_SCHEMA=kcu.TABLE_SCHEMA "
                "WHERE tc.CONSTRAINT_TYPE='PRIMARY KEY' AND tc.TABLE_SCHEMA=? AND tc.TABLE_NAME=? "
                "ORDER BY kcu.ORDINAL_POSITION", schema, table)
            pk = [r[0] for r in cur.fetchall()]

            fks = []
            if not args.no_fk:
                cur.execute(
                    "SELECT rc.CONSTRAINT_NAME, kcu.COLUMN_NAME, kcu2.TABLE_SCHEMA, "
                    "       kcu2.TABLE_NAME, kcu2.COLUMN_NAME "
                    "FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc "
                    "JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu "
                    "  ON rc.CONSTRAINT_NAME=kcu.CONSTRAINT_NAME "
                    "JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu2 "
                    "  ON rc.UNIQUE_CONSTRAINT_NAME=kcu2.CONSTRAINT_NAME "
                    "  AND kcu.ORDINAL_POSITION=kcu2.ORDINAL_POSITION "
                    "WHERE kcu.TABLE_SCHEMA=? AND kcu.TABLE_NAME=? "
                    "ORDER BY rc.CONSTRAINT_NAME, kcu.ORDINAL_POSITION", schema, table)
                grouped = {}
                for cname, col, rsch, rtab, rcol in cur.fetchall():
                    e = grouped.setdefault(cname, {"from": [], "rt": sqlname(rsch, rtab), "ref": []})
                    e["from"].append(col)
                    e["ref"].append(rcol)
                fks = [(c, e["from"], e["rt"], e["ref"]) for c, e in grouped.items()]

            name = sqlname(schema, table)
            try:
                s.execute(create_sql(name, cols, pk, fks, with_fk=not args.no_fk))
            except sqlite3.Error:
                s.execute(create_sql(name, cols, [], [], with_fk=False))

            exprs = ", ".join(select_expr(c, t) for c, t in cols)
            colnames = [c for c, _ in cols]
            ph = ",".join("?" for _ in colnames)
            ins = f'INSERT INTO "{name}" VALUES ({ph})'
            cur.execute(f"SELECT {exprs} FROM [{schema}].[{table}]")
            n = 0
            while True:
                rows = cur.fetchmany(args.batch)
                if not rows:
                    break
                s.executemany(ins, [[coerce(v) for v in row] for row in rows])
                n += len(rows)
            s.commit()
            total += n
            print(f"  - {name}: {n} rows, {len(colnames)} cols, pk={pk or '-'}, fks={len(fks)}")
        print(f"Wrote {args.db} ({total} rows across {len(tables)} tables)")
    finally:
        s.close()
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
