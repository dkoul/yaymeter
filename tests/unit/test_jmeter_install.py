import ssl
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from api_test_agent.jmeter_install import (
    download_bytes,
    adoptium_platform,
    discover_jdk_home,
    parse_version,
    read_local_java_home,
    read_local_jmeter_home,
    resolve_jdk_home,
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


def test_adoptium_platform_linux():
    import platform

    if platform.system().lower() == "linux":
        assert adoptium_platform()[0] == "linux"


def test_resolve_jdk_home_linux_layout(tmp_path: Path):
    root = tmp_path / "jdk-21.0.12+7"
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "java").write_text("", encoding="utf-8")
    assert resolve_jdk_home(root) == root


def test_resolve_jdk_home_macos_layout(tmp_path: Path):
    root = tmp_path / "jdk-21.0.12.1+12"
    home = root / "Contents" / "Home"
    (home / "bin").mkdir(parents=True)
    (home / "bin" / "java").write_text("", encoding="utf-8")
    assert resolve_jdk_home(root) == home


def test_read_local_java_home_macos_marker(tmp_path: Path):
    tools = tmp_path / ".tools"
    root = tools / "jdk-21.0.12.1+12"
    home = root / "Contents" / "Home"
    (home / "bin").mkdir(parents=True)
    (home / "bin" / "java").write_text("", encoding="utf-8")
    (tools / "java-home").write_text(str(root) + "\n", encoding="utf-8")
    assert read_local_java_home(tools) == home


def test_discover_jdk_home_picks_newest(tmp_path: Path):
    tools = tmp_path / ".tools"
    tools.mkdir()
    old = tools / "jdk-21.0.1+1"
    (old / "bin").mkdir(parents=True)
    (old / "bin" / "java").write_text("", encoding="utf-8")
    new = tools / "jdk-21.0.12.1+12"
    (new / "bin").mkdir(parents=True)
    (new / "bin" / "java").write_text("", encoding="utf-8")
    import os
    import time

    os.utime(old, (time.time() - 100, time.time() - 100))
    os.utime(new, (time.time(), time.time()))
    assert discover_jdk_home(tools) == new


def test_download_bytes_insecure_opt_in():
    payload = b"archive-bytes"
    good_response = MagicMock()
    good_response.read.return_value = payload
    good_response.__enter__ = lambda self: self
    good_response.__exit__ = MagicMock(return_value=False)

    ssl_err = ssl.SSLCertVerificationError("certificate verify failed")
    with patch.dict("os.environ", {"YAYMETER_INSECURE_DOWNLOAD": "1"}):
        with patch(
            "api_test_agent.jmeter_install.urlopen",
            side_effect=[ssl_err, good_response],
        ) as mock_open:
            assert download_bytes("https://example.test/file.tgz", timeout=10) == payload
    assert mock_open.call_count == 2
    assert mock_open.call_args_list[1].kwargs.get("context") is not None


def test_wrapper_points_at_home(tmp_path: Path):
    tools = tmp_path / ".tools"
    home = tools / "apache-jmeter-5.6.3"
    (home / "bin").mkdir(parents=True)
    shim = tools / "bin" / "jmeter"
    _write_jmeter_wrapper(shim, home.resolve())
    text = shim.read_text(encoding="utf-8")
    assert f'JMETER_HOME="{home.resolve()}"' in text
