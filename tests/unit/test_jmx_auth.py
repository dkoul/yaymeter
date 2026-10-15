from api_test_agent.config import AuthConfig
from api_test_agent.jmx_builder import auth_header_entries, build_jmx
from api_test_agent.openapi_loader import load_inventory
from api_test_agent.test_design import generate_plan
from api_test_agent.config import load_config


def test_jmx_omits_auth_when_type_none():
    inv = load_inventory("tests/fixtures/bookstore-openapi.yaml")
    cfg = load_config("examples/test-config.yaml")
    plan = generate_plan(inv, cfg)
    xml = build_jmx(plan, auth=AuthConfig(type="none"))
    assert "Authorization" not in xml
    assert "yaymeter.auth_token" not in xml


def test_jmx_bearer_uses_jmeter_property():
    inv = load_inventory("tests/fixtures/bookstore-openapi.yaml")
    cfg = load_config("examples/test-config.yaml")
    plan = generate_plan(inv, cfg)
    auth = AuthConfig(type="bearer", header_name="Authorization")
    xml = build_jmx(plan, auth=auth)
    assert "Bearer ${__P(yaymeter.auth_token,)}" in xml
    assert auth_header_entries(auth) == [
        ("Content-Type", "application/json"),
        ("Authorization", "Bearer ${__P(yaymeter.auth_token,)}"),
    ]
