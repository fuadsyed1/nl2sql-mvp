import { useState } from "react";

function App() {

  const [question, setQuestion] = useState("");
  const [response, setResponse] = useState(null);

  const askQuestion = async () => {

    const res = await fetch("http://127.0.0.1:8000/query", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        question: question,
      }),
    });

    const data = await res.json();

    setResponse(data);
  };

  return (
    <div style={{ padding: "40px", fontFamily: "Arial" }}>
      <h1>NL to SQL Converter</h1>

      <input
        type="text"
        placeholder="Ask a question..."
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        style={{
          width: "400px",
          padding: "10px",
          marginRight: "10px",
        }}
      />

      <button onClick={askQuestion}>
        Submit
      </button>

      {response && (
        <div style={{ marginTop: "30px" }}>

          <h3>Generated SQL</h3>
          <pre>{response.sql}</pre>

          <h3>Results</h3>
          <pre>{JSON.stringify(response.results, null, 2)}</pre>

        </div>
      )}
    </div>
  );
}

export default App;