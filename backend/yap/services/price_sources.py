"""Ticker lookup and price sources (PRC-02 to PRC-06): which listing prices an investor's
asset, or whether its prices are entered by hand. Lookups are cached for the whole server,
so a ticker another investor already looked up costs no provider call."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from yap.db.models import (
    Asset,
    Investor,
    Policy,
    PolicyVersion,
    Portfolio,
    PriceProvider,
    PriceSource,
    Snapshot,
    TickerLookup,
)
from yap.db.models import Listing as ListingRow
from yap.messages import Message, msg
from yap.prices import AdapterFactory, Listing, PriceAdapter, PriceError, Provider
from yap.prices.base import NAMES
from yap.services import price_providers
from yap.services.assets import find_asset, get_or_create_asset, normalize_ticker
from yap.services.common import Clock, ValidationError, require_investor
from yap.services.secrets import KeyBox

log = logging.getLogger(__name__)

# PRC-03: how long a cached answer counts
NOT_FOUND_TTL = timedelta(days=7)
UNUSED_TTL = timedelta(days=30)
# PRC-06: "try auto" asks again, but a cached "not found" at most once a day
RETRY_AFTER = timedelta(days=1)

AUTO, MANUAL, UNRESOLVED = "auto", "manual", "unresolved"
KINDS = (AUTO, MANUAL, UNRESOLVED)


@dataclass(frozen=True)
class ProviderProblem:
    provider: str
    message: Message


@dataclass(frozen=True)
class LookupResult:
    """`found`: listings to choose from; `not_found`: no provider has the ticker;
    `unresolved`: no listing, and at least one provider could not be asked (PRC-04)."""

    ticker: str
    status: str
    listings: list[ListingRow]
    problems: list[ProviderProblem] = field(default_factory=list)


def _lookup_providers(session: Session) -> list[PriceProvider]:
    return list(
        session.scalars(
            select(PriceProvider)
            .where(
                PriceProvider.archived_at.is_(None),
                PriceProvider.enabled,
                PriceProvider.built_in.is_(False),
            )
            .order_by(PriceProvider.id)
        )
    )


def _in_use(session: Session, cached: TickerLookup) -> bool:
    """A listing of the answer is an investor's price source."""
    ids = [listing.id for listing in cached.listings]
    return bool(ids) and bool(
        session.scalar(
            select(exists().where(PriceSource.listing_id.in_(ids), PriceSource.kind == "auto"))
        )
    )


def _fresh(session: Session, cached: TickerLookup, now: datetime, retry: bool) -> bool:
    """PRC-03, PRC-06: whether the cached answer is used instead of asking the provider."""
    age = now - cached.looked_up_at
    if cached.result == "not_found":
        return age < (RETRY_AFTER if retry else NOT_FOUND_TTL)
    if retry and any(not listing.available for listing in cached.listings):
        return age < RETRY_AFTER  # a retired listing may be back (PRC-09)
    return age < UNUSED_TTL or _in_use(session, cached)


def _store(
    session: Session,
    provider: PriceProvider,
    ticker: str,
    cached: TickerLookup | None,
    found: list[Listing],
    now: datetime,
) -> TickerLookup:
    rows = []
    for item in found:
        row = session.scalar(
            select(ListingRow).where(
                ListingRow.provider_id == provider.id, ListingRow.symbol == item.symbol
            )
        )
        if row is None:
            row = ListingRow(
                provider_id=provider.id,
                symbol=item.symbol,
                available=True,
                not_found_count=0,
            )
            session.add(row)
        row.exchange, row.quote_currency, row.name = item.exchange, item.currency, item.name
        if not row.available:  # found again (PRC-09)
            row.available, row.not_found_count = True, 0
        rows.append(row)
    if cached is None:
        cached = TickerLookup(provider_id=provider.id, ticker=ticker)
        session.add(cached)
    cached.result = "found" if rows else "not_found"
    cached.looked_up_at = now
    cached.listings = rows
    session.flush()
    return cached


def lookup(
    session: Session,
    actor: Investor,
    clock: Clock,
    keys: KeyBox,
    adapters: AdapterFactory,
    ticker: str,
    *,
    retry: bool = False,
) -> LookupResult:
    """PRC-02 to PRC-04, PRC-06: the listings of a ticker at all enabled providers, from the
    cache where possible. Checks only that the ticker is available; fetches no prices."""
    require_investor(actor)
    ticker = normalize_ticker(ticker)
    if not ticker:
        raise ValidationError.single(msg("ticker_required"), "ticker")
    providers = _lookup_providers(session)
    if not providers:
        problem = ProviderProblem("", msg("price_no_provider"))
        return LookupResult(ticker, UNRESOLVED, [], [problem])
    now = clock.now()
    listings: list[ListingRow] = []
    problems: list[ProviderProblem] = []
    for provider in providers:
        cached = session.scalar(
            select(TickerLookup).where(
                TickerLookup.provider_id == provider.id, TickerLookup.ticker == ticker
            )
        )
        if cached is None or not _fresh(session, cached, now, retry):
            try:
                config = price_providers.config_for(provider, keys)
                with price_providers.counted_client(session, provider, clock) as client:
                    adapter: PriceAdapter = adapters(config, client)  # type: ignore[assignment]
                    found = adapter.lookup(ticker)
                cached = _store(session, provider, ticker, cached, found, now)
            except PriceError as e:
                problems.append(ProviderProblem(NAMES[Provider(provider.provider)], e.message))
                if cached is None or cached.result == "not_found":
                    continue  # an older "found" answer is still better than none
        listings.extend(listing for listing in cached.listings if listing.available)
    if listings:
        return LookupResult(ticker, "found", listings, problems)
    return LookupResult(ticker, UNRESOLVED if problems else "not_found", [], problems)


# --- Price sources (PRC-05) ---------------------------------------------------------------


def get_source(session: Session, actor: Investor, asset: Asset) -> PriceSource | None:
    return session.get(PriceSource, (actor.id, asset.id))


def set_source(
    session: Session,
    actor: Investor,
    clock: Clock,
    ticker: str,
    kind: str,
    listing_id: int | None = None,
    *,
    name: str | None = None,
    asset_type: str | None = None,
) -> PriceSource:
    """PRC-02, PRC-05, PRC-06: the investor's choice for an asset; it never changes stored
    snapshots or policy versions. An asset new to the catalog needs name and type (IMP-08)."""
    require_investor(actor)
    if kind not in KINDS:
        raise ValidationError.single(msg("price_source_kind_unknown", kind=kind), "kind")
    listing = None
    if kind == AUTO:
        listing = session.get(ListingRow, listing_id) if listing_id is not None else None
        provider = listing.provider if listing else None
        if (
            listing is None
            or not listing.available
            or provider is None
            or provider.archived_at is not None
            or not provider.enabled
        ):
            raise ValidationError.single(
                msg("price_listing_unavailable", id=listing_id or 0), "listing_id"
            )
    asset = get_or_create_asset(session, ticker, name, asset_type, "ticker")
    source = get_source(session, actor, asset)
    if source is None:
        source = PriceSource(investor_id=actor.id, asset_id=asset.id)
        session.add(source)
    source.kind = kind
    source.listing_id = listing.id if listing else None
    source.updated_at = clock.now()
    session.flush()
    session.refresh(source)
    return source


@dataclass(frozen=True)
class AssetSource:
    asset: Asset
    source: PriceSource | None  # None: never looked up (e.g. assets from before prices)


def used_assets(session: Session, actor: Investor) -> list[Asset]:
    """PRC-05: the assets of the investor's policies (latest version, drafts included) and
    of the latest snapshot of each portfolio, then those that only have a price source."""
    assets: dict[int, Asset] = {}
    for policy in session.scalars(
        select(Policy).where(Policy.owner_id == actor.id, Policy.archived_at.is_(None))
    ):
        latest = session.scalar(
            select(PolicyVersion)
            .where(PolicyVersion.policy_id == policy.id)
            .order_by(PolicyVersion.version_no.desc())
            .limit(1)
        )
        for position in latest.positions if latest else []:
            assets.setdefault(position.asset_id, position.asset)
    for portfolio in session.scalars(
        select(Portfolio).where(Portfolio.owner_id == actor.id, Portfolio.archived_at.is_(None))
    ):
        snapshot = session.scalar(
            select(Snapshot)
            .where(Snapshot.portfolio_id == portfolio.id)
            .order_by(Snapshot.taken_at.desc(), Snapshot.id.desc())
            .limit(1)
        )
        for value in snapshot.values if snapshot else []:
            assets.setdefault(value.asset_id, value.asset)
    for source in session.scalars(select(PriceSource).where(PriceSource.investor_id == actor.id)):
        assets.setdefault(source.asset_id, source.asset)
    return sorted(assets.values(), key=lambda a: a.ticker)


def list_sources(session: Session, actor: Investor) -> list[AssetSource]:
    require_investor(actor)
    return [AssetSource(a, get_source(session, actor, a)) for a in used_assets(session, actor)]


def source_for_ticker(session: Session, actor: Investor, ticker: str) -> PriceSource | None:
    asset = find_asset(session, ticker)
    return get_source(session, actor, asset) if asset else None
