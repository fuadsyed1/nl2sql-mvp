function Sidebar({
  target,
  conversions,
  setActivePage,
  newConversion,
}) {
  return (
    <aside className="w-[13%] bg-white border-r border-gray-200 flex flex-col">
      <div className="p-6">
        <h1 className="text-2xl font-bold text-blue-600">NL Translator</h1>
        <p className="text-sm text-gray-500 mt-1">NL to {target}</p>
      </div>

      <nav className="p-4 space-y-2">
        <button
          onClick={() => setActivePage("dashboard")}
          className="w-full text-left px-4 py-3 rounded-lg hover:bg-blue-50"
        >
          Dashboard
        </button>

        <button
          onClick={newConversion}
          className="w-full text-left px-4 py-3 rounded-lg bg-blue-500 text-white hover:bg-blue-600"
        >
          + New Conversion
        </button>
      </nav>

      <div className="px-4 mt-4 flex-1 overflow-y-auto">
        <h2 className="text-sm font-semibold text-gray-500 mb-3">
          Recent Sessions
        </h2>

        {conversions.length === 0 ? (
          <p className="text-sm text-gray-400 px-4">
            No previous conversions
          </p>
        ) : (
          <div className="space-y-2">
            {conversions.map((item) => (
              <button
                key={item.id}
                onClick={() => setActivePage("conversion")}
                className="w-full text-left px-4 py-2 rounded-lg text-gray-700 hover:bg-gray-100"
              >
                {item.title}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="p-4">
        <button
          onClick={() => setActivePage("account")}
          className="w-full text-left px-4 py-3 rounded-lg hover:bg-blue-50"
        >
          Account Settings
        </button>
      </div>
    </aside>
  );
}

export default Sidebar;