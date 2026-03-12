"""Tool: create_pdf_report

Generate a styled PDF report from markdown content.
"""

import os
import tempfile
from pathlib import Path

import markdown
from mcp.types import Tool, TextContent
from weasyprint import HTML

_LOGO_PATH = Path(__file__).resolve().parent.parent / "Dylogy_logo.svg"


# ── Tool definition ──────────────────────────────────────────────────────────
TOOL = Tool(
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


# ── Handler ──────────────────────────────────────────────────────────────────
async def handle(args: dict) -> list[TextContent]:
    md = args["markdown_content"]
    title = args.get("title", "Report")
    filename = args.get("filename")
    path = markdown_to_pdf(md, title=title, filename=filename)
    return [TextContent(type="text", text=f"PDF report saved to: {path}")]


# ── Implementation ───────────────────────────────────────────────────────────
def _get_logo_svg() -> str:
    """Read the Dylogy logo SVG, recoloured for print (dark on white)."""
    svg = _LOGO_PATH.read_text()
    return svg.replace('fill="white"', 'fill="#1e293b"')


def _build_html(body_html: str, title: str) -> str:
    """Wrap converted HTML body in a full page with print styles."""
    logo_svg = _get_logo_svg()

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
    @page {{
        size: A4;
        margin: 2.5cm 2cm 2cm 2cm;

        @top-left {{
            content: element(running-header);
        }}

        @bottom-center {{
            content: "Page " counter(page) " of " counter(pages);
            font-family: 'Helvetica Neue', Arial, sans-serif;
            font-size: 9pt;
            color: #64748b;
        }}
    }}

    .running-header {{
        position: running(running-header);
        border-bottom: 1px solid #e2e8f0;
        padding-bottom: 6px;
    }}

    .running-header svg {{
        height: 22px;
        width: auto;
    }}

    body {{
        font-family: 'Helvetica Neue', Arial, sans-serif;
        font-size: 11pt;
        line-height: 1.6;
        color: #1e293b;
    }}

    h1 {{
        font-size: 20pt;
        color: #0f172a;
        border-bottom: 2px solid #3b82f6;
        padding-bottom: 6px;
        margin-top: 1.5em;
    }}

    h2 {{
        font-size: 16pt;
        color: #1e40af;
        margin-top: 1.2em;
    }}

    h3 {{
        font-size: 13pt;
        color: #1e3a5f;
        margin-top: 1em;
    }}

    table {{
        width: 100%;
        border-collapse: collapse;
        margin: 1em 0;
        font-size: 10pt;
    }}

    th {{
        background-color: #f1f5f9;
        border: 1px solid #cbd5e1;
        padding: 8px 10px;
        text-align: left;
        font-weight: 600;
    }}

    td {{
        border: 1px solid #e2e8f0;
        padding: 6px 10px;
    }}

    tr:nth-child(even) {{
        background-color: #f8fafc;
    }}

    code {{
        background-color: #f1f5f9;
        padding: 2px 5px;
        border-radius: 3px;
        font-size: 9.5pt;
        font-family: 'Courier New', monospace;
    }}

    pre {{
        background-color: #f1f5f9;
        padding: 12px;
        border-radius: 4px;
        border: 1px solid #e2e8f0;
        overflow-x: auto;
    }}

    pre code {{
        padding: 0;
        background: none;
    }}

    blockquote {{
        border-left: 3px solid #3b82f6;
        margin-left: 0;
        padding-left: 1em;
        color: #475569;
    }}

    ul, ol {{
        padding-left: 1.5em;
    }}

    strong {{
        color: #0f172a;
    }}

    hr {{
        border: none;
        border-top: 1px solid #e2e8f0;
        margin: 1.5em 0;
    }}
</style>
</head>
<body>
    <div class="running-header">{logo_svg}</div>
    {body_html}
</body>
</html>"""


def markdown_to_pdf(
    md_content: str,
    title: str = "Report",
    filename: str | None = None,
) -> str:
    """Convert markdown to a styled PDF with Dylogy header and page numbers.

    Returns the absolute path to the generated PDF file.
    """
    body_html = markdown.markdown(
        md_content,
        extensions=["tables", "fenced_code"],
    )

    html_str = _build_html(body_html, title)

    if filename:
        if not filename.endswith(".pdf"):
            filename += ".pdf"
        output_path = os.path.join(tempfile.gettempdir(), filename)
    else:
        fd, output_path = tempfile.mkstemp(suffix=".pdf", prefix="dylogy_report_")
        os.close(fd)

    HTML(string=html_str, base_url=str(_LOGO_PATH.parent)).write_pdf(output_path)

    return output_path
