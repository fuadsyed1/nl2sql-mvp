import { useState } from "react";
import Sidebar from "./components/Sidebar";
import Dashboard from "./components/Dashboard";
import AccountSettings from "./components/AccountSettings";
import ConversionPage from "./components/ConversionPage";

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

  const handleSubmit = async () => {
    if (!input.trim()) return;

    const userInput = input.trim();

    const userMessage = {
      type: "user",
      text: userInput,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsProcessing(true);

    if (messages.length === 0) {
      setConversions((prev) => [
        { id: Date.now(), title: userInput.slice(0, 35) },
        ...prev,
      ]);
    }

    try {
      const response = await fetch("http://localhost:8000/query", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          user_id: 1,
          question: userInput,
        }),
      });

      if (!response.ok) {
        throw new Error(`Backend error: ${response.status}`);
      }

      const data = await response.json();
      console.log("BACKEND RESPONSE:", data);

      let outputText = "";


      if (data.type === "clarification") {
        outputText = `❓ Clarification Needed\n\n${data.question}`;
      } else if (data.type === "schema_mismatch") {
        outputText = `⚠️ Schema Mismatch\n\n${data.question}`;
      } else if (data.type === "missing_dataset") {
        outputText = `📂 No Dataset Found\n\n${data.question}`;
      } else if (data.type === "generated_schema") {
        outputText = `✅ Schema Generated\n\n${data.schema}\n\n${data.message}`;
      } else if (data.type === "schema_saved") {
        outputText = `✅ Schema Saved\n\n${data.schema}\n\n${data.message}`;
      } else if (data.type === "dataset_required") {
        outputText = `📂 Dataset Required\n\n${data.message}`;
      } else if (data.type === "schema_error") {
        outputText = `❌ Schema Error\n\n${data.message}`;
      } else if (data.type === "blocked") {
        outputText = `🚫 Blocked\n\n${data.error}\n\nSQL attempted:\n${data.sql}`;
      } else if (data.type === "design_query") {
        outputText = `🔬 Design Query\n\n${data.message}`;
      } else if (data.type === "success") {
        outputText =
          `SQL\n${"─".repeat(40)}\n${data.sql}\n\n` +
          `Clean Query\n${"─".repeat(40)}\n${data.clean_query}\n\n` +
          `Results\n${"─".repeat(40)}\n${JSON.stringify(data.results || [], null, 2)}`;
      } else if (data.error) {
        outputText = `❌ Error\n\n${data.error}\n\nSQL:\n${data.sql || "No SQL generated"}`;
      } else {
        outputText = JSON.stringify(data, null, 2);
      }

      const systemMessage = {
        type: "system",
        output: outputText,
      };

      setMessages((prev) => [...prev, systemMessage]);
    } catch (error) {
      const systemMessage = {
        type: "system",
        output: `Error:\n${error.message}`,
      };

      setMessages((prev) => [...prev, systemMessage]);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 flex">
      <Sidebar
        target={target}
        conversions={conversions}
        setActivePage={setActivePage}
        newConversion={newConversion}
      />

      <main className="flex-1 flex flex-col">
        {activePage === "dashboard" && (
          <Dashboard newConversion={newConversion} />
        )}

        {activePage === "account" && (
          <AccountSettings target={target} setTarget={setTarget} />
        )}

        {activePage === "conversion" && (
          <ConversionPage
            target={target}
            messages={messages}
            isProcessing={isProcessing}
            input={input}
            setInput={setInput}
            handleSubmit={handleSubmit}
          />
        )}
      </main>
    </div>
  );
}

export default App;