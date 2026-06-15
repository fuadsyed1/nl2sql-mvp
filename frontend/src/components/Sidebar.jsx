function Sidebar({
  target,
  conversions,
  setActivePage,
  newConversion,
  loadConversationMessages,
  user,
  setUser,
}) {
  const handleLogout = () => {
    localStorage.removeItem("user_id");
    localStorage.removeItem("username");
    setUser(null);
  };

  const deleteConversation = async (conversationId) => {
    try {
      await fetch(`http://localhost:8000/conversation/${conversationId}`, {
        method: "DELETE",
      });

      window.location.reload();
    } catch (err) {
      console.error("Failed to delete conversation:", err);
    }
  };

  return (
    <aside className="w-[13%] bg-white border-r border-gray-200 flex flex-col">
      <div className="p-6">
        <h1 className="text-2xl font-bold text-blue-600">NL Translator</h1>
        <p className="text-sm text-gray-500 mt-1">NL to {target}</p>

        {user && (
          <p className="text-xs text-gray-400 mt-2">
            Signed in as {user.username}
          </p>
        )}
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
          + New Chat
        </button>
      </nav>

      <div className="px-4 mt-4 flex-1 overflow-y-auto">
        <h2 className="text-sm font-semibold text-gray-500 mb-3">
          Recent Chats
        </h2>

        {conversions.length === 0 ? (
          <p className="text-sm text-gray-400 px-4">No previous chats</p>
        ) : (
          <div className="space-y-2">
            {conversions.map((item) => (
              <div
                key={item.conversation_id}
                className="flex items-center gap-2 group"
              >
                <button
                  onClick={() =>
                    loadConversationMessages(item.conversation_id)
                  }
                  className="flex-1 text-left px-4 py-2 rounded-lg text-gray-700 hover:bg-gray-100 truncate"
                >
                  {item.title || "New Chat"}
                </button>

                <button
                  onClick={() =>
                    deleteConversation(item.conversation_id)
                  }
                  className="text-red-500 hover:text-red-700 px-2 text-lg font-bold"
                  title="Delete chat"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="p-4 space-y-2">
        <button
          onClick={() => setActivePage("account")}
          className="w-full text-left px-4 py-3 rounded-lg hover:bg-blue-50"
        >
          Account Settings
        </button>

        <button
          onClick={handleLogout}
          className="w-full text-left px-4 py-3 rounded-lg bg-red-500 text-white hover:bg-red-600"
        >
          Sign Out
        </button>
      </div>
    </aside>
  );
}

export default Sidebar;