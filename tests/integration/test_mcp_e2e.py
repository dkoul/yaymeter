"""MCP plan and in-process execution."""

import pytest

pytest.importorskip("mcp")

from mcp import Client
from mcp.server.mcpserver import MCPServer

from api_test_agent.config import AgentConfig
from api_test_agent.mcp_executor import _run_tool_case
from api_test_agent.mcp_inventory import _tool_to_operation
from api_test_agent.mcp_plan import generate_mcp_plan
from api_test_agent.models import (
    ApiInventory,
    AssertionOutcome,
    McpTransportConfig,
    TestCategory,
)

mcp_server = MCPServer("yaymeter-e2e")


@mcp_server.tool()
def echo(message: str) -> str:
    """Echo a message."""
    return message


@pytest.mark.integration
def test_mcp_plan_and_tool_call():
    import asyncio

    async def _run():
        async with Client(mcp_server) as client:
            page = await client.list_tools()
            operations = [_tool_to_operation(t) for t in page.tools]
            inv = ApiInventory(
                inventory_kind="mcp",
                title="e2e",
                openapi_version="mcp",
                spec_hash="test",
                servers=["inproc"],
                operations=operations,
                mcp_transport=McpTransportConfig(kind="stdio", command=["true"]),
            )
            cfg = AgentConfig(base_url="http://127.0.0.1:1", allowed_hosts=["127.0.0.1"])
            plan = generate_mcp_plan(inv, cfg)
            assert plan.transport == "mcp"
            positive = next(t for t in plan.test_cases if t.category == TestCategory.POSITIVE)
            assertions = await _run_tool_case(client, positive)
            return assertions

    assertions = asyncio.run(_run())
    assert any(a.outcome == AssertionOutcome.PASS for a in assertions)
