#!/usr/bin/env python3
import subprocess
import sys


def main() -> int:
    # CLI uses --plan; accept --plan from argv as-is
    args = ["-m", "api_test_agent.cli", "validate-plan"] + sys.argv[1:]
    return subprocess.call([sys.executable, *args])


if __name__ == "__main__":
    raise SystemExit(main())
