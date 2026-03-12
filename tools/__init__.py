"""
Custom MCP tools package.

Each tool lives in its own module with a TOOL definition and handle() function.
This __init__ collects them all and provides init() to wire up auth.
"""

from tools import (
    view_document_graph,
    graph_to_mermaid,
    graph_stats,
    compare_document_graphs,
    export_environment_report,
    create_pdf_report,
    create_rich_pdf_report,
    search_actuarial_library,
)

# All tool modules (each has TOOL and handle)
_MODULES = [
    view_document_graph,
    graph_to_mermaid,
    graph_stats,
    compare_document_graphs,
    export_environment_report,
    create_pdf_report,
    create_rich_pdf_report,
    search_actuarial_library,
]

# Collected definitions for the MCP protocol
CUSTOM_TOOLS = [m.TOOL for m in _MODULES]

# Map tool name → handler
CUSTOM_HANDLERS = {m.TOOL.name: m.handle for m in _MODULES}


def init(api_base: str, get_token_fn, authed_get_fn):
    """Wire up auth functions into each tool module that needs them."""
    # Tools that need authed_get (graph fetching)
    for mod in [view_document_graph, graph_to_mermaid, graph_stats, compare_document_graphs]:
        mod.init(api_base, authed_get_fn)

    # export_environment_report needs get_token (makes its own requests)
    export_environment_report.init(api_base, get_token_fn)
