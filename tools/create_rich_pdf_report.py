"""Tool: create_rich_pdf_report

Generate a rich PDF report from markdown with support for LaTeX math,
Mermaid diagrams, and embedded images.
"""

import base64
import mimetypes
import os
import re
import subprocess
import tempfile
from pathlib import Path

import markdown
import latex2mathml.converter
from mcp.types import Tool, TextContent
from weasyprint import HTML

_LOGO_PATH = Path(__file__).resolve().parent.parent / "Dylogy_logo.svg"


# ── Tool definition ──────────────────────────────────────────────────────────
TOOL = Tool(
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


# ── Handler ──────────────────────────────────────────────────────────────────
async def handle(args: dict) -> list[TextContent]:
    md = args["markdown_content"]
    title = args.get("title", "Report")
    filename = args.get("filename")
    path = markdown_to_rich_pdf(md, title=title, filename=filename)
    return [TextContent(type="text", text=f"Rich PDF report saved to: {path}")]


# ── Math rendering ───────────────────────────────────────────────────────────

_INLINE_MATH_RE = re.compile(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)")
_BLOCK_MATH_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)


def _latex_to_mathml(latex: str, block: bool = False) -> str:
    """Convert a LaTeX expression to MathML."""
    try:
        mathml = latex2mathml.converter.convert(latex.strip())
        if block:
            mathml = f'<div class="math-block">{mathml}</div>'
        else:
            mathml = f'<span class="math-inline">{mathml}</span>'
        return mathml
    except Exception:
        tag = "div" if block else "span"
        return f'<{tag} class="math-fallback"><code>{latex.strip()}</code></{tag}>'


def _render_math(md_content: str) -> str:
    """Replace $...$ and $$...$$ with MathML in the markdown source."""
    def _replace_block(m):
        return _latex_to_mathml(m.group(1), block=True)

    def _replace_inline(m):
        return _latex_to_mathml(m.group(1), block=False)

    md_content = _BLOCK_MATH_RE.sub(_replace_block, md_content)
    md_content = _INLINE_MATH_RE.sub(_replace_inline, md_content)
    return md_content


# ── Mermaid rendering ────────────────────────────────────────────────────────

_MERMAID_BLOCK_RE = re.compile(
    r"```mermaid\s*\n(.*?)```", re.DOTALL
)


def _render_mermaid_to_svg(mermaid_code: str) -> str | None:
    """Render a Mermaid diagram to SVG using mmdc CLI."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".mmd", delete=False
    ) as mmd_file:
        mmd_file.write(mermaid_code)
        mmd_path = mmd_file.name

    svg_path = mmd_path.replace(".mmd", ".svg")

    config_path = mmd_path.replace(".mmd", ".json")
    Path(config_path).write_text(
        '{"htmlLabels":false,"flowchart":{"htmlLabels":false,"useMaxWidth":false}}'
    )

    try:
        result = subprocess.run(
            [
                "mmdc", "-i", mmd_path, "-o", svg_path,
                "-b", "transparent", "-c", config_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and os.path.exists(svg_path):
            svg_content = Path(svg_path).read_text()
            return svg_content
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    finally:
        for p in (mmd_path, svg_path, config_path):
            if os.path.exists(p):
                os.unlink(p)


def _render_mermaid(md_content: str) -> str:
    """Replace ```mermaid blocks with inline SVG (or fallback code block)."""
    def _replace(m):
        code = m.group(1)
        svg = _render_mermaid_to_svg(code)
        if svg:
            return f'<div class="mermaid-diagram">{svg}</div>'
        return f"```\n{code}```"

    return _MERMAID_BLOCK_RE.sub(_replace, md_content)


# ── Image embedding ──────────────────────────────────────────────────────────

_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def _embed_image(match) -> str:
    """Convert a markdown image reference to a base64 data URI."""
    alt = match.group(1)
    src = match.group(2)

    if src.startswith("data:") or src.startswith("http"):
        return match.group(0)

    path = Path(src).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path

    if not path.exists():
        return match.group(0)

    mime, _ = mimetypes.guess_type(str(path))
    if mime is None:
        mime = "application/octet-stream"

    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f'![{alt}](data:{mime};base64,{b64})'


def _embed_images(md_content: str) -> str:
    """Embed local images as base64 data URIs."""
    return _IMG_RE.sub(_embed_image, md_content)


# ── HTML builder ─────────────────────────────────────────────────────────────

def _get_logo_svg() -> str:
    svg = _LOGO_PATH.read_text()
    return svg.replace('fill="white"', 'fill="#1e293b"')


def _build_html(body_html: str, title: str) -> str:
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

    /* ── Math ── */
    .math-block {{
        text-align: center;
        margin: 1em 0;
        overflow-x: auto;
    }}

    .math-inline {{
        display: inline;
    }}

    .math-fallback code {{
        color: #7c3aed;
        background-color: #f5f3ff;
    }}

    /* ── Mermaid diagrams ── */
    .mermaid-diagram {{
        text-align: center;
        margin: 1.5em 0;
        page-break-inside: avoid;
    }}

    .mermaid-diagram svg {{
        max-width: 100%;
        height: auto;
    }}

    /* ── Images ── */
    img {{
        max-width: 100%;
        height: auto;
        display: block;
        margin: 1em auto;
    }}

    figure {{
        text-align: center;
        margin: 1.5em 0;
        page-break-inside: avoid;
    }}

    figcaption {{
        font-size: 9.5pt;
        color: #64748b;
        margin-top: 0.5em;
    }}
</style>
</head>
<body>
    <div class="running-header">{logo_svg}</div>
    {body_html}
</body>
</html>"""


# ── Public API ───────────────────────────────────────────────────────────────

def markdown_to_rich_pdf(
    md_content: str,
    title: str = "Report",
    filename: str | None = None,
) -> str:
    """Convert markdown (with math, mermaid, images) to a styled PDF.

    Returns the absolute path to the generated PDF file.
    """
    md_content = _embed_images(md_content)
    md_content = _render_mermaid(md_content)
    md_content = _render_math(md_content)

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
        fd, output_path = tempfile.mkstemp(suffix=".pdf", prefix="dylogy_rich_report_")
        os.close(fd)

    HTML(string=html_str, base_url=str(_LOGO_PATH.parent)).write_pdf(output_path)

    return output_path
