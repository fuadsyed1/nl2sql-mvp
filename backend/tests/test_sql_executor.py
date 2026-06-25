"""
test_sql_executor.py — offline test for Phase 8 step 2.

Builds a temporary PetShop SQLite database and exercises execute_sql end to end
(no server, no LLM, no pytest):

    python test_sql_executor.py
"""

import os
import sqlite3
import tempfile

from generation.sql_executor import execute_sql
from generation.execution_result import to_dict
from generation.sql_types import generated_sql as gen_sql, failed_sql, to_dict as sql_to_dict

JOIN_SQL = (
    'SELECT DISTINCT "owners"."lastname" '
    'FROM "owners" '
    'INNER JOIN "owns" ON "owners"."oid" = "owns"."oid" '
    'INNER JOIN "pets" ON "owns"."petid" = "pets"."petid" '
    'WHERE "pets"."species" = ?'
)


def build_petshop(path):
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute("CREATE TABLE owners (oid INTEGER, lastname TEXT, city TEXT)")
    c.execute("CREATE TABLE owns (oid INTEGER, petid INTEGER)")
    c.execute("CREATE TABLE pets (petid INTEGER, name TEXT, species TEXT)")
    c.executemany("INSERT INTO owners VALUES (?,?,?)",
                  [(1, "Smith", "Moscow"), (2, "Jones", "Boise"), (3, "Lee", "Pullman")])
    c.executemany("INSERT INTO pets VALUES (?,?,?)",
                  [(10, "Rex", "dog"), (11, "Milo", "cat"), (12, "Spot", "dog"), (13, "Tom", "cat")])
    # Smith->Rex(dog), Jones->Milo(cat)+Tom(cat), Lee->Spot(dog)
    c.executemany("INSERT INTO owns VALUES (?,?)",
                  [(1, 10), (2, 11), (3, 12), (2, 13)])
    conn.commit()
    conn.close()


def test_success_join(db):
    d = to_dict(execute_sql(gen_sql(JOIN_SQL, params=["dog"]), db))
    assert d["executed"] is True
    assert d["columns"] == ["lastname"], d["columns"]
    assert {r[0] for r in d["rows"]} == {"Smith", "Lee"}, d["rows"]
    assert d["row_count"] == 2 and d["truncated"] is False
    print("[1] successful join query (dogs) -> OK")


def test_param_binding(db):
    d = to_dict(execute_sql(gen_sql(JOIN_SQL, params=["cat"]), db))
    assert d["executed"] is True
    assert {r[0] for r in d["rows"]} == {"Jones"}, d["rows"]
    print("[2] parameter binding (cat returns different rows) -> OK")


def test_not_generated(db):
    # object form
    d1 = to_dict(execute_sql(failed_sql("empty_select"), db))
    assert d1["executed"] is False and d1["reason"] == "not_generated"
    # dict form
    d2 = to_dict(execute_sql({"generated": False, "reason": "unresolved_plan"}, db))
    assert d2["executed"] is False and d2["reason"] == "not_generated"
    print("[3] not_generated (object + dict forms) -> OK")


def test_db_unavailable(tmpdir):
    missing = os.path.join(tmpdir, "does_not_exist.db")
    d = to_dict(execute_sql(gen_sql(JOIN_SQL, params=["dog"]), missing))
    assert d["executed"] is False and d["reason"] == "db_unavailable"
    assert d["error"]
    print("[4] db_unavailable (missing file) -> OK")


def test_sql_error(db):
    bad = gen_sql('SELECT "owners"."nope" FROM "owners"')
    d = to_dict(execute_sql(bad, db))
    assert d["executed"] is False and d["reason"] == "sql_error"
    assert "nope" in d["error"] or "no such column" in d["error"]
    print("[5] sql_error (missing column) -> OK")


def test_read_only_protection(db):
    insert = gen_sql('INSERT INTO owners (oid, lastname, city) VALUES (99, \'X\', \'Y\')')
    d = to_dict(execute_sql(insert, db))
    assert d["executed"] is False and d["reason"] == "sql_error"
    # confirm the DB was NOT modified
    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM owners").fetchone()[0]
    conn.close()
    assert n == 3, f"read-only violated: owners count is {n}"
    print("[6] read-only protection (INSERT rejected, DB unchanged) -> OK")


def test_truncation(db):
    # 3 owners; cap at 2 -> truncated
    d = to_dict(execute_sql(gen_sql('SELECT "owners"."lastname" FROM "owners"'), db, row_limit=2))
    assert d["executed"] is True
    assert d["truncated"] is True
    assert d["row_count"] == 2 and len(d["rows"]) == 2
    # cap >= count -> not truncated
    d2 = to_dict(execute_sql(gen_sql('SELECT "owners"."lastname" FROM "owners"'), db, row_limit=10))
    assert d2["truncated"] is False and d2["row_count"] == 3
    print("[7] truncation (row_limit < count) -> OK")


def test_deterministic_and_no_mutation(db):
    g = gen_sql(JOIN_SQL, params=["dog"])
    snapshot = sql_to_dict(g)
    a = to_dict(execute_sql(g, db))
    b = to_dict(execute_sql(g, db))
    assert a == b, "execution must be deterministic"
    assert sql_to_dict(g) == snapshot, "generated_sql must not be mutated"
    # dict form yields the same result as the object form
    c = to_dict(execute_sql(sql_to_dict(g), db))
    assert c == a, "dict input must match object input"
    print("[8] deterministic + no mutation + dict==object input -> OK")


def main():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = os.path.join(tmpdir, "petshop.db")
        build_petshop(db)

        tests = [
            lambda: test_success_join(db),
            lambda: test_param_binding(db),
            lambda: test_not_generated(db),
            lambda: test_db_unavailable(tmpdir),
            lambda: test_sql_error(db),
            lambda: test_read_only_protection(db),
            lambda: test_truncation(db),
            lambda: test_deterministic_and_no_mutation(db),
        ]
        passed = 0
        for t in tests:
            t()
            passed += 1
        print(f"\nRESULT: {passed}/{len(tests)} passed — sql_executor.py verified")


if __name__ == "__main__":
    main()