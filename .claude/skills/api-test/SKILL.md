# API Test Agent

Use this skill to inspect an OpenAPI spec, build a deterministic test plan, obtain user approval for risky tests, execute tests, and produce a Markdown report.

**Do not ask users to install Java or JMeter.** Functional testing uses the built-in Python executor (default). Only fetch the JMeter runtime when the user explicitly wants JMeter-based execution or performance/load testing.

## Workflow

1. **Environment** — `python3 .claude/skills/api-test/scripts/check_environment.py` (confirms Python; JVM is optional).
2. **Inspect** — `inspect_openapi.py --spec <path>`.
3. **Plan** — `build_plan.py --spec <path> --config <yaml> --out generated-tests/plan.json`.
4. **Review** — Present test counts, mutation/performance cases, and `requires_approval` flags.
5. **Validate** — `validate_plan.py`.
6. **Run** — `run_jmeter.py` passes through to `api-test-agent run` (default **python** executor). For performance profiles, the CLI switches to JMeter and auto-downloads portable Java + JMeter to `.tools/` if needed—still no manual setup.
7. **Analyze & report** — `analyze_results.py`, `make_report.py`.

## Commands (from repo root)

```bash
pip install -e ".[dev]"
api-test-agent check-environment
api-test-agent inspect --spec <spec>
api-test-agent plan --spec <spec> --config <config> --out generated-tests/plan.json
api-test-agent validate-plan --plan generated-tests/plan.json
api-test-agent run --plan generated-tests/plan.json --config <config> --profile functional --approve
api-test-agent report --run-dir results/<run-id> --spec <spec>
```

Optional (only for explicit JMeter/load needs):

```bash
api-test-agent install-runtime   # portable JRE + JMeter in .tools/
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
- `references/jmeter-bootstrap.md`
