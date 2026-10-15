# API Test Agent

OpenAPI-driven functional API testing with deterministic Python planning and Apache JMeter (or Python) execution. Produces evidence-backed Markdown reports with coverage gaps.

## Requirements

- Python 3.11+
- Apache JMeter 5.6+ (optional if using `--executor python`; can be installed into `.tools/` via CLI)
- Java 8+ (required when using JMeter)

## Install

```bash
pip install -e ".[dev]"
```

## Quick start

```bash
api-test-agent check-environment
api-test-agent install-jmeter
source .tools/jmeter-env.sh
api-test-agent inspect --spec tests/fixtures/bookstore-openapi.yaml
api-test-agent plan --spec tests/fixtures/bookstore-openapi.yaml --config examples/test-config.yaml --out generated-tests/plan.json
api-test-agent validate-plan --plan generated-tests/plan.json
api-test-agent run --plan generated-tests/plan.json --config examples/test-config.yaml --executor python --approve
api-test-agent report --run-dir results/run-<id> --spec tests/fixtures/bookstore-openapi.yaml
```

## Claude Code skill

See `.claude/skills/api-test/SKILL.md` for the agent workflow. Skill scripts in `.claude/skills/api-test/scripts/` wrap the CLI.

## Safety

- Confirm `base_url` and `allowed_hosts` before running against a real target.
- Mutations and performance tests require `--approve` and appropriate config flags.
- Secrets are loaded from environment variables, not embedded in JMX.

## License

MIT
