"""Reading rebalancing reference cases (test strategy §5).

A case file contains:
  description  – what the case shows, with the requirements it covers
  approved     – reviewed and approved by the product owner
  calculation  – how the expected values were obtained
  input        – contribution, withdrawal (optional, default 0), mode (optional, `normal` or
                 `sell_all`, RB-25), positions; a position may
                 have units, price and whole_units, then the amounts are converted into
                 units (RB-24)
  expected     – per ticker: buffer_buy, sell_amount, buy_amount, withdrawal_sell (optional),
                 phase1_action, phase3_action, and with units buffer_buy_units, sell_units,
                 buy_units, withdrawal_sell_units, units_after (optional, exact);
                 and totals; amounts rounded to cents
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from yap.domain.bands import Band
from yap.domain.rebalancing import PositionInput
from yap.domain.types import AssetType

CASES_DIR = Path(__file__).parent / "cases"


def load_case(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(), parse_float=Decimal)  # type: ignore[no-any-return]


def case_files() -> list[Path]:
    return sorted(CASES_DIR.glob("*.json"))


def _optional(p: dict[str, Any], key: str) -> Decimal | None:
    return None if p.get(key) is None else Decimal(str(p[key]))


def has_units(case: dict[str, Any]) -> bool:
    """RB-24: the case converts amounts into units."""
    return any("units" in p for p in case["input"]["positions"])


def positions_from_case(case: dict[str, Any]) -> list[PositionInput]:
    positions = []
    for p in case["input"]["positions"]:
        band = None
        if p.get("in_policy", True):
            band = Band(
                target_pct=Decimal(str(p["target_pct"])),
                buy_threshold_pct=Decimal(str(p["buy_threshold_pct"])),
                sell_threshold_pct=Decimal(str(p["sell_threshold_pct"])),
            )
        positions.append(
            PositionInput(
                ticker=p["ticker"],
                name=p["name"],
                asset_type=AssetType(p["type"]),
                value=Decimal(str(p["value"])),
                band=band,
                exit=p.get("exit", False),
                broker=p.get("broker"),
                units=_optional(p, "units"),
                price=_optional(p, "price"),
                whole_units=p.get("whole_units"),
            )
        )
    return positions
