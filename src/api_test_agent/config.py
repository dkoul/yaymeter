"""Configuration loading and validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, HttpUrl, field_validator


class AuthConfig(BaseModel):
    type: str = "none"
    header_name: str = "Authorization"
    env_var: str = "API_TEST_AUTH_TOKEN"
    value: str | None = None


class SafetyLimits(BaseModel):
    request_timeout_seconds: float = 30.0
    run_timeout_seconds: float = 300.0
    max_requests: int = 500
    max_concurrency: int = 1
    max_ramp_up_seconds: int = 60
    max_requests_per_second: float = 50.0
    error_rate_threshold: float = 0.5


class PerformanceProfile(BaseModel):
    enabled: bool = False
    threads: int = 10
    ramp_up_seconds: int = 30
    duration_seconds: int = 60
    loops: int = 20
    target_operations: list[str] = Field(default_factory=list)


class AgentConfig(BaseModel):
    base_url: HttpUrl
    target_label: str = "default"
    allowed_hosts: list[str] = Field(default_factory=list)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    seed: int = 42
    generator_version: str = "0.1.0"
    allow_mutations: bool = False
    allow_performance: bool = False
    disposable_test_environment: bool = False
    safety: SafetyLimits = Field(default_factory=SafetyLimits)
    performance: PerformanceProfile = Field(default_factory=PerformanceProfile)
    sensitive_json_fields: list[str] = Field(
        default_factory=lambda: ["password", "token", "secret", "apiKey", "api_key"]
    )

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def default_hosts_from_url(cls, v: Any, info: Any) -> list[str]:
        if v:
            return list(v)
        return []

    def resolved_allowed_hosts(self) -> list[str]:
        if self.allowed_hosts:
            return self.allowed_hosts
        from urllib.parse import urlparse

        host = urlparse(str(self.base_url)).hostname
        return [host] if host else []

    def config_hash(self) -> str:
        payload = self.model_dump(mode="json")
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


def load_config(path: Path | str) -> AgentConfig:
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    cfg = AgentConfig.model_validate(data)
    if not cfg.allowed_hosts:
        cfg.allowed_hosts = cfg.resolved_allowed_hosts()
    return cfg
