"""
Rich PDF report generation from markdown content.

Supports:
- Standard markdown (tables, code, lists, etc.)
- LaTeX math: $inline$ and $$block$$ expressions
- Mermaid diagrams: ```mermaid code blocks rendered to inline SVG
- Images: local file paths auto-embedded as base64 data URIs
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
from weasyprint import HTML

_LOGO_PATH = Path(__file__).parent / "Dylogy_logo.svg"


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
        # Fallback: show raw LaTeX in a code block
        tag = "div" if block else "span"
        return f'<{tag} class="math-fallback"><code>{latex.strip()}</code></{tag}>'


def _render_math(md_content: str) -> str:
    """Replace $...$ and $$...$$ with MathML in the markdown source."""
    # Block math first (greedy match issues if inline goes first)
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
    """Render a Mermaid diagram to SVG using mmdc CLI.

    Uses htmlLabels:false so text is rendered as native SVG <text> elements
    instead of <foreignObject> (which WeasyPrint cannot render).
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".mmd", delete=False
    ) as mmd_file:
        mmd_file.write(mermaid_code)
        mmd_path = mmd_file.name

    svg_path = mmd_path.replace(".mmd", ".svg")

    # Config to force native SVG text instead of foreignObject HTML
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
        # Fallback: keep as a code block
        return f"```\n{code}```"

    return _MERMAID_BLOCK_RE.sub(_replace, md_content)


# ── Image embedding ──────────────────────────────────────────────────────────

_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def _embed_image(match) -> str:
    """Convert a markdown image reference to a base64 data URI."""
    alt = match.group(1)
    src = match.group(2)

    # Already a data URI or URL — leave as is
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

    Processing pipeline:
    1. Embed local images as base64 data URIs
    2. Render ```mermaid blocks to inline SVG
    3. Convert $...$ and $$...$$ to MathML
    4. Convert remaining markdown to HTML
    5. Wrap in styled HTML template
    6. Render to PDF with WeasyPrint

    Returns the absolute path to the generated PDF file.
    """
    # Step 1: Embed local images
    md_content = _embed_images(md_content)

    # Step 2: Render mermaid diagrams to SVG
    md_content = _render_mermaid(md_content)

    # Step 3: Convert LaTeX math to MathML
    md_content = _render_math(md_content)

    # Step 4: Convert markdown to HTML
    body_html = markdown.markdown(
        md_content,
        extensions=["tables", "fenced_code"],
    )

    # Step 5: Build full HTML
    html_str = _build_html(body_html, title)

    # Step 6: Render to PDF
    if filename:
        if not filename.endswith(".pdf"):
            filename += ".pdf"
        output_path = os.path.join(tempfile.gettempdir(), filename)
    else:
        fd, output_path = tempfile.mkstemp(suffix=".pdf", prefix="dylogy_rich_report_")
        os.close(fd)

    HTML(string=html_str, base_url=str(_LOGO_PATH.parent)).write_pdf(output_path)

    return output_path
