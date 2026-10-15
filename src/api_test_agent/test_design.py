"""Deterministic test case generation."""

from __future__ import annotations

import json
import random
import re
from typing import Any

from api_test_agent.config import AgentConfig
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
from api_test_agent.safety import classify_operation, mutation_requires_approval


def _slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()


def _success_statuses(op: OperationModel) -> list[int]:
    codes: list[int] = []
    for r in op.responses:
        if r.status_code.isdigit():
            code = int(r.status_code)
            if 200 <= code < 300:
                codes.append(code)
        elif r.status_code == "default":
            continue
    return codes or [200]


def _error_statuses(op: OperationModel) -> list[int]:
    codes: list[int] = []
    for r in op.responses:
        if r.status_code.isdigit():
            code = int(r.status_code)
            if code >= 400:
                codes.append(code)
    return codes or [400, 422]


def _minimal_json_from_schema(schema: dict[str, Any] | None, rng: random.Random) -> Any:
    if not schema:
        return {}
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]
    t = schema.get("type")
    if t == "object":
        props = schema.get("properties", {})
        required = schema.get("required", [])
        out: dict[str, Any] = {}
        for key in required:
            if key in props:
                out[key] = _minimal_json_from_schema(props[key], rng)
            else:
                out[key] = "value"
        return out
    if t == "array":
        items = schema.get("items", {})
        return [_minimal_json_from_schema(items, rng)]
    if t == "integer":
        return int(schema.get("minimum", 1))
    if t == "number":
        return float(schema.get("minimum", 1.0))
    if t == "boolean":
        return True
    if t == "string":
        if schema.get("format") == "email":
            return "user@example.com"
        min_len = schema.get("minLength", 1)
        return "a" * max(1, min_len)
    return "test"


def _fill_path(
    path: str,
    op: OperationModel,
    rng: random.Random,
    overrides: dict[str, str] | None = None,
) -> str:
    overrides = overrides or {}
    result = path
    for param in op.parameters:
        if param.location != "path":
            continue
        if param.name in overrides:
            val = overrides[param.name]
        else:
            val = "1"
            if param.enum:
                val = str(param.enum[0])
            elif param.schema_type == "integer":
                val = str(int(param.minimum or 1))
            elif param.schema_type == "string":
                val = "sample"
        result = result.replace("{" + param.name + "}", val)
    return result


def _auth_error_codes(op: OperationModel) -> list[int]:
    codes: list[int] = []
    for r in op.responses:
        if r.status_code in ("401", "403"):
            codes.append(int(r.status_code))
    return codes or [401, 403]


def _test_id(category: str, operation_id: str, suffix: str) -> str:
    return f"{category}_{_slug(operation_id)}_{suffix}"


def generate_plan(inventory: ApiInventory, config: AgentConfig) -> TestPlan:
    if inventory.inventory_kind == "mcp":
        from api_test_agent.mcp_plan import generate_mcp_plan

        return generate_mcp_plan(inventory, config)

    rng = random.Random(config.seed)
    cases: list[TestCase] = []
    order = 0

    for op in inventory.operations:
        safety = classify_operation(op.method)
        success = _success_statuses(op)
        errors = _error_statuses(op)
        success_schema = None
        for r in op.responses:
            if r.status_code in ("200", "201") and r.inline_schema:
                success_schema = r.inline_schema
                break

        # Contract inventory test
        order += 1
        cases.append(
            TestCase(
                test_id=_test_id("contract", op.operation_id, "declared"),
                operation_id=op.operation_id,
                order=order,
                category=TestCategory.CONTRACT,
                request=TestRequest(
                    method=op.method,
                    path=_fill_path(op.path, op, rng),
                ),
                expected=TestExpected(
                    status_codes=success + errors,
                    response_schema=None,
                ),
                expectation_source=ExpectationSource.OPENAPI,
                rationale="Enumerate declared response codes for operation",
                risk=RiskLevel.LOW,
                priority=10,
                safety_class=safety,
                requires_approval=mutation_requires_approval(
                    TestCase(
                        test_id="",
                        operation_id=op.operation_id,
                        order=0,
                        category=TestCategory.CONTRACT,
                        request=TestRequest(method=op.method, path=op.path),
                        expected=TestExpected(),
                        expectation_source=ExpectationSource.OPENAPI,
                        rationale="",
                        risk=RiskLevel.LOW,
                        safety_class=safety,
                    ),
                    config,
                ),
                coverage_targets=CoverageTargets(
                    operation=True,
                    response_statuses=[r.status_code for r in op.responses],
                ),
            )
        )

        # Positive case
        body = None
        blocked = False
        blocked_reason = None
        if op.request_body_schema is not None or op.request_body_content_types:
            body = _minimal_json_from_schema(op.request_body_schema, rng)
        elif op.method in ("POST", "PUT", "PATCH") and not op.request_body_content_types:
            blocked = True
            blocked_reason = "missing request body schema"

        order += 1
        pos = TestCase(
            test_id=_test_id("positive", op.operation_id, "minimal"),
            operation_id=op.operation_id,
            order=order,
            category=TestCategory.POSITIVE,
            request=TestRequest(
                method=op.method,
                path=_fill_path(op.path, op, rng),
                body=body,
            ),
            expected=TestExpected(status_codes=success, response_schema=success_schema),
            expectation_source=ExpectationSource.OPENAPI,
            rationale="Simplest valid request inferred from schema",
            risk=RiskLevel.MEDIUM if safety != SafetyClass.READ_ONLY else RiskLevel.LOW,
            priority=30,
            safety_class=safety,
            requires_approval=mutation_requires_approval(
                TestCase(
                    test_id="",
                    operation_id=op.operation_id,
                    order=0,
                    category=TestCategory.POSITIVE,
                    request=TestRequest(method=op.method, path=op.path),
                    expected=TestExpected(),
                    expectation_source=ExpectationSource.OPENAPI,
                    rationale="",
                    risk=RiskLevel.LOW,
                    safety_class=safety,
                ),
                config,
            ),
            coverage_targets=CoverageTargets(
                operation=True,
                parameters=[p.name for p in op.parameters if p.required],
                response_statuses=[str(c) for c in success],
            ),
            blocked=blocked,
            blocked_reason=blocked_reason,
        )
        cases.append(pos)

        # Negative: missing required field in body
        if op.request_body_schema and isinstance(op.request_body_schema, dict):
            req = op.request_body_schema.get("required", [])
            if req:
                bad_body = _minimal_json_from_schema(op.request_body_schema, rng)
                if isinstance(bad_body, dict) and req[0] in bad_body:
                    del bad_body[req[0]]
                order += 1
                cases.append(
                    TestCase(
                        test_id=_test_id("negative", op.operation_id, "missing_required"),
                        operation_id=op.operation_id,
                        order=order,
                        category=TestCategory.NEGATIVE,
                        request=TestRequest(
                            method=op.method,
                            path=_fill_path(op.path, op, rng),
                            body=bad_body,
                        ),
                        expected=TestExpected(status_codes=errors),
                        expectation_source=ExpectationSource.OPENAPI,
                        rationale=f"Omit required field {req[0]!r}",
                        risk=RiskLevel.LOW,
                        priority=40,
                        safety_class=safety,
                        requires_approval=pos.requires_approval,
                        coverage_targets=CoverageTargets(
                            parameters=[req[0]],
                            schema_constraints=["required"],
                        ),
                    )
                )

        # Boundary: string maxLength if present
        for param in op.parameters:
            if param.max_length is not None:
                order += 1
                long_val = "x" * (param.max_length + 1)
                q: dict[str, str] = {}
                headers: dict[str, str] = {}
                path_overrides: dict[str, str] = {}
                blocked = False
                blocked_reason = None
                if param.location == "query":
                    q[param.name] = long_val
                elif param.location == "path":
                    path_overrides[param.name] = long_val
                elif param.location == "header":
                    headers[param.name] = long_val
                elif param.location == "cookie":
                    blocked = True
                    blocked_reason = "cookie parameters are not supported in JMeter export"

                path = _fill_path(op.path, op, rng, path_overrides)
                cases.append(
                    TestCase(
                        test_id=_test_id("boundary", op.operation_id, f"{param.name}_maxlen"),
                        operation_id=op.operation_id,
                        order=order,
                        category=TestCategory.BOUNDARY,
                        request=TestRequest(
                            method=op.method,
                            path=path,
                            query=q,
                            headers=headers,
                        ),
                        expected=TestExpected(status_codes=errors + success),
                        expectation_source=ExpectationSource.OPENAPI,
                        rationale=f"Exceed maxLength for {param.name}",
                        risk=RiskLevel.LOW,
                        priority=50,
                        safety_class=safety,
                        requires_approval=pos.requires_approval,
                        coverage_targets=CoverageTargets(
                            parameters=[param.name],
                            schema_constraints=["maxLength"],
                        ),
                        blocked=blocked,
                        blocked_reason=blocked_reason,
                    )
                )

        # Negative: wrong type on first required integer property
        if op.request_body_schema and isinstance(op.request_body_schema, dict):
            props = op.request_body_schema.get("properties", {})
            required_fields = op.request_body_schema.get("required", [])
            for field in required_fields:
                field_schema = props.get(field, {})
                if field_schema.get("type") == "integer":
                    bad_body = _minimal_json_from_schema(op.request_body_schema, rng)
                    if isinstance(bad_body, dict):
                        bad_body[field] = "not-an-integer"
                    order += 1
                    cases.append(
                        TestCase(
                            test_id=_test_id("negative", op.operation_id, f"wrong_type_{field}"),
                            operation_id=op.operation_id,
                            order=order,
                            category=TestCategory.NEGATIVE,
                            request=TestRequest(
                                method=op.method,
                                path=_fill_path(op.path, op, rng),
                                body=bad_body,
                            ),
                            expected=TestExpected(status_codes=errors),
                            expectation_source=ExpectationSource.OPENAPI,
                            rationale=f"Send string where integer expected for {field!r}",
                            risk=RiskLevel.LOW,
                            priority=42,
                            safety_class=safety,
                            requires_approval=pos.requires_approval,
                            coverage_targets=CoverageTargets(
                                parameters=[field],
                                schema_constraints=["type"],
                            ),
                        )
                    )
                    break

            for field, field_schema in props.items():
                min_len = field_schema.get("minLength")
                if isinstance(min_len, int) and min_len > 0:
                    short_body = _minimal_json_from_schema(op.request_body_schema, rng)
                    if isinstance(short_body, dict) and field in short_body:
                        short_body[field] = "a" * max(0, min_len - 1)
                    order += 1
                    cases.append(
                        TestCase(
                            test_id=_test_id("boundary", op.operation_id, f"{field}_minlen"),
                            operation_id=op.operation_id,
                            order=order,
                            category=TestCategory.BOUNDARY,
                            request=TestRequest(
                                method=op.method,
                                path=_fill_path(op.path, op, rng),
                                body=short_body,
                            ),
                            expected=TestExpected(status_codes=errors),
                            expectation_source=ExpectationSource.OPENAPI,
                            rationale=f"Violate minLength on body field {field!r}",
                            risk=RiskLevel.LOW,
                            priority=48,
                            safety_class=safety,
                            requires_approval=pos.requires_approval,
                            coverage_targets=CoverageTargets(
                                parameters=[field],
                                schema_constraints=["minLength"],
                            ),
                        )
                    )
                    break

        # Security-basic when operation declares security
        if op.security and config.auth.type != "none":
            auth_errors = _auth_error_codes(op)
            order += 1
            cases.append(
                TestCase(
                    test_id=_test_id("security", op.operation_id, "no_auth"),
                    operation_id=op.operation_id,
                    order=order,
                    category=TestCategory.SECURITY_BASIC,
                    request=TestRequest(
                        method=op.method,
                        path=_fill_path(op.path, op, rng),
                        body=body if op.method in ("POST", "PUT", "PATCH") else None,
                        headers={"_yaymeter_auth_mode": "none"},
                    ),
                    expected=TestExpected(status_codes=auth_errors),
                    expectation_source=ExpectationSource.OPENAPI,
                    rationale="Protected operation should reject missing credentials",
                    risk=RiskLevel.LOW,
                    priority=35,
                    safety_class=SafetyClass.READ_ONLY,
                    requires_approval=False,
                    coverage_targets=CoverageTargets(operation=True),
                )
            )
            order += 1
            cases.append(
                TestCase(
                    test_id=_test_id("security", op.operation_id, "bad_token"),
                    operation_id=op.operation_id,
                    order=order,
                    category=TestCategory.SECURITY_BASIC,
                    request=TestRequest(
                        method=op.method,
                        path=_fill_path(op.path, op, rng),
                        body=body if op.method in ("POST", "PUT", "PATCH") else None,
                        headers={"_yaymeter_auth_mode": "invalid"},
                    ),
                    expected=TestExpected(status_codes=auth_errors),
                    expectation_source=ExpectationSource.OPENAPI,
                    rationale="Protected operation should reject invalid token",
                    risk=RiskLevel.LOW,
                    priority=36,
                    safety_class=SafetyClass.READ_ONLY,
                    requires_approval=False,
                    coverage_targets=CoverageTargets(operation=True),
                )
            )

    return TestPlan(
        transport="http",
        spec_hash=inventory.spec_hash,
        config_hash=config.config_hash(),
        seed=config.seed,
        generator_version=config.generator_version,
        base_url=str(config.base_url),
        created_at=utc_now_iso(),
        test_cases=cases,
    )


def validate_plan(plan: TestPlan) -> list[str]:
    errors: list[str] = []
    ids = [t.test_id for t in plan.test_cases]
    if len(ids) != len(set(ids)):
        errors.append("Duplicate test_id values in plan")
    for t in plan.test_cases:
        if not t.expectation_source:
            errors.append(f"{t.test_id}: missing expectation_source")
        if t.category == TestCategory.PERFORMANCE and t.safety_class != SafetyClass.LOAD:
            errors.append(f"{t.test_id}: performance test must have safety_class=load")
    return errors


def plan_to_json(plan: TestPlan) -> str:
    return json.dumps(plan.model_dump(mode="json"), indent=2, sort_keys=True)
