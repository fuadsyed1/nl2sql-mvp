import { useState, useEffect } from "react";
import SchemaView from "./SchemaView";
import RelationshipsView from "./RelationshipsView";

import { API_BASE } from "../api";

function DatabaseWorkspace({ userId, activeDatabaseId = null, onClose, onSelectDatabase = () => {} }) {
  const [graph, setGraph] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Read-only: this modal only describes the current chat's active database. It
  // never switches databases — loading happens through the Database Workspace
  // card before query mode.

  // Load the active database. Small mode: full graph (schema + relationships),
  // unchanged. Large mode: a lightweight summary only (no full graph build).
  useEffect(() => {
    if (!activeDatabaseId) {
      setGraph(null);
      setSummary(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    setGraph(null);
    setSummary(null);

    fetch(`${API_BASE}/database/${activeDatabaseId}/meta`)
      .then((r) => r.json())
      .then((meta) => {
        if (cancelled) return null;
        if (!meta.success) {
          setError(meta.message || "Failed to load database.");
          return null;
        }
        if (meta.mode === "large") {
          return fetch(
            `${API_BASE}/database/${activeDatabaseId}/graph?summary=true`
          )
            .then((r) => r.json())
            .then((d) => {
              if (cancelled) return;
              if (!d.success)
                setError(d.message || "Failed to load database.");
              else setSummary({ name: meta.name, ...d });
            });
        }
        // Small mode: existing full-graph behavior, unchanged.
        return fetch(`${API_BASE}/database/${activeDatabaseId}/graph`)
          .then((r) => r.json())
          .then((d) => {
            if (cancelled) return;
            if (!d.success) {
              setError(d.message || "Failed to load database.");
              setGraph(null);
            } else {
              setGraph(d.database);
            }
          });
      })
      .catch((e) => {
        if (!cancelled) setError(`Could not load database: ${e.message}`);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activeDatabaseId]);

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
          <h2 className="text-lg font-semibold text-gray-800">Active database</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
            ✕
          </button>
        </div>

        <div className="overflow-y-auto px-6 py-4">
          {error && <p className="text-sm text-red-500 mb-3">{error}</p>}
          {loading && <p className="text-sm text-gray-500">Loading…</p>}
          {!loading && !graph && !summary && !error && (
            <p className="text-sm text-gray-500">
              No active database selected.
            </p>
          )}

          {summary && (
            <div className="flex flex-col gap-4">
              <div>
                <p className="text-sm text-gray-500">Workspace</p>
                <p className="text-base font-semibold text-gray-800">
                  {summary.name}{" "}
                  <span className="text-gray-400 font-normal">
                    #{summary.database_id}
                  </span>
                  <span className="ml-2 text-[10px] uppercase tracking-wide bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded align-middle">
                    {summary.mode}
                  </span>
                </p>
                <p className="text-xs text-gray-400">
                  {summary.table_count} tables ·{" "}
                  {summary.relationship_count} relationships
                </p>
              </div>

              <p className="text-sm text-gray-600 border border-gray-200 rounded-xl p-3 bg-gray-50">
                {summary.message}
              </p>
            </div>
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
