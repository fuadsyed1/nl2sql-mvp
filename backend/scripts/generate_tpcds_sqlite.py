"""
scripts/generate_tpcds_sqlite.py

Generate a small local TPC-DS dataset with DuckDB and export it to SQLite.
RUN THIS LOCALLY (DuckDB downloads its `tpcds` extension the first time, which
needs network access):

    pip install duckdb
    python backend/scripts/generate_tpcds_sqlite.py            # default sf=0.01
    python backend/scripts/generate_tpcds_sqlite.py --sf 0.05  # a bit more data

Output:
    backend/local_benchmarks/relational_sample_dbs/sqlite/tpcds.sqlite

TPC-DS has 24 tables and ~425 columns, so even a tiny scale factor profiles as
STRONG (the column/table count is schema-driven; sf only controls row counts).
Keep sf small (0.01-0.1) so the database stays small. dsdgen creates no declared
PK/FK, so the SQLite copy has none (0 declared PK/FK is expected and fine).

Then profile it:
    python backend/scripts/profile_local_benchmark_db.py \
        --db backend/local_benchmarks/relational_sample_dbs/sqlite/tpcds.sqlite \
        --name tpcds
"""

import argparse
import datetime
import os
import sqlite3
import sys
from decimal import Decimal

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
DEFAULT_DB = os.path.join(
    _BACKEND, "local_benchmarks", "relational_sample_dbs", "sqlite",
    "tpcds.sqlite",
)


def map_type(duck_type: str) -> str:
    t = (duck_type or "").upper()
    if any(k in t for k in ("INT", "HUGEINT", "BIGINT", "SMALLINT", "TINYINT")):
        return "INTEGER"
    if any(k in t for k in ("DEC", "NUMERIC", "DOUBLE", "REAL", "FLOAT")):
        return "REAL"
    return "TEXT"


def coerce(v):
    if v is None or isinstance(v, (int, float, str)):
        return v
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime.date, datetime.datetime, datetime.time)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return bytes(v)
    return str(v)


def main(argv=None):
    p = argparse.ArgumentParser(description="Generate TPC-DS into SQLite via DuckDB.")
    p.add_argument("--db", default=DEFAULT_DB, help="output sqlite path")
    p.add_argument("--sf", type=float, default=0.01, help="TPC-DS scale factor (small)")
    p.add_argument("--batch", type=int, default=10000)
    args = p.parse_args(argv)

    try:
        import duckdb  # pip install duckdb
    except ImportError:
        print("DuckDB not installed. Run: pip install duckdb", file=sys.stderr)
        return 2

    con = duckdb.connect()
    print(f"Loading tpcds extension and generating sf={args.sf} ...")
    con.execute("INSTALL tpcds; LOAD tpcds;")
    con.execute(f"CALL dsdgen(sf={args.sf})")
    tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
    print(f"Generated {len(tables)} tables.")

    os.makedirs(os.path.dirname(os.path.abspath(args.db)), exist_ok=True)
    if os.path.exists(args.db):
        os.remove(args.db)
    sconn = sqlite3.connect(args.db)
    try:
        total_rows = 0
        for t in tables:
            desc = con.execute(f'DESCRIBE "{t}"').fetchall()  # (name, type, ...)
            cols = [d[0] for d in desc]
            types = [map_type(d[1]) for d in desc]
            col_defs = ", ".join(f'"{c}" {ty}' for c, ty in zip(cols, types))
            sconn.execute(f'CREATE TABLE "{t}" ({col_defs})')
            placeholders = ",".join("?" for _ in cols)
            insert = f'INSERT INTO "{t}" VALUES ({placeholders})'
            cur = con.execute(f'SELECT * FROM "{t}"')
            count = 0
            while True:
                batch = cur.fetchmany(args.batch)
                if not batch:
                    break
                sconn.executemany(insert, [[coerce(v) for v in row] for row in batch])
                count += len(batch)
            sconn.commit()
            total_rows += count
            print(f"  - {t}: {count} rows, {len(cols)} cols")
        print(f"Wrote {args.db} ({total_rows} rows across {len(tables)} tables)")
    finally:
        sconn.close()

    print("\nNext: profile it")
    print("  python backend/scripts/profile_local_benchmark_db.py "
          f"--db {os.path.relpath(args.db, os.path.dirname(_BACKEND))} --name tpcds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
