import { useState } from "react";
import { API_BASE } from "../api";

// Startup card shown in the chat area when a conversation has no active
// database yet. Frontend-only for this step: it collects file selections and
// shows a processing state, but does NOT create or activate a real database.
// Tabs 2-4 are placeholders. Once a real active database exists (selected via
// the header selector, or created by a future wired flow), ConversionPage
// swaps this card out for the query input bar.

const TABS = [
  { id: "upload", label: "Upload Database / Tables" },
  { id: "schema", label: "Create Database from Schema" },
  { id: "browse", label: "Browse Existing Databases" },
  { id: "spider", label: "Load from Spider 2.0" },
];

function DatabaseWorkspaceCard({
  activeDatabaseLabel = "None",
  userId = null,
  conversationId = null,
  onDatabaseCreated = () => {},
}) {
  const [activeTab, setActiveTab] = useState("upload");

  // Upload tab selections.
  const [dbFile, setDbFile] = useState(null);
  const [csvFiles, setCsvFiles] = useState([]);
  const [processing, setProcessing] = useState(false);
  const [notice, setNotice] = useState("");

  const hasSelection = csvFiles.length > 0 || Boolean(dbFile);

  const deriveName = () => {
    if (csvFiles.length > 0) {
      return csvFiles[0].name.replace(/\.[Cc][Ss][Vv]$/, "") || "database";
    }
    return "database";
  };

  const handleCreate = async () => {
    setNotice("");

    // CSV path: reuse the existing /upload-database endpoint. On success App's
    // onDatabaseCreated sets the active database + summary; the query input
    // stays hidden until relationships are finalized in a later step.
    if (csvFiles.length > 0) {
      if (!userId) {
        setNotice("Please sign in first.");
        return;
      }
      setProcessing(true);
      try {
        const formData = new FormData();
        csvFiles.forEach((f) => formData.append("files", f));
        formData.append("user_id", userId);
        if (conversationId) formData.append("conversation_id", conversationId);
        formData.append("name", deriveName());

        const res = await fetch(`${API_BASE}/upload-database`, {
          method: "POST",
          body: formData,
        });
        const data = await res.json();

        if (!data.success) {
          setNotice(data.message || "Database creation failed.");
          return;
        }
        onDatabaseCreated(data);
      } catch (e) {
        setNotice(`Could not reach the server: ${e.message}`);
      } finally {
        setProcessing(false);
      }
      return;
    }

    // SQLite .db only: no backend endpoint exists yet.
    if (dbFile) {
      setNotice("SQLite upload backend not connected yet.");
    }
  };

  return (
    <div className="h-full flex items-center justify-center">
      <div className="w-[80%] max-w-5xl h-[85%] bg-white border border-gray-200 rounded-2xl shadow-lg flex flex-col overflow-hidden">
        <div className="px-6 py-5 border-b border-gray-100">
          <h2 className="text-2xl font-bold text-gray-800">Database Workspace</h2>
          <p className="text-gray-500 text-sm mt-1">
            Load a database to start asking questions.
          </p>
        </div>

        {/* Tabs — all four fit in one row, no horizontal scroll */}
        <div className="flex gap-1 px-3 pt-3 border-b border-gray-100">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 px-2 py-2 text-xs font-medium leading-tight text-center rounded-t-lg transition-colors ${
                activeTab === tab.id
                  ? "bg-gray-100 text-gray-900 border-b-2 border-blue-500"
                  : "text-gray-500 hover:text-gray-800"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab body — scrolls internally so the card never grows the page */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {activeTab === "upload" && (
            <div className="flex flex-col gap-6">
              {/* Two upload choices: CSV table files, or a SQLite database file */}
              <div className="flex flex-col gap-4 sm:flex-row sm:gap-6">
                <div className="flex-1 border border-gray-200 rounded-xl p-4">
                  <h3 className="text-sm font-semibold text-gray-800 mb-1">
                    CSV table files
                  </h3>
                  <p className="text-xs text-gray-500 mb-3">
                    Upload one CSV for a single-table database, or multiple CSV
                    files for a multi-table database.
                  </p>
                  <label className="inline-block cursor-pointer bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm rounded-xl px-4 py-2">
                    Choose CSV file(s)
                    <input
                      type="file"
                      accept=".csv"
                      multiple
                      className="hidden"
                      onChange={(e) => setCsvFiles(Array.from(e.target.files || []))}
                    />
                  </label>
                </div>

                <div className="flex-1 border border-gray-200 rounded-xl p-4">
                  <h3 className="text-sm font-semibold text-gray-800 mb-1">
                    SQLite database file
                  </h3>
                  <p className="text-xs text-gray-500 mb-3">
                    Upload an existing SQLite database file.
                  </p>
                  <label className="inline-block cursor-pointer bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm rounded-xl px-4 py-2">
                    Choose database file
                    <input
                      type="file"
                      accept=".db,.sqlite,.sqlite3"
                      className="hidden"
                      onChange={(e) => setDbFile(e.target.files?.[0] || null)}
                    />
                  </label>
                </div>
              </div>

              {/* Selected files, grouped by kind */}
              {hasSelection ? (
                <div className="flex flex-col gap-3">
                  {csvFiles.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-gray-500 mb-1">
                        Selected CSV files
                      </p>
                      <ul className="flex flex-col gap-1">
                        {csvFiles.map((f, i) => (
                          <li
                            key={`${f.name}-${i}`}
                            className="text-sm text-gray-700 bg-gray-50 border border-gray-200 rounded-lg px-3 py-1.5"
                          >
                            {f.name}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {dbFile && (
                    <div>
                      <p className="text-xs font-semibold text-gray-500 mb-1">
                        Selected database file
                      </p>
                      <p className="text-sm text-gray-700 bg-gray-50 border border-gray-200 rounded-lg px-3 py-1.5">
                        {dbFile.name}
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-sm text-gray-400">No files selected yet.</p>
              )}

              <div className="flex flex-col gap-2">
                {notice && <p className="text-sm text-amber-600">{notice}</p>}
                <div>
                  <button
                    onClick={handleCreate}
                    disabled={!hasSelection || processing}
                    className="bg-blue-500 text-white text-sm px-5 py-2.5 rounded-xl hover:bg-blue-600 disabled:opacity-50"
                  >
                    {processing ? "Processing…" : "Create Database"}
                  </button>
                </div>
              </div>
            </div>
          )}

          {activeTab === "schema" && (
            <div className="text-sm text-gray-600">
              <p className="font-medium text-gray-800 mb-2">
                Create Database from Schema
              </p>
              <p>
                Coming next: define tables from a text input, or upload a{" "}
                <code>.txt</code>, <code>.docx</code>, or <code>.md</code> schema
                file. Schema-based creation is not implemented yet.
              </p>
            </div>
          )}

          {activeTab === "browse" && (
            <div className="text-sm text-gray-600">
              <p className="font-medium text-gray-800 mb-2">
                Browse Existing Databases
              </p>
              <p>Coming next: pick from databases you've already created.</p>
            </div>
          )}

          {activeTab === "spider" && (
            <div className="text-sm text-gray-600">
              <p className="font-medium text-gray-800 mb-2">Load from Spider 2.0</p>
              <p>Coming next: load a benchmark database from Spider 2.0.</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-gray-100">
          <p className="text-sm text-gray-500">
            Active Database:{" "}
            <span className="font-medium text-gray-700">{activeDatabaseLabel}</span>
          </p>
        </div>
      </div>
    </div>
  );
}

export default DatabaseWorkspaceCard;
