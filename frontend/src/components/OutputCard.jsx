function OutputCard({ output }) {
  return (
    <div className="bg-white rounded-2xl shadow p-6 max-w-3xl">
      <h3 className="font-bold text-lg mb-2">Output</h3>

      <pre className="bg-gray-900 text-green-300 p-4 rounded-xl overflow-x-auto whitespace-pre-wrap">
        {output}
      </pre>
    </div>
  );
}

export default OutputCard;