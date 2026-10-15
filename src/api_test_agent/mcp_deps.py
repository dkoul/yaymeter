"""Optional MCP SDK dependency."""

from __future__ import annotations

from typing import Any


def require_mcp_sdk() -> Any:
    try:
        import mcp  # noqa: F401
        from mcp import Client

        return Client
    except ImportError as exc:
        raise ImportError(
            "MCP support requires the mcp package. Install with: pip install 'yaymeter[mcp]'"
        ) from exc
