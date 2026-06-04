function InputBar({ input, setInput, handleSubmit }) {
  return (
    <footer className="bg-white p-5 border-t border-gray-200 sticky bottom-0 z-10">
      <div className="flex gap-3 max-w-4xl mx-auto">
        <input
          className="flex-1 border border-gray-300 rounded-xl px-5 py-4 focus:outline-none focus:ring-2 focus:ring-purple-500"
          placeholder="Type natural language input..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSubmit();
          }}
        />

        <button
          onClick={handleSubmit}
          className="bg-purple-600 text-white px-6 py-4 rounded-xl hover:bg-purple-700"
        >
          Convert
        </button>
      </div>
    </footer>
  );
}

export default InputBar;