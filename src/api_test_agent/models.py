"""Versioned JSON documents between pipeline stages."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class SchemaVersion(str, Enum):
    INVENTORY = "1.0"
    PLAN = "1.0"
    MANIFEST = "1.0"
    RESULTS = "1.0"


class ParameterModel(BaseModel):
    name: str
    location: Literal["path", "query", "header", "cookie"]
    required: bool = False
    schema_type: str | None = None
    format: str | None = None
    enum: list[Any] | None = None
    minimum: float | None = None
    maximum: float | None = None
    min_length: int | None = None
    max_length: int | None = None


class ResponseModel(BaseModel):
    status_code: str
    description: str | None = None
    content_types: list[str] = Field(default_factory=list)
    schema_ref: str | None = None
    inline_schema: dict[str, Any] | None = None


class OperationModel(BaseModel):
    operation_id: str
    method: str
    path: str
    summary: str | None = None
    parameters: list[ParameterModel] = Field(default_factory=list)
    request_body_content_types: list[str] = Field(default_factory=list)
    request_body_schema: dict[str, Any] | None = None
    responses: list[ResponseModel] = Field(default_factory=list)
    security: list[dict[str, list[str]]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ApiInventory(BaseModel):
    schema_version: str = SchemaVersion.INVENTORY.value
    title: str | None = None
    openapi_version: str
    spec_hash: str
    servers: list[str] = Field(default_factory=list)
    operations: list[OperationModel] = Field(default_factory=list)


class TestCategory(str, Enum):
    CONTRACT = "contract"
    POSITIVE = "positive"
    NEGATIVE = "negative"
    BOUNDARY = "boundary"
    WORKFLOW = "workflow"
    SECURITY_BASIC = "security-basic"
    PERFORMANCE = "performance"


class ExpectationSource(str, Enum):
    OPENAPI = "openapi"
    PROJECT_POLICY = "project_policy"
    HYPOTHESIS = "hypothesis"


class SafetyClass(str, Enum):
    READ_ONLY = "read_only"
    MUTATION = "mutation"
    DESTRUCTIVE = "destructive"
    LOAD = "load"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TestRequest(BaseModel):
    method: str
    path: str
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, str] = Field(default_factory=dict)
    body: Any | None = None
    body_content_type: str | None = "application/json"


class TestExpected(BaseModel):
    status_codes: list[int] = Field(default_factory=list)
    response_schema: dict[str, Any] | None = None
    required_headers: list[str] = Field(default_factory=list)


class CoverageTargets(BaseModel):
    operation: bool = True
    parameters: list[str] = Field(default_factory=list)
    response_statuses: list[str] = Field(default_factory=list)
    schema_constraints: list[str] = Field(default_factory=list)
    workflow_edge: str | None = None


class TestCase(BaseModel):
    test_id: str
    operation_id: str
    order: int
    category: TestCategory
    request: TestRequest
    expected: TestExpected
    expectation_source: ExpectationSource
    rationale: str
    risk: RiskLevel
    priority: int = 50
    safety_class: SafetyClass
    requires_approval: bool = False
    coverage_targets: CoverageTargets = Field(default_factory=CoverageTargets)
    blocked: bool = False
    blocked_reason: str | None = None


class TestPlan(BaseModel):
    schema_version: str = SchemaVersion.PLAN.value
    spec_hash: str
    config_hash: str
    seed: int
    generator_version: str
    base_url: str
    created_at: str
    test_cases: list[TestCase] = Field(default_factory=list)


class AssertionOutcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"
    INCONCLUSIVE = "INCONCLUSIVE"


class AssertionResult(BaseModel):
    name: str
    outcome: AssertionOutcome
    message: str | None = None


class ResultRecord(BaseModel):
    test_id: str
    operation_id: str
    timestamp: str
    target_label: str
    request_fingerprint: str
    response_status: int | None = None
    elapsed_ms: float | None = None
    assertions: list[AssertionResult] = Field(default_factory=list)
    overall: AssertionOutcome
    error_class: str | None = None
    artifact_refs: dict[str, str] = Field(default_factory=dict)
    redacted: bool = True


class NormalizedResults(BaseModel):
    schema_version: str = SchemaVersion.RESULTS.value
    run_id: str
    records: list[ResultRecord] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)


class RunManifest(BaseModel):
    schema_version: str = SchemaVersion.MANIFEST.value
    run_id: str
    spec_hash: str
    config_hash: str
    seed: int
    generator_version: str
    python_version: str
    jmeter_version: str | None = None
    profile: str
    started_at: str
    finished_at: str | None = None
    base_url: str
    target_label: str
    approvals: dict[str, bool] = Field(default_factory=dict)
    artifacts: dict[str, str] = Field(default_factory=dict)
    command_args: list[str] = Field(default_factory=list)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
