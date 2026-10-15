#!/usr/bin/env python3
import subprocess
import sys


def main() -> int:
    args = ["-m", "api_test_agent.cli", "plan"] + sys.argv[1:]
    return subprocess.call([sys.executable, *args])


if __name__ == "__main__":
    raise SystemExit(main())
