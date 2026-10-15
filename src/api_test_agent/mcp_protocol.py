"""MCP protocol conformance test cases (issue #16)."""

from __future__ import annotations

from api_test_agent.models import (
    CoverageTargets,
    ExpectationSource,
    RiskLevel,
    SafetyClass,
    TestCase,
    TestCategory,
    TestExpected,
    TestRequest,
)


def generate_protocol_cases(
    capabilities: dict | None,
    order_start: int,
) -> list[TestCase]:
    cases: list[TestCase] = []
    order = order_start
    op_id = "mcp.protocol"

    order += 1
    cases.append(
        TestCase(
            test_id="mcp_protocol_initialize_negotiation",
            operation_id=op_id,
            order=order,
            category=TestCategory.MCP_PROTOCOL,
            request=TestRequest(
                method="MCP",
                path="/mcp/protocol",
                mcp_protocol_step="initialize_capabilities",
            ),
            expected=TestExpected(mcp_expect_error=False),
            expectation_source=ExpectationSource.PROJECT_POLICY,
            rationale="Server returns negotiated capabilities after initialize",
            risk=RiskLevel.LOW,
            priority=5,
            safety_class=SafetyClass.READ_ONLY,
            requires_approval=False,
            coverage_targets=CoverageTargets(operation=True),
        )
    )

    order += 1
    cases.append(
        TestCase(
            test_id="mcp_protocol_unknown_tool",
            operation_id=op_id,
            order=order,
            category=TestCategory.MCP_PROTOCOL,
            request=TestRequest(
                method="MCP",
                path="/mcp/protocol",
                mcp_protocol_step="call_unknown_tool",
            ),
            expected=TestExpected(mcp_expect_error=True, mcp_is_error=True),
            expectation_source=ExpectationSource.PROJECT_POLICY,
            rationale="Unknown tool name returns a JSON-RPC / MCP error",
            risk=RiskLevel.LOW,
            priority=6,
            safety_class=SafetyClass.READ_ONLY,
            requires_approval=False,
        )
    )

    order += 1
    cases.append(
        TestCase(
            test_id="mcp_protocol_invalid_params",
            operation_id=op_id,
            order=order,
            category=TestCategory.MCP_PROTOCOL,
            request=TestRequest(
                method="MCP",
                path="/mcp/protocol",
                mcp_protocol_step="invalid_tool_arguments",
            ),
            expected=TestExpected(
                mcp_expect_error=True,
                mcp_jsonrpc_error_code=-32602,
            ),
            expectation_source=ExpectationSource.PROJECT_POLICY,
            rationale="Invalid tool arguments should yield invalid-params style errors",
            risk=RiskLevel.LOW,
            priority=7,
            safety_class=SafetyClass.READ_ONLY,
            requires_approval=False,
        )
    )

    if capabilities and capabilities.get("resources"):
        order += 1
        cases.append(
            TestCase(
                test_id="mcp_protocol_resources_list",
                operation_id=op_id,
                order=order,
                category=TestCategory.MCP_PROTOCOL,
                request=TestRequest(
                    method="MCP",
                    path="/mcp/protocol",
                    mcp_protocol_step="resources_list",
                ),
                expected=TestExpected(mcp_expect_error=False),
                expectation_source=ExpectationSource.PROJECT_POLICY,
                rationale="resources/list works when capability is advertised",
                risk=RiskLevel.LOW,
                priority=8,
                safety_class=SafetyClass.READ_ONLY,
                requires_approval=False,
            )
        )

    if capabilities and capabilities.get("prompts"):
        order += 1
        cases.append(
            TestCase(
                test_id="mcp_protocol_prompts_list",
                operation_id=op_id,
                order=order,
                category=TestCategory.MCP_PROTOCOL,
                request=TestRequest(
                    method="MCP",
                    path="/mcp/protocol",
                    mcp_protocol_step="prompts_list",
                ),
                expected=TestExpected(mcp_expect_error=False),
                expectation_source=ExpectationSource.PROJECT_POLICY,
                rationale="prompts/list works when capability is advertised",
                risk=RiskLevel.LOW,
                priority=9,
                safety_class=SafetyClass.READ_ONLY,
                requires_approval=False,
            )
        )

    return cases
