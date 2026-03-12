"""Tool: graph_stats

Compute analytics on a document's knowledge graph.
"""

import httpx
from mcp.types import Tool, TextContent

from tools._graph_helpers import (
    extract_value,
    get_node_label,
    get_node_prop,
    parse_graph,
)

# ── Auth (injected at startup) ───────────────────────────────────────────────
_api_base: str = ""
_authed_get = None


def init(api_base: str, authed_get_fn):
    global _api_base, _authed_get
    _api_base = api_base
    _authed_get = authed_get_fn


# ── Tool definition ──────────────────────────────────────────────────────────
TOOL = Tool(
    name="graph_stats",
    description=(
        "Compute analytics on a document's knowledge graph: topology, "
        "longest causal chain, hub nodes, causation/category distributions."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "env_id": {"type": "string", "description": "Environment ID"},
            "document_id": {"type": "string", "description": "Document ID"},
        },
        "required": ["env_id", "document_id"],
    },
)


# ── Handler ──────────────────────────────────────────────────────────────────
async def handle(args: dict) -> list[TextContent]:
    data = await _fetch_graph(args["env_id"], args["document_id"])
    stats = graph_stats(data)
    return [TextContent(type="text", text=stats)]


# ── Implementation ───────────────────────────────────────────────────────────
async def _fetch_graph(env_id: str, doc_id: str) -> dict:
    url = f"{_api_base}/document-graph/{env_id}/{doc_id}"
    async with httpx.AsyncClient(timeout=30) as client:
        return await _authed_get(client, url)


def graph_stats(graph_data: dict) -> str:
    """Compute analytics on a document graph."""
    nodes, edges, properties = parse_graph(graph_data)

    if not nodes:
        return "Empty graph – no statistics to compute."

    node_count = len(nodes)
    edge_count = len(edges)

    # Build adjacency for analysis
    adj: dict[int, list[int]] = {}
    in_degree: dict[int, int] = {}
    out_degree: dict[int, int] = {}

    for node in nodes:
        nid = node.get("nodeId")
        adj[nid] = []
        in_degree[nid] = 0
        out_degree[nid] = 0

    for edge in edges:
        src = edge.get("nodeOriginId")
        dst = edge.get("nodeDestinationId")
        if src in adj:
            adj[src].append(dst)
            out_degree[src] = out_degree.get(src, 0) + 1
        if dst in in_degree:
            in_degree[dst] = in_degree.get(dst, 0) + 1

    # Root nodes (no incoming edges)
    roots = [nid for nid, deg in in_degree.items() if deg == 0]

    # Leaf nodes (no outgoing edges)
    leaves = [nid for nid, deg in out_degree.items() if deg == 0]

    # Hub nodes (highest total degree)
    total_degree = {nid: in_degree.get(nid, 0) + out_degree.get(nid, 0) for nid in adj}
    hub_id = max(total_degree, key=total_degree.get)

    # Longest path (DFS)
    memo: dict[int, list[int]] = {}

    def longest_path(nid: int, visited: set) -> list[int]:
        if nid in memo:
            return memo[nid]
        visited.add(nid)
        best = [nid]
        for neighbor in adj.get(nid, []):
            if neighbor not in visited:
                candidate = [nid] + longest_path(neighbor, visited)
                if len(candidate) > len(best):
                    best = candidate
        visited.discard(nid)
        memo[nid] = best
        return best

    longest = []
    for root in (roots or list(adj.keys())):
        path = longest_path(root, set())
        if len(path) > len(longest):
            longest = path

    # Causation distribution
    causation_counts: dict[str, int] = {}
    for node in nodes:
        c = get_node_prop(node, "causation") or "Unknown"
        causation_counts[c] = causation_counts.get(c, 0) + 1

    # Category distribution
    category_counts: dict[str, int] = {}
    for node in nodes:
        cat = get_node_prop(node, "eventCategory") or "Unknown"
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # Relation type distribution
    relation_counts: dict[str, int] = {}
    for edge in edges:
        rel = edge.get("relation", "Unknown")
        relation_counts[rel] = relation_counts.get(rel, 0) + 1

    # Global properties
    global_props = {}
    for k, v in properties.items():
        global_props[k] = extract_value(v)

    # Build node lookup
    node_map = {n.get("nodeId"): get_node_label(n) for n in nodes}

    # Format output
    lines = [
        "## Graph Statistics",
        "",
        f"- **Nodes:** {node_count}",
        f"- **Edges:** {edge_count}",
        f"- **Density:** {edge_count / (node_count * (node_count - 1)) * 100:.1f}%" if node_count > 1 else f"- **Density:** N/A",
        f"- **Sub-graphs merged:** {graph_data.get('numGraphs', 'N/A')}",
        f"- **Merge method:** {graph_data.get('mergeMethod', 'N/A')}",
    ]

    if global_props:
        lines += ["", "### Global Properties"]
        for k, v in global_props.items():
            if v is not None:
                lines.append(f"- **{k}:** {v}")

    lines += [
        "",
        "### Topology",
        f"- **Root nodes** (no incoming): {', '.join(node_map.get(r, str(r)) for r in roots) or 'None (cyclic)'}",
        f"- **Leaf nodes** (no outgoing): {', '.join(node_map.get(l, str(l)) for l in leaves) or 'None'}",
        f"- **Hub node** (most connections): {node_map.get(hub_id, str(hub_id))} ({total_degree[hub_id]} connections)",
        f"- **Longest causal chain:** {len(longest)} nodes",
    ]

    if longest:
        chain_labels = [f"  {i+1}. {node_map.get(nid, str(nid))}" for i, nid in enumerate(longest)]
        lines += ["", "### Longest Chain"] + chain_labels

    lines += ["", "### Causation Distribution"]
    for cause, count in sorted(causation_counts.items(), key=lambda x: -x[1]):
        bar = "\u2588" * count
        lines.append(f"  {cause}: {count} {bar}")

    lines += ["", "### Event Category Distribution"]
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {cat}: {count}")

    lines += ["", "### Edge Relation Types"]
    for rel, count in sorted(relation_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {rel}: {count}")

    return "\n".join(lines)
