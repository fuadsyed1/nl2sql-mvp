import { useState, useEffect } from "react";
import Sidebar from "./components/Sidebar";
import Dashboard from "./components/Dashboard";
import AccountSettings from "./components/AccountSettings";
import ConversionPage from "./components/ConversionPage";
import AuthPage from "./components/AuthPage";

function App() {
  const [activePage, setActivePage] = useState("dashboard");
  const [target, setTarget] = useState("SQL");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [conversions, setConversions] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const [user, setUser] = useState(() => {
    const user_id = localStorage.getItem("user_id");
    const username = localStorage.getItem("username");

    if (user_id && username) {
      return { user_id, username };
    }

    return null;
  });

  const formatBackendOutput = (data) => {
    if (data.type === "clarification") {
      return `❓ Clarification Needed\n\n${data.question}`;
    }

    if (data.type === "schema_mismatch") {
      return `⚠️ Schema Mismatch\n\n${data.question}`;
    }

    if (data.type === "missing_dataset") {
      return `📂 No Dataset Found\n\n${data.question}`;
    }

    if (data.type === "generated_schema") {
      return `✅ Schema Generated\n\n${data.schema}\n\n${data.message}`;
    }

    if (data.type === "schema_saved") {
      return `✅ Schema Saved\n\n${data.schema}\n\n${data.message}`;
    }

    if (data.type === "dataset_required") {
      return `📂 Dataset Required\n\n${data.message}`;
    }

    if (data.type === "schema_error") {
      return `❌ Schema Error\n\n${data.message}`;
    }

    if (data.type === "blocked") {
      return `🚫 Blocked\n\n${data.error}\n\nSQL attempted:\n${data.sql}`;
    }

    if (data.type === "design_query") {
      return `🔬 Design Query\n\n${data.message}`;
    }

    if (data.type === "success") {
      return (
        `SQL\n${"─".repeat(40)}\n${data.sql}\n\n` +
        `Clean Query\n${"─".repeat(40)}\n${data.clean_query}\n\n` +
        `Results\n${"─".repeat(40)}\n${JSON.stringify(
          data.results || [],
          null,
          2
        )}`
      );
    }

    if (data.error) {
      return `❌ Error\n\n${data.error}\n\nSQL:\n${
        data.sql || "No SQL generated"
      }`;
    }

    return JSON.stringify(data, null, 2);
  };

  const loadConversations = async () => {
    if (!user) return;

    try {
      const response = await fetch(
        `http://localhost:8000/conversations/${user.user_id}`
      );

      const data = await response.json();

      if (data.success) {
        setConversions(data.conversations);
      }
    } catch (err) {
      console.error("Failed to load conversations:", err);
    }
  };

  useEffect(() => {
    if (user) {
      loadConversations();
    }
  }, [user]);

  const newConversion = async () => {
    if (!user) return;

    try {
      const response = await fetch(
        `http://localhost:8000/conversation/create?user_id=${user.user_id}`,
        {
          method: "POST",
        }
      );

      const data = await response.json();

      if (!data.success) {
        throw new Error("Could not create conversation");
      }

      setCurrentConversationId(data.conversation_id);
      setMessages([]);
      setInput("");
      setActivePage("conversion");

      await loadConversations();
    } catch (err) {
      console.error("Failed to create conversation:", err);
    }
  };

  const loadConversationMessages = async (conversationId) => {
    try {
      const response = await fetch(
        `http://localhost:8000/conversation/${conversationId}/messages`
      );

      const data = await response.json();

      if (!data.success) {
        throw new Error("Could not load conversation messages");
      }

      const restoredMessages = [];

      data.messages.forEach((msg) => {
        restoredMessages.push({
          type: "user",
          text: msg.question,
        });

        restoredMessages.push({
          type: "system",
          output:
            `SQL\n${"─".repeat(40)}\n${msg.sql || ""}\n\n` +
            `Clean Query\n${"─".repeat(40)}\n${msg.clean_query || ""}\n\n` +
            `Results\n${"─".repeat(40)}\n${
              msg.results
                ? JSON.stringify(JSON.parse(msg.results), null, 2)
                : "No results saved"
            }`,
        });
      });

      setCurrentConversationId(conversationId);
      setMessages(restoredMessages);
      setInput("");
      setActivePage("conversion");
    } catch (err) {
      console.error("Failed to load conversation:", err);
    }
  };

  const handleSubmit = async () => {
    if (!input.trim()) return;

    let conversationId = currentConversationId;

    if (!conversationId) {
      try {
        const response = await fetch(
          `http://localhost:8000/conversation/create?user_id=${user.user_id}`,
          {
            method: "POST",
          }
        );

        const data = await response.json();

        if (!data.success) {
          throw new Error("Could not create conversation");
        }

        conversationId = data.conversation_id;

        setCurrentConversationId(conversationId);

        setConversions((prev) => [
          {
            conversation_id: conversationId,
            title: userInput,
          },
          ...prev,
        ]);

        await loadConversations();
      } catch (err) {
        console.error("Failed to auto-create conversation:", err);
        return;
      }
    }

    const userInput = input.trim();

    setConversions((prev) =>
      prev.map((chat) =>
        chat.conversation_id === conversationId
          ? {
              ...chat,
              title: userInput,
            }
          : chat
      )
    );

    const userMessage = {
      type: "user",
      text: userInput,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsProcessing(true);

    try {
      const response = await fetch("http://localhost:8000/query", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          user_id: Number(user.user_id),
          conversation_id: conversationId,
          question: userInput,
        }),
      });

      if (!response.ok) {
        throw new Error(`Backend error: ${response.status}`);
      }

      const data = await response.json();
      console.log("BACKEND RESPONSE:", data);

      const systemMessage = {
        type: "system",
        output: formatBackendOutput(data),
      };

      setMessages((prev) => [...prev, systemMessage]);

      await loadConversations();
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

  if (!user) {
    return <AuthPage setUser={setUser} />;
  }

  return (
    <div className="min-h-screen bg-gray-100 flex">
      <Sidebar
        target={target}
        conversions={conversions}
        setActivePage={setActivePage}
        newConversion={newConversion}
        loadConversationMessages={loadConversationMessages}
        user={user}
        setUser={setUser}
      />

      <main className="flex-1 flex flex-col">
        {activePage === "dashboard" && (
          <Dashboard newConversion={newConversion} />
        )}

        {activePage === "account" && (
          <AccountSettings
            target={target}
            setTarget={setTarget}
            user={user}
            onFactoryReset={() => {
              setConversions([]);
              setMessages([]);
              setCurrentConversationId(null);
              setActivePage("dashboard");
            }}
          />
        )}

        {activePage === "conversion" && (
        <ConversionPage
          target={target}
          messages={messages}
          isProcessing={isProcessing}
          input={input}
          setInput={setInput}
          handleSubmit={handleSubmit}
          currentConversationId={currentConversationId}
        />
        )}
      </main>
    </div>
  );
}

export default App;