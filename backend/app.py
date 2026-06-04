from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from sql_generator import generate_sql
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

    sql = generate_sql(clean_query, request.schema)

    if not validate_query(sql):
        return {
            "question": request.question,
            "sql": sql,
            "error": "Unsafe SQL query blocked"
        }
    
    results = execute_query(sql)

    return{
        "question": request.question,
        "clean_query": clean_query,
        "sql": sql,
        "results": results
    }