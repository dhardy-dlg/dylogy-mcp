"""
Dylogy MCP Server
Authenticates, fetches the OpenAPI spec, and registers each route as an MCP tool.
"""

import os
import sys
import httpx
import asyncio
from typing import Any
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

import tool_definitions


def _log(msg: str) -> None:
    """Log to stderr so we don't corrupt the MCP stdio transport."""
    print(msg, file=sys.stderr, flush=True)

# ── Config ────────────────────────────────────────────────────────────────────
DYLOGY_API_BASE = os.environ["DYLOGY_API_BASE"].rstrip("/")
AUTH_ENDPOINT   = f"{DYLOGY_API_BASE}/auth/token"
OPEN_API        = f"{DYLOGY_API_BASE}/openapi.json"

DYLOGY_EMAIL    = os.environ["DYLOGY_EMAIL"]
DYLOGY_PASSWORD = os.environ["DYLOGY_PASSWORD"]

# ── Auth ──────────────────────────────────────────────────────────────────────
_token: str | None = None

async def get_token(client: httpx.AsyncClient) -> str:
    """Authenticate and cache the Bearer token."""
    global _token
    if _token is not None:
        return _token

    resp = await client.post(
        AUTH_ENDPOINT,
        data={"username": DYLOGY_EMAIL, "password": DYLOGY_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp.raise_for_status()
    _token = resp.json()["accessToken"]
    return _token


async def authed_get(client: httpx.AsyncClient, url: str) -> Any:
    """GET with Bearer auth; re-authenticates once on 401."""
    global _token
    token = await get_token(client)
    resp  = await client.get(url, headers={"Authorization": f"Bearer {token}"})

    if resp.status_code == 401:          # token expired → retry once
        _token = None
        token  = await get_token(client)
        resp   = await client.get(url, headers={"Authorization": f"Bearer {token}"})

    resp.raise_for_status()
    return resp.json()


# ── OpenAPI helpers ───────────────────────────────────────────────────────────
def _resolve_ref(schema: dict, components: dict, _seen: set | None = None) -> dict:
    """Recursively inline $ref pointers."""
    if _seen is None:
        _seen = set()

    ref = schema.get("$ref", "")
    if ref.startswith("#/components/schemas/"):
        if ref in _seen:
            return schema
        _seen.add(ref)
        name = ref.split("/")[-1]
        resolved = components.get("schemas", {}).get(name, schema)
        return _resolve_ref(resolved, components, _seen)

    result = dict(schema)

    # Resolve refs inside properties
    if "properties" in result:
        result["properties"] = {
            k: _resolve_ref(v, components, set(_seen))
            for k, v in result["properties"].items()
        }

    # Resolve refs inside array items
    if "items" in result:
        result["items"] = _resolve_ref(result["items"], components, set(_seen))

    # Resolve refs inside anyOf / oneOf / allOf
    for key in ("anyOf", "oneOf", "allOf"):
        if key in result:
            result[key] = [_resolve_ref(s, components, set(_seen)) for s in result[key]]

    return result


def openapi_to_tools(spec: dict) -> list[Tool]:
    """Convert OpenAPI paths → MCP Tool list."""
    components = spec.get("components", {})
    tools: list[Tool] = []

    for path, path_item in spec.get("paths", {}).items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue

            op_id   = operation.get("operationId") or f"{method}_{path.replace('/', '_')}"
            summary = operation.get("summary", "")
            desc    = operation.get("description", summary)

            # Build JSON-schema properties from parameters + requestBody
            properties: dict = {}
            required: list   = []

            for param in operation.get("parameters", []):
                p_name   = param["name"]
                p_schema = _resolve_ref(param.get("schema", {"type": "string"}), components)
                properties[p_name] = {
                    "type":        p_schema.get("type", "string"),
                    "description": f"[{param.get('in','query')}] {param.get('description','')}",
                }
                if param.get("required"):
                    required.append(p_name)

            body = operation.get("requestBody", {})
            if body:
                content  = body.get("content", {})
                mt       = content.get("application/json") or next(iter(content.values()), {})
                b_schema = _resolve_ref(mt.get("schema", {}), components)
                for prop, val in b_schema.get("properties", {}).items():
                    properties[prop] = _resolve_ref(val, components)
                required += b_schema.get("required", [])

            tools.append(Tool(
                name        = op_id,
                description = f"[{method.upper()} {path}] {desc}",
                inputSchema = {
                    "type":       "object",
                    "properties": properties,
                    "required":   list(set(required)),
                },
            ))

    return tools


def build_request(spec: dict, tool_name: str, args: dict) -> tuple[str, str, dict, dict, dict]:
    """Return (method, url, path_params, query_params, body) for a tool call."""
    base_url   = (spec.get("servers") or [{}])[0].get("url", DYLOGY_API_BASE)

    for path, path_item in spec.get("paths", {}).items():
        for method, operation in path_item.items():
            op_id = operation.get("operationId") or f"{method}_{path.replace('/', '_')}"
            if op_id != tool_name:
                continue

            path_params:  dict = {}
            query_params: dict = {}
            body:         dict = {}

            for param in operation.get("parameters", []):
                name = param["name"]
                if name not in args:
                    continue
                if param["in"] == "path":
                    path_params[name]  = args[name]
                elif param["in"] == "query":
                    query_params[name] = args[name]

            if operation.get("requestBody"):
                body = {k: v for k, v in args.items() if k not in path_params and k not in query_params}

            url = base_url.rstrip("/") + path
            for k, v in path_params.items():
                url = url.replace(f"{{{k}}}", str(v))

            return method, url, path_params, query_params, body

    raise ValueError(f"No operation found for tool '{tool_name}'")


# ── MCP Server ────────────────────────────────────────────────────────────────
server = Server("dylogy-mcp")
_spec:  dict        = {}
_tools: list[Tool]  = []


@server.list_tools()
async def list_tools() -> list[Tool]:
    return _tools + tool_definitions.CUSTOM_TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    # Custom tools
    handler = tool_definitions.CUSTOM_HANDLERS.get(name)
    if handler:
        return await handler(arguments)

    # Auto-generated OpenAPI tools
    global _token
    async with httpx.AsyncClient(timeout=30) as client:
        token = await get_token(client)

        try:
            method, url, _, query, body = build_request(_spec, name, arguments)
        except ValueError as e:
            return [TextContent(type="text", text=str(e))]

        req_kwargs: dict = {
            "headers": {"Authorization": f"Bearer {token}"},
            "params":  query,
        }
        if body:
            req_kwargs["json"] = body

        resp = await client.request(method.upper(), url, **req_kwargs)

        # Re-auth once on 401 and retry
        if resp.status_code == 401:
            _token = None
            token = await get_token(client)
            req_kwargs["headers"] = {"Authorization": f"Bearer {token}"}
            resp = await client.request(method.upper(), url, **req_kwargs)

        try:
            result = resp.json()
        except Exception:
            result = resp.text

        return [TextContent(type="text", text=str(result))]


# ── Entrypoint ────────────────────────────────────────────────────────────────
async def main() -> None:
    global _spec, _tools

    # Wire auth functions into tool_definitions
    tool_definitions.init(DYLOGY_API_BASE, get_token, authed_get)

    _log("Authenticating and fetching OpenAPI spec …")
    async with httpx.AsyncClient(timeout=15) as client:
        _spec  = await authed_get(client, OPEN_API)
        _tools = openapi_to_tools(_spec)

    _log(f"Registered {len(_tools)} tools from {len(_spec.get('paths', {}))} paths.")
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())


def main_sync() -> None:
    """Sync wrapper used as the console_scripts entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
