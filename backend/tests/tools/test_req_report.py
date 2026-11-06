from pathlib import Path

import pytest

from yap.tools import req_report


@pytest.mark.req("NFR-11")
def test_reads_requirement_ids_from_spec_tables(tmp_path: Path) -> None:
    spec = tmp_path / "spec.md"
    spec.write_text("| ID | Requirement |\n|---|---|\n| RB-01 | x | M |\n| NFR-14 | y | M |\n")
    assert req_report.spec_requirements(spec) == ["RB-01", "NFR-14"]


@pytest.mark.req("NFR-11")
def test_reads_not_yet_implemented_list(tmp_path: Path) -> None:
    strategy = tmp_path / "strategy.md"
    strategy.write_text("- **Not yet implemented** (excluded): USR-01, REV-02\n")
    assert req_report.not_implemented(strategy) == {"USR-01", "REV-02"}


@pytest.mark.req("NFR-11")
def test_report_flags_missing_failed_and_unknown() -> None:
    results = {
        "RB-01": [{"test": "t1", "outcome": "passed"}],
        "RB-02": [{"test": "t2", "outcome": "failed"}],
        "XX-99": [{"test": "t3", "outcome": "passed"}],
    }
    rows, problems = req_report.build_report(
        ["RB-01", "RB-02", "RB-03", "RB-04"], results, pending={"RB-04"}
    )
    assert [status for _, status, _ in rows] == [
        "covered",
        "failed",
        "missing",
        "not yet implemented",
    ]
    assert problems == [
        "RB-02: 1 failing test(s)",
        "RB-03: no test",
        "XX-99: referenced by tests but not in the spec",
    ]


@pytest.mark.req("NFR-11")
def test_merges_result_files_and_writes_report(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()
    (results / "pytest.json").write_text('{"RB-01": [{"test": "a", "outcome": "passed"}]}')
    (results / "vitest.json").write_text('{"RB-01": [{"test": "b", "outcome": "passed"}]}')
    assert len(req_report.load_results(results)["RB-01"]) == 2

    output = tmp_path / "report.md"
    exit_code = req_report.main(["--results", str(results), "--output", str(output)])
    report = output.read_text()
    assert "| RB-01 | covered | 2 |" in report
    # Every other requirement of the real spec is either pending or reported missing
    assert exit_code == (1 if "## Problems" in report else 0)


@pytest.mark.req("NFR-11")
def test_render_lists_problems() -> None:
    report = req_report.render([("RB-01", "missing", 0)], ["RB-01: no test"])
    assert "missing: 1" in report
    assert "- RB-01: no test" in report


@pytest.mark.req("NFR-11")
def test_strategy_without_pending_list(tmp_path: Path) -> None:
    strategy = tmp_path / "strategy.md"
    strategy.write_text("nothing here\n")
    assert req_report.not_implemented(strategy) == set()


@pytest.mark.req("NFR-11")
def test_spec_and_strategy_are_readable() -> None:
    assert "RB-07" in req_report.spec_requirements()
    assert isinstance(req_report.not_implemented(), set)
