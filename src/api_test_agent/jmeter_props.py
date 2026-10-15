"""JMeter -J properties and command-line helpers."""

from __future__ import annotations

import os
import re

from api_test_agent.config import AgentConfig
from api_test_agent.models import TestPlan


def executable_tests(plan: TestPlan, profile: str) -> list:
    executable = [t for t in plan.test_cases if not t.blocked and t.category.value != "contract"]
    if profile == "functional":
        executable = [t for t in executable if t.category.value != "performance"]
    return executable


def jmeter_properties_for_run(
    config: AgentConfig,
    profile: str,
    threads: int,
    ramp_seconds: int,
    loops: int,
) -> dict[str, str | int | float]:
    props: dict[str, str | int | float] = {
        "yaymeter.threads": threads,
        "yaymeter.ramp_seconds": ramp_seconds,
        "yaymeter.loops": loops,
    }
    if config.auth.type != "none":
        token = config.auth.value or os.environ.get(config.auth.env_var, "")
        if token:
            props["yaymeter.auth_token"] = token
    max_rps = config.safety.max_requests_per_second
    if max_rps and max_rps > 0:
        props["yaymeter.max_rps"] = max_rps
    return props


def redact_command_args(cmd: list[str]) -> list[str]:
    redacted: list[str] = []
    for arg in cmd:
        if arg.startswith("-Jyaymeter.auth_token="):
            redacted.append("-Jyaymeter.auth_token=***REDACTED***")
        else:
            redacted.append(arg)
    return redacted


_AUTH_TOKEN_RE = re.compile(r"(-Jyaymeter\.auth_token=)(.+)$")


def redact_command_arg_string(arg: str) -> str:
    return _AUTH_TOKEN_RE.sub(r"\1***REDACTED***", arg)
