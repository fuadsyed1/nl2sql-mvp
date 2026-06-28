import { useState, useEffect } from "react";
import OutputCard from "./OutputCard";
import QueryResultCard from "./QueryResultCard";
import InputBar from "./InputBar";
import DatabaseWorkspace from "./DatabaseWorkspace";
import DatabaseWorkspaceCard from "./DatabaseWorkspaceCard";
import DatabaseSummaryCard from "./DatabaseSummaryCard";
import RelationshipReviewCard from "./RelationshipReviewCard";
import SetupSummaryCard from "./SetupSummaryCard";

function ConversionPage({
  target,
  messages,
  isProcessing,
  input,
  setInput,
  handleSubmit,
  currentConversationId,
  conversationTitle,
  onAssignmentResult,
  onDatabaseCreated,
  onSelectDatabase,
  activeDatabaseId,
  activeDatabaseSummary,
  relationshipsFinalized = false,
  onFinalizeRelationships = () => {},
}) {
  // Dynamic bottom padding so the last message always clears the (auto-growing)
  // input bar instead of hiding behind it.
  const [inputBarHeight, setInputBarHeight] = useState(160);
  // Header database selector opens the same DatabaseWorkspace overlay that the
  // input bar previously triggered (separate instance, only one open at a time).
  const [dbBrowserOpen, setDbBrowserOpen] = useState(false);
  const userId =
    typeof window !== "undefined" ? localStorage.getItem("user_id") : null;

  // Query input is only available once a database is active AND its
  // relationships are finalized. Relationship finalization is a later step;
  // for now relationshipsFinalized stays false, so the input stays hidden even
  // after a database is created.
  const canQuery = Boolean(activeDatabaseId) && relationshipsFinalized;
  // Show the summary/relationship-review area whenever a database is active and
  // the chat has no messages yet. It stays visible after finalizing (so the
  // review UI isn't removed) until the user sends their first query.
  const showSummary = Boolean(activeDatabaseId) && messages.length === 0;
  // No active database and a fresh (empty) chat -> show the upload workspace.
  const showWorkspaceCard = !activeDatabaseId && messages.length === 0;

  // Toggle between the summary card and the (placeholder) relationship review
  // card. Reset whenever the active database changes.
  const [reviewingRelationships, setReviewingRelationships] = useState(false);
  useEffect(() => {
    setReviewingRelationships(false);
  }, [activeDatabaseId]);

  return (
    <div className="flex flex-col h-full bg-gray-100">
      {dbBrowserOpen && (
        <DatabaseWorkspace
          userId={userId}
          activeDatabaseId={activeDatabaseId}
          onClose={() => setDbBrowserOpen(false)}
          onSelectDatabase={onSelectDatabase}
        />
      )}

      <header className="bg-white px-8 py-5 rounded-bl-3xl ml-2 flex items-center justify-between gap-6">
        <div className="min-w-0">
          <h2 className="text-2xl font-bold truncate">
            {conversationTitle || "New Conversion"}
          </h2>
          <p className="text-gray-500 text-sm">NL to {target}</p>
        </div>

        <button
          onClick={() => setDbBrowserOpen(true)}
          className="w-1/2 flex items-center justify-between gap-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-xl px-4 py-2.5 text-sm font-medium"
          title="Browse and select a database"
        >
          <span>🗄️ {activeDatabaseId ? `Database #${activeDatabaseId}` : "Databases"}</span>
          <span className="text-gray-400">▾</span>
        </button>
      </header>

      <section
        style={{ paddingBottom: canQuery ? inputBarHeight + 56 : 32 }}
        className="flex-1 overflow-y-auto p-8 mx-2 mt-2 mb-0 bg-white rounded-tl-3xl shadow-sm space-y-6 min-h-0">
        {showSummary &&
          (reviewingRelationships ? (
            <RelationshipReviewCard
              summary={activeDatabaseSummary}
              onBack={() => setReviewingRelationships(false)}
              onFinalize={onFinalizeRelationships}
              finalized={relationshipsFinalized}
            />
          ) : (
            <DatabaseSummaryCard
              summary={activeDatabaseSummary}
              onReviewRelationships={() => setReviewingRelationships(true)}
            />
          ))}

        {showWorkspaceCard && (
          <DatabaseWorkspaceCard
            userId={userId}
            conversationId={currentConversationId}
            onDatabaseCreated={onDatabaseCreated}
          />
        )}

        {!showSummary && !showWorkspaceCard && messages.length === 0 && !isProcessing && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center max-w-xl">
              <h3 className="text-3xl font-bold mb-3">
                What do you want to translate?
              </h3>

              <p className="text-gray-500">
                Example: show students with GPA above 3.5
              </p>
            </div>
          </div>
        )}

        {messages.map((msg, index) => (
          <div key={index} className="w-[87%] mx-auto">
            {msg.type === "user" && (
              <div className="flex justify-end mx-[12%]">
                <div className="bg-blue-500 text-white px-5 py-3 rounded-2xl w-fit max-w-[500px]">
                  {msg.text}
                </div>
              </div>
            )}

            {msg.type === "system" &&
              (msg.setup ? (
                <SetupSummaryCard setup={msg.setup} />
              ) : msg.result ? (
                <QueryResultCard result={msg.result} />
              ) : (
                <OutputCard output={msg.output} />
              ))}
          </div>
        ))}

        {isProcessing && (
          <div className="bg-white rounded-2xl shadow p-6 w-[87%] mx-auto">
            <h3 className="font-bold text-lg mb-4">Processing...</h3>

            <p className="text-gray-600">Reading natural language input...</p>
            <p className="text-gray-600">Creating semantic meaning...</p>
            <p className="text-gray-600">Generating {target} output...</p>
          </div>
        )}
      </section>

      {canQuery && (
        <InputBar
          input={input}
          setInput={setInput}
          handleSubmit={handleSubmit}
          currentConversationId={currentConversationId}
          onAssignmentResult={onAssignmentResult}
          onDatabaseCreated={onDatabaseCreated}
          onSelectDatabase={onSelectDatabase}
          activeDatabaseId={activeDatabaseId}
          onBarResize={setInputBarHeight}
        />
      )}
    </div>
  );
}

export default ConversionPage;