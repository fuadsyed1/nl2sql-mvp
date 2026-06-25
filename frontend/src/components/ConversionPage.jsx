import OutputCard from "./OutputCard";
import InputBar from "./InputBar";

function ConversionPage({
  target,
  messages,
  isProcessing,
  input,
  setInput,
  handleSubmit,
  currentConversationId,
  onAssignmentResult,
}) {
  return (
    <div className="flex flex-col h-screen bg-gray-100">
      <header className="bg-white px-8 py-5 rounded-bl-3xl ml-2">
        <h2 className="text-2xl font-bold">New Conversion</h2>
        <p className="text-gray-500 text-sm">NL to {target}</p>
      </header>

      <section className="flex-1 overflow-y-auto p-8 pb-40 mx-2 mt-2 mb-0 bg-white rounded-tl-3xl shadow-sm space-y-6 min-h-0">
        {messages.length === 0 && !isProcessing && (
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

            {msg.type === "system" && <OutputCard output={msg.output} />}
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

      <InputBar
        input={input}
        setInput={setInput}
        handleSubmit={handleSubmit}
        currentConversationId={currentConversationId}
        onAssignmentResult={onAssignmentResult}
      />
    </div>
  );
}

export default ConversionPage;