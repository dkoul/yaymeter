"""Invoke JMeter in non-GUI mode."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from api_test_agent.jmeter_install import local_jmeter_bin
from api_test_agent.models import RunManifest, utc_now_iso


class JMeterNotFoundError(Exception):
    pass


def find_jmeter() -> str | None:
    for env_name in ("JMETER_HOME", "API_TEST_JMETER_HOME"):
        env = os.environ.get(env_name)
        if env:
            candidate = Path(env) / "bin" / "jmeter"
            if candidate.exists():
                return str(candidate)
    local = local_jmeter_bin()
    if local:
        return local
    return shutil.which("jmeter")


def jmeter_version(jmeter_bin: str | None = None) -> str | None:
    bin_path = jmeter_bin or find_jmeter()
    if not bin_path:
        return None
    try:
        proc = subprocess.run(
            [bin_path, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        for pattern in (
            r"Version\s+([\d.]+)",
            r"\\_\s+([\d]+\.[\d]+\.[\d]+)\s*$",
            r"Apache JMeter\s*\(?([\d.]+)\)?",
        ):
            m = re.search(pattern, out, re.MULTILINE | re.IGNORECASE)
            if m:
                return m.group(1)
        found = re.findall(r"\b(\d+\.\d+\.\d+)\b", out)
        if found:
            return found[-1]
        return None
    except (OSError, subprocess.TimeoutExpired):
        return None


def run_jmeter(
    jmx_path: Path,
    results_dir: Path,
    run_id: str | None = None,
    timeout_seconds: float = 300.0,
) -> tuple[Path, Path, RunManifest]:
    jmeter = find_jmeter()
    if not jmeter:
        raise JMeterNotFoundError(
            "JMeter not found. Run `api-test-agent install-jmeter` or set JMETER_HOME / PATH. "
            "See `api-test-agent check-environment --help`."
        )

    run_id = run_id or f"run-{uuid.uuid4().hex[:12]}"
    results_dir = Path(results_dir) / run_id
    results_dir.mkdir(parents=True, exist_ok=True)

    jtl = results_dir / "results.jtl"
    log = results_dir / "jmeter.log"

    cmd = [
        jmeter,
        "-n",
        "-t",
        str(jmx_path),
        "-l",
        str(jtl),
        "-j",
        str(log),
    ]

    started = utc_now_iso()
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )

    manifest = RunManifest(
        run_id=run_id,
        spec_hash="",
        config_hash="",
        seed=0,
        generator_version="",
        python_version=sys.version.split()[0],
        jmeter_version=jmeter_version(jmeter),
        profile="functional",
        started_at=started,
        finished_at=utc_now_iso(),
        base_url="",
        target_label="",
        artifacts={
            "jmx": str(jmx_path),
            "jtl": str(jtl),
            "jmeter_log": str(log),
        },
        command_args=cmd,
    )

    (results_dir / "jmeter_stdout.txt").write_text(proc.stdout or "", encoding="utf-8")
    (results_dir / "jmeter_stderr.txt").write_text(proc.stderr or "", encoding="utf-8")
    (results_dir / "jmeter_exit_code.txt").write_text(str(proc.returncode), encoding="utf-8")

    return jtl, log, manifest
