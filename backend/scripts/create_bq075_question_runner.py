#!/usr/bin/env python3
from __future__ import annotations

"""
Create a high-quality SpiderSQL benchmark runner for Spider 2.0 database bq075.

Run from the backend directory:

    python scripts/create_bq075_question_runner.py
    python scripts/create_bq075_question_runner.py --database-id 40
    python scripts/create_bq075_question_runner.py --database-name bq075 --execute

What it does:
1. Finds the requested database in app_data.db.
2. Reads the physical SQLite schema table-by-table and column-by-column.
3. Writes a full schema report so every table and every column is visible.
4. Generates only validated natural-language questions from real table/column names.
5. Writes a runner .py file like the bq023 example, with a QUESTIONS list and API calls.
6. Also writes a JSON answer key containing reference SQL for strict manual/automatic scoring.

It avoids known bad question types:
- no same-column duplicate questions, such as distinct case_gdc_id by case_gdc_id
- no fake monthly/date questions on numeric age/day fields
- no aggregating ID/code/zip/accession/batch columns as meaningful metrics
- no joins unless two real tables share the exact join column
- no questions that reference tables or columns absent from the physical SQLite file
"""

import argparse
import json
import os
import re
import sqlite3
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

BASE_URL_DEFAULT = "http://127.0.0.1:8000"
DEFAULT_DATABASE_NAME = "bq075"
DEFAULT_TIMEOUT_SECONDS = 240
OUTPUT_DIR = Path("benchmarks/generated")

BAD_METRIC_TOKENS = {
    "id", "gdc", "uuid", "barcode", "zip", "zipcode", "postal", "code",
    "accession", "dbgap", "batch", "year", "month", "day", "days_to",
    "index", "number", "num", "phone", "fax",
}
GOOD_METRIC_TOKENS = {
    "age", "amount", "count", "total", "size", "length", "weight", "height",
    "volume", "score", "rate", "percent", "percentage", "duration", "quantity",
    "value", "cost", "price", "time", "survival", "tumor", "days",
}
GROUP_TOKENS = {
    "type", "status", "state", "category", "class", "classification", "gender",
    "sex", "race", "ethnicity", "program", "project", "disease", "diagnosis",
    "site", "sample", "tissue", "organ", "method", "workflow", "platform",
    "experimental", "strategy", "access", "acl", "db", "name", "short_name",
}
ID_TOKENS = {
    "id", "gdc_id", "case_id", "sample_id", "file_id", "project_id", "submitter_id",
    "barcode", "uuid", "key",
}
DATE_TOKENS = {"date", "datetime", "timestamp", "created", "updated", "submitted", "released"}


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    declared_type: str
    notnull: bool
    pk: bool


@dataclass
class TableInfo:
    name: str
    columns: List[ColumnInfo]
    row_count: Optional[int]

    @property
    def column_names(self) -> List[str]:
        return [c.name for c in self.columns]


@dataclass
class QuestionSpec:
    id: int
    difficulty: str
    question_type: str
    tables: List[str]
    columns: List[str]
    question: str
    reference_sql: str
    validation_notes: str


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s or "").lower()).strip("_")


def token_set(name: str) -> set[str]:
    return set(t for t in re.split(r"[^a-z0-9]+", str(name).lower()) if t)


def is_numeric_type(declared: str) -> bool:
    t = declared.lower()
    return any(x in t for x in ("int", "real", "double", "float", "numeric", "decimal"))


def is_text_type(declared: str) -> bool:
    t = declared.lower()
    return not t or any(x in t for x in ("char", "text", "clob", "varchar"))


def is_id_like(col: str) -> bool:
    n = norm(col)
    toks = token_set(col)
    if n.endswith("_id") or n == "id" or "uuid" in toks or "barcode" in toks:
        return True
    return bool(toks & ID_TOKENS)


def is_date_like(col: str, declared: str) -> bool:
    n = norm(col)
    toks = token_set(col)
    if n.startswith("days_to") or "age" in toks or n.startswith("age_"):
        return False
    if any(x in declared.lower() for x in ("date", "time")):
        return True
    return bool(toks & DATE_TOKENS)


def is_meaningful_metric(col: ColumnInfo) -> bool:
    n = norm(col.name)
    toks = token_set(col.name)
    if is_id_like(col.name):
        return False
    if any(tok in n for tok in BAD_METRIC_TOKENS):
        # allow days only when not a date-trend and clearly a duration/measurement; still not monthly.
        if n.startswith("days_to") or n.endswith("_days"):
            return True
        return False
    if not is_numeric_type(col.declared_type):
        # Some Spider/SQLite imports leave numeric-looking columns untyped; use name only when clearly metric.
        return bool(toks & GOOD_METRIC_TOKENS)
    return bool(toks & GOOD_METRIC_TOKENS) or is_numeric_type(col.declared_type)


def is_group_column(col: ColumnInfo) -> bool:
    if is_id_like(col.name):
        return False
    if is_date_like(col.name, col.declared_type):
        return False
    toks = token_set(col.name)
    n = norm(col.name)
    return is_text_type(col.declared_type) or bool(toks & GROUP_TOKENS) or n.endswith("_name")


def good_id_column(col: ColumnInfo) -> bool:
    return is_id_like(col.name) and not norm(col.name).endswith("rowid")


def read_metadata_db() -> sqlite3.Connection:
    candidates = [Path("app_data.db"), Path("backend/app_data.db")]
    for p in candidates:
        if p.exists():
            return sqlite3.connect(str(p))
    raise FileNotFoundError("Could not find app_data.db. Run this script from the backend directory.")


def find_database(database_id: Optional[int], database_name: str) -> Dict[str, Any]:
    conn = read_metadata_db()
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        if database_id is not None:
            cur.execute("SELECT * FROM databases WHERE id = ?", (database_id,))
        else:
            cur.execute("SELECT * FROM databases WHERE lower(name) = lower(?) ORDER BY id DESC LIMIT 1", (database_name,))
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"Database not found: id={database_id!r}, name={database_name!r}")
        return dict(row)
    finally:
        conn.close()


def physical_schema(db_path: str, count_rows: bool = True) -> List[TableInfo]:
    path = Path(db_path)
    if not path.exists():
        # database_service paths are sometimes relative to backend cwd; try normalized path.
        path = Path(str(db_path).replace("\\", os.sep))
    if not path.exists():
        raise FileNotFoundError(f"Physical SQLite file not found: {db_path}")

    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10.0)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        names = [r[0] for r in cur.fetchall()]
        tables: List[TableInfo] = []
        for table in names:
            cur.execute(f"PRAGMA table_info({qident(table)})")
            cols = [ColumnInfo(name=r[1], declared_type=r[2] or "", notnull=bool(r[3]), pk=bool(r[5])) for r in cur.fetchall()]
            row_count: Optional[int] = None
            if count_rows:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {qident(table)}")
                    row_count = int(cur.fetchone()[0])
                except sqlite3.Error:
                    row_count = None
            tables.append(TableInfo(name=table, columns=cols, row_count=row_count))
        return tables
    finally:
        conn.close()


def table_score(t: TableInfo) -> Tuple[int, int, int, int]:
    groups = len(group_cols(t))
    ids = len(id_cols(t))
    metrics = len(metric_cols(t))
    dates = len(date_cols(t))
    rows = t.row_count if t.row_count is not None else 0
    return (groups + ids + metrics + dates, min(rows, 1000000), len(t.columns), -len(t.name))


def group_cols(t: TableInfo) -> List[ColumnInfo]:
    return [c for c in t.columns if is_group_column(c)]


def id_cols(t: TableInfo) -> List[ColumnInfo]:
    return [c for c in t.columns if good_id_column(c)]


def metric_cols(t: TableInfo) -> List[ColumnInfo]:
    return [c for c in t.columns if is_meaningful_metric(c)]


def date_cols(t: TableInfo) -> List[ColumnInfo]:
    return [c for c in t.columns if is_date_like(c.name, c.declared_type)]


def choose_distinct(a: Sequence[ColumnInfo], not_name: str) -> Optional[ColumnInfo]:
    for c in a:
        if norm(c.name) != norm(not_name):
            return c
    return None


def shared_key_pairs(tables: List[TableInfo]) -> List[Tuple[TableInfo, TableInfo, str]]:
    pairs: List[Tuple[TableInfo, TableInfo, str]] = []
    for i, a in enumerate(tables):
        a_cols = {norm(c.name): c.name for c in a.columns if is_id_like(c.name)}
        for b in tables[i + 1:]:
            b_cols = {norm(c.name): c.name for c in b.columns if is_id_like(c.name)}
            common = sorted(set(a_cols) & set(b_cols), key=lambda x: (0 if x not in {"id"} else 1, x))
            for key_norm in common:
                if key_norm == "id" and (len(a_cols) > 1 or len(b_cols) > 1):
                    continue
                pairs.append((a, b, a_cols[key_norm]))
                break
    return pairs


def add_question(out: List[QuestionSpec], seen: set[str], spec: QuestionSpec, max_questions: int) -> None:
    if len(out) >= max_questions:
        return
    key = norm(spec.question)
    if key in seen:
        return
    # Hard validation: no bad questions.
    if "distinct " in spec.question.lower():
        m = re.search(r"for each ([a-zA-Z0-9_]+).*distinct ([a-zA-Z0-9_]+)", spec.question, re.I)
        if m and norm(m.group(1)) == norm(m.group(2)):
            return
    if "monthly" in spec.question.lower():
        bad_words = ["age_", "days_to", "year", "years"]
        if any(b in spec.question.lower() for b in bad_words):
            return
    if any("." not in c for c in spec.columns):
        return
    out.append(spec)
    seen.add(key)


def generate_questions(tables: List[TableInfo], database_id: int, max_questions: int = 20) -> List[QuestionSpec]:
    ranked = sorted(tables, key=table_score, reverse=True)
    qs: List[QuestionSpec] = []
    seen: set[str] = set()

    def next_id() -> int:
        return len(qs) + 1

    # Single-table high-confidence questions.
    for t in ranked:
        if len(qs) >= max_questions:
            break
        groups = group_cols(t)
        ids = id_cols(t)
        metrics = metric_cols(t)
        dates = date_cols(t)

        if groups and ids:
            g = groups[0]
            did = choose_distinct(ids, g.name)
            if did:
                ref = f"""
                SELECT {qident(g.name)} AS {qident(g.name)},
                       COUNT(*) AS row_count,
                       COUNT(DISTINCT {qident(did.name)}) AS distinct_{did.name}_count
                FROM {qident(t.name)}
                GROUP BY {qident(g.name)}
                HAVING COUNT(*) >= 2
                ORDER BY row_count DESC, distinct_{did.name}_count DESC
                LIMIT 10;
                """
                add_question(qs, seen, QuestionSpec(
                    id=next_id(), difficulty="hard", question_type="group_by_having_order_limit",
                    tables=[t.name], columns=[f"{t.name}.{g.name}", f"{t.name}.{did.name}"],
                    question=(f"Using {t.name}, for each {g.name}, show the row count and the number of distinct "
                              f"{did.name} values; keep only {g.name} groups with at least 2 rows, order by row count "
                              f"descending, and return the top 10 groups."),
                    reference_sql=textwrap.dedent(ref).strip(),
                    validation_notes="Valid: one table, one grouping column, distinct column is different from grouping column."
                ), max_questions)

        if groups and metrics:
            g = groups[0]
            m = metrics[0]
            ref = f"""
            SELECT {qident(g.name)} AS {qident(g.name)},
                   COUNT(*) AS row_count,
                   AVG(CAST({qident(m.name)} AS REAL)) AS avg_{m.name},
                   AVG(CAST({qident(m.name)} AS REAL)) - (SELECT AVG(CAST({qident(m.name)} AS REAL)) FROM {qident(t.name)}) AS difference_from_overall_average
            FROM {qident(t.name)}
            WHERE {qident(m.name)} IS NOT NULL
            GROUP BY {qident(g.name)}
            HAVING AVG(CAST({qident(m.name)} AS REAL)) > (SELECT AVG(CAST({qident(m.name)} AS REAL)) FROM {qident(t.name)})
            ORDER BY avg_{m.name} DESC;
            """
            add_question(qs, seen, QuestionSpec(
                id=next_id(), difficulty="hard", question_type="above_overall_average",
                tables=[t.name], columns=[f"{t.name}.{g.name}", f"{t.name}.{m.name}"],
                question=(f"Using {t.name}, find {g.name} groups whose average {m.name} is greater than the overall "
                          f"average {m.name} in {t.name}; show {g.name}, row count, average {m.name}, and the "
                          f"difference from the overall average."),
                reference_sql=textwrap.dedent(ref).strip(),
                validation_notes="Valid: meaningful numeric metric compared against same-table scalar aggregate."
            ), max_questions)

        if groups and len(metrics) >= 2:
            g = groups[0]
            m1, m2 = metrics[0], metrics[1]
            ref = f"""
            WITH grouped AS (
                SELECT {qident(g.name)} AS {qident(g.name)},
                       COUNT(*) AS row_count,
                       SUM(CAST({qident(m1.name)} AS REAL)) AS total_{m1.name},
                       AVG(CAST({qident(m2.name)} AS REAL)) AS avg_{m2.name}
                FROM {qident(t.name)}
                WHERE {qident(m1.name)} IS NOT NULL AND {qident(m2.name)} IS NOT NULL
                GROUP BY {qident(g.name)}
            )
            SELECT *
            FROM grouped
            WHERE total_{m1.name} > (SELECT AVG(total_{m1.name}) FROM grouped)
            ORDER BY total_{m1.name} DESC;
            """
            add_question(qs, seen, QuestionSpec(
                id=next_id(), difficulty="hard", question_type="aggregate_subquery_comparison",
                tables=[t.name], columns=[f"{t.name}.{g.name}", f"{t.name}.{m1.name}", f"{t.name}.{m2.name}"],
                question=(f"Using {t.name}, group rows by {g.name}; for each group calculate row count, total {m1.name}, "
                          f"and average {m2.name}; return only groups whose total {m1.name} is above the average "
                          f"group total {m1.name}, ordered by total {m1.name} descending."),
                reference_sql=textwrap.dedent(ref).strip(),
                validation_notes="Valid: two different meaningful numeric metrics from the same table."
            ), max_questions)

        if groups and ids:
            did = ids[0]
            cat = choose_distinct(groups, did.name)
            if cat:
                ref = f"""
                SELECT {qident(did.name)} AS {qident(did.name)},
                       COUNT(DISTINCT {qident(cat.name)}) AS distinct_{cat.name}_count,
                       COUNT(*) AS row_count
                FROM {qident(t.name)}
                GROUP BY {qident(did.name)}
                HAVING COUNT(DISTINCT {qident(cat.name)}) > 1
                ORDER BY distinct_{cat.name}_count DESC, row_count DESC;
                """
                add_question(qs, seen, QuestionSpec(
                    id=next_id(), difficulty="medium-hard", question_type="entity_multi_category_check",
                    tables=[t.name], columns=[f"{t.name}.{did.name}", f"{t.name}.{cat.name}"],
                    question=(f"Using {t.name}, find {did.name} values that are associated with more than one distinct "
                              f"{cat.name}; show {did.name}, the distinct {cat.name} count, and total row count, ordered "
                              f"by the distinct {cat.name} count descending."),
                    reference_sql=textwrap.dedent(ref).strip(),
                    validation_notes="Valid: duplicate/consistency question uses two different columns."
                ), max_questions)

        if len(groups) >= 2:
            g1, g2 = groups[0], groups[1]
            ref = f"""
            SELECT {qident(g1.name)} AS {qident(g1.name)},
                   {qident(g2.name)} AS {qident(g2.name)},
                   COUNT(*) AS row_count
            FROM {qident(t.name)}
            GROUP BY {qident(g1.name)}, {qident(g2.name)}
            HAVING COUNT(*) >= 2
            ORDER BY {qident(g1.name)}, row_count DESC;
            """
            add_question(qs, seen, QuestionSpec(
                id=next_id(), difficulty="medium-hard", question_type="two_column_grouping",
                tables=[t.name], columns=[f"{t.name}.{g1.name}", f"{t.name}.{g2.name}"],
                question=(f"Using {t.name}, group rows by the pair ({g1.name}, {g2.name}); show both columns and the row "
                          f"count, keep only pairs with at least 2 rows, and order by {g1.name} then row count descending."),
                reference_sql=textwrap.dedent(ref).strip(),
                validation_notes="Valid: two real categorical columns from one table."
            ), max_questions)

        if dates and groups:
            d = dates[0]
            g = groups[0]
            ref = f"""
            SELECT strftime('%Y-%m', {qident(d.name)}) AS month,
                   {qident(g.name)} AS {qident(g.name)},
                   COUNT(*) AS row_count
            FROM {qident(t.name)}
            WHERE {qident(d.name)} IS NOT NULL
            GROUP BY strftime('%Y-%m', {qident(d.name)}), {qident(g.name)}
            ORDER BY month, row_count DESC;
            """
            add_question(qs, seen, QuestionSpec(
                id=next_id(), difficulty="hard", question_type="real_date_monthly_breakdown",
                tables=[t.name], columns=[f"{t.name}.{d.name}", f"{t.name}.{g.name}"],
                question=(f"Using {t.name}, bucket rows by the calendar month of {d.name} and by {g.name}; show month, "
                          f"{g.name}, and row count, ordered by month and row count descending."),
                reference_sql=textwrap.dedent(ref).strip(),
                validation_notes="Valid: date question uses a real date/timestamp-like column, not age or days_to fields."
            ), max_questions)

    # Join questions from exact shared keys only.
    pairs = shared_key_pairs(ranked)
    for a, b, key in pairs:
        if len(qs) >= max_questions:
            break
        a_groups = group_cols(a)
        b_ids = id_cols(b)
        if a_groups:
            g = a_groups[0]
            did = choose_distinct(b_ids, key) or (b_ids[0] if b_ids else None)
            if did:
                ref = f"""
                SELECT a.{qident(g.name)} AS {qident(g.name)},
                       COUNT(*) AS matching_row_count,
                       COUNT(DISTINCT b.{qident(did.name)}) AS distinct_{did.name}_count
                FROM {qident(a.name)} AS a
                JOIN {qident(b.name)} AS b ON a.{qident(key)} = b.{qident(key)}
                GROUP BY a.{qident(g.name)}
                HAVING COUNT(*) >= 2
                ORDER BY matching_row_count DESC
                LIMIT 10;
                """
                add_question(qs, seen, QuestionSpec(
                    id=next_id(), difficulty="hard", question_type="join_group_by_shared_key",
                    tables=[a.name, b.name], columns=[f"{a.name}.{key}", f"{a.name}.{g.name}", f"{b.name}.{key}", f"{b.name}.{did.name}"],
                    question=(f"Using {a.name} and {b.name}, join the tables on {key}; for each {a.name}.{g.name}, "
                              f"show the matching row count and the number of distinct {b.name}.{did.name} values, keep "
                              f"groups with at least 2 matches, order by matching row count descending, and return the top 10."),
                    reference_sql=textwrap.dedent(ref).strip(),
                    validation_notes="Valid: join uses one exact shared key column present in both tables."
                ), max_questions)

        ref = f"""
        SELECT a.{qident(key)} AS {qident(key)}
        FROM {qident(a.name)} AS a
        WHERE a.{qident(key)} IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM {qident(b.name)} AS b
              WHERE b.{qident(key)} = a.{qident(key)}
          )
        ORDER BY a.{qident(key)}
        LIMIT 50;
        """
        add_question(qs, seen, QuestionSpec(
            id=next_id(), difficulty="hard", question_type="anti_join_missing_match",
            tables=[a.name, b.name], columns=[f"{a.name}.{key}", f"{b.name}.{key}"],
            question=(f"Using {a.name} and {b.name}, list {a.name}.{key} values that appear in {a.name} but have no "
                      f"matching {b.name}.{key}; return the first 50 unmatched values ordered by {key}."),
            reference_sql=textwrap.dedent(ref).strip(),
            validation_notes="Valid: anti-join uses one exact shared key column present in both tables."
        ), max_questions)

    # If we still do not have enough, fail clearly instead of creating bad questions.
    if len(qs) < max_questions:
        raise RuntimeError(
            f"Only generated {len(qs)} validated questions, but {max_questions} were requested. "
            "I refused to invent unsafe/bad questions. Try a database with more categorical, ID, metric, or real date columns."
        )

    for i, q in enumerate(qs, start=1):
        q.id = i
    return qs[:max_questions]


def write_schema_report(db: Dict[str, Any], tables: List[TableInfo], out_dir: Path) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    db_id = int(db["id"])
    txt = out_dir / f"bq075_schema_report_db{db_id}.txt"
    js = out_dir / f"bq075_schema_report_db{db_id}.json"
    payload = {
        "database": db,
        "tables": [
            {
                "name": t.name,
                "row_count": t.row_count,
                "columns": [asdict(c) for c in t.columns],
            }
            for t in tables
        ],
    }
    js.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with txt.open("w", encoding="utf-8") as f:
        f.write(f"Database id   : {db['id']}\n")
        f.write(f"Database name : {db.get('name')}\n")
        f.write(f"Database file : {db.get('db_path')}\n")
        f.write(f"Physical tables: {len(tables)}\n\n")
        for t in tables:
            f.write(f"TABLE: {t.name}  rows={t.row_count}\n")
            for c in t.columns:
                flags = []
                if c.pk:
                    flags.append("PK")
                if c.notnull:
                    flags.append("NOT NULL")
                f.write(f"  - {c.name}  type={c.declared_type or '(none)'} {' '.join(flags)}\n")
            f.write("\n")
    return txt, js


def write_question_files(db: Dict[str, Any], questions: List[QuestionSpec], out_dir: Path) -> Tuple[Path, Path, Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    db_id = int(db["id"])
    json_path = out_dir / f"bq075_validated_questions_db{db_id}.json"
    txt_path = out_dir / f"bq075_validated_questions_db{db_id}.txt"
    key_path = out_dir / f"bq075_answer_key_db{db_id}.json"
    runner_path = out_dir / f"run_bq075_validated_nl_sql_db{db_id}.py"

    question_payload = [
        {
            "id": q.id,
            "difficulty": q.difficulty,
            "question_type": q.question_type,
            "tables": q.tables,
            "columns": q.columns,
            "question": q.question,
            "validation_notes": q.validation_notes,
        }
        for q in questions
    ]
    json_path.write_text(json.dumps(question_payload, indent=2), encoding="utf-8")
    key_path.write_text(json.dumps([asdict(q) for q in questions], indent=2), encoding="utf-8")

    with txt_path.open("w", encoding="utf-8") as f:
        for q in questions:
            f.write(f"===== QUERY {q.id:02d} =====\n")
            f.write(f"Difficulty: {q.difficulty}\n")
            f.write(f"Type: {q.question_type}\n")
            f.write(f"Tables: {', '.join(q.tables)}\n")
            f.write(f"Columns: {', '.join(q.columns)}\n")
            f.write("NL:\n")
            f.write(q.question + "\n\n")

    runner = f'''#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

BASE_URL = "{BASE_URL_DEFAULT}"
DATABASE_ID = {db_id}
TIMEOUT_SECONDS = {DEFAULT_TIMEOUT_SECONDS}
OUTPUT_FILE = "bq075_validated_nl_sql_db{db_id}.txt"

QUESTIONS: List[str] = {json.dumps([q.question for q in questions], indent=4)}


def post_query(question: str) -> Dict[str, Any]:
    payload = json.dumps({{"question": question}}).encode("utf-8")
    request = urllib.request.Request(
        f"{{BASE_URL}}/database/{{DATABASE_ID}}/execute_sql",
        data=payload,
        headers={{"Content-Type": "application/json"}},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_sql(response: Dict[str, Any]) -> str:
    generated = response.get("generated_sql")
    if isinstance(generated, dict):
        sql = generated.get("sql")
        if isinstance(sql, str) and sql.strip():
            return sql.strip()
    sql = response.get("sql")
    if isinstance(sql, str) and sql.strip():
        return sql.strip()
    return "-- NO SQL GENERATED"


def normalize_sql(sql: str) -> str:
    sql = sql.strip()
    if not sql:
        return "-- NO SQL GENERATED;"
    if sql.startswith("--"):
        return sql
    return sql if sql.endswith(";") else sql + ";"


def main() -> None:
    output_path = Path(OUTPUT_FILE)
    with output_path.open("w", encoding="utf-8") as out:
        for i, question in enumerate(QUESTIONS, start=1):
            print(f"\\n===== QUERY {{i:02d}} =====")
            print("NL:")
            print(question)
            out.write(f"===== QUERY {{i:02d}} =====\\n")
            out.write("NL:\\n")
            out.write(question + "\\n\\n")

            try:
                sql = normalize_sql(extract_sql(post_query(question)))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                sql = f"-- ERROR: HTTPError {{exc.code}}: {{body}}"
            except Exception as exc:
                sql = f"-- ERROR: {{type(exc).__name__}}: {{exc}}"

            print("SQL:")
            print(sql)
            print()
            out.write("SQL:\\n")
            out.write(sql + "\\n\\n")

    print(f"Saved NL + SQL output to: {{output_path.resolve()}}")


if __name__ == "__main__":
    main()
'''
    runner_path.write_text(runner, encoding="utf-8")
    return json_path, txt_path, key_path, runner_path


def execute_runner(questions: List[QuestionSpec], database_id: int, base_url: str, timeout: int) -> List[Dict[str, Any]]:
    results = []
    for q in questions:
        payload = json.dumps({"question": q.question}).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/database/{database_id}/execute_sql",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            generated = body.get("generated_sql") if isinstance(body, dict) else None
            sql = generated.get("sql") if isinstance(generated, dict) else None
            success = bool(body.get("success")) if isinstance(body, dict) else False
            results.append({"id": q.id, "question": q.question, "success": success, "generated_sql": sql, "response": body})
            print(f"Q{q.id:02d}: success={success}")
        except Exception as exc:
            results.append({"id": q.id, "question": q.question, "success": False, "error": f"{type(exc).__name__}: {exc}"})
            print(f"Q{q.id:02d}: ERROR {type(exc).__name__}: {exc}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-id", type=int, default=None, help="Database id. If omitted, finds newest database named bq075.")
    parser.add_argument("--database-name", default=DEFAULT_DATABASE_NAME)
    parser.add_argument("--max-questions", type=int, default=20)
    parser.add_argument("--no-count-rows", action="store_true", help="Skip row counts during inspection.")
    parser.add_argument("--execute", action="store_true", help="After generating files, call the backend API for each question.")
    parser.add_argument("--base-url", default=BASE_URL_DEFAULT)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args()

    db = find_database(args.database_id, args.database_name)
    db_id = int(db["id"])
    db_path = db.get("db_path")
    print("=" * 72)
    print(f"Database id   : {db_id}")
    print(f"Database name : {db.get('name')}")
    print(f"Database file : {db_path}")
    print("Inspecting physical SQLite schema head-to-toe...")

    tables = physical_schema(str(db_path), count_rows=not args.no_count_rows)
    print(f"Physical tables: {len(tables)}")
    print(f"Physical columns: {sum(len(t.columns) for t in tables)}")

    schema_txt, schema_json = write_schema_report(db, tables, OUTPUT_DIR)
    print(f"Saved full schema TXT : {schema_txt}")
    print(f"Saved full schema JSON: {schema_json}")

    questions = generate_questions(tables, database_id=db_id, max_questions=args.max_questions)
    q_json, q_txt, key_json, runner_py = write_question_files(db, questions, OUTPUT_DIR)
    print(f"Saved questions JSON : {q_json}")
    print(f"Saved questions TXT  : {q_txt}")
    print(f"Saved answer key JSON: {key_json}")
    print(f"Saved runner PY      : {runner_py}")

    print("\nGenerated validated natural-language questions:")
    for q in questions:
        print(f"Q{q.id:02d}. {q.question}")

    if args.execute:
        print("\nExecuting generated questions through backend API...")
        results = execute_runner(questions, db_id, args.base_url, args.timeout)
        exec_path = OUTPUT_DIR / f"bq075_execution_results_db{db_id}.json"
        exec_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"Saved execution results: {exec_path}")


if __name__ == "__main__":
    main()
