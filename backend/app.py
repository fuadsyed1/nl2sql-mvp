from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from sql_generator import generate_sql_from_semantic
from semantic_parser import parse_natural_language
from query_executor import execute_query
from validator import validate_query
from llm_clarifier import clarify_query

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
class QueryRequest(BaseModel):
    schema: str
    question: str

@app.get("/")
def home():
    return {"message": "NL to SQL backend is running"}

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

    semantic = parse_natural_language(clean_query)

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
        request.schema
    )

    if not validate_query(sql):
        return {
            "question": request.question,
            "sql": sql,
            "error": "Unsafe SQL query blocked"
        }

    results = execute_query(sql)

    return {
        "question": request.question,
        "clean_query": clean_query,
        "sql": sql,
        "results": results
    }