"""Execute test plans with Python (for CI without JMeter)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from api_test_agent.config import AgentConfig
from api_test_agent.models import (
    AssertionOutcome,
    AssertionResult,
    NormalizedResults,
    ResultRecord,
    TestCase,
    TestPlan,
    utc_now_iso,
)
from api_test_agent.redaction import fingerprint_request, redact_headers


def _request(
    base_url: str,
    test: TestCase,
    auth_token: str | None,
    timeout: float,
) -> tuple[int | None, float, str | None, dict[str, str]]:
    url = base_url.rstrip("/") + test.request.path
    if test.request.query:
        from urllib.parse import urlencode

        url += "?" + urlencode(test.request.query)

    headers = {k: v for k, v in test.request.headers.items() if not k.startswith("_yaymeter")}
    headers.setdefault("Content-Type", test.request.body_content_type or "application/json")
    auth_mode = test.request.headers.get("_yaymeter_auth_mode")
    if auth_mode == "none":
        pass
    elif auth_mode == "invalid":
        headers.setdefault("Authorization", "Bearer yaymeter-invalid-token")
    elif auth_token:
        headers.setdefault("Authorization", f"Bearer {auth_token}")

    data = None
    if test.request.body is not None:
        data = json.dumps(test.request.body).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=test.request.method.upper(),
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = (time.perf_counter() - start) * 1000
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, elapsed, body, dict(resp.headers)
    except urllib.error.HTTPError as e:
        elapsed = (time.perf_counter() - start) * 1000
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return e.code, elapsed, body, dict(e.headers or {})
    except Exception:
        elapsed = (time.perf_counter() - start) * 1000
        return None, elapsed, None, {}


def evaluate_test(
    test: TestCase,
    status: int | None,
    body: str | None,
    headers: dict[str, str],
) -> list[AssertionResult]:
    results: list[AssertionResult] = []

    if test.blocked:
        return [
            AssertionResult(
                name="execution",
                outcome=AssertionOutcome.BLOCKED,
                message=test.blocked_reason,
            )
        ]

    if status is None:
        return [
            AssertionResult(
                name="http_request",
                outcome=AssertionOutcome.FAIL,
                message="Request failed or timed out",
            )
        ]

    if test.expected.status_codes:
        if status in test.expected.status_codes:
            results.append(
                AssertionResult(
                    name="status_code",
                    outcome=AssertionOutcome.PASS,
                    message=f"status {status}",
                )
            )
        else:
            results.append(
                AssertionResult(
                    name="status_code",
                    outcome=AssertionOutcome.FAIL,
                    message=f"expected one of {test.expected.status_codes}, got {status}",
                )
            )

    for h in test.expected.required_headers:
        if h.lower() in {k.lower() for k in headers}:
            results.append(
                AssertionResult(name=f"header:{h}", outcome=AssertionOutcome.PASS)
            )
        else:
            results.append(
                AssertionResult(
                    name=f"header:{h}",
                    outcome=AssertionOutcome.FAIL,
                    message=f"missing header {h}",
                )
            )

    if test.expected.response_schema and body:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            results.append(
                AssertionResult(
                    name="json_body",
                    outcome=AssertionOutcome.FAIL,
                    message="response is not valid JSON",
                )
            )
            return results
        try:
            Draft202012Validator(test.expected.response_schema).validate(payload)
            results.append(
                AssertionResult(name="response_schema", outcome=AssertionOutcome.PASS)
            )
        except ValidationError as e:
            results.append(
                AssertionResult(
                    name="response_schema",
                    outcome=AssertionOutcome.FAIL,
                    message=str(e.message),
                )
            )

    if not results:
        results.append(
            AssertionResult(
                name="http_request",
                outcome=AssertionOutcome.INCONCLUSIVE,
                message="no assertions configured",
            )
        )

    return results


def overall_from_assertions(assertions: list[AssertionResult]) -> AssertionOutcome:
    if not assertions:
        return AssertionOutcome.INCONCLUSIVE
    if any(a.outcome == AssertionOutcome.BLOCKED for a in assertions):
        return AssertionOutcome.BLOCKED
    if any(a.outcome == AssertionOutcome.FAIL for a in assertions):
        return AssertionOutcome.FAIL
    if all(a.outcome == AssertionOutcome.PASS for a in assertions):
        return AssertionOutcome.PASS
    if any(a.outcome == AssertionOutcome.INCONCLUSIVE for a in assertions):
        return AssertionOutcome.INCONCLUSIVE
    return AssertionOutcome.SKIPPED


def execute_plan(
    plan: TestPlan,
    config: AgentConfig,
    run_dir: Path,
    run_id: str,
    target_label: str,
) -> NormalizedResults:
    run_dir.mkdir(parents=True, exist_ok=True)
    auth = config.auth.value or __import__("os").environ.get(config.auth.env_var)
    records: list[ResultRecord] = []

    for test in sorted(plan.test_cases, key=lambda t: t.order):
        if test.category.value == "contract":
            records.append(
                ResultRecord(
                    test_id=test.test_id,
                    operation_id=test.operation_id,
                    timestamp=utc_now_iso(),
                    target_label=target_label,
                    request_fingerprint=fingerprint_request(
                        test.request.method, test.request.path, test.request.query
                    ),
                    overall=AssertionOutcome.SKIPPED,
                    assertions=[
                        AssertionResult(
                            name="contract_inventory",
                            outcome=AssertionOutcome.SKIPPED,
                            message="inventory-only case",
                        )
                    ],
                )
            )
            continue

        if test.blocked:
            records.append(
                ResultRecord(
                    test_id=test.test_id,
                    operation_id=test.operation_id,
                    timestamp=utc_now_iso(),
                    target_label=target_label,
                    request_fingerprint=fingerprint_request(
                        test.request.method, test.request.path, test.request.query
                    ),
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

        status, elapsed, body, headers = _request(
            plan.base_url,
            test,
            auth,
            config.safety.request_timeout_seconds,
        )
        assertions = evaluate_test(test, status, body, headers)
        records.append(
            ResultRecord(
                test_id=test.test_id,
                operation_id=test.operation_id,
                timestamp=utc_now_iso(),
                target_label=target_label,
                request_fingerprint=fingerprint_request(
                    test.request.method, test.request.path, test.request.query
                ),
                response_status=status,
                elapsed_ms=elapsed,
                assertions=assertions,
                overall=overall_from_assertions(assertions),
                redacted=True,
            )
        )

    summary: dict[str, int] = {}
    for r in records:
        summary[r.overall.value] = summary.get(r.overall.value, 0) + 1

    results = NormalizedResults(run_id=run_id, records=records, summary=summary)
    (run_dir / "results.json").write_text(
        results.model_dump_json(indent=2), encoding="utf-8"
    )
    return results
