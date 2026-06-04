function Dashboard({ newConversion }) {
  return (
    <div className="p-10">
      <h2 className="text-3xl font-bold mb-4">Dashboard</h2>

      <button
        onClick={newConversion}
        className="bg-purple-600 text-white px-6 py-3 rounded-xl"
      >
        Start New Conversion
      </button>
    </div>
  );
}

export default Dashboard;