"""Coverage and gap analysis."""

from __future__ import annotations

from dataclasses import dataclass, field

from api_test_agent.models import ApiInventory, AssertionOutcome, NormalizedResults, TestPlan


@dataclass
class CoverageReport:
    operations_discovered: int = 0
    operations_tested: int = 0
    responses_declared: int = 0
    responses_asserted: int = 0
    parameters_in_scope: int = 0
    parameters_exercised: int = 0
    tests_generated: int = 0
    tests_executed: int = 0
    counts_by_outcome: dict[str, int] = field(default_factory=dict)
    untested_operations: list[dict[str, str]] = field(default_factory=list)
    gaps: list[dict[str, str | int]] = field(default_factory=list)


def _executed_test_ids(results: NormalizedResults) -> set[str]:
    executed = set()
    for r in results.records:
        if r.overall not in (AssertionOutcome.SKIPPED, AssertionOutcome.BLOCKED):
            executed.add(r.test_id)
        elif r.overall == AssertionOutcome.BLOCKED:
            continue
    return executed


def compute_coverage(
    inventory: ApiInventory,
    plan: TestPlan,
    results: NormalizedResults | None,
) -> CoverageReport:
    report = CoverageReport()
    report.operations_discovered = len(inventory.operations)
    report.tests_generated = len(plan.test_cases)

    tested_ops: set[str] = set()
    for t in plan.test_cases:
        if not t.blocked and t.category.value != "contract":
            tested_ops.add(t.operation_id)
    report.operations_tested = len(tested_ops)

    report.responses_declared = sum(len(op.responses) for op in inventory.operations)
    asserted_statuses: set[tuple[str, str]] = set()
    for t in plan.test_cases:
        for s in t.coverage_targets.response_statuses:
            asserted_statuses.add((t.operation_id, s))
    report.responses_asserted = len(asserted_statuses)

    params_scope: set[tuple[str, str]] = set()
    for op in inventory.operations:
        for p in op.parameters:
            params_scope.add((op.operation_id, p.name))
    report.parameters_in_scope = len(params_scope)

    params_hit: set[tuple[str, str]] = set()
    for t in plan.test_cases:
        for pname in t.coverage_targets.parameters:
            params_hit.add((t.operation_id, pname))
    report.parameters_exercised = len(params_hit)

    if results:
        report.counts_by_outcome = dict(results.summary)
        report.tests_executed = sum(
            1
            for r in results.records
            if r.overall
            not in (AssertionOutcome.SKIPPED, AssertionOutcome.BLOCKED)
        )

    tested_op_ids = {op.operation_id for op in inventory.operations if op.operation_id in tested_ops}
    for op in inventory.operations:
        if op.operation_id not in tested_op_ids:
            reason = "no generated executable tests"
            if op.method in ("DELETE",):
                reason = "unsafe mutation or missing approval policy"
            report.untested_operations.append(
                {"operation_id": op.operation_id, "reason": reason}
            )

    for item in report.untested_operations:
        report.gaps.append(
            {
                "priority": 80,
                "operation_id": item["operation_id"],
                "rationale": item["reason"],
                "requires_approval": "true"
                if any(
                    op.method not in ("GET", "HEAD")
                    for op in inventory.operations
                    if op.operation_id == item["operation_id"]
                )
                else "false",
            }
        )

    report.gaps.sort(key=lambda g: int(g["priority"]), reverse=True)
    return report
