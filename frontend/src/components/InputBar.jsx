import { useState, useRef, useEffect, useLayoutEffect } from "react";
import DatabaseWorkspace from "./DatabaseWorkspace";
import AssignmentResult from "./AssignmentResult";

import { API_BASE } from "../api";

const TEXTAREA_MAX_H = 180;

function InputBar({
  input,
  setInput,
  handleSubmit,
  currentConversationId,
  onDatabaseCreated = () => {},
  onAssignmentResult = () => {},
  onSelectDatabase = () => {},
  activeDatabaseId = null,
  onBarResize = () => {},
  onContainmentSubmit = () => {},
}) {
  // Auto-grow textarea: reset to auto then grow to content, capped at max.
  const textareaRef = useRef(null);
  const barRef = useRef(null);

  const resizeTextarea = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, TEXTAREA_MAX_H)}px`;
  };

  // Re-fit whenever the value changes (typing, paste, or programmatic clear).
  useLayoutEffect(() => {
    resizeTextarea();
  }, [input]);

  // Report the footer's rendered height up so the chat area can reserve space.
  useEffect(() => {
    const node = barRef.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => {
      onBarResize(node.offsetHeight);
    });
    ro.observe(node);
    onBarResize(node.offsetHeight);
    return () => ro.disconnect();
  }, [onBarResize]);
  // --- multi-file "Create database" flow state ----------------------------
  const [stagedFiles, setStagedFiles] = useState([]);
  const [dbName, setDbName] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [dbError, setDbError] = useState("");

  // --- workspace overlay --------------------------------------------------
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [workspaceDbId, setWorkspaceDbId] = useState(null);

  // --- containment-check mode (INLINE in the input bar; no modal) ----------
  // ONE textarea; each non-empty line is treated as a separate NL query.
  const [mode, setMode] = useState("normal"); // "normal" | "containment"
  const [containInput, setContainInput] = useState("");

  const submitContainment = () => {
    const queries = containInput
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    if (queries.length < 2) return; // need at least two queries
    onContainmentSubmit(queries);
    setContainInput("");
  };

  const userId = localStorage.getItem("user_id");

    // --- Mode B/C assignment flow ------------------------------------------
  const [assignmentResult, setAssignmentResult] = useState(null);
  const [assignmentBusy, setAssignmentBusy] = useState(false);

  // Mode C is detected ONLY by the presence of table/schema definitions, NOT by
  // numbered questions alone. A schema line is composed only of one or more
  // Name(col, ...) definitions, so question lines like "1. List ... (PetID, Name)"
  // are never mistaken for schema.
  const hasSchemaDefinitions = (text) => {
    const lines = (text || "").split("\n");
    let tableDefs = 0;
    for (const line of lines) {
      const trimmed = line.trim();
      if (/^([A-Za-z_]\w*\s*\([^)]*\)\s*)+$/.test(trimmed)) {
        tableDefs += (trimmed.match(/[A-Za-z_]\w*\s*\([^)]*\)/g) || []).length;
      }
    }
    return tableDefs >= 2;
  };

  const importAssignmentText = async () => {
    if (!userId) {
      alert("Please sign in first.");
      return;
    }

    const pasted = input;
    setAssignmentBusy(true);

    try {
      const response = await fetch(`${API_BASE}/assignment/import-text`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: Number(userId),
          text: pasted,
          conversation_id: currentConversationId,
        }),
      });

      const data = await response.json();

      // Output goes to the chat body (no auto-modal). On failure, report in
      // chat too instead of an alert.
      if (!data.success) {
        onAssignmentResult({
          userMessage: pasted,
          error: data.message || "Assignment import failed.",
        });
        setInput("");
        return;
      }

      onDatabaseCreated(data);
      onAssignmentResult({ userMessage: pasted, data });
      setInput("");
    } catch (err) {
      alert(`Could not reach the server: ${err.message}`);
    } finally {
      setAssignmentBusy(false);
    }
  };

  const handleAssignmentFile = async (e) => {
    const file = e.target.files[0];
    e.target.value = "";

    if (!file) return;

    if (!userId) {
      alert("Please sign in first.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("user_id", userId);

    if (currentConversationId) {
      formData.append("conversation_id", currentConversationId);
    }

    formData.append("name", file.name);

    setAssignmentBusy(true);

    try {
      const response = await fetch(`${API_BASE}/assignment/import-file`, {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      const fileLabel = `Uploaded assignment file: ${file.name}`;
      if (!data.success) {
        onAssignmentResult({
          userMessage: fileLabel,
          error: data.message || "Assignment import failed.",
        });
        return;
      }

      onDatabaseCreated(data);
      onAssignmentResult({ userMessage: fileLabel, data });
    } catch (err) {
      alert(`Could not reach the server: ${err.message}`);
    } finally {
      setAssignmentBusy(false);
    }
  };

  const onConvert = () => {
    // Active database -> everything typed is a query for that database
    // (App handles single vs. multiple numbered questions). Never assignment.
    if (activeDatabaseId) {
      handleSubmit();
      return;
    }
    // No active database: treat as a Mode C assignment paste ONLY if it actually
    // contains table/schema definitions; otherwise it's a normal query and App
    // shows the no-database message.
    if (hasSchemaDefinitions(input)) {
      importAssignmentText();
      return;
    }
    handleSubmit();
  };

  // --- existing single-CSV upload (unchanged, still feeds /query) ---------
  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (!userId) {
      alert("Please sign in first.");
      return;
    }

    if (!currentConversationId) {
      alert("Please start a new chat before uploading a dataset.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("user_id", userId);
    formData.append("conversation_id", currentConversationId);

    const response = await fetch(`${API_BASE}/upload-csv`, {
      method: "POST",
      body: formData,
    });

    const data = await response.json();

    if (!data.success) {
      alert(data.message || "File upload failed");
      return;
    }

    alert(`Uploaded: ${data.filename}`);
  };

  // --- multi-file flow ----------------------------------------------------
  const baseName = (filename) =>
    filename.replace(/\.[Cc][Ss][Vv]$/, "").replace(/^.*[\\/]/, "");

  const handleDatabaseSelect = (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (files.length === 0) return;

    setDbError("");
    setStagedFiles(files);
    setDbName((prev) => prev || baseName(files[0].name));
  };

  const removeStagedFile = (index) => {
    setStagedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const cancelStaging = () => {
    setStagedFiles([]);
    setDbName("");
    setDbError("");
  };

  const createDatabase = async () => {
    if (!userId) {
      setDbError("Please sign in first.");
      return;
    }
    if (!currentConversationId) {
      setDbError("Start a new chat before creating a database.");
      return;
    }
    if (stagedFiles.length === 0) {
      setDbError("Choose at least one CSV file.");
      return;
    }

    const formData = new FormData();
    stagedFiles.forEach((file) => formData.append("files", file));
    formData.append("user_id", userId);
    formData.append("conversation_id", currentConversationId);
    formData.append("name", dbName.trim() || "database");

    setIsUploading(true);
    setDbError("");

    try {
      const response = await fetch(`${API_BASE}/upload-database`, {
        method: "POST",
        body: formData,
      });
      const data = await response.json();

      if (!data.success) {
        setDbError(data.message || "Database creation failed.");
        return;
      }

      // Created: clear staging and open the workspace on the new database.
      setStagedFiles([]);
      setDbName("");
      setWorkspaceDbId(data.database_id);
      setWorkspaceOpen(true);
      onDatabaseCreated(data);
    } catch (err) {
      setDbError(`Could not reach the server: ${err.message}`);
    } finally {
      setIsUploading(false);
    }
  };

    // --- unified upload button: routes by selected file type ----------------
  const handleUploadAny = (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";

    if (files.length === 0) return;

    const isCsv = (file) => /\.csv$/i.test(file.name);
    const csvFiles = files.filter(isCsv);
    const otherFiles = files.filter((file) => !isCsv(file));

    if (csvFiles.length > 0 && otherFiles.length > 0) {
      alert("Please upload either CSV files or one assignment document, not both.");
      return;
    }

    if (otherFiles.length > 0) {
      if (otherFiles.length > 1) {
        alert("Please upload only one assignment document.");
        return;
      }

      handleAssignmentFile({
        target: {
          files: [otherFiles[0]],
          value: "",
        },
      });
      return;
    }

    // Any number of CSVs (including a single file) goes through the database
    // staging flow so it creates/opens a Database Workspace. A single CSV no
    // longer routes to the dataset-only /upload-csv path.
    handleDatabaseSelect({
      target: {
        files: csvFiles,
        value: "",
      },
    });
  };

  const isStaging = stagedFiles.length > 0;

  return (
    <>
      {workspaceOpen && (
        <DatabaseWorkspace
          userId={userId}
          activeDatabaseId={activeDatabaseId}
          onClose={() => setWorkspaceOpen(false)}
          onSelectDatabase={onSelectDatabase}
        />
      )}

      {assignmentResult && (
        <AssignmentResult
          result={assignmentResult}
          onClose={() => setAssignmentResult(null)}
        />
      )}

      <footer
        ref={barRef}
        className="fixed bottom-6 left-[13%] w-[87%] z-30 pointer-events-none"
      >
        <div className="w-[900px] mx-auto flex flex-col gap-3">
          {/* Staging panel: name + confirm before creating */}
          {isStaging && (
            <div className="bg-white rounded-2xl shadow-xl p-4 pointer-events-auto">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-gray-800">
                  New database — {stagedFiles.length}{" "}
                  {stagedFiles.length === 1 ? "table" : "tables"}
                </h3>
                <button
                  onClick={cancelStaging}
                  className="text-sm text-gray-500 hover:text-gray-700"
                >
                  Cancel
                </button>
              </div>

              <input
                className="w-full border border-gray-300 rounded-xl px-4 py-2 mb-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="Database name"
                value={dbName}
                onChange={(e) => setDbName(e.target.value)}
              />

              <ul className="flex flex-col gap-1 mb-3">
                {stagedFiles.map((file, index) => (
                  <li
                    key={`${file.name}-${index}`}
                    className="flex items-center justify-between bg-gray-100 rounded-lg px-3 py-2 text-sm text-gray-700"
                  >
                    <span>
                      {file.name}{" "}
                      <span className="text-gray-400">
                        → {baseName(file.name).toLowerCase()}
                      </span>
                    </span>
                    <button
                      onClick={() => removeStagedFile(index)}
                      className="text-gray-400 hover:text-red-500"
                      aria-label={`Remove ${file.name}`}
                    >
                      ✕
                    </button>
                  </li>
                ))}
              </ul>

              {dbError && <p className="text-sm text-red-500 mb-3">{dbError}</p>}

              <button
                onClick={createDatabase}
                disabled={isUploading}
                className="bg-blue-500 text-white px-5 py-2.5 rounded-xl hover:bg-blue-600 disabled:opacity-60"
              >
                {isUploading ? "Creating…" : "Create database"}
              </button>
            </div>
          )}

          {/* Mode toggle: normal chat vs. containment check. Switching mode only
              changes the input area below (single box vs. two boxes) — results
              always land in the chat, never a modal. */}
          {activeDatabaseId && (
            <div className="flex gap-1 bg-white rounded-full shadow-md p-1 pointer-events-auto w-fit mx-auto">
              <button
                onClick={() => setMode("normal")}
                className={`px-4 py-1.5 rounded-full text-sm transition ${
                  mode === "normal"
                    ? "bg-blue-500 text-white"
                    : "text-gray-600 hover:bg-gray-100"
                }`}
              >
                Normal Query
              </button>
              <button
                onClick={() => setMode("containment")}
                className={`px-4 py-1.5 rounded-full text-sm transition ${
                  mode === "containment"
                    ? "bg-blue-500 text-white"
                    : "text-gray-600 hover:bg-gray-100"
                }`}
              >
                Containment Check
              </button>
            </div>
          )}

          {/* Input bar (existing layout, plus the database picker button) */}
          <div className="flex gap-3 bg-white rounded-3xl shadow-xl p-3 pointer-events-auto">

            {/* Upload/create-database happens in the Database Workspace before
                the chat input is shown. Once a database is active the query bar
                is just text + Convert, so hide this legacy upload control. */}
            {!activeDatabaseId && mode === "normal" && (
              <label
                className="cursor-pointer bg-gray-100 px-5 py-4 rounded-xl hover:bg-gray-200"
                title="Upload CSV file(s) or assignment document"
              >
                📎
                <input
                  type="file"
                  accept=".csv,.txt,.md,.sql,.docx,.pdf"
                  multiple
                  onChange={handleUploadAny}
                  className="hidden"
                />
              </label>
            )}

            {mode === "containment" ? (
              // ONE box; each non-empty line is a separate query. Enter adds a
              // new line; Ctrl/Cmd+Enter (or the Convert button) submits.
              <textarea
                className="flex-1 border border-gray-300 rounded-xl px-5 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none min-h-[56px] max-h-[180px] overflow-y-auto"
                placeholder="Enter multiple natural-language queries, one per line..."
                value={containInput}
                rows={3}
                onChange={(e) => setContainInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault();
                    submitContainment();
                  }
                }}
              />
            ) : (
              <textarea
                ref={textareaRef}
                className="flex-1 border border-gray-300 rounded-xl px-5 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none min-h-[56px] max-h-[180px] overflow-y-auto"
                placeholder="Type a question, or paste assignment schema + questions..."
                value={input}
                rows={1}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  // Enter submits; Shift+Enter inserts a new line.
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    if (input.trim()) {
                      onConvert();
                    }
                  }
                }}
              />
            )}

            <button
              onClick={mode === "containment" ? submitContainment : onConvert}
              disabled={assignmentBusy}
              className="bg-blue-500 text-white px-6 py-4 rounded-xl hover:bg-blue-600 disabled:opacity-60"
            >
              {assignmentBusy ? "Working…" : "Convert"}
            </button>
          </div>
        </div>
      </footer>
    </>
  );
}

export default InputBar;
