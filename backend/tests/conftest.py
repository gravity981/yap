"""Shared test setup.

Records which requirement IDs (`@pytest.mark.req`) were verified by which test
and with which outcome, for the requirement coverage report (test strategy §3).
"""

import json
import os
from pathlib import Path

import pytest

pytest_plugins = ["tests.fixtures"]

RESULTS_DIR = Path(os.environ.get("REQ_RESULTS_DIR", Path(__file__).parents[1] / ".req-results"))

_results: dict[str, list[dict[str, str]]] = {}


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]):  # type: ignore[no-untyped-def]
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" and not (report.when == "setup" and report.failed):
        return
    for marker in item.iter_markers("req"):
        for req_id in marker.args:
            _results.setdefault(req_id, []).append({"test": item.nodeid, "outcome": report.outcome})


def pytest_sessionfinish(session: pytest.Session) -> None:
    # Only a full run gives a complete picture; a partial run (paths, -k, -m) must not
    # overwrite the results of the last full run.
    config = session.config
    full_run = (
        config.args_source is pytest.Config.ArgsSource.TESTPATHS
        and not config.option.keyword
        and not config.option.markexpr
    )
    if not _results or not full_run:
        return
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "pytest.json").write_text(json.dumps(_results, indent=2, sort_keys=True))
