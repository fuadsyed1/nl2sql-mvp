"""
join_tree_builder.py

Phase 6, step 4 — span the required IR tables into one connected join tree.

Given the required tables, deterministic adjacency, and the path resolver, this
module:
  * checks connectivity via connected components among the required tables,
  * when connected, computes a root-independent spanning edge set, selects the
    root by (-confirmed_degree_within_plan, ir_table_index, table_name), and
    emits joins in attachment order (every join's from_table is already in the
    growing tree),
  * reports tables_used (root-first), bridge_tables (tables_used - ir_tables),
    and diagnostics,
  * when disconnected, reports the components and unresolved tables.

It does NOT build the final success/failure plan (Step 5), generate SQL, or
mutate the IR / its table list. The adjacency is read-only.
"""

from planning.path_resolver import find_best_path
from planning.query_plan import join_step

__all__ = ["build_join_tree"]


def _lower(value):
    return str(value).strip().lower()


def _edge_conf(edge):
    c = edge.get("confidence")
    if isinstance(c, bool):
        return 0.0
    return c if isinstance(c, (int, float)) else 0.0


def _conn_key(edge):
    a = (_lower(edge.get("from_table", "")), _lower(edge.get("from_column", "")))
    b = (_lower(edge.get("to_table", "")), _lower(edge.get("to_column", "")))
    return frozenset((a, b))


def _conn_sig(edge):
    return (
        f"{_lower(edge.get('from_table',''))}.{_lower(edge.get('from_column',''))}->"
        f"{_lower(edge.get('to_table',''))}.{_lower(edge.get('to_column',''))}"
        f"#{edge.get('relationship_id', '')}"
    )


def _normalize_required(ir_tables):
    """Lowercased, de-duplicated required tables (input list left unchanged),
    plus {table: ir_index}."""
    required = []
    ir_index = {}
    for t in ir_tables or []:
        lt = _lower(t)
        if lt and lt not in ir_index:
            ir_index[lt] = len(required)
            required.append(lt)
    return required, ir_index


def _components(adjacency, required):
    """Connected components (undirected) over the graph, returned as the groups
    of REQUIRED tables, ordered by earliest IR appearance."""
    nodes = set(adjacency.keys()) | set(required)
    label = {}
    cid = 0
    for node in sorted(nodes):
        if node in label:
            continue
        stack = [node]
        label[node] = cid
        while stack:
            cur = stack.pop()
            for e in adjacency.get(cur, []):
                nb = _lower(e.get("to_table", ""))
                if nb and nb not in label:
                    label[nb] = cid
                    stack.append(nb)
        cid += 1

    groups = {}
    for r in required:               # iterate in IR order -> stable within-group order
        groups.setdefault(label[r], []).append(r)

    ordered_labels = sorted(groups.keys(), key=lambda L: min(required.index(x) for x in groups[L]))
    return [groups[L] for L in ordered_labels]


def _local_rank(path):
    """Rank used to pick among candidate connection paths (mirrors the resolver
    minus hints, which were already applied per-pair)."""
    non_key = sum(1 for e in path if e.get("relationship_type") != "foreign_key")
    hop = len(path)
    unconfirmed = sum(1 for e in path if not e.get("confirmed"))
    min_conf = min((_edge_conf(e) for e in path), default=1.0)
    signature = "|".join(_conn_sig(e) for e in path)
    return (non_key, hop, unconfirmed, -min_conf, signature)


def _span_edges(required, adjacency, hints):
    """Root-independent spanning edge set connecting all required tables."""
    seed = required[0]
    tree = {seed}
    edges = []
    keys = set()

    for target in required[1:]:
        if target in tree:
            continue
        best = None
        best_rank = None
        for src in sorted(tree):
            path = find_best_path(adjacency, src, target, hints)
            if path is None:
                continue
            rank = _local_rank(path)
            if best_rank is None or rank < best_rank:
                best_rank = rank
                best = path
        if best is None:
            continue  # unreachable (handled by the component check upstream)
        for e in best:
            tree.add(_lower(e["from_table"]))
            tree.add(_lower(e["to_table"]))
            k = _conn_key(e)
            if k not in keys:
                keys.add(k)
                edges.append(e)
    return edges


def _orient(edge, from_side):
    """Emit a join step oriented so from_table == from_side (already in tree)."""
    if _lower(edge["from_table"]) == from_side:
        return join_step(edge["from_table"], edge["from_column"],
                         edge["to_table"], edge["to_column"])
    return join_step(edge["to_table"], edge["to_column"],
                     edge["from_table"], edge["from_column"])


def _order_joins(root, spanning_edges):
    """Emit joins in attachment order from the root. Invariant: each emitted
    join's from_table is already in the growing tree."""
    tree = {root}
    ordered = [root]
    joins = []
    edges = list(spanning_edges)

    while True:
        # drop edges whose endpoints are both already in the tree (no cycles)
        edges = [e for e in edges
                 if not (_lower(e["from_table"]) in tree and _lower(e["to_table"]) in tree)]

        eligible = []
        for e in edges:
            a, b = _lower(e["from_table"]), _lower(e["to_table"])
            in_a, in_b = a in tree, b in tree
            if in_a != in_b:
                new_table = b if in_a else a
                from_side = a if in_a else b
                eligible.append((new_table, _conn_sig(e), e, from_side))

        if not eligible:
            break

        eligible.sort(key=lambda x: (x[0], x[1]))
        new_table, _, e, from_side = eligible[0]
        joins.append(_orient(e, from_side))
        tree.add(new_table)
        ordered.append(new_table)
        edges.remove(e)

    return ordered, joins


def build_join_tree(ir_tables, adjacency, hints=None):
    """Span the required IR tables into a connected join tree (or report
    disconnection). Returns a structured dict; it does not build the final
    plan. The input ir_tables list is never mutated."""
    required, ir_index = _normalize_required(ir_tables)

    if not required:
        return {
            "connected": False,
            "from_table": None,
            "joins": [],
            "tables_used": [],
            "bridge_tables": [],
            "components": [],
            "unresolved_tables": [],
            "diagnostics": {"note": "no required tables"},
        }

    components = _components(adjacency, required)
    required_set = set(required)

    if len(components) > 1:
        primary = components[0]      # ordered by earliest IR appearance
        primary_set = set(primary)
        unresolved = [t for t in required if t not in primary_set]
        return {
            "connected": False,
            "from_table": None,
            "joins": [],
            "tables_used": [],
            "bridge_tables": [],
            "components": components,
            "unresolved_tables": unresolved,
            "diagnostics": {
                "reason": "disconnected",
                "components": components,
                "unresolved_tables": unresolved,
                "primary_component": primary,
            },
        }

    # --- connected: span, choose root, order joins --------------------------
    spanning = _span_edges(required, adjacency, hints)

    confirmed_degree = {}
    for r in required:
        confirmed_degree[r] = sum(
            1 for e in spanning
            if e.get("confirmed")
            and (_lower(e["from_table"]) == r or _lower(e["to_table"]) == r)
        )

    root = min(required, key=lambda t: (-confirmed_degree.get(t, 0), ir_index[t], t))
    tables_used, joins = _order_joins(root, spanning)
    bridge_tables = [t for t in tables_used if t not in required_set]

    diagnostics = {
        "root": root,
        "root_selection": {
            "rule": "(-confirmed_degree_within_plan, ir_table_index, table_name)",
            "confirmed_degree": confirmed_degree,
        },
        "bridge_tables_added": bridge_tables,
        "spanning_edge_count": len(spanning),
        "components": components,
    }

    return {
        "connected": True,
        "from_table": root,
        "joins": joins,
        "tables_used": tables_used,
        "bridge_tables": bridge_tables,
        "components": components,
        "unresolved_tables": [],
        "diagnostics": diagnostics,
    }