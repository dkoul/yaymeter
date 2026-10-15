import json

from api_test_agent.config import load_config
from api_test_agent.openapi_loader import load_inventory
from api_test_agent.test_design import generate_plan, validate_plan


def test_plan_deterministic():
    inv = load_inventory("tests/fixtures/bookstore-openapi.yaml")
    cfg = load_config("examples/test-config.yaml")
    p1 = generate_plan(inv, cfg)
    p2 = generate_plan(inv, cfg)
    assert p1.model_dump() == p2.model_dump()


def test_plan_has_expectation_and_safety():
    inv = load_inventory("tests/fixtures/bookstore-openapi.yaml")
    cfg = load_config("examples/test-config.yaml")
    plan = generate_plan(inv, cfg)
    for t in plan.test_cases:
        assert t.expectation_source
        assert t.safety_class
    assert validate_plan(plan) == []


def test_golden_plan_subset():
    inv = load_inventory("tests/fixtures/bookstore-openapi.yaml")
    cfg = load_config("examples/test-config.yaml")
    plan = generate_plan(inv, cfg)
    expected = json.loads(open("tests/fixtures/expected-plan.json", encoding="utf-8").read())
    assert plan.spec_hash == expected["spec_hash"]
    assert len(plan.test_cases) == expected["test_case_count"]
    assert [t.test_id for t in plan.test_cases] == expected["test_ids"]
