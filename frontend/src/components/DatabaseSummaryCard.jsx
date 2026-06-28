import { useState } from "react";
import { API_BASE } from "../api";

// Shown in the chat area after a database is created/loaded but before its
// relationships are finalized. Read-only for now: lists tables (clickable for a
// schema/sample preview) and offers an entry point into Relationship Review.
// Query input stays hidden until relationships are finalized (a later step).
function DatabaseSummaryCard({ summary, onReviewRelationships = () => {} }) {
  const { database_id, name, tables } = summary || {};
  const tableList = Array.isArray(tables) ? tables : [];

  const [selectedTable, setSelectedTable] = useState(null);
  const [graph, setGraph] = useState(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState("");

  // Lazily fetch the database graph (schema + sample values) the first time a
  // table is clicked, then reuse it for subsequent selections.
  const ensureGraph = () => {
    if (graph || graphLoading || database_id == null) return;
    setGraphLoading(true);
    setGraphError("");
    fetch(`${API_BASE}/database/${database_id}/graph`)
      .then((r) => r.json())
      .then((d) => {
        if (!d.success) setGraphError(d.message || "Could not load table details.");
        else setGraph(d.database);
      })
      .catch((e) => setGraphError(`Could not load table details: ${e.message}`))
      .finally(() => setGraphLoading(false));
  };

  const handleSelectTable = (t) => {
    setSelectedTable(t);
    ensureGraph();
  };

  const selectedColumns =
    selectedTable && graph
      ? ((graph.tables || []).find((t) => t.table_name === selectedTable)
          ?.columns || [])
      : [];

  return (
    <div className="h-full flex items-center justify-center">
      <div className="w-[80%] max-w-3xl bg-white border border-gray-200 rounded-2xl shadow-lg flex flex-col">
        <div className="px-6 py-5 border-b border-gray-100">
          <h2 className="text-2xl font-bold text-gray-800">Database ready</h2>
          <p className="text-gray-500 text-sm mt-1">
            Review the database below. Relationship review is the next step.
          </p>
        </div>

        <div className="px-6 py-5 flex flex-col gap-4">
          <div>
            <p className="text-xs font-semibold text-gray-500">Name</p>
            <p className="text-base font-semibold text-gray-800">
              {name || `Database ${database_id}`}{" "}
              {database_id != null && (
                <span className="text-gray-400 font-normal">#{database_id}</span>
              )}
            </p>
          </div>

          <div>
            <p className="text-xs font-semibold text-gray-500 mb-1">
              Tables{tableList.length > 0 ? ` (${tableList.length})` : ""}
            </p>
            {tableList.length > 0 ? (
              <ul className="flex flex-wrap gap-2">
                {tableList.map((t, i) => (
                  <li key={`${t}-${i}`}>
                    <button
                      onClick={() => handleSelectTable(t)}
                      className={`text-sm rounded-lg px-3 py-1.5 border transition-colors ${
                        selectedTable === t
                          ? "bg-blue-50 border-blue-300 text-blue-700"
                          : "bg-gray-50 border-gray-200 text-gray-700 hover:bg-gray-100"
                      }`}
                    >
                      {t}
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-gray-400">Table details unavailable.</p>
            )}
          </div>

          {/* Table preview (schema + sample values from the graph endpoint) */}
          {selectedTable && (
            <div className="border border-gray-200 rounded-xl p-4">
              <p className="text-sm font-semibold text-gray-800 mb-2">
                Table Preview: {selectedTable}
              </p>

              {graphLoading && (
                <p className="text-sm text-gray-500">Loading…</p>
              )}
              {graphError && (
                <p className="text-sm text-amber-600">{graphError}</p>
              )}

              {!graphLoading && !graphError && (
                selectedColumns.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-gray-500 border-b border-gray-200">
                          <th className="px-3 py-1 font-medium">Column</th>
                          <th className="px-3 py-1 font-medium">Type</th>
                          <th className="px-3 py-1 font-medium">Samples</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedColumns.map((col, ci) => (
                          <tr
                            key={col.column_id ?? ci}
                            className="border-b border-gray-100 last:border-0"
                          >
                            <td className="px-3 py-1 text-gray-800">
                              {col.column_name}
                            </td>
                            <td className="px-3 py-1 text-gray-600">
                              {col.data_type}
                            </td>
                            <td className="px-3 py-1 text-gray-400 truncate max-w-[260px]">
                              {(col.sample_values || []).slice(0, 4).join(", ")}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-sm text-gray-400">
                    Table preview not available.
                  </p>
                )
              )}
            </div>
          )}

          <div>
            <button
              onClick={onReviewRelationships}
              className="bg-blue-500 text-white text-sm px-5 py-2.5 rounded-xl hover:bg-blue-600"
            >
              Review Relationships
            </button>
          </div>
        </div>

        <div className="px-6 py-3 border-t border-gray-100">
          <p className="text-sm text-gray-500">
            Active Database:{" "}
            <span className="font-medium text-gray-700">
              {name || `Database ${database_id}`}
              {database_id != null ? ` #${database_id}` : ""}
            </span>
          </p>
        </div>
      </div>
    </div>
  );
}

export default DatabaseSummaryCard;
