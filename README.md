# Yaymeter

OpenAPI-driven functional and performance API testing with **JMeter by default**. Yaymeter plans tests deterministically in Python, executes with Apache JMeter, and publishes evidence-backed Markdown reports.

## Requirements

- Python 3.11+
- **Default executor is JMeter**; first `yaymeter run` auto-downloads a portable JRE + JMeter into `.tools/` (no manual JVM setup).
- Use `--executor python` for a JVM-free fallback.

## Install

```bash
pip install -e ".[dev]"
```

## Quick start

```bash
yaymeter check-environment
yaymeter inspect --spec tests/fixtures/bookstore-openapi.yaml
yaymeter plan --spec tests/fixtures/bookstore-openapi.yaml --config examples/test-config.yaml --out generated-tests/plan.json
yaymeter validate-plan --plan generated-tests/plan.json
yaymeter run --plan generated-tests/plan.json --config examples/test-config.yaml --approve
yaymeter report --run-dir results/run-<id> --spec tests/fixtures/bookstore-openapi.yaml
```

The `api-test-agent` console script is kept as an alias for `yaymeter`.

## Claude Code skill

See `.claude/skills/yaymeter/SKILL.md`.

## Safety

- Confirm `base_url` and `allowed_hosts` before running against a real target.
- Mutations and performance tests require `--approve` and appropriate config flags.
- Secrets are loaded from environment variables, not embedded in JMX.

## License

MIT
