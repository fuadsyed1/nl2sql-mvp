import { useState, useEffect } from "react";

const API = "http://localhost:8000";

// Mode B / Mode C result panel: schema-only output. Shows detected tables,
// detected relationships, and the generated SQL per question. It deliberately
// shows NO result table — assignment mode never executes SQL for data rows.
function AssignmentResult({ result, onClose }) {
  const [graph, setGraph] = useState(null);

  // Pull the persisted schema graph so tables/relationships render exactly
  // like the database workspace (and confirm what was created).
  useEffect(() => {
    if (!result || !result.database_id) return;
    fetch(`${API}/database/${result.database_id}/graph`)
      .then((r) => r.json())
      .then((d) => setGraph(d.success ? d.database : null))
      .catch(() => setGraph(null));
  }, [result]);

  if (!result) return null;

  const tables = (graph && graph.tables) || result.tables || [];
  const relationships = (graph && graph.relationships) || result.relationships || [];
  const generated = result.generated_sql || [];

  const tableLine = (t) => {
    const name = t.table_name || t.name;
    const cols = (t.columns || []).map((c) => c.column_name || c.name || c);
    return `${name}(${cols.join(", ")})`;
  };

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
          <div>
            <h2 className="text-lg font-semibold text-gray-800">Assignment mode</h2>
            <p className="text-xs text-gray-400">
              Schema created and SQL generated — no data rows executed.
            </p>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
            ✕
          </button>
        </div>

        <div className="overflow-y-auto px-6 py-4 flex flex-col gap-6">
          <section>
            <h3 className="text-sm font-semibold text-gray-700 mb-2">
              Detected tables
            </h3>
            <ul className="flex flex-col gap-1">
              {tables.map((t, i) => (
                <li
                  key={i}
                  className="font-mono text-xs bg-gray-100 rounded-lg px-3 py-2 text-gray-700"
                >
                  {tableLine(t)}
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-gray-700 mb-2">
              Detected relationships
            </h3>
            {relationships.length === 0 ? (
              <p className="text-sm text-gray-400">None detected.</p>
            ) : (
              <ul className="flex flex-col gap-1">
                {relationships.map((r, i) => (
                  <li key={i} className="font-mono text-xs text-gray-600">
                    {r.from_table}.{r.from_column} → {r.to_table}.{r.to_column}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h3 className="text-sm font-semibold text-gray-700 mb-2">
              Generated SQL
            </h3>
            <div className="flex flex-col gap-4">
              {generated.map((q, i) => (
                <div key={i} className="border border-gray-200 rounded-xl p-3">
                  <p className="text-sm text-gray-800 mb-2">
                    <span className="text-gray-400">Q{i + 1}.</span> {q.question}
                  </p>
                  {q.sql ? (
                    <pre className="font-mono text-xs bg-gray-900 text-gray-100 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap">
                      {q.sql}
                    </pre>
                  ) : (
                    <p className="text-xs text-amber-600">
                      No SQL generated{q.reason ? ` (${q.reason})` : ""}.
                    </p>
                  )}
                  {q.relationships_used && q.relationships_used.length > 0 && (
                    <p className="text-xs text-gray-400 mt-2">
                      Joins:{" "}
                      {q.relationships_used
                        .map(
                          (j) =>
                            `${j.from_table}.${j.from_column}→${j.to_table}.${j.to_column}`
                        )
                        .join(", ")}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

export default AssignmentResult;
