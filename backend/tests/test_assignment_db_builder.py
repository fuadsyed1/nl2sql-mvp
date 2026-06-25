"""
test_assignment_db_builder.py

Standalone unit tests for assignment_db_builder (Mode B / Mode C empty-table
creation). No app database, no Ollama. Run with:

    python test_assignment_db_builder.py
"""

import os
import sqlite3
import tempfile

from assignment.assignment_parser import extract_assignment_spec
from assignment.assignment_db_builder import build_empty_database, normalize_spec


PETFOOD = """\
Pets(PetID, Name, Age, Street, City, ZipCode, State, TypeofPet)
Owners(OID, LastName, Street, City, ZipCode, State, Age, AnnualIncome)
Owns(PetID, Year, OID, PetAgeatOwnership, PricePaid)
Likes(PetID, TypeofFood)
Foods(FoodID, Name, Brand, TypeofFood, Price, ItemWeight, ClassofFood)
Purchases(OID, FoodID, PetID, Month, Year, Quantity)

Write SQL for:
1. List all cats aged at least 2.
2. List all owners and their pets who own at least two pets.
"""


def _tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)            # let sqlite create it fresh
    return path


def _tables_in(db_path):
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    conn.close()
    return sorted(r[0] for r in rows)


def _columns_of(db_path, table):
    conn = sqlite3.connect(db_path)
    info = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    conn.close()
    return info  # (cid, name, type, notnull, dflt, pk)


def test_creates_all_tables_normalized():
    spec = extract_assignment_spec(PETFOOD)
    db = _tmp_db()
    try:
        build_empty_database(spec, db)
        assert _tables_in(db) == ["foods", "likes", "owners", "owns", "pets", "purchases"], _tables_in(db)
        print("[1] all six tables created with normalized lowercase names -> OK")
    finally:
        os.remove(db)


def test_tables_are_empty():
    spec = extract_assignment_spec(PETFOOD)
    db = _tmp_db()
    try:
        build_empty_database(spec, db)
        conn = sqlite3.connect(db)
        for t in _tables_in(db):
            n = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            assert n == 0, f"{t} has {n} rows, expected 0"
        conn.close()
        print("[2] every table created empty (no sample data) -> OK")
    finally:
        os.remove(db)


def test_columns_and_types():
    spec = extract_assignment_spec(PETFOOD)
    db = _tmp_db()
    try:
        build_empty_database(spec, db)
        pets = _columns_of(db, "pets")
        names = [c[1] for c in pets]
        assert names == ["petid", "name", "age", "street", "city", "zipcode", "state", "typeofpet"], names
        types = {c[1]: c[2] for c in pets}
        assert types["petid"] == "INTEGER", types
        assert types["name"] == "TEXT", types
        # OID-style key column also INTEGER
        owners_types = {c[1]: c[2] for c in _columns_of(db, "owners")}
        assert owners_types["oid"] == "INTEGER", owners_types
        print("[3] columns normalized; id keys INTEGER, others TEXT -> OK")
    finally:
        os.remove(db)


def test_normalized_relationships():
    spec = extract_assignment_spec(PETFOOD)
    manifest = build_empty_database(spec, _tmp_db_and_keep := _tmp_db())
    try:
        got = {
            (r["from_table"], r["from_column"], r["to_table"], r["to_column"])
            for r in manifest["relationships"]
        }
        expected = {
            ("owns", "petid", "pets", "petid"),
            ("owns", "oid", "owners", "oid"),
            ("likes", "petid", "pets", "petid"),
            ("purchases", "oid", "owners", "oid"),
            ("purchases", "foodid", "foods", "foodid"),
            ("purchases", "petid", "pets", "petid"),
        }
        assert got == expected, f"\n got: {sorted(got)}\n exp: {sorted(expected)}"
        assert manifest["executed"] is False
        assert len(manifest["questions"]) == 2
        print("[4] manifest carries 6 normalized FKs, executed=False, 2 questions -> OK")
    finally:
        os.remove(_tmp_db_and_keep)


def test_idempotent_reimport():
    spec = extract_assignment_spec(PETFOOD)
    db = _tmp_db()
    try:
        build_empty_database(spec, db)
        # second import must not error and must not add rows
        build_empty_database(spec, db)
        assert _tables_in(db) == ["foods", "likes", "owners", "owns", "pets", "purchases"]
        conn = sqlite3.connect(db)
        n = conn.execute('SELECT COUNT(*) FROM "pets"').fetchone()[0]
        conn.close()
        assert n == 0
        print("[5] re-import is idempotent (drop+recreate, still empty) -> OK")
    finally:
        os.remove(db)


def test_quoting_safe_identifiers():
    # spec with a space-y / odd table name still produces a safe identifier
    spec = {"tables": [{"name": "Order Items", "columns": ["Item ID", "Qty"]}],
            "relationships": [], "questions": []}
    norm = normalize_spec(spec)
    assert norm["tables"][0]["name"] == "order_items", norm
    assert [c["name"] for c in norm["tables"][0]["columns"]] == ["item_id", "qty"]
    db = _tmp_db()
    try:
        build_empty_database(spec, db)          # must not raise
        assert _tables_in(db) == ["order_items"]
        print("[6] odd names normalized + quoted into safe identifiers -> OK")
    finally:
        os.remove(db)


def main():
    tests = [
        test_creates_all_tables_normalized,
        test_tables_are_empty,
        test_columns_and_types,
        test_normalized_relationships,
        test_idempotent_reimport,
        test_quoting_safe_identifiers,
    ]
    passed = 0
    for t in tests:
        t()
        passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed -- assignment_db_builder.py verified")


if __name__ == "__main__":
    main()
