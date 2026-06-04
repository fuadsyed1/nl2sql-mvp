function AccountSettings({ target, setTarget }) {
  return (
    <div className="p-10">
      <h2 className="text-3xl font-bold mb-6">Account Settings</h2>

      <div className="bg-white rounded-2xl shadow p-6 max-w-2xl space-y-4">
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
      </div>
    </div>
  );
}

export default AccountSettings;