function InputBar({
  input,
  setInput,
  handleSubmit,
  currentConversationId,
}) {
  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const userId = localStorage.getItem("user_id");

    if (!userId) {
      alert("Please sign in first.");
      return;
    }

    if (!currentConversationId) {
      alert("Please start a new chat before uploading a dataset.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("user_id", userId);
    formData.append("conversation_id", currentConversationId);

    const response = await fetch("http://localhost:8000/upload-csv", {
      method: "POST",
      body: formData,
    });

    const data = await response.json();

    if (!data.success) {
      alert(data.message || "File upload failed");
      return;
    }

    alert(`Uploaded: ${data.filename}`);
  };

  return (
    <footer className="fixed bottom-6 left-[13%] w-[87%] z-30 pointer-events-none">
      <div className="flex gap-3 w-[900px] mx-auto bg-white rounded-3xl shadow-xl p-3 pointer-events-auto">
        <label className="cursor-pointer bg-gray-100 px-5 py-4 rounded-xl hover:bg-gray-200">
          📎
          <input
            type="file"
            accept=".csv"
            onChange={handleFileUpload}
            className="hidden"
          />
        </label>

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