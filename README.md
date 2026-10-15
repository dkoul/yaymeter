# Yaymeter

**[Project site](https://dkoul.github.io/yaymeter/)** — overview for testers and quick visual tour.

Turn an **OpenAPI spec** into a **JMeter test plan** (`.jmx`), run it locally or in **CI**, and get a Markdown report. Works with **Claude Code** via the skill in [`.claude/skills/yaymeter/SKILL.md`](.claude/skills/yaymeter/SKILL.md).

You need **Python 3.11+** only. Yaymeter downloads Java + JMeter into `.tools/` automatically when you first run tests.

---

## What you get

| Artifact | Purpose |
|----------|---------|
| `generated-tests/plan.json` | Deterministic test cases (review, diff, validate) |
| **`generated-tests/plan.jmx`** | **One JMeter plan** for functional *and* load runs (commit this for CI) |
| `results/.../results.jtl` | Raw JMeter results |
| `reports/....md` | Human-readable report with coverage gaps |

The `.jmx` uses JMeter properties (`yaymeter.threads`, `yaymeter.ramp_seconds`, `yaymeter.loops`). **Functional** and **load** runs use the **same file**; only the `-J` flags change.

---

## 1. Install

```bash
git clone https://github.com/dkoul/yaymeter.git
cd yaymeter
pip install -e ".[dev]"
```

---

## 2. Point at your API

Copy and edit the config (base URL + safety):

```bash
cp examples/test-config.yaml my-api.yaml
```

```yaml
# my-api.yaml
base_url: https://api.example.com
target_label: staging
allowed_hosts:
  - api.example.com
disposable_test_environment: false   # set true only for throwaway envs
allow_mutations: false
allow_performance: false             # set true before load tests
auth:
  type: none
  env_var: API_TEST_AUTH_TOKEN       # Bearer token from env in JMeter
```

Export a token if needed:

```bash
export API_TEST_AUTH_TOKEN="your-token"
```

---

## 3. OpenAPI → test plan → JMX

Replace `openapi.yaml` with your spec.

```bash
# Optional: validate spec and list operations
yaymeter inspect --spec openapi.yaml

# Build deterministic test plan
yaymeter plan --spec openapi.yaml --config my-api.yaml --out generated-tests/plan.json
yaymeter validate-plan --plan generated-tests/plan.json

# Export the JMeter plan (commit this file for CI)
yaymeter export-jmx --plan generated-tests/plan.json --out generated-tests/plan.jmx
```

**Using Claude:** open the repo in Claude Code, enable the **Yaymeter** skill, and ask it to run the steps above for your spec and config. It should not ask you to install Java or JMeter manually.

---

## 4. Run tests

### Functional (single virtual user)

One thread, one loop — smoke / contract style:

```bash
yaymeter run-jmx --jmx generated-tests/plan.jmx --config my-api.yaml \
  --threads 1 --loops 1 --approve
```

Or the full pipeline (plan → JMeter → report) in one step:

```bash
yaymeter run --plan generated-tests/plan.json --config my-api.yaml \
  --profile functional --approve

yaymeter report --run-dir results/<run-id> --spec openapi.yaml
```

(`run` also refreshes `generated-tests/plan.jmx`.)

### Load (multiple virtual users)

Same `plan.jmx`, higher threads and loops. Requires `allow_performance: true` in config and `--approve`:

```yaml
# my-api.yaml (load section)
allow_performance: true
performance:
  threads: 25
  ramp_up_seconds: 60
  loops: 30
```

```bash
yaymeter run-jmx --jmx generated-tests/plan.jmx --config my-api.yaml \
  --threads 25 --ramp-seconds 60 --loops 30 --approve
```

Or:

```bash
yaymeter run --plan generated-tests/plan.json --config my-api.yaml \
  --profile performance --approve
```

---

## 5. Reuse the same JMX in CI

Check in `generated-tests/plan.jmx` (and optionally `plan.json`). In GitHub Actions / GitLab CI / Jenkins, install JMeter (or use a JMeter image) and run:

**Functional job**

```bash
jmeter -n \
  -t generated-tests/plan.jmx \
  -l results/ci-functional.jtl \
  -j results/jmeter.log \
  -Jyaymeter.threads=1 \
  -Jyaymeter.ramp_seconds=1 \
  -Jyaymeter.loops=1
```

**Load job** (nightly or gated)

```bash
jmeter -n \
  -t generated-tests/plan.jmx \
  -l results/ci-load.jtl \
  -j results/jmeter.log \
  -Jyaymeter.threads=25 \
  -Jyaymeter.ramp_seconds=60 \
  -Jyaymeter.loops=30
```

Set `API_TEST_AUTH_TOKEN` (and any other secrets) in CI secrets — they are **not** baked into the JMX.

**Yaymeter wrapper in CI** (auto-installs JRE + JMeter on the runner):

```bash
pip install -e .
yaymeter run-jmx --jmx generated-tests/plan.jmx --config my-api.yaml \
  --threads 1 --loops 1 --approve --run-dir results --run-id ci
```

Fail the job if `results/ci/jmeter_exit_code.txt` is not `0`.

---

## Command cheat sheet

| Command | When |
|---------|------|
| `yaymeter inspect --spec …` | Validate OpenAPI, list operations |
| `yaymeter plan --spec … --config … --out …` | Generate `plan.json` |
| `yaymeter export-jmx --plan … --out generated-tests/plan.jmx` | **Produce CI-ready JMX** |
| `yaymeter run-jmx --jmx … --threads 1` | Functional JMeter run |
| `yaymeter run-jmx --jmx … --threads N` | Load JMeter run |
| `yaymeter run --plan … --profile functional` | Plan + JMeter + results |
| `yaymeter report --run-dir … --spec …` | Markdown report |

Alias: `api-test-agent` = `yaymeter`.

---

## Safety defaults

- Confirm `base_url` and `allowed_hosts` before hitting a real environment.
- Mutations and multi-user load need `--approve` and appropriate config flags.
- Do not point load tests at production without an explicit disposable test policy.

## License

MIT
