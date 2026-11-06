"""Ticker lookup and price sources of the investor (PRC-02 to PRC-06)."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from yap.api.decimals import PlainDecimal
from yap.api.deps import (
    AppClock,
    AppKeys,
    CurrentUser,
    DbSession,
    PriceAdapters,
)
from yap.db.models import Asset, PriceSource
from yap.db.models import Listing as ListingRow
from yap.messages import Message
from yap.prices import Provider
from yap.prices.base import NAMES
from yap.services import price_sources

router = APIRouter(prefix="/price-sources", tags=["prices"])


class MessageOut(BaseModel):
    """English text and code with params (NFR-10)."""

    message: str
    code: str
    params: dict[str, str | int | float]

    @classmethod
    def of(cls, message: Message) -> MessageOut:
        return cls(message=str(message), code=message.code, params=message.params)


class ListingOut(BaseModel):
    id: int
    provider: str
    provider_name: str
    symbol: str
    exchange: str
    currency: str
    name: str
    available: bool
    price: PlainDecimal | None  # latest only, in the listing's currency; null until updated
    price_date: str | None  # as reported by the provider
    price_updated_at: datetime | None  # PRC-05: date and time of the last update

    @classmethod
    def of(cls, row: ListingRow) -> ListingOut:
        provider = Provider(row.provider.provider)
        return cls(
            id=row.id,
            provider=provider.value,
            provider_name=NAMES[provider],
            symbol=row.symbol,
            exchange=row.exchange,
            currency=row.quote_currency,
            name=row.name,
            available=row.available,
            price=row.price,
            price_date=row.price_date,
            price_updated_at=row.price_updated_at,
        )


class PriceSourceOut(BaseModel):
    """`kind` null: never looked up (assets from before price sources)."""

    ticker: str
    name: str
    type: str
    kind: str | None  # auto | manual | unresolved
    listing: ListingOut | None
    updated_at: datetime | None

    @classmethod
    def of(cls, asset: Asset, source: PriceSource | None) -> PriceSourceOut:
        return cls(
            ticker=asset.ticker,
            name=asset.name,
            type=asset.type,
            kind=source.kind if source else None,
            listing=ListingOut.of(source.listing) if source and source.listing else None,
            updated_at=source.updated_at if source else None,
        )


class LookupIn(BaseModel):
    ticker: str
    retry: bool = False  # PRC-06: "try auto" asks again after a cached "not found"


class ProblemOut(MessageOut):
    provider: str


class LookupOut(BaseModel):
    ticker: str
    status: str  # found | not_found | unresolved
    listings: list[ListingOut]
    problems: list[ProblemOut]  # providers that could not be asked (PRC-04)
    source: PriceSourceOut | None  # the investor's current choice, if the asset exists


class PriceSourceIn(BaseModel):
    kind: str  # auto | manual | unresolved
    listing_id: int | None = None  # for auto
    name: str | None = None  # only for tickers new to the catalog (IMP-08)
    type: str | None = None


@router.get("")
def list_sources(session: DbSession, user: CurrentUser) -> list[PriceSourceOut]:
    """PRC-05: every asset the investor uses, with its price source."""
    return [PriceSourceOut.of(s.asset, s.source) for s in price_sources.list_sources(session, user)]


@router.post("/lookup")
def lookup(
    body: LookupIn,
    session: DbSession,
    clock: AppClock,
    keys: AppKeys,
    adapters: PriceAdapters,
    user: CurrentUser,
) -> LookupOut:
    """PRC-02 to PRC-04, PRC-06: never blocks; problems are reported, not raised."""
    result = price_sources.lookup(
        session, user, clock, keys, adapters, body.ticker, retry=body.retry
    )
    source = price_sources.source_for_ticker(session, user, result.ticker)
    return LookupOut(
        ticker=result.ticker,
        status=result.status,
        listings=[ListingOut.of(row) for row in result.listings],
        problems=[
            ProblemOut(provider=p.provider, **MessageOut.of(p.message).model_dump())
            for p in result.problems
        ],
        source=PriceSourceOut.of(source.asset, source) if source else None,
    )


@router.put("/{ticker}")
def set_source(
    ticker: str, body: PriceSourceIn, session: DbSession, clock: AppClock, user: CurrentUser
) -> PriceSourceOut:
    source = price_sources.set_source(
        session,
        user,
        clock,
        ticker,
        body.kind,
        body.listing_id,
        name=body.name,
        asset_type=body.type,
    )
    return PriceSourceOut.of(source.asset, source)
