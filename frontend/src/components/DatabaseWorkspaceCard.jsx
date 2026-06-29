import { useState, useEffect } from "react";
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

  // Create-from-schema tab state.
  const [schemaName, setSchemaName] = useState("");
  const [schemaText, setSchemaText] = useState("");
  const [schemaProcessing, setSchemaProcessing] = useState(false);
  const [schemaNotice, setSchemaNotice] = useState("");

  // Browse-existing tab state.
  const [browseList, setBrowseList] = useState([]);
  const [browseLoading, setBrowseLoading] = useState(false);
  const [browseError, setBrowseError] = useState("");
  const [loadingId, setLoadingId] = useState(null);

  // Load-from-Spider-2.0 tab state.
  const [spiderStatus, setSpiderStatus] = useState(null);
  const [spiderStatusLoading, setSpiderStatusLoading] = useState(false);
  const [spiderQuery, setSpiderQuery] = useState("");
  const [spiderList, setSpiderList] = useState([]);
  const [spiderLoading, setSpiderLoading] = useState(false);
  const [spiderError, setSpiderError] = useState("");
  const [spiderImportingId, setSpiderImportingId] = useState(null);

  // Fetch the user's previously created databases when the Browse tab opens.
  useEffect(() => {
    if (activeTab !== "browse") return;
    if (!userId) {
      setBrowseError("Please sign in first.");
      return;
    }
    setBrowseLoading(true);
    setBrowseError("");
    fetch(`${API_BASE}/databases/${userId}`)
      .then((r) => r.json())
      .then((d) => {
        if (d.success === false) {
          setBrowseError(d.message || "Could not load databases.");
          setBrowseList([]);
        } else {
          setBrowseList(d.databases || []);
        }
      })
      .catch((e) => setBrowseError(`Could not load databases: ${e.message}`))
      .finally(() => setBrowseLoading(false));
  }, [activeTab, userId]);

  // Load an existing database into this chat. Reuses onDatabaseCreated so the
  // rest of the flow (summary -> relationship review -> finalize) is unchanged.
  // No setup message is added here; that only happens on finalize.
  const handleLoadExisting = (db) => {
    if (loadingId != null) return; // ignore rapid double-clicks
    setLoadingId(db.database_id);
    const tables = (db.tables || []).map((t) => ({
      table_name: t.table_name,
      rows_inserted: t.row_count != null ? t.row_count : null,
      success: true,
    }));
    onDatabaseCreated({
      success: true,
      database_id: db.database_id,
      name: db.name || `Database ${db.database_id}`,
      tables,
      relationships: [],
    });
  };

  // Check whether a real Spider 2.0 source is configured when the tab opens.
  useEffect(() => {
    if (activeTab !== "spider") return;
    let cancelled = false;
    setSpiderStatusLoading(true);
    // Cache-bust so a restarted backend's fresh status is never read from cache.
    fetch(`${API_BASE}/spider2/status?t=${Date.now()}`, { cache: "no-store" })
      .then((r) => r.json())
      .then((s) => {
        if (!cancelled) setSpiderStatus(s);
      })
      .catch((e) => {
        if (!cancelled)
          setSpiderStatus({
            configured: false,
            message: `Could not load Spider 2.0 status: ${e.message}`,
          });
      })
      .finally(() => {
        if (!cancelled) setSpiderStatusLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeTab, userId]);

  // Fetch the real catalog only when a source is configured (and on search).
  useEffect(() => {
    if (activeTab !== "spider") return;
    if (!spiderStatus || !spiderStatus.configured) {
      setSpiderList([]);
      return;
    }
    let cancelled = false;
    setSpiderLoading(true);
    setSpiderError("");
    const url = `${API_BASE}/spider2/catalog?user_id=${
      userId || ""
    }&q=${encodeURIComponent(spiderQuery)}`;
    fetch(url)
      .then((r) => r.json())
      .then((d) => {
        if (cancelled) return;
        if (d.success === false) {
          setSpiderError(d.message || "Could not load catalog.");
          setSpiderList([]);
        } else {
          setSpiderList(d.items || []);
        }
      })
      .catch((e) => {
        if (!cancelled) setSpiderError(`Could not load catalog: ${e.message}`);
      })
      .finally(() => {
        if (!cancelled) setSpiderLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeTab, spiderQuery, userId, spiderStatus]);

  const handleImportSpider = async (item) => {
    if (spiderImportingId != null) return; // ignore rapid double-clicks
    if (!item.importable) return; // browse-only items can't be imported
    setSpiderImportingId(item.spider2_id);
    setSpiderError("");
    try {
      const res = await fetch(`${API_BASE}/spider2/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: Number(userId),
          conversation_id: conversationId,
          spider2_id: item.spider2_id,
        }),
      });
      const data = await res.json();
      if (!data.success) {
        setSpiderError(data.message || "Import failed.");
        return;
      }
      onDatabaseCreated(data);
    } catch (e) {
      setSpiderError(`Could not reach the server: ${e.message}`);
    } finally {
      setSpiderImportingId(null);
    }
  };

  const handleSchemaFile = (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    const lower = f.name.toLowerCase();
    if (lower.endsWith(".docx")) {
      setSchemaNotice(
        "DOCX schema upload is not connected yet. Please use .txt, .md, or paste SQL."
      );
      return;
    }
    if (!(lower.endsWith(".txt") || lower.endsWith(".md") || lower.endsWith(".sql"))) {
      setSchemaNotice("Unsupported file type. Use .txt, .md, or paste SQL.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setSchemaText(String(reader.result || ""));
      setSchemaNotice("");
      if (!schemaName) setSchemaName(f.name.replace(/\.[^.]+$/, ""));
    };
    reader.readAsText(f);
  };

  const handleCreateFromSchema = async () => {
    setSchemaNotice("");
    if (!userId) {
      setSchemaNotice("Please sign in first.");
      return;
    }
    if (!schemaName.trim()) {
      setSchemaNotice("Please enter a database name.");
      return;
    }
    if (!schemaText.trim()) {
      setSchemaNotice("Please paste schema text or upload a schema file.");
      return;
    }
    setSchemaProcessing(true);
    try {
      const formData = new FormData();
      formData.append("user_id", userId);
      if (conversationId) formData.append("conversation_id", conversationId);
      formData.append("name", schemaName.trim());
      formData.append("schema_text", schemaText);

      const res = await fetch(`${API_BASE}/create-database-from-schema`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();

      if (!data.success) {
        setSchemaNotice(data.message || "Database creation failed.");
        return;
      }
      onDatabaseCreated(data);
    } catch (e) {
      setSchemaNotice(`Could not reach the server: ${e.message}`);
    } finally {
      setSchemaProcessing(false);
    }
  };

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
            <div className="flex flex-col gap-4">
              <p className="text-sm text-gray-500">
                Paste SQL CREATE TABLE statements or upload a schema file.
              </p>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Database name
                </label>
                <input
                  value={schemaName}
                  onChange={(e) => setSchemaName(e.target.value)}
                  placeholder="e.g. UniversitySchema"
                  className="w-full border border-gray-300 rounded-xl px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Schema (SQL DDL)
                </label>
                <textarea
                  value={schemaText}
                  onChange={(e) => setSchemaText(e.target.value)}
                  rows={8}
                  placeholder="CREATE TABLE students ( student_id INTEGER PRIMARY KEY, student_name TEXT, major TEXT );"
                  className="w-full border border-gray-300 rounded-xl px-4 py-2 text-sm font-mono resize-y focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="inline-block cursor-pointer bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm rounded-xl px-4 py-2">
                  Upload schema file (.txt, .md, .docx)
                  <input
                    type="file"
                    accept=".txt,.md,.sql,.docx"
                    className="hidden"
                    onChange={handleSchemaFile}
                  />
                </label>
              </div>

              {schemaNotice && (
                <p className="text-sm text-amber-600">{schemaNotice}</p>
              )}

              <div>
                <button
                  onClick={handleCreateFromSchema}
                  disabled={schemaProcessing}
                  className="bg-blue-500 text-white text-sm px-5 py-2.5 rounded-xl hover:bg-blue-600 disabled:opacity-50"
                >
                  {schemaProcessing ? "Processing…" : "Create Database"}
                </button>
              </div>
            </div>
          )}

          {activeTab === "browse" && (
            <div className="flex flex-col gap-4">
              <p className="text-sm text-gray-500">
                Select a database you previously created.
              </p>

              {browseLoading && (
                <p className="text-sm text-gray-500">Loading…</p>
              )}
              {browseError && (
                <p className="text-sm text-amber-600">{browseError}</p>
              )}

              {!browseLoading && !browseError && browseList.length === 0 && (
                <p className="text-sm text-gray-400">
                  No databases found yet. Create one from Upload or Schema first.
                </p>
              )}

              {!browseLoading && !browseError && browseList.length > 0 && (
                <ul className="flex flex-col gap-2">
                  {browseList.map((db) => {
                    const tables = db.tables || [];
                    return (
                      <li
                        key={db.database_id}
                        className="border border-gray-200 rounded-xl p-4 flex items-start justify-between gap-3"
                      >
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-gray-800">
                            {db.name || `Database ${db.database_id}`}{" "}
                            <span className="text-gray-400 font-normal">
                              #{db.database_id}
                            </span>
                          </p>
                          <p className="text-xs text-gray-500">
                            {tables.length}{" "}
                            {tables.length === 1 ? "table" : "tables"}
                            {db.created_at ? ` · ${db.created_at}` : ""}
                          </p>
                          {tables.length > 0 && (
                            <div className="mt-1 flex flex-wrap gap-1.5">
                              {tables.map((t, i) => (
                                <span
                                  key={`${t.table_name}-${i}`}
                                  className="text-xs text-gray-700 bg-gray-50 border border-gray-200 rounded-lg px-2 py-0.5"
                                >
                                  {t.table_name}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>

                        <button
                          onClick={() => handleLoadExisting(db)}
                          disabled={loadingId != null}
                          className="shrink-0 bg-blue-500 text-white text-sm px-4 py-2 rounded-xl hover:bg-blue-600 disabled:opacity-50"
                        >
                          {loadingId === db.database_id
                            ? "Loading…"
                            : "Load Database"}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          )}

          {activeTab === "spider" && (
            <div className="flex flex-col gap-4">
              <p className="text-sm text-gray-500">
                Browse local Spider 2.0 benchmark databases. Cloud
                BigQuery/Snowflake loading will be added later.
              </p>

              {spiderStatusLoading && (
                <p className="text-sm text-gray-500">Checking Spider 2.0 source…</p>
              )}

              {/* Not configured: show setup instructions only — no fake data. */}
              {!spiderStatusLoading &&
                spiderStatus &&
                !spiderStatus.configured && (
                  <div className="border border-gray-200 rounded-xl p-4 text-sm text-gray-600 flex flex-col gap-2">
                    <p className="font-semibold text-gray-800">
                      Spider 2.0 data source is not configured.
                    </p>
                    <div>
                      <p className="mb-1">To use real Spider 2.0 databases:</p>
                      <ol className="list-decimal list-inside space-y-0.5">
                        <li>
                          Clone or download the official Spider 2.0
                          repository/data.
                        </li>
                        <li>
                          Set environment variable:{" "}
                          <code>SPIDER2_DATA_DIR=C:\path\to\Spider2</code>
                        </li>
                        <li>Restart the backend.</li>
                        <li>Return to this tab.</li>
                      </ol>
                    </div>
                    <div>
                      <p className="mb-1">Official sources:</p>
                      <ul className="list-disc list-inside space-y-0.5">
                        <li>https://spider2-sql.github.io/</li>
                        <li>https://github.com/xlang-ai/Spider2</li>
                      </ul>
                    </div>
                    <p className="text-xs text-gray-400">
                      Future cloud loading: BigQuery/Snowflake execution will
                      require credentials and connector setup.
                    </p>
                  </div>
                )}

              {/* Configured: source info + search + real catalog list. */}
              {!spiderStatusLoading &&
                spiderStatus &&
                spiderStatus.configured && (
                  <>
                    <p className="text-xs text-gray-500">
                      Source: {spiderStatus.source?.path} ·{" "}
                      {(spiderStatus.source?.detected_files || []).length}{" "}
                      metadata files detected
                    </p>

                    <input
                      value={spiderQuery}
                      onChange={(e) => setSpiderQuery(e.target.value)}
                      placeholder="Search Spider 2.0 tasks/databases..."
                      className="w-full border border-gray-300 rounded-xl px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />

                    {spiderLoading && (
                      <p className="text-sm text-gray-500">Loading…</p>
                    )}
                    {spiderError && (
                      <p className="text-sm text-amber-600">{spiderError}</p>
                    )}

                    {!spiderLoading &&
                      !spiderError &&
                      spiderList.length === 0 && (
                        <p className="text-sm text-gray-400">
                          Spider 2.0 source detected, but no metadata entries
                          were found by the scanner. Path:{" "}
                          {spiderStatus.source?.path}
                        </p>
                      )}

                    {!spiderLoading &&
                      !spiderError &&
                      spiderList.length > 0 && (
                        <ul className="flex flex-col gap-2">
                          {spiderList.map((item) => (
                            <li
                              key={item.spider2_id}
                              className="border border-gray-200 rounded-xl p-4 flex items-start justify-between gap-3"
                            >
                              <div className="min-w-0">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <p className="text-sm font-semibold text-gray-800">
                                    {item.name}
                                  </p>
                                  {item.dialect && (
                                    <span className="text-[10px] uppercase tracking-wide bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded">
                                      {item.dialect}
                                    </span>
                                  )}
                                  <span
                                    className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded ${
                                      item.importable
                                        ? "bg-green-100 text-green-700"
                                        : "bg-gray-200 text-gray-600"
                                    }`}
                                  >
                                    {item.availability ||
                                      (item.importable
                                        ? "LOCAL_SCHEMA_IMPORTABLE"
                                        : "LOCAL_METADATA_ONLY")}
                                  </span>
                                </div>
                                <p className="text-xs text-gray-500">
                                  {item.spider2_id}
                                  {item.domain ? ` · ${item.domain}` : ""} ·{" "}
                                  {item.table_count}{" "}
                                  {item.table_count === 1 ? "table" : "tables"}
                                  {item.column_count != null
                                    ? ` · ${item.column_count} columns`
                                    : ""}
                                </p>
                                {item.question && (
                                  <p className="text-xs text-gray-500 mt-1">
                                    {item.question}
                                  </p>
                                )}
                                {item.description && (
                                  <p className="text-xs text-gray-500 mt-1">
                                    {item.description}
                                  </p>
                                )}
                                {(item.table_names || []).length > 0 && (
                                  <div className="mt-1 flex flex-wrap gap-1.5">
                                    {item.table_names.map((t, i) => (
                                      <span
                                        key={`${t}-${i}`}
                                        className="text-xs text-gray-700 bg-gray-50 border border-gray-200 rounded-lg px-2 py-0.5"
                                      >
                                        {t}
                                      </span>
                                    ))}
                                  </div>
                                )}
                                {!item.importable && (
                                  <p className="text-xs text-amber-600 mt-1">
                                    Schema import not available yet for this item.
                                  </p>
                                )}
                              </div>

                              <button
                                onClick={() => handleImportSpider(item)}
                                disabled={
                                  spiderImportingId != null || !item.importable
                                }
                                title={
                                  item.importable
                                    ? "Load this database"
                                    : "Schema import is not available for this Spider 2.0 item yet."
                                }
                                className={`shrink-0 text-sm px-4 py-2 rounded-xl disabled:opacity-60 ${
                                  item.importable
                                    ? "bg-blue-500 text-white hover:bg-blue-600"
                                    : "bg-gray-200 text-gray-500 cursor-not-allowed"
                                }`}
                              >
                                {spiderImportingId === item.spider2_id
                                  ? "Loading…"
                                  : item.importable
                                  ? "Load Database"
                                  : "Schema unavailable"}
                              </button>
                            </li>
                          ))}
                        </ul>
                      )}
                  </>
                )}
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
