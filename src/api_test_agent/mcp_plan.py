"""Test plan generation for MCP inventories."""

from __future__ import annotations

import random
from api_test_agent.config import AgentConfig
from api_test_agent.mcp_protocol import generate_protocol_cases
from api_test_agent.mcp_safety import classify_mcp_operation, mcp_mutation_requires_approval
from api_test_agent.mcp_security import generate_metadata_security_cases
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
    TestPlan,
    TestRequest,
    utc_now_iso,
)
from api_test_agent.test_design import _minimal_json_from_schema, _slug


def _test_id(category: str, operation_id: str, suffix: str) -> str:
    return f"{category}_{_slug(operation_id)}_{suffix}"


def generate_mcp_plan(inventory: ApiInventory, config: AgentConfig) -> TestPlan:
    if not inventory.mcp_transport:
        raise ValueError("MCP inventory missing mcp_transport")

    rng = random.Random(config.seed)
    cases: list[TestCase] = []
    order = 0

    for op in inventory.operations:
        safety = classify_mcp_operation(op)
        requires_approval = mcp_mutation_requires_approval(op)
        if config.disposable_test_environment and config.allow_mutations and safety != SafetyClass.READ_ONLY:
            requires_approval = False

        body = _minimal_json_from_schema(op.request_body_schema, rng)
        output_schema = None
        for r in op.responses:
            if r.inline_schema:
                output_schema = r.inline_schema
                break

        order += 1
        cases.append(
            TestCase(
                test_id=_test_id("positive", op.operation_id, "minimal"),
                operation_id=op.operation_id,
                order=order,
                category=TestCategory.POSITIVE,
                request=TestRequest(
                    method="MCP",
                    path=op.path,
                    mcp_tool=op.mcp_tool_name or op.operation_id,
                    mcp_arguments=body if isinstance(body, dict) else {"value": body},
                ),
                expected=TestExpected(
                    mcp_is_error=False,
                    response_schema=output_schema,
                ),
                expectation_source=ExpectationSource.OPENAPI,
                rationale="Minimal arguments from tool inputSchema",
                risk=RiskLevel.MEDIUM if requires_approval else RiskLevel.LOW,
                priority=30,
                safety_class=safety,
                requires_approval=requires_approval,
                coverage_targets=CoverageTargets(operation=True),
            )
        )

        if op.request_body_schema and isinstance(op.request_body_schema, dict):
            req = op.request_body_schema.get("required", [])
            if req:
                bad = _minimal_json_from_schema(op.request_body_schema, rng)
                if isinstance(bad, dict) and req[0] in bad:
                    del bad[req[0]]
                order += 1
                cases.append(
                    TestCase(
                        test_id=_test_id("negative", op.operation_id, "missing_required"),
                        operation_id=op.operation_id,
                        order=order,
                        category=TestCategory.NEGATIVE,
                        request=TestRequest(
                            method="MCP",
                            path=op.path,
                            mcp_tool=op.mcp_tool_name or op.operation_id,
                            mcp_arguments=bad if isinstance(bad, dict) else {},
                        ),
                        expected=TestExpected(mcp_expect_error=True, mcp_is_error=True),
                        expectation_source=ExpectationSource.OPENAPI,
                        rationale=f"Omit required field {req[0]!r}",
                        risk=RiskLevel.LOW,
                        priority=40,
                        safety_class=safety,
                        requires_approval=requires_approval,
                        coverage_targets=CoverageTargets(
                            parameters=[req[0]],
                            schema_constraints=["required"],
                        ),
                    )
                )

    cases.extend(
        generate_protocol_cases(inventory.mcp_server_capabilities, order_start=order + 1)
    )
    order = max(t.order for t in cases) if cases else order
    cases.extend(generate_metadata_security_cases(inventory, order_start=order + 1))

    base = inventory.servers[0] if inventory.servers else "mcp://local"
    return TestPlan(
        transport="mcp",
        spec_hash=inventory.spec_hash,
        config_hash=config.config_hash(),
        seed=config.seed,
        generator_version=config.generator_version,
        base_url=base,
        created_at=utc_now_iso(),
        mcp_transport=inventory.mcp_transport,
        test_cases=cases,
    )
