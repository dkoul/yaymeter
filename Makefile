.PHONY: install test lint inspect example jmeter

jmeter:
	api-test-agent install-jmeter

install:
	pip install -e ".[dev]"

test:
	pytest tests/unit -q

test-all:
	pytest tests -q

lint:
	ruff check src tests

inspect:
	api-test-agent inspect --spec tests/fixtures/bookstore-openapi.yaml

example:
	api-test-agent plan --spec tests/fixtures/bookstore-openapi.yaml --config examples/test-config.yaml --out generated-tests/plan.json
	api-test-agent validate-plan --plan generated-tests/plan.json
