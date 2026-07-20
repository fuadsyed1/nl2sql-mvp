"""
test_import_csv_dir_to_sqlite.py — offline tests for the CSV -> SQLite importer.

    python -m pytest backend/tests/test_import_csv_dir_to_sqlite.py -q
"""

import os
import sqlite3
import tempfile

import pytest

from scripts.import_csv_dir_to_sqlite import import_dir, _infer_types


@pytest.fixture()
def csv_dir():
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "People.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("playerID,nameFirst,weight,bats\n")
        f.write("aardsda01,David,215,R\n")
        f.write("abadfe01,Fernando,,L\n")   # empty weight -> NULL
    with open(os.path.join(d, "Batting.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("playerID,yearID,AVG\n")
        f.write("aardsda01,2004,0.0\n")
        f.write("abadfe01,2010,0.25\n")
    yield d
    for name in os.listdir(d):
        os.remove(os.path.join(d, name))
    os.rmdir(d)


def test_type_inference():
    header = ["a", "b", "c"]
    rows = [["1", "1.5", "x"], ["2", "", "y"], ["", "3.0", ""]]
    assert _infer_types(header, rows) == ["INTEGER", "REAL", "TEXT"]


def test_import_creates_tables_and_rows(csv_dir):
    fd, db = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        results = import_dir(csv_dir, db, drop=True)
        by = dict(results)
        assert by["People"] == 2
        assert by["Batting"] == 2

        conn = sqlite3.connect(db)
        # People.weight inferred INTEGER; empty -> NULL
        rows = conn.execute(
            "SELECT playerID, weight FROM People ORDER BY playerID").fetchall()
        assert rows[0] == ("aardsda01", 215)
        assert rows[1] == ("abadfe01", None)
        # Batting.AVG inferred REAL
        types = {r[1]: r[2] for r in conn.execute("PRAGMA table_info(Batting)")}
        assert types["AVG"] == "REAL"
        assert types["yearID"] == "INTEGER"
        # No invented PK/FK.
        pk_cols = [r for r in conn.execute("PRAGMA table_info(People)") if r[5]]
        assert pk_cols == []
        assert conn.execute("PRAGMA foreign_key_list(Batting)").fetchall() == []
        conn.close()
    finally:
        os.remove(db)


def test_missing_dir_raises():
    with pytest.raises(FileNotFoundError):
        import_dir("/no/such/dir", "/tmp/x.sqlite")
