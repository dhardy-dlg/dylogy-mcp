"""Tool: export_environment_report

Generate a full markdown report for an environment.
"""

import httpx
from mcp.types import Tool, TextContent

from tools._graph_helpers import extract_value, get_node_label, get_node_prop

# ── Auth (injected at startup) ───────────────────────────────────────────────
_api_base: str = ""
_get_token = None


def init(api_base: str, get_token_fn):
    global _api_base, _get_token
    _api_base = api_base
    _get_token = get_token_fn


# ── Tool definition ──────────────────────────────────────────────────────────
TOOL = Tool(
    name="export_environment_report",
    description=(
        "Generate a full markdown report for an environment: document inventory, "
        "analysis success rates, graph summaries, metadata schema, and per-document details."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "env_id": {"type": "string", "description": "Environment ID"},
        },
        "required": ["env_id"],
    },
)


# ── Handler ──────────────────────────────────────────────────────────────────
async def handle(args: dict) -> list[TextContent]:
    env_id = args["env_id"]

    async with httpx.AsyncClient(timeout=60) as client:
        token = await _get_token(client)
        headers = {"Authorization": f"Bearer {token}"}

        env_resp = await client.get(
            f"{_api_base}/environments/{env_id}", headers=headers
        )
        env_resp.raise_for_status()
        environment = env_resp.json()

        docs_resp = await client.get(
            f"{_api_base}/documents/{env_id}/v2/search",
            headers=headers, params={"limit": 100},
        )
        docs_resp.raise_for_status()
        docs_data = docs_resp.json()
        documents = docs_data.get("results", [])

        graphs: dict[str, dict | None] = {}
        for doc in documents:
            doc_obj = doc if "id" in doc and "publicName" in doc else doc.get("document", doc)
            doc_id = doc_obj.get("id", "")
            try:
                g_resp = await client.get(
                    f"{_api_base}/document-graph/{env_id}/{doc_id}",
                    headers=headers,
                )
                if g_resp.status_code == 200:
                    graphs[doc_id] = g_resp.json()
                else:
                    graphs[doc_id] = None
            except Exception:
                graphs[doc_id] = None

    flat_docs = []
    for doc in documents:
        doc_obj = doc if "publicName" in doc else doc.get("document", doc)
        flat_docs.append(doc_obj)

    report = export_environment_report(environment, flat_docs, graphs)
    return [TextContent(type="text", text=report)]


# ── Implementation ───────────────────────────────────────────────────────────
def export_environment_report(
    environment: dict,
    documents: list[dict],
    graphs: dict[str, dict | None],
) -> str:
    """Generate a full markdown report for an environment."""
    env_name = environment.get("name", "Unknown")
    env_id = environment.get("id", "")
    lang = environment.get("llmLanguageTag", "")
    created = environment.get("createdAt", "")[:10]

    total_docs = len(documents)
    success = sum(1 for d in documents if d.get("analysisStatus") == "SUCCESS")
    failed = sum(1 for d in documents if d.get("analysisStatus") == "FAILED")
    pending = total_docs - success - failed
    docs_with_graphs = sum(1 for g in graphs.values() if g and len(g.get("graphData", {}).get("nodes", [])) > 0)

    lines = [
        f"# Environment Report: {env_name}",
        "",
        f"- **ID:** `{env_id}`",
        f"- **Language:** {lang}",
        f"- **Created:** {created}",
        "",
        "## Summary",
        "",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Total documents | {total_docs} |",
        f"| Analysis SUCCESS | {success} |",
        f"| Analysis FAILED | {failed} |",
        f"| Analysis PENDING | {pending} |",
        f"| Documents with graphs | {docs_with_graphs} |",
        "",
    ]

    if total_docs > 0:
        lines.append(f"**Success rate:** {success / total_docs * 100:.0f}%")
        lines.append("")

    # Metadata schema
    metadata = environment.get("customMetadata", [])
    if metadata:
        lines += [
            "## Metadata Schema",
            "",
            "| Field | Type | Mandatory | Grouped |",
            "|-------|------|-----------|---------|",
        ]
        for m in metadata:
            lines.append(
                f"| {m.get('name', '')} | {m.get('type', '')} "
                f"| {'Yes' if m.get('mandatory') else 'No'} "
                f"| {'Yes' if m.get('grouped') else 'No'} |"
            )
        lines.append("")

    # Document details
    lines += [
        "## Documents",
        "",
        "| # | Document | Analysis | Graph Nodes | Graph Edges |",
        "|---|----------|----------|-------------|-------------|",
    ]

    for i, doc in enumerate(documents, 1):
        doc_obj = doc if "publicName" in doc else doc.get("document", doc)
        name = doc_obj.get("publicName", "?")
        status = doc_obj.get("analysisStatus", "?")
        doc_id = doc_obj.get("id", "")

        g = graphs.get(doc_id)
        if g and "graphData" in g:
            n_nodes = len(g["graphData"].get("nodes", []))
            n_edges = len(g["graphData"].get("edges", []))
        else:
            n_nodes = "\u2013"
            n_edges = "\u2013"

        status_icon = {"SUCCESS": "\u2705", "FAILED": "\u274c"}.get(status, "\u23f3")
        lines.append(f"| {i} | {name} | {status_icon} {status} | {n_nodes} | {n_edges} |")

    lines.append("")

    # Per-document graph summaries
    for doc in documents:
        doc_obj = doc if "publicName" in doc else doc.get("document", doc)
        doc_id = doc_obj.get("id", "")
        doc_name = doc_obj.get("publicName", "?")
        g = graphs.get(doc_id)

        if not g or not g.get("graphData", {}).get("nodes"):
            continue

        gd = g["graphData"]
        g_nodes = gd.get("nodes", [])
        g_edges = gd.get("edges", [])

        lines += [
            f"### {doc_name}",
            "",
            f"- Nodes: {len(g_nodes)}, Edges: {len(g_edges)}, "
            f"Sub-graphs: {g.get('numGraphs', '?')}, Merge: {g.get('mergeMethod', '?')}",
            "",
        ]

        # List nodes
        lines.append("| Node | Label | Causation | Category |")
        lines.append("|------|-------|-----------|----------|")
        for node in sorted(g_nodes, key=lambda n: n.get("nodeId", 0)):
            nid = node.get("nodeId", "?")
            label = get_node_label(node)
            causation = get_node_prop(node, "causation") or "\u2013"
            category = get_node_prop(node, "eventCategory") or "\u2013"
            lines.append(f"| {nid} | {label} | {causation} | {category} |")

        lines += ["", "**Edges:**", ""]
        for edge in g_edges:
            src = edge.get("nodeOriginId")
            dst = edge.get("nodeDestinationId")
            rel = edge.get("relation", "?")
            src_label = next((get_node_label(n) for n in g_nodes if n.get("nodeId") == src), str(src))
            dst_label = next((get_node_label(n) for n in g_nodes if n.get("nodeId") == dst), str(dst))
            lines.append(f"- {src_label} \u2192*{rel}*\u2192 {dst_label}")

        lines += [""]

    lines += [
        "---",
        "*Report generated by Dylogy MCP*",
    ]

    return "\n".join(lines)
