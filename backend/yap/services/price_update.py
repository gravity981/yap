"""The price update and exchange rates (PRC-07 to PRC-12): a scheduled job that fetches the
latest price of every listing in use and the exchange rates needed for them, and the auto
prices snapshots are taken with."""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, available_timezones

from sqlalchemy import select
from sqlalchemy.orm import Session

from yap.db.models import (
    Asset,
    FxRate,
    Investor,
    Portfolio,
    PriceProvider,
    PriceSource,
    PriceUpdateRun,
    PriceUpdateSettings,
)
from yap.db.models import Listing as ListingRow
from yap.messages import msg
from yap.prices import (
    AdapterFactory,
    ErrorKind,
    PriceAdapter,
    PriceError,
    Provider,
    RateAdapter,
)
from yap.prices.base import NAMES
from yap.services import price_providers
from yap.services.accounts import require_admin
from yap.services.common import Clock, ValidationError
from yap.services.secrets import KeyBox

log = logging.getLogger(__name__)

INTERVALS = (1, 2, 3, 4, 6, 8, 12, 24)  # hours (PRC-07)
NOT_FOUND_LIMIT = 2  # consecutive updates before a listing is unavailable (PRC-09)
STALE_AFTER = timedelta(days=3)  # PRC-12
RUNNING_AT_MOST = timedelta(hours=1)  # an unfinished run older than this was interrupted

# --- Schedule (PRC-07) --------------------------------------------------------------------


def get_settings(session: Session) -> PriceUpdateSettings:
    settings = session.get(PriceUpdateSettings, 1)
    assert settings is not None  # created by the migration
    return settings


def _times_of_day(settings: PriceUpdateSettings) -> list[time]:
    """The local times of day of the runs: the time of day, then every interval."""
    hour, minute = (int(part) for part in settings.time_of_day.split(":"))
    return sorted(
        time((hour + k * settings.interval_hours) % 24, minute)
        for k in range(24 // settings.interval_hours)
    )


def next_run(settings: PriceUpdateSettings, now: datetime) -> datetime:
    """The first run after `now`, in UTC; computed in local time, so daylight saving changes
    keep the local time of day (NFR-14)."""
    zone = ZoneInfo(settings.time_zone)
    today = now.astimezone(zone).date()
    for day in (today, today + timedelta(days=1)):
        for moment in _times_of_day(settings):
            candidate = datetime.combine(day, moment, tzinfo=zone).astimezone(UTC)
            if candidate > now:
                return candidate
    raise AssertionError("a run within two days")  # pragma: no cover


def update_settings(
    session: Session,
    actor: Investor,
    clock: Clock,
    *,
    time_of_day: str,
    time_zone: str,
    interval_hours: int,
) -> PriceUpdateSettings:
    """PRC-07: set by the admin; the next run follows from them."""
    require_admin(actor)
    problems = []
    try:
        hour, minute = (int(part) for part in time_of_day.split(":"))
        if not (0 <= hour < 24 and 0 <= minute < 60 and len(time_of_day) == 5):
            raise ValueError(time_of_day)
    except ValueError:
        problems.append(("time_of_day", msg("time_of_day_invalid")))
    if time_zone not in available_timezones():
        problems.append(("time_zone", msg("time_zone_unknown", time_zone=time_zone)))
    if interval_hours not in INTERVALS:
        hours = ", ".join(str(i) for i in INTERVALS)
        problems.append(("interval_hours", msg("interval_invalid", intervals=hours)))
    if problems:
        raise ValidationError(problems)
    settings = get_settings(session)
    settings.time_of_day, settings.time_zone = time_of_day, time_zone
    settings.interval_hours = interval_hours
    settings.next_run_at = next_run(settings, clock.now())
    return settings


def due(session: Session, clock: Clock) -> bool:
    """Whether the scheduled run is due; a run missed while the app was down is due at once
    (spec 2.5)."""
    settings = get_settings(session)
    if settings.next_run_at is None:
        settings.next_run_at = next_run(settings, clock.now())
        session.commit()
    return settings.next_run_at <= clock.now()


# --- Exchange rates and auto prices (PRC-11, CMP-01) --------------------------------------


@dataclass(frozen=True)
class Conversion:
    rate: Decimal
    date: str | None  # None: the same currency


def conversion(session: Session, base: str, quote: str) -> Conversion | None:
    if base == quote:
        return Conversion(Decimal(1), None)
    row = session.get(FxRate, (base, quote))
    return Conversion(row.rate, row.rate_date) if row else None


@dataclass(frozen=True)
class AutoPrice:
    """An auto price in the portfolio currency, with where it came from (CMP-10)."""

    listing: ListingRow
    listing_price: Decimal
    fx_rate: Decimal
    price: Decimal  # listing_price x fx_rate
    price_date: str


@dataclass(frozen=True)
class PriceInfo:
    """The price source of a position for a snapshot form: an auto price, or why there is
    none (`notice`: no_price, unavailable, no_rate)."""

    kind: str | None  # auto | manual | unresolved | None (never looked up)
    auto: AutoPrice | None = None
    notice: str | None = None
    listing: ListingRow | None = None


def price_info(session: Session, actor: Investor, asset: Asset, currency: str) -> PriceInfo:
    """CMP-01, PRC-09, PRC-11: what the snapshot form pre-fills for the position."""
    source = session.get(PriceSource, (actor.id, asset.id))
    if source is None:
        return PriceInfo(None)
    listing = source.listing
    if source.kind != "auto":
        # A listing kept on a manual source was retired (PRC-09)
        notice = "unavailable" if listing is not None and not listing.available else None
        return PriceInfo(source.kind, notice=notice, listing=listing)
    assert listing is not None
    if listing.price is None or listing.price_date is None:
        return PriceInfo("auto", notice="no_price", listing=listing)
    rate = conversion(session, listing.quote_currency, currency)
    if rate is None:
        return PriceInfo("auto", notice="no_rate", listing=listing)
    auto = AutoPrice(
        listing, listing.price, rate.rate, listing.price * rate.rate, listing.price_date
    )
    return PriceInfo("auto", auto=auto, listing=listing)


def stale(price_date: str | None, today: date) -> bool:
    """PRC-12: more than 3 days old."""
    return price_date is not None and today - date.fromisoformat(price_date) > STALE_AFTER


# --- The update (PRC-07 to PRC-11) --------------------------------------------------------


def _listings_in_use(session: Session) -> list[ListingRow]:
    """Each listing used as a price source by at least one investor, once; the oldest
    update first (PRC-08)."""
    rows = session.scalars(
        select(ListingRow)
        .join(PriceSource, PriceSource.listing_id == ListingRow.id)
        .where(PriceSource.kind == "auto", ListingRow.available)
        .distinct()
    )
    epoch = datetime.min.replace(tzinfo=UTC)
    return sorted(rows, key=lambda row: (row.price_updated_at or epoch, row.id))


def _count(result: dict[str, dict[str, int]], provider: str, outcome: str) -> None:
    counts = result.setdefault(provider, {"updated": 0, "skipped": 0, "failed": 0})
    counts[outcome] = counts.get(outcome, 0) + 1


def _retire(session: Session, listing: ListingRow, clock: Clock) -> None:
    price_providers.retire_listing(session, listing, clock)


def _update_prices(
    session: Session,
    clock: Clock,
    keys: KeyBox,
    adapters: AdapterFactory,
    result: dict[str, dict[str, int]],
) -> set[str]:
    """Returns the currencies of the listings in use."""
    currencies: set[str] = set()
    for listing in _listings_in_use(session):
        currencies.add(listing.quote_currency)
        provider: PriceProvider = listing.provider
        name = NAMES[Provider(provider.provider)]
        if provider.archived_at is not None or not provider.enabled:
            _retire(session, listing, clock)  # PRC-09
            session.commit()
            continue
        if not price_providers.can_call(session, provider, clock):
            _count(result, name, "skipped")  # the next run updates it first (PRC-08)
            session.commit()
            continue
        try:
            config = price_providers.config_for(provider, keys)
            with price_providers.counted_client(session, provider, clock) as client:
                adapter: PriceAdapter = adapters(config, client)  # type: ignore[assignment]
                quote = adapter.price(listing.symbol)
            listing.price, listing.price_date = quote.price, quote.date.isoformat()
            listing.price_updated_at = clock.now()
            listing.not_found_count = 0
            _count(result, name, "updated")
        except PriceError as e:
            if e.kind is ErrorKind.NOT_FOUND:
                listing.not_found_count += 1
                if listing.not_found_count >= NOT_FOUND_LIMIT:
                    _retire(session, listing, clock)
                _count(result, name, "not_found")
            else:
                _count(result, name, "skipped" if e.kind is ErrorKind.QUOTA else "failed")
        session.commit()  # an interrupted run keeps the prices it fetched (spec 2.5)
    return currencies


def _update_rates(
    session: Session,
    clock: Clock,
    keys: KeyBox,
    adapters: AdapterFactory,
    currencies: set[str],
    result: dict[str, dict[str, int]],
) -> None:
    """PRC-11: from each listing currency to each portfolio currency, one call per base."""
    targets = set(
        session.scalars(select(Portfolio.currency).where(Portfolio.archived_at.is_(None)))
    )
    source = session.scalar(select(PriceProvider).where(PriceProvider.built_in))
    assert source is not None
    name = NAMES[Provider(source.provider)]
    for base in sorted(currencies):
        quotes = sorted(targets - {base})
        if not quotes:
            continue
        try:
            with price_providers.counted_client(session, source, clock) as client:
                adapter: RateAdapter = adapters(  # type: ignore[assignment]
                    price_providers.config_for(source, keys), client
                )
                rates = adapter.rates(base, quotes)
            for quote, rate in rates.items():
                row = session.get(FxRate, (base, quote)) or FxRate(base=base, quote=quote)
                row.rate, row.rate_date = rate.rate, rate.date.isoformat()
                row.updated_at = clock.now()
                session.add(row)
            _count(result, name, "updated")
        except PriceError:
            _count(result, name, "failed")
        session.commit()


def running(session: Session, clock: Clock) -> PriceUpdateRun | None:
    """A run that started less than an hour ago and has not finished; only one at a time."""
    return session.scalar(
        select(PriceUpdateRun).where(
            PriceUpdateRun.finished_at.is_(None),
            PriceUpdateRun.started_at > clock.now() - RUNNING_AT_MOST,
        )
    )


def run_update(
    session: Session, clock: Clock, keys: KeyBox, adapters: AdapterFactory, trigger: str
) -> PriceUpdateRun | None:
    """PRC-07: one run of the price update, in its own session; None if one is running.
    Sets the next scheduled run."""
    if running(session, clock) is not None:
        return None
    run = PriceUpdateRun(trigger=trigger, started_at=clock.now(), finished_at=None)
    session.add(run)
    settings = get_settings(session)
    settings.next_run_at = next_run(settings, clock.now())
    session.commit()
    result: dict[str, dict[str, int]] = {}
    try:
        currencies = _update_prices(session, clock, keys, adapters, result)
        _update_rates(session, clock, keys, adapters, currencies, result)
    finally:
        run.result = result
        run.finished_at = clock.now()
        session.commit()
    return run


def last_run(session: Session) -> PriceUpdateRun | None:
    return session.scalar(select(PriceUpdateRun).order_by(PriceUpdateRun.id.desc()).limit(1))


def listings_in_use_count(session: Session, provider: PriceProvider) -> int:
    """PRC-10"""
    return sum(1 for row in _listings_in_use(session) if row.provider_id == provider.id)
