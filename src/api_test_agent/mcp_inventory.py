"""Build ApiInventory from a live MCP server."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shlex
from typing import Any

from api_test_agent.mcp_deps import require_mcp_sdk
from api_test_agent.models import (
    ApiInventory,
    McpTransportConfig,
    OperationModel,
    ResponseModel,
)


class McpInventoryError(Exception):
    pass


def _inventory_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def _tool_safety_hints(tool: Any) -> tuple[bool | None, bool | None]:
    read_only = None
    destructive = None
    ann = getattr(tool, "annotations", None) or getattr(tool, "toolAnnotations", None)
    if ann is not None:
        read_only = getattr(ann, "readOnlyHint", None)
        destructive = getattr(ann, "destructiveHint", None)
    return read_only, destructive


def _tool_to_operation(tool: Any) -> OperationModel:
    name = tool.name
    input_schema = getattr(tool, "inputSchema", None) or {}
    if hasattr(input_schema, "model_dump"):
        input_schema = input_schema.model_dump(mode="json", exclude_none=True)
    output_schema = getattr(tool, "outputSchema", None)
    if output_schema is not None and hasattr(output_schema, "model_dump"):
        output_schema = output_schema.model_dump(mode="json", exclude_none=True)

    responses = [
        ResponseModel(
            status_code="200",
            description="Successful tool result",
            content_types=["application/json"],
            inline_schema=output_schema,
        )
    ]
    read_only, destructive = _tool_safety_hints(tool)
    return OperationModel(
        operation_id=name,
        method="MCP",
        path=f"/mcp/tools/{name}",
        summary=getattr(tool, "description", None),
        mcp_tool_name=name,
        mcp_description=getattr(tool, "description", None),
        mcp_read_only_hint=read_only,
        mcp_destructive_hint=destructive,
        request_body_content_types=["application/json"],
        request_body_schema=input_schema if input_schema else None,
        responses=responses,
        tags=["mcp-tool"],
    )


async def _fetch_tools_async(transport: McpTransportConfig) -> tuple[list[Any], dict[str, Any] | None]:
    Client = require_mcp_sdk()
    from mcp.client.stdio import StdioServerParameters

    if transport.kind == "streamable_http":
        if not transport.url:
            raise McpInventoryError("streamable_http transport requires url")
        server: Any = transport.url
    else:
        if not transport.command:
            raise McpInventoryError("stdio transport requires command")
        server = StdioServerParameters(
            command=transport.command[0],
            args=transport.command[1:],
        )

    async with Client(server) as client:
        tools: list[Any] = []
        cursor: str | None = None
        while True:
            page = await client.list_tools(cursor=cursor, cache_mode="refresh")
            tools.extend(page.tools)
            cursor = getattr(page, "nextCursor", None) or getattr(page, "next_cursor", None)
            if not cursor:
                break

        caps = None
        session = getattr(client, "session", None)
        if session is not None:
            get_caps = getattr(session, "get_server_capabilities", None)
            if callable(get_caps):
                raw = get_caps()
                if hasattr(raw, "model_dump"):
                    caps = raw.model_dump(mode="json", exclude_none=True)
                elif isinstance(raw, dict):
                    caps = raw
        return tools, caps


def fetch_mcp_inventory(
    transport: McpTransportConfig,
    title: str | None = None,
) -> ApiInventory:
    """Connect to MCP server, list tools (paginated), return ApiInventory."""
    tools, caps = asyncio.run(_fetch_tools_async(transport))
    operations = [_tool_to_operation(t) for t in tools]
    payload = {
        "transport": transport.model_dump(mode="json"),
        "tools": [t.name for t in tools],
        "capabilities": caps,
    }
    endpoint = transport.url or " ".join(transport.command)
    return ApiInventory(
        inventory_kind="mcp",
        title=title or "MCP Server",
        openapi_version="mcp",
        spec_hash=_inventory_hash(payload),
        servers=[endpoint] if endpoint else [],
        operations=operations,
        mcp_transport=transport,
        mcp_server_capabilities=caps,
    )


def parse_stdio_command(command_line: str) -> list[str]:
    return shlex.split(command_line.strip())


def transport_from_cli(mcp_url: str | None, mcp_stdio: str | None) -> McpTransportConfig:
    if mcp_url and mcp_stdio:
        raise McpInventoryError("Use only one of --mcp-url or --mcp-stdio")
    if mcp_url:
        return McpTransportConfig(kind="streamable_http", url=mcp_url.strip())
    if mcp_stdio:
        parts = parse_stdio_command(mcp_stdio)
        if not parts:
            raise McpInventoryError("Empty --mcp-stdio command")
        return McpTransportConfig(kind="stdio", command=parts)
    raise McpInventoryError("Provide --mcp-url or --mcp-stdio")
