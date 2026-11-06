from decimal import Decimal as D

import pytest

from yap.domain.bands import Band, BandStatus, allocation_pct


@pytest.mark.req("POL-04")
def test_thresholds_are_relative_to_target() -> None:
    band = Band(target_pct=D(40), buy_threshold_pct=D(-20), sell_threshold_pct=D(25))
    assert band.buy_abs == D(32)
    assert band.sell_abs == D(50)


@pytest.mark.req("POL-04")
def test_midband_is_halfway_between_target_and_sell_threshold() -> None:
    band = Band(target_pct=D(50), buy_threshold_pct=D(-20), sell_threshold_pct=D(20))
    assert band.midband == D(55)


@pytest.mark.req("CMP-05")
@pytest.mark.parametrize(
    ("allocation", "expected"),
    [
        (D("31.99"), BandStatus.BELOW_BUY_THRESHOLD),
        (D(32), BandStatus.BELOW_TARGET),
        (D("39.99"), BandStatus.BELOW_TARGET),
        (D(40), BandStatus.WITHIN_BAND),
        (D(50), BandStatus.WITHIN_BAND),
        (D("50.01"), BandStatus.ABOVE_SELL_THRESHOLD),
    ],
)
def test_band_status(allocation: D, expected: BandStatus) -> None:
    band = Band(target_pct=D(40), buy_threshold_pct=D(-20), sell_threshold_pct=D(25))
    assert band.status(allocation) is expected


@pytest.mark.req("CMP-05", "RB-05")
def test_allocation_of_empty_portfolio_is_zero() -> None:
    assert allocation_pct(D(0), D(0)) == 0
    assert allocation_pct(D(25), D(100)) == 25
