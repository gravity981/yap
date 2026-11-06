"""Bands around a target allocation and the band status of a position (POL-04, CMP-05)."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from yap.domain.types import HUNDRED


class BandStatus(StrEnum):
    BELOW_BUY_THRESHOLD = "below_buy_threshold"
    BELOW_TARGET = "below_target"
    WITHIN_BAND = "within_band"
    ABOVE_SELL_THRESHOLD = "above_sell_threshold"
    NOT_IN_POLICY = "not_in_policy"


@dataclass(frozen=True)
class Band:
    """Target allocation with thresholds relative to it, all in percent."""

    target_pct: Decimal
    buy_threshold_pct: Decimal
    sell_threshold_pct: Decimal

    @property
    def buy_abs(self) -> Decimal:
        """Absolute buy threshold: target × (1 + buy threshold / 100)."""
        return self.target_pct * (1 + self.buy_threshold_pct / HUNDRED)

    @property
    def sell_abs(self) -> Decimal:
        """Absolute sell threshold: target × (1 + sell threshold / 100)."""
        return self.target_pct * (1 + self.sell_threshold_pct / HUNDRED)

    @property
    def midband(self) -> Decimal:
        """Midpoint between target and absolute sell threshold."""
        return (self.target_pct + self.sell_abs) / 2

    def status(self, allocation_pct: Decimal) -> BandStatus:
        if allocation_pct < self.buy_abs:
            return BandStatus.BELOW_BUY_THRESHOLD
        if allocation_pct < self.target_pct:
            return BandStatus.BELOW_TARGET
        if allocation_pct > self.sell_abs:
            return BandStatus.ABOVE_SELL_THRESHOLD
        return BandStatus.WITHIN_BAND


def allocation_pct(value: Decimal, total: Decimal) -> Decimal:
    """Share of `value` in `total` in percent; 0 for an empty portfolio."""
    if total == 0:
        return Decimal(0)
    return value / total * HUNDRED
