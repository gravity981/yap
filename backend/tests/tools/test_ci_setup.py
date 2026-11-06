"""The CI setup enforces unit tests and their coverage (NFR-12) and runs all tests on
every change (NFR-13). That a failing run blocks a merge is GitHub's branch protection,
checked by hand (test strategy §9)."""

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]


def _ci() -> dict[str, Any]:
    return yaml.safe_load((REPO / ".github/workflows/ci.yml").read_text())  # type: ignore[no-any-return]


def _commands(job: str) -> str:
    return "\n".join(step.get("run", "") for step in _ci()["jobs"][job]["steps"])


@pytest.mark.req("NFR-13")
def test_ci_runs_on_every_pull_request_and_push_to_main() -> None:
    triggers = _ci()[True]  # YAML reads the key `on` as True
    assert "pull_request" in triggers
    assert triggers["push"]["branches"] == ["main"]


@pytest.mark.req("NFR-13")
def test_all_tests_run_with_one_command_per_side() -> None:
    assert re.search(r"^\s*pytest\b", _commands("backend"), re.MULTILINE)
    scripts = json.loads((REPO / "frontend/package.json").read_text())["scripts"]
    assert scripts["test"].startswith("vitest run")
    assert "npm run coverage" in _commands("frontend")
    assert "npm run e2e" in _commands("e2e")


@pytest.mark.req("NFR-12")
def test_coverage_is_enforced() -> None:
    backend = _commands("backend")
    assert "--cov-fail-under=90" in backend
    critical = re.search(r"coverage report --fail-under=100\s+--include='([^']+)'", backend)
    assert critical is not None
    for module in ("domain/rebalancing.py", "services/versioning.py", "imports/importer.py"):
        assert module in critical.group(1)
    vite = (REPO / "frontend/vite.config.ts").read_text()
    assert re.search(r"thresholds:\s*\{\s*lines:\s*80\s*\}", vite)
