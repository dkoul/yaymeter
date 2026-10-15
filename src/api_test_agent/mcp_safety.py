"""Safety classification for MCP tools."""

from __future__ import annotations

from api_test_agent.models import OperationModel, SafetyClass


def classify_mcp_operation(op: OperationModel) -> SafetyClass:
    if op.mcp_destructive_hint:
        return SafetyClass.DESTRUCTIVE
    if op.mcp_read_only_hint:
        return SafetyClass.READ_ONLY
    return SafetyClass.MUTATION


def mcp_mutation_requires_approval(op: OperationModel) -> bool:
    """Unannotated tools default to mutation (issue #15)."""
    if op.mcp_read_only_hint:
        return False
    return True
