import { useState } from "react";
import DatabaseWorkspace from "./DatabaseWorkspace";

const API = "http://localhost:8000";

function InputBar({
  input,
  setInput,
  handleSubmit,
  currentConversationId,
  onDatabaseCreated = () => {},
}) {
  // --- multi-file "Create database" flow state ----------------------------
  const [stagedFiles, setStagedFiles] = useState([]);
  const [dbName, setDbName] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [dbError, setDbError] = useState("");

  // --- workspace overlay --------------------------------------------------
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [workspaceDbId, setWorkspaceDbId] = useState(null);

  const userId = localStorage.getItem("user_id");

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

    const response = await fetch(`${API}/upload-csv`, {
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
      const response = await fetch(`${API}/upload-database`, {
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

  const openDatabaseBrowser = () => {
    setWorkspaceDbId(null); // null => workspace picks the most recent
    setWorkspaceOpen(true);
  };

  const isStaging = stagedFiles.length > 0;

  return (
    <>
      {workspaceOpen && (
        <DatabaseWorkspace
          userId={userId}
          databaseId={workspaceDbId}
          onClose={() => setWorkspaceOpen(false)}
        />
      )}

      <footer className="fixed bottom-6 left-[13%] w-[87%] z-30 pointer-events-none">
        <div className="w-[900px] mx-auto flex flex-col gap-3">
          {/* Browse existing databases */}
          {!isStaging && (
            <div className="pointer-events-auto">
              <button
                onClick={openDatabaseBrowser}
                className="text-sm bg-white shadow rounded-full px-4 py-1.5 text-gray-600 hover:text-gray-800"
              >
                🗄️ Databases
              </button>
            </div>
          )}

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

          {/* Input bar (existing layout, plus the database picker button) */}
          <div className="flex gap-3 bg-white rounded-3xl shadow-xl p-3 pointer-events-auto">
            <label
              className="cursor-pointer bg-gray-100 px-5 py-4 rounded-xl hover:bg-gray-200"
              title="Upload one CSV"
            >
              📎
              <input
                type="file"
                accept=".csv"
                onChange={handleFileUpload}
                className="hidden"
              />
            </label>

            <label
              className="cursor-pointer bg-gray-100 px-5 py-4 rounded-xl hover:bg-gray-200"
              title="Upload several CSVs as one database"
            >
              🗄️
              <input
                type="file"
                accept=".csv"
                multiple
                onChange={handleDatabaseSelect}
                className="hidden"
              />
            </label>

            <input
              className="flex-1 border border-gray-300 rounded-xl px-5 py-4 focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Type natural language input..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSubmit();
              }}
            />

            <button
              onClick={handleSubmit}
              className="bg-blue-500 text-white px-6 py-4 rounded-xl hover:bg-blue-600"
            >
              Convert
            </button>
          </div>
        </div>
      </footer>
    </>
  );
}

export default InputBar;