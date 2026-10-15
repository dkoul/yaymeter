# Safety policy

- Default: read-only functional profile, no production targets.
- Mutations and DELETE require approval unless disposable test environment is configured.
- Performance requires `--approve` and `allow_performance` in config.
- Reject hosts outside `allowed_hosts`.
- Redact secrets in logs and reports.
