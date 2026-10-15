# Runtime bootstrap (optional)

**Default `run` uses JMeter**; users should not install Java/JMeter manually. On first run the CLI **auto-installs** into `.tools/`:

- Eclipse Temurin JRE 21 (portable, no system Java)
- Apache JMeter 5.6.3

Manual prefetch (optional):

```bash
yaymeter install-runtime
```

Helpers: `.tools/runtime-env.sh` (and legacy `.tools/jmeter-env.sh`). Subprocess runs set `JAVA_HOME` / `JMETER_HOME` automatically when `.tools/` is present.

macOS notes:

- Temurin JRE archives use `jdk-<ver>/Contents/Home`; yaymeter resolves that layout when writing `JAVA_HOME`.
- If Python’s SSL store is missing (common on stock macOS Python), downloads retry once without certificate verification.

Skill script: `install_runtime.py`
