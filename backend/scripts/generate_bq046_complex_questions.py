"""
scripts/generate_bq046_complex_questions.py

Generate 20 complicated NL questions for a SpiderSQL database using ONLY the
actual tables/columns in that database. Default target: database_id=40 (bq046).

Run from the backend directory:

    python scripts/generate_bq046_complex_questions.py
    python scripts/generate_bq046_complex_questions.py --database-id 40

Optional: execute the generated questions through the backend API:

    # first start backend in another terminal: uvicorn app:app --reload
    python scripts/generate_bq046_complex_questions.py --execute

Outputs:
    benchmarks/generated/bq046_complex_questions_db40.json
    benchmarks/generated/bq046_complex_questions_db40.txt
    benchmarks/generated/bq046_complex_results_db40_<timestamp>.json  (--execute only)

This script is read-only against the database. It does not change SQL generation,
scoring, linker, metadata, or Phase 4.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Make backend package importable when this file is run from scripts/<file>.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from db.database_service import get_database, get_database_tables  # type: ignore
except Exception as exc:  # pragma: no cover - host/backend import issue
    print("ERROR: Could not import backend database service.")
    print("Run this script from C:\\Projects\\nl2sql-mvp\\backend")
    print(f"Import error: {exc}")
    raise


@dataclass
class ColumnInfo:
    name: str
    type: str
    notnull: bool = False
    pk: bool = False


@dataclass
class TableInfo:
    name: str
    columns: List[ColumnInfo]
    row_count: Optional[int] = None


@dataclass
class GeneratedQuestion:
    id: int
    difficulty: str
    question_type: str
    tables: List[str]
    columns: List[str]
    question: str
    notes: str


TEXT_HINTS = (
    "name", "type", "status", "category", "class", "state", "city", "country",
    "code", "description", "title", "party", "office", "gender", "race", "region",
)
NUMERIC_HINTS = (
    "amount", "total", "sum", "avg", "average", "count", "num", "number", "price",
    "cost", "score", "rate", "percent", "percentage", "median", "income", "pop",
    "population", "age", "size", "area", "year", "rank", "value", "quantity",
)
DATE_HINTS = ("date", "dt", "time", "timestamp", "year", "month", "day")
ID_HINTS = ("id", "key", "code", "no", "num")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def token_set(s: str) -> set[str]:
    return set(t for t in re.split(r"[^a-z0-9]+", str(s or "").lower()) if t)


def sqlite_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def resolve_db_path(db_path: str) -> str:
    if os.path.isabs(db_path):
        return db_path
    return os.path.abspath(db_path)


def physical_schema(db_path: str, sample_counts: bool = True) -> Dict[str, TableInfo]:
    path = resolve_db_path(db_path)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Physical SQLite DB not found: {path}")

    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10.0)
    out: Dict[str, TableInfo] = {}
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        table_names = [r[0] for r in cur.fetchall()]
        for table in table_names:
            cur.execute(f"PRAGMA table_info({sqlite_ident(table)})")
            cols = [
                ColumnInfo(
                    name=row[1],
                    type=str(row[2] or ""),
                    notnull=bool(row[3]),
                    pk=bool(row[5]),
                )
                for row in cur.fetchall()
            ]
            row_count: Optional[int] = None
            if sample_counts:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {sqlite_ident(table)}")
                    row_count = int(cur.fetchone()[0])
                except sqlite3.Error:
                    row_count = None
            out[table] = TableInfo(name=table, columns=cols, row_count=row_count)
    finally:
        conn.close()
    return out


def is_numeric(col: ColumnInfo) -> bool:
    typ = (col.type or "").upper()
    name = col.name.lower()
    if any(x in typ for x in ("INT", "REAL", "NUM", "DEC", "FLOAT", "DOUBLE")):
        return True
    return any(h in name for h in NUMERIC_HINTS) and not is_date(col)


def is_text(col: ColumnInfo) -> bool:
    typ = (col.type or "").upper()
    name = col.name.lower()
    if any(x in typ for x in ("CHAR", "TEXT", "CLOB", "VARCHAR")):
        return True
    return any(h in name for h in TEXT_HINTS)


def is_date(col: ColumnInfo) -> bool:
    name = col.name.lower()
    typ = (col.type or "").upper()
    return any(h in name for h in DATE_HINTS) or "DATE" in typ or "TIME" in typ


def is_id_like(col: ColumnInfo) -> bool:
    n = col.name.lower()
    return col.pk or n == "id" or n.endswith("_id") or any(h == n or n.endswith("_" + h) for h in ID_HINTS)


def pick(cols: Iterable[ColumnInfo], predicate, fallback: Optional[ColumnInfo] = None) -> Optional[ColumnInfo]:
    for col in cols:
        if predicate(col):
            return col
    return fallback


def table_score(t: TableInfo) -> int:
    cols = t.columns
    score = min(len(cols), 20)
    score += 5 if any(is_numeric(c) for c in cols) else 0
    score += 5 if any(is_text(c) for c in cols) else 0
    score += 4 if any(is_date(c) for c in cols) else 0
    score += 4 if any(is_id_like(c) for c in cols) else 0
    if t.row_count is not None and t.row_count > 0:
        score += 3
    return score


def find_join_pairs(tables: Dict[str, TableInfo]) -> List[Tuple[TableInfo, TableInfo, str]]:
    pairs: List[Tuple[TableInfo, TableInfo, str]] = []
    names = sorted(tables)
    for i, a_name in enumerate(names):
        a = tables[a_name]
        a_cols = {c.name.lower(): c.name for c in a.columns if is_id_like(c) or "id" in c.name.lower() or "code" in c.name.lower()}
        for b_name in names[i + 1:]:
            b = tables[b_name]
            b_cols = {c.name.lower(): c.name for c in b.columns if is_id_like(c) or "id" in c.name.lower() or "code" in c.name.lower()}
            common = sorted(set(a_cols) & set(b_cols), key=lambda x: (x != "id", len(x)))
            for key in common:
                # Avoid joining two unrelated tables on generic state/year-only columns.
                if key in {"state", "year", "type", "name"}:
                    continue
                pairs.append((a, b, a_cols[key]))
                break
    # Favor likely FK style pairs sharing table tokens or strong key names.
    def pair_score(p: Tuple[TableInfo, TableInfo, str]) -> Tuple[int, str]:
        a, b, key = p
        shared_tokens = token_set(a.name) & token_set(b.name)
        key_bonus = 3 if key.lower().endswith("_id") or key.lower() == "id" else 0
        return (len(shared_tokens) + key_bonus, key)
    pairs.sort(key=pair_score, reverse=True)
    return pairs


def profile_table(t: TableInfo) -> Dict[str, Optional[ColumnInfo]]:
    cols = t.columns
    fallback = cols[0] if cols else None
    text = pick(cols, is_text, fallback)
    text2 = None
    if text:
        text2 = pick((c for c in cols if c.name != text.name), is_text, fallback)
    num = pick(cols, is_numeric, None)
    num2 = None
    if num:
        num2 = pick((c for c in cols if c.name != num.name), is_numeric, None)
    date = pick(cols, is_date, None)
    ident = pick(cols, is_id_like, fallback)
    return {"text": text, "text2": text2, "num": num, "num2": num2, "date": date, "id": ident}


def qcols(table: str, cols: Iterable[Optional[ColumnInfo]]) -> List[str]:
    return [f"{table}.{c.name}" for c in cols if c]


def add_question(out: List[GeneratedQuestion], seen: set[str], difficulty: str, qtype: str,
                 tables: List[str], cols: List[str], question: str, notes: str) -> None:
    clean = " ".join(question.split())
    if clean.lower() in seen:
        return
    seen.add(clean.lower())
    out.append(
        GeneratedQuestion(
            id=len(out) + 1,
            difficulty=difficulty,
            question_type=qtype,
            tables=tables,
            columns=cols,
            question=clean,
            notes=notes,
        )
    )


def generate_questions(schema: Dict[str, TableInfo], target_count: int = 20) -> List[GeneratedQuestion]:
    ranked = sorted(schema.values(), key=table_score, reverse=True)
    ranked = [t for t in ranked if len(t.columns) >= 2]
    pairs = find_join_pairs(schema)
    out: List[GeneratedQuestion] = []
    seen: set[str] = set()

    # Single-table complex aggregate/subquery/date/top-N templates.
    for t in ranked:
        if len(out) >= target_count:
            break
        p = profile_table(t)
        text, text2, num, num2, date, ident = p["text"], p["text2"], p["num"], p["num2"], p["date"], p["id"]
        if text and num:
            add_question(
                out, seen, "hard", "group_by_having_order_limit", [t.name], qcols(t.name, [text, num, ident]),
                f"Using {t.name}, for each {text.name}, show the row count, distinct {ident.name if ident else text.name} count, total {num.name}, average {num.name}, and maximum {num.name}; keep only groups with at least 2 rows and order by total {num.name} descending, returning the top 10.",
                "Uses only actual columns from one table: GROUP BY, aggregates, HAVING, ORDER BY, LIMIT.",
            )
        if text and num:
            add_question(
                out, seen, "hard", "above_overall_average", [t.name], qcols(t.name, [text, num]),
                f"Using {t.name}, find {text.name} values whose average {num.name} is greater than the overall average {num.name} in the same table; show {text.name}, row count, average {num.name}, and difference from the overall average.",
                "Single-table comparison against scalar subquery.",
            )
        if text and num and num2:
            add_question(
                out, seen, "hard", "two_metric_group_comparison", [t.name], qcols(t.name, [text, num, num2]),
                f"Using {t.name}, group by {text.name} and compare total {num.name} with average {num2.name}; return groups where total {num.name} is above the table-wide average total per {text.name}, sorted by total {num.name} descending.",
                "Two measures from the same table with aggregate comparison.",
            )
        if text and text2 and num:
            add_question(
                out, seen, "hard", "multi_group_rollup", [t.name], qcols(t.name, [text, text2, num]),
                f"Using {t.name}, for each pair of {text.name} and {text2.name}, calculate row count, total {num.name}, and average {num.name}; keep pairs with at least 2 rows and rank them by total {num.name} within each {text.name}.",
                "Two-dimensional grouping plus rank-style ordering expectation.",
            )
        if date and num:
            add_question(
                out, seen, "hard", "date_trend", [t.name], qcols(t.name, [date, num]),
                f"Using {t.name}, calculate monthly totals of {num.name} based on {date.name}, then show each month, total {num.name}, previous-month total, and month-over-month percent change ordered by month.",
                "Date bucketing + window/LAG style question when a date-like column exists.",
            )
        if text and ident:
            add_question(
                out, seen, "medium-hard", "duplicates", [t.name], qcols(t.name, [text, ident]),
                f"Using {t.name}, find duplicate {text.name} values that are associated with more than one distinct {ident.name}; show {text.name}, distinct {ident.name} count, and total row count, ordered by distinct count descending.",
                "Duplicate/entity consistency check.",
            )
        if len(out) >= target_count:
            break

    # Join questions only when the schema has plausible same-name key pairs.
    for a, b, key in pairs:
        if len(out) >= target_count:
            break
        pa, pb = profile_table(a), profile_table(b)
        a_text, b_text = pa["text"], pb["text"]
        b_num = pb["num"]
        a_num = pa["num"]
        metric = b_num or a_num
        metric_table = b if b_num else a
        group_col = a_text or pa["id"]
        if not group_col or not metric:
            continue
        add_question(
            out, seen, "hard", "inner_join_group_by", [a.name, b.name], [f"{a.name}.{key}", f"{b.name}.{key}", f"{a.name}.{group_col.name}", f"{metric_table.name}.{metric.name}"],
            f"Using {a.name} and {b.name}, join them on {key}; for each {a.name}.{group_col.name}, show matching row count, distinct {b.name}.{key} count, total {metric_table.name}.{metric.name}, and average {metric_table.name}.{metric.name}, keeping only groups with at least 2 joined rows.",
            "Join generated only because both tables share the exact key column.",
        )
        add_question(
            out, seen, "hard", "anti_join", [a.name, b.name], [f"{a.name}.{key}", f"{b.name}.{key}"],
            f"Using {a.name} and {b.name}, find rows in {a.name} whose {key} has no matching {key} in {b.name}; return the {a.name}.{key} value and a count of unmatched rows.",
            "Anti-join / NOT EXISTS generated only from a shared key.",
        )
        if b_text:
            add_question(
                out, seen, "hard", "join_distinct_diversity", [a.name, b.name], [f"{a.name}.{key}", f"{b.name}.{key}", f"{b.name}.{b_text.name}"],
                f"Using {a.name} and {b.name}, join on {key} and find each {a.name}.{key} that is linked to more than one distinct {b.name}.{b_text.name}; show the key, distinct {b_text.name} count, and joined row count.",
                "Join diversity/count-distinct question generated from actual columns.",
            )

    # Fallbacks to guarantee 20 even on narrow schema-only databases.
    for t in ranked:
        if len(out) >= target_count:
            break
        p = profile_table(t)
        cols = t.columns
        if not cols:
            continue
        c1 = p["text"] or p["id"] or cols[0]
        c2 = p["num"] or (cols[1] if len(cols) > 1 else cols[0])
        add_question(
            out, seen, "medium", "top_values", [t.name], qcols(t.name, [c1, c2]),
            f"Using {t.name}, list the top 20 distinct {c1.name} values with the number of rows for each value, ordered by row count descending and then {c1.name} ascending.",
            "Safe fallback distinct/group question from actual table columns.",
        )
        if len(cols) >= 3:
            add_question(
                out, seen, "medium", "not_null_filter", [t.name], [f"{t.name}.{cols[0].name}", f"{t.name}.{cols[1].name}", f"{t.name}.{cols[2].name}"],
                f"Using {t.name}, show rows where {cols[0].name}, {cols[1].name}, and {cols[2].name} are all not null; return those three columns and limit to 50 rows.",
                "Safe fallback filter/projection question from actual columns.",
            )

    return out[:target_count]


def post_execute(api_base: str, database_id: int, question: str, timeout: int = 120) -> Dict[str, Any]:
    url = api_base.rstrip("/") + f"/database/{database_id}/execute_sql"
    payload = json.dumps({"question": question}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"success": False, "http_error": exc.code, "body": body}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def save_outputs(database_id: int, questions: List[GeneratedQuestion], execute: bool, api_base: str) -> None:
    out_dir = os.path.join("benchmarks", "generated")
    os.makedirs(out_dir, exist_ok=True)
    stem = f"bq046_complex_questions_db{database_id}"
    json_path = os.path.join(out_dir, stem + ".json")
    txt_path = os.path.join(out_dir, stem + ".txt")

    data = [asdict(q) for q in questions]
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    with open(txt_path, "w", encoding="utf-8") as f:
        for q in questions:
            f.write(f"===== QUERY {q.id:02d} =====\n")
            f.write(f"Difficulty: {q.difficulty}\n")
            f.write(f"Type: {q.question_type}\n")
            f.write(f"Tables: {', '.join(q.tables)}\n")
            f.write(f"Columns: {', '.join(q.columns)}\n")
            f.write("NL:\n")
            f.write(q.question + "\n\n")

    print(f"Saved questions JSON: {json_path}")
    print(f"Saved questions TXT : {txt_path}")

    if execute:
        results: List[Dict[str, Any]] = []
        for q in questions:
            print(f"\nExecuting Q{q.id:02d}: {q.question}")
            response = post_execute(api_base, database_id, q.question)
            results.append({"question": asdict(q), "response": response})
            sql = ((response.get("generated_sql") or {}).get("sql") if isinstance(response, dict) else None)
            print("SQL:", sql or "(no sql)")
            print("success:", response.get("success") if isinstance(response, dict) else None)
        ts = time.strftime("%Y%m%d_%H%M%S")
        result_path = os.path.join(out_dir, f"bq046_complex_results_db{database_id}_{ts}.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nSaved execution results: {result_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate 20 schema-grounded complex NL questions for bq046/db40.")
    parser.add_argument("--database-id", type=int, default=40, help="Database id to inspect. Default: 40")
    parser.add_argument("--count", type=int, default=20, help="Number of questions. Default: 20")
    parser.add_argument("--execute", action="store_true", help="Also POST questions to /database/{id}/execute_sql")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000", help="Backend API base URL for --execute")
    args = parser.parse_args()

    db = get_database(args.database_id)
    if not db:
        raise SystemExit(f"database_id={args.database_id} not found. Check the id and try again.")

    db_path = db.get("db_path") or db.get("path") or db.get("file_path")
    if not db_path:
        raise SystemExit(f"database_id={args.database_id} has no db_path in metadata: {db}")

    schema = physical_schema(db_path, sample_counts=True)
    meta_rows = get_database_tables(args.database_id)
    meta_names = sorted(r.get("table_name") for r in meta_rows if r.get("table_name"))
    physical_names = sorted(schema.keys())

    print("=" * 72)
    print(f"Database id   : {args.database_id}")
    print(f"Database name : {db.get('name')}")
    print(f"Database file : {db_path}")
    print(f"Metadata tables: {len(meta_names)}")
    print(f"Physical tables: {len(physical_names)}")
    print("=" * 72)

    ranked = sorted(schema.values(), key=table_score, reverse=True)
    print("\nTop schema tables used for generation:")
    for t in ranked[:15]:
        cols = ", ".join(c.name for c in t.columns[:8])
        rc = "unknown" if t.row_count is None else str(t.row_count)
        print(f"  - {t.name}  rows={rc}  cols={len(t.columns)}  [{cols}]")

    pairs = find_join_pairs(schema)
    print(f"\nDetected plausible same-key table pairs: {len(pairs)}")
    for a, b, key in pairs[:10]:
        print(f"  - {a.name} <-> {b.name} on {key}")

    questions = generate_questions(schema, target_count=args.count)
    if len(questions) < args.count:
        print(f"WARNING: generated only {len(questions)} questions from available schema.")

    print("\nGenerated questions:")
    for q in questions:
        print(f"\nQ{q.id:02d}. {q.question}")
        print(f"    tables: {', '.join(q.tables)}")

    save_outputs(args.database_id, questions, args.execute, args.api_base)


if __name__ == "__main__":
    main()
