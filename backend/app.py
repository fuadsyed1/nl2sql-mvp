from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from sql_generator import generate_sql_from_semantic
from semantic_parser import parse_natural_language
from validator import validate_query
from llm_clarifier import clarify_query
from ai_schema_inferencer import infer_schema_with_ai
from auth_db import init_auth_db
from auth_service import create_user, login_user
from dataset_service import (
    save_schema_dataset,
    get_latest_dataset,
    save_query,
    get_user_queries,
    save_chat_state,
    get_chat_state,
    clear_chat_state,
)
from conversation_manager import understand_followup


app = FastAPI()
init_auth_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    user_id: int | None = None
    schema_text: str | None = None
    question: str


class AuthRequest(BaseModel):
    username: str
    password: str


class SchemaDatasetRequest(BaseModel):
    user_id: int
    name: str
    schema_text: str


def schema_text_to_schema_info(schema_text: str):
    table = schema_text.split("(", 1)[0].strip()

    columns_text = (
        schema_text
        .split("(", 1)[1]
        .split(")", 1)[0]
    )

    columns = [
        col.strip().lower()
        for col in columns_text.split(",")
        if col.strip()
    ]

    return {
        "table": table,
        "columns": columns,
        "schema": schema_text,
        "aggregation": None,
        "group_by": None,
        "sort": None,
        "limit": None,
    }


@app.get("/")
def home():
    return {"message": "NL to SQL/Hylos backend is running"}


@app.post("/signup")
def signup(request: AuthRequest):
    return create_user(request.username, request.password)


@app.post("/login")
def login(request: AuthRequest):
    return login_user(request.username, request.password)


@app.post("/dataset/schema")
def add_schema_dataset(request: SchemaDatasetRequest):
    return save_schema_dataset(
        request.user_id,
        request.name,
        request.schema_text,
    )


@app.get("/dataset/latest/{user_id}")
def latest_dataset(user_id: int):
    dataset = get_latest_dataset(user_id)

    if not dataset:
        return {
            "success": False,
            "message": "No dataset found",
        }

    return {
        "success": True,
        "dataset": dataset,
    }


@app.get("/queries/{user_id}")
def user_queries(user_id: int):
    return {
        "success": True,
        "queries": get_user_queries(user_id),
    }


@app.post("/query")
def query_database(request: QueryRequest):
    print("USER ID:", request.user_id, flush=True)
    print("QUESTION:", request.question, flush=True)

    clean_query = request.question
    skip_clarifier = False

    dataset = None
    inferred_schema = None
    schema_info = None

    if request.user_id:
        state = get_chat_state(request.user_id)
        print("CHAT STATE:", state, flush=True)

        if state:
            followup = understand_followup(
                request.question,
                state["pending_action"],
                state["last_question"],
            )

            print("FOLLOWUP:", followup, flush=True)

            if followup["intent"] == "confirm_generate_schema":
                schema_info = infer_schema_with_ai(state["last_question"])
                generated_schema = schema_info["schema"]

                dataset_result = save_schema_dataset(
                    request.user_id,
                    "AI Generated Schema",
                    generated_schema,
                )

                clear_chat_state(request.user_id)

                return {
                    "type": "generated_schema",
                    "message": "I generated a schema based on your previous query.",
                    "schema": generated_schema,
                    "dataset": dataset_result,
                    "note": "No data rows are available because this is schema-only.",
                }

            if followup["intent"] == "provide_schema":
                dataset_result = save_schema_dataset(
                    request.user_id,
                    "User Provided Schema",
                    followup["schema_text"],
                )

                clear_chat_state(request.user_id)

                return {
                    "type": "schema_saved",
                    "message": "I saved your schema. Please ask your query again.",
                    "schema": followup["schema_text"],
                    "dataset": dataset_result,
                }

            if followup["intent"] == "deny_generate_schema":
                clear_chat_state(request.user_id)

                return {
                    "type": "dataset_required",
                    "message": "Please upload a dataset or provide a schema before asking the query.",
                }

            if followup["intent"] == "answer_clarification":

                if (
                    request.question.strip().lower()
                    == state["last_question"].strip().lower()
                ):
                    clear_chat_state(request.user_id)

                else:
                    combined_question = (
                        state["last_question"]
                        + " "
                        + followup["clarification"]
                    )

                    clear_chat_state(request.user_id)

                    request.question = combined_question
                    clean_query = combined_question
                    skip_clarifier = True

    if request.user_id:
        dataset = get_latest_dataset(request.user_id)
        print("DATASET:", dataset, flush=True)

    if dataset:
        inferred_schema = dataset["schema_text"]
        schema_info = schema_text_to_schema_info(inferred_schema)

    elif request.schema_text:
        inferred_schema = request.schema_text
        schema_info = schema_text_to_schema_info(inferred_schema)

    if not skip_clarifier:
        clarifier_result = clarify_query(
            request.question,
            inferred_schema,
        )

        print("CLARIFIER:", clarifier_result, flush=True)

        if clarifier_result.get("status") == "ready":
            clean_query = clarifier_result.get("clean_query", request.question)
        else:
            if request.user_id:
                save_chat_state(
                    request.user_id,
                    "clarification_needed",
                    request.question,
                )

            return {
                "type": "clarification",
                "question": clarifier_result.get("question")
                or "What information should I use to answer this query?",
                "debug": clarifier_result,
            }

    if not inferred_schema:
        if request.user_id:
            save_chat_state(
                request.user_id,
                "confirm_generate_schema",
                request.question,
            )

            return {
                "type": "missing_dataset",
                "question": "You did not submit any dataset. Do you want me to generate a schema for this query?",
                "last_question": request.question,
            }

        schema_info = infer_schema_with_ai(request.question)
        print("SCHEMA INFO:", schema_info, flush=True)

        inferred_schema = schema_info["schema"]

    if not schema_info:
        schema_info = schema_text_to_schema_info(inferred_schema)

    semantic = parse_natural_language(clean_query, schema_info)
    print("SEMANTIC:", semantic, flush=True)

    if semantic.get("query_type") == "inverse_design":
        return {
            "question": request.question,
            "clean_query": clean_query,
            "semantic": semantic,
            "message": "Design/Hylos query parsed successfully. Hylos generation will be added next.",
        }

    sql = generate_sql_from_semantic(
        semantic,
        inferred_schema,
    )

    if not validate_query(sql):
        return {
            "question": request.question,
            "clean_query": clean_query,
            "sql": sql,
            "error": "Unsafe SQL query blocked.",
        }

    dataset_id = dataset["dataset_id"] if dataset else None

    if request.user_id:
        save_query(
            request.user_id,
            dataset_id,
            request.question,
            clean_query,
            sql,
        )

    return {
        "question": request.question,
        "clean_query": clean_query,
        "semantic": semantic,
        "sql": sql,
        "results": "Database execution skipped. SQL preview only.",
    }