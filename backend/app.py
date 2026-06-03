from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from sql_generator import generate_sql
from query_executor import execute_query
from validator import validate_query

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
    sql = generate_sql(request.question, request.schema)
    if not validate_query(sql):
        return {
            "question": request.question,
            "sql": sql,
            "error": "Unsafe SQL query blocked"
        }
    
    results = execute_query(sql)

    return{
        "question": request.question,
        "sql": sql,
        "results": results
    }