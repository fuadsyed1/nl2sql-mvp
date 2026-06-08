from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from sql_generator import generate_sql_from_semantic
from semantic_parser import parse_natural_language
from query_executor import execute_query
from validator import validate_query
from llm_clarifier import clarify_query
from schema_inferencer import infer_schema
from auth_db import init_auth_db
from auth_service import create_user, login_user
from dataset_service import save_schema_dataset, get_latest_dataset, save_query, get_user_queries

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
    schema: str | None = None
    question: str

class AuthRequest(BaseModel):
    username: str
    password: str

class SchemaDatasetRequest(BaseModel):
    user_id: int
    name: str
    schema_text: str

@app.get("/")
def home():
    return {"message": "NL to SQL backend is running"}

@app.post("/dataset/schema")
def add_schema_dataset(request: SchemaDatasetRequest):
    return save_schema_dataset(
        request.user_id,
        request.name,
        request.schema_text
    )

@app.get("/dataset/latest/{user_id}")
def latest_dataset(user_id: int):
    dataset = get_latest_dataset(user_id)

    if not dataset:
        return {
            "success": False,
            "message": "No dataset found"
        }

    return {
        "success": True,
        "dataset": dataset
    }

@app.post("/signup")
def signup(request: AuthRequest):
    return create_user(request.username, request.password)

@app.post("/login")
def login(request: AuthRequest):
    return login_user(request.username, request.password)

@app.get("/queries/{user_id}")
def user_queries(user_id: int):
    return {
        "success": True,
        "queries": get_user_queries(user_id)
    }

@app.post("/query")
def query_database(request: QueryRequest):

    simple_keywords = [
        
        "list",
        "get",
        "count",
        "how many",
        "average",
        "highest",
        "lowest",
        "top",
        "sorted",
        "design",
        "dye",
        "molecule",
        "rdkit",
        "dft",
        "askcos"
    ]

    question_lower = request.question.lower()

    should_skip_clarifier = any(
        word in question_lower
        for word in simple_keywords
    )

    if should_skip_clarifier:
        clean_query = request.question
    else:
        clarifier_result = clarify_query(request.question)

        if clarifier_result.get("status") != "ready":
            return {
                "type": "clarification",
                "question": clarifier_result.get(
                    "question",
                    "Please Clarify your request."
                ),
                "debug": clarifier_result
            }

        clean_query = clarifier_result.get("clean_query", request.question)

    dataset = None

    if request.user_id:
        dataset = get_latest_dataset(request.user_id)

    if dataset:
        inferred_schema = dataset["schema_text"]
        schema_info = infer_schema(request.question)

        schema_info["schema"] = inferred_schema
        schema_info["table"] = inferred_schema.split("(", 1)[0].strip()
        schema_info["columns"] = (
            inferred_schema
            .split("(", 1)[1]
            .split(")", 1)[0]
            .replace("{", "")
            .replace("}", "")
            .split(",")
        )

        schema_info["columns"] = [
            col.strip().lower()
            for col in schema_info["columns"]
        ]

    else:
        schema_info = infer_schema(request.question)
        inferred_schema = schema_info["schema"]

    print("SCHEMA INFO:", schema_info)

    print("INFERRED SCHEMA:", inferred_schema)

    semantic = parse_natural_language(request.question, schema_info)

    print("\nSEMANTIC OBJECT:")
    print(semantic)

    if semantic.get("query_type") == "inverse_design":
        return {
            "question": request.question,
            "clean_query": clean_query,
            "semantic": semantic,
            "message": "Design/Hylos query parsed successfully. SQL generation is not supported for this query yet."
        }

    sql = generate_sql_from_semantic(
        semantic,
        inferred_schema
    )

    if not validate_query(sql):
        return {
            "question": request.question,
            "sql": sql,
            "error": "Unsafe SQL query blocked"
        }

    # results = execute_query(sql)

    dataset_id = None

    if dataset:
        dataset_id = dataset["dataset_id"]

    if request.user_id:
        save_query(
            request.user_id,
            dataset_id,
            request.question,
            clean_query,
            sql
        )

    return {
        "question": request.question,
        "clean_query": clean_query,
        "semantic": semantic,
        "sql": sql,
        "results": "Database execution skipped. SQL preview only." 
    }