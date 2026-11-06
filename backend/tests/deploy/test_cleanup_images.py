"""scripts/cleanup_images.py: which images expire (spec 5.3)."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def _script() -> ModuleType:
    path = Path(__file__).resolve().parents[3] / "scripts" / "cleanup_images.py"
    spec = importlib.util.spec_from_file_location("cleanup_images", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def version(id: int, created: str, *tags: str) -> dict[str, Any]:
    return {"id": id, "created_at": created, "metadata": {"container": {"tags": list(tags)}}}


@pytest.mark.req("NFR-09")
def test_only_old_main_builds_expire() -> None:
    now = datetime(2026, 11, 2, tzinfo=UTC)
    old = "2026-09-01T10:00:00Z"
    versions = [
        version(1, old, "1.1.0_build.57"),  # expired
        version(2, "2026-10-20T10:00:00Z", "1.1.0_build.80"),  # younger than 30 days
        version(3, old, "1.1.0_build.60", "main"),  # still main
        version(4, old, "1.2.0-rc.1"),  # candidate
        version(5, old, "1.2.0-rc.2", "1.2.0", "1.2", "1"),  # release
        version(6, old),  # untagged
        version(7, old, "local"),
    ]
    assert [v["id"] for v in _script().expired(versions, now)] == [1]
