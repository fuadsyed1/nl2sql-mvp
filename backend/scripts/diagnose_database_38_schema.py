"""
scripts/diagnose_database_38_schema.py

Diagnose a schema/data mismatch for a database group (default id 38, the bq023
build). Read-only: it inspects the METADATA (app_data.db: databases +
database_tables) and the PHYSICAL SQLite file, compares them, and reports
whether the tables the benchmark needs actually exist.

Run from the backend directory:

    python scripts/diagnose_database_38_schema.py            # defaults to id 38
    python scripts/diagnose_database_38_schema.py 41         # any other id

Nothing is written or changed. This does not touch SQL generation, scoring,
the schema-linker, or Phase 4.
"""

import os
import re
import sys
import sqlite3

# make the backend package importable when run as scripts/<file>.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database_service import get_database, get_database_tables  # noqa: E402

# tables the bq023 / Query-1 benchmark expects to exist
REQUIRED_TABLES = ["zipcode_to_census_tracts", "censustract_2018_5yr"]

# keyword families to surface "similar" tables/columns
NAME_KEYWORDS = ["zip", "tract", "census", "2018", "5yr", "income", "pop"]
COLUMN_KEYWORDS = ["zip", "tract", "median_income", "total_pop", "population",
                   "geo", "income"]


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _physical_schema(db_path):
    """{table_name: [column_name, ...]} from the physical SQLite file, or None
    if the file can't be opened."""
    if not db_path or not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5.0)
    except sqlite3.Error as exc:
        print(f"  !! cannot open physical DB: {exc}")
        return None
    out = {}
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' ORDER BY name")
        for (name,) in cur.fetchall():
            try:
                cur.execute(f'PRAGMA table_info("{name}")')
                out[name] = [r[1] for r in cur.fetchall()]
            except sqlite3.Error:
                out[name] = []
    except sqlite3.Error as exc:
        print(f"  !! error reading sqlite_master: {exc}")
    finally:
        conn.close()
    return out


def _matches(names, keywords):
    return sorted(n for n in names
                  if any(k in n.lower() for k in keywords))


def _exists(names, target):
    """Exact (case-insensitive) or separator-insensitive match."""
    tl = target.lower()
    tn = _norm(target)
    for n in names:
        if n.lower() == tl or _norm(n) == tn:
            return n
    return None


def main(database_id):
    print("=" * 72)
    print(f"DATABASE SCHEMA DIAGNOSIS — database_id={database_id}")
    print("=" * 72)

    db = get_database(database_id)
    if not db:
        print(f"database_id={database_id} NOT FOUND in app_data.db 'databases'.")
        print("Recommended fix: correct the benchmark DB id, or (re)build the DB.")
        return
    db_path = db.get("db_path")
    print(f"database name : {db.get('name')}")
    print(f"database file : {db_path}")
    print(f"file exists   : {bool(db_path and os.path.exists(db_path))}")

    # -- metadata --------------------------------------------------------
    try:
        meta_rows = get_database_tables(database_id)
    except Exception as exc:
        meta_rows = []
        print(f"  !! get_database_tables error: {exc}")
    meta_names = [r["table_name"] for r in meta_rows]
    print(f"\nMETADATA (database_tables) count: {len(meta_names)}")

    # -- physical --------------------------------------------------------
    phys = _physical_schema(db_path)
    if phys is None:
        print("PHYSICAL SQLite file could not be read — cannot compare.")
        print("Recommended fix: verify db_path is correct and the file exists.")
        return
    phys_names = sorted(phys.keys())
    print(f"PHYSICAL SQLite table count: {len(phys_names)}")

    # -- compare ---------------------------------------------------------
    meta_set = {n.lower() for n in meta_names}
    phys_set = {n.lower() for n in phys_names}
    physical_only = sorted(n for n in phys_names if n.lower() not in meta_set)
    metadata_only = sorted(n for n in meta_names if n.lower() not in phys_set)
    print(f"\nphysical-only tables (in file, NOT in metadata): {len(physical_only)}")
    for n in physical_only[:40]:
        print(f"   - {n}")
    if len(physical_only) > 40:
        print(f"   ... (+{len(physical_only) - 40} more)")
    print(f"\nmetadata-only tables (in metadata, NOT in file): {len(metadata_only)}")
    for n in metadata_only[:40]:
        print(f"   - {n}")

    # -- keyword matches -------------------------------------------------
    print("\nPHYSICAL tables matching zip/tract/census/2018/5yr/income/pop:")
    for n in _matches(phys_names, NAME_KEYWORDS):
        cols = phys.get(n) or []
        hot = [c for c in cols if any(k in c.lower() for k in COLUMN_KEYWORDS)]
        print(f"   - {n}  cols≈{hot or cols[:6]}")

    # -- required tables -------------------------------------------------
    print("\nREQUIRED bq023 tables:")
    result = {}
    for t in REQUIRED_TABLES:
        p = _exists(phys_names, t)
        m = _exists(meta_names, t)
        result[t] = (p, m)
        print(f"   - {t}: physical={p or 'MISSING'}  metadata={m or 'MISSING'}")

    # -- verdict ---------------------------------------------------------
    print("\n" + "-" * 72)
    all_phys = all(result[t][0] for t in REQUIRED_TABLES)
    all_meta = all(result[t][1] for t in REQUIRED_TABLES)
    if all_phys and all_meta:
        print("VERDICT: tables exist in BOTH physical DB and metadata.")
        print("If Query 1 still fails, the mismatch is elsewhere (not schema).")
    elif all_phys and not all_meta:
        print("VERDICT — CASE B: required tables exist PHYSICALLY but are MISSING "
              "from database_tables metadata.")
        print("Recommended fix: metadata sync — re-register every physical table "
              "into database_tables (+ table_columns) for this database_id.")
    elif not all_phys:
        # maybe present under different names (Case C)?
        similar = _matches(phys_names, ["zip", "tract", "census"])
        if similar:
            print("VERDICT — CASE A/C: at least one required table is NOT present "
                  "physically under the expected name.")
            print("Possible CASE C — similar tables exist under other names "
                  f"(see the keyword list above): {similar[:15]}")
            print("Recommended fix: if the data exists under different names, point "
                  "the benchmark at the real names; otherwise rebuild DB "
                  f"{database_id}.")
        else:
            print("VERDICT — CASE A: required tables do NOT exist physically and no "
                  "similar tables were found.")
            print(f"Recommended fix: DB {database_id} was built/uploaded "
                  "incompletely — REBUILD it, or point the benchmark at the "
                  "correct database id. Do NOT patch around missing data.")
    print("-" * 72)

    # -- machine-readable summary (for the report) -----------------------
    print("\nSUMMARY:")
    print(f"  physical_table_count = {len(phys_names)}")
    print(f"  metadata_table_count = {len(meta_names)}")
    for t in REQUIRED_TABLES:
        p, m = result[t]
        print(f"  {t}: physical={'YES' if p else 'NO'} metadata={'YES' if m else 'NO'}")


if __name__ == "__main__":
    _id = int(sys.argv[1]) if len(sys.argv) > 1 else 38
    main(_id)
