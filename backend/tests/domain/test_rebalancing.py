"""Unit tests for the individual rebalancing rules (RB-04 to RB-12, RB-22)."""

from decimal import Decimal as D

import pytest

from yap.domain.bands import Band
from yap.domain.rebalancing import (
    MultipleCashBuffersError,
    NegativeContributionError,
    NegativeWithdrawalError,
    Phase1Action,
    Phase3Action,
    PositionInput,
    TargetSumError,
    WithdrawalTooLargeError,
    rebalance,
    to_units,
)
from yap.domain.types import AssetType


def pos(
    ticker: str,
    value: int | str,
    target: int | str | None = None,
    buy: int = -20,
    sell: int = 20,
    *,
    asset_type: AssetType = AssetType.ETF,
    exit: bool = False,
    broker: str | None = "B1",
) -> PositionInput:
    band = None if target is None else Band(D(target), D(buy), D(sell))
    return PositionInput(ticker, ticker, asset_type, D(value), band, exit, broker)


def by_ticker(result, ticker):  # type: ignore[no-untyped-def]
    return next(r for r in result.positions if r.position.ticker == ticker)


@pytest.mark.req("RB-04")
def test_rejects_targets_not_summing_to_100() -> None:
    with pytest.raises(TargetSumError) as err:
        rebalance([pos("A", 100, 60), pos("B", 100, 30)], D(0))
    assert err.value.difference == D(-10)


@pytest.mark.req("RB-04")
def test_accepts_target_sum_within_tolerance() -> None:
    rebalance([pos("A", 100, "60.005"), pos("B", 100, 40)], D(0))


@pytest.mark.req("POL-05")
def test_rejects_more_than_one_cash_buffer() -> None:
    cash = AssetType.CASH_BUFFER
    with pytest.raises(MultipleCashBuffersError):
        rebalance(
            [pos("C1", 1, 5, asset_type=cash), pos("C2", 1, 5, asset_type=cash), pos("A", 1, 90)],
            D(0),
        )


@pytest.mark.req("RB-01")
def test_rejects_negative_withdrawal() -> None:
    with pytest.raises(NegativeWithdrawalError):
        rebalance([pos("A", 100, 100)], D(0), D(-1))


@pytest.mark.req("RB-01")
def test_rejects_withdrawal_above_value_plus_contribution() -> None:
    with pytest.raises(WithdrawalTooLargeError):
        rebalance([pos("A", 100, 100)], D(10), D("110.01"))


@pytest.mark.req("RB-01")
def test_rejects_negative_contribution() -> None:
    with pytest.raises(NegativeContributionError):
        rebalance([pos("A", 100, 100)], D(-1))


@pytest.mark.req("RB-05")
def test_current_allocation_includes_cash_buffer() -> None:
    result = rebalance(
        [pos("CASH", 20, 20, -100, 100, asset_type=AssetType.CASH_BUFFER), pos("A", 80, 80)],
        D(0),
    )
    assert by_ticker(result, "CASH").allocation_before_pct == 20
    assert by_ticker(result, "A").allocation_before_pct == 80


@pytest.mark.req("RB-07")
def test_buffer_with_exit_flag_is_not_deployed_but_sold() -> None:
    result = rebalance(
        [
            pos("CASH", 1000, 10, -100, 100, asset_type=AssetType.CASH_BUFFER, exit=True),
            pos("A", 100, 90, -50),
            pos("B", 8900, 0, -100, 1000),
        ],
        D(0),
    )
    assert result.total_buffer_used == 0
    assert by_ticker(result, "CASH").phase1_action is Phase1Action.SELL_ALL_EXIT


@pytest.mark.req("RB-07")
def test_dip_buy_measured_against_total_including_buffer() -> None:
    # Total 100000 incl. 10000 buffer; GOLD 3 % with buy threshold 6 % -> buys 3000
    result = rebalance(
        [
            pos("CASH", 10000, 10, -100, 100, asset_type=AssetType.CASH_BUFFER),
            pos("GOLD", 3000, 10, -40),
            pos("REST", 87000, 80, -10, 30),
        ],
        D(0),
    )
    gold = by_ticker(result, "GOLD")
    assert gold.buffer_buy == 3000
    assert gold.allocation_after_phase1_pct == 6


@pytest.mark.req("RB-07")
def test_tiny_buffer_buys_are_ignored() -> None:
    result = rebalance(
        [
            pos("CASH", "0.005", 1, -100, 100000, asset_type=AssetType.CASH_BUFFER),
            pos("A", 1, 50, -50),
            pos("B", 1000, 49, -100, 100000),
        ],
        D(0),
    )
    assert by_ticker(result, "A").buffer_buy == 0
    assert result.total_buffer_used == 0


@pytest.mark.req("RB-08", "POL-11")
def test_exit_flag_sells_completely_and_blocks_buys() -> None:
    result = rebalance([pos("A", 500, 50, exit=True), pos("B", 500, 50)], D(1000))
    a = by_ticker(result, "A")
    assert a.sell_amount == 500
    assert a.buy_amount == 0
    assert a.phase1_action is Phase1Action.SELL_ALL_EXIT
    assert a.phase3_action is Phase3Action.EXIT


@pytest.mark.req("RB-08")
def test_no_sell_when_contribution_lifts_midband_above_position_value() -> None:
    # A is above its sell threshold (70 % > 60 %), but 55 % of the final value
    # (70 + 30 + 1000) is more than A's value, so nothing needs to be sold.
    result = rebalance([pos("A", 70, 50), pos("B", 30, 50)], D(1000))
    assert by_ticker(result, "A").sell_amount == 0


@pytest.mark.req("RB-08")
def test_position_at_sell_threshold_is_not_sold() -> None:
    result = rebalance([pos("A", 60, 50, sell=20), pos("B", 40, 50)], D(0))
    assert by_ticker(result, "A").sell_amount == 0


@pytest.mark.req("RB-08")
def test_sold_position_ends_on_midband_with_withdrawal() -> None:
    result = rebalance([pos("A", 70000, 50), pos("B", 30000, 50)], D(5000), D(20000))
    a = by_ticker(result, "A")
    assert abs(a.allocation_after_phase3_pct - D(55)) < D("0.000001")


@pytest.mark.req("RB-09")
def test_withdrawal_is_paid_from_sell_proceeds() -> None:
    result = rebalance([pos("A", 600, 50, exit=True), pos("B", 400, 50)], D(100), D(600))
    assert result.available_cash == 100
    assert result.total_withdrawal_sells == 0
    assert result.total_value_after == 500


@pytest.mark.req("RB-10")
def test_position_sold_in_phase1_gets_no_buys() -> None:
    result = rebalance([pos("A", 70, 50), pos("B", 30, 50)], D(10))
    assert by_ticker(result, "A").sell_amount > 0
    assert by_ticker(result, "A").buy_amount == 0
    assert by_ticker(result, "A").phase3_action is Phase3Action.HOLD


@pytest.mark.req("RB-10")
def test_cash_without_eligible_position_stays_unallocated() -> None:
    result = rebalance([pos("A", 100, 100, exit=True)], D(50))
    assert result.unallocated_cash == 150


@pytest.mark.req("RB-10")
def test_buys_go_to_larger_deficits_first() -> None:
    result = rebalance([pos("A", 300, 40), pos("B", 350, 40), pos("C", 350, 20)], D(100))
    assert by_ticker(result, "A").buy_amount > by_ticker(result, "B").buy_amount
    assert by_ticker(result, "C").buy_amount == 0


@pytest.mark.req("RB-10")
def test_no_progress_falls_back_to_distribution_by_target() -> None:
    # A is only 0.0002 below its target value; the rest of the cash cannot go
    # anywhere by deficit and is distributed by target (A is the only eligible).
    result = rebalance([pos("A", "0.4998", 50), pos("B", "0.5", 50, exit=True)], D("0.0002"))
    assert by_ticker(result, "A").buy_amount == D("0.5002")
    assert result.unallocated_cash == 0


@pytest.mark.req("RB-10")
def test_cash_is_not_lost_when_buy_rounds_run_out(monkeypatch: pytest.MonkeyPatch) -> None:
    import yap.domain.rebalancing as rb

    monkeypatch.setattr(rb, "MAX_BUY_ROUNDS", 1)
    result = rebalance([pos("A", 0, 70), pos("B", 300, 30)], D(700))
    assert by_ticker(result, "A").buy_amount + by_ticker(result, "B").buy_amount == 700


@pytest.mark.req("RB-13")
def test_buys_are_grouped_by_broker() -> None:
    result = rebalance(
        [
            pos("A", 0, 50, broker="Southbank"),
            pos("B", 0, 25, broker="Northbank"),
            pos("C", 0, 25, broker="Southbank"),
        ],
        D(1000),
    )
    assert result.buys_by_broker == {"Southbank": D(750), "Northbank": D(250)}


@pytest.mark.req("RB-11", "RB-14")
def test_difference_to_target_after_all_actions() -> None:
    result = rebalance([pos("A", 70, 50), pos("B", 30, 50), pos("L", 0)], D(0))
    assert by_ticker(result, "L").difference_to_target_pct is None
    diff = by_ticker(result, "A").difference_to_target_pct
    assert diff is not None and abs(diff - 5) < D("0.000001")


@pytest.mark.req("RB-12")
def test_buffer_row_shows_sell_and_deploy() -> None:
    # Buffer deploys into A's dip and is itself above its sell threshold afterwards
    result = rebalance(
        [
            pos("CASH", 3000, 1, -100, 0, asset_type=AssetType.CASH_BUFFER),
            pos("A", 1000, 40, -50),
            pos("B", 96000, 59, -100, 100),
        ],
        D(0),
    )
    cash = by_ticker(result, "CASH")
    assert cash.buffer_deployed == 3000
    assert cash.phase1_action is Phase1Action.DEPLOY


@pytest.mark.req("RB-22")
def test_no_buys_when_withdrawal_exceeds_cash() -> None:
    result = rebalance([pos("A", 600, 50, sell=100), pos("B", 400, 50, sell=100)], D(0), D(100))
    a, b = by_ticker(result, "A"), by_ticker(result, "B")
    assert a.withdrawal_sell == 100 and a.phase3_action is Phase3Action.SELL_WITHDRAWAL
    assert b.withdrawal_sell == 0 and b.phase3_action is Phase3Action.HOLD
    assert a.buy_amount == b.buy_amount == 0
    assert result.total_withdrawal_sells == 100


@pytest.mark.req("RB-22")
def test_withdrawal_sells_skip_exit_and_sold_positions() -> None:
    result = rebalance(
        [pos("A", 700, 40), pos("B", 200, 30), pos("C", 100, 30, exit=True)], D(0), D(800)
    )
    # A is sold to its midband in 1B and C completely; only B is left for the shortfall
    assert by_ticker(result, "A").withdrawal_sell == 0
    assert by_ticker(result, "C").withdrawal_sell == 0
    assert by_ticker(result, "B").withdrawal_sell == result.total_withdrawal_sells > 0
    assert result.total_value_after == 200


@pytest.mark.req("RB-22")
def test_withdrawal_rest_by_target_is_capped_at_value(monkeypatch: pytest.MonkeyPatch) -> None:
    import yap.domain.rebalancing as rb

    # Without surplus rounds the whole amount is sold by target: 250 each, but B only has 100
    monkeypatch.setattr(rb, "MAX_BUY_ROUNDS", 0)
    result = rebalance([pos("A", 900, 50, sell=100), pos("B", 100, 50, sell=100)], D(0), D(500))
    assert by_ticker(result, "B").withdrawal_sell == 100
    assert by_ticker(result, "A").withdrawal_sell == 400


@pytest.mark.req("RB-22")
def test_withdrawal_sells_stop_when_a_round_moves_less_than_a_cent() -> None:
    # Tiny amounts: a surplus round ends below one cent; the rest goes by target
    result = rebalance(
        [pos("A", 17, "33.3", -8, 100), pos("B", 4, 60, -13, 12), pos("C", "0.06", "6.7", -48, 10)],
        D(0),
        D("20.21"),
    )
    a = by_ticker(result, "A")
    assert a.sell_amount + result.total_withdrawal_sells == D("20.21")
    assert result.total_value_after == D("0.85")
    assert all(r.withdrawal_sell >= 0 for r in result.positions)


@pytest.mark.req("RB-01", "RB-22")
def test_withdrawing_the_whole_portfolio_sells_everything() -> None:
    result = rebalance([pos("A", 600, 50), pos("B", 400, 50)], D(0), D(1000))
    assert by_ticker(result, "A").withdrawal_sell == 600
    assert by_ticker(result, "B").withdrawal_sell == 400
    assert result.total_value_after == 0


@pytest.mark.req("NFR-07")
def test_rebalancing_50_positions_takes_less_than_a_second() -> None:
    import time

    positions = [
        pos("CASH", 5000, 2, -100, 100, asset_type=AssetType.CASH_BUFFER),
        *[pos(f"P{i:02}", 1000 + 97 * i, 2, -30, 40) for i in range(49)],
    ]
    start = time.perf_counter()
    rebalance(positions, D(5000))
    assert time.perf_counter() - start < 1


@pytest.mark.req("NFR-04")
def test_amounts_are_decimals() -> None:
    result = rebalance([pos("A", "0.1", 50), pos("B", "0.2", 50)], D("0.3"))
    for r in result.positions:
        assert isinstance(r.buy_amount, D)
        assert isinstance(r.allocation_after_phase3_pct, D)


@pytest.mark.req("RB-24")
def test_without_units_the_result_stays_as_calculated() -> None:
    result = rebalance([pos("A", 600, 50), pos("B", 400, 50)], D(100))
    before = [(r.buy_amount, r.value_after_phase3) for r in result.positions]
    assert to_units(result) is result
    assert [(r.buy_amount, r.value_after_phase3) for r in result.positions] == before
    assert all(r.buy_units is None for r in result.positions) and result.rounding_cash == 0


@pytest.mark.req("RB-24", "NFR-04")
def test_fractional_units_keep_18_decimals_and_every_decimal_held() -> None:
    # A token held with 28 significant digits; sold for a withdrawal, in fractions
    held = D("1000000000.123456789012345678")
    token = PositionInput(
        "TOK",
        "Token",
        AssetType.CRYPTO,
        D("100.00"),
        Band(D(50), D(-20), D(20)),
        False,
        None,
        units=held,
        price=D("0.0000001"),
        whole_units=False,
    )
    other = pos("A", 100, 50)
    result = to_units(rebalance([token, other], D(0), D(30)))
    sold = by_ticker(result, "TOK")
    assert sold.withdrawal_sell_units is not None and sold.units_after is not None
    assert sold.withdrawal_sell_units == sold.withdrawal_sell_units.quantize(D("1E-18"))
    assert sold.units_after + sold.withdrawal_sell_units == held  # no digit lost
