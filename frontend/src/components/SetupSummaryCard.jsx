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

      <div className="text-sm text-gray-600">
        <p>Database loaded successfully. Metadata created.</p>
        <p>Tables: {tables.length}</p>
        <p>Relationships saved in metadata: {relationships.length}</p>
      </div>

      <div className="pt-2 border-t border-gray-100">
        <p className="text-sm font-medium text-gray-700">Ready for SQL queries.</p>
      </div>
    </div>
  );
}

export default SetupSummaryCard;
