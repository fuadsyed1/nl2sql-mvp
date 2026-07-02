"""
analyze_spider2_relationship_signals.py

DIAGNOSTIC ONLY. Analyzes the locally available Spider 2.0 catalog databases and
reports, per database, what relationship signal exists in the *schema* (not the
data, not gold answers): declared foreign keys, FK-like shared id columns, and
date-partition table families. It changes nothing in the app — no import, no
metadata, no relationship saving, no query-time inference, no SQL, no UI.

Sources used (all local, cheap, deterministic — no LLM, no BigQuery, no rows):
  * DDL.csv  (table_name + CREATE TABLE text)  -> table names, column names,
    declared-FK text.
Partition families are detected from table names; each family is collapsed to a
single representative before column parsing so cost stays bounded even for
date-partitioned datasets with hundreds of tables.

Run:
    cd C:\\Projects\\nl2sql-mvp\\backend
    python tools/analyze_spider2_relationship_signals.py

Writes: backend/reports/spider2_relationship_signal_summary.json
Prints: a short console summary.
"""

import os
import re
import csv
import json
import glob
import datetime
from collections import defaultdict

# Spider 2.0 DDLs can have very large fields (wide BigQuery STRUCT columns).
try:
    csv.field_size_limit(16 * 1024 * 1024)
except OverflowError:  # pragma: no cover - platform dependent
    csv.field_size_limit(2 ** 31 - 1)

_DIALECTS = {"bigquery", "snowflake", "sqlite"}
_CONSTRAINT_KW = {"primary", "foreign", "unique", "check", "constraint", "key",
                  "partition", "cluster"}
_PARTITION_RE = re.compile(r"^(.*)_(\d{6,8})$")  # <prefix>_YYYYMM(DD)
_FK_RE = re.compile(r"\bFOREIGN\s+KEY\b", re.IGNORECASE)
_LOCAL_DEV_FALLBACK = r"C:\Datasets\Spider2"
_COLBODY_CAP = 50000  # cap column-body chars parsed per table (bounds STRUCTs)
_TOP_N = 20

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPORT_PATH = os.path.join(_HERE, "..", "reports",
                            "spider2_relationship_signal_summary.json")


def _resolve_root():
    for cand in (os.getenv("SPIDER2_DATA_DIR"), _LOCAL_DEV_FALLBACK):
        if not cand:
            continue
        p = os.path.abspath(
            os.path.expanduser(str(cand).strip().strip('"').strip("'"))
        )
        if os.path.isdir(p):
            return p
    return None


def _build_index(root):
    """db (lowercased) -> {db, dialect, dirs:[dataset folders]} via bounded globs."""
    idx = {}
    patterns = [
        os.path.join(root, "*", "resource", "databases", "*", "*", "DDL.csv"),
        os.path.join(root, "*", "resource", "databases", "*", "*", "*", "DDL.csv"),
    ]
    for pat in patterns:
        for ddl in glob.glob(pat):
            parts = ddl.replace("\\", "/").split("/")
            for i, p in enumerate(parts):
                if p in _DIALECTS and i > 0 and parts[i - 1] == "databases":
                    if i + 1 < len(parts):
                        db = parts[i + 1]
                        e = idx.setdefault(
                            db.lower(), {"db": db, "dialect": p, "dirs": set()}
                        )
                        e["dirs"].add(os.path.dirname(ddl))
                    break
    return idx


def _read_ddls(dirs):
    """Return [(table_name, ddl_text), ...] across a db's dataset folders."""
    rows = []
    for d in dirs:
        path = os.path.join(d, "DDL.csv")
        try:
            with open(path, encoding="utf-8", errors="replace", newline="") as fh:
                for row in csv.DictReader(fh):
                    low = {(k or "").lower(): v for k, v in row.items()}
                    tn = low.get("table_name")
                    if tn:
                        rows.append((tn, low.get("ddl") or ""))
        except (OSError, csv.Error, UnicodeError):
            continue
    return rows


def _column_names(ddl):
    """Cheap, bounded column-name extraction (names only, not types)."""
    i = ddl.find("(")
    j = ddl.rfind(")")
    if i < 0 or j <= i:
        return []
    body = ddl[i + 1:j][:_COLBODY_CAP]
    names, buf, depth = [], [], 0

    def _flush():
        seg = "".join(buf).strip()
        if not seg:
            return
        toks = seg.split()
        first = toks[0].strip('`"[]') if toks else ""
        if first and first.lower() not in _CONSTRAINT_KW:
            names.append(first)

    for ch in body:
        if ch in "(<":
            depth += 1
            buf.append(ch)
        elif ch in ")>":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == "," and depth == 0:
            _flush()
            buf = []
        else:
            buf.append(ch)
    _flush()
    return names


def _partition_prefix(name):
    m = _PARTITION_RE.match(name)
    return m.group(1) if m else None


def _analyze_db(db, dialect, dirs):
    rows = _read_ddls(dirs)
    table_count = len(rows)
    if table_count == 0:
        return None

    # Declared FK count (cheap text scan of the DDL).
    declared_fk_count = sum(len(_FK_RE.findall(ddl)) for _, ddl in rows)

    # Partition families from table names.
    fam = defaultdict(list)
    for tn, _ddl in rows:
        pre = _partition_prefix(tn)
        if pre is not None:
            fam[pre].append(tn)
    families = {p: m for p, m in fam.items() if len(m) >= 2}
    partition_group_count = len(families)
    partition_table_count = sum(len(m) for m in families.values())
    member_to_prefix = {m: p for p, ms in families.items() for m in ms}

    # Representatives: one per family member-set, plus all non-family tables.
    ddl_by_table = {tn: ddl for tn, ddl in rows}
    rep_tables, seen_fam = [], set()
    for tn, _ddl in rows:
        p = member_to_prefix.get(tn)
        if p is not None:
            if p in seen_fam:
                continue
            seen_fam.add(p)
        rep_tables.append(tn)

    cols_by_rep = {tn: _column_names(ddl_by_table[tn]) for tn in rep_tables}
    column_count = sum(len(c) for c in cols_by_rep.values())

    # FK-like shared id columns across representatives (column-name based only).
    col_to_tables = defaultdict(set)
    for tn, cols in cols_by_rep.items():
        for c in cols:
            lc = c.lower()
            if lc.endswith("_id") or lc == "id":
                col_to_tables[lc].add(tn)
    inferred_join_candidate_count = sum(
        len(ts) - 1 for ts in col_to_tables.values() if len(ts) >= 2
    )

    has_fk = declared_fk_count > 0
    partition_dominant = (
        partition_group_count >= 1
        and partition_table_count >= 0.5 * table_count
    )
    has_join = inferred_join_candidate_count > 0

    if has_fk:
        classification = "declared_fk_schema"
    elif partition_dominant and has_join:
        classification = "mixed"
    elif partition_dominant:
        classification = "partition_family_schema"
    elif has_join:
        classification = "inferable_join_schema"
    else:
        classification = "messy_or_no_join_signal"

    return {
        "database": db,
        "dialect": dialect,
        "source_type": "local_spider2_metadata",
        "table_count": table_count,
        "representative_table_count": len(rep_tables),
        "column_count": column_count,
        "declared_fk_count": declared_fk_count,
        "inferred_join_candidate_count": inferred_join_candidate_count,
        "partition_group_count": partition_group_count,
        "partition_table_count": partition_table_count,
        "classification": classification,
    }


def analyze(root):
    index = _build_index(root)
    results = []
    for key in sorted(index):
        info = index[key]
        r = _analyze_db(info["db"], info["dialect"], info["dirs"])
        if r:
            results.append(r)

    by_class = defaultdict(int)
    for r in results:
        by_class[r["classification"]] += 1

    totals = {
        "total_databases": len(results),
        "with_declared_fk": sum(1 for r in results if r["declared_fk_count"] > 0),
        "with_inferable_joins": sum(
            1 for r in results if r["inferred_join_candidate_count"] > 0
        ),
        "partition_family": by_class["partition_family_schema"] + by_class["mixed"],
        "no_join_signal": by_class["messy_or_no_join_signal"],
        "by_classification": dict(by_class),
    }

    best_inferable = sorted(
        [r for r in results if r["inferred_join_candidate_count"] > 0],
        key=lambda r: (-r["inferred_join_candidate_count"], -r["declared_fk_count"],
                       r["database"]),
    )[:_TOP_N]
    partition_family = sorted(
        [r for r in results if r["partition_group_count"] > 0],
        key=lambda r: (-r["partition_table_count"], -r["partition_group_count"],
                       r["database"]),
    )[:_TOP_N]
    biggest_messy = sorted(
        [r for r in results if r["classification"] == "messy_or_no_join_signal"],
        key=lambda r: (-r["table_count"], -r["column_count"], r["database"]),
    )[:_TOP_N]

    return {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "root": root,
        "totals": totals,
        "top": {
            "best_inferable": best_inferable,
            "partition_family": partition_family,
            "biggest_messy": biggest_messy,
        },
        "databases": results,
    }


def _print_summary(report):
    t = report["totals"]
    print(f"Spider 2.0 relationship-signal summary")
    print(f"  source: {report['root']}")
    print(f"  total databases:        {t['total_databases']}")
    print(f"  with declared FK:       {t['with_declared_fk']}")
    print(f"  with inferable joins:   {t['with_inferable_joins']}")
    print(f"  partition-family:       {t['partition_family']}")
    print(f"  no join signal:         {t['no_join_signal']}")
    print(f"  by classification:      {t['by_classification']}")

    def _line(r):
        return (f"    {r['database']} [{r['dialect']}] "
                f"tables={r['table_count']} cols={r['column_count']} "
                f"fk={r['declared_fk_count']} join_cand="
                f"{r['inferred_join_candidate_count']} "
                f"part_groups={r['partition_group_count']} -> {r['classification']}")

    print("  top inferable schemas:")
    for r in report["top"]["best_inferable"][:5]:
        print(_line(r))
    print("  top partition-family schemas:")
    for r in report["top"]["partition_family"][:5]:
        print(_line(r))
    print("  biggest messy / no-join schemas:")
    for r in report["top"]["biggest_messy"][:5]:
        print(_line(r))


def main():
    root = _resolve_root()
    if not root:
        print("Spider 2.0 data source not configured. Set SPIDER2_DATA_DIR "
              "to your local Spider2 clone, or place it at "
              f"{_LOCAL_DEV_FALLBACK}.")
        return 1

    report = analyze(root)
    os.makedirs(os.path.dirname(_REPORT_PATH), exist_ok=True)
    with open(_REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    _print_summary(report)
    print(f"\nFull JSON report: {os.path.abspath(_REPORT_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
