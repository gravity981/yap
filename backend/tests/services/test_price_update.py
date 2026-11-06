"""The price update, exchange rates and auto prices in snapshots (PRC-07 to PRC-12, CMP-01,
CMP-10, RB-17)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import httpx2
import pytest
from sqlalchemy.orm import Session

from tests.fixtures import TEST_SECRET, Factory
from yap.db.models import FxRate, Investor, Portfolio, PriceProvider
from yap.messages import msg
from yap.prices import (
    ErrorKind,
    Listing,
    PriceError,
    ProviderConfig,
    Quote,
    Rate,
)
from yap.services import (
    price_providers,
    price_sources,
    price_update,
    rebalances,
    snapshots,
)
from yap.services.common import ValidationError
from yap.services.price_providers import ProviderSpec
from yap.services.secrets import KeyBox
from yap.services.snapshots import ValueSpec

KEYS = KeyBox(TEST_SECRET)
DAY = date(2026, 11, 2)


class Scripted:
    """Prices per symbol (or an error), rates to CHF, and the calls made."""

    def __init__(self, prices: dict[str, Decimal | PriceError]) -> None:
        self.prices = prices
        self.calls: list[str] = []

    def __call__(self, config: ProviderConfig, client: httpx2.Client) -> Scripted:
        self.provider = config.provider.value
        self.client = client
        return self

    def _request(self) -> None:
        """Counted like an HTTP request of a real adapter (PRC-08)."""
        for hook in self.client.event_hooks["request"]:
            hook(self.client.build_request("GET", "https://example.com"))

    def lookup(self, ticker: str) -> list[Listing]:
        self._request()
        return [
            Listing(f"{ticker}.SW", "SIX", "CHF", ticker),
            Listing(f"{ticker}.US", "NYSE", "USD", ticker),
        ]

    def price(self, symbol: str) -> Quote:
        self._request()
        self.calls.append(symbol)
        answer = self.prices[symbol]
        if isinstance(answer, PriceError):
            raise answer
        return Quote(answer, None, DAY)

    def rates(self, base: str, quotes: list[str]) -> dict[str, Rate]:
        self.calls.append(f"rates {base}->{','.join(quotes)}")
        return {q: Rate(Decimal("0.8"), DAY) for q in quotes if q == "CHF"}


def not_found() -> PriceError:
    return PriceError(ErrorKind.NOT_FOUND, msg("price_not_found", provider="Yahoo", symbol="x"))


def setup(
    session: Session, factory: Factory, adapters: Scripted, **spec_kw: object
) -> tuple[Investor, Portfolio, PriceProvider]:
    """Alice's portfolio (CHF) with AAA on its US listing (USD) and BBB on SIX (CHF)."""
    provider = price_providers.create_provider(
        session,
        factory.admin(),
        factory.clock,
        KEYS,
        ProviderSpec("yahoo", **spec_kw),  # type: ignore[arg-type]
    )
    alice = factory.investor()
    portfolio = factory.portfolio(alice)
    for ticker, symbol in (("AAA", "AAA.US"), ("BBB", "BBB.SW")):
        found = price_sources.lookup(session, alice, factory.clock, KEYS, adapters, ticker)
        listing = next(x for x in found.listings if x.symbol == symbol)
        price_sources.set_source(session, alice, factory.clock, ticker, "auto", listing.id)
    session.commit()
    return alice, portfolio, provider


def run(session: Session, factory: Factory, adapters: Scripted):  # type: ignore[no-untyped-def]
    return price_update.run_update(session, factory.clock, KEYS, adapters, "schedule")


# --- Schedule ---------------------------------------------------------------------------


@pytest.mark.req("PRC-07", "NFR-14", "USR-11")
def test_the_local_time_of_day_stays_across_daylight_saving(
    session: Session, factory: Factory
) -> None:
    root = factory.admin()
    settings = price_update.update_settings(
        session,
        root,
        factory.clock,
        time_of_day="22:00",
        time_zone="Europe/Zurich",
        interval_hours=24,
    )
    summer = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    winter = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)
    assert price_update.next_run(settings, summer) == datetime(2026, 7, 1, 20, 0, tzinfo=UTC)
    assert price_update.next_run(settings, winter) == datetime(2026, 12, 1, 21, 0, tzinfo=UTC)
    # Every 6 hours from 22:00: 04:00, 10:00, 16:00, 22:00 local
    settings.interval_hours = 6
    assert price_update.next_run(settings, winter) == datetime(2026, 12, 1, 15, 0, tzinfo=UTC)
    assert settings.next_run_at is not None  # set when the settings change
    for kw, field in (
        ({"time_of_day": "25:00"}, "time_of_day"),
        ({"time_zone": "Mars/Base"}, "time_zone"),
        ({"interval_hours": 5}, "interval_hours"),
    ):
        with pytest.raises(ValidationError) as err:
            price_update.update_settings(
                session,
                root,
                factory.clock,
                **{"time_of_day": "22:00", "time_zone": "UTC", "interval_hours": 24, **kw},  # type: ignore[arg-type]
            )
        assert err.value.problems[0][0] == field


@pytest.mark.req("PRC-07")
def test_a_missed_run_is_due_at_once(session: Session, factory: Factory) -> None:
    settings = price_update.get_settings(session)  # default: daily at 22:00 UTC
    assert (settings.time_of_day, settings.time_zone, settings.interval_hours) == (
        "22:00",
        "UTC",
        24,
    )
    assert not price_update.due(session, factory.clock)  # 09:00: next run at 22:00
    factory.clock.advance(days=2)  # the app was down
    assert price_update.due(session, factory.clock)


# --- The update ---------------------------------------------------------------------------


@pytest.mark.req("PRC-07", "PRC-11", "PRC-10", "NFR-04")
def test_the_update_fetches_each_listing_once_and_the_rates(
    session: Session, factory: Factory
) -> None:
    adapters = Scripted({"AAA.US": Decimal("100.5"), "BBB.SW": Decimal("50")})
    alice, _, provider = setup(session, factory, adapters)
    bob = factory.investor()  # uses the same listing: fetched once
    listing = price_sources.source_for_ticker(session, alice, "AAA").listing  # type: ignore[union-attr]
    price_sources.set_source(session, bob, factory.clock, "AAA", "auto", listing.id)  # type: ignore[union-attr]
    record = run(session, factory, adapters)
    assert record is not None and record.finished_at is not None
    assert sorted(c for c in adapters.calls if not c.startswith("rates")) == ["AAA.US", "BBB.SW"]
    assert (listing.price, listing.price_date) == (Decimal("100.5"), "2026-11-02")  # type: ignore[union-attr]
    # The portfolio is in CHF: a rate from USD, none needed for CHF
    assert [c for c in adapters.calls if c.startswith("rates")] == ["rates USD->CHF"]
    assert session.get(FxRate, ("USD", "CHF")).rate == Decimal("0.8")  # type: ignore[union-attr]
    assert record.result == {
        "Yahoo Finance": {"updated": 2, "skipped": 0, "failed": 0},
        "Frankfurter (ECB)": {"updated": 1, "skipped": 0, "failed": 0},
    }
    assert price_update.listings_in_use_count(session, provider) == 2
    # The next scheduled run follows the run
    assert price_update.get_settings(session).next_run_at > factory.clock.now()  # type: ignore[operator]


@pytest.mark.req("PRC-08")
def test_beyond_the_limit_the_oldest_update_goes_first_next_time(
    session: Session, factory: Factory
) -> None:
    adapters = Scripted({"AAA.US": Decimal(1), "BBB.SW": Decimal(2)})
    setup(session, factory, adapters, daily_call_limit=3)  # 2 lookups + 1 price
    first = run(session, factory, adapters)
    assert first.result["Yahoo Finance"] == {"updated": 1, "skipped": 1, "failed": 0}  # type: ignore[index, union-attr]
    updated_first = [c for c in adapters.calls if not c.startswith("rates")]
    factory.clock.advance(days=1)
    adapters.calls.clear()
    run(session, factory, adapters)
    second = [c for c in adapters.calls if not c.startswith("rates")]
    # The one skipped (never updated) goes first
    assert second[0] not in updated_first


@pytest.mark.req("PRC-09")
def test_a_listing_not_found_twice_becomes_unavailable(session: Session, factory: Factory) -> None:
    adapters = Scripted({"AAA.US": not_found(), "BBB.SW": Decimal(2)})
    alice, portfolio, _ = setup(session, factory, adapters)
    run(session, factory, adapters)
    source = price_sources.source_for_ticker(session, alice, "AAA")
    assert source is not None and source.kind == "auto"  # once may be a glitch
    factory.clock.advance(days=1)
    run(session, factory, adapters)
    session.refresh(source)
    assert source.kind == "manual" and source.listing is not None
    assert not source.listing.available
    asset = source.asset
    info = price_update.price_info(session, alice, asset, portfolio.currency)
    assert (info.kind, info.notice, info.listing.symbol) == ("manual", "unavailable", "AAA.US")  # type: ignore[union-attr]
    # "Try auto" asks again; found again, the listing is available again
    found = price_sources.lookup(session, alice, factory.clock, KEYS, adapters, "AAA", retry=True)
    assert source.listing.available and "AAA.US" in [x.symbol for x in found.listings]


@pytest.mark.req("PRC-09", "PRC-01")
def test_disabling_a_provider_retires_its_listings(session: Session, factory: Factory) -> None:
    adapters = Scripted({})
    alice, _, provider = setup(session, factory, adapters)
    price_providers.update_provider(
        session,
        factory.admin(),
        factory.clock,
        KEYS,
        provider.id,
        ProviderSpec("yahoo", enabled=False),
    )
    assert price_sources.source_for_ticker(session, alice, "BBB").kind == "manual"  # type: ignore[union-attr]


@pytest.mark.req("PRC-07")
def test_only_one_run_at_a_time(session: Session, factory: Factory) -> None:
    adapters = Scripted({})
    first = run(session, factory, adapters)
    assert first is not None
    first.finished_at = None  # as if it were still running
    session.commit()
    assert run(session, factory, adapters) is None
    factory.clock.advance(hours=2)  # an hour later it counts as interrupted
    assert run(session, factory, adapters) is not None


# --- Auto prices in snapshots -------------------------------------------------------------


@pytest.mark.req("CMP-01", "CMP-10", "PRC-11", "RB-17")
def test_snapshots_take_and_keep_the_auto_price(session: Session, factory: Factory) -> None:
    adapters = Scripted({"AAA.US": Decimal("100"), "BBB.SW": Decimal("50")})
    alice, portfolio, _ = setup(session, factory, adapters)
    rows = {r.ticker: r for r in snapshots.prefill(session, alice, factory.clock, portfolio.id)}
    assert rows["AAA"].source.notice == "no_price"  # not updated yet
    run(session, factory, adapters)
    rows = {r.ticker: r for r in snapshots.prefill(session, alice, factory.clock, portfolio.id)}
    assert rows["AAA"].price == Decimal("80.0")  # 100 USD x 0.8
    snapshot = snapshots.create_snapshot(
        session,
        alice,
        factory.clock,
        portfolio.id,
        [ValueSpec("AAA", units=Decimal(6)), ValueSpec("BBB", units=Decimal(4), price=Decimal(51))],
        require_units=True,
    )
    aaa, bbb = sorted(snapshot.values, key=lambda v: v.asset.ticker)
    assert (aaa.price_kind, aaa.price, aaa.value) == ("auto", Decimal("80.0"), Decimal("480.00"))
    assert (aaa.listing.symbol, aaa.listing_price, aaa.listing_currency) == ("AAA.US", 100, "USD")  # type: ignore[union-attr]
    assert (aaa.fx_rate, aaa.price_date) == (Decimal("0.8"), "2026-11-02")
    assert (bbb.price_kind, bbb.price) == ("manual", 51)  # changed by hand
    # Later prices never change the snapshot
    adapters.prices["AAA.US"] = Decimal(200)
    factory.clock.advance(days=1)
    run(session, factory, adapters)
    session.refresh(aaa)
    assert (aaa.price, aaa.listing_price) == (Decimal("80.0"), 100)
    # A confirmed rebalance keeps the input's auto price in its result (RB-17)
    plan = rebalances.plan(
        session,
        alice,
        factory.clock,
        portfolio.id,
        snapshot_id=snapshot.id,
        contribution=Decimal(0),
    )
    record = rebalances.confirm(
        session,
        alice,
        factory.clock,
        portfolio.id,
        snapshot_id=snapshot.id,
        contribution=Decimal(0),
        policy_version_id=plan.version.id,
        executed=[],
    )
    result = {v.asset.ticker: v for v in record_result(session, record)}
    assert (result["AAA"].price_kind, result["AAA"].price) == ("auto", Decimal("80.0"))


def record_result(session: Session, record):  # type: ignore[no-untyped-def]
    from yap.db.models import Snapshot

    return session.get(Snapshot, record.result_snapshot_id).values  # type: ignore[union-attr]


@pytest.mark.req("PRC-11")
def test_without_a_rate_the_position_is_manual_with_a_notice(
    session: Session, factory: Factory
) -> None:
    adapters = Scripted({"AAA.US": Decimal("100"), "BBB.SW": Decimal("50")})
    alice, portfolio, _ = setup(session, factory, adapters)
    run(session, factory, adapters)
    other = factory.portfolio(alice, portfolio.policy, name="Euro", currency="EUR")
    info = price_update.price_info(
        session, alice, price_sources.source_for_ticker(session, alice, "AAA").asset, other.currency
    )  # type: ignore[union-attr]
    assert (info.auto, info.notice) == (None, "no_rate")


@pytest.mark.req("PRC-12")
def test_prices_older_than_three_days_are_stale() -> None:
    assert not price_update.stale("2026-11-02", date(2026, 11, 5))
    assert price_update.stale("2026-11-01", date(2026, 11, 5))
    assert not price_update.stale(None, date(2026, 11, 5))


@pytest.mark.req("PRC-07")
def test_cli_and_scheduler_run_the_update(
    db_url: str, monkeypatch: pytest.MonkeyPatch, session: Session, factory: Factory
) -> None:
    from yap import cli

    monkeypatch.setenv("PRICE_FAKE", "1")
    monkeypatch.setenv("APP_SECRET_KEY", TEST_SECRET)
    assert cli.update_prices(db_url) == "Nothing to update"
    assert price_update.last_run(session) is not None
    monkeypatch.setenv("APP_ENV", "prod")
    with pytest.raises(SystemExit):
        cli.update_prices(db_url)
