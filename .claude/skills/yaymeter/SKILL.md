# Yaymeter

Use this skill to inspect an OpenAPI spec, build a deterministic test plan, obtain user approval for risky tests, **run with JMeter (default)**, and produce a Markdown report.

**Do not ask users to install Java or JMeter manually.** Yaymeter auto-downloads portable JRE + JMeter to `.tools/` on first `run`. Use `--executor python` only when the user explicitly wants a JVM-free fallback.

## Workflow

1. **Environment** — `python3 .claude/skills/yaymeter/scripts/check_environment.py`
2. **Inspect** — `inspect_openapi.py --spec <path>`
3. **Plan** — `build_plan.py --spec <path> --config <yaml> --out generated-tests/plan.json`
4. **Export JMX** — `export_jmx.py --plan generated-tests/plan.json --out generated-tests/plan.jmx` (commit this for CI)
5. **Review** — Present test counts, mutation/performance cases, and `requires_approval` flags
6. **Validate** — `validate_plan.py`
7. **Run** — Functional: `yaymeter run-jmx --jmx generated-tests/plan.jmx --threads 1 --loops 1`. Load: same JMX with higher `--threads` / `--loops` and `--approve`. Or `run_jmeter.py` → `yaymeter run`.
8. **Analyze & report** — `analyze_results.py`, `make_report.py`

## Commands (from repo root)

```bash
pip install -e ".[dev]"
yaymeter check-environment
yaymeter inspect --spec <spec>
yaymeter plan --spec <spec> --config <config> --out generated-tests/plan.json
yaymeter validate-plan --plan generated-tests/plan.json
yaymeter export-jmx --plan generated-tests/plan.json --out generated-tests/plan.jmx
yaymeter run-jmx --jmx generated-tests/plan.jmx --config <config> --threads 1 --loops 1 --approve
# Load (same JMX): --threads 25 --ramp-seconds 60 --loops 30 --approve
yaymeter report --run-dir results/<run-id> --spec <spec>
```

Optional prefetch: `yaymeter install-runtime`

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
