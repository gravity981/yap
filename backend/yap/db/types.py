"""Column types for exact decimals (NFR-04) and UTC timestamps (NFR-14) on SQLite."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import String
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class DecimalText(TypeDecorator[Decimal]):
    """Stores a Decimal as text, so no precision is lost (SQLite has no decimal type)."""

    impl = String(64)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if not isinstance(value, Decimal):
            raise TypeError(f"Expected Decimal, got {type(value).__name__}")
        return str(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        return None if value is None else Decimal(value)


class UTCDateTime(TypeDecorator[datetime]):
    """Stores an aware datetime as ISO 8601 text in UTC.

    The fixed format (always microseconds, always +00:00) keeps text comparison
    in SQL equal to chronological comparison.
    """

    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise TypeError("Expected a timezone-aware datetime")
        return value.astimezone(UTC).isoformat(timespec="microseconds")

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        return None if value is None else datetime.fromisoformat(value)
