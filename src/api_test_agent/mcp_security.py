"""MCP tool metadata security checks (issue #18)."""

from __future__ import annotations

import re

from api_test_agent.models import (
    ApiInventory,
    CoverageTargets,
    ExpectationSource,
    OperationModel,
    RiskLevel,
    SafetyClass,
    TestCase,
    TestCategory,
    TestExpected,
    TestRequest,
)

INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
    re.compile(r"disregard\s+(the\s+)?(above|prior)", re.I),
    re.compile(r"system\s+prompt", re.I),
    re.compile(r"<\s*script", re.I),
)


def scan_tool_metadata(op: OperationModel) -> list[str]:
    findings: list[str] = []
    text = " ".join(filter(None, [op.mcp_tool_name, op.mcp_description, op.summary]))
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            findings.append(f"pattern:{pattern.pattern}")
    if op.mcp_tool_name and len(op.mcp_tool_name) > 128:
        findings.append("tool_name_too_long")
    return findings


def generate_metadata_security_cases(
    inventory: ApiInventory,
    order_start: int,
) -> list[TestCase]:
    cases: list[TestCase] = []
    order = order_start
    for op in inventory.operations:
        findings = scan_tool_metadata(op)
        if not findings:
            continue
        order += 1
        cases.append(
            TestCase(
                test_id=f"mcp_metadata_{op.operation_id}_injection_risk",
                operation_id=op.operation_id,
                order=order,
                category=TestCategory.MCP_METADATA,
                request=TestRequest(
                    method="MCP",
                    path=f"/mcp/metadata/{op.operation_id}",
                    mcp_protocol_step="metadata_scan",
                ),
                expected=TestExpected(mcp_expect_error=False),
                expectation_source=ExpectationSource.PROJECT_POLICY,
                rationale=f"Tool metadata matched risky patterns: {', '.join(findings)}",
                risk=RiskLevel.MEDIUM,
                priority=20,
                safety_class=SafetyClass.READ_ONLY,
                requires_approval=False,
                coverage_targets=CoverageTargets(operation=True),
                blocked=False,
            )
        )
    return cases
