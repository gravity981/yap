"""Rebalancing reference cases (test strategy §5, NFR-04)."""

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from tests.reference.case_io import case_files, has_units, load_case, positions_from_case
from yap.domain.rebalancing import Mode, RebalanceResult, rebalance, to_units

# Expected amounts are rounded to cents; units are exact
TOLERANCE = Decimal("0.01")
AMOUNTS = ("buffer_buy", "sell_amount", "buy_amount", "withdrawal_sell")
UNITS = ("buffer_buy_units", "sell_units", "buy_units", "withdrawal_sell_units", "units_after")
TOTALS = (
    "total_sell_proceeds",
    "available_cash",
    "total_withdrawal_sells",
    "total_buffer_used",
    "unallocated_cash",
    "rounding_cash",
    "total_value_after",
)


def _run(case: dict[str, Any]) -> RebalanceResult:
    result = rebalance(
        positions_from_case(case),
        Decimal(str(case["input"]["contribution"])),
        Decimal(str(case["input"].get("withdrawal", 0))),
        Mode(case["input"].get("mode", "normal")),
    )
    return to_units(result) if has_units(case) else result


def _close(actual: Decimal, expected: Any) -> bool:
    return abs(actual - Decimal(str(expected))) <= TOLERANCE


@pytest.mark.req(
    "NFR-04",
    "RB-05",
    "RB-06",
    "RB-07",
    "RB-08",
    "RB-09",
    "RB-10",
    "RB-12",
    "RB-21",
    "RB-22",
    "RB-24",
    "RB-25",
)
@pytest.mark.parametrize("path", case_files(), ids=lambda p: p.stem)
def test_reference_case(path: Path) -> None:
    case = load_case(path)
    result = _run(case)
    by_ticker = {r.position.ticker: r for r in result.positions}
    for ticker, expected in case["expected"]["positions"].items():
        actual = by_ticker[ticker]
        for field in AMOUNTS:
            want = expected.get(field, 0)
            assert _close(getattr(actual, field), want), (
                f"{ticker}.{field}: {getattr(actual, field)} != {want}"
            )
        for field in UNITS:
            if field in expected:
                got = getattr(actual, field)
                want = expected[field]
                # Units exactly, with every decimal (crypto, NFR-04)
                assert (got is None and want is None) or (
                    got is not None and want is not None and got == Decimal(str(want))
                ), f"{ticker}.{field}: {got} != {want}"
        assert actual.phase1_action.value == expected["phase1_action"], ticker
        assert actual.phase3_action.value == expected["phase3_action"], ticker
    for field in TOTALS:
        if field in case["expected"]:
            assert _close(getattr(result, field), case["expected"][field]), field
