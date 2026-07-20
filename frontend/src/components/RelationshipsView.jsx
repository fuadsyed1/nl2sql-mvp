const SOURCE_LABELS = {
  pk_fk: "Database-declared PK/FK",
  user: "User-added",
  inferred: "Inferred",
  legacy_unknown: "Legacy — needs review",
  benchmark_trusted: "Benchmark",
};

function sourceLabel(src) {
  return SOURCE_LABELS[src] || (src ? String(src) : "—");
}

function RelationshipsView({ relationships = [] }) {
  if (!relationships.length) {
    return <p className="text-sm text-gray-500">No relationships detected.</p>;
  }

  return (
    <ul className="flex flex-col gap-2">
      {relationships.map((rel) => {
        const pct = Math.round((rel.confidence || 0) * 100);
        return (
          <li
            key={rel.relationship_id}
            className="flex items-center justify-between bg-gray-50 border border-gray-200 rounded-xl px-4 py-2 text-sm"
          >
            <span className="text-gray-800">
              <span className="font-medium">
                {rel.from_table}.{rel.from_column}
              </span>
              <span className="text-gray-400 mx-2">→</span>
              <span className="font-medium">
                {rel.to_table}.{rel.to_column}
              </span>
            </span>

            <span className="flex items-center gap-2">
              <span className="text-[10px] uppercase tracking-wide bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
                {sourceLabel(rel.source)}
              </span>
              {rel.confidence != null && (
                <span className="text-xs text-gray-500">{pct}%</span>
              )}
              {rel.confirmed ? (
                <span className="text-[10px] uppercase tracking-wide bg-green-100 text-green-700 px-1.5 py-0.5 rounded">
                  confirmed
                </span>
              ) : (
                <span className="text-[10px] uppercase tracking-wide bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">
                  suggested
                </span>
              )}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export default RelationshipsView;