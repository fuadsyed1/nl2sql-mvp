// A one-time system/setup message added to the chat when relationships are
// finalized. Renders as an assistant-style card in the message stream (left
// aligned, ~70% width — not a centered full-width setup card, not a user
// bubble). Frontend-only; not persisted.
function SetupSummaryCard({ setup }) {
  const {
    database_id,
    name,
    tables = [],
    relationships = [],
  } = setup || {};

  return (
    <div className="w-full max-w-[70%] mr-auto bg-white border border-gray-200 rounded-2xl shadow-sm p-5 flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-wide bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">
          System
        </span>
        <span className="text-sm font-semibold text-gray-800">
          Database created: {name || `Database ${database_id}`}
          {database_id != null ? ` #${database_id}` : ""}
        </span>
      </div>

      <div>
        <p className="text-xs font-semibold text-gray-500 mb-1">
          Tables{tables.length ? ` (${tables.length})` : ""}
        </p>
        {tables.length ? (
          <div className="flex flex-wrap gap-1.5">
            {tables.map((t, i) => (
              <span
                key={`${t}-${i}`}
                className="text-xs text-gray-700 bg-gray-50 border border-gray-200 rounded-lg px-2 py-1"
              >
                {t}
              </span>
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-400">—</p>
        )}
      </div>

      <div>
        <p className="text-xs font-semibold text-gray-500 mb-1">
          Relationships finalized{relationships.length ? ` (${relationships.length})` : ""}
        </p>
        {relationships.length ? (
          <ul className="flex flex-col gap-1">
            {relationships.map((r, i) => (
              <li key={i} className="text-xs text-gray-700">
                <span className="font-medium">
                  {r.from_table}.{r.from_column}
                </span>
                <span className="text-gray-400 mx-1">→</span>
                <span className="font-medium">
                  {r.to_table}.{r.to_column}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-gray-500">none selected</p>
        )}
      </div>

      <div className="pt-2 border-t border-gray-100">
        <p className="text-sm text-gray-500">
          System loaded this database in the current chat.
        </p>
        <p className="text-sm font-medium text-gray-700">Ready for SQL queries.</p>
      </div>
    </div>
  );
}

export default SetupSummaryCard;
