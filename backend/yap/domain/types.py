"""Value types shared by the whole backend."""

from decimal import Decimal
from enum import StrEnum


class AssetType(StrEnum):
    """Fixed list of asset types (POL-02)."""

    ETF = "ETF"
    STOCK = "stock"
    CRYPTO = "crypto"
    CASH_BUFFER = "cash_buffer"


class ThesisStatus(StrEnum):
    INTACT = "intact"
    NEEDS_ADAPTATION = "needs_adaptation"
    BROKEN = "broken"


class Visibility(StrEnum):
    PRIVATE = "private"
    SHARED = "shared"


HUNDRED = Decimal(100)

# Tolerance for "target allocations sum to 100 %" (POL-05, RB-04, IMP-05)
TARGET_SUM_TOLERANCE = Decimal("0.01")

# Threshold ranges, relative to target (POL-04)
BUY_THRESHOLD_MIN = Decimal(-100)
BUY_THRESHOLD_MAX = Decimal(0)
SELL_THRESHOLD_MIN = Decimal(0)
