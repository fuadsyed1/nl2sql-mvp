function SchemaView({ tables = [] }) {
  if (!tables.length) {
    return <p className="text-sm text-gray-500">No tables in this database.</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      {tables.map((table) => (
        <div
          key={table.table_id}
          className="border border-gray-200 rounded-xl overflow-hidden"
        >
          <div className="flex items-center justify-between bg-gray-50 px-4 py-2">
            <span className="font-semibold text-gray-800">{table.table_name}</span>
            <span className="text-xs text-gray-500">
              {table.row_count} rows · {(table.columns || []).length} columns
            </span>
          </div>

          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-200">
                <th className="px-4 py-1 font-medium">Column</th>
                <th className="px-4 py-1 font-medium">Type</th>
                <th className="px-4 py-1 font-medium">Nulls</th>
                <th className="px-4 py-1 font-medium">Unique</th>
                <th className="px-4 py-1 font-medium">Samples</th>
              </tr>
            </thead>
            <tbody>
              {(table.columns || []).map((col) => (
                <tr
                  key={col.column_id}
                  className="border-b border-gray-100 last:border-0"
                >
                  <td className="px-4 py-1">
                    <span className="text-gray-800">{col.column_name}</span>
                    {col.is_primary_key_candidate && (
                      <span className="ml-2 text-[10px] uppercase tracking-wide bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">
                        PK?
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-1 text-gray-600">{col.data_type}</td>
                  <td className="px-4 py-1 text-gray-600">{col.null_count}</td>
                  <td className="px-4 py-1 text-gray-600">{col.unique_count}</td>
                  <td className="px-4 py-1 text-gray-400 truncate max-w-[220px]">
                    {(col.sample_values || []).slice(0, 4).join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

export default SchemaView;