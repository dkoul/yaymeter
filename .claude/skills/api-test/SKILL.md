# API Test Agent

Use this skill to inspect an OpenAPI spec, build a deterministic test plan, obtain user approval for risky tests, execute via JMeter (or Python executor), and produce a Markdown report.

## Workflow

1. **Environment** — Run `python3 .claude/skills/api-test/scripts/check_environment.py` and confirm Python/JMeter versions.
2. **Inspect** — `inspect_openapi.py --spec <path>` to validate the spec and list operations.
3. **Plan** — `build_plan.py --spec <path> --config <yaml> --out generated-tests/plan.json`.
4. **Review** — Present test counts, mutation/performance cases, and `requires_approval` flags. Do not run destructive or load tests without explicit user approval.
5. **Validate** — `validate_plan.py` before execution.
6. **Run** — `run_jmeter.py` (or `--executor python` when JMeter is unavailable). Never regenerate the plan during `run`.
7. **Analyze & report** — `analyze_results.py` and `make_report.py` for coverage and Markdown output.

## Commands (from repo root)

```bash
pip install -e ".[dev]"
api-test-agent inspect --spec <spec>
api-test-agent plan --spec <spec> --config <config> --out generated-tests/plan.json
api-test-agent validate-plan --plan generated-tests/plan.json
api-test-agent run --plan generated-tests/plan.json --config <config> --profile functional --approve
api-test-agent report --run-dir results/<run-id> --spec <spec>
```

## Safety

- Confirm `base_url` and `allowed_hosts` with the user before the first run.
- Require `--approve` for performance profiles and for mutations unless `disposable_test_environment` and `allow_mutations` are set in config.
- Do not invent business rules; label hypotheses and show coverage gaps.
- Never treat LLM summaries as metrics; use `results.json` and JTL.

## References

- `references/test-strategy.md`
- `references/safety-policy.md`
- `references/coverage-model.md`
- `references/reporting-contract.md`
