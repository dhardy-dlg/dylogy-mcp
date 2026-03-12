"""Tool: graph_to_mermaid

Convert a document's knowledge graph to a Mermaid flowchart diagram.
"""

import base64
import json
import webbrowser
import zlib

import httpx
from mcp.types import Tool, TextContent

from tools._graph_helpers import extract_value, get_node_label, get_node_prop, parse_graph

# ── Auth (injected at startup) ───────────────────────────────────────────────
_api_base: str = ""
_authed_get = None


def init(api_base: str, authed_get_fn):
    global _api_base, _authed_get
    _api_base = api_base
    _authed_get = authed_get_fn


# ── Tool definition ──────────────────────────────────────────────────────────
TOOL = Tool(
    name="graph_to_mermaid",
    description=(
        "Convert a document's knowledge graph to a Mermaid flowchart diagram. "
        "Returns the Mermaid markdown that can be pasted into any markdown renderer."
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
    mermaid = graph_to_mermaid(data)
    url = open_mermaid_viewer(mermaid)
    return [TextContent(
        type="text",
        text=f"Mermaid viewer opened in browser.\nURL: {url}\n\n```mermaid\n{mermaid}\n```",
    )]


# ── Implementation ───────────────────────────────────────────────────────────
async def _fetch_graph(env_id: str, doc_id: str) -> dict:
    url = f"{_api_base}/document-graph/{env_id}/{doc_id}"
    async with httpx.AsyncClient(timeout=30) as client:
        return await _authed_get(client, url)


def graph_to_mermaid(graph_data: dict, document_name: str = "Document") -> str:
    """Convert a document graph to a Mermaid flowchart string."""
    nodes, edges, properties = parse_graph(graph_data)

    if not nodes:
        return "graph TD\n  empty[No nodes in graph]"

    lines = ["graph TD"]

    causation_styles = {
        "PrimaryCause":        "fill:#f0fdf4,stroke:#22c55e,color:#15803d",
        "SecondaryCause":      "fill:#ecfeff,stroke:#06b6d4,color:#0e7490",
        "TriggerEvent":        "fill:#ecfdf5,stroke:#10b981,color:#047857",
        "DirectConsequence":   "fill:#eff6ff,stroke:#3b82f6,color:#1d4ed8",
        "IndirectConsequence": "fill:#fffbeb,stroke:#f59e0b,color:#b45309",
        "MitigationAction":    "fill:#fdf2f8,stroke:#ec4899,color:#be185d",
        "ResolutionProposed":  "fill:#fdf4ff,stroke:#d946ef,color:#a21caf",
        "ResolutionCompleted": "fill:#f7fee7,stroke:#84cc16,color:#4d7c0f",
    }

    for node in sorted(nodes, key=lambda n: n.get("nodeId", 0)):
        nid = node.get("nodeId", "?")
        label = get_node_label(node).replace('"', "'")
        lines.append(f'  n{nid}["{label}"]')

    lines.append("")

    for edge in edges:
        src = edge.get("nodeOriginId")
        dst = edge.get("nodeDestinationId")
        rel = edge.get("relation", "")
        rel_label = rel.replace("_", " ").title()
        lines.append(f'  n{src} -->|"{rel_label}"| n{dst}')

    lines.append("")

    for node in nodes:
        nid = node.get("nodeId", "?")
        causation = get_node_prop(node, "causation") or "default"
        style = causation_styles.get(causation)
        if style:
            lines.append(f"  style n{nid} {style}")

    return "\n".join(lines)


def mermaid_live_url(mermaid_code: str) -> str:
    """Encode a Mermaid diagram into a mermaid.live playground URL."""
    state = json.dumps({
        "code": mermaid_code,
        "mermaid": {"theme": "default"},
        "autoSync": True,
        "updateDiagram": True,
    })
    compressed = zlib.compress(state.encode("utf-8"), 9)
    encoded = base64.urlsafe_b64encode(compressed).decode("ascii").rstrip("=")
    return f"https://mermaid.live/edit#pako:{encoded}"


def open_mermaid_viewer(mermaid_code: str) -> str:
    """Build the mermaid.live URL and open it in the default browser."""
    url = mermaid_live_url(mermaid_code)
    webbrowser.open(url)
    return url
