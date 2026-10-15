from pathlib import Path

from api_test_agent.jmeter_install import (
    parse_version,
    read_local_jmeter_home,
    version_at_least,
    _write_jmeter_wrapper,
)


def test_version_at_least():
    assert version_at_least("5.6.3", (5, 6))
    assert version_at_least("5.7.0", (5, 6))
    assert not version_at_least("5.5.1", (5, 6))


def test_parse_version():
    assert parse_version("5.6.3") == (5, 6, 3)


def test_read_local_jmeter_home(tmp_path: Path):
    tools = tmp_path / ".tools"
    home = tools / "apache-jmeter-5.6.3"
    (home / "bin").mkdir(parents=True)
    (home / "bin" / "jmeter").write_text("#!/bin/sh\n", encoding="utf-8")
    (tools / "jmeter-home").write_text(str(home) + "\n", encoding="utf-8")

    assert read_local_jmeter_home(tools) == home


def test_wrapper_points_at_home(tmp_path: Path):
    tools = tmp_path / ".tools"
    home = tools / "apache-jmeter-5.6.3"
    (home / "bin").mkdir(parents=True)
    shim = tools / "bin" / "jmeter"
    _write_jmeter_wrapper(shim, home.resolve())
    text = shim.read_text(encoding="utf-8")
    assert f'JMETER_HOME="{home.resolve()}"' in text
