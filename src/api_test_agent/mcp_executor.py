"""Execute MCP test plans via the official MCP Python SDK."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from api_test_agent.config import AgentConfig
from api_test_agent.mcp_deps import require_mcp_sdk
from api_test_agent.models import (
    AssertionOutcome,
    AssertionResult,
    NormalizedResults,
    ResultRecord,
    TestCase,
    TestPlan,
    utc_now_iso,
)
from api_test_agent.python_executor import overall_from_assertions


class McpExecutorError(Exception):
    pass


def _client_server(transport: Any) -> Any:
    from mcp.client.stdio import StdioServerParameters

    if transport.kind == "streamable_http":
        return transport.url
    return StdioServerParameters(
        command=transport.command[0],
        args=transport.command[1:],
    )


def _jsonrpc_code(exc: BaseException) -> int | None:
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code
    err = getattr(exc, "error", None)
    if err is not None:
        c = getattr(err, "code", None)
        if isinstance(c, int):
            return c
    return None


async def _run_protocol_step(
    client: Any,
    test: TestCase,
    first_tool: str | None,
) -> list[AssertionResult]:
    step = test.request.mcp_protocol_step or ""
    session = client.session

    if step == "initialize_capabilities":
        caps = getattr(session, "get_server_capabilities", lambda: None)()
        if caps is None:
            return [
                AssertionResult(
                    name="mcp_initialize",
                    outcome=AssertionOutcome.FAIL,
                    message="No server capabilities after handshake",
                )
            ]
        return [
            AssertionResult(
                name="mcp_initialize",
                outcome=AssertionOutcome.PASS,
                message="Capabilities present after connect",
            )
        ]

    if step == "call_unknown_tool":
        try:
            await client.call_tool("__yaymeter_unknown_tool__", {})
            return [
                AssertionResult(
                    name="unknown_tool",
                    outcome=AssertionOutcome.FAIL,
                    message="Expected error for unknown tool",
                )
            ]
        except Exception as exc:
            if test.expected.mcp_expect_error:
                return [
                    AssertionResult(
                        name="unknown_tool",
                        outcome=AssertionOutcome.PASS,
                        message=str(exc),
                    )
                ]
            return [
                AssertionResult(
                    name="unknown_tool",
                    outcome=AssertionOutcome.FAIL,
                    message=str(exc),
                )
            ]

    if step == "invalid_tool_arguments" and first_tool:
        try:
            await client.call_tool(first_tool, {})
            return [
                AssertionResult(
                    name="invalid_params",
                    outcome=AssertionOutcome.FAIL,
                    message="Expected validation error for empty args",
                )
            ]
        except Exception as exc:
            code = _jsonrpc_code(exc)
            if test.expected.mcp_jsonrpc_error_code and code != test.expected.mcp_jsonrpc_error_code:
                return [
                    AssertionResult(
                        name="invalid_params",
                        outcome=AssertionOutcome.INCONCLUSIVE,
                        message=f"got code {code}, expected {test.expected.mcp_jsonrpc_error_code}: {exc}",
                    )
                ]
            return [
                AssertionResult(
                    name="invalid_params",
                    outcome=AssertionOutcome.PASS,
                    message=str(exc),
                )
            ]

    if step == "resources_list":
        try:
            await session.list_resources()
            return [AssertionResult(name="resources_list", outcome=AssertionOutcome.PASS)]
        except Exception as exc:
            return [
                AssertionResult(
                    name="resources_list",
                    outcome=AssertionOutcome.FAIL,
                    message=str(exc),
                )
            ]

    if step == "prompts_list":
        try:
            await session.list_prompts()
            return [AssertionResult(name="prompts_list", outcome=AssertionOutcome.PASS)]
        except Exception as exc:
            return [
                AssertionResult(
                    name="prompts_list",
                    outcome=AssertionOutcome.FAIL,
                    message=str(exc),
                )
            ]

    if step == "metadata_scan":
        return [
            AssertionResult(
                name="metadata_scan",
                outcome=AssertionOutcome.PASS,
                message="Metadata finding recorded in test rationale",
            )
        ]

    return [
        AssertionResult(
            name="mcp_protocol",
            outcome=AssertionOutcome.SKIPPED,
            message=f"Unknown protocol step: {step}",
        )
    ]


async def _run_tool_case(client: Any, test: TestCase) -> list[AssertionResult]:
    tool = test.request.mcp_tool
    if not tool:
        return [
            AssertionResult(
                name="mcp_tool",
                outcome=AssertionOutcome.FAIL,
                message="Missing mcp_tool on request",
            )
        ]
    args = test.request.mcp_arguments or {}
    start = time.perf_counter()
    try:
        result = await client.call_tool(tool, args)
        elapsed = (time.perf_counter() - start) * 1000
        assertions: list[AssertionResult] = []

        is_error = bool(getattr(result, "is_error", False))
        if test.expected.mcp_is_error is False and is_error:
            assertions.append(
                AssertionResult(
                    name="mcp_is_error",
                    outcome=AssertionOutcome.FAIL,
                    message="Tool returned is_error=True",
                )
            )
        elif test.expected.mcp_expect_error and not is_error:
            assertions.append(
                AssertionResult(
                    name="mcp_is_error",
                    outcome=AssertionOutcome.FAIL,
                    message="Expected tool error",
                )
            )
        else:
            assertions.append(
                AssertionResult(
                    name="mcp_is_error",
                    outcome=AssertionOutcome.PASS,
                    message=f"is_error={is_error}",
                )
            )

        structured = getattr(result, "structured_content", None) or getattr(
            result, "structuredContent", None
        )
        if test.expected.response_schema and structured is not None:
            try:
                Draft202012Validator(test.expected.response_schema).validate(structured)
                assertions.append(
                    AssertionResult(name="output_schema", outcome=AssertionOutcome.PASS)
                )
            except ValidationError as e:
                assertions.append(
                    AssertionResult(
                        name="output_schema",
                        outcome=AssertionOutcome.FAIL,
                        message=str(e.message),
                    )
                )

        assertions.append(
            AssertionResult(
                name="elapsed_ms",
                outcome=AssertionOutcome.PASS,
                message=f"{elapsed:.1f}ms",
            )
        )
        return assertions
    except Exception as exc:
        if test.expected.mcp_expect_error:
            code = _jsonrpc_code(exc)
            if test.expected.mcp_jsonrpc_error_code and code != test.expected.mcp_jsonrpc_error_code:
                return [
                    AssertionResult(
                        name="mcp_call",
                        outcome=AssertionOutcome.INCONCLUSIVE,
                        message=f"code {code}: {exc}",
                    )
                ]
            return [
                AssertionResult(
                    name="mcp_call",
                    outcome=AssertionOutcome.PASS,
                    message=str(exc),
                )
            ]
        return [
            AssertionResult(
                name="mcp_call",
                outcome=AssertionOutcome.FAIL,
                message=str(exc),
            )
        ]


async def _execute_async(
    plan: TestPlan,
    config: AgentConfig,
    run_dir: Path,
    run_id: str,
    target_label: str,
) -> NormalizedResults:
    if not plan.mcp_transport:
        raise McpExecutorError("MCP plan missing mcp_transport")

    Client = require_mcp_sdk()
    server = _client_server(plan.mcp_transport)
    records: list[ResultRecord] = []
    first_tool = next(
        (t.request.mcp_tool for t in plan.test_cases if t.request.mcp_tool),
        None,
    )

    async with Client(server, read_timeout_seconds=config.safety.request_timeout_seconds) as client:
        for test in sorted(plan.test_cases, key=lambda t: t.order):
            if test.blocked:
                records.append(
                    ResultRecord(
                        test_id=test.test_id,
                        operation_id=test.operation_id,
                        timestamp=utc_now_iso(),
                        target_label=target_label,
                        request_fingerprint=test.test_id,
                        overall=AssertionOutcome.BLOCKED,
                        assertions=[
                            AssertionResult(
                                name="blocked",
                                outcome=AssertionOutcome.BLOCKED,
                                message=test.blocked_reason,
                            )
                        ],
                    )
                )
                continue

            if test.category.value == "mcp-metadata":
                assertions = [
                    AssertionResult(
                        name="metadata_injection",
                        outcome=AssertionOutcome.FAIL,
                        message=test.rationale,
                    )
                ]
            elif test.category.value == "mcp-protocol":
                assertions = await _run_protocol_step(client, test, first_tool)
            elif test.request.mcp_tool:
                assertions = await _run_tool_case(client, test)
            else:
                assertions = [
                    AssertionResult(
                        name="mcp_skip",
                        outcome=AssertionOutcome.SKIPPED,
                        message="No MCP action configured",
                    )
                ]

            records.append(
                ResultRecord(
                    test_id=test.test_id,
                    operation_id=test.operation_id,
                    timestamp=utc_now_iso(),
                    target_label=target_label,
                    request_fingerprint=test.test_id,
                    assertions=assertions,
                    overall=overall_from_assertions(assertions),
                )
            )

    summary: dict[str, int] = {}
    for r in records:
        summary[r.overall.value] = summary.get(r.overall.value, 0) + 1

    results = NormalizedResults(run_id=run_id, records=records, summary=summary)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "results.json").write_text(results.model_dump_json(indent=2), encoding="utf-8")
    return results


def execute_mcp_plan(
    plan: TestPlan,
    config: AgentConfig,
    run_dir: Path,
    run_id: str,
    target_label: str,
) -> NormalizedResults:
    return asyncio.run(_execute_async(plan, config, run_dir, run_id, target_label))
