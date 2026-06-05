function InputBar({ input, setInput, handleSubmit }) {
  return (
    <footer className="fixed bottom-6 left-[13%] w-[87%] z-30 pointer-events-none">
      <div className="flex gap-3 w-[900px] mx-auto bg-white rounded-3xl shadow-xl p-3 pointer-events-auto">
        <input
          className="flex-1 border border-gray-300 rounded-xl px-5 py-4 focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="Type natural language input..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSubmit();
          }}
        />

        <button
          onClick={handleSubmit}
          className="bg-blue-500 text-white px-6 py-4 rounded-xl hover:bg-blue-600"
        >
          Convert
        </button>
      </div>
    </footer>
  );
}

export default InputBar;