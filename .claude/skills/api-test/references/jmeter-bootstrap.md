# JMeter bootstrap

From the repository root:

```bash
api-test-agent install-jmeter
source .tools/jmeter-env.sh
api-test-agent check-environment
```

- Installs Apache JMeter 5.6.3 under `.tools/apache-jmeter-5.6.3/` (gitignored).
- Writes `.tools/jmeter-home`, `.tools/bin/jmeter` (PATH shim), and `.tools/jmeter-env.sh`.
- Requires Java on `PATH`. Override version with `install-jmeter --version 5.6.3`.
- `find_jmeter()` also honors `JMETER_HOME` and `API_TEST_JMETER_HOME`.

Skill script: `.claude/skills/api-test/scripts/install_jmeter.py`
