import { API_BASE } from "./api";
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
  // Active database for the current chat. The database workspace is the single
  // source of truth: when null, chat queries return a "no database" message and
  // never trigger schema generation from the question.
  const [currentDatabaseId, setCurrentDatabaseId] = useState(null);
  const [activeDatabaseSchemaOnly, setActiveDatabaseSchemaOnly] = useState(false);

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
        `${API_BASE}/conversations/${user.user_id}`
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
        `${API_BASE}/conversation/create?user_id=${user.user_id}`,
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
      setCurrentDatabaseId(null);
      setActiveDatabaseSchemaOnly(false);
      setActivePage("conversion");

      await loadConversations();
    } catch (err) {
      console.error("Failed to create conversation:", err);
    }
  };

  const loadConversationMessages = async (conversationId) => {
    try {
      const response = await fetch(
        `${API_BASE}/conversation/${conversationId}/messages`
      );

      const data = await response.json();

      if (!data.success) {
        throw new Error("Could not load conversation messages");
      }

      const restoredMessages = [];

      data.messages.forEach((msg) => {
        // New chat-format messages store the assistant text as {"output": "..."}.
        let parsed = null;
        try {
          parsed = msg.results ? JSON.parse(msg.results) : null;
        } catch (e) {
          parsed = null;
        }

        // Structured query result -> render as a table card.
        if (parsed && parsed.result) {
          if (msg.question) {
            restoredMessages.push({ type: "user", text: msg.question });
          }
          restoredMessages.push({ type: "system", result: parsed.result });
          return;
        }

        if (parsed && typeof parsed.output === "string" && parsed.output) {
          if (msg.question) {
            restoredMessages.push({ type: "user", text: msg.question });
          }
          restoredMessages.push({ type: "system", output: parsed.output });
          return;
        }

        // Legacy /query format.
        restoredMessages.push({ type: "user", text: msg.question });
        restoredMessages.push({
          type: "system",
          output:
            `SQL\n${"─".repeat(40)}\n${msg.sql || ""}\n\n` +
            `Clean Query\n${"─".repeat(40)}\n${msg.clean_query || ""}\n\n` +
            `Results\n${"─".repeat(40)}\n${
              parsed ? JSON.stringify(parsed, null, 2) : "No results saved"
            }`,
        });
      });

      setCurrentConversationId(conversationId);
      setMessages(restoredMessages);
      setInput("");
      // Chat -> database mapping is not persisted yet, so a reopened chat starts
      // with no active database (see reported limitation).
      setCurrentDatabaseId(null);
      setActiveDatabaseSchemaOnly(false);
      setActivePage("conversion");
    } catch (err) {
      console.error("Failed to load conversation:", err);
    }
  };

  // A database was created/opened (Mode A CSV upload, or Mode B/C assignment)
  // -> make it the active query target for the current chat. Schema-only
  // (assignment) databases are flagged so empty results read clearly.
  const handleDatabaseCreated = (data) => {
    if (data && data.database_id) {
      setCurrentDatabaseId(data.database_id);
      // Mode B/C (schema-only assignment) databases have no rows.
      setActiveDatabaseSchemaOnly(data.mode === "schema_only_assignment");
    }
  };

  // User picked a previous database from the workspace dropdown -> make it the
  // active query target for the current chat.
  const handleSelectDatabase = (databaseId) => {
    // databaseId is null when the user picks "None".
    setCurrentDatabaseId(databaseId || null);
    setActiveDatabaseSchemaOnly(false);
    console.log("ACTIVE DATABASE ->", databaseId || null);
  };

  // Split a "1. ... 2. ..." block into individual questions. Returns [] when
  // there are not at least two numbered items.
  const splitNumberedQuestions = (text) => {
    const lines = (text || "").split("\n");
    const items = [];
    let cur = null;
    const numRe = /^\s*\d+\s*[).\-]\s+(.*\S)\s*$/;
    for (const line of lines) {
      const m = line.match(numRe);
      if (m) {
        if (cur !== null) items.push(cur.trim());
        cur = m[1];
      } else if (cur !== null) {
        const s = line.trim();
        if (s) cur += " " + s;
      }
    }
    if (cur !== null) items.push(cur.trim());
    return items.length >= 2 ? items : [];
  };

  // Ensure a conversation exists; create one if needed. Returns its id or null.
  const ensureConversation = async () => {
    if (currentConversationId) return currentConversationId;
    if (!user) return null;
    try {
      const response = await fetch(
        `${API_BASE}/conversation/create?user_id=${user.user_id}`,
        { method: "POST" }
      );
      const data = await response.json();
      if (!data.success) return null;
      setCurrentConversationId(data.conversation_id);
      return data.conversation_id;
    } catch (err) {
      console.error("Failed to create conversation:", err);
      return null;
    }
  };

  // Persist an exchange to backend history. items: [{question, output}].
  // The title is applied only to the first message of the conversation.
  const persistExchange = async (conversationId, items, title) => {
    if (!conversationId || !user || !items || items.length === 0) return;
    try {
      await fetch(
        `${API_BASE}/conversation/${conversationId}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_id: Number(user.user_id),
            items,
            title: title || (items[0] && items[0].question) || null,
          }),
        }
      );
      await loadConversations();
    } catch (err) {
      console.error("Failed to persist messages:", err);
    }
  };

  // Render a database query result (SQL + executed rows) as chat text.
  const formatDatabaseQueryOutput = (data) => {
    if (!data.success) {
      const reason =
        (data.execution && (data.execution.error || data.execution.reason)) ||
        (data.validation && data.validation.reason) ||
        (data.plan && data.plan.reason) ||
        "Could not generate SQL for this question.";
      const sql = data.generated_sql && data.generated_sql.sql;
      return `Could not run the query.\n${reason}${sql ? `\n\nSQL:\n${sql}` : ""}`;
    }
    const sql = (data.generated_sql && data.generated_sql.sql) || "";
    const cols = (data.execution && data.execution.columns) || [];
    const rows = (data.execution && data.execution.rows) || [];
    const count =
      (data.execution && data.execution.row_count) != null
        ? data.execution.row_count
        : rows.length;
    if (rows.length === 0) {
      const note = activeDatabaseSchemaOnly
        ? "This database contains schema only, so SQL was generated but no rows were executed."
        : "No rows returned.";
      return `SQL:\n${sql}\n\n${note}`;
    }
    const header = cols.join(" | ");
    const sep = cols.map(() => "---").join(" | ");
    const body = rows.map((r) => r.join(" | ")).join("\n");
    return `SQL:\n${sql}\n\nResult (${count} rows):\n${header}\n${sep}\n${body}`;
  };

  // Structured result for QueryResultCard (SQL + relational algebra + table).
  const buildQueryResult = (data, label) => {
    const sql = (data.generated_sql && data.generated_sql.sql) || "";
    const ra = data.relational_algebra || "";
    const ex = data.execution || {};
    const columns = ex.columns || [];
    const rows = ex.rows || [];
    const rowCount = ex.row_count != null ? ex.row_count : rows.length;
    let note = null;
    if (!data.success) {
      const reason =
        (ex.error || ex.reason) ||
        (data.validation && data.validation.reason) ||
        (data.plan && data.plan.reason) ||
        "Could not generate SQL for this question.";
      note = `Could not run the query. ${reason}`;
    } else if (rows.length === 0) {
      note = activeDatabaseSchemaOnly
        ? "This database contains schema only, so SQL was generated but no rows were executed."
        : null; // QueryResultCard shows its own "No rows returned."
    }
    return {
      label,
      sql,
      relational_algebra: ra,
      columns,
      rows,
      row_count: rowCount,
      note,
    };
  };

  const handleSubmit = async () => {
    if (!input.trim()) return;

    const userInput = input.trim();
    let conversationId = currentConversationId;

    if (!conversationId) {
      try {
        const response = await fetch(
          `${API_BASE}/conversation/create?user_id=${user.user_id}`,
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

    // Mode A: if a CSV database is active, query it via the multitable pipeline
    // (executes SQL and returns rows) instead of the legacy dataset path.
    if (currentDatabaseId) {
      // Multiple numbered questions are run one at a time; a single question
      // runs as-is. Each result is shown separately in the chat.
      const numbered = splitNumberedQuestions(userInput);
      const toRun = numbered.length >= 2 ? numbered : [userInput];
      const items = [];
      try {
        for (let i = 0; i < toRun.length; i++) {
          const q = toRun[i];
          const response = await fetch(
            `${API_BASE}/database/${currentDatabaseId}/execute_sql`,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ question: q }),
            }
          );
          if (!response.ok) {
            throw new Error(`Backend error: ${response.status}`);
          }
          const data = await response.json();
          const label = toRun.length > 1 ? `Q${i + 1}. ${q}` : null;
          const result = buildQueryResult(data, label);
          setMessages((prev) => [...prev, { type: "system", result }]);
          // First item carries the user bubble; later items are system-only.
          items.push({ question: i === 0 ? userInput : "", result });
        }
        await persistExchange(conversationId, items, userInput);
      } catch (error) {
        setMessages((prev) => [
          ...prev,
          { type: "system", output: `Error:\n${error.message}` },
        ]);
      } finally {
        setIsProcessing(false);
      }
      return;
    }

    // No active database: the database workspace is the single source of truth.
    // Do NOT fall back to the legacy /query schema-generation path.
    const noDbOutput =
      "No database uploaded or selected. Please upload a dataset or select a database workspace first.";
    setMessages((prev) => [
      ...prev,
      { type: "system", output: noDbOutput },
    ]);
    await persistExchange(
      conversationId,
      [{ question: userInput, output: noDbOutput }],
      userInput
    );
    setIsProcessing(false);
  };

  // Mode B / Mode C: mirror the schema-only assignment result into the chat
  // body, reusing the same system-message mechanism as normal query output.
  const addAssignmentToChat = async (payload) => {
    // Payload: { userMessage, data } on success, or { userMessage, error }.
    const userMessage = payload && payload.userMessage;
    const data = payload && payload.data;
    const error = payload && payload.error;

    const lines = ["Schema-Based SQL Generation"];
    if (error || !data) {
      lines.push("");
      lines.push(error || "Could not import the assignment.");
    } else {
      lines.push(`Database ${data.database_id}`);
      lines.push("");
      lines.push("Detected tables:");
      (data.tables || []).forEach((t) => {
        const name = t.name || t.table_name;
        const cols = (t.columns || [])
          .map((c) => c.name || c.column_name || c)
          .join(", ");
        lines.push(`- ${name}(${cols})`);
      });
      lines.push("");
      lines.push("Detected relationships:");
      const rels = data.relationships || [];
      if (rels.length === 0) {
        lines.push("- None");
      } else {
        rels.forEach((r) =>
          lines.push(
            `- ${r.from_table}.${r.from_column} -> ${r.to_table}.${r.to_column}`
          )
        );
      }
      lines.push("");
      lines.push("Generated SQL:");
      (data.generated_sql || []).forEach((q, i) => {
        lines.push(`Q${i + 1}. ${q.question}`);
        if (q.sql) {
          lines.push(`SQL: ${q.sql}`);
        } else {
          lines.push(`No SQL generated${q.reason ? ` (${q.reason})` : ""}.`);
        }
        lines.push("");
      });
      lines.push(
        "Note: This schema does not include a dataset, so only SQL was generated."
      );
    }

    const assistantOutput = lines.join("\n");
    setMessages((prev) => {
      const next = [...prev];
      if (userMessage) next.push({ type: "user", text: userMessage });
      next.push({ type: "system", output: assistantOutput });
      return next;
    });

    // Persist the exchange so it survives refresh / chat switch, and set the
    // chat title from the first line of the user's input (or the file label).
    const conversationId = await ensureConversation();
    const title = (
      (userMessage || "")
        .split("\n")
        .map((s) => s.trim())
        .find(Boolean) || "Assignment"
    ).slice(0, 60);
    await persistExchange(
      conversationId,
      [{ question: userMessage || "", output: assistantOutput }],
      title
    );
  };

  if (!user) {
    return <AuthPage setUser={setUser} />;
  }

  const conversationTitle =
    conversions.find((c) => c.conversation_id === currentConversationId)?.title ||
    "";

  return (
    <div className="h-screen overflow-hidden bg-gray-100 flex">
      <Sidebar
        target={target}
        conversions={conversions}
        setActivePage={setActivePage}
        newConversion={newConversion}
        loadConversationMessages={loadConversationMessages}
        user={user}
        setUser={setUser}
      />

      <main className="flex-1 flex flex-col min-h-0">
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
          onAssignmentResult={addAssignmentToChat}
          onDatabaseCreated={handleDatabaseCreated}
          onSelectDatabase={handleSelectDatabase}
          activeDatabaseId={currentDatabaseId}
          conversationTitle={conversationTitle}
        />
        )}
      </main>
    </div>
  );
}

export default App;
