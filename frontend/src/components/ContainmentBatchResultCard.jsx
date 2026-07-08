import { useState } from "react";

// Presentational card for a /check_containment_batch response. Optimized for
// readability in the chat: a short natural-language summary and a compact
// relationship table come first; generated SQL, pairwise details, and
// counterexample rows are all collapsed by default. Wording uses
// "broader / narrower / contained in / contains / equivalent / incomparable /
// empty-result query" - no single "main" query - and never claims a symbolic
// proof. No modal.

const qShort = (ids) => (ids || []).map((i) => `Q${i}`).join(", ");
const qLong = (ids) => (ids || []).map((i) => `Query ${i}`).join(", ");
const DASH = "-";

function summarySentence(s, total) {
  const id = s.query_id;
  if (s.empty_result) {
    return `Query ${id} returned no rows, so it is an empty-result query and is contained in the others on the current database.`;
  }
  const clauses = [];
  if (s.contained_in.length) clauses.push(`is contained in ${qLong(s.contained_in)}`);
  if (s.contains.length) clauses.push(`contains ${qLong(s.contains)}`);
  if (s.equivalent_to.length) clauses.push(`is equivalent to ${qLong(s.equivalent_to)}`);
  if (s.incomparable_with.length)
    clauses.push(`is incomparable with ${qLong(s.incomparable_with)}`);
  if (s.unknown_with.length)
    clauses.push(`could not be compared with ${qLong(s.unknown_with)}`);

  if (!clauses.length) {
    return `Query ${id} has no containment relationship with the other tested queries on the current database.`;
  }

  const others = total - 1;
  let prefix = "";
  if (s.contains.length && !s.contained_in.length) {
    prefix =
      s.contains.length >= others
        ? "is the broadest query among the tested queries; it "
        : "is a broader query; it ";
  } else if (s.contained_in.length && !s.contains.length) {
    prefix = "is a narrower query; it ";
  }
  return `Query ${id} ${prefix}${clauses.join(" and ")}.`;
}

function noteFor(s, total) {
  if (s.empty_result) return "empty-result query";
  const others = total - 1;
  if (s.contains.length && !s.contained_in.length)
    return s.contains.length >= others
      ? "broadest among tested queries"
      : `broader than ${qShort(s.contains)}`;
  if (s.contained_in.length && !s.contains.length)
    return `narrower than ${qShort(s.contained_in)}`;
  if (s.contains.length && s.contained_in.length)
    return `broader than ${qShort(s.contains)}; narrower than ${qShort(s.contained_in)}`;
  if (s.equivalent_to.length) return `equivalent to ${qShort(s.equivalent_to)}`;
  if (s.incomparable_with.length) return "incomparable";
  return DASH;
}

function RowsTable({ columns = [], rows = [] }) {
  if (!rows || rows.length === 0) return null;
  return (
    <div className="overflow-x-auto border border-gray-200 rounded-lg mt-1">
      <table className="min-w-full text-xs">
        <thead className="bg-gray-100 text-gray-600">
          <tr>
            {columns.map((c, i) => (
              <th key={i} className="text-left font-semibold px-3 py-1.5">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} className="border-t border-gray-100">
              {row.map((cell, ci) => (
                <td key={ci} className="px-3 py-1 font-mono text-gray-700">
                  {cell === null ? <span className="text-gray-300">NULL</span> : String(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CollapsibleSql({ sql }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-1">
      <button
        onClick={() => setOpen((o) => !o)}
        className="text-xs text-blue-600 hover:underline"
      >
        {open ? "Hide SQL" : "Show SQL"}
      </button>
      {open &&
        (sql ? (
          <pre className="font-mono text-xs bg-gray-900 text-gray-100 rounded-lg p-3 mt-1 overflow-x-auto whitespace-pre-wrap">
            {sql}
          </pre>
        ) : (
          <p className="text-xs text-amber-600 mt-1">No SQL was generated.</p>
        ))}
    </div>
  );
}

function Section({ label, children }) {
  const [open, setOpen] = useState(false);
  return (
    <section>
      <button
        onClick={() => setOpen((o) => !o)}
        className="text-sm text-blue-600 hover:underline font-medium"
      >
        {open ? `Hide ${label}` : `Show ${label}`}
      </button>
      {open && <div className="mt-2">{children}</div>}
    </section>
  );
}

function ContainmentBatchResultCard({ data }) {
  if (!data) return null;

  if (!data.success) {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-sm font-semibold text-gray-800">Containment check</p>
        <ul className="text-xs text-amber-600 list-disc list-inside">
          {(data.warnings || ["Could not run the containment check."]).map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      </div>
    );
  }

  const queries = data.query_results || [];
  const summaries = data.query_summaries || [];
  const pairwise = data.pairwise_relationships || [];
  const total = queries.length;
  const byId = Object.fromEntries(queries.map((q) => [q.query_id, q]));
  const colsFor = (id) => (byId[id] && byId[id].execution_columns) || [];
  const rowsFor = (id) => (byId[id] ? byId[id].row_count : "");

  // Augment pairwise text: note when a containment holds because the contained
  // query is empty (so an empty result never reads as a meaningful subset).
  const pairwiseText = (p) => {
    let contained = null;
    if (p.relationship === "query_a_contained_in_query_b") contained = p.query_a;
    else if (p.relationship === "query_b_contained_in_query_a") contained = p.query_b;
    if (contained != null && byId[contained] && byId[contained].row_count === 0) {
      return `${p.explanation.replace(/\.$/, "")} because Query ${contained} returned no rows.`;
    }
    return p.explanation;
  };

  const hasCounterexamples = pairwise.some(
    (p) => (p.a_minus_b_rows || []).length || (p.b_minus_a_rows || []).length
  );

  return (
    <div className="flex flex-col gap-5">
      {/* 1. Top summary card: title + natural-language summary */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
        <p className="text-sm font-semibold text-blue-800 mb-2">
          Containment check {DASH} {total} queries
        </p>
        <ul className="flex flex-col gap-1">
          {summaries.map((s) => (
            <li key={s.query_id} className="text-sm text-gray-700">
              {summarySentence(s, total)}
            </li>
          ))}
        </ul>
      </div>

      {/* 2. Compact relationship table */}
      <section>
        <div className="overflow-x-auto border border-gray-200 rounded-lg">
          <table className="min-w-full text-xs">
            <thead className="bg-gray-100 text-gray-600">
              <tr>
                {["Query", "Rows", "Contained in", "Contains", "Equivalent to", "Incomparable with", "Notes"].map(
                  (h) => (
                    <th key={h} className="text-left font-semibold px-3 py-2 whitespace-nowrap">
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {summaries.map((s) => (
                <tr key={s.query_id} className="border-t border-gray-100 text-gray-700">
                  <td className="px-3 py-1.5 font-semibold">Q{s.query_id}</td>
                  <td className="px-3 py-1.5">{rowsFor(s.query_id)}</td>
                  <td className="px-3 py-1.5">{qShort(s.contained_in) || DASH}</td>
                  <td className="px-3 py-1.5">{qShort(s.contains) || DASH}</td>
                  <td className="px-3 py-1.5">{qShort(s.equivalent_to) || DASH}</td>
                  <td className="px-3 py-1.5">{qShort(s.incomparable_with) || DASH}</td>
                  <td className="px-3 py-1.5 text-gray-500">{noteFor(s, total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* 3. Query details (SQL collapsed per query) */}
      <section>
        <h4 className="text-sm font-semibold text-gray-700 mb-2">Query details</h4>
        <div className="flex flex-col gap-3">
          {queries.map((q) => (
            <div key={q.query_id} className="border border-gray-200 rounded-xl p-3">
              <p className="text-sm text-gray-800">
                <span className="text-gray-400">Q{q.query_id}.</span> {q.question}
              </p>
              <div className="flex flex-wrap gap-2 mt-1 text-xs">
                <span className="text-gray-500">rows: {q.row_count}</span>
                {q.safe === false && (
                  <span className="text-red-600">
                    excluded from comparison{q.safety_reason ? ` (${q.safety_reason})` : ""}
                  </span>
                )}
                {q.low_confidence && <span className="text-amber-600">low confidence</span>}
              </div>
              {q.empty_result && (
                <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mt-2">
                  Empty-result query: it returns no rows. On the current database, an empty
                  result is contained in every other compatible result.
                </p>
              )}
              <CollapsibleSql sql={q.sql} />
            </div>
          ))}
        </div>
      </section>

      {/* 4. Pairwise details (collapsed) */}
      <Section label="pairwise details">
        <ul className="flex flex-col gap-1">
          {pairwise.map((p, i) => (
            <li key={i} className="text-sm text-gray-600">
              {pairwiseText(p)}
            </li>
          ))}
        </ul>
      </Section>

      {/* 5. Counterexample rows (collapsed) */}
      {hasCounterexamples && (
        <Section label="counterexample rows">
          <div className="flex flex-col gap-3">
            {pairwise.map((p, i) => {
              const amb = p.a_minus_b_rows || [];
              const bma = p.b_minus_a_rows || [];
              if (!amb.length && !bma.length) return null;
              return (
                <div key={i} className="text-xs text-gray-600">
                  <p className="font-medium text-gray-700">
                    Query {p.query_a} vs Query {p.query_b}
                  </p>
                  {amb.length > 0 && (
                    <>
                      <p className="mt-1">
                        In Query {p.query_a} but not in Query {p.query_b}:
                      </p>
                      <RowsTable columns={colsFor(p.query_a)} rows={amb} />
                    </>
                  )}
                  {bma.length > 0 && (
                    <>
                      <p className="mt-1">
                        In Query {p.query_b} but not in Query {p.query_a}:
                      </p>
                      <RowsTable columns={colsFor(p.query_b)} rows={bma} />
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </Section>
      )}

      {data.limitations && (
        <p className="text-xs text-gray-400 border-t border-gray-100 pt-3">
          {data.limitations}
        </p>
      )}
    </div>
  );
}

export default ContainmentBatchResultCard;
