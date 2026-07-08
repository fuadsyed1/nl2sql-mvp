import { useState } from "react";

import { API_BASE } from "../api";
import ContainmentResultCard from "./ContainmentResultCard";

// Modal overlay for Natural-Language Query Containment Checking. Fully
// self-contained: it takes two NL questions, POSTs them to
// /database/{activeDatabaseId}/check_containment, and renders the verdict via
// ContainmentResultCard. It does not touch the normal chat/query flow.
function ContainmentPanel({ activeDatabaseId, onClose }) {
  const [query1, setQuery1] = useState("");
  const [query2, setQuery2] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  const canCheck = query1.trim() && query2.trim() && !loading;

  const runCheck = async () => {
    if (!activeDatabaseId) {
      setError("No active database.");
      return;
    }
    if (!query1.trim() || !query2.trim()) {
      setError("Please enter both queries.");
      return;
    }
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const response = await fetch(
        `${API_BASE}/database/${activeDatabaseId}/check_containment`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query1, query2 }),
        }
      );
      const data = await response.json();
      if (data && data.message && data.containment_result === undefined) {
        // Backend early-return shape (e.g. database not found).
        setError(data.message);
      } else {
        setResult(data);
      }
    } catch (err) {
      setError(`Could not reach the server: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="bg-white w-full max-w-3xl max-h-[85vh] rounded-2xl shadow-2xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <div>
            <h2 className="text-lg font-semibold text-gray-800">
              Containment check
            </h2>
            <p className="text-xs text-gray-400">
              Is Query 1 contained in Query 2 on the current database?
            </p>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
            ✕
          </button>
        </div>

        <div className="overflow-y-auto px-6 py-4 flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <label className="text-sm font-semibold text-gray-700">Query 1</label>
            <textarea
              className="w-full border border-gray-300 rounded-xl px-4 py-2 min-h-[60px] focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
              placeholder="e.g. Which clubs have a budget greater than 5000?"
              value={query1}
              onChange={(e) => setQuery1(e.target.value)}
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-sm font-semibold text-gray-700">Query 2</label>
            <textarea
              className="w-full border border-gray-300 rounded-xl px-4 py-2 min-h-[60px] focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
              placeholder="e.g. Which clubs have a budget greater than 3000?"
              value={query2}
              onChange={(e) => setQuery2(e.target.value)}
            />
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={runCheck}
              disabled={!canCheck}
              className="bg-blue-500 text-white px-5 py-2.5 rounded-xl hover:bg-blue-600 disabled:opacity-60"
            >
              {loading ? "Checking…" : "Check containment"}
            </button>
            {error && <p className="text-sm text-red-500">{error}</p>}
          </div>

          {result && (
            <div className="border-t border-gray-200 pt-4">
              <ContainmentResultCard data={result} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default ContainmentPanel;
