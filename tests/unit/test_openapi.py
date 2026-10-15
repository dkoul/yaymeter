import pytest

from api_test_agent.openapi_loader import OpenApiLoadError, load_inventory


def test_load_bookstore_inventory():
    inv = load_inventory("tests/fixtures/bookstore-openapi.yaml")
    assert inv.title == "Bookstore API"
    assert len(inv.operations) == 3
    ids = [o.operation_id for o in inv.operations]
    assert ids == ["listBooks", "createBook", "getBook"]


def test_invalid_spec_fails():
    with pytest.raises(OpenApiLoadError):
        load_inventory("tests/fixtures/invalid-openapi.yaml")


def test_inventory_stable_hash():
    a = load_inventory("tests/fixtures/bookstore-openapi.yaml")
    b = load_inventory("tests/fixtures/bookstore-openapi.yaml")
    assert a.spec_hash == b.spec_hash
    assert [o.operation_id for o in a.operations] == [o.operation_id for o in b.operations]
