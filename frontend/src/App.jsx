import { useState } from "react";

function App() {
  const [activePage, setActivePage] = useState("dashboard");
  const [target, setTarget] = useState("SQL");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [conversions, setConversions] = useState([]);
  const [isProcessing, setIsProcessing] = useState(false);

  const newConversion = () => {
    setMessages([]);
    setInput("");
    setActivePage("conversion");
  };

  const handleSubmit = () => {
    if (!input.trim()) return;

    const userMessage = { type: "user", text: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsProcessing(true);

    if (messages.length === 0) {
      setConversions((prev) => [
        { id: Date.now(), title: input.slice(0, 35) },
        ...prev,
      ]);
    }

    setTimeout(() => {
      const systemMessage = {
        type: "system",
        output:
          target === "SQL"
            ? "SELECT * FROM students WHERE gpa > 3.5;"
            : "Hylos output will be generated here.",
      };

      setMessages((prev) => [...prev, systemMessage]);
      setIsProcessing(false);
    }, 1200);
  };

  return (
    <div className="min-h-screen bg-gray-100 flex">
      <aside className="w-72 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-6">
          <h1 className="text-2xl font-bold text-purple-700">NL Translator</h1>
          <p className="text-sm text-gray-500 mt-1">NL to {target}</p>
        </div>

        <nav className="p-4 space-y-2">
          <button
            onClick={() => setActivePage("dashboard")}
            className="w-full text-left px-4 py-3 rounded-lg hover:bg-purple-50"
          >
            Dashboard
          </button>

          <button
            onClick={newConversion}
            className="w-full text-left px-4 py-3 rounded-lg bg-purple-600 text-white hover:bg-purple-700"
          >
            + New Conversion
          </button>
        </nav>

        <div className="px-4 mt-4 flex-1 overflow-y-auto">
          <h2 className="text-sm font-semibold text-gray-500 mb-3">
            Recent Sessions
          </h2>

          {conversions.length === 0 ? (
            <p className="text-sm text-gray-400 px-4">
              No previous conversions
            </p>
          ) : (
            <div className="space-y-2">
              {conversions.map((item) => (
                <button
                  key={item.id}
                  onClick={() => setActivePage("conversion")}
                  className="w-full text-left px-4 py-2 rounded-lg text-gray-700 hover:bg-gray-100"
                >
                  {item.title}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="p-4">
          <button
            onClick={() => setActivePage("account")}
            className="w-full text-left px-4 py-3 rounded-lg hover:bg-purple-50"
          >
            Account Settings
          </button>
        </div>
      </aside>

      <main className="flex-1 flex flex-col">
        {activePage === "dashboard" && (
          <div className="p-10">
            <h2 className="text-3xl font-bold mb-4">Dashboard</h2>
            <button
              onClick={newConversion}
              className="bg-purple-600 text-white px-6 py-3 rounded-xl"
            >
              Start New Conversion
            </button>
          </div>
        )}

        {activePage === "account" && (
          <div className="p-10">
            <h2 className="text-3xl font-bold mb-6">Account Settings</h2>

            <div className="bg-white rounded-2xl shadow p-6 max-w-2xl space-y-4">
              <div>
                <label className="text-sm text-gray-500">Default Target</label>
                <select
                  className="w-full border rounded-lg px-4 py-3 mt-1"
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                >
                  <option value="SQL">SQL</option>
                  <option value="Hylos">Hylos</option>
                </select>
              </div>
            </div>
          </div>
        )}

        {activePage === "conversion" && (
          <>
            <header className="bg-white px-8 py-5">
              <h2 className="text-2xl font-bold">New Conversion</h2>
              <p className="text-gray-500 text-sm">NL to {target}</p>
            </header>

            <section className="flex-1 overflow-y-auto p-8 space-y-6">
              {messages.length === 0 && !isProcessing && (
                <div className="h-full flex items-center justify-center">
                  <div className="text-center max-w-xl">
                    <h3 className="text-3xl font-bold mb-3">
                      What do you want to translate?
                    </h3>
                    <p className="text-gray-500">
                      Example: show students with GPA above 3.5
                    </p>
                  </div>
                </div>
              )}

              {messages.map((msg, index) => (
                <div key={index}>
                  {msg.type === "user" && (
                    <div className="flex justify-end">
                      <div className="bg-purple-600 text-white px-5 py-3 rounded-2xl max-w-xl">
                        {msg.text}
                      </div>
                    </div>
                  )}

                  {msg.type === "system" && (
                    <div className="bg-white rounded-2xl shadow p-6 max-w-3xl">
                      <h3 className="font-bold text-lg mb-2">Output</h3>
                      <pre className="bg-gray-900 text-green-300 p-4 rounded-xl overflow-x-auto">
                        {msg.output}
                      </pre>
                    </div>
                  )}
                </div>
              ))}

              {isProcessing && (
                <div className="bg-white rounded-2xl shadow p-6 max-w-3xl">
                  <h3 className="font-bold text-lg mb-4">Processing...</h3>
                  <p className="text-gray-600">Reading natural language input...</p>
                  <p className="text-gray-600">Creating semantic meaning...</p>
                  <p className="text-gray-600">Generating {target} output...</p>
                </div>
              )}
            </section>

            <footer className="bg-white p-5">
              <div className="flex gap-3 max-w-4xl mx-auto">
                <input
                  className="flex-1 border border-gray-300 rounded-xl px-5 py-4 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="Type natural language input..."
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleSubmit();
                  }}
                />

                <button
                  onClick={handleSubmit}
                  className="bg-purple-600 text-white px-6 py-4 rounded-xl hover:bg-purple-700"
                >
                  Convert
                </button>
              </div>
            </footer>
          </>
        )}
      </main>
    </div>
  );
}
export default App;