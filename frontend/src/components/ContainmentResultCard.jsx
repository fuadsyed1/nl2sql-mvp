import { useState } from "react";

// Presentational card for a /check_containment response. No fetching, no state
// beyond the collapsible SQL toggles — it renders whatever the backend returned.
// Wording deliberately says "on the current database" and never claims a full
// symbolic proof.

const RESULT_META = {
  contained_on_current_database: {
    label: "Contained on current database",
    tone: "bg-green-50 text-green-700 border-green-200",
  },
  equivalent_on_current_database: {
    label: "Equivalent on current database",
    tone: "bg-emerald-50 text-emerald-700 border-emerald-200",
  },
  not_contained: {
    label: "Not contained",
    tone: "bg-red-50 text-red-700 border-red-200",
  },
  unknown: {
    label: "Unknown",
    tone: "bg-amber-50 text-amber-700 border-amber-200",
  },
  not_checked_yet: {
    label: "Not checked yet",
    tone: "bg-gray-50 text-gray-600 border-gray-200",
  },
};

function RowsTable({ columns = [], rows = [] }) {
  if (!rows || rows.length === 0) {
    return <p className="text-xs text-gray-400">No rows.</p>;
  }
  return (
    <div className="overflow-x-auto border border-gray-200 rounded-lg">
      <table className="min-w-full text-xs">
        <thead className="bg-gray-100 text-gray-600">
          <tr>
            {columns.map((c, i) => (
              <th key={i} className="text-left font-semibold px-3 py-2">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} className="border-t border-gray-100">
              {row.map((cell, ci) => (
                <td key={ci} className="px-3 py-1.5 font-mono text-gray-700">
                  {cell === null ? <span className="text-gray-300">NULL</span> : String(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CollapsibleSql({ title, sql }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-gray-200 rounded-xl">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 rounded-xl"
      >
        <span>{title}</span>
        <span className="text-gray-400">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        sql ? (
          <pre className="font-mono text-xs bg-gray-900 text-gray-100 rounded-b-xl p-3 overflow-x-auto whitespace-pre-wrap">
            {sql}
          </pre>
        ) : (
          <p className="text-xs text-amber-600 px-3 pb-3">No SQL was generated.</p>
        )
      )}
    </div>
  );
}

function ContainmentResultCard({ data }) {
  if (!data) return null;

  const meta = RESULT_META[data.containment_result] || RESULT_META.unknown;
  const q1 = data.query1_result || {};
  const q2 = data.query2_result || {};

  const counterexampleCols =
    (data.counterexample_columns && data.counterexample_columns.length
      ? data.counterexample_columns
      : q1.execution_columns) || [];
  const counterexampleRows = data.counterexample_rows || [];
  const reverseRows = data.reverse_counterexample_rows || [];
  const warnings = data.warnings || [];

  // Result-specific secondary message (spec wording).
  let detail = null;
  if (data.containment_result === "not_contained") {
    detail = "These rows appear in Query 1 but not in Query 2.";
  } else if (data.containment_result === "contained_on_current_database") {
    detail = "No rows from Query 1 were missing from Query 2 on the current database.";
  } else if (data.containment_result === "equivalent_on_current_database") {
    detail = "Both queries returned the same rows on the current database.";
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Verdict badge */}
      <div className={`inline-flex w-fit items-center gap-2 border rounded-full px-4 py-1.5 text-sm font-semibold ${meta.tone}`}>
        {meta.label}
      </div>

      {/* Explanation + secondary detail */}
      {detail && <p className="text-sm text-gray-700">{detail}</p>}
      {data.explanation && (
        <p className="text-sm text-gray-500">{data.explanation}</p>
      )}

      {/* Warnings (mostly for unknown) */}
      {warnings.length > 0 && (
        <ul className="text-xs text-amber-600 list-disc list-inside">
          {warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}

      {/* Counterexample rows when not contained */}
      {data.containment_result === "not_contained" && (
        <section>
          <h4 className="text-sm font-semibold text-gray-700 mb-2">
            Counterexample rows (in Query 1, not in Query 2)
          </h4>
          <RowsTable columns={counterexampleCols} rows={counterexampleRows} />
        </section>
      )}

      {/* Reverse rows note when contained but not equivalent */}
      {data.containment_result === "contained_on_current_database" &&
        reverseRows.length > 0 && (
          <section>
            <p className="text-sm text-gray-700 mb-2">
              Query 2 has extra rows not returned by Query 1.
            </p>
            <RowsTable columns={counterexampleCols} rows={reverseRows} />
          </section>
        )}

      {/* Generated SQL (collapsible) */}
      <section className="flex flex-col gap-2">
        <h4 className="text-sm font-semibold text-gray-700">Generated SQL</h4>
        <CollapsibleSql title="SQL for Query 1" sql={q1.sql} />
        <CollapsibleSql title="SQL for Query 2" sql={q2.sql} />
      </section>

      {/* Limitations — never claim symbolic proof */}
      {data.limitations && (
        <p className="text-xs text-gray-400 border-t border-gray-100 pt-3">
          {data.limitations}
        </p>
      )}
    </div>
  );
}

export default ContainmentResultCard;
