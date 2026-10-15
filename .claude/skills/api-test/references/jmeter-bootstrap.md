# Runtime bootstrap (optional)

**Users should not need this for normal functional API tests.** The default `run` executor is Python (no JVM).

When JMeter is required (explicit `--executor jmeter` or `performance` profile), the CLI can **auto-install** into `.tools/`:

- Eclipse Temurin JRE 21 (portable, no system Java)
- Apache JMeter 5.6.3

Manual prefetch (optional):

```bash
api-test-agent install-runtime
```

Helpers: `.tools/runtime-env.sh` (and legacy `.tools/jmeter-env.sh`). Subprocess runs set `JAVA_HOME` / `JMETER_HOME` automatically when `.tools/` is present.

Skill script: `install_runtime.py`
