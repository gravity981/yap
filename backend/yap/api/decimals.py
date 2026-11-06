"""Decimals in API responses: as strings in plain notation, with every digit (NFR-04).

Python writes small or large decimals in exponent notation (`1E-8` for one satoshi);
the UI shows and edits them as typed, so the API writes `0.00000001` instead.
"""

from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer


def plain(value: Decimal) -> str:
    """`1E-8` -> `0.00000001`, `650.00` stays `650.00`."""
    return format(value, "f")


PlainDecimal = Annotated[Decimal, PlainSerializer(plain, return_type=str, when_used="json")]
