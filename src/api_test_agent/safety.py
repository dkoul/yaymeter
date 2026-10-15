"""Safety policy enforcement."""

from __future__ import annotations

from urllib.parse import urlparse

from api_test_agent.config import AgentConfig
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
