"""Version information (spec section 5.7).

Images get `APP_VERSION` and `APP_COMMIT` baked in at build time. deploy.sh may add a
pre-release suffix with `APP_VERSION_SUFFIX` (`rc.N` when deploying a release candidate),
reported as `<version>-rc.N`. Running from source in dev, the version is derived from git:
`<last release>+dev`.
"""

import os
import subprocess
from dataclasses import dataclass
from functools import cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class VersionInfo:
    version: str
    commit: str


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=5
        )
    except OSError, subprocess.SubprocessError:
        return None
    return result.stdout.strip() or None


def _from_git() -> VersionInfo:
    last_release = _git(
        "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*", "--exclude", "*-*"
    )
    base = last_release.removeprefix("v") if last_release else "0.0.0"
    return VersionInfo(
        version=f"{base}+dev", commit=_git("rev-parse", "--short", "HEAD") or "unknown"
    )


@cache
def version_info() -> VersionInfo:
    version = os.environ.get("APP_VERSION")
    if version:
        if suffix := os.environ.get("APP_VERSION_SUFFIX"):
            version = f"{version}-{suffix}"
        return VersionInfo(version=version, commit=os.environ.get("APP_COMMIT", "unknown"))
    return _from_git()
