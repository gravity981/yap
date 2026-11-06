"""Requirement coverage report (test strategy §3, NFR-11).

Reads all requirement IDs from spec/sw-architecture.md, the test results written
by the test runners into `.req-results/*.json` ({id: [{test, outcome}]}), and the
"not yet implemented" list from spec/test-strategy.md §8. Prints a markdown table
and exits with 1 if an implemented requirement has no passing test or a failing one.

    python -m yap.tools.req_report [--results DIR] [--output FILE]
"""

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC = REPO_ROOT / "spec" / "sw-architecture.md"
STRATEGY = REPO_ROOT / "spec" / "test-strategy.md"
DEFAULT_RESULTS = REPO_ROOT / "backend" / ".req-results"

REQ_ROW = re.compile(r"^\| ([A-Z]{2,4}-\d{2}) \|", re.MULTILINE)
NOT_IMPLEMENTED_LINE = re.compile(r"^- \*\*Not yet implemented\*\*.*?:(.*)$", re.MULTILINE)
REQ_ID = re.compile(r"[A-Z]{2,4}-\d{2}")


def spec_requirements(spec: Path = SPEC) -> list[str]:
    return REQ_ROW.findall(spec.read_text())


def not_implemented(strategy: Path = STRATEGY) -> set[str]:
    match = NOT_IMPLEMENTED_LINE.search(strategy.read_text())
    return set(REQ_ID.findall(match.group(1))) if match else set()


def load_results(results_dir: Path) -> dict[str, list[dict[str, str]]]:
    merged: dict[str, list[dict[str, str]]] = {}
    for path in sorted(results_dir.glob("*.json")):
        for req_id, tests in json.loads(path.read_text()).items():
            merged.setdefault(req_id, []).extend(tests)
    return merged


def build_report(
    requirements: list[str],
    results: dict[str, list[dict[str, str]]],
    pending: set[str],
) -> tuple[list[tuple[str, str, int]], list[str]]:
    """Returns rows (id, status, number of tests) and the list of problems."""
    rows: list[tuple[str, str, int]] = []
    problems: list[str] = []
    for req_id in requirements:
        tests = results.get(req_id, [])
        failed = [t for t in tests if t["outcome"] != "passed"]
        if failed:
            status = "failed"
            problems.append(f"{req_id}: {len(failed)} failing test(s)")
        elif tests:
            status = "covered"
        elif req_id in pending:
            status = "not yet implemented"
        else:
            status = "missing"
            problems.append(f"{req_id}: no test")
        rows.append((req_id, status, len(tests)))
    unknown = sorted(set(results) - set(requirements))
    problems.extend(f"{req_id}: referenced by tests but not in the spec" for req_id in unknown)
    return rows, problems


def render(rows: list[tuple[str, str, int]], problems: list[str]) -> str:
    counts: dict[str, int] = {}
    for _, status, _ in rows:
        counts[status] = counts.get(status, 0) + 1
    lines = ["# Requirement coverage", ""]
    lines.append(", ".join(f"{status}: {n}" for status, n in sorted(counts.items())))
    lines += ["", "| Requirement | Status | Tests |", "|---|---|---|"]
    lines += [f"| {req_id} | {status} | {n} |" for req_id, status, n in rows]
    if problems:
        lines += ["", "## Problems", ""] + [f"- {p}" for p in problems]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    rows, problems = build_report(
        spec_requirements(), load_results(args.results), not_implemented()
    )
    report = render(rows, problems)
    if args.output:
        args.output.write_text(report)
    print(report)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
