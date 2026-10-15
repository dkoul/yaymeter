"""Parse JMeter JTL output into normalized results."""

from __future__ import annotations

import csv
from pathlib import Path

from api_test_agent.models import (
    AssertionOutcome,
    AssertionResult,
    NormalizedResults,
    ResultRecord,
    TestPlan,
    utc_now_iso,
)
from api_test_agent.python_executor import overall_from_assertions


def parse_jtl(jtl_path: Path, plan: TestPlan, run_id: str, target_label: str) -> NormalizedResults:
    """Map JTL samples to plan test cases by sampler label (test_id)."""
    by_id = {t.test_id: t for t in plan.test_cases}
    samples: dict[str, dict] = {}

    with jtl_path.open(encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            label = row.get("label") or row.get("Label") or ""
            if not label:
                continue
            samples[label] = row

    records: list[ResultRecord] = []
    for test in sorted(plan.test_cases, key=lambda t: t.order):
        if test.test_id not in samples:
            if test.blocked or test.category.value == "contract":
                outcome = (
                    AssertionOutcome.BLOCKED if test.blocked else AssertionOutcome.SKIPPED
                )
                records.append(
                    ResultRecord(
                        test_id=test.test_id,
                        operation_id=test.operation_id,
                        timestamp=utc_now_iso(),
                        target_label=target_label,
                        request_fingerprint=test.test_id,
                        overall=outcome,
                        assertions=[
                            AssertionResult(
                                name="jmeter_sample",
                                outcome=outcome,
                                message="no JTL sample",
                            )
                        ],
                    )
                )
            continue

        row = samples[test.test_id]
        success = (row.get("success") or row.get("Success") or "").lower() == "true"
        status_raw = row.get("responseCode") or row.get("Response Code") or ""
        try:
            status = int(status_raw)
        except ValueError:
            status = None
        elapsed_raw = row.get("elapsed") or row.get("Elapsed") or "0"
        try:
            elapsed = float(elapsed_raw)
        except ValueError:
            elapsed = None

        assertions: list[AssertionResult] = []
        if success:
            assertions.append(
                AssertionResult(
                    name="jmeter_success",
                    outcome=AssertionOutcome.PASS,
                    message="JMeter marked sample successful",
                )
            )
        else:
            msg = row.get("failureMessage") or row.get("Failure Message") or "JMeter failure"
            assertions.append(
                AssertionResult(
                    name="jmeter_success",
                    outcome=AssertionOutcome.FAIL,
                    message=msg,
                )
            )

        if test.expected.status_codes and status is not None:
            if status in test.expected.status_codes:
                assertions.append(
                    AssertionResult(
                        name="status_code",
                        outcome=AssertionOutcome.PASS,
                        message=str(status),
                    )
                )
            else:
                assertions.append(
                    AssertionResult(
                        name="status_code",
                        outcome=AssertionOutcome.FAIL,
                        message=f"expected {test.expected.status_codes}, got {status}",
                    )
                )

        records.append(
            ResultRecord(
                test_id=test.test_id,
                operation_id=test.operation_id,
                timestamp=utc_now_iso(),
                target_label=target_label,
                request_fingerprint=test.test_id,
                response_status=status,
                elapsed_ms=elapsed,
                assertions=assertions,
                overall=overall_from_assertions(assertions),
            )
        )

    summary: dict[str, int] = {}
    for r in records:
        summary[r.overall.value] = summary.get(r.overall.value, 0) + 1

    return NormalizedResults(run_id=run_id, records=records, summary=summary)
