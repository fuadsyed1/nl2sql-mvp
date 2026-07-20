import { useState, useEffect } from "react";
import { API_BASE } from "../api";

// Shown in the chat area after a database is created/loaded. Lists tables
// (clickable for a column preview) and offers an entry point into Relationship
// Review.
//
// Two modes (Phase 1):
//   - small: existing behavior — table chips from the summary, preview columns
//     come from the full /graph (loaded once).
//   - large: scalable — a searchable/paginated table list from /tables, and
//     columns are loaded lazily per table from /table/{name}/columns. The full
//     /graph is never fetched for large databases.
function DatabaseSummaryCard({ summary, onReviewRelationships = () => {} }) {
  const { database_id, name, tables } = summary || {};
  const tableList = Array.isArray(tables) ? tables : [];

  const LIMIT = 50;

  // Database mode/metadata.
  const [meta, setMeta] = useState(null);
  useEffect(() => {
    if (database_id == null) return;
    let cancelled = false;
    fetch(`${API_BASE}/database/${database_id}/meta`)
      .then((r) => r.json())
      .then((d) => {
        if (!cancelled && d.success) setMeta(d);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [database_id]);
  const isLarge = meta?.mode === "large";

  // Shared selection + column preview.
  const [selectedTable, setSelectedTable] = useState(null);
  const [previewCols, setPreviewCols] = useState([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");

  // Small-mode graph cache (schema + sample values).
  const [graph, setGraph] = useState(null);

  // Large-mode paginated table list.
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [pageData, setPageData] = useState(null);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState("");

  useEffect(() => {
    if (!isLarge || database_id == null) return;
    let cancelled = false;
    (async () => {
      setListLoading(true);
      setListError("");
      try {
        const d = await (
          await fetch(
            `${API_BASE}/database/${database_id}/tables?q=${encodeURIComponent(
              query
            )}&limit=${LIMIT}&offset=${offset}`
          )
        ).json();
        if (cancelled) return;
        if (d.success) setPageData(d);
        else setListError(d.message || "Could not load tables.");
      } catch (e) {
        if (!cancelled) setListError(`Could not load tables: ${e.message}`);
      } finally {
        if (!cancelled) setListLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isLarge, database_id, query, offset]);

  const colsFromGraph = (g, t) =>
    (g?.tables || []).find((x) => x.table_name === t)?.columns || [];

  // Small mode: load columns from the full graph (fetched once).
  const selectSmall = (t) => {
    setSelectedTable(t);
    setPreviewError("");
    if (graph) {
      setPreviewCols(colsFromGraph(graph, t));
      return;
    }
    setPreviewLoading(true);
    fetch(`${API_BASE}/database/${database_id}/graph`)
      .then((r) => r.json())
      .then((d) => {
        if (d.success) {
          setGraph(d.database);
          setPreviewCols(colsFromGraph(d.database, t));
        } else {
          setPreviewError(d.message || "Could not load table details.");
        }
      })
      .catch((e) =>
        setPreviewError(`Could not load table details: ${e.message}`)
      )
      .finally(() => setPreviewLoading(false));
  };

  // Large mode: load columns lazily for just this table.
  const selectLarge = (t) => {
    setSelectedTable(t);
    setPreviewError("");
    setPreviewCols([]);
    setPreviewLoading(true);
    fetch(
      `${API_BASE}/database/${database_id}/table/${encodeURIComponent(t)}/columns`
    )
      .then((r) => r.json())
      .then((d) => {
        if (d.success) setPreviewCols(d.columns || []);
        else setPreviewError(d.message || "Could not load columns.");
      })
      .catch((e) => setPreviewError(`Could not load columns: ${e.message}`))
      .finally(() => setPreviewLoading(false));
  };

  const total = isLarge ? pageData?.total ?? meta?.table_count ?? 0 : tableList.length;
  const pageTables = pageData?.tables || [];

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
              {isLarge && (
                <span className="ml-2 text-[10px] uppercase tracking-wide bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded align-middle">
                  large
                </span>
              )}
            </p>
          </div>

          <div>
            <p className="text-xs font-semibold text-gray-500 mb-1">
              Tables{total ? ` (${total})` : ""}
            </p>

            {isLarge ? (
              <div className="flex flex-col gap-2">
                <input
                  value={query}
                  onChange={(e) => {
                    setQuery(e.target.value);
                    setOffset(0);
                  }}
                  placeholder="Search tables..."
                  className="w-full border border-gray-300 rounded-xl px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />

                {listLoading && (
                  <p className="text-sm text-gray-500">Loading…</p>
                )}
                {listError && (
                  <p className="text-sm text-amber-600">{listError}</p>
                )}

                {!listLoading && !listError && pageTables.length === 0 && (
                  <p className="text-sm text-gray-400">No tables found.</p>
                )}

                {!listLoading && !listError && pageTables.length > 0 && (
                  <ul className="flex flex-wrap gap-2 max-h-[220px] overflow-y-auto">
                    {pageTables.map((t) => (
                      <li key={t.table_id ?? t.table_name}>
                        <button
                          onClick={() => selectLarge(t.table_name)}
                          className={`text-sm rounded-lg px-3 py-1.5 border transition-colors ${
                            selectedTable === t.table_name
                              ? "bg-blue-50 border-blue-300 text-blue-700"
                              : "bg-gray-50 border-gray-200 text-gray-700 hover:bg-gray-100"
                          }`}
                        >
                          {t.table_name}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}

                {total > LIMIT && (
                  <div className="flex items-center justify-between text-xs text-gray-500">
                    <span>
                      Showing {Math.min(offset + 1, total)}–
                      {Math.min(offset + LIMIT, total)} of {total}
                    </span>
                    <span className="flex gap-2">
                      <button
                        onClick={() => setOffset(Math.max(0, offset - LIMIT))}
                        disabled={offset === 0}
                        className="border border-gray-200 rounded-lg px-3 py-1 disabled:opacity-50"
                      >
                        Prev
                      </button>
                      <button
                        onClick={() => setOffset(offset + LIMIT)}
                        disabled={offset + LIMIT >= total}
                        className="border border-gray-200 rounded-lg px-3 py-1 disabled:opacity-50"
                      >
                        Next
                      </button>
                    </span>
                  </div>
                )}
              </div>
            ) : tableList.length > 0 ? (
              <ul className="flex flex-wrap gap-2">
                {tableList.map((t, i) => (
                  <li key={`${t}-${i}`}>
                    <button
                      onClick={() => selectSmall(t)}
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

          {/* Table preview (columns; sample values when available) */}
          {selectedTable && (
            <div className="border border-gray-200 rounded-xl p-4">
              <p className="text-sm font-semibold text-gray-800 mb-2">
                Table Preview: {selectedTable}
              </p>

              {previewLoading && (
                <p className="text-sm text-gray-500">Loading…</p>
              )}
              {previewError && (
                <p className="text-sm text-amber-600">{previewError}</p>
              )}

              {!previewLoading &&
                !previewError &&
                (previewCols.length > 0 ? (
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
                        {previewCols.map((col, ci) => (
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
                ))}
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
