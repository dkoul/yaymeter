import pytest

from api_test_agent.config import load_config
from api_test_agent.safety import SafetyViolation, validate_plan_for_run
from api_test_agent.test_design import generate_plan
from api_test_agent.openapi_loader import load_inventory
import json


def test_performance_requires_approve(tmp_path):
    inv = load_inventory("tests/fixtures/bookstore-openapi.yaml")
    cfg = load_config("examples/test-config.yaml")
    plan = generate_plan(inv, cfg)
    with pytest.raises(SafetyViolation):
        validate_plan_for_run(plan, cfg, "performance", approve=False)


def test_mutation_requires_approve_when_not_disposable():
    cfg = load_config("examples/test-config.yaml")
    cfg.disposable_test_environment = False
    cfg.allow_mutations = False
    inv = load_inventory("tests/fixtures/bookstore-openapi.yaml")
    plan = generate_plan(inv, cfg)
    with pytest.raises(SafetyViolation):
        validate_plan_for_run(plan, cfg, "functional", approve=False)
