"""Tool: compare_document_graphs

Compare two document graphs side-by-side.
"""

import httpx
from mcp.types import Tool, TextContent

from tools._graph_helpers import extract_value, get_node_prop, parse_graph

# ── Auth (injected at startup) ───────────────────────────────────────────────
_api_base: str = ""
_authed_get = None


def init(api_base: str, authed_get_fn):
    global _api_base, _authed_get
    _api_base = api_base
    _authed_get = authed_get_fn


# ── Tool definition ──────────────────────────────────────────────────────────
TOOL = Tool(
    name="compare_document_graphs",
    description=(
        "Compare two document graphs side-by-side: node/edge counts, "
        "causation distributions, category overlap, structural similarity."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "env_id": {"type": "string", "description": "Environment ID"},
            "document_id_a": {"type": "string", "description": "First document ID"},
            "document_name_a": {"type": "string", "description": "First document name (for display)"},
            "document_id_b": {"type": "string", "description": "Second document ID"},
            "document_name_b": {"type": "string", "description": "Second document name (for display)"},
        },
        "required": ["env_id", "document_id_a", "document_id_b"],
    },
)


# ── Handler ──────────────────────────────────────────────────────────────────
async def handle(args: dict) -> list[TextContent]:
    env_id = args["env_id"]
    graph_a = await _fetch_graph(env_id, args["document_id_a"])
    graph_b = await _fetch_graph(env_id, args["document_id_b"])
    name_a = args.get("document_name_a", "Document A")
    name_b = args.get("document_name_b", "Document B")
    result = compare_document_graphs(graph_a, name_a, graph_b, name_b)
    return [TextContent(type="text", text=result)]


# ── Implementation ───────────────────────────────────────────────────────────
async def _fetch_graph(env_id: str, doc_id: str) -> dict:
    url = f"{_api_base}/document-graph/{env_id}/{doc_id}"
    async with httpx.AsyncClient(timeout=30) as client:
        return await _authed_get(client, url)


def compare_document_graphs(
    graph_a: dict, name_a: str,
    graph_b: dict, name_b: str,
) -> str:
    """Compare two document graphs and produce a structured diff."""
    nodes_a, edges_a, props_a = parse_graph(graph_a)
    nodes_b, edges_b, props_b = parse_graph(graph_b)

    lines = [
        "## Graph Comparison",
        "",
        f"| Metric | {name_a} | {name_b} |",
        "|--------|" + "-" * (len(name_a) + 2) + "|" + "-" * (len(name_b) + 2) + "|",
        f"| Nodes | {len(nodes_a)} | {len(nodes_b)} |",
        f"| Edges | {len(edges_a)} | {len(edges_b)} |",
        f"| Sub-graphs | {graph_a.get('numGraphs', 'N/A')} | {graph_b.get('numGraphs', 'N/A')} |",
    ]

    # Global property comparison
    all_prop_keys = set()
    for k, v in props_a.items():
        if extract_value(v) is not None:
            all_prop_keys.add(k)
    for k, v in props_b.items():
        if extract_value(v) is not None:
            all_prop_keys.add(k)

    if all_prop_keys:
        for k in sorted(all_prop_keys):
            va = extract_value(props_a.get(k)) or "\u2013"
            vb = extract_value(props_b.get(k)) or "\u2013"
            lines.append(f"| {k} | {va} | {vb} |")

    # Causation comparison
    def causation_dist(nodes):
        d = {}
        for n in nodes:
            c = get_node_prop(n, "causation") or "Unknown"
            d[c] = d.get(c, 0) + 1
        return d

    ca = causation_dist(nodes_a)
    cb = causation_dist(nodes_b)
    all_causes = sorted(set(list(ca.keys()) + list(cb.keys())))

    lines += [
        "",
        "### Causation Distribution",
        "",
        f"| Causation | {name_a} | {name_b} |",
        "|-----------|" + "-" * (len(name_a) + 2) + "|" + "-" * (len(name_b) + 2) + "|",
    ]
    for cause in all_causes:
        lines.append(f"| {cause} | {ca.get(cause, 0)} | {cb.get(cause, 0)} |")

    # Category comparison
    def category_dist(nodes):
        d = {}
        for n in nodes:
            c = get_node_prop(n, "eventCategory") or "Unknown"
            d[c] = d.get(c, 0) + 1
        return d

    cat_a = category_dist(nodes_a)
    cat_b = category_dist(nodes_b)
    all_cats = sorted(set(list(cat_a.keys()) + list(cat_b.keys())))

    lines += [
        "",
        "### Event Category Distribution",
        "",
        f"| Category | {name_a} | {name_b} |",
        "|----------|" + "-" * (len(name_a) + 2) + "|" + "-" * (len(name_b) + 2) + "|",
    ]
    for cat in all_cats:
        lines.append(f"| {cat} | {cat_a.get(cat, 0)} | {cat_b.get(cat, 0)} |")

    # Relation comparison
    def relation_dist(edges):
        d = {}
        for e in edges:
            r = e.get("relation", "Unknown")
            d[r] = d.get(r, 0) + 1
        return d

    rel_a = relation_dist(edges_a)
    rel_b = relation_dist(edges_b)
    all_rels = sorted(set(list(rel_a.keys()) + list(rel_b.keys())))

    lines += [
        "",
        "### Edge Relations",
        "",
        f"| Relation | {name_a} | {name_b} |",
        "|----------|" + "-" * (len(name_a) + 2) + "|" + "-" * (len(name_b) + 2) + "|",
    ]
    for rel in all_rels:
        lines.append(f"| {rel} | {rel_a.get(rel, 0)} | {rel_b.get(rel, 0)} |")

    # Shared event categories
    shared_cats = set(cat_a.keys()) & set(cat_b.keys())
    only_a_cats = set(cat_a.keys()) - set(cat_b.keys())
    only_b_cats = set(cat_b.keys()) - set(cat_a.keys())

    lines += [
        "",
        "### Category Overlap",
        f"- **Shared categories ({len(shared_cats)}):** {', '.join(sorted(shared_cats)) or 'None'}",
        f"- **Only in {name_a} ({len(only_a_cats)}):** {', '.join(sorted(only_a_cats)) or 'None'}",
        f"- **Only in {name_b} ({len(only_b_cats)}):** {', '.join(sorted(only_b_cats)) or 'None'}",
    ]

    # Structural similarity (Jaccard on causation patterns)
    set_a = set(ca.keys())
    set_b = set(cb.keys())
    if set_a or set_b:
        jaccard = len(set_a & set_b) / len(set_a | set_b) * 100
        lines += [
            "",
            "### Structural Similarity",
            f"- **Causation pattern similarity (Jaccard):** {jaccard:.0f}%",
        ]

    return "\n".join(lines)
