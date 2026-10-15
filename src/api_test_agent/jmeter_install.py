"""Download and install Apache JMeter into a local .tools directory."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import ssl
import subprocess
import tarfile
import tempfile
import warnings
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.request import urlopen

try:
    import certifi
except ImportError:  # pragma: no cover
    certifi = None

DEFAULT_JMETER_VERSION = "5.6.3"
MIN_JMETER_VERSION = (5, 6)

APACHE_MIRRORS: tuple[str, ...] = (
    "https://dlcdn.apache.org/jmeter/binaries/apache-jmeter-{version}.tgz",
    "https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-{version}.tgz",
)

JMETER_HOME_FILE = "jmeter-home"
JAVA_HOME_FILE = "java-home"
DEFAULT_JAVA_FEATURE = "21"


class JMeterInstallError(Exception):
    pass


def _is_ssl_verify_error(exc: BaseException) -> bool:
    if isinstance(exc, ssl.SSLCertVerificationError):
        return True
    if isinstance(exc, URLError) and isinstance(exc.reason, ssl.SSLCertVerificationError):
        return True
    message = str(exc)
    return "CERTIFICATE_VERIFY_FAILED" in message or "certificate verify failed" in message.lower()


def _unverified_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _ssl_context() -> ssl.SSLContext:
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def download_bytes(url: str, timeout: float) -> bytes:
    """Fetch URL bytes with verified TLS (certifi). Opt-in insecure fallback via env."""
    insecure = os.environ.get("YAYMETER_INSECURE_DOWNLOAD") == "1"
    try:
        with urlopen(url, timeout=timeout, context=_ssl_context()) as response:
            return response.read()
    except ssl.SSLCertVerificationError as exc:
        if insecure:
            warnings.warn(
                "YAYMETER_INSECURE_DOWNLOAD=1: downloading without TLS verification",
                stacklevel=2,
            )
            with urlopen(url, timeout=timeout, context=_unverified_ssl_context()) as response:
                return response.read()
        raise JMeterInstallError(
            "TLS certificate verification failed while downloading runtime. "
            "Install certifi (included with yaymeter) or fix system CA certificates. "
            "Last resort only: YAYMETER_INSECURE_DOWNLOAD=1"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        if _is_ssl_verify_error(exc) and insecure:
            warnings.warn(
                "YAYMETER_INSECURE_DOWNLOAD=1: downloading without TLS verification",
                stacklevel=2,
            )
            with urlopen(url, timeout=timeout, context=_unverified_ssl_context()) as response:
                return response.read()
        raise


def _verify_sha512(data: bytes, expected_line: str, filename: str) -> None:
    """Parse Apache-style sha512 sum file and verify archive bytes."""
    digest = None
    for line in expected_line.splitlines():
        line = line.strip()
        if not line or filename not in line:
            continue
        parts = line.split()
        if parts:
            digest = parts[0].lower()
            break
    if not digest:
        raise JMeterInstallError(f"Could not parse checksum for {filename}")
    actual = hashlib.sha512(data).hexdigest().lower()
    if actual != digest:
        raise JMeterInstallError(f"Checksum mismatch for {filename}")


def _verify_jmeter_archive(version: str, archive_bytes: bytes) -> None:
    archive_name = f"apache-jmeter-{version}.tgz"
    checksum_urls = [
        f"https://dlcdn.apache.org/jmeter/binaries/{archive_name}.sha512",
        f"https://archive.apache.org/dist/jmeter/binaries/{archive_name}.sha512",
    ]
    last_error: Exception | None = None
    for url in checksum_urls:
        try:
            checksum_text = download_bytes(url, timeout=60).decode("utf-8", errors="replace")
            _verify_sha512(archive_bytes, checksum_text, archive_name)
            return
        except (URLError, TimeoutError, OSError, JMeterInstallError) as exc:
            last_error = exc
    raise JMeterInstallError(f"Could not verify JMeter archive checksum: {last_error}")


def adoptium_jre_asset() -> dict:
    os_name, arch = adoptium_platform()
    api_url = (
        "https://api.adoptium.net/v3/assets/latest/"
        f"{DEFAULT_JAVA_FEATURE}/hotspot?architecture={arch}&image_type=jre&os={os_name}&vendor=eclipse"
    )
    raw = download_bytes(api_url, timeout=120)
    assets = json.loads(raw.decode("utf-8"))
    if not assets:
        raise JMeterInstallError("Adoptium API returned no JRE assets")
    return assets[0]


def _verify_adoptium_archive(asset: dict, archive_bytes: bytes) -> None:
    for checksum in asset.get("checksums", []):
        if checksum.get("algorithm") != "sha256":
            continue
        expected = checksum.get("checksum", "").lower()
        actual = hashlib.sha256(archive_bytes).hexdigest().lower()
        if actual != expected:
            raise JMeterInstallError("Adoptium JRE archive checksum mismatch")
        return
    raise JMeterInstallError("Adoptium asset metadata missing sha256 checksum")


def resolve_jdk_home(candidate: Path) -> Path | None:
    """
    Normalize a Temurin JRE/JDK extract to JAVA_HOME.

    macOS archives use ``jdk-<ver>/Contents/Home``; Linux uses ``jdk-<ver>/`` directly.
    """
    if (candidate / "bin" / "java").is_file():
        return candidate
    nested = candidate / "Contents" / "Home"
    if (nested / "bin" / "java").is_file():
        return nested
    return None


def discover_jdk_home(tools_dir: Path) -> Path | None:
    """Find the newest bundled jdk-* directory under tools_dir."""
    homes: list[Path] = []
    for candidate in tools_dir.glob("jdk-*"):
        resolved = resolve_jdk_home(candidate)
        if resolved:
            homes.append(resolved)
    if not homes:
        return None
    return max(homes, key=lambda p: p.stat().st_mtime)


def parse_version(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in re.split(r"[.\-+]", version):
        if piece.isdigit():
            parts.append(int(piece))
        elif parts:
            break
    return tuple(parts)


def version_at_least(version: str, minimum: tuple[int, ...]) -> bool:
    current = parse_version(version)
    width = max(len(current), len(minimum))
    cur = current + (0,) * (width - len(current))
    minv = minimum + (0,) * (width - len(minimum))
    return cur >= minv


def adoptium_platform() -> tuple[str, str]:
    import platform

    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        os_name = "mac"
        arch = "aarch64" if machine in ("arm64", "aarch64") else "x64"
    elif system == "linux":
        os_name = "linux"
        arch = "aarch64" if machine in ("arm64", "aarch64") else "x64"
    elif system == "windows":
        os_name = "windows"
        arch = "x64"
    else:
        raise JMeterInstallError(f"Unsupported OS for bundled JRE: {system}")
    return os_name, arch


def read_local_java_home(tools_dir: Path | None = None) -> Path | None:
    tools = tools_dir or discover_tools_dir()
    if not tools:
        return None
    marker = tools / JAVA_HOME_FILE
    if marker.is_file():
        raw = Path(marker.read_text(encoding="utf-8").strip())
        home = resolve_jdk_home(raw) or raw
        if (home / "bin" / "java").exists():
            return home
    return discover_jdk_home(tools)


def find_java(tools_dir: Path | None = None) -> str | None:
    """Prefer bundled JRE in .tools, then system Java on PATH."""
    bundled = read_local_java_home(tools_dir)
    if bundled:
        java_bin = bundled / "bin" / "java"
        if java_bin.exists():
            return str(java_bin)
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidate = Path(java_home) / "bin" / "java"
        if candidate.exists():
            return str(candidate)
    return shutil.which("java")


def java_works(java_bin: str) -> bool:
    proc = subprocess.run(
        [java_bin, "-version"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return proc.returncode == 0


def require_java(tools_dir: Path | None = None) -> str:
    java = find_java(tools_dir)
    if not java or not java_works(java):
        raise JMeterInstallError(
            "Java runtime not found. Run `yaymeter install-runtime` to download a "
            "portable JRE into .tools/, or install Java 8+ on PATH."
        )
    return java


def adoptium_jre_url() -> str:
    os_name, arch = adoptium_platform()
    return (
        "https://api.adoptium.net/v3/binary/latest/"
        f"{DEFAULT_JAVA_FEATURE}/ga/{os_name}/{arch}/jre/hotspot/normal/eclipse?project=jdk"
    )


def install_portable_java(
    project_root: Path | None = None,
    force: bool = False,
) -> Path:
    """Download Eclipse Temurin JRE into .tools/ (no system Java required)."""
    root = project_root or Path.cwd()
    tools_dir = root / ".tools"
    tools_dir.mkdir(parents=True, exist_ok=True)

    existing = read_local_java_home(tools_dir)
    if existing and not force:
        return existing

    os_name, _arch = adoptium_platform()
    if os_name == "windows":
        raise JMeterInstallError(
            "Bundled JRE auto-install is not implemented on Windows yet. "
            "Install a JRE manually or use --executor python for functional tests."
        )

    try:
        asset = adoptium_jre_asset()
        download_link = asset["binary"]["package"]["link"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise JMeterInstallError(f"Could not resolve Adoptium JRE download: {exc}") from exc

    with tempfile.TemporaryDirectory() as tmp:
        archive_path = Path(tmp) / "temurin-jre.tar.gz"
        try:
            archive_bytes = download_bytes(download_link, timeout=300)
            _verify_adoptium_archive(asset, archive_bytes)
            archive_path.write_bytes(archive_bytes)
        except (URLError, TimeoutError, OSError, JMeterInstallError) as exc:
            raise JMeterInstallError(f"Could not download portable JRE: {exc}") from exc

        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=tools_dir)

    home = discover_jdk_home(tools_dir)
    if not home:
        raise JMeterInstallError(
            "Portable JRE archive did not extract a usable jdk-* directory "
            "(expected bin/java or Contents/Home/bin/java on macOS)"
        )

    (tools_dir / JAVA_HOME_FILE).write_text(str(home.resolve()) + "\n", encoding="utf-8")
    return home


def ensure_java(project_root: Path | None = None, allow_download: bool = True) -> str:
    root = project_root or Path.cwd()
    tools_dir = root / ".tools"
    java = find_java(tools_dir)
    if java and java_works(java):
        return java
    if not allow_download:
        return require_java(tools_dir)
    install_portable_java(project_root=root)
    return require_java(tools_dir)


def runtime_env(project_root: Path | None = None) -> dict[str, str]:
    """Environment variables for subprocess JMeter invocations."""
    env = os.environ.copy()
    root = project_root or Path.cwd()
    tools = discover_tools_dir(root) or root / ".tools"
    java_home = read_local_java_home(tools)
    jmeter_home = read_local_jmeter_home(tools)
    if java_home:
        env["JAVA_HOME"] = str(java_home)
        env["PATH"] = str(java_home / "bin") + os.pathsep + env.get("PATH", "")
    if jmeter_home:
        env["JMETER_HOME"] = str(jmeter_home)
        env["PATH"] = str(tools / "bin") + os.pathsep + env.get("PATH", "")
    return env


def discover_tools_dir(start: Path | None = None) -> Path | None:
    """Find repo .tools directory containing a JMeter install marker."""
    start = start or Path.cwd()
    for base in [start, *start.parents]:
        tools = base / ".tools"
        if (tools / JMETER_HOME_FILE).is_file():
            return tools
        if any(tools.glob("apache-jmeter-*/bin/jmeter")):
            return tools
    return None


def read_local_jmeter_home(tools_dir: Path | None = None) -> Path | None:
    tools = tools_dir or discover_tools_dir()
    if not tools:
        return None
    marker = tools / JMETER_HOME_FILE
    if marker.is_file():
        home = Path(marker.read_text(encoding="utf-8").strip())
        if (home / "bin" / "jmeter").exists():
            return home
    for candidate in sorted(tools.glob("apache-jmeter-*")):
        if (candidate / "bin" / "jmeter").exists():
            return candidate
    return None


def local_jmeter_bin() -> str | None:
    home = read_local_jmeter_home()
    if not home:
        return None
    bin_path = home / "bin" / "jmeter"
    return str(bin_path) if bin_path.exists() else None


def local_tools_bin_dir() -> Path | None:
    tools = discover_tools_dir()
    if not tools:
        return None
    shim = tools / "bin" / "jmeter"
    return tools / "bin" if shim.exists() else None


def jmeter_download_urls(version: str) -> Iterable[str]:
    for template in APACHE_MIRRORS:
        yield template.format(version=version)


def download_jmeter_archive(version: str, dest: Path) -> Path:
    last_error: Exception | None = None
    for url in jmeter_download_urls(version):
        try:
            archive_bytes = download_bytes(url, timeout=120)
            _verify_jmeter_archive(version, archive_bytes)
            dest.write_bytes(archive_bytes)
            return dest
        except (URLError, TimeoutError, OSError, JMeterInstallError) as exc:
            last_error = exc
    raise JMeterInstallError(
        f"Could not download Apache JMeter {version} from Apache mirrors: {last_error}"
    )


def _write_jmeter_wrapper(
    shim_path: Path,
    jmeter_home: Path,
    java_home: Path | None = None,
) -> None:
    shim_path.parent.mkdir(parents=True, exist_ok=True)
    java_line = f'export JAVA_HOME="{java_home}"\n' if java_home else ""
    content = f"""#!/bin/sh
# Generated by yaymeter install-runtime
{java_line}export JMETER_HOME="{jmeter_home}"
exec "$JMETER_HOME/bin/jmeter" "$@"
"""
    shim_path.write_text(content, encoding="utf-8")
    shim_path.chmod(shim_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write_env_snippet(
    tools_dir: Path,
    jmeter_home: Path,
    java_home: Path | None = None,
) -> Path:
    snippet = tools_dir / "runtime-env.sh"
    legacy = tools_dir / "jmeter-env.sh"
    lines = ["# Generated by yaymeter install-runtime"]
    if java_home:
        lines.append(f'export JAVA_HOME="{java_home}"')
        lines.append(f'export PATH="{java_home / "bin"}:$PATH"')
    lines.extend(
        [
            f'export JMETER_HOME="{jmeter_home}"',
            f'export PATH="{tools_dir / "bin"}:$PATH"',
            "",
        ]
    )
    text = "\n".join(lines)
    snippet.write_text(text, encoding="utf-8")
    legacy.write_text(text, encoding="utf-8")
    return snippet


def install_jmeter(
    version: str = DEFAULT_JMETER_VERSION,
    project_root: Path | None = None,
    force: bool = False,
    with_java: bool = True,
) -> Path:
    """
    Download and extract JMeter under <project_root>/.tools and write PATH/JMETER_HOME helpers.

    Returns JMETER_HOME path.
    """
    if not version_at_least(version, MIN_JMETER_VERSION):
        raise JMeterInstallError(f"JMeter version must be >= {MIN_JMETER_VERSION[0]}.{MIN_JMETER_VERSION[1]}")

    root = project_root or Path.cwd()
    tools_dir = root / ".tools"
    tools_dir.mkdir(parents=True, exist_ok=True)

    if with_java:
        ensure_java(project_root=root, allow_download=True)
    else:
        require_java(tools_dir)

    existing = read_local_jmeter_home(tools_dir)
    if existing and not force:
        installed_version = jmeter_version_from_home(existing)
        if installed_version and version_at_least(installed_version, MIN_JMETER_VERSION):
            _refresh_runtime_helpers(tools_dir, existing)
            return existing

    archive_name = f"apache-jmeter-{version}.tgz"
    extract_dir = tools_dir / f"apache-jmeter-{version}"

    with tempfile.TemporaryDirectory() as tmp:
        archive_path = Path(tmp) / archive_name
        download_jmeter_archive(version, archive_path)
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=tools_dir)

    if not extract_dir.exists():
        raise JMeterInstallError(f"Expected extracted directory missing: {extract_dir}")

    jmeter_bin = extract_dir / "bin" / "jmeter"
    if not jmeter_bin.exists():
        raise JMeterInstallError(f"JMeter binary not found at {jmeter_bin}")

    (tools_dir / JMETER_HOME_FILE).write_text(str(extract_dir.resolve()) + "\n", encoding="utf-8")
    _refresh_runtime_helpers(tools_dir, extract_dir.resolve())

    installed_version = jmeter_version_from_home(extract_dir)
    if not installed_version or not version_at_least(installed_version, MIN_JMETER_VERSION):
        raise JMeterInstallError(
            f"Installed JMeter version {installed_version!r} does not meet minimum 5.6+"
        )

    return extract_dir


def jmeter_version_from_home(home: Path) -> str | None:
    from api_test_agent.jmeter_runner import jmeter_version

    bin_path = home / "bin" / "jmeter"
    if not bin_path.exists():
        return None
    return jmeter_version(str(bin_path))


def _refresh_runtime_helpers(tools_dir: Path, jmeter_home: Path) -> None:
    java_home = read_local_java_home(tools_dir)
    _write_jmeter_wrapper(tools_dir / "bin" / "jmeter", jmeter_home, java_home)
    _write_env_snippet(tools_dir, jmeter_home, java_home)


def install_runtime(
    version: str = DEFAULT_JMETER_VERSION,
    project_root: Path | None = None,
    force: bool = False,
) -> Path:
    """Download portable JRE (if needed) and JMeter into .tools/."""
    return install_jmeter(
        version=version,
        project_root=project_root,
        force=force,
        with_java=True,
    )


def activation_instructions(project_root: Path | None = None) -> str:
    root = project_root or Path.cwd()
    tools = root / ".tools"
    home = read_local_jmeter_home(tools)
    if not home:
        return (
            "JMeter runtime not installed. Run `yaymeter run` (auto-install) or `yaymeter install-runtime`.\n"
            "JVM-free fallback: yaymeter run --executor python"
        )
    java = read_local_java_home(tools)
    snippet = tools / "runtime-env.sh"
    lines = [f"JMETER_HOME={home}"]
    if java:
        lines.append(f"JAVA_HOME={java} (bundled)")
    lines.append(f"Optional shell setup: source {snippet}")
    return "\n".join(lines)


def ensure_jmeter(
    version: str = DEFAULT_JMETER_VERSION,
    project_root: Path | None = None,
    with_java: bool = True,
) -> Path:
    """Install JMeter locally if missing; return JMETER_HOME."""
    root = project_root or Path.cwd()
    tools = discover_tools_dir(root) or root / ".tools"
    home = read_local_jmeter_home(tools)
    if home:
        ver = jmeter_version_from_home(home)
        if ver and version_at_least(ver, MIN_JMETER_VERSION):
            _refresh_runtime_helpers(tools, home)
            return home
    return install_jmeter(version=version, project_root=root, with_java=with_java)

