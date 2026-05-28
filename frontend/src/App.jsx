import {useState } from "react"

export default function App(){
  const [prompt, setPrompt] = useState("");
  const [sql, setSql] = useState("");
  const [loading, setLoading] = useState(false);

  async function generateSql() {
    if (!prompt.trim()) {
      setSql("");
      return;
    }
    try {
      setLoading(true);

      const response = await fetch("http://127.0.0.1:8000/generate-sql", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          prompt: prompt,
        }),
      });
      
      const data = await response.json();
      setSql(data.sql);
    } catch (error){
      setSql("-- Failed to connect to backend");
    }finally {
      setLoading(false);
    }
  }
  return (
    <div className=" min-h-screen bg-slate-100 p-8">
      <div className="max-w-5xl mx-auto">
        <h1 className="text-4xl font-bold text-center mb-8">
          Natural Language to SQL Converter
        </h1>

        <div className="bg-white rounded-xl shadow p-6">
          <label className="block text-lg font-medium mb-2">
            Enter your request
          </label>

          <div className="flex flex-col gap-4">
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey){
                  e.preventDefault();
                  generateSql();
                }
              }}
              className="w-full border rounded-lg p-3 h-40 resize-none"
              placeholder="Example: Show all students with GPA above 3.5"
            />
            <div className="flex gap-3">
              <button
                onClick={generateSql}
                disabled={loading}
                className={`min-w-[160px] px-6 py-3 text-white rounded-lg ${
                  loading
                    ? "bg-gray-400 cursor-not-allowed"
                    : "bg-blue-600 hover:bg-blue-700"
                }`}
              >
                {loading ? "Generating..." : "Generate SQL"}
              </button>

              <button
                onClick={() => {
                  setPrompt("");
                  setSql("");
                }}
                className="px-6 py-3 bg-gray-200 text-gray-800 rounded-lg w-fit hover:bg-gray-300"
              >
                Clear
              </button>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl shadow p-6 mt-8">
          <h2 className="text-2xl font-semibold mb-3">
            Generated SQL 
          </h2>

          <div className="bg-gray-100 p-4 rounded min-h-[60px]">
            {sql ? (
              <pre className="text-green-600 font-mono whitespace-pre-wrap">
                {sql}
              </pre>
            ) : (
              <p className="text-gray-400 select-none">
                SQL will appear here after you click Generate SQL
              </p>
            )}
          </div>   
        </div>
      </div>
    </div>
  )
}