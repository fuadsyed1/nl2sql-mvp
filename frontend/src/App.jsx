import { API_BASE } from "./api";
import { useState, useEffect } from "react";
import Sidebar from "./components/Sidebar";
import Dashboard from "./components/Dashboard";
import AccountSettings from "./components/AccountSettings";
import ConversionPage from "./components/ConversionPage";
import AuthPage from "./components/AuthPage";

// Per-conversation database state (active database, finalize state, finalized
// relationships) is not persisted on the backend, so it is kept in localStorage
// keyed by conversation id. This lets a chat remember its database when the user
// switches chats or reloads.
const chatDbStateKey = (cid) => `spidersql_chat_db_state_${cid}`;

const readChatDbState = (cid) => {
  if (!cid) return null;
  try {
    const raw = localStorage.getItem(chatDbStateKey(cid));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
};

const saveChatDbState = (cid, partial) => {
  if (!cid) return;
  const current = readChatDbState(cid) || {};
  try {
    localStorage.setItem(
      chatDbStateKey(cid),
      JSON.stringify({ ...current, ...partial })
    );
  } catch {
    /* ignore quota / serialization errors */
  }
};

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
  // Summary of the active database (name/id/tables) shown after creation.
  const [activeDatabaseSummary, setActiveDatabaseSummary] = useState(null);
  // Gating: the query input stays hidden until relationships are finalized for
  // the active database. Finalization is frontend-only for this chat session.
  const [relationshipsFinalized, setRelationshipsFinalized] = useState(false);
  const [finalizedRelationships, setFinalizedRelationships] = useState(null);

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
      setActiveDatabaseSummary(null);
      setRelationshipsFinalized(false);
      setFinalizedRelationships(null);
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

      // Restore this chat's database state from localStorage (active database,
      // finalize state, finalized relationships). The setup message and these
      // flags are not persisted on the backend, so they live per-conversation.
      const saved = readChatDbState(conversationId);
      if (saved && saved.activeDatabaseId) {
        setCurrentDatabaseId(saved.activeDatabaseId);
        setActiveDatabaseSchemaOnly(false);
        setActiveDatabaseSummary(
          saved.activeDatabaseSummary || { database_id: saved.activeDatabaseId }
        );
        setRelationshipsFinalized(Boolean(saved.relationshipsFinalized));
        setFinalizedRelationships(saved.finalizedRelationships || null);

        // Rebuild the one-time setup message if relationships were finalized and
        // it isn't already present (it is frontend-only, never saved to backend).
        if (
          saved.relationshipsFinalized &&
          !restoredMessages.some((m) => m.setup)
        ) {
          restoredMessages.unshift({
            type: "system",
            setup: {
              database_id: saved.activeDatabaseId,
              name: saved.activeDatabaseSummary?.name,
              tables: saved.activeDatabaseSummary?.tables || [],
              data_availability: saved.activeDatabaseSummary?.data_availability,
              relationships: saved.finalizedRelationships || [],
            },
          });
        }
      } else {
        setCurrentDatabaseId(null);
        setActiveDatabaseSchemaOnly(false);
        setActiveDatabaseSummary(null);
        setRelationshipsFinalized(false);
        setFinalizedRelationships(null);
      }

      setMessages(restoredMessages);
      setInput("");
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
      // Store a summary for the post-creation card. The /upload-database
      // response carries name + per-table info.
      const tables = (data.tables || [])
        .filter((t) => t.success !== false)
        .map((t) => t.table_name)
        .filter(Boolean);
      const summary = {
        database_id: data.database_id,
        name: data.name || `Database ${data.database_id}`,
        tables,
        // Carried from the import response (e.g. Spider 2.0 "schema_only") so the
        // setup summary can note it. Undefined for normal CSV/SQLite/schema DBs.
        data_availability: data.data_availability,
      };
      setActiveDatabaseSummary(summary);
      // A freshly created database has not had its relationships finalized yet.
      setRelationshipsFinalized(false);
      setFinalizedRelationships(null);
      // Pin this database to the current chat so it restores on reopen.
      saveChatDbState(currentConversationId, {
        activeDatabaseId: data.database_id,
        activeDatabaseSummary: summary,
        relationshipsFinalized: false,
        finalizedRelationships: null,
      });
    }
  };

  // User picked a previous database from the workspace dropdown -> make it the
  // active query target for the current chat.
  const handleSelectDatabase = (databaseId) => {
    // databaseId is null when the user picks "None".
    const id = databaseId || null;
    setCurrentDatabaseId(id);
    setActiveDatabaseSchemaOnly(false);
    const summary = id ? { database_id: id } : null;
    setActiveDatabaseSummary(summary);
    setRelationshipsFinalized(false);
    setFinalizedRelationships(null);
    saveChatDbState(currentConversationId, {
      activeDatabaseId: id,
      activeDatabaseSummary: summary,
      relationshipsFinalized: false,
      finalizedRelationships: null,
    });
    console.log("ACTIVE DATABASE ->", id);
  };

  // Frontend-only finalize: store the confirmed relationship list for this chat
  // session, unlock the query input, and drop a one-time setup summary message
  // into the chat. No backend persistence (no endpoint).
  const handleFinalizeRelationships = (rels) => {
    if (relationshipsFinalized) return; // add the setup message only once
    const list = rels || [];
    setFinalizedRelationships(list);
    setRelationshipsFinalized(true);
    const setup = {
      database_id: currentDatabaseId,
      name: activeDatabaseSummary?.name,
      tables: activeDatabaseSummary?.tables || [],
      data_availability: activeDatabaseSummary?.data_availability,
      relationships: list.map((r) => ({
        from_table: r.from_table,
        from_column: r.from_column,
        to_table: r.to_table,
        to_column: r.to_column,
      })),
    };
    setMessages((prev) => [...prev, { type: "system", setup }]);
    // Persist finalize state so the chat restores its input + setup message.
    saveChatDbState(currentConversationId, {
      activeDatabaseId: currentDatabaseId,
      activeDatabaseSummary,
      relationshipsFinalized: true,
      finalizedRelationships: setup.relationships,
    });
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
              body: JSON.stringify({
                question: q,
                database_id: currentDatabaseId,
              }),
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

  // Text summary of a batch containment result, persisted to history so the
  // exchange survives reload (the live card is structured; history is text).
  // No backend change — reuses the {question, output} persistence.
  const buildContainmentSummary = (data) => {
    const qref = (ids) => ids.map((i) => `Q${i}`).join(", ");
    const lines = ["Containment Check"];
    (data.query_results || []).forEach((q) => {
      const flags = [];
      if (q.empty_result) flags.push("empty result");
      if (q.safe === false) flags.push("excluded (unsafe)");
      lines.push(
        `Q${q.query_id}: ${q.question}${flags.length ? ` [${flags.join(", ")}]` : ""}`
      );
    });
    lines.push("");
    (data.query_summaries || []).forEach((s) => {
      const parts = [];
      if (s.contained_in.length) parts.push(`contained in ${qref(s.contained_in)}`);
      if (s.contains.length) parts.push(`contains ${qref(s.contains)}`);
      if (s.equivalent_to.length) parts.push(`equivalent to ${qref(s.equivalent_to)}`);
      if (s.incomparable_with.length)
        parts.push(`incomparable with ${qref(s.incomparable_with)}`);
      if (s.unknown_with.length) parts.push(`unknown vs ${qref(s.unknown_with)}`);
      lines.push(
        `Q${s.query_id}: ${parts.length ? parts.join("; ") : "no containment relationship"}`
      );
    });
    if (data.limitations) lines.push("", data.limitations);
    return lines.join("\n");
  };

  // Containment Check mode: submit N NL queries (one per line) to
  // /check_containment_batch and add the pairwise result to the chat as a
  // ContainmentBatchResultCard — the SAME chat-message flow as normal results,
  // no modal. The result stays in the chat.
  const handleContainmentSubmit = async (queries) => {
    const list = (queries || []).map((q) => String(q).trim()).filter(Boolean);
    if (list.length < 2 || !currentDatabaseId) return;

    const conversationId = await ensureConversation();

    const userText =
      "Containment Check\n" + list.map((q, i) => `Q${i + 1}: ${q}`).join("\n");
    setMessages((prev) => [...prev, { type: "user", text: userText }]);
    setIsProcessing(true);

    try {
      const response = await fetch(
        `${API_BASE}/database/${currentDatabaseId}/check_containment_batch`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ queries: list }),
        }
      );
      if (!response.ok) throw new Error(`Backend error: ${response.status}`);
      const data = await response.json();
      setMessages((prev) => [...prev, { type: "system", containmentBatch: data }]);
      await persistExchange(
        conversationId,
        [{ question: userText, output: buildContainmentSummary(data) }],
        `Containment: ${list[0]}`.slice(0, 60)
      );
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        { type: "system", output: `Containment check failed:\n${error.message}` },
      ]);
    } finally {
      setIsProcessing(false);
    }
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
          activeDatabaseSummary={activeDatabaseSummary}
          relationshipsFinalized={relationshipsFinalized}
          onFinalizeRelationships={handleFinalizeRelationships}
          onContainmentSubmit={handleContainmentSubmit}
          conversationTitle={conversationTitle}
        />
        )}
      </main>
    </div>
  );
}

export default App;

