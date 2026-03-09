# Dylogy API MCP

MCP server that auto-generates tools from the Dylogy OpenAPI spec.
Authenticates, fetches the spec, and exposes each API route as a callable tool.

## Setup

```bash
# Install dependencies
uv sync
```

## Add to Claude Code

```bash
claude mcp add dylogy \
  -e DYLOGY_API_BASE="https://dev.dlg-api.com" \
  -e DYLOGY_EMAIL="your-email@dylogy.com" \
  -e DYLOGY_PASSWORD="your-password" \
  -- uv run --directory /path-to/dylogy-mcp python dylogy.py
```

## Verify

```bash
claude mcp list        # check it's registered
claude mcp get dylogy  # check it's healthy
```
