import { API_BASE } from "../api";
import { useState } from "react";

function AccountSettings({ target, setTarget, user, onFactoryReset }) {
  const [showResetBox, setShowResetBox] = useState(false);
  const [resetText, setResetText] = useState("");
  const [loading, setLoading] = useState(false);

  const handleFactoryReset = async () => {
    if (resetText !== "RESET") return;

    setLoading(true);
    console.log("USER:", user)
    try {
      const res = await fetch(
        `${API_BASE}/user/${user.user_id}/factory-reset`,
        {
          method: "DELETE",
        }
      );

      const data = await res.json();

      if (data.success) {
        setResetText("");
        setShowResetBox(false);

        if (onFactoryReset) {
          onFactoryReset();
        }

        alert("Factory reset completed.");
      } else {
        alert("Factory reset failed.");
      }
    } catch (error) {
      console.error(error);
      alert("Factory reset failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-10">
      <h2 className="text-3xl font-bold mb-6">Account Settings</h2>

      <div className="bg-white rounded-2xl shadow p-6 max-w-2xl space-y-6">
        <div>
          <label className="text-sm text-gray-500">Default Target</label>

          <select
            className="w-full border rounded-lg px-4 py-3 mt-1"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
          >
            <option value="SQL">SQL</option>
            <option value="Hylos">Hylos</option>
          </select>
        </div>

        <div className="border-t pt-6">
          <h3 className="text-lg font-bold text-red-600">Danger Zone</h3>

          <p className="text-sm text-gray-600 mt-2">
            Factory Reset will delete all conversations, queries, datasets,
            uploaded files, and chat history. This action cannot be undone.
          </p>

          {!showResetBox ? (
            <button
              onClick={() => setShowResetBox(true)}
              className="mt-4 bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg font-medium"
            >
              Factory Reset
            </button>
          ) : (
            <div className="mt-4 bg-red-50 border border-red-200 rounded-xl p-4">
              <p className="text-sm font-medium text-red-700">
                Type RESET to confirm factory reset.
              </p>

              <input
                className="w-full border rounded-lg px-4 py-2 mt-3"
                value={resetText}
                onChange={(e) => setResetText(e.target.value)}
                placeholder="Type RESET"
              />

              <div className="flex gap-3 mt-4">
                <button
                  onClick={() => {
                    setShowResetBox(false);
                    setResetText("");
                  }}
                  className="px-4 py-2 rounded-lg border"
                  disabled={loading}
                >
                  Cancel
                </button>

                <button
                  onClick={handleFactoryReset}
                  disabled={resetText !== "RESET" || loading}
                  className={`px-4 py-2 rounded-lg text-white font-medium ${
                    resetText === "RESET" && !loading
                      ? "bg-red-600 hover:bg-red-700"
                      : "bg-red-300 cursor-not-allowed"
                  }`}
                >
                  {loading ? "Resetting..." : "Factory Reset"}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default AccountSettings;
