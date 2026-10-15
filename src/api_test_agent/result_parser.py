"""Parse JMeter JTL output into normalized results."""

from __future__ import annotations

import csv
from pathlib import Path

from api_test_agent.jtl_aggregate import SampleAggregate, ingest_jtl_row
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
    aggregates: dict[str, SampleAggregate] = {}

    with jtl_path.open(encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ingest_jtl_row(aggregates, row)

    records: list[ResultRecord] = []
    total_samples = 0
    total_failures = 0

    for test in sorted(plan.test_cases, key=lambda t: t.order):
        if test.test_id not in aggregates:
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

        agg = aggregates[test.test_id]
        total_samples += agg.sample_count
        total_failures += agg.failure_count
        row = agg.last_row or {}

        success = not agg.any_failure()
        status_raw = row.get("responseCode") or row.get("Response Code") or ""
        try:
            status = int(status_raw)
        except ValueError:
            status = None
        if agg.response_codes and status is None:
            status = sorted(agg.response_codes)[-1]

        elapsed = agg.avg_elapsed_ms
        p95 = agg.p95_elapsed_ms()

        assertions: list[AssertionResult] = []
        if success:
            assertions.append(
                AssertionResult(
                    name="jmeter_success",
                    outcome=AssertionOutcome.PASS,
                    message=f"{agg.sample_count} sample(s), 0 failures",
                )
            )
        else:
            msg = row.get("failureMessage") or row.get("Failure Message") or "JMeter failure"
            assertions.append(
                AssertionResult(
                    name="jmeter_success",
                    outcome=AssertionOutcome.FAIL,
                    message=f"{agg.failure_count}/{agg.sample_count} failed; last: {msg}",
                )
            )

        if agg.sample_count > 1:
            assertions.append(
                AssertionResult(
                    name="load_aggregate",
                    outcome=AssertionOutcome.PASS if success else AssertionOutcome.FAIL,
                    message=(
                        f"samples={agg.sample_count} error_rate={agg.error_rate:.2%} "
                        f"avg_ms={elapsed:.1f}" if elapsed is not None else f"samples={agg.sample_count}"
                    ),
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
                codes = sorted(agg.response_codes) if agg.response_codes else [status]
                assertions.append(
                    AssertionResult(
                        name="status_code",
                        outcome=AssertionOutcome.FAIL,
                        message=f"expected {test.expected.status_codes}, saw {codes}",
                    )
                )

        if test.expected.response_schema and success:
            assertions.append(
                AssertionResult(
                    name="response_schema",
                    outcome=AssertionOutcome.PASS,
                    message="JMX JSONPath checks on required fields (not full jsonschema)",
                )
            )

        artifact_refs = {}
        if agg.sample_count > 1:
            artifact_refs["sample_count"] = str(agg.sample_count)
            artifact_refs["failure_count"] = str(agg.failure_count)
            artifact_refs["error_rate"] = f"{agg.error_rate:.4f}"
            if p95 is not None:
                artifact_refs["p95_elapsed_ms"] = f"{p95:.2f}"

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
                artifact_refs=artifact_refs,
            )
        )

    summary: dict[str, int] = {}
    for r in records:
        summary[r.overall.value] = summary.get(r.overall.value, 0) + 1

    load_stats = {
        "total_jtl_samples": total_samples,
        "total_jtl_failures": total_failures,
        "global_error_rate": (total_failures / total_samples) if total_samples else 0.0,
    }

    return NormalizedResults(run_id=run_id, records=records, summary=summary, load_stats=load_stats)
