import json

from api_test_agent.config import load_config
from api_test_agent.jmx_builder import build_jmx, jmeter_load_properties
from api_test_agent.openapi_loader import load_inventory
from api_test_agent.test_design import generate_plan


def test_parametric_jmx_contains_properties():
    inv = load_inventory("tests/fixtures/bookstore-openapi.yaml")
    cfg = load_config("examples/test-config.yaml")
    plan = generate_plan(inv, cfg)
    xml = build_jmx(plan, parametric=True)
    assert "${__P(yaymeter.threads,1)}" in xml
    assert "${__P(yaymeter.loops,1)}" in xml


def test_load_properties():
    assert jmeter_load_properties("functional")["yaymeter.threads"] == 1
    load = jmeter_load_properties("performance", threads=5, loops=9)
    assert load["yaymeter.threads"] == 5
    assert load["yaymeter.loops"] == 9
