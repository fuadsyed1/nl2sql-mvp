import re
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from ai_semantic_extractor import extract_semantics
from ir_converter import ir_to_semantic
from sql_generator import generate_sql_from_semantic
from semantic_parser import (
    parse_natural_language,
    create_semantic_object,
    validate_and_normalise,
)
from validator import validate_query
from llm_clarifier import clarify_query
from ai_schema_inferencer import infer_schema_with_ai
from auth_db import init_auth_db, get_connection
from auth_service import create_user, login_user
from dataset_service import (
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
from conversation_manager import understand_followup
from fastapi import UploadFile, File, Form
import os
import shutil
from csv_schema_detector import detect_csv_schema
from csv_to_sqlite_loader import load_csv_to_sqlite, clean_table_name
from conversation_service import (
    create_conversation,
    get_user_conversations,
    delete_conversation,
    update_conversation_title,
    factory_reset_user,
)
from schema_extractor import extract_table_columns
from relationship_detector import detect_relationships
from database_service import (
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
)
from ai_semantic_extractor import extract_semantics, extract_multitable_ir_extraction
from ir_builder import build_from_extraction
from ir_validator import validate_ir
from semantic_ir import to_dict as ir_to_dict
from plan_resolver import resolve_plan
from query_plan import to_dict as plan_to_dict

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI()
init_auth_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173"
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

    created_tables = []
    used_names = set()

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
            created_tables.append({
                "source_filename": file.filename,
                "table_name": table_name,
                "success": False,
                "message": load_result.get("message"),
            })
            continue

        schema_text = detect_csv_schema(file_path, table_name=table_name)
        rows_inserted = load_result.get("rows_inserted", 0)

        table_id = add_database_table(
            database_id,
            table_name,
            file.filename,
            file_path,
            schema_text,
            rows_inserted,
        )

        columns_meta = extract_table_columns(db_path, table_name)
        add_table_columns(table_id, columns_meta)

        created_tables.append({
            "source_filename": file.filename,
            "table_name": table_name,
            "rows_inserted": rows_inserted,
            "schema_text": schema_text,
            "columns": columns_meta,
            "success": True,
        })

    clear_relationships(database_id)
    relationships = detect_relationships(database_id)
    add_relationships(database_id, relationships)

    return {
        "success": True,
        "database_id": database_id,
        "name": db_name,
        "db_path": db_path,
        "tables": created_tables,
        "relationships": relationships,
    }

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


@app.get("/database/{database_id}/relationships")
def database_relationships(database_id: int):
    return {"success": True, "relationships": get_relationships(database_id)}


@app.post("/database/{database_id}/detect-relationships")
def redetect_relationships(database_id: int):
    if not get_database(database_id):
        return {"success": False, "message": "Database not found"}
    clear_relationships(database_id)
    relationships = detect_relationships(database_id)
    add_relationships(database_id, relationships)
    return {"success": True, "relationships": relationships}


@app.get("/database/{database_id}/graph")
def database_graph(database_id: int):
    graph = get_database_graph(database_id)
    if not graph:
        return {"success": False, "message": "Database not found"}
    return {"success": True, "database": graph}

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
    graph = get_database_graph(database_id)
    if not graph:
        return {"success": False, "message": "Database not found"}

    extraction = extract_multitable_ir_extraction(body.question, graph)
    ir = build_from_extraction(database_id, extraction, graph)
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
    graph = get_database_graph(database_id)

    if not graph:
        return {
            "success": False,
            "message": "Database not found"
        }

    extraction = extract_multitable_ir_extraction(
        body.question,
        graph
    )

    ir = build_from_extraction(
        database_id,
        extraction,
        graph
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

@app.delete("/user/{user_id}/factory-reset")
def factory_reset(user_id: int):
    return factory_reset_user(user_id)