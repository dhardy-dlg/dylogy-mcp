"""
Search the ressources-actuarielles.net actuarial library (ISFA).
"""

import httpx
from html.parser import HTMLParser

SEARCH_URL = (
    "http://www.ressources-actuarielles.net"
    "/C12574E200674F5B/d512ad5b22d73cc1c1257052003f1aed?SearchView"
)

HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/144.0.0.0 Safari/537.36"
    ),
}


class _ResultParser(HTMLParser):
    """Extract search results from the Domino HTML table."""

    def __init__(self):
        super().__init__()
        self.results: list[dict] = []
        self._in_row = False
        self._cells: list[str] = []
        self._current_cell = ""
        self._cell_depth = 0
        self._current_href: str | None = None
        self._row_href: str | None = None
        self._row_score: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attr = dict(attrs)
        if tag == "tr" and attr.get("valign") == "top":
            self._in_row = True
            self._cells = []
            self._current_cell = ""
            self._cell_depth = 0
            self._row_href = None
            self._row_score = None
        elif self._in_row and tag == "td":
            self._cell_depth += 1
            if self._cell_depth == 1:
                self._current_cell = ""
        elif self._in_row and tag == "a" and attr.get("href"):
            self._row_href = attr["href"]
        elif self._in_row and tag == "img":
            alt = attr.get("alt", "")
            if alt and "%" in alt:
                self._row_score = alt

    def handle_endtag(self, tag: str):
        if self._in_row and tag == "td":
            self._cell_depth -= 1
            if self._cell_depth == 0:
                self._cells.append(self._current_cell.strip())
                self._current_cell = ""
        elif self._in_row and tag == "tr":
            self._in_row = False
            self._emit_row()

    def handle_data(self, data: str):
        if self._in_row and self._cell_depth > 0:
            self._current_cell += data

    def _emit_row(self):
        if len(self._cells) < 4:
            return
        # cells: [score_img, author, ??, title, source, year]
        author = self._cells[1] if len(self._cells) > 1 else ""
        title = self._cells[3] if len(self._cells) > 3 else ""
        source = self._cells[4] if len(self._cells) > 4 else ""
        year = self._cells[5] if len(self._cells) > 5 else ""

        base = "http://www.ressources-actuarielles.net"
        href = self._row_href
        if href and not href.startswith("http"):
            href = base + href

        self.results.append({
            "author": author,
            "title": title,
            "source": source,
            "year": year,
            "relevance": self._row_score or "",
            "url": href or "",
        })


async def search_actuarial_library(
    query: str,
    max_results: int = 10,
    search_order: int = 1,
) -> list[dict]:
    """Search ressources-actuarielles.net and return parsed results.

    Args:
        query: Search terms.
        max_results: Maximum number of results (default 10).
        search_order: 1 = by relevance (default), 2 = by date.

    Returns:
        List of dicts with keys: author, title, source, year, relevance, url.
    """
    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        resp = await client.post(
            SEARCH_URL,
            headers=HEADERS,
            data={
                "Query": query,
                "SearchOrder": str(search_order),
                "SearchMax": str(max_results),
            },
        )
        resp.raise_for_status()

    parser = _ResultParser()
    parser.feed(resp.text)
    return parser.results


def format_results(results: list[dict], query: str) -> str:
    """Format search results as markdown."""
    if not results:
        return f"No results found for **{query}**."

    lines = [
        f"## Actuarial Library Search: \"{query}\"",
        f"**{len(results)} result(s) found**",
        "",
        "| # | Author | Title | Source | Year | Relevance |",
        "|---|--------|-------|--------|------|-----------|",
    ]
    for i, r in enumerate(results, 1):
        title = r["title"]
        if r["url"]:
            title = f"[{r['title']}]({r['url']})"
        lines.append(
            f"| {i} | {r['author']} | {title} | {r['source']} | {r['year']} | {r['relevance']} |"
        )

    lines += ["", "*Source: ressources-actuarielles.net (ISFA)*"]
    return "\n".join(lines)
