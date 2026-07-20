export const API_BASE =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";


// ---------------------------------------------------------------------------
// Relationship lifecycle API (ownership context threaded on every call).
// `ctx` = { user_id, username, conversation_id } from the authenticated session.
// ---------------------------------------------------------------------------
function _ctxQuery(ctx = {}) {
  const p = new URLSearchParams();
  if (ctx.user_id != null) p.set("user_id", ctx.user_id);
  if (ctx.username != null) p.set("username", ctx.username);
  if (ctx.conversation_id != null) p.set("conversation_id", ctx.conversation_id);
  const q = p.toString();
  return q ? `?${q}` : "";
}

export async function getRelationships(databaseId, ctx) {
  const r = await fetch(
    `${API_BASE}/database/${databaseId}/relationships${_ctxQuery(ctx)}`
  );
  return r.json();
}

export async function createRelationship(databaseId, edge, ctx) {
  const r = await fetch(
    `${API_BASE}/database/${databaseId}/relationships${_ctxQuery(ctx)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(edge),
    }
  );
  return r.json();
}

export async function updateRelationship(databaseId, relId, fields, ctx) {
  const r = await fetch(
    `${API_BASE}/database/${databaseId}/relationships/${relId}${_ctxQuery(ctx)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fields || {}),
    }
  );
  return r.json();
}

export async function deleteRelationship(databaseId, relId, ctx) {
  const r = await fetch(
    `${API_BASE}/database/${databaseId}/relationships/${relId}${_ctxQuery(ctx)}`,
    { method: "DELETE" }
  );
  return r.json();
}

export async function finalizeRelationships(databaseId, ctx) {
  const r = await fetch(
    `${API_BASE}/database/${databaseId}/relationships/finalize${_ctxQuery(ctx)}`,
    { method: "POST" }
  );
  return r.json();
}

export async function redetectRelationships(databaseId, ctx) {
  const r = await fetch(
    `${API_BASE}/database/${databaseId}/detect-relationships${_ctxQuery(ctx)}`,
    { method: "POST" }
  );
  return r.json();
}

export async function saveRelationships(databaseId, relationships, ctx) {
  const r = await fetch(
    `${API_BASE}/database/${databaseId}/relationships${_ctxQuery(ctx)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ relationships }),
    }
  );
  return r.json();
}
