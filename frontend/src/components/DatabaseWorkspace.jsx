import { useState, useEffect } from "react";
import SchemaView from "./SchemaView";
import RelationshipsView from "./RelationshipsView";

const API = "http://localhost:8000";

function DatabaseWorkspace({ userId, databaseId = null, onClose }) {
  const [list, setList] = useState([]);
  const [activeId, setActiveId] = useState(databaseId);
  const [graph, setGraph] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Load the user's databases for the switcher.
  useEffect(() => {
    if (!userId) return;
    fetch(`${API}/databases/${userId}`)
      .then((r) => r.json())
      .then((d) => {
        const dbs = d.databases || [];
        setList(dbs);
        setActiveId((cur) => cur || (dbs[0] && dbs[0].database_id) || null);
      })
      .catch((e) => setError(`Could not load databases: ${e.message}`));
  }, [userId]);

  // Load the active database's graph (schema + relationships in one call).
  useEffect(() => {
    if (!activeId) {
      setGraph(null);
      return;
    }
    setLoading(true);
    setError("");
    fetch(`${API}/database/${activeId}/graph`)
      .then((r) => r.json())
      .then((d) => {
        if (!d.success) {
          setError(d.message || "Failed to load database.");
          setGraph(null);
        } else {
          setGraph(d.database);
        }
      })
      .catch((e) => setError(`Could not load database: ${e.message}`))
      .finally(() => setLoading(false));
  }, [activeId]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="bg-white w-full max-w-3xl max-h-[85vh] rounded-2xl shadow-2xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-800">Database workspace</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
            ✕
          </button>
        </div>

        {list.length > 0 && (
          <div className="px-6 py-3 border-b border-gray-100">
            <select
              value={activeId || ""}
              onChange={(e) => setActiveId(Number(e.target.value))}
              className="w-full border border-gray-300 rounded-xl px-4 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {list.map((db) => {
                const names = (db.tables || [])
                  .map((t) => t.table_name)
                  .join(", ");

                return (
                  <option key={db.database_id} value={db.database_id}>
                    Database {db.database_id}: {`{${names}}`}
                  </option>
                );
              })}
            </select>
          </div>
        )}

        <div className="overflow-y-auto px-6 py-4">
          {error && <p className="text-sm text-red-500 mb-3">{error}</p>}
          {loading && <p className="text-sm text-gray-500">Loading…</p>}
          {!loading && !graph && !error && (
            <p className="text-sm text-gray-500">
              No database selected. Upload CSVs to create one.
            </p>
          )}

          {graph && (
            <div className="flex flex-col gap-6">
              <div>
                <p className="text-sm text-gray-500">Workspace</p>
                <p className="text-base font-semibold text-gray-800">
                  {graph.name}{" "}
                  <span className="text-gray-400 font-normal">
                    #{graph.database_id}
                  </span>
                </p>
                <p className="text-xs text-gray-400">
                  {(graph.tables || []).length} tables ·{" "}
                  {(graph.relationships || []).length} relationships
                </p>
              </div>

              <section>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Schema</h3>
                <SchemaView tables={graph.tables} />
              </section>

              <section>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">
                  Detected relationships
                </h3>
                <RelationshipsView relationships={graph.relationships} />
              </section>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default DatabaseWorkspace;