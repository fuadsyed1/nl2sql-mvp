// Renders a database query result: SQL, Relational Algebra, row count, and a
// real table (styled like the dataset preview). Used for successful Mode-A
// queries; text-only messages (errors, assignment output, old saved messages)
// keep using OutputCard.
function QueryResultCard({ result }) {
  const {
    label,
    sql,
    relational_algebra: ra,
    columns = [],
    rows = [],
    row_count,
    note,
  } = result || {};

  const count = row_count != null ? row_count : rows.length;

  return (
    <div className="bg-white rounded-2xl shadow p-6 w-full flex flex-col gap-4">
      {label && (
        <p className="text-sm font-semibold text-gray-800">{label}</p>
      )}

      {sql && (
        <div>
          <h4 className="text-xs font-semibold text-gray-500 mb-1">SQL</h4>
          <pre className="bg-gray-50 border border-gray-200 text-gray-800 p-3 rounded-xl overflow-x-auto whitespace-pre-wrap text-xs">
            {sql}
          </pre>
        </div>
      )}

      {ra && (
        <div>
          <h4 className="text-xs font-semibold text-gray-500 mb-1">
            Relational Algebra
          </h4>
          <pre className="bg-gray-50 border border-gray-200 text-gray-800 p-3 rounded-xl overflow-x-auto whitespace-pre-wrap text-xs">
            {ra}
          </pre>
        </div>
      )}

      <div>
        <div className="flex items-center justify-between mb-1">
          <h4 className="text-xs font-semibold text-gray-500">Result</h4>
          <span className="text-xs text-gray-400">
            {count} {count === 1 ? "row" : "rows"}
          </span>
        </div>

        {note ? (
          <p className="text-sm text-amber-600">{note}</p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-gray-500">No rows returned.</p>
        ) : (
          <div className="border border-gray-200 rounded-xl overflow-auto max-h-[360px]">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-200 bg-gray-50 sticky top-0">
                  {columns.map((c, i) => (
                    <th key={i} className="px-4 py-1.5 font-medium whitespace-nowrap">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, ri) => {
                  const cells = Array.isArray(r) ? r : columns.map((c) => r[c]);
                  return (
                    <tr key={ri} className="border-b border-gray-100 last:border-0">
                      {cells.map((cell, ci) => (
                        <td
                          key={ci}
                          className="px-4 py-1.5 text-gray-700 whitespace-nowrap"
                        >
                          {cell === null || cell === undefined ? "-" : String(cell)}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default QueryResultCard;
