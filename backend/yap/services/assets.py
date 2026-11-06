"""Shared asset catalog (POL-02, IMP-08)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from yap.db.models import Asset
from yap.domain.types import AssetType
from yap.messages import msg
from yap.services.common import ValidationError


def normalize_ticker(ticker: str) -> str:
    """Tickers are case-insensitive: trimmed and stored in uppercase (POL-02)."""
    return ticker.strip().upper()


def find_asset(session: Session, ticker: str) -> Asset | None:
    return session.scalar(select(Asset).where(Asset.ticker == normalize_ticker(ticker)))


def get_or_create_asset(
    session: Session,
    ticker: str,
    name: str | None,
    asset_type: AssetType | str | None,
    path: str = "",
) -> Asset:
    """Returns the catalog entry for `ticker`, adding it if name and type are given."""
    normalized = normalize_ticker(ticker)
    if not normalized:
        raise ValidationError.single(msg("ticker_required"), f"{path}.ticker")
    asset = find_asset(session, normalized)
    if asset is not None:
        return asset
    if not name or not name.strip() or asset_type is None:
        raise ValidationError.single(msg("ticker_unknown_add", ticker=normalized), f"{path}.ticker")
    try:
        type_value = AssetType(asset_type).value
    except ValueError:
        raise ValidationError.single(
            msg("asset_type_unknown", type=str(asset_type)), f"{path}.type"
        ) from None
    asset = Asset(ticker=normalized, name=name.strip(), type=type_value)
    session.add(asset)
    session.flush()
    return asset
