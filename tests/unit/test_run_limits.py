import pytest

from api_test_agent.config import load_config
from api_test_agent.openapi_loader import load_inventory
from api_test_agent.safety import SafetyViolation, validate_jmeter_run_limits
from api_test_agent.test_design import generate_plan


def test_max_requests_requires_approve():
    inv = load_inventory("tests/fixtures/bookstore-openapi.yaml")
    cfg = load_config("examples/test-config.yaml")
    cfg.safety.max_requests = 2
    plan = generate_plan(inv, cfg)
    with pytest.raises(SafetyViolation):
        validate_jmeter_run_limits(plan, cfg, "functional", threads=1, loops=5, ramp_seconds=1, approve=False)
