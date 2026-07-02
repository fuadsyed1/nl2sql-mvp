"""
benchmarks/gold_eval.py

Automatic semantic grading against gold SQL (benchmarks/gold_sql.py).

grade(benchmark, index, question, generated_sql, params) executes BOTH the
gold SQL and the generated SQL against the benchmark database (read-only) and
compares result SETS, so SQL style never matters:

  match_level:
    strict        same #columns, same rows (order-insensitive, values
                  normalized: case/whitespace/float rounding)
    column_order  same rows with columns permuted
    subset        every gold column can be matched to a generated column and
                  the projected rows agree (generated SELECTed extra columns)
    none          result sets differ
  Plus flags: both_empty (a weak trivial match), gold_error, gen_error.

The cyber database (id 30) is schema-only, so it is graded on a deterministic
SEEDED COPY built next to this file (benchmarks/eval_dbs/db_30_eval.db) —
the user's database is never modified.
"""

import os
import re
import sqlite3

from benchmarks.gold_sql import GOLD, get_gold

__all__ = ["grade", "eval_db_path", "ROW_CAP"]

ROW_CAP = 5000
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)


# ---------------------------------------------------------------------------
# database resolution (+ seeded eval copy for schema-only DBs)
# ---------------------------------------------------------------------------
def _registered_path(database_id):
    con = sqlite3.connect(os.path.join(_BACKEND, "app_data.db"))
    try:
        row = con.execute("SELECT db_path FROM databases WHERE id=?",
                          (database_id,)).fetchone()
    finally:
        con.close()
    if not row:
        return None
    rel = str(row[0]).replace("\\", os.sep).replace("/", os.sep)
    return rel if os.path.isabs(rel) else os.path.join(_BACKEND, rel)


def _is_empty_db(path):
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            tables = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
            return all(
                con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] == 0
                for t in tables) if tables else True
        finally:
            con.close()
    except sqlite3.Error:
        return False


def eval_db_path(database_id):
    """Path to grade against: the real DB, or a seeded copy when it is
    schema-only (currently the cyber DB)."""
    real = _registered_path(database_id)
    if real is None or not os.path.exists(real):
        return None
    if not _is_empty_db(real):
        return real
    seeded = os.path.join(_HERE, "eval_dbs", f"db_{database_id}_eval.db")
    if not os.path.exists(seeded) or _is_empty_db(seeded):
        os.makedirs(os.path.dirname(seeded), exist_ok=True)
        _build_seeded_copy(real, seeded)
    return seeded


def _build_seeded_copy(schema_src, dest):
    """Copy the schema of `schema_src` into `dest` and fill it with
    deterministic synthetic data (seed=42). Only knows the cyber schema."""
    import random
    import shutil
    import tempfile
    rng = random.Random(42)
    src = sqlite3.connect(f"file:{schema_src}?mode=ro", uri=True)
    creates = [r[0] for r in src.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL")]
    src.close()
    # build in a local temp file first (network/mounted paths can fail sqlite
    # journaling), then copy into place.
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(tmp)
    con = sqlite3.connect(tmp)
    cur = con.cursor()
    for c in creates:
        cur.execute(c)

    deps = ["security", "engineering", "finance", "hr"]
    cities = ["Boise", "Spokane", "Moscow", "Pullman"]
    sevs = ["critical", "high", "medium", "low"]

    # employees: ids 1..8 are managers (2 per department), 9..32 report to one.
    emps = []
    for i in range(1, 33):
        dep = deps[(i - 1) % 4]
        city = cities[(i * 3) % 4]
        risk = round(rng.uniform(1, 10), 1)
        if i <= 8:
            mgr = None
        else:
            pair = [((i - 1) % 4) + 1, ((i - 1) % 4) + 5]
            mgr = rng.choice(pair)
        emps.append((i, f"emp_{i:02d}", dep, city, risk, mgr))
    cur.executemany("INSERT INTO employees VALUES (?,?,?,?,?,?)", emps)

    dtypes = ["laptop", "desktop", "server", "mobile"]
    osf = ["windows", "linux", "macos", "android"]
    devs = []
    for i in range(1, 46):
        emp = rng.randint(1, 32)
        devs.append((i, emp, f"host{i:02d}", rng.choice(dtypes), rng.choice(osf),
                     rng.choice(["yes", "no"]),
                     f"2026-0{rng.randint(1, 5)}-{rng.randint(1, 28):02d}"))
    cur.executemany("INSERT INTO devices VALUES (?,?,?,?,?,?,?)", devs)

    vulns = []
    for i in range(1, 25):
        # ids 17..24 reuse CVE codes 1..8 with different scores (dup codes)
        code = f"CVE-2026-{1000 + (i if i <= 16 else i - 16)}"
        vulns.append((i, code, rng.choice(sevs), round(rng.uniform(2, 10), 1),
                      f"2026-0{rng.randint(1, 4)}-{rng.randint(1, 28):02d}",
                      rng.choice(["yes", "no"])))
    cur.executemany("INSERT INTO vulnerabilities VALUES (?,?,?,?,?,?)", vulns)

    dvs = []
    for i in range(1, 91):
        det = f"2026-0{rng.randint(2, 5)}-{rng.randint(1, 28):02d}"
        rem = None if rng.random() < 0.5 else f"2026-06-{rng.randint(1, 28):02d}"
        dvs.append((i, rng.randint(1, 45), rng.randint(1, 24), det, rem,
                    "yes" if rng.random() < 0.1 else "no"))
    cur.executemany("INSERT INTO device_vulnerabilities VALUES (?,?,?,?,?,?)", dvs)

    atypes = ["malware", "phishing", "intrusion", "dlp"]
    alerts = []
    for i in range(1, 81):
        alerts.append((i, rng.randint(1, 45), rng.choice(atypes), rng.choice(sevs),
                       f"2026-0{rng.randint(3, 6)}-{rng.randint(1, 28):02d} "
                       f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}",
                       f"10.0.{rng.randint(0, 255)}.{rng.randint(1, 254)}",
                       rng.choice(["yes", "no"])))
    cur.executemany("INSERT INTO alerts VALUES (?,?,?,?,?,?,?)", alerts)

    itypes = ["breach", "outage", "ransomware"]
    incs = []
    for i in range(1, 26):
        opened = (f"2026-0{rng.randint(3, 6)}-{rng.randint(1, 28):02d} "
                  f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}")
        closed = None if rng.random() < 0.3 else f"2026-06-{rng.randint(1, 28):02d} 12:00"
        incs.append((i, rng.randint(1, 32), rng.choice(itypes), opened, closed,
                     rng.choice(["high", "medium", "low"]),
                     rng.choice(["phishing", "misconfig", "unpatched", "unknown"])))
    cur.executemany("INSERT INTO incidents VALUES (?,?,?,?,?,?,?)", incs)

    cur.executemany("INSERT INTO incident_alerts VALUES (?,?,?)",
                    [(i, rng.randint(1, 25), rng.randint(1, 80))
                     for i in range(1, 31)])

    courses = ["phishing awareness", "secure coding", "data handling",
               "incident response"]
    trs = []
    for i in range(1, 61):
        score = rng.randint(40, 100)
        trs.append((i, rng.randint(1, 32), rng.choice(courses),
                    f"2026-0{rng.randint(1, 6)}-{rng.randint(1, 28):02d}",
                    score, "yes" if score >= 60 else "no"))
    cur.executemany("INSERT INTO training_records VALUES (?,?,?,?,?,?)", trs)
    con.commit()
    con.close()
    shutil.copyfile(tmp, dest)
    os.remove(tmp)


# ---------------------------------------------------------------------------
# execution + result comparison
# ---------------------------------------------------------------------------
def _run(db_path, sql, params=None):
    """(columns, rows, error). rows capped at ROW_CAP+1 to detect overflow."""
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return None, None, f"db_unavailable: {exc}"
    try:
        cur = con.execute(sql, list(params or []))
        cols = [d[0] for d in (cur.description or [])]
        rows = cur.fetchmany(ROW_CAP + 1)
        return cols, [list(r) for r in rows], None
    except sqlite3.Error as exc:
        return None, None, str(exc)
    finally:
        con.close()


def _norm(v):
    if v is None:
        return "∅"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        f = float(v)
        return str(int(f)) if f == int(f) else f"{f:.6g}"
    return re.sub(r"\s+", " ", str(v).strip().lower())


def _norm_rows(rows):
    return sorted(tuple(_norm(v) for v in r) for r in rows)


def _subset_match(gold_rows, gen_rows):
    """True when each gold column maps (injectively) to a generated column and
    the projected generated rows equal the gold rows as a multiset."""
    if len(gold_rows) != len(gen_rows):
        return False
    if not gold_rows:
        return True
    k, m = len(gold_rows[0]), len(gen_rows[0])
    if k > m:
        return False
    gold_cols = [sorted(r[i] for r in gold_rows) for i in range(k)]
    gen_cols = [sorted(r[j] for r in gen_rows) for j in range(m)]
    cand = [[j for j in range(m) if gen_cols[j] == gold_cols[i]] for i in range(k)]

    target = sorted(gold_rows)

    def bt(i, used, mapping):
        if i == k:
            proj = sorted(tuple(r[j] for j in mapping) for r in gen_rows)
            return proj == target
        for j in cand[i]:
            if j not in used:
                if bt(i + 1, used | {j}, mapping + [j]):
                    return True
        return False

    return bt(0, set(), [])


def compare_results(gold_cols, gold_rows, gen_cols, gen_rows):
    """-> (match_level, both_empty)."""
    g, h = _norm_rows(gold_rows), _norm_rows(gen_rows)
    both_empty = not g and not h
    if len(gold_cols) == len(gen_cols) and g == h:
        return "strict", both_empty
    rg = sorted(tuple(sorted(r)) for r in g)
    rh = sorted(tuple(sorted(r)) for r in h)
    if len(gold_cols) == len(gen_cols) and rg == rh:
        return "column_order", both_empty
    if _subset_match(g, h):
        return "subset", both_empty
    if _subset_match(h, g):
        return "gen_subset", both_empty
    return "none", both_empty


def grade(benchmark, index_1based, question, generated_sql, params=None):
    """Grade one generated query against gold. Never raises."""
    out = {"benchmark": benchmark, "index": index_1based, "gold_found": False,
           "match_level": "none", "semantic_ok": False, "both_empty": False,
           "gold_rows": None, "gen_rows": None, "gold_error": None,
           "gen_error": None, "note": None}
    try:
        entry = get_gold(benchmark, index_1based, question)
        if entry is None:
            out["note"] = "no gold entry / question mismatch"
            return out
        out["gold_found"] = True
        out["note"] = entry.get("note")
        db_path = eval_db_path(GOLD[benchmark]["database_id"])
        if db_path is None:
            out["gold_error"] = "database not found"
            return out

        gcols, grows, gerr = _run(db_path, entry["sql"])
        out["gold_error"] = gerr
        if gerr:
            return out
        out["gold_rows"] = len(grows)

        if not generated_sql:
            out["gen_error"] = "no SQL generated"
            return out
        hcols, hrows, herr = _run(db_path, generated_sql, params)
        out["gen_error"] = herr
        if herr:
            return out
        out["gen_rows"] = len(hrows)

        if len(grows) > ROW_CAP or len(hrows) > ROW_CAP:
            out["note"] = (out["note"] or "") + " [row cap exceeded]"
            return out

        level, both_empty = compare_results(gcols, grows, hcols, hrows)
        out["match_level"] = level
        out["both_empty"] = both_empty
        out["semantic_ok"] = level in ("strict", "column_order", "subset", "gen_subset")
        return out
    except Exception as exc:
        out["note"] = f"grader error: {type(exc).__name__}: {exc}"
        return out
