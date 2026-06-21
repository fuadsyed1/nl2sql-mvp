"""
merge_smoke_test.py — offline verification of Phases 1–4.

Run from the backend directory (where the modules live):

    python merge_smoke_test.py

It uses a throwaway database and temp CSVs, exercises the full pipeline
(create database -> load tables -> extract columns -> detect relationships),
asserts the expected results, and cleans up after itself. It does NOT touch
your real app_data.db and does NOT require the web server or Ollama.
"""

import os
import sqlite3
import tempfile
import shutil

# Redirect persistence to a throwaway DB BEFORE importing the services.
import auth_db
import database_service as dbsvc

_TMP = tempfile.mkdtemp(prefix="nl2sql_smoke_")
auth_db.DB_NAME = os.path.join(_TMP, "smoke_app_data.db")
dbsvc.DB_NAME = auth_db.DB_NAME

from csv_to_sqlite_loader import load_csv_to_sqlite, clean_table_name
from csv_schema_detector import detect_csv_schema
from schema_extractor import extract_table_columns
from relationship_detector import detect_relationships


def main():
    auth_db.init_auth_db()

    # --- sanity: all new tables exist -----------------------------------
    conn = sqlite3.connect(auth_db.DB_NAME)
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    conn.close()
    for t in ["databases", "database_tables", "table_columns", "database_relationships"]:
        assert t in names, f"missing table: {t}"
    print("[1] schema    : new tables present:", sorted(
        t for t in names if t in
        {"databases", "database_tables", "table_columns", "database_relationships"}
    ))

    # --- a user to own the database -------------------------------------
    conn = sqlite3.connect(auth_db.DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT INTO users(username, password) VALUES('smoke','x')")
    conn.commit()
    user_id = cur.lastrowid
    conn.close()

    # --- sample relational CSVs (owners / pets / owns junction) ---------
    csv_dir = os.path.join(_TMP, "csvs")
    os.makedirs(csv_dir, exist_ok=True)
    open(f"{csv_dir}/Owners.csv", "w").write(
        "OID,LastName,City\n10,Smith,Moscow\n11,Jones,Boise\n12,Lee,Pullman\n")
    open(f"{csv_dir}/Pets.csv", "w").write(
        "PetID,Name,Species\n1,Rex,dog\n2,Milo,cat\n3,Zoe,cat\n4,Ace,dog\n")
    open(f"{csv_dir}/Owns.csv", "w").write(
        "OID,PetID\n10,1\n10,2\n11,3\n12,1\n")

    # --- Phase 1/2: create database, load each CSV into its own table ---
    db_id = dbsvc.create_database(user_id, "PetShop", conversation_id=None)
    db_path = os.path.join(_TMP, "petshop.db")
    dbsvc.set_database_path(db_id, db_path)

    for fname in ["Owners.csv", "Pets.csv", "Owns.csv"]:
        path = f"{csv_dir}/{fname}"
        tname = clean_table_name(fname)
        schema_text = detect_csv_schema(path, table_name=tname)
        res = load_csv_to_sqlite(path, db_path=db_path, table_name=tname)
        tid = dbsvc.add_database_table(
            db_id, tname, fname, path, schema_text, res["rows_inserted"])
        # Phase 3:
        dbsvc.add_table_columns(tid, extract_table_columns(db_path, tname))

    loaded = sqlite3.connect(db_path).execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    loaded = [r[0] for r in loaded]
    assert loaded == ["owners", "owns", "pets"], loaded
    print("[2] load      : tables in petshop.db:", loaded)

    # --- Phase 3: per-column metadata -----------------------------------
    schema = dbsvc.get_database_schema(db_id)
    pets = next(t for t in schema["tables"] if t["table_name"] == "pets")
    petid = next(c for c in pets["columns"] if c["column_name"] == "petid")
    assert petid["is_primary_key_candidate"] is True
    assert petid["data_type"] == "INTEGER"
    assert petid["null_count"] == 0 and petid["unique_count"] == 4
    print("[3] columns   : pets.petid -> type=%s nulls=%d unique=%d pk_candidate=%s"
          % (petid["data_type"], petid["null_count"], petid["unique_count"],
             petid["is_primary_key_candidate"]))

    # --- Phase 4: relationship detection --------------------------------
    edges = detect_relationships(db_id)
    dbsvc.add_relationships(db_id, edges)
    links = {(e["from_table"], e["from_column"], e["to_table"], e["to_column"]): e
             for e in edges}
    assert ("owns", "oid", "owners", "oid") in links
    assert ("owns", "petid", "pets", "petid") in links
    assert all(links[k]["confirmed"] for k in links), "both FKs should auto-confirm"
    print("[4] relations :")
    for e in sorted(edges, key=lambda x: -x["confidence"]):
        print("      %s.%s -> %s.%s  [%s]  overlap=%s conf=%s confirmed=%s"
              % (e["from_table"], e["from_column"], e["to_table"], e["to_column"],
                 e["relationship_type"], e["value_overlap"], e["confidence"],
                 e["confirmed"]))

    # --- graph getter round-trip ----------------------------------------
    graph = dbsvc.get_database_graph(db_id)
    assert len(graph["tables"]) == 3 and len(graph["relationships"]) == 2
    print("[5] graph     : %d tables + %d edges"
          % (len(graph["tables"]), len(graph["relationships"])))

    print("\nALL PHASES 1-4 VERIFIED")


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
