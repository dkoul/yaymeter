.PHONY: install test lint inspect example runtime

install:
	pip install -e ".[dev]"

test:
	pytest tests/unit -q

test-all:
	pytest tests -q

lint:
	ruff check src tests

runtime:
	yaymeter install-runtime

inspect:
	yaymeter inspect --spec tests/fixtures/bookstore-openapi.yaml

example:
	yaymeter plan --spec tests/fixtures/bookstore-openapi.yaml --config examples/test-config.yaml --out generated-tests/plan.json
	yaymeter validate-plan --plan generated-tests/plan.json
