"""File formats for JSON import (IMP-01 to IMP-03).

The JSON Schemas in schemas are generated from these models (IMP-09).
"""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema

SCHEMA_MAJOR = 1
# 1.1: thesis status `needs_adaptation` (THS-04)
# 1.2: target structure without `reinvest_sells` (accepted and ignored, IMP-02)
# 1.3: current structure with units and price per position (IMP-03)
SCHEMA_VERSION = f"{SCHEMA_MAJOR}.3"
UNITS_SINCE_MINOR = 3
# Files of the same major version are accepted (IMP-04)
SchemaVersion = Annotated[
    str,
    Field(
        pattern=rf"^{SCHEMA_MAJOR}\.[0-9]+$",
        description=f"Schema version the file follows; any {SCHEMA_MAJOR}.x is accepted",
        examples=[SCHEMA_VERSION],
    ),
]


def number(description: str | None = None, *, minimum: int, maximum: int | None = None) -> object:
    """A decimal that is a plain JSON number in the file, with its bounds in the schema.

    Files are parsed without float rounding (NFR-04).
    """
    json_schema: dict[str, object] = {"type": "number", "minimum": minimum}
    if maximum is not None:
        json_schema["maximum"] = maximum
    if description:
        json_schema["description"] = description
    return Annotated[Decimal, Field(ge=minimum, le=maximum), WithJsonSchema(json_schema)]


Pct = number(minimum=0, maximum=100)
BuyThreshold = number("Relative to target, -100 to 0", minimum=-100, maximum=0)
SellThreshold = number("Relative to target, 0 or more", minimum=0)
Value = number("In the portfolio currency", minimum=0)
Units = number("Quantity held (shares, coins); for the cash buffer its amount", minimum=0)
Price = number("Price of one unit in the portfolio currency", minimum=0)
Ticker = Annotated[str, Field(min_length=1, max_length=32, pattern=r"\S")]
AssetTypeName = Literal["ETF", "stock", "crypto", "cash_buffer"]


class ImportFile(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_ref: str | None = Field(
        default=None,
        alias="$schema",
        description="Optional reference to the JSON Schema, e.g. for editor validation",
    )
    schema_version: SchemaVersion


class ThesisFile(ImportFile):
    """A thesis (IMP-01). Visibility only applies when a new thesis is created."""

    model_config = ConfigDict(title="Thesis import")

    title: Annotated[str, Field(min_length=1, max_length=200, pattern=r"\S")]
    visibility: Literal["private", "shared"] = "private"
    status: Literal["intact", "needs_adaptation", "broken"] = "intact"
    content_md: str = Field(description="Thesis content in markdown")
    change_note: str | None = Field(
        default=None,
        description="Why the thesis changed; needed at the latest when the draft is activated",
    )


class TargetPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: Ticker
    name: Annotated[str, Field(min_length=1, max_length=200)]
    type: AssetTypeName
    target_pct: Pct  # type: ignore[valid-type]
    buy_threshold_pct: BuyThreshold  # type: ignore[valid-type]
    sell_threshold_pct: SellThreshold  # type: ignore[valid-type]
    exit: bool = False
    rationale_md: str = ""


class TargetStructureFile(ImportFile):
    """Target structure of a policy (IMP-02); imported into the selected policy."""

    model_config = ConfigDict(title="Target structure import")

    reinvest_sells: bool | None = Field(
        default=None,
        deprecated=True,
        description="Ignored since 1.2: sell proceeds are always reinvested",
    )
    positions: Annotated[list[TargetPosition], Field(min_length=1)]


class CurrentPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: Ticker
    units: Units | None = Field(  # type: ignore[valid-type]
        default=None,
        description=(
            "Since 1.3; needed except for the cash buffer. Files before 1.3 have only values"
        ),
    )
    price: Price | None = Field(  # type: ignore[valid-type]
        default=None,
        description="Optional; without price and value, the price last entered is used",
    )
    value: Value | None = Field(  # type: ignore[valid-type]
        default=None,
        description="Optional with units (then price = value / units); the cash buffer's amount",
    )
    name: str | None = Field(default=None, description="Needed only for tickers not yet known")
    type: AssetTypeName | None = Field(
        default=None, description="Needed only for tickers not yet known"
    )


class CurrentStructureFile(ImportFile):
    """Current positions of a portfolio (IMP-03); imported into the selected portfolio."""

    model_config = ConfigDict(title="Current structure import")

    positions: list[CurrentPosition]
