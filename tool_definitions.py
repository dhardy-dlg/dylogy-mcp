"""
Custom MCP tool definitions and their async handlers.

Each tool has:
- A Tool(...) definition (schema for the MCP protocol)
- An async handler function that executes the tool logic
"""

import httpx
from mcp.types import Tool, TextContent

import actuarial_search
import custom_tools
import graph_viewer
import pdf_report
import rich_report


# ── Shared helpers ───────────────────────────────────────────────────────────
# These are injected at startup by dylogy.py
_api_base: str = ""
_get_token = None
_authed_get = None


def init(api_base: str, get_token_fn, authed_get_fn):
    """Wire up the auth functions from the main server module."""
    global _api_base, _get_token, _authed_get
    _api_base = api_base
    _get_token = get_token_fn
    _authed_get = authed_get_fn


async def _fetch_graph(env_id: str, doc_id: str) -> dict:
    """Fetch a document graph from the API."""
    url = f"{_api_base}/document-graph/{env_id}/{doc_id}"
    async with httpx.AsyncClient(timeout=30) as client:
        return await _authed_get(client, url)


# ── Tool definitions ─────────────────────────────────────────────────────────

VIEW_GRAPH_TOOL = Tool(
    name="view_document_graph",
    description=(
        "Fetch a document's knowledge graph and open an interactive "
        "React Flow viewer in the browser. Use this when the user "
        "wants to *see* or *visualise* a graph."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "env_id": {
                "type": "string",
                "description": "Environment ID",
            },
            "document_id": {
                "type": "string",
                "description": "Document ID",
            },
            "document_name": {
                "type": "string",
                "description": "Human-readable document name (used as viewer title)",
            },
        },
        "required": ["env_id", "document_id"],
    },
)

GRAPH_TO_MERMAID_TOOL = Tool(
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

GRAPH_STATS_TOOL = Tool(
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

COMPARE_GRAPHS_TOOL = Tool(
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

EXPORT_ENV_REPORT_TOOL = Tool(
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

MARKDOWN_TO_PDF_TOOL = Tool(
    name="create_pdf_report",
    description=(
        "Generate a styled PDF report from markdown content. "
        "The PDF includes the Dylogy logo in the page header and page numbers in the footer. "
        "Use this to convert any markdown output (e.g. from export_environment_report, "
        "graph_stats, compare_document_graphs) into a downloadable PDF."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "markdown_content": {
                "type": "string",
                "description": "The markdown text to render into a PDF",
            },
            "title": {
                "type": "string",
                "description": "Document title (used in PDF metadata, defaults to 'Report')",
            },
            "filename": {
                "type": "string",
                "description": "Output filename (without path). Saved to a temp directory. Defaults to an auto-generated name.",
            },
        },
        "required": ["markdown_content"],
    },
)

RICH_PDF_REPORT_TOOL = Tool(
    name="create_rich_pdf_report",
    description=(
        "Generate a rich PDF report from markdown with support for LaTeX math "
        "($inline$ and $$block$$), Mermaid diagrams (```mermaid code blocks), "
        "and embedded images (local file paths auto-converted to base64). "
        "Use this instead of create_pdf_report when the content includes "
        "mathematical formulas, diagrams, or images."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "markdown_content": {
                "type": "string",
                "description": (
                    "Markdown text with optional extensions: "
                    "$...$ for inline math, $$...$$ for block math, "
                    "```mermaid for diagrams, ![alt](path) for images"
                ),
            },
            "title": {
                "type": "string",
                "description": "Document title (PDF metadata). Defaults to 'Report'.",
            },
            "filename": {
                "type": "string",
                "description": "Output filename (without path). Defaults to auto-generated name.",
            },
        },
        "required": ["markdown_content"],
    },
)

ACTUARIAL_SEARCH_TOOL = Tool(
    name="search_actuarial_library",
    description=(
        "Search the ressources-actuarielles.net actuarial library (ISFA). "
        "Returns academic papers and memoirs from actuarial science, "
        "with author, title, source, year, and relevance score."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search terms (e.g. 'claims reserving', 'Solvency II', 'mortalité')",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default 10)",
            },
            "search_order": {
                "type": "integer",
                "description": "Sort order: 1 = by relevance (default), 2 = by date",
            },
        },
        "required": ["query"],
    },
)

# All custom tools exposed to the MCP protocol
CUSTOM_TOOLS = [
    VIEW_GRAPH_TOOL,
    GRAPH_TO_MERMAID_TOOL,
    GRAPH_STATS_TOOL,
    COMPARE_GRAPHS_TOOL,
    EXPORT_ENV_REPORT_TOOL,
    MARKDOWN_TO_PDF_TOOL,
    RICH_PDF_REPORT_TOOL,
    ACTUARIAL_SEARCH_TOOL,
]


# ── Handlers ─────────────────────────────────────────────────────────────────

async def _handle_view_graph(args: dict) -> list[TextContent]:
    env_id = args["env_id"]
    doc_id = args["document_id"]
    doc_name = args.get("document_name", "Document")
    url = f"{_api_base}/document-graph/{env_id}/{doc_id}"

    async with httpx.AsyncClient(timeout=30) as client:
        data = await _authed_get(client, url)

    path = graph_viewer.open_graph_viewer(data, doc_name)
    node_count = len(data.get("graphData", {}).get("nodes", []))
    edge_count = len(data.get("graphData", {}).get("edges", []))

    return [TextContent(
        type="text",
        text=(
            f"Graph viewer opened in browser.\n"
            f"Nodes: {node_count}, Edges: {edge_count}\n"
            f"File: {path}"
        ),
    )]


async def _handle_graph_to_mermaid(args: dict) -> list[TextContent]:
    data = await _fetch_graph(args["env_id"], args["document_id"])
    mermaid = custom_tools.graph_to_mermaid(data)
    url = custom_tools.open_mermaid_viewer(mermaid)
    return [TextContent(
        type="text",
        text=f"Mermaid viewer opened in browser.\nURL: {url}\n\n```mermaid\n{mermaid}\n```",
    )]


async def _handle_graph_stats(args: dict) -> list[TextContent]:
    data = await _fetch_graph(args["env_id"], args["document_id"])
    stats = custom_tools.graph_stats(data)
    return [TextContent(type="text", text=stats)]


async def _handle_compare_graphs(args: dict) -> list[TextContent]:
    env_id = args["env_id"]
    graph_a = await _fetch_graph(env_id, args["document_id_a"])
    graph_b = await _fetch_graph(env_id, args["document_id_b"])
    name_a = args.get("document_name_a", "Document A")
    name_b = args.get("document_name_b", "Document B")
    result = custom_tools.compare_document_graphs(graph_a, name_a, graph_b, name_b)
    return [TextContent(type="text", text=result)]


async def _handle_export_env_report(args: dict) -> list[TextContent]:
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

    report = custom_tools.export_environment_report(environment, flat_docs, graphs)
    return [TextContent(type="text", text=report)]


async def _handle_create_pdf_report(args: dict) -> list[TextContent]:
    md = args["markdown_content"]
    title = args.get("title", "Report")
    filename = args.get("filename")
    path = pdf_report.markdown_to_pdf(md, title=title, filename=filename)
    return [TextContent(type="text", text=f"PDF report saved to: {path}")]


async def _handle_rich_pdf_report(args: dict) -> list[TextContent]:
    md = args["markdown_content"]
    title = args.get("title", "Report")
    filename = args.get("filename")
    path = rich_report.markdown_to_rich_pdf(md, title=title, filename=filename)
    return [TextContent(type="text", text=f"Rich PDF report saved to: {path}")]


async def _handle_actuarial_search(args: dict) -> list[TextContent]:
    query = args["query"]
    max_results = args.get("max_results", 10)
    search_order = args.get("search_order", 1)
    results = await actuarial_search.search_actuarial_library(
        query, max_results=max_results, search_order=search_order,
    )
    text = actuarial_search.format_results(results, query)
    return [TextContent(type="text", text=text)]


# Map tool name → handler
CUSTOM_HANDLERS = {
    "view_document_graph":       _handle_view_graph,
    "graph_to_mermaid":          _handle_graph_to_mermaid,
    "graph_stats":               _handle_graph_stats,
    "compare_document_graphs":   _handle_compare_graphs,
    "export_environment_report": _handle_export_env_report,
    "create_pdf_report":         _handle_create_pdf_report,
    "create_rich_pdf_report":    _handle_rich_pdf_report,
    "search_actuarial_library":  _handle_actuarial_search,
}
