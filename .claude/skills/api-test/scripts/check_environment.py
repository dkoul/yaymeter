#!/usr/bin/env python3
import subprocess
import sys


def main() -> int:
    return subprocess.call([sys.executable, "-m", "api_test_agent.cli", "check-environment"])


if __name__ == "__main__":
    raise SystemExit(main())
