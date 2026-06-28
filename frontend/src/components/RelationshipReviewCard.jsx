import { useState, useEffect } from "react";
import { API_BASE } from "../api";

const SELECT_CLASS =
  "border border-gray-300 rounded-lg px-2 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500";

// Read-only relationship review. Fetches detected relationships for the active
// database and lists them. Edit/add/delete/finalize are later steps; for now
// this is review-only with a way back to the summary. Query input stays hidden.
function RelationshipReviewCard({
  summary,
  onBack = () => {},
  onFinalize = () => {},
  finalized = false,
}) {
  const { database_id, name } = summary || {};

  const [relationships, setRelationships] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  // True once at least one relationship was fetched, so an empty list after
  // local removals reads "No relationships selected." rather than "...detected".
  const [loadedAny, setLoadedAny] = useState(false);

  useEffect(() => {
    if (database_id == null) return;
    setLoading(true);
    setError("");
    setLoadedAny(false);
    fetch(`${API_BASE}/database/${database_id}/relationships`)
      .then((r) => r.json())
      .then((d) => {
        if (d.success === false) {
          setError(d.message || "Could not load relationships.");
          setRelationships([]);
        } else {
          const list = d.relationships || [];
          setRelationships(list);
          if (list.length) setLoadedAny(true);
        }
      })
      .catch((e) => setError(`Could not load relationships: ${e.message}`))
      .finally(() => setLoading(false));
  }, [database_id]);

  // Frontend-only removal: drops the row from local state. No backend call;
  // the database is unchanged until relationships are finalized (a later step).
  const removeRelationship = (index) => {
    setRelationships((prev) => prev.filter((_, idx) => idx !== index));
    if (editingIndex === index) setEditingIndex(null);
  };

  // --- Frontend-only edit via dropdowns -----------------------------------
  // Schema graph (tables + columns) is fetched lazily the first time a row is
  // edited, then reused. Same shape used by the table preview.
  const [graph, setGraph] = useState(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState("");
  const [editingIndex, setEditingIndex] = useState(null);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState(null);
  const [formError, setFormError] = useState("");

  const emptyDraft = () => ({
    from_table: "",
    from_column: "",
    to_table: "",
    to_column: "",
  });

  // --- Validation (Steps 1 & 2) -------------------------------------------
  const isComplete = (d) =>
    Boolean(d && d.from_table && d.from_column && d.to_table && d.to_column);
  const isSelfLink = (d) =>
    Boolean(d && d.from_table === d.to_table && d.from_column === d.to_column);
  const sameEdge = (a, b) =>
    a.from_table === b.from_table &&
    a.from_column === b.from_column &&
    a.to_table === b.to_table &&
    a.to_column === b.to_column;
  const exactDuplicate = (d, ignoreIndex) =>
    relationships.some((r, idx) => idx !== ignoreIndex && sameEdge(r, d));
  const reverseDuplicate = (d, ignoreIndex) =>
    relationships.some(
      (r, idx) =>
        idx !== ignoreIndex &&
        r.from_table === d.to_table &&
        r.from_column === d.to_column &&
        r.to_table === d.from_table &&
        r.to_column === d.from_column
    );

  // Returns an error string for blocking problems, or "" when savable.
  const validate = (d, ignoreIndex) => {
    if (!isComplete(d)) return "Please select all relationship fields.";
    if (isSelfLink(d)) return "A relationship cannot connect a column to itself.";
    if (exactDuplicate(d, ignoreIndex)) return "This relationship already exists.";
    return "";
  };

  const tableNames = (graph?.tables || []).map((t) => t.table_name);
  const columnsForTable = (tableName) =>
    ((graph?.tables || []).find((t) => t.table_name === tableName)?.columns ||
      []).map((c) => c.column_name);

  const ensureGraph = () => {
    if (graph || graphLoading || database_id == null) return;
    setGraphLoading(true);
    setGraphError("");
    fetch(`${API_BASE}/database/${database_id}/graph`)
      .then((r) => r.json())
      .then((d) => {
        if (!d.success) setGraphError(d.message || "Could not load schema.");
        else setGraph(d.database);
      })
      .catch((e) => setGraphError(`Could not load schema: ${e.message}`))
      .finally(() => setGraphLoading(false));
  };

  const startEdit = (index) => {
    const rel = relationships[index] || {};
    setAdding(false); // adding and editing are mutually exclusive
    setFormError("");
    setDraft({
      from_table: rel.from_table || "",
      from_column: rel.from_column || "",
      to_table: rel.to_table || "",
      to_column: rel.to_column || "",
    });
    setEditingIndex(index);
    ensureGraph();
  };

  const cancelEdit = () => {
    setEditingIndex(null);
    setDraft(null);
    setFormError("");
  };

  const startAdd = () => {
    setEditingIndex(null); // adding and editing are mutually exclusive
    setFormError("");
    setDraft(emptyDraft());
    setAdding(true);
    ensureGraph();
  };

  const cancelAdd = () => {
    setAdding(false);
    setDraft(null);
    setFormError("");
  };

  const saveAdd = () => {
    if (!draft) return;
    const err = validate(draft, -1);
    if (err) {
      setFormError(err);
      return;
    }
    const newRel = {
      from_table: draft.from_table,
      from_column: draft.from_column,
      to_table: draft.to_table,
      to_column: draft.to_column,
      confidence: null,
      relationship_type: "manual",
      confirmed: false,
      local: true,
    };
    setRelationships((prev) => [...prev, newRel]);
    cancelAdd();
  };

  // Changing a table clears its column if no longer valid for that table.
  const setDraftField = (field, value) => {
    setFormError(""); // clear stale duplicate/self errors on change
    setDraft((prev) => {
      const next = { ...prev, [field]: value };
      if (field === "from_table" &&
          !columnsForTable(value).includes(next.from_column)) {
        next.from_column = "";
      }
      if (field === "to_table" &&
          !columnsForTable(value).includes(next.to_column)) {
        next.to_column = "";
      }
      return next;
    });
  };

  const saveEdit = () => {
    if (editingIndex == null || !draft) return;
    const err = validate(draft, editingIndex);
    if (err) {
      setFormError(err);
      return;
    }
    setRelationships((prev) =>
      prev.map((rel, idx) =>
        idx === editingIndex
          ? {
              ...rel, // keep confidence, relationship_type, confirmed, id
              from_table: draft.from_table,
              from_column: draft.from_column,
              to_table: draft.to_table,
              to_column: draft.to_column,
            }
          : rel
      )
    );
    cancelEdit();
  };

  return (
    <div className="h-full flex items-center justify-center">
      <div className="w-[80%] max-w-3xl bg-white border border-gray-200 rounded-2xl shadow-lg flex flex-col">
        <div className="px-6 py-5 border-b border-gray-100">
          <h2 className="text-2xl font-bold text-gray-800">Relationship Review</h2>
          <p className="text-gray-500 text-sm mt-1">
            Review detected table relationships before querying.
          </p>
        </div>

        <div className="px-6 py-5">
          {/* Add relationship (frontend-only) */}
          <div className="mb-4">
            {!adding ? (
              <button
                onClick={startAdd}
                className="text-sm text-blue-600 hover:text-blue-700 border border-blue-200 rounded-lg px-4 py-2"
              >
                + Add Relationship
              </button>
            ) : (
              <div className="border border-gray-200 rounded-xl p-4 flex flex-col gap-3">
                <p className="text-sm font-semibold text-gray-800">
                  New relationship
                </p>

                {graphLoading && (
                  <p className="text-sm text-gray-500">Loading schema…</p>
                )}
                {graphError && (
                  <p className="text-sm text-amber-600">{graphError}</p>
                )}

                <div className="flex flex-wrap items-center gap-2">
                  <select
                    value={draft.from_table}
                    onChange={(e) => setDraftField("from_table", e.target.value)}
                    className={SELECT_CLASS}
                  >
                    <option value="">table</option>
                    {tableNames.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                  <select
                    value={draft.from_column}
                    onChange={(e) => setDraftField("from_column", e.target.value)}
                    className={SELECT_CLASS}
                  >
                    <option value="">column</option>
                    {columnsForTable(draft.from_table).map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>

                  <span className="text-gray-400 mx-1">→</span>

                  <select
                    value={draft.to_table}
                    onChange={(e) => setDraftField("to_table", e.target.value)}
                    className={SELECT_CLASS}
                  >
                    <option value="">table</option>
                    {tableNames.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                  <select
                    value={draft.to_column}
                    onChange={(e) => setDraftField("to_column", e.target.value)}
                    className={SELECT_CLASS}
                  >
                    <option value="">column</option>
                    {columnsForTable(draft.to_table).map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>

                {formError && (
                  <p className="text-sm text-red-600">{formError}</p>
                )}
                {!formError &&
                  draft &&
                  reverseDuplicate(draft, -1) &&
                  !exactDuplicate(draft, -1) && (
                    <p className="text-sm text-amber-600">
                      A reverse relationship already exists. Please confirm this
                      direction is correct.
                    </p>
                  )}

                <div className="flex gap-2">
                  <button
                    onClick={saveAdd}
                    disabled={!isComplete(draft) || isSelfLink(draft)}
                    className="bg-blue-500 text-white text-sm px-4 py-2 rounded-lg hover:bg-blue-600 disabled:opacity-50"
                  >
                    Save
                  </button>
                  <button
                    onClick={cancelAdd}
                    className="bg-gray-100 text-gray-700 text-sm px-4 py-2 rounded-lg hover:bg-gray-200"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>

          {loading && <p className="text-sm text-gray-500">Loading…</p>}
          {error && <p className="text-sm text-amber-600">{error}</p>}

          {!loading && !error && relationships.length === 0 && (
            <p className="text-sm text-gray-500">
              {loadedAny
                ? "No relationships selected."
                : "No relationships detected yet."}
            </p>
          )}

          {!loading && !error && relationships.length > 0 && (
            <>
              <p className="text-xs text-gray-400 mb-2">
                Changes are local until finalized.
              </p>
              <ul className="flex flex-col gap-2">
                {relationships.map((rel, i) => (
                  <li
                    key={rel.relationship_id ?? i}
                    className="bg-gray-50 border border-gray-200 rounded-xl px-4 py-3"
                  >
                    {editingIndex === i ? (
                      <div className="flex flex-col gap-3">
                        {graphLoading && (
                          <p className="text-sm text-gray-500">Loading schema…</p>
                        )}
                        {graphError && (
                          <p className="text-sm text-amber-600">{graphError}</p>
                        )}

                        <div className="flex flex-wrap items-center gap-2">
                          <select
                            value={draft.from_table}
                            onChange={(e) =>
                              setDraftField("from_table", e.target.value)
                            }
                            className={SELECT_CLASS}
                          >
                            <option value="">table</option>
                            {tableNames.map((t) => (
                              <option key={t} value={t}>
                                {t}
                              </option>
                            ))}
                          </select>
                          <select
                            value={draft.from_column}
                            onChange={(e) =>
                              setDraftField("from_column", e.target.value)
                            }
                            className={SELECT_CLASS}
                          >
                            <option value="">column</option>
                            {columnsForTable(draft.from_table).map((c) => (
                              <option key={c} value={c}>
                                {c}
                              </option>
                            ))}
                          </select>

                          <span className="text-gray-400 mx-1">→</span>

                          <select
                            value={draft.to_table}
                            onChange={(e) =>
                              setDraftField("to_table", e.target.value)
                            }
                            className={SELECT_CLASS}
                          >
                            <option value="">table</option>
                            {tableNames.map((t) => (
                              <option key={t} value={t}>
                                {t}
                              </option>
                            ))}
                          </select>
                          <select
                            value={draft.to_column}
                            onChange={(e) =>
                              setDraftField("to_column", e.target.value)
                            }
                            className={SELECT_CLASS}
                          >
                            <option value="">column</option>
                            {columnsForTable(draft.to_table).map((c) => (
                              <option key={c} value={c}>
                                {c}
                              </option>
                            ))}
                          </select>
                        </div>

                        {formError && (
                          <p className="text-sm text-red-600">{formError}</p>
                        )}
                        {!formError &&
                          draft &&
                          reverseDuplicate(draft, editingIndex) &&
                          !exactDuplicate(draft, editingIndex) && (
                            <p className="text-sm text-amber-600">
                              A reverse relationship already exists. Please
                              confirm this direction is correct.
                            </p>
                          )}

                        <div className="flex gap-2">
                          <button
                            onClick={saveEdit}
                            disabled={!isComplete(draft) || isSelfLink(draft)}
                            className="bg-blue-500 text-white text-sm px-4 py-2 rounded-lg hover:bg-blue-600 disabled:opacity-50"
                          >
                            Save
                          </button>
                          <button
                            onClick={cancelEdit}
                            className="bg-gray-100 text-gray-700 text-sm px-4 py-2 rounded-lg hover:bg-gray-200"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-sm text-gray-800">
                            <span className="font-medium">
                              {rel.from_table}.{rel.from_column}
                            </span>
                            <span className="text-gray-400 mx-2">→</span>
                            <span className="font-medium">
                              {rel.to_table}.{rel.to_column}
                            </span>
                          </div>

                          <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
                            {rel.confidence != null && (
                              <span>
                                Confidence: {Number(rel.confidence).toFixed(2)}
                              </span>
                            )}
                            {rel.confirmed != null && (
                              <span>
                                Status: {rel.confirmed ? "confirmed" : "suggested"}
                              </span>
                            )}
                            {rel.relationship_type && (
                              <span>Type: {rel.relationship_type}</span>
                            )}
                          </div>
                        </div>

                        <div className="shrink-0 flex items-center gap-2">
                          <button
                            onClick={() => startEdit(i)}
                            className="text-xs text-gray-500 hover:text-blue-600 border border-gray-200 rounded-lg px-3 py-1.5"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => removeRelationship(i)}
                            className="text-xs text-gray-500 hover:text-red-600 border border-gray-200 rounded-lg px-3 py-1.5"
                          >
                            Remove
                          </button>
                        </div>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}

          <div className="mt-5 flex flex-col gap-2">
            <div className="flex gap-2">
              {finalized ? (
                <span className="self-center text-sm font-medium text-green-700">
                  Relationships finalized.
                </span>
              ) : (
                <button
                  onClick={() => onFinalize(relationships)}
                  disabled={adding || editingIndex != null}
                  className="bg-green-600 text-white text-sm px-5 py-2.5 rounded-xl hover:bg-green-700 disabled:opacity-50"
                >
                  Finalize Relationships
                </button>
              )}
              <button
                onClick={onBack}
                className="bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm px-5 py-2.5 rounded-xl"
              >
                Back to Database Summary
              </button>
            </div>
            <p className="text-xs text-gray-400">
              Relationship changes are finalized for this chat session.
            </p>
          </div>
        </div>

        <div className="px-6 py-3 border-t border-gray-100">
          <p className="text-sm text-gray-500">
            Active Database:{" "}
            <span className="font-medium text-gray-700">
              {name || `Database ${database_id}`}
              {database_id != null ? ` #${database_id}` : ""}
            </span>
          </p>
        </div>
      </div>
    </div>
  );
}

export default RelationshipReviewCard;
