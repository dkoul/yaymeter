"""Markdown report generation."""

from __future__ import annotations

from pathlib import Path

from api_test_agent.coverage import CoverageReport
from api_test_agent.models import NormalizedResults, RunManifest, TestPlan


def render_report(
    plan: TestPlan,
    results: NormalizedResults,
    coverage: CoverageReport,
    manifest: RunManifest | None = None,
) -> str:
    lines: list[str] = ["# Yaymeter API Test Report", ""]

    lines.append("## Run summary")
    if manifest:
        lines.append(f"- Target: {manifest.target_label} (`{manifest.base_url}`)")
        lines.append(f"- Spec hash: `{manifest.spec_hash}`")
        lines.append(f"- Profile: {manifest.profile}")
        lines.append(f"- Started: {manifest.started_at}")
        if manifest.jmeter_version:
            lines.append(f"- JMeter: {manifest.jmeter_version}")
        executor = manifest.artifacts.get("executor", "jmeter")
        lines.append(f"- Executor: {executor}")
        if executor == "jmeter":
            lines.append(
                "- Schema checks: JSONPath presence on required fields in JMX; "
                "full jsonschema validation only with `--executor python`"
            )
    lines.append(f"- Tool version: {plan.generator_version}")
    lines.append(f"- Seed: {plan.seed}")
    total = sum(results.summary.values())
    fails = results.summary.get("FAIL", 0)
    overall = "PASS" if fails == 0 else "FAIL"
    lines.append(f"- Overall status: **{overall}**")
    lines.append(f"- Result counts: {results.summary}")
    if results.load_stats.get("total_jtl_samples", 0) > 0:
        lines.append(
            f"- JTL samples: {results.load_stats.get('total_jtl_samples')} "
            f"(failures {results.load_stats.get('total_jtl_failures', 0)}, "
            f"error rate {float(results.load_stats.get('global_error_rate', 0)):.2%})"
        )
    lines.append("")

    lines.append("## Executive findings")
    failures = [r for r in results.records if r.overall.value == "FAIL"]
    if failures:
        for r in failures[:10]:
            lines.append(
                f"- **{r.test_id}** ({r.operation_id}): status={r.response_status}"
            )
    else:
        lines.append("- No confirmed contract failures in executed tests.")
    blocked = results.summary.get("BLOCKED", 0)
    if blocked:
        lines.append(f"- {blocked} test(s) blocked (missing data or policy).")
    lines.append("")

    lines.append("## Coverage")
    lines.append(
        f"- Operations: {coverage.operations_tested}/{coverage.operations_discovered} with executable tests"
    )
    lines.append(
        f"- Responses with assertions: {coverage.responses_asserted}/{coverage.responses_declared}"
    )
    lines.append(
        f"- Parameters exercised: {coverage.parameters_exercised}/{coverage.parameters_in_scope}"
    )
    lines.append(f"- Tests generated: {coverage.tests_generated}")
    lines.append(f"- Tests executed: {coverage.tests_executed}")
    if coverage.untested_operations:
        lines.append("- Untested operations:")
        for u in coverage.untested_operations:
            lines.append(f"  - `{u['operation_id']}`: {u['reason']}")
    lines.append("")

    lines.append("## Functional and contract results")
    lines.append("| Test ID | Operation | Expected | Actual | Result |")
    lines.append("|---------|-----------|----------|--------|--------|")
    for r in results.records:
        test = next((t for t in plan.test_cases if t.test_id == r.test_id), None)
        expected = (
            ",".join(str(c) for c in (test.expected.status_codes if test else []))
            or "-"
        )
        lines.append(
            f"| {r.test_id} | {r.operation_id} | {expected} | {r.response_status or '-'} | {r.overall.value} |"
        )
    lines.append("")

    lines.append("## Performance results")
    elapsed = [r.elapsed_ms for r in results.records if r.elapsed_ms is not None]
    if elapsed:
        sorted_e = sorted(elapsed)
        n = len(sorted_e)

        def pct(p: float) -> float:
            idx = min(n - 1, int(p * n))
            return sorted_e[idx]

        lines.append(f"- Sample count: {n}")
        lines.append(f"- p50 latency (ms): {pct(0.5):.1f}")
        lines.append(f"- p90 latency (ms): {pct(0.9):.1f}")
        lines.append(f"- p95 latency (ms): {pct(0.95):.1f}")
        lines.append(f"- p99 latency (ms): {pct(0.99):.1f}")
    else:
        lines.append("- No latency samples (functional profile or no execution).")
    lines.append("")

    lines.append("## Coverage gaps and next tests")
    for gap in coverage.gaps[:20]:
        lines.append(
            f"- Priority {gap['priority']}: `{gap['operation_id']}` — {gap['rationale']}"
        )
    lines.append("")

    lines.append("## Artifacts")
    if manifest and manifest.artifacts:
        for name, path in manifest.artifacts.items():
            lines.append(f"- {name}: `{path}`")
    lines.append(f"- Normalized results: `results.json`")
    lines.append("")

    return "\n".join(lines)


def write_report(content: str, path: Path | str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p
