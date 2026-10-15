"""Safety policy enforcement."""

from __future__ import annotations

from urllib.parse import urlparse

from api_test_agent.config import AgentConfig
from api_test_agent.jmeter_props import executable_tests
from api_test_agent.models import SafetyClass, TestCase, TestPlan


class SafetyViolation(Exception):
    pass


def classify_operation(method: str) -> SafetyClass:
    m = method.upper()
    if m in ("GET", "HEAD", "OPTIONS"):
        return SafetyClass.READ_ONLY
    if m == "DELETE":
        return SafetyClass.DESTRUCTIVE
    return SafetyClass.MUTATION


def mutation_requires_approval(test: TestCase, config: AgentConfig) -> bool:
    if test.safety_class == SafetyClass.READ_ONLY:
        return False
    if config.disposable_test_environment and config.allow_mutations:
        return False
    return True


def validate_target_url(url: str, config: AgentConfig) -> None:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise SafetyViolation(f"Invalid base URL: {url}")
    allowed = set(config.resolved_allowed_hosts())
    if host not in allowed:
        raise SafetyViolation(
            f"Host {host!r} is not in allowed_hosts {sorted(allowed)!r}"
        )


def validate_plan_for_run(
    plan: TestPlan,
    config: AgentConfig,
    profile: str,
    approve: bool,
) -> None:
    validate_target_url(plan.base_url, config)

    if profile == "performance":
        if not config.allow_performance:
            raise SafetyViolation("Performance profile is disabled in config")
        if not approve:
            raise SafetyViolation(
                "Performance runs require --approve and explicit config allow_performance"
            )

    for test in plan.test_cases:
        if test.blocked:
            continue
        if test.requires_approval and not approve:
            if not (
                config.disposable_test_environment
                and test.safety_class in (SafetyClass.MUTATION, SafetyClass.DESTRUCTIVE)
                and config.allow_mutations
            ):
                raise SafetyViolation(
                    f"Test {test.test_id} requires approval (safety_class={test.safety_class})"
                )


def validate_jmeter_run_limits(
    plan: TestPlan,
    config: AgentConfig,
    profile: str,
    threads: int,
    loops: int,
    ramp_seconds: int,
    approve: bool,
) -> None:
    """Enforce SafetyLimits before starting JMeter."""
    limits = config.safety
    executable = executable_tests(plan, profile)
    sampler_count = len(executable)
    total_requests = sampler_count * max(1, threads) * max(1, loops)

    if total_requests > limits.max_requests and not approve:
        raise SafetyViolation(
            f"Run would execute ~{total_requests} HTTP samples "
            f"(>{limits.max_requests} max_requests); pass --approve to continue"
        )

    if profile == "functional" and threads > limits.max_concurrency:
        raise SafetyViolation(
            f"threads={threads} exceeds max_concurrency={limits.max_concurrency} "
            "for functional profile"
        )

    if threads > limits.max_concurrency and profile == "performance" and not approve:
        raise SafetyViolation(
            f"threads={threads} exceeds max_concurrency={limits.max_concurrency}; use --approve"
        )

    if ramp_seconds > limits.max_ramp_up_seconds:
        raise SafetyViolation(
            f"ramp_seconds={ramp_seconds} exceeds max_ramp_up_seconds={limits.max_ramp_up_seconds}"
        )


def check_global_error_rate(
    results_summary: dict[str, int],
    load_stats: dict[str, float | int],
    config: AgentConfig,
) -> None:
    rate = float(load_stats.get("global_error_rate", 0.0))
    if rate > config.safety.error_rate_threshold:
        raise SafetyViolation(
            f"Observed error rate {rate:.2%} exceeds threshold "
            f"{config.safety.error_rate_threshold:.2%}"
        )
