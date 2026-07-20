from dotenv import load_dotenv
load_dotenv()
import re
import json
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from semantic.ai_semantic_extractor import extract_semantics
from semantic.ir_converter import ir_to_semantic
from generation.sql_generator import generate_sql_from_semantic
from semantic.semantic_parser import (
    parse_natural_language,
    create_semantic_object,
    validate_and_normalise,
)
from semantic.validator import validate_query
from llm.llm_clarifier import clarify_query
from schema.ai_schema_inferencer import infer_schema_with_ai
from db.auth_db import init_auth_db, get_connection
from services.auth_service import create_user, login_user
from services.dataset_service import (
    save_schema_dataset,
    get_latest_dataset,
    get_latest_dataset_for_conversation,
    get_queries_for_conversation,
    save_query,
    get_user_queries,
    save_chat_state,
    get_chat_state,
    clear_chat_state,
)
from services.conversation_manager import understand_followup
from fastapi import UploadFile, File, Form, Body
import os
import shutil
from schema.csv_schema_detector import detect_csv_schema
from schema.csv_to_sqlite_loader import load_csv_to_sqlite, clean_table_name
from schema.sqlite_db_import import inspect_sqlite_file
from services.conversation_service import (
    create_conversation,
    get_user_conversations,
    delete_conversation,
    update_conversation_title,
    factory_reset_user,
)
from schema.schema_extractor import extract_table_columns
from schema.relationship_detector import detect_relationships
from containment.models import ContainmentRequest, ContainmentBatchRequest
from containment.service import check_containment, check_containment_batch
from local_benchmarks.benchmark_registry import list_benchmarks
from local_benchmarks.benchmark_loader import load_benchmark
from local_benchmarks.benchmark_relationships import (
    augment_graph as augment_local_benchmark_relationships,
)
from schema.lazy_loader import (
    get_database_meta,
    list_tables as lazy_list_tables,
    ensure_table_columns as lazy_ensure_table_columns,
)
from schema.database_mode import (
    is_large_database,
    update_database_mode,
    set_table_columns_loaded,
)
from retrieval.table_retriever import retrieve_tables, requested_dates_satisfied
from schema.subgraph_builder import build_subgraph
from schema.query_context import resolve_query_graph
from schema.named_table_forcing import force_named_tables, physical_tables
from sql_candidates.name_normalizer import normalize_schema_prefixes
from retrieval.relationship_expansion import augment_graph_with_physical_fks
from schema.partition_filter import (
    remove_redundant_partition_date_filters,
    detect_partitioned_ambiguity,
)
from services.metadata_service import create_metadata
from schema.schema_database_creator import (
    create_empty_db_from_ddl,
    extract_declared_foreign_keys,
    infer_schema_name_relationships,
    SchemaDDLError,
)
from spider2.spider2_catalog import (
    spider2_status,
    list_catalog as spider2_list_catalog,
    database_signal_counts as spider2_signal_counts,
    get_catalog_entry as spider2_get_entry,
    entry_is_importable as spider2_entry_importable,
    entry_to_ddl as spider2_entry_to_ddl,
    entry_relationship_edges as spider2_entry_edges,
    entry_inferred_edges as spider2_entry_inferred_edges,
)
from db.database_service import (
    create_database,
    set_database_path,
    add_database_table,
    get_user_databases,
    get_database,
    get_database_tables,
    add_table_columns,
    get_database_schema,
    add_relationships,
    get_relationships,
    clear_relationships,
    get_database_graph,
    get_database_path,
    set_relationships_finalized,
    get_relationships_finalized,
    set_relationship_status,
    get_relationship_status,
    set_all_relationships_confirmed,
    add_user_relationship,
    update_relationship,
    delete_relationship,
    delete_database,
    verify_database_access,
)
from semantic.ai_semantic_extractor import (
    extract_semantics,
    extract_multitable_ir_extraction,
    extract_multitable_ir_extraction_variant,
)
from semantic.ir_builder import build_from_extraction
from query_families import route_and_build
from query_families.family_guard import validate_family_output
from sql_candidates import (
    build_candidate,
    build_direct_sql_candidate,
    score_candidate,
    select_best,
    annotate_with_probes,
)
from sql_candidates.candidate_selector import enforce_selection_safety
from diagnostics import full_trace
print(
    "[FULL TRACE STARTUP]",
    f"enabled={full_trace.enabled()}",
    f"debug={full_trace.trace_debug_enabled()}",
    f"run_id={os.getenv('SPIDERSQL_TRACE_RUN_ID')!r}",
    flush=True,
)
from semantic.semantic_checklist import generate_checklist
from semantic.semantic_contract import build_grain_contract, contract_to_dict
from semantic.schema_linker import correct_checklist_tables
from sql_candidates.direct_sql_enforcement import direct_sql_violations, required_tables_for
from query_families.slot_extractor import index_schema as se_index_schema
from semantic.llm_sql_direct import (
    generate_direct_sql,
    generate_direct_sql_grain,
    generate_direct_sql_variant,
)
from semantic.llm_sql_repair import should_repair, generate_repair_sql
from sql_candidates.semantic_join_path_candidate import (
    build_semantic_join_path_sql,
)
from schema.value_profiler import grounding_profile, format_value_hints

# Confidence gate for the deterministic query-family router. At or above this,
# and only when the builder yields a VALID extraction, the family path is used;
# otherwise the existing LLM extractor runs unchanged.
FAMILY_CONFIDENCE_THRESHOLD = 0.80
from semantic.ir_validator import validate_ir
from semantic.semantic_ir import to_dict as ir_to_dict
from planning.plan_resolver import resolve_plan
from planning.plan_postprocess import apply_left_join_for_each
from planning.query_plan import to_dict as plan_to_dict
from generation.multitable_sql_generator import generate_sql
from generation.relational_algebra import to_relational_algebra
from generation.sql_types import to_dict as sql_to_dict
from generation.sql_executor import execute_sql
from generation.execution_result import to_dict as execution_to_dict
from assignment.assignment_parser import extract_assignment_spec
from assignment.assignment_db_builder import build_empty_database

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI()
init_auth_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://nl2sql-mvp.vercel.app"
    ],

    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    question: str
    user_id: int | None = None
    conversation_id: int | None = None
    schema_text: str | None = None
    


class AuthRequest(BaseModel):
    username: str
    password: str


class SchemaDatasetRequest(BaseModel):
    user_id: int
    name: str
    schema_text: str


class SignupRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str

class IRRequest(BaseModel):
    question: str
    # Ownership context (threaded from the frontend's authenticated session).
    # When present, the query endpoints verify the (user_id, username) pair owns
    # this database + conversation before running.
    user_id: int | None = None
    username: str | None = None
    conversation_id: int | None = None

class AssignmentTextRequest(BaseModel):
    user_id: int
    text: str
    name: str | None = None
    conversation_id: int | None = None

# ---------------------------------------------------------------------------
# Schema parsing helper
# ---------------------------------------------------------------------------

# Matches:  table_name (col1 TYPE, col2, ...)
# Handles optional whitespace and SQL type annotations after column names.
_SCHEMA_RE = re.compile(r"^(\w[\w\s]*?)\s*\((.+)\)\s*$", re.DOTALL)


def schema_text_to_schema_info(schema_text: str) -> dict | None:
    """
    Parse a schema string of the form  table(col1, col2, ...)  into a
    schema_info dict.  Column type annotations (e.g. 'id INTEGER') are
    stripped so only the bare column name is kept.

    Returns None if the schema string cannot be parsed.
    """
    m = _SCHEMA_RE.match(schema_text.strip())
    if not m:
        print(f"SCHEMA PARSE FAILED: {schema_text!r}", flush=True)
        return None

    table   = m.group(1).strip().lower()
    col_raw = m.group(2)

    columns = []
    for part in col_raw.split(","):
        # take the first token only — drops SQL type keywords like INTEGER, TEXT
        name = part.strip().split()[0].lower()
        if name:
            columns.append(name)

    if not columns:
        return None

    return {
        "table":       table,
        "columns":     columns,
        "schema":      schema_text.strip(),
        "aggregation": None,
        "group_by":    None,
        "sort":        None,
        "limit":       None,
    }


def get_latest_dataset_for_user(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, name, file_path, schema_text
        FROM datasets
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (user_id,)
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "name": row[1],
        "file_path": row[2],
        "schema_text": row[3],
    }

def _register_assignment_schema(user_id, name, conversation_id, spec):
    """Create a database group, build EMPTY tables from the parsed spec, and
    register schema + parser-inferred relationships. Inserts no rows."""
    generic = {"", "assignment", "database"}
    if not name or str(name).strip().lower() in generic:
        parsed = [
            t.get("name")
            for t in (spec.get("tables") or [])
            if t.get("name")
        ]
        db_name = ", ".join(parsed) if parsed else "assignment"
    else:
        db_name = name
    database_id = create_database(user_id, db_name, conversation_id)

    db_dir = f"uploads/user_{user_id}/databases/db_{database_id}"
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "data.db")
    set_database_path(database_id, db_path)

    manifest = build_empty_database(spec, db_path)

    for t in manifest["tables"]:
        schema_text = f"{t['name']}(" + ", ".join(c["name"] for c in t["columns"]) + ")"
        table_id = add_database_table(
            database_id, t["name"], "assignment_schema", db_path, schema_text, 0
        )
        columns_meta = extract_table_columns(db_path, t["name"])
        add_table_columns(table_id, columns_meta)

    edges = [
        {
            "from_table": r["from_table"], "from_column": r["from_column"],
            "to_table": r["to_table"], "to_column": r["to_column"],
            "relationship_type": "foreign_key",
            "name_similarity": 1.0, "value_overlap": 1.0,
            "confidence": 1.0, "confirmed": 1,
        }
        for r in manifest["relationships"]
    ]
    clear_relationships(database_id)
    add_relationships(database_id, edges)

    return database_id, db_path, manifest


def _generate_assignment_sql(database_id, questions):
    """Run each question through the existing IR -> plan -> SQL pipeline
    WITHOUT executing it. A failure on one question is captured as a result
    entry so it never aborts the whole import response."""
    graph = get_database_graph(database_id)
    results = []
    for q in questions:
        try:
            extraction = extract_multitable_ir_extraction(q, graph)
            ir = build_from_extraction(database_id, extraction, graph, question=q)
            validation = validate_ir(ir, graph)
            if not validation["valid"]:
                results.append({
                    "question": q, "sql": None, "params": [],
                    "relationships_used": [], "resolved": False,
                    "reason": "invalid_ir", "validation": validation,
                })
                continue
            plan_obj = resolve_plan(ir, graph)
            apply_left_join_for_each(q, plan_obj)
            plan = plan_to_dict(plan_obj)
            if not plan["resolved"]:
                results.append({
                    "question": q, "sql": None, "params": [],
                    "relationships_used": [], "resolved": False,
                    "reason": plan.get("reason"),
                })
                continue
            generated = sql_to_dict(generate_sql(plan_obj))
            results.append({
                "question": q,
                "sql": generated["sql"],
                "params": generated["params"],
                "relational_algebra": to_relational_algebra(plan_obj),
                "relationships_used": plan["joins"],
                "tables_used": plan["tables_used"],
                "resolved": True,
                "generated": generated["generated"],
            })
        except Exception as e:
            results.append({
                "question": q, "sql": None, "params": [],
                "relationships_used": [], "resolved": False,
                "reason": f"generation_error: {type(e).__name__}: {e}",
            })
    return results


def _assignment_response(database_id, db_path, manifest):
    return {
        "success": True,
        "mode": "schema_only_assignment",
        "database_id": database_id,
        "db_path": db_path,
        "tables": manifest["tables"],
        "relationships": manifest["relationships"],
        "questions": manifest["questions"],
        "generated_sql": _generate_assignment_sql(database_id, manifest["questions"]),
        "executed": False,
    }


def _extract_text_from_upload(upload) -> str:
    name = (upload.filename or "").lower()
    raw = upload.file.read()
    if name.endswith((".txt", ".md", ".sql", ".csv")):
        return raw.decode("utf-8-sig", errors="ignore")
    if name.endswith(".docx"):
        import io as _io, zipfile as _zip
        with _zip.ZipFile(_io.BytesIO(raw)) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
        xml = xml.replace("</w:p>", "\n")
        return re.sub(r"<[^>]+>", "", xml)
    if name.endswith(".pdf"):
        try:
            import io as _io, pdfplumber
            with pdfplumber.open(_io.BytesIO(raw)) as pdf:
                return "\n".join(p.extract_text() or "" for p in pdf.pages)
        except Exception:
            return ""
    return raw.decode("utf-8", errors="ignore")

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def home():
    return {"message": "NL to SQL/Hylos backend is running"}


@app.post("/signup")
def signup(request: AuthRequest):
    return create_user(request.username, request.password)


@app.post("/login")
def login(request: AuthRequest):
    return login_user(request.username, request.password)


@app.post("/upload-csv")
async def upload_csv(
    user_id: int = Form(...),
    conversation_id: int = Form(...),
    file: UploadFile = File(...)
    ):
    if not file.filename.endswith(".csv"):
        return {"success": False, "message": "Only CSV files are allowed"}

    user_folder = f"uploads/user_{user_id}/datasets"
    os.makedirs(user_folder, exist_ok=True)

    file_path = os.path.join(user_folder, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    schema_text = detect_csv_schema(file_path)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO datasets
        (user_id, conversation_id, name, file_path, file_type, schema_text)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            conversation_id,
            file.filename,
            file_path,
            "csv",
            schema_text
        )
    )

    conn.commit()
    conn.close()   

    return {
        "success": True,
        "message": "CSV uploaded successfully",
        "filename": file.filename,
        "path": file_path
    }

def _rollback_if_rejected(result, database_id):
    """When relationship resolution rejects a large DB (no declared PK/FK and no
    user-supplied relationships), roll back the just-created instance: delete the
    databases row + metadata and remove ONLY the SpiderSQL-managed db_<id> folder.
    The user's original source files outside that folder are never touched.
    Returns a rejection response dict, or None when not rejected."""
    if not isinstance(result, dict) or not result.get("rejected"):
        return None
    try:
        db_path = delete_database(database_id)
    except Exception as exc:
        print(f"ROLLBACK ERROR (metadata): {exc}", flush=True)
        db_path = result.get("db_path")
    try:
        managed_dir = os.path.dirname(db_path) if db_path else None
        # Safety: only remove a path under the managed uploads/.../databases/db_<id> tree.
        if managed_dir and os.path.basename(managed_dir) == f"db_{database_id}" \
                and os.path.isdir(managed_dir):
            shutil.rmtree(managed_dir, ignore_errors=True)
    except Exception as exc:
        print(f"ROLLBACK ERROR (folder): {exc}", flush=True)
    return {
        "success": False,
        "error": result.get("reason") or "large_database_requires_relationships",
        "message": ("This large database has no declared PK/FK relationships. "
                    "Upload a database with declared foreign-key relationships, "
                    "or provide relationships, before it can be used."),
    }


@app.post("/upload-database")
async def upload_database(
    user_id: int = Form(...),
    conversation_id: int | None = Form(None),
    name: str | None = Form(None),
    files: list[UploadFile] = File(...),
    ):
    csv_files = [f for f in files if f.filename.lower().endswith(".csv")]
    if not csv_files:
        return {"success": False, "message": "No CSV files provided"}

    db_name = name or "database"
    database_id = create_database(user_id, db_name, conversation_id)

    db_dir = f"uploads/user_{user_id}/databases/db_{database_id}"
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "data.db")
    set_database_path(database_id, db_path)

    # Large DBs (many CSVs) skip eager column extraction + global relationship
    # detection; columns load lazily on demand.
    large = is_large_database(len(csv_files))

    used_names = set()
    table_specs = []
    # Response rows in upload order: None is a placeholder for a successful table
    # (filled from the metadata result); failures are inline dicts.
    table_entries = []

    for file in csv_files:
        file_path = os.path.join(db_dir, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        base = clean_table_name(file.filename)
        table_name = base
        suffix = 2
        while table_name in used_names:
            table_name = f"{base}_{suffix}"
            suffix += 1
        used_names.add(table_name)

        load_result = load_csv_to_sqlite(
            file_path, db_path=db_path, table_name=table_name
        )

        if not load_result.get("success"):
            table_entries.append({
                "source_filename": file.filename,
                "table_name": table_name,
                "success": False,
                "message": load_result.get("message"),
            })
            continue

        schema_text = detect_csv_schema(file_path, table_name=table_name)
        table_specs.append({
            "table_name": table_name,
            "source_filename": file.filename,
            "file_path": file_path,
            "row_count": load_result.get("rows_inserted", 0),
            "schema_text": schema_text,
        })
        table_entries.append(None)

    # Value-overlap detection (small mode) must read the just-saved metadata, so
    # pass it as a callable; large mode skips it. Behavior unchanged.
    rel_provider = (lambda _did: []) if large else (
        lambda did: detect_relationships(did)
    )
    result = create_metadata(
        database_id, db_path, db_name, table_specs, rel_provider, large
    )
    _rej = _rollback_if_rejected(result, database_id)
    if _rej is not None:
        return _rej

    # Re-shape successful tables to the original CSV entry keys, interleaving
    # them with failures in upload order.
    successes = iter(result["tables"])
    tables_out = []
    for entry in table_entries:
        if entry is None:
            t = next(successes)
            tables_out.append({
                "source_filename": t["source_filename"],
                "table_name": t["table_name"],
                "rows_inserted": t["rows_inserted"],
                "schema_text": t["schema_text"],
                "columns": t["columns"],
                "success": True,
            })
        else:
            tables_out.append(entry)
    result["tables"] = tables_out
    return result


@app.post("/create-database-from-schema")
async def create_database_from_schema(
    user_id: int = Form(...),
    conversation_id: int | None = Form(None),
    name: str | None = Form(None),
    schema_text: str | None = Form(None),
    file: UploadFile | None = File(None),
    ):
    """Create an EMPTY SQLite database workspace from SQL DDL (CREATE TABLE
    only). Schema may come from `schema_text` or an uploaded .txt/.md/.sql file.
    Inserts no rows. Response shape mirrors /upload-database so the frontend can
    reuse onDatabaseCreated()."""
    text = schema_text or ""

    # Fall back to an uploaded text-based schema file when no text was pasted.
    if not text.strip() and file is not None:
        fname = (file.filename or "").lower()
        if fname.endswith(".docx"):
            # Extract schema text from the DOCX (reuses the existing
            # zipfile-based extractor — no new dependency), then parse it
            # exactly like pasted / .txt / .md / .sql schema input below.
            try:
                text = _extract_text_from_upload(file)
            except Exception as exc:
                return {"success": False,
                        "message": f"Could not read DOCX schema: {exc}"}
            if not text.strip():
                return {"success": False,
                        "message": "The DOCX contained no readable schema text."}
        elif not (fname.endswith(".txt") or fname.endswith(".md")
                  or fname.endswith(".sql")):
            return {
                "success": False,
                "message": "Unsupported file type. Use .txt, .md, .sql, or "
                           ".docx, or paste SQL.",
            }
        else:
            raw = await file.read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("latin-1", errors="replace")

    if not text.strip():
        return {"success": False, "message": "No schema text provided."}

    db_name = (name or "").strip() or "database"
    database_id = create_database(user_id, db_name, conversation_id)

    db_dir = f"uploads/user_{user_id}/databases/db_{database_id}"
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "data.db")
    set_database_path(database_id, db_path)

    try:
        table_names = create_empty_db_from_ddl(text, db_path)
    except SchemaDDLError as e:
        return {"success": False, "message": str(e)}

    large = is_large_database(len(table_names))

    # Relationship detection. Explicit FOREIGN KEY constraints are cheap and used
    # in both modes. The name-based fallback (O(tables x columns)) runs only for
    # small databases; large databases stay FK-only.
    fk_edges = extract_declared_foreign_keys(text)
    if fk_edges:
        relationships = fk_edges
    elif large:
        relationships = []
    else:
        relationships = infer_schema_name_relationships(db_path, table_names)

    table_specs = [
        {"table_name": t, "source_filename": "schema_ddl",
         "file_path": db_path, "row_count": 0}
        for t in table_names
    ]
    result = create_metadata(
        database_id, db_path, db_name, table_specs, relationships, large
    )
    _rej = _rollback_if_rejected(result, database_id)
    if _rej is not None:
        return _rej
    result["tables"] = [
        {"table_name": t["table_name"], "rows_inserted": t["rows_inserted"],
         "success": True}
        for t in result["tables"]
    ]
    return result


@app.post("/upload-sqlite")
async def upload_sqlite(
    user_id: int = Form(...),
    conversation_id: int | None = Form(None),
    name: str | None = Form(None),
    file: UploadFile = File(...),
    ):
    """Register an uploaded SQLite (.db/.sqlite/.sqlite3) file as a database
    group. The file is stored as the database's db_path, its real tables and
    columns are inspected, and metadata is created through the SAME pipeline
    as CSV / schema imports (create_metadata), so it appears in the database
    list and becomes selectable/queryable like any other database."""
    fname = (file.filename or "").lower()
    if not fname.endswith((".db", ".sqlite", ".sqlite3")):
        return {"success": False,
                "message": "Please upload a .db, .sqlite, or .sqlite3 file."}

    base = os.path.splitext(os.path.basename(file.filename or ""))[0]
    db_name = (name or "").strip() or base or "database"
    database_id = create_database(user_id, db_name, conversation_id)

    db_dir = f"uploads/user_{user_id}/databases/db_{database_id}"
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "data.db")
    set_database_path(database_id, db_path)

    # Persist the uploaded SQLite bytes as the database file.
    raw = await file.read()
    with open(db_path, "wb") as buffer:
        buffer.write(raw)

    # Inspect real tables/columns from the uploaded database.
    try:
        table_specs = inspect_sqlite_file(db_path)
    except ValueError as exc:
        return {"success": False, "message": str(exc)}
    except Exception as exc:
        return {"success": False,
                "message": f"Could not read SQLite database: {exc}"}
    if not table_specs:
        return {"success": False,
                "message": "No tables found in the uploaded SQLite database."}

    for spec in table_specs:
        spec["source_filename"] = file.filename
        spec["file_path"] = db_path

    large = is_large_database(len(table_specs))
    # Declared FKs in the uploaded DB are read by create_metadata itself;
    # small mode adds value-overlap/name-based edges from the real data.
    rel_provider = (lambda _did: []) if large else (
        lambda did: detect_relationships(did)
    )
    result = create_metadata(
        database_id, db_path, db_name, table_specs, rel_provider, large
    )
    _rej = _rollback_if_rejected(result, database_id)
    if _rej is not None:
        return _rej
    result["tables"] = [
        {"table_name": t["table_name"],
         "rows_inserted": t.get("rows_inserted", 0),
         "columns": t.get("columns", []),
         "success": True}
        for t in result["tables"]
    ]
    return result


# ---------------------------------------------------------------------------
# Local benchmark databases — list + load the accepted relational sample DBs
# ---------------------------------------------------------------------------

class LocalBenchmarkLoadRequest(BaseModel):
    user_id: int
    conversation_id: int | None = None


@app.get("/local_benchmarks/databases")
def local_benchmarks_list():
    """List the accepted local benchmark databases and whether each SQLite file
    exists locally (available=false when the file is missing)."""
    return {"success": True, "databases": list_benchmarks()}


@app.post("/local_benchmarks/databases/{benchmark_id}/load")
def local_benchmarks_load(benchmark_id: str, body: LocalBenchmarkLoadRequest):
    """Load one benchmark into the current chat, reusing the SAME registration
    flow as an uploaded SQLite file (create_database -> copy -> create_metadata).
    The source template under relational_sample_dbs/sqlite/ is never modified."""
    return load_benchmark(
        benchmark_id, body.user_id, body.conversation_id,
        create_database=create_database,
        set_database_path=set_database_path,
        inspect_sqlite_file=inspect_sqlite_file,
        is_large_database=is_large_database,
        create_metadata=create_metadata,
        uploads_root="uploads",
    )


# ---------------------------------------------------------------------------
# Spider 2.0 — local sample catalog browse + import (no cloud, app-side only)
# ---------------------------------------------------------------------------

class Spider2ImportRequest(BaseModel):
    user_id: int
    conversation_id: int | None = None
    spider2_id: str


@app.get("/spider2/status")
def spider2_status_endpoint():
    """Report whether a local Spider 2.0 data source is configured."""
    return {"success": True, **spider2_status()}


@app.get("/spider2/catalog")
def spider2_catalog(
    user_id: int | None = None,
    q: str | None = None,
    include_samples: bool = False,
):
    """Browse/search the local Spider 2.0 catalog. Returns only schemas with
    usable join signal (declared FK / inferable joins); partition-family and
    no-join schemas are hidden. Developer samples only when include_samples=true."""
    return {
        "success": True,
        "items": spider2_list_catalog(q, include_samples),
        "signal_counts": spider2_signal_counts(),
    }


@app.post("/spider2/import")
def spider2_import(req: Spider2ImportRequest):
    """Import a catalog entry as an EMPTY SQLite database workspace. Mirrors the
    create-database response so the frontend reuses onDatabaseCreated(). Only
    items that carry full table schema are importable."""
    entry = spider2_get_entry(req.spider2_id)
    if not entry:
        return {"success": False, "message": f"Unknown spider2_id: {req.spider2_id}"}

    if not spider2_entry_importable(entry):
        return {
            "success": False,
            "message": "This Spider 2.0 item does not include local schema "
                       "information yet.",
        }

    db_name = entry.get("name") or req.spider2_id
    database_id = create_database(req.user_id, db_name, req.conversation_id)

    db_dir = f"uploads/user_{req.user_id}/databases/db_{database_id}"
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "data.db")
    set_database_path(database_id, db_path)

    try:
        table_names = create_empty_db_from_ddl(spider2_entry_to_ddl(entry), db_path)
    except SchemaDDLError as e:
        return {"success": False, "message": f"Import failed: {e}"}

    large = is_large_database(len(table_names))

    # Relationships: prefer REAL declared FK constraints (A). When the schema
    # declares none but has a join signal (inferable_join_schema / mixed), fall
    # back to bounded, deterministic name-based suggestions (B) so metadata is
    # useful immediately. confirmed=False, confidence<1.0, capped per database.
    relationships = spider2_entry_edges(entry)
    inferred_count = 0
    if not relationships:
        relationships = spider2_entry_inferred_edges(entry)
        inferred_count = len(relationships)

    table_specs = [
        {"table_name": t, "source_filename": "spider2_catalog",
         "file_path": db_path, "row_count": 0}
        for t in table_names
    ]
    result = create_metadata(
        database_id, db_path, db_name, table_specs, relationships, large,
        source={"type": "spider2", "spider2_id": req.spider2_id},
    )
    _rej = _rollback_if_rejected(result, database_id)
    if _rej is not None:
        return _rej
    result["tables"] = [
        {"table_name": t["table_name"], "rows_inserted": t["rows_inserted"],
         "success": True}
        for t in result["tables"]
    ]
    # Spider 2.0 imports are schema-only (empty tables, no local data rows).
    result["data_availability"] = "schema_only"
    result["data_note"] = "Schema-only import. Local data rows are not included."
    result["relationship_count"] = len(result.get("relationships", []))
    result["inferred_relationship_count"] = inferred_count
    skipped_reserved = entry.get("skipped_reserved_tables", 0)
    if skipped_reserved:
        result["skipped_reserved_tables"] = skipped_reserved
        result["data_note"] += (
            f" Skipped {skipped_reserved} reserved SQLite "
            f"table name(s) (sqlite_*)."
        )
    return result


@app.get("/datasets/{user_id}")
def get_user_datasets(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, name, file_path,schema_text, created_at
        FROM datasets
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,)
    )

    rows = cursor.fetchall()
    conn.close()

    datasets = [
        {
            "id": row[0],
            "name": row[1],
            "file_path": row[2],
            "schema_text": row[3],
            "created_at": row[4],
        }
        for row in rows
    ]

    return {
        "success": True,
        "datasets": datasets
    }

@app.get("/databases/{user_id}")
def list_databases(user_id: int):
    return {"success": True, "databases": get_user_databases(user_id)}


@app.get("/database/{database_id}")
def database_detail(database_id: int):
    db = get_database(database_id)
    if not db:
        return {"success": False, "message": "Database not found"}
    db["tables"] = get_database_tables(database_id)
    return {"success": True, "database": db}


@app.get("/database/{database_id}/schema")
def database_schema(database_id: int):
    schema = get_database_schema(database_id)
    if not schema:
        return {"success": False, "message": "Database not found"}
    return {"success": True, "database": schema}


def _access_error(database_id, user_id, username, conversation_id):
    """Ownership enforcement for every relationship + query operation. Verifies
    the login-issued (user_id, username) pair, that the database belongs to that
    user AND the specified conversation, and that the conversation belongs to the
    user. Returns an error dict on any mismatch, else None."""
    ok, reason = verify_database_access(
        user_id, username, conversation_id, database_id)
    if not ok:
        return {"success": False, "error": "access_denied", "message": reason}
    return None


@app.get("/database/{database_id}/relationships")
def database_relationships(database_id: int, user_id: int = None,
                           username: str = None, conversation_id: int = None):
    err = _access_error(database_id, user_id, username, conversation_id)
    if err is not None:
        return err
    return {"success": True,
            "relationships": get_relationships(database_id),
            "relationship_status": get_relationship_status(database_id)}


@app.post("/database/{database_id}/detect-relationships")
def redetect_relationships(database_id: int, user_id: int = None,
                           username: str = None, conversation_id: int = None):
    """Explicit redetection through the single authority resolver: PK/FK
    constraints win (100%, no inference); a small DB with none gets inferred
    suggestions; a large DB with none and no user rows is rejected. The result
    always returns to 'review' — approval is a separate step."""
    err = _access_error(database_id, user_id, username, conversation_id)
    if err is not None:
        return err
    from services.relationship_resolver import resolve_and_store_relationships
    res = resolve_and_store_relationships(database_id, force_inference=True)
    if res.get("rejected"):
        return {"success": False, "error": res.get("reason"),
                "message": ("Detection produced no usable relationship set. "
                            "Add relationships manually before querying.")}
    return {"success": True, "relationships": res.get("edges", []),
            "relationship_status": res.get("status") or "review"}


def _validate_relationship_endpoints(database_id, from_table, from_column,
                                     to_table, to_column):
    """Ensure both endpoints reference tables that exist in this database's
    metadata. Returns (ok, message)."""
    tables = {t["table_name"] for t in (get_database_tables(database_id) or [])}
    for tbl in (from_table, to_table):
        if tbl not in tables:
            return False, f"unknown table '{tbl}' for database {database_id}"
    return True, ""


class UserRelationshipBody(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    relationship_type: str = "foreign_key"


@app.post("/database/{database_id}/relationships")
def create_user_relationship(database_id: int, body: UserRelationshipBody,
                             user_id: int = None, username: str = None,
                             conversation_id: int = None):
    """Add a user relationship to the single stored set. Any edit returns the
    database to 'review' until re-finalized."""
    err = _access_error(database_id, user_id, username, conversation_id)
    if err is not None:
        return err
    ok, msg = _validate_relationship_endpoints(
        database_id, body.from_table, body.from_column,
        body.to_table, body.to_column)
    if not ok:
        return {"success": False, "message": msg}
    rel_id = add_user_relationship(
        database_id, body.from_table, body.from_column,
        body.to_table, body.to_column, body.relationship_type)
    set_all_relationships_confirmed(database_id, False)
    set_relationship_status(database_id, "review")
    return {"success": True, "relationship_id": rel_id,
            "relationship_status": "review"}


@app.patch("/database/{database_id}/relationships/{rel_id}")
def edit_user_relationship(database_id: int, rel_id: int,
                           body: dict = Body(default=None),
                           user_id: int = None, username: str = None,
                           conversation_id: int = None):
    err = _access_error(database_id, user_id, username, conversation_id)
    if err is not None:
        return err
    update_relationship(rel_id, **{k: v for k, v in (body or {}).items()})
    set_all_relationships_confirmed(database_id, False)
    set_relationship_status(database_id, "review")
    return {"success": True, "relationship_status": "review"}


@app.delete("/database/{database_id}/relationships/{rel_id}")
def remove_user_relationship(database_id: int, rel_id: int,
                             user_id: int = None, username: str = None,
                             conversation_id: int = None):
    err = _access_error(database_id, user_id, username, conversation_id)
    if err is not None:
        return err
    delete_relationship(rel_id)
    set_all_relationships_confirmed(database_id, False)
    set_relationship_status(database_id, "review")
    return {"success": True, "relationship_status": "review"}


@app.put("/database/{database_id}/relationships")
def replace_relationship_set(database_id: int, body: dict = Body(default=None),
                             user_id: int = None, username: str = None,
                             conversation_id: int = None):
    """Replace the entire stored relationship set with the reviewed list (used by
    the review card, which edits locally then commits). Per-row `source` is
    preserved; rows without a source are treated as user-added. Sets the database
    back to 'review' (the caller finalizes separately)."""
    err = _access_error(database_id, user_id, username, conversation_id)
    if err is not None:
        return err
    incoming = (body or {}).get("relationships") or []
    sanitized = []
    for r in incoming:
        if not isinstance(r, dict):
            continue
        if not (r.get("from_table") and r.get("from_column")
                and r.get("to_table") and r.get("to_column")):
            continue
        src = r.get("source") or "user"
        sanitized.append({
            "from_table": r.get("from_table"),
            "from_column": r.get("from_column"),
            "to_table": r.get("to_table"),
            "to_column": r.get("to_column"),
            "relationship_type": r.get("relationship_type") or "foreign_key",
            "name_similarity": r.get("name_similarity"),
            "value_overlap": r.get("value_overlap"),
            "confidence": r.get("confidence",
                                1.0 if src in ("pk_fk", "user") else None),
            # Saving a reviewed set leaves it unapproved until finalized; the
            # finalize step marks every row confirmed. Origin is preserved.
            "confirmed": 0,
            "source": src,
        })
    clear_relationships(database_id)
    add_relationships(database_id, sanitized)
    set_all_relationships_confirmed(database_id, False)
    set_relationship_status(database_id, "review")
    return {"success": True, "relationships": get_relationships(database_id),
            "relationship_status": "review"}


@app.post("/database/{database_id}/relationships/finalize")
def finalize_relationships(database_id: int, user_id: int = None,
                           username: str = None, conversation_id: int = None):
    """Approve the current stored set; enables querying for this instance.
    Marks every current relationship row confirmed (approval is separate from
    origin — `source` is unchanged) so the finalized set renders as Confirmed."""
    err = _access_error(database_id, user_id, username, conversation_id)
    if err is not None:
        return err
    set_all_relationships_confirmed(database_id, True)
    set_relationship_status(database_id, "finalized")
    return {"success": True, "relationship_status": "finalized",
            "relationships": get_relationships(database_id)}


@app.get("/database/{database_id}/graph")
def database_graph(database_id: int, summary: bool = False):
    # Opt-in lightweight summary (no full graph build). Default is unchanged so
    # existing consumers (RelationshipReviewCard, DatabaseWorkspace) keep working.
    if summary:
        meta = get_database_meta(database_id)
        if not meta:
            return {"success": False, "message": "Database not found"}
        return {
            "success": True,
            "database_id": database_id,
            "mode": meta["mode"],
            "table_count": meta["table_count"],
            "relationship_count": len(get_relationships(database_id)),
            "message": "Large database graph is available through metadata "
                       "retrieval. Full graph is not loaded by default.",
        }

    graph = get_database_graph(database_id)
    if not graph:
        return {"success": False, "message": "Database not found"}
    return {"success": True, "database": graph}


# ---------------------------------------------------------------------------
# Phase 1 — lazy schema endpoints (metadata, paginated tables, lazy columns).
# Additive: query execution / SQL generation / relationships are unchanged.
# ---------------------------------------------------------------------------
@app.get("/database/{database_id}/meta")
def database_meta(database_id: int):
    meta = get_database_meta(database_id)
    if not meta:
        return {"success": False, "message": "Database not found"}
    return {"success": True, **meta}


@app.get("/database/{database_id}/tables")
def database_tables_list(
    database_id: int,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    return {"success": True, **lazy_list_tables(database_id, q, limit, offset)}


@app.get("/database/{database_id}/table/{table_name}/columns")
def database_table_columns(database_id: int, table_name: str):
    res = lazy_ensure_table_columns(database_id, table_name)
    if res is None:
        return {"success": False, "message": "Table not found"}
    return {"success": True, **res}


# --- Phase 3: query-time retrieval + sub-graph (large-DB scalability) --------
class RetrieveRequest(BaseModel):
    question: str
    k: int | None = 8


@app.post("/database/{database_id}/retrieve")
def database_retrieve(database_id: int, body: RetrieveRequest):
    """Top-k relevant tables for a question (debug / future UI). Does NOT load
    the full graph."""
    meta = get_database_meta(database_id)
    if not meta:
        return {"success": False, "message": "Database not found"}
    tables = retrieve_tables(database_id, body.question, k=body.k or 8)
    return {
        "success": True,
        "database_id": database_id,
        "mode": meta["mode"],
        "tables": tables,
    }


@app.get("/database/{database_id}/subgraph")
def database_subgraph(database_id: int, tables: str | None = None):
    """Build a sub-graph for an explicit comma-separated table set (testing)."""
    names = [t.strip() for t in (tables or "").split(",") if t.strip()]
    graph = build_subgraph(database_id, names)
    if graph is None:
        return {"success": False, "message": "Database not found"}
    return {
        "success": True,
        "database_id": database_id,
        "tables": graph.get("tables", []),
        "relationships": graph.get("relationships", []),
    }


@app.post("/dataset/schema")
def add_schema_dataset(request: SchemaDatasetRequest):
    return save_schema_dataset(request.user_id, request.name, request.schema_text)


@app.get("/dataset/latest/{user_id}")
def latest_dataset(user_id: int):
    dataset = get_latest_dataset(user_id)
    if not dataset:
        return {"success": False, "message": "No dataset found"}
    return {"success": True, "dataset": dataset}

@app.post("/database/{database_id}/ir")
def inspect_ir(database_id: int, body: IRRequest):
    # Mode-aware schema selection (small=full graph, large=retrieved subgraph).
    graph, _tables_considered, early = resolve_query_graph(database_id, body.question)
    if early is not None:
        return early

    extraction = extract_multitable_ir_extraction(body.question, graph)
    ir = build_from_extraction(database_id, extraction, graph, question=body.question)
    validation = validate_ir(ir, graph)

    return {
        "success": True,
        "database_id": database_id,
        "question": body.question,
        "extraction": extraction,
        "ir": ir_to_dict(ir),
        "validation": validation,
    }

@app.post("/database/{database_id}/resolve")
def resolve_query_plan(database_id: int, body: IRRequest):
    # Mode-aware schema selection (small=full graph, large=retrieved subgraph).
    graph, _tables_considered, early = resolve_query_graph(database_id, body.question)
    if early is not None:
        return early

    extraction = extract_multitable_ir_extraction(
        body.question,
        graph
    )

    ir = build_from_extraction(
        database_id,
        extraction,
        graph,
        question=body.question
    )

    validation = validate_ir(ir, graph)

    plan = None

    if validation["valid"]:
        plan = plan_to_dict(
            resolve_plan(ir, graph)
        )

    return {
        "success": True,
        "database_id": database_id,
        "question": body.question,
        "extraction": extraction,
        "ir": ir_to_dict(ir),
        "validation": validation,
        "plan": plan
    }

@app.post("/database/{database_id}/generate_sql")
def generate_sql_endpoint(database_id: int, body: IRRequest):
    # Mode-aware schema selection (small=full graph, large=retrieved subgraph).
    graph, _tables_considered, early = resolve_query_graph(database_id, body.question)
    if early is not None:
        return early

    extraction = extract_multitable_ir_extraction(body.question, graph)
    ir = build_from_extraction(database_id, extraction, graph, question=body.question)
    validation = validate_ir(ir, graph)

    base = {
        "database_id": database_id,
        "question": body.question,
        "extraction": extraction,
        "ir": ir_to_dict(ir),
        "validation": validation,
    }

    if not validation["valid"]:
        return {
            "success": False,
            **base,
            "plan": None,
            "generated_sql": None,
        }

    plan_obj = resolve_plan(ir, graph)
    apply_left_join_for_each(body.question, plan_obj)
    plan = plan_to_dict(plan_obj)

    if not plan["resolved"]:
        return {
            "success": False,
            **base,
            "plan": plan,
            "generated_sql": None,
        }

    generated = sql_to_dict(generate_sql(plan_obj))

    return {
        "success": generated["generated"],
        **base,
        "plan": plan,
        "generated_sql": generated,
        "relational_algebra": to_relational_algebra(plan_obj),
    }

@app.post("/assignment/import-text")
def assignment_import_text(body: AssignmentTextRequest):
    """Mode C — pasted assignment/schema text -> empty tables + SQL per question."""
    spec = extract_assignment_spec(body.text)
    if not spec["tables"]:
        return {"success": False, "mode": "schema_only_assignment",
                "message": "No table definitions found in the provided text."}
    database_id, db_path, manifest = _register_assignment_schema(
        body.user_id, body.name, body.conversation_id, spec
    )
    return _assignment_response(database_id, db_path, manifest)


@app.post("/assignment/import-file")
async def assignment_import_file(
    user_id: int = Form(...),
    conversation_id: int | None = Form(None),
    name: str | None = Form(None),
    file: UploadFile = File(...),
):
    """Mode B — assignment document upload -> empty tables + SQL per question."""
    text = _extract_text_from_upload(file)
    spec = extract_assignment_spec(text)
    if not spec["tables"]:
        return {"success": False, "mode": "schema_only_assignment",
                "message": "No table definitions found in the uploaded document."}
    database_id, db_path, manifest = _register_assignment_schema(
        user_id, name, conversation_id, spec
    )
    return _assignment_response(database_id, db_path, manifest)

def _log_layer(n, title):
    """Print a clear banner so the console groups each pipeline layer."""
    bar = "=" * 72
    print(f"\n{bar}\n  LAYER {n}: {title}\n{bar}", flush=True)


def run_nl_sql_pipeline(database_id: int, question: str) -> dict:
    """Shared NL->SQL pipeline (table-pick -> checklist -> multi-candidate
    build -> score/select -> repair -> execute).

    Extracted verbatim from the original execute_sql_endpoint body so that
    /execute_sql and /check_containment run ONE identical code path with no
    duplication. `question` replaces the former request field; a tiny local
    `body` shim keeps every existing `body.question` reference intact, so the
    pipeline logic below is byte-for-byte unchanged and its return contract is
    preserved exactly.
    """
    body = IRRequest(question=question)
    full_trace.begin(database_id, question)   # no-op unless SPIDERSQL_FULL_TRACE
    meta = get_database_meta(database_id)
    if not meta:
        return {"success": False, "message": "Database not found"}

    # Relationship-finality gate: queries run ONLY on a finalized, authoritative
    # relationship set. A database whose relationships are unfinalized (empty or
    # unreviewed inference suggestions) must be detected/finalized first — the
    # query interface never fabricates relationships to fill the gap.
    if not get_relationships_finalized(database_id):
        return {
            "success": False,
            "error": "relationships_not_finalized",
            "message": ("This database's relationships are not finalized. "
                        "Run relationship detection and finalize the set "
                        "before querying."),
            "database_id": database_id,
        }

    # Mode-aware schema selection (small = full graph, large = retrieve top-k +
    # sub-graph). Shared helper; behavior unchanged. Returns an early response
    # for no_relevant_tables_found / requested_date_table_not_found / not-found.
    _log_layer(1, "TABLE-PICKING - choose which tables are in play")
    graph, tables_considered, early = resolve_query_graph(
        database_id, body.question, meta
    )
    if early is not None:
        return early

    # NOTE (relationship lifecycle): query-time relationship augmentation was
    # removed. Benchmark-trusted and declared FK edges are imported and saved as
    # metadata at database setup / redetection (services/relationship_resolver),
    # so the graph handed to generation/validation/scoring is exactly the
    # finalized stored set. Queries never create, merge, or rediscover
    # relationships.

    # Force explicitly-named tables into the graph (MODE-INDEPENDENT + physical
    # fallback): top-k retrieval must never hide a table the question named
    # verbatim, AND a table missing from database_tables METADATA but present
    # physically must still be injected (build_subgraph drops non-metadata
    # tables). Loud [GRAPH FORCE] logs make the table set auditable.
    try:
        graph, _fdbg = force_named_tables(graph, body.question, database_id)
        print(f"[GRAPH FORCE] database_id={_fdbg['database_id']}", flush=True)
        print(f"[GRAPH FORCE] all_db_tables={_fdbg['all_db_tables']}", flush=True)
        print(f"[GRAPH FORCE] explicit_names={_fdbg['explicit_names']}", flush=True)
        print(f"[GRAPH FORCE] found_named={_fdbg['found_named']}", flush=True)
        print(f"[GRAPH FORCE] missing_named={_fdbg['missing_named']}", flush=True)
        if _fdbg["metadata_missing"]:
            print("[METADATA] explicitly-named tables present PHYSICALLY but "
                  f"MISSING from database_tables metadata: {_fdbg['metadata_missing']} "
                  "(injected into graph from physical schema)", flush=True)
        print(f"[GRAPH FORCE] final_subgraph_tables={_fdbg['final_subgraph_tables']}",
              flush=True)
        full_trace.note("layer3", "graph_force", _fdbg)
    except Exception as exc:
        print(f"GRAPH FORCE ERROR: {exc}", flush=True)
    print("[GRAPH] available tables for checklist: "
          f"{[t.get('table_name') for t in (graph.get('tables') or [])]}",
          flush=True)

    # =========================================================================
    # Multi-candidate SQL selection.
    # Instead of trusting ONE path (query family gate OR LLM fallback), build
    # several candidates (family + LLM primary + LLM variants), run each
    # through the same IR -> plan -> SQL -> execute pipeline, score them
    # against the question/schema, and select via execution self-consistency
    # + validation score. Wrong-but-executable SQL scores low and loses.
    # =========================================================================
    db_path = get_database_path(database_id)
    candidates = []

    # Physical table names — used to normalize hallucinated SQL-Server schema
    # prefixes (Purchasing.PurchaseOrderHeader -> PurchaseOrderHeader) on every
    # generated direct/repair SQL, so a semantically-correct candidate is not
    # lost to a bare qualification error. Read once; empty on any problem.
    try:
        _phys_names = list(physical_tables(db_path).keys())
    except Exception:
        _phys_names = []

    def _norm_sql(s):
        return normalize_schema_prefixes(s, _phys_names) if s else s

    # -- Value grounding: sample distinct values of enum-like columns so the
    #    LLM writes literals with the DB's actual conventions (yes/no vs
    #    true/false). Schema-only DBs ground from the seeded eval copy
    #    (prompts only — the user's DB is never written).
    try:
        value_profile, value_grounded_from_eval = grounding_profile(
            database_id, db_path)
        value_hints = format_value_hints(value_profile)
    except Exception as exc:
        print(f"VALUE PROFILER ERROR: {exc}", flush=True)
        value_profile, value_grounded_from_eval, value_hints = {}, False, ""

    # -- Semantic checklist (Stage 2): one LLM call producing the explicit
    #    contract the correct SQL must satisfy. Used as the strongest scorer
    #    signal + question-anchored fatal checks. None on failure — everything
    #    below degrades gracefully.
    _log_layer(2, "CHECKLIST - rules a correct answer must follow")
    try:
        checklist = generate_checklist(body.question, graph, value_hints)
    except Exception as exc:
        print(f"SEMANTIC CHECKLIST ERROR: {exc}", flush=True)
        checklist = None
    # Schema-linker correction: force exact-named tables, disambiguate
    #    same-family siblings by question tokens, add ZIP<->tract bridge and
    #    the real metric/ACS table. Corrects must_use_tables BEFORE any
    #    candidate generation so the focused schema is not poisoned.
    try:
        checklist = correct_checklist_tables(body.question, checklist, graph)
    except Exception as exc:
        print(f"SCHEMA LINKER ERROR: {exc}", flush=True)

    # -- Typed grain contract (semantic-contract Stage 0): machine-checkable
    #    view of the checklist's optional grain fields, consumed by the grain
    #    validator during scoring. Building it can never fail the request; a
    #    None / low-confidence contract simply means grain validation is
    #    skipped or advisory.
    grain_contract = None
    try:
        grain_contract = build_grain_contract(checklist, graph)
        if grain_contract is not None:
            print("SEMANTIC CONTRACT:", contract_to_dict(grain_contract),
                  flush=True)
        else:
            print("SEMANTIC CONTRACT: none (typed grain fields absent) — "
                  "grain validation skipped", flush=True)
    except Exception as exc:
        print(f"SEMANTIC CONTRACT ERROR: {exc}", flush=True)
        grain_contract = None

    # -- large-mode IR postprocess (table fallback + partition filter), applied
    #    per LLM candidate. Mirrors the previous single-path behavior.
    def _make_ir_postprocess():
        def _post(ir):
            diag = {"large_mode_table_fallback": False, "fallback_table": None}
            if meta["mode"] != "large":
                return diag
            if tables_considered:
                ir_tables = ir["tables"] if isinstance(ir, dict) else getattr(ir, "tables", None)
                if not ir_tables:
                    fb = tables_considered[0]["table_name"]
                    if isinstance(ir, dict):
                        ir["tables"] = [fb]
                    else:
                        ir.tables = [fb]
                    diag["large_mode_table_fallback"] = True
                    diag["fallback_table"] = fb
            diag.update(remove_redundant_partition_date_filters(ir))
            ir_tables_now = ir["tables"] if isinstance(ir, dict) else getattr(ir, "tables", None)
            ambiguity = detect_partitioned_ambiguity(body.question, ir_tables_now)
            if ambiguity:
                diag["ambiguity"] = ambiguity
            return diag
        return _post

    _log_layer(3, "EXTRACTION - turn the question into recipe-based SQL candidates")
    # -- Candidate A: query-family builder (kept behind its confidence gate).
    #    The guard verdict no longer hard-blocks: a guard-rejected family
    #    candidate still competes, but the scorer penalizes it, so selection
    #    (not a binary gate) decides. Routing must never break the endpoint.
    family_name = None
    family_confidence = None
    family_reason = None
    family_guard_valid = None
    family_guard_reasons = None
    try:
        fam_extraction, decision = route_and_build(body.question, graph)
        family_name = decision.get("family")
        family_confidence = decision.get("confidence")
        family_reason = decision.get("reason")
        if (fam_extraction is not None
                and (family_confidence or 0) >= FAMILY_CONFIDENCE_THRESHOLD):
            fam_ir = build_from_extraction(database_id, fam_extraction, graph)
            if validate_ir(fam_ir, graph)["valid"]:
                guard = validate_family_output(
                    body.question, family_name, fam_extraction, fam_ir, graph)
                family_guard_valid = guard["valid"]
                family_guard_reasons = guard["reasons"]
                candidates.append(build_candidate(
                    source="query_family",
                    label="query_family",
                    question=body.question,
                    database_id=database_id,
                    extraction=fam_extraction,
                    graph=graph,
                    db_path=db_path,
                    question_aware=False,
                    family_info={
                        "family": family_name,
                        "confidence": family_confidence,
                        "guard_valid": guard["valid"],
                        "guard_reasons": guard["reasons"],
                    },
                ))
    except Exception as exc:
        print(f"QUERY FAMILY ROUTER ERROR: {exc}", flush=True)

    have_family = bool(candidates)

    # -- Candidate B: normal LLM extraction (unchanged primary fallback path).
    primary_extraction = extract_multitable_ir_extraction(body.question, graph)
    primary = build_candidate(
        source="llm_primary",
        label="llm_primary",
        question=body.question,
        database_id=database_id,
        extraction=primary_extraction,
        graph=graph,
        db_path=db_path,
        ir_postprocess=_make_ir_postprocess(),
    )
    candidates.append(primary)

    # Partitioned-table ambiguity (large mode): preserved early clarification,
    # unless the deterministic family candidate already answered cleanly.
    ambiguity = primary.diagnostics.get("ambiguity")
    if ambiguity and not any(c.source == "query_family" and c.executed_ok
                             for c in candidates):
        return {
            "success": False,
            **ambiguity,
            "database_id": database_id,
            "question": body.question,
            "tables_considered": tables_considered,
        }

    # -- Candidates C/D: LLM variants (different prompt emphasis + mild
    #    temperature). One variant when the family produced a candidate,
    #    two otherwise — max 4 candidates total. Duplicate extractions are
    #    skipped: an identical reading adds no information.
    def _ext_key(e):
        try:
            return json.dumps(e, sort_keys=True, default=str)
        except Exception:
            return repr(e)

    seen_extractions = {_ext_key(c.extraction) for c in candidates}
    variant_count = 1 if have_family else 2
    for v in range(1, variant_count + 1):
        try:
            var_extraction = extract_multitable_ir_extraction_variant(
                body.question, graph, variant=v)
        except Exception as exc:
            print(f"LLM VARIANT {v} ERROR: {exc}", flush=True)
            var_extraction = None
        if not var_extraction:
            continue
        key = _ext_key(var_extraction)
        if key in seen_extractions:
            continue
        seen_extractions.add(key)
        candidates.append(build_candidate(
            source="llm_variant",
            label=f"llm_variant_{v}",
            question=body.question,
            database_id=database_id,
            extraction=var_extraction,
            graph=graph,
            db_path=db_path,
            ir_postprocess=_make_ir_postprocess(),
        ))

    # -- Candidate E0: semantic join-path (Phase 4). DISABLED BY DEFAULT
    #    (made bq023 worse); set ENABLE_SEMANTIC_JOIN_PATH=1 to re-enable.
    #    Code retained — only skipped in runtime selection while off.
    if os.getenv("ENABLE_SEMANTIC_JOIN_PATH", "").strip().lower() in ("1", "true", "yes", "on"):
        try:
            sjp_sql = build_semantic_join_path_sql(
                body.question, graph, checklist, value_hints)
        except Exception as exc:
            print(f"SEMANTIC JOIN PATH ERROR: {exc}", flush=True)
            sjp_sql = None
        if sjp_sql:
            candidates.append(build_direct_sql_candidate(
                label="semantic_join_path", sql=sjp_sql, db_path=db_path,
                source="semantic_join_path"))

    _log_layer(4, "SQL WRITING - Creates SQL directly (plain / grain / variant)")
    # -- Candidate E: direct LLM SQL (Stage 2). One question->SQL call with the
    #    relevant schema, FK edges, and the checklist. Not gated by the IR
    #    pipeline, so it can express shapes the families/IR cannot.
    try:
        direct_sql = generate_direct_sql(body.question, graph, checklist,
                                         value_hints)
    except Exception as exc:
        print(f"DIRECT SQL ERROR: {exc}", flush=True)
        direct_sql = None
    direct_sql = _norm_sql(direct_sql)
    if direct_sql:
        _v = direct_sql_violations(direct_sql, body.question, checklist, graph)
        if _v:
            print(f"REJECTED direct candidate llm_sql_direct: {_v}", flush=True)
            full_trace.note("layer5", "rejected::llm_sql_direct",
                            {"sql": direct_sql, "violations": _v})
        else:
            candidates.append(build_direct_sql_candidate(
                label="llm_sql_direct", sql=direct_sql, db_path=db_path))

    # -- Candidates F/G: alternate direct-SQL samples (Option B). Two more
    #    question->SQL calls that diversify the direct-SQL pool so selection
    #    does not hinge on the single temperature-0 candidate: a grain-aware
    #    prompt, and a reworded prompt at a mild temperature. Each sample is
    #    fully isolated in its own try/except — a failed or slow extra sample
    #    falls back to existing behavior and can never break the endpoint.
    try:
        direct_sql_grain = generate_direct_sql_grain(
            body.question, graph, checklist, value_hints)
    except Exception as exc:
        print(f"DIRECT SQL GRAIN ERROR: {exc}", flush=True)
        direct_sql_grain = None
    direct_sql_grain = _norm_sql(direct_sql_grain)
    if direct_sql_grain:
        _v = direct_sql_violations(direct_sql_grain, body.question, checklist, graph)
        if _v:
            print(f"REJECTED direct candidate llm_sql_direct_grain: {_v}", flush=True)
            full_trace.note("layer5", "rejected::llm_sql_direct_grain",
                            {"sql": direct_sql_grain, "violations": _v})
        else:
            candidates.append(build_direct_sql_candidate(
                label="llm_sql_direct_grain", sql=direct_sql_grain,
                db_path=db_path, source="llm_sql_direct_grain"))

    try:
        direct_sql_variant = generate_direct_sql_variant(
            body.question, graph, checklist, value_hints)
    except Exception as exc:
        print(f"DIRECT SQL VARIANT ERROR: {exc}", flush=True)
        direct_sql_variant = None
    direct_sql_variant = _norm_sql(direct_sql_variant)
    if direct_sql_variant:
        _v = direct_sql_violations(direct_sql_variant, body.question, checklist, graph)
        if _v:
            print(f"REJECTED direct candidate llm_sql_direct_variant: {_v}", flush=True)
            full_trace.note("layer5", "rejected::llm_sql_direct_variant",
                            {"sql": direct_sql_variant, "violations": _v})
        else:
            candidates.append(build_direct_sql_candidate(
                label="llm_sql_direct_variant", sql=direct_sql_variant,
                db_path=db_path, source="llm_sql_direct_variant"))

    _log_layer(5, "CHECKING & SCORING - grade candidates, reject bad ones, pick winner")
    # -- Score + select.
    for cand in candidates:
        try:
            score_candidate(body.question, cand, graph, checklist=checklist,
                            value_profile=value_profile,
                            contract=grain_contract)
        except Exception as exc:
            print(f"CANDIDATE SCORER ERROR ({cand.label}): {exc}", flush=True)
            cand.score = 0.0
            cand.reasons = [f"scorer error: {exc}"]

    # -- Option A: execution-guided sanity probes (advisory). Read-only,
    #    small-timeout checks run AFTER scoring and BEFORE selection: a
    #    contradiction probe (zero-row query whose relaxed form returns
    #    rows) and a join-fanout probe (COUNT(*)/SUM over 2+ joins). Each
    #    only adds a warning + small score penalty to executed candidates
    #    (never fatal, never rejects an empty result on its own). A probe
    #    failure/timeout is ignored and normal behavior is preserved. The
    #    warnings land in candidate.reasons, so the repair prompt gets them.
    for cand in candidates:
        annotate_with_probes(cand, db_path)

    # -- Explicit-table enforcement across ALL candidate sources (not just
    #    the direct ones): when the question NAMES schema tables, any
    #    candidate whose SQL omits a required table or joins ZIP directly to
    #    a tract/geo id is REJECTED before selection, so an uncovered path
    #    (IR / query_family / primary) cannot smuggle in a bad join. If every
    #    candidate violates, none is kept and the endpoint reports no valid
    #    SQL rather than returning a wrong answer. Temporary [ENFORCE] debug.
    try:
        _named_dbg = required_tables_for(
            body.question, checklist, se_index_schema(graph))
    except Exception:
        _named_dbg = set()
    if _named_dbg:
        _kept = []
        for cand in candidates:
            _v = direct_sql_violations(cand.sql, body.question, checklist, graph)
            _first = ((cand.sql or "").strip().splitlines() or ["(no sql)"])[0]
            print(f"[ENFORCE] {cand.source}/{cand.label} required={sorted(_named_dbg)} "
                  f"sql0={_first!r} violations={_v} -> "
                  f"{'REJECT' if _v else 'KEEP'}", flush=True)
            if not _v:
                _kept.append(cand)
        candidates = _kept

    sem_index = se_index_schema(graph)
    selected, selection_meta = select_best(
        candidates, checklist=checklist, contract=grain_contract,
        idx=sem_index, question=body.question)

    # -- One-shot repair ("llm_sql_repair"): when the winner looks unreliable
    #    (fatal / low score / missing concepts / zero rows / weak family pick),
    #    ONE extra LLM call corrects the selected SQL using every candidate's
    #    diagnostics. The repaired SQL is scored like any candidate and
    #    selection re-runs once. Exactly one round — never a loop.
    repair_meta = {
        "repair_attempted": False,
        "repair_triggers": [],
        "repair_executed": False,
        "repair_score": None,
        "repair_selected": False,
        "selected_source_before_repair": selected.source if selected else None,
    }
    try:
        do_repair, repair_triggers = should_repair(selected, candidates, checklist)
    except Exception as exc:
        print(f"REPAIR TRIGGER ERROR: {exc}", flush=True)
        do_repair, repair_triggers = False, []
    if do_repair:
        repair_meta["repair_attempted"] = True
        repair_meta["repair_triggers"] = repair_triggers
        repair_sql = generate_repair_sql(
            body.question, graph, value_hints, checklist, selected, candidates,
            contract=grain_contract)
        repair_sql = _norm_sql(repair_sql)
        if repair_sql and direct_sql_violations(
                repair_sql, body.question, checklist, graph):
            print("REJECTED repair candidate: "
                  f"{direct_sql_violations(repair_sql, body.question, checklist, graph)}",
                  flush=True)
            repair_sql = None
        if repair_sql:
            repair_cand = build_direct_sql_candidate(
                label="llm_sql_repair", sql=repair_sql, db_path=db_path,
                source="llm_sql_repair")
            try:
                score_candidate(body.question, repair_cand, graph,
                                checklist=checklist, value_profile=value_profile,
                                contract=grain_contract)
            except Exception as exc:
                print(f"REPAIR SCORER ERROR: {exc}", flush=True)
                repair_cand.score = 0.0
                repair_cand.reasons = [f"scorer error: {exc}"]
            candidates.append(repair_cand)
            annotate_with_probes(repair_cand, db_path)
            repair_meta["repair_executed"] = repair_cand.executed_ok
            repair_meta["repair_score"] = repair_cand.score
            selected, selection_meta = select_best(
                candidates, checklist=checklist, contract=grain_contract,
                idx=sem_index, question=body.question)
            repair_meta["repair_selected"] = selected is repair_cand

    _trace_enforce_rejected = False        # diagnostics only (full trace)
    # -- FINAL enforcement (post-repair): nothing may bypass the explicit
    #    table-lock / bridge rules — not repair, not any post-selection path.
    #    If the final SQL violates, drop it and fall back to the best
    #    non-violating candidate; if none exists, return NO SQL rather than
    #    the bad one.
    if selected is not None:
        _fv = direct_sql_violations(selected.sql, body.question, checklist, graph)
        _req = required_tables_for(
            body.question, checklist, se_index_schema(graph))
        _first = ((selected.sql or "").strip().splitlines() or ["(no sql)"])[0]
        print(f"[FINAL ENFORCE] required={sorted(_req)} violations={_fv} "
              f"sql0={_first!r} -> {'REJECT' if _fv else 'KEEP'}", flush=True)
        if _fv:
            _ok = [c for c in candidates if c.sql and not
                   direct_sql_violations(c.sql, body.question, checklist, graph)]
            if _ok:
                selected, selection_meta = select_best(
                    _ok, checklist=checklist, contract=grain_contract,
                    idx=sem_index, question=body.question)
                print(f"[FINAL ENFORCE] replaced with non-violating candidate: "
                      f"{selected.label if selected else None}", flush=True)
            else:
                selected = None
                print("[FINAL ENFORCE] no non-violating candidate; returning "
                      "NO SQL", flush=True)
                _trace_enforce_rejected = True

    # HARD SELECTION INVARIANT (final stabilization): a candidate with ANY
    # fatal reason can never be returned as a normal success — regardless of
    # score, consensus, repair, or low-confidence fallback. The old gate only
    # fired when *every* candidate (including non-executed ones) was fatal,
    # which let an all-executed-fatal consensus slip through as ACCEPTED.
    def _cand_fatal(c):
        return bool((c.validation or {}).get("fatal"))

    _rejected_debug_sql = (selected.sql if selected is not None
                           and _cand_fatal(selected) else None)
    selected, _controlled_failure, _fatal_reasons = enforce_selection_safety(
        selected, candidates)
    if _controlled_failure:
        print("[SEMANTIC FAILURE] selected candidate is fatal and no clean "
              "executed candidate exists; returning controlled "
              "no-valid-SQL failure instead of misleading SQL", flush=True)
        _resp = {
            "success": False,
            "error": "no_semantically_valid_sql",
            "database_id": database_id,
            "question": body.question,
            "tables_considered": tables_considered,
            "message": ("No semantically valid SQL could be generated for this "
                        "question — every executed candidate violated a "
                        "required relationship, measure, or query shape."),
            "semantic_checklist": checklist,
            "semantic_contract": contract_to_dict(grain_contract),
            "candidate_fatal_reasons": {
                c.label: (c.validation or {}).get("fatal") or []
                for c in candidates},
            # diagnostic ONLY — never presented as accepted generated SQL
            "debug_rejected_sql": _rejected_debug_sql,
            "debug_rejected_fatal_reasons": _fatal_reasons,
            **selection_meta,
        }
        full_trace.finish(
            response=_resp, graph=graph, checklist=checklist,
            contract_dict=contract_to_dict(grain_contract),
            candidates=candidates, selected=None,
            selection_meta=selection_meta, repair_meta=repair_meta,
            tables_considered=tables_considered, controlled=True,
            enforcement_rejected=_trace_enforce_rejected)
        return _resp

    # Value-grounding warning: the WINNER compares a profiled column against a
    # literal that was never seen in that column's sampled values.
    if selected is not None:
        for v in (selected.validation or {}).get("unseen_literals") or []:
            selection_meta["warnings"].append(
                f"selected SQL uses literal '{v['literal']}' not found in "
                f"sampled values of '{v['column']}' (known: {v['known_values']})")
        for w in ((selected.validation or {}).get("probes") or {}).get(
                "warnings") or []:
            selection_meta["warnings"].append(f"selected SQL: {w}")

    # -- Response: same contract as before, filled from the SELECTED candidate,
    #    plus candidate-selection metadata.
    _log_layer(6, "RESULT - winner selected; run it and return the answer")
    if selected is None:  # defensive; primary always exists
        _resp = {
            "success": False,
            "database_id": database_id,
            "question": body.question,
            "tables_considered": tables_considered,
            "message": "No SQL candidates could be generated.",
            **selection_meta,
        }
        full_trace.finish(
            response=_resp, graph=graph, checklist=checklist,
            contract_dict=contract_to_dict(grain_contract),
            candidates=candidates, selected=None,
            selection_meta=selection_meta, repair_meta=repair_meta,
            tables_considered=tables_considered, controlled=False,
            enforcement_rejected=_trace_enforce_rejected)
        return _resp

    base = {
        "database_id": database_id,
        "question": body.question,
        "extraction": selected.extraction,
        "ir": selected.ir,
        "validation": selected.ir_validation,
        "tables_considered": tables_considered,
        "large_mode_table_fallback": selected.diagnostics.get(
            "large_mode_table_fallback", False),
        "fallback_table": selected.diagnostics.get("fallback_table"),
        "removed_redundant_partition_date_filter": selected.diagnostics.get(
            "removed_redundant_partition_date_filter", False),
        "partition_date": selected.diagnostics.get("partition_date"),
        # legacy field: "query_family" or "llm" (benchmarks group by this)
        "extraction_source": ("query_family"
                              if selected.source == "query_family" else "llm"),
        "query_family": family_name,
        "query_family_confidence": family_confidence,
        "query_family_reason": family_reason,
        "family_guard_valid": family_guard_valid,
        "family_guard_reasons": family_guard_reasons,
        # candidate-selection metadata
        **selection_meta,
        "selected_candidate_score": selected.score,
        "selected_candidate_validation": selected.validation,
        "semantic_checklist": checklist,
        "semantic_contract": contract_to_dict(grain_contract),
        **repair_meta,
        "value_grounding": {
            "profiled_columns": sum(len(c) for c in value_profile.values()),
            "grounded_from_eval_copy": value_grounded_from_eval,
        },
    }

    # Final assertion (Part A): the selected candidate cannot be fatal here.
    # enforce_selection_safety above guarantees it; if this is ever violated
    # by a future code path, convert to a controlled failure instead of
    # returning misleading SQL as a success.
    if _cand_fatal(selected):
        print("[ASSERTION] fatal candidate reached response assembly; "
              "converting to controlled failure", flush=True)
        _resp = {
            "success": False,
            "error": "no_semantically_valid_sql",
            "database_id": database_id,
            "question": body.question,
            "message": "selected candidate failed semantic validation",
            "debug_rejected_sql": selected.sql,
            "debug_rejected_fatal_reasons":
                (selected.validation or {}).get("fatal") or [],
            **selection_meta,
        }
        full_trace.finish(
            response=_resp, graph=graph, checklist=checklist,
            contract_dict=contract_to_dict(grain_contract),
            candidates=candidates, selected=selected,
            selection_meta=selection_meta, repair_meta=repair_meta,
            tables_considered=tables_considered, controlled=True,
            enforcement_rejected=_trace_enforce_rejected)
        return _resp

    _resp = {
        "success": selected.executed_ok and not _cand_fatal(selected),
        **base,
        "plan": selected.plan,
        "generated_sql": selected.generated_sql,
        "relational_algebra": selected.relational_algebra,
        "execution": selected.execution,
    }
    full_trace.finish(
        response=_resp, graph=graph, checklist=checklist,
        contract_dict=contract_to_dict(grain_contract),
        candidates=candidates, selected=selected,
        selection_meta=selection_meta, repair_meta=repair_meta,
        tables_considered=tables_considered, controlled=False,
        enforcement_rejected=_trace_enforce_rejected)
    return _resp


@app.post("/database/{database_id}/execute_sql")
def execute_sql_endpoint(database_id: int, body: IRRequest,
                         request: Request = None):
    """Unchanged public contract. Thin wrapper that delegates to the shared
    run_nl_sql_pipeline helper so /check_containment can reuse the same path.
    When SPIDERSQL_FULL_TRACE is enabled, optional X-SpiderSQL-* headers
    attach benchmark metadata to the diagnostic trace (never logged
    otherwise; authorization headers are never read)."""
    if full_trace.enabled() and request is not None:
        full_trace.set_request_meta(
            full_trace.request_meta_from_headers(request.headers))
    # Ownership enforcement when the frontend threads authenticated context.
    # (Non-interactive tools, e.g. the benchmark runner, omit it and are not
    # ownership-checked — see report; strict mode can require it.)
    if body.user_id is not None:
        ok, reason = verify_database_access(
            body.user_id, body.username, body.conversation_id, database_id)
        if not ok:
            return {"success": False, "error": "access_denied",
                    "message": reason}
    response = run_nl_sql_pipeline(database_id, body.question)
    full_trace.ensure_finished(response)
    return response


@app.post("/database/{database_id}/check_containment")
def check_containment_endpoint(database_id: int, body: ContainmentRequest):
    """Step 1 of NL query containment: generate + validate SQL for two natural
    language questions using the SAME pipeline as /execute_sql, then return both
    SQLs plus a non-committal verdict ('not_checked_yet' / 'unknown'). The
    actual containment check (EXCEPT / symbolic) is added in a later step."""
    if not get_database_meta(database_id):
        return {"success": False, "message": "Database not found"}
    return check_containment(database_id, body, run_nl_sql_pipeline)


@app.post("/database/{database_id}/check_containment_batch")
def check_containment_batch_endpoint(database_id: int, body: ContainmentBatchRequest):
    """Batch NL query containment: generate + validate SQL for N natural-language
    questions, then compare every safe pair in both directions on the current
    database. Returns pairwise relationships + per-query rollups. Not a symbolic
    proof; reuses the same run_nl_sql_pipeline as /execute_sql."""
    if not get_database_meta(database_id):
        return {"success": False, "message": "Database not found"}
    return check_containment_batch(database_id, body, run_nl_sql_pipeline)


@app.get("/queries/{user_id}")
def user_queries(user_id: int):
    return {"success": True, "queries": get_user_queries(user_id)}


# ---------------------------------------------------------------------------
# Core query endpoint
# ---------------------------------------------------------------------------

@app.post("/query")
def query_database(request: QueryRequest):
    print(f"USER ID: {request.user_id}  QUESTION: {request.question!r}", flush=True)

    working_question = request.question   # may be rewritten during clarification
    skip_clarifier   = False
    dataset          = None
    inferred_schema  = None
    schema_info      = None

    # ------------------------------------------------------------------
    # 1. Handle any pending conversation state
    # ------------------------------------------------------------------
    if request.user_id:
        state = get_chat_state(request.user_id)
        print(f"CHAT STATE: {state}", flush=True)

        if state:
            followup = understand_followup(
                request.question,
                state["pending_action"],
                state["last_question"],
            )
            print(f"FOLLOWUP: {followup}", flush=True)
            intent = followup.get("intent")

            # --- User confirmed: generate schema from their original question ---
            if intent == "confirm_generate_schema":
                schema_info = infer_schema_with_ai(state["last_question"])
                generated_schema = schema_info["schema"]

                dataset_result = save_schema_dataset(
                    request.user_id,
                    "AI Generated Schema",
                    generated_schema,
                    request.conversation_id
                )

                clear_chat_state(request.user_id)

                message = "Schema generated from your question. You can now ask your query."

                if request.conversation_id:
                    save_query(
                        request.user_id,
                        request.conversation_id,
                        dataset_result.get("dataset_id"),
                        request.question,
                        state["last_question"],
                        "SCHEMA_GENERATED",
                        json.dumps({
                            "message": message,
                            "schema": generated_schema
                        })
                    )

                    update_conversation_title(
                        request.conversation_id,
                        state["last_question"]
                    )

                return {
                    "type": "generated_schema",
                    "message": message,
                    "schema": generated_schema,
                    "dataset": dataset_result,
                }

            # --- User provided a schema string manually ---
            if intent == "provide_schema":
                provided = followup.get("schema_text", "").strip()
                if not provided:
                    return {
                        "type":    "clarification",
                        "question": "I couldn't read the schema you provided. Please use the format: table(col1, col2, ...)",
                    }
                dataset_result = save_schema_dataset(
                    request.user_id, "User Provided Schema", provided
                )
                clear_chat_state(request.user_id)
                return {
                    "type":    "schema_saved",
                    "message": "Schema saved. Please ask your query again.",
                    "schema":  provided,
                    "dataset": dataset_result,
                }

            # --- User declined schema generation ---
            if intent == "deny_generate_schema":
                clear_chat_state(request.user_id)
                return {
                    "type":    "dataset_required",
                    "message": "No problem. Please upload a dataset or paste a schema string, then ask your query.",
                }

            # --- User answered a clarification question ---
            if intent == "answer_clarification":
                clarification = followup.get("clarification", "").strip()
                # If they just repeated the same question, clear state and continue
                if not clarification or clarification.lower() == state["last_question"].strip().lower():
                    clear_chat_state(request.user_id)
                else:
                    # Merge the clarification into the original question
                    working_question = f"{state['last_question']} {clarification}"
                    clear_chat_state(request.user_id)
                    skip_clarifier = True

            # --- Unrelated / new query: fall through to normal processing ---
            # (intent == "new_query" or anything unexpected)

    # ------------------------------------------------------------------
    # 2. Resolve schema
    # ------------------------------------------------------------------
    if request.conversation_id:
        dataset = get_latest_dataset_for_conversation(
            request.conversation_id
        )
        print(f"DATASET: {dataset}", flush=True)

    if dataset:
        inferred_schema = dataset["schema_text"]
        schema_info     = schema_text_to_schema_info(inferred_schema)
        if schema_info is None:
            # dataset schema is malformed — try AI inference as recovery
            print("SCHEMA PARSE FAILED for saved dataset, falling back to AI inference.", flush=True)
            schema_info     = infer_schema_with_ai(working_question)
            inferred_schema = schema_info["schema"]

    elif request.schema_text:
        inferred_schema = request.schema_text
        schema_info     = schema_text_to_schema_info(inferred_schema)
        if schema_info is None:
            return {
                "type":    "schema_error",
                "message": "Could not parse the schema you provided. Use the format: table(col1, col2, ...)",
            }

    # ------------------------------------------------------------------
    # 3. Run clarifier (unless we already merged a clarification)
    # ------------------------------------------------------------------
    if not skip_clarifier:
        clarifier_result = clarify_query(working_question, inferred_schema)
        print(f"CLARIFIER: {clarifier_result}", flush=True)

        clarifier_status = clarifier_result.get("status")

        if clarifier_status == "ready":
            working_question = clarifier_result.get("clean_query") or working_question

        elif clarifier_status == "schema_mismatch":
            # The saved schema belongs to a different domain than this query.
            # Offer to generate a fresh schema rather than running against the wrong table.
            if request.user_id:
                save_chat_state(request.user_id, "confirm_generate_schema", working_question)
            return {
                "type":          "schema_mismatch",
                "question":      clarifier_result.get("question"),
                "last_question": working_question,
            }

        else:
            # need_clarification
            if request.user_id:
                save_chat_state(request.user_id, "clarification_needed", working_question)
            return {
                "type":     "clarification",
                "question": clarifier_result.get("question") or "Could you clarify your query?",
            }

    # ------------------------------------------------------------------
    # 4. If still no schema, ask user or auto-infer
    # ------------------------------------------------------------------
    if not inferred_schema:
        if request.user_id:
            save_chat_state(request.user_id, "confirm_generate_schema", working_question)

            message = "You haven't provided a dataset or schema. Would you like me to generate one for your query?"

            if request.conversation_id:
                save_query(
                    request.user_id,
                    request.conversation_id,
                    None,
                    request.question,
                    working_question,
                    "NO_DATASET",
                    json.dumps({"message": message})
                )

                update_conversation_title(
                    request.conversation_id,
                    request.question
                )

            print("MISSING DATASET BRANCH HIT")

            return {
                "type": "missing_dataset",
                "question": message,
                "last_question": working_question,
            }

        # No user_id — auto-infer without asking
        schema_info     = infer_schema_with_ai(working_question)
        inferred_schema = schema_info["schema"]
        print(f"AUTO SCHEMA INFO: {schema_info}", flush=True)

    if not schema_info:
        schema_info = schema_text_to_schema_info(inferred_schema)

    # ------------------------------------------------------------------
    # 5. Parse → generate → validate → return
    # ------------------------------------------------------------------
    ai_relational = extract_semantics(working_question, inferred_schema)

    print("AI RELATIONAL:", ai_relational, flush=True)

    if ai_relational:
        # AI returned something — validate and normalise it against the schema.
        # This ensures unknown columns are dropped, types are correct, and the
        # semantic object shape is guaranteed before it reaches the SQL generator.
        semantic = ir_to_semantic(ai_relational, schema_info)
    else:
        # AI returned nothing — use the structural fallback.
        # The fallback only does schema-driven work (no linguistic guessing).
        semantic = parse_natural_language(working_question, schema_info)

    print(f"SEMANTIC: {semantic}", flush=True)

    if semantic.get("query_type") == "inverse_design":
        return {
            "type":        "design_query",
            "question":    request.question,
            "clean_query": working_question,
            "semantic":    semantic,
            "message":     "Design query parsed. Hylos generation coming soon.",
        }

    sql = generate_sql_from_semantic(semantic, inferred_schema)

    if not sql or sql.strip().upper().startswith("ERROR"):
        return {
            "type": "sql_generation_error",
            "sql": sql,
            "error": "SQL generator could not create valid SQL from the semantic object.",
            "semantic": semantic,
        }

    if not validate_query(sql):
        return {
            "type":  "blocked",
            "sql":   sql,
            "error": "The generated SQL was blocked by the safety validator.",
        }

    results = "No dataset execution available."

    if dataset and dataset.get("file_path"):
        load_result = load_csv_to_sqlite(dataset["file_path"])

        if not load_result.get("success"):
            return {
                "type": "execution_error",
                "sql": sql,
                "error": load_result.get("message"),
            }

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(sql)
        rows = cursor.fetchall()

        column_names = [description[0] for description in cursor.description]

        conn.close()

        results = [
            dict(zip(column_names, row))
            for row in rows
        ]

    if request.user_id:
        dataset_id = dataset["dataset_id"] if dataset else None

        save_query(
            request.user_id,
            request.conversation_id,
            dataset_id,
            request.question,
            working_question,
            sql,
            json.dumps(results)
        )

        if request.conversation_id:
            update_conversation_title(
                request.conversation_id,
                request.question
            )

    return {
        "type":        "success",
        "question":    request.question,
        "clean_query": working_question,
        "semantic":    semantic,
        "sql":         sql,
        "results":     results,
    }

@app.post("/conversation/create")
def create_new_conversation(user_id: int):
    conversation_id = create_conversation(user_id)
    return {
        "success": True,
        "conversation_id": conversation_id
    }


@app.get("/conversations/{user_id}")
def get_conversations(user_id: int):
    return {
        "success": True,
        "conversations": get_user_conversations(user_id)
    }


@app.delete("/conversation/{conversation_id}")
def remove_conversation(conversation_id: int):
    delete_conversation(conversation_id)

    return {
        "success": True
    }

@app.get("/conversation/{conversation_id}/messages")
def get_conversation_messages(conversation_id: int):
    return {
        "success": True,
        "messages": get_queries_for_conversation(conversation_id)
    }


class SaveMessagesRequest(BaseModel):
    user_id: int
    items: list[dict] = []
    title: str | None = None


@app.post("/conversation/{conversation_id}/messages")
def save_conversation_messages(conversation_id: int, body: SaveMessagesRequest):
    """Persist chat-format exchanges (database-aware queries, assignment output,
    no-database notes). Each item is {question, output}; the assistant output is
    stored as JSON in the `results` column so it round-trips verbatim. The title
    is set only on the first message of the conversation (matching old behavior)."""
    existing = get_queries_for_conversation(conversation_id)
    for item in body.items:
        save_query(
            body.user_id,
            conversation_id,
            None,
            item.get("question", ""),
            None,
            None,
            json.dumps({"output": item.get("output"), "result": item.get("result")}),
        )
    if not existing and body.title:
        update_conversation_title(conversation_id, body.title)
    return {"success": True}

@app.delete("/user/{user_id}/factory-reset")
def factory_reset(user_id: int):
    return factory_reset_user(user_id)
# (multi-candidate SQL selection wired into /database/{id}/execute_sql)
