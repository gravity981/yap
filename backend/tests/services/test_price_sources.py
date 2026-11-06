"""Ticker lookup with its shared cache, and the investor's price sources (PRC-02 to
PRC-06)."""

import httpx2
import pytest
from sqlalchemy.orm import Session

from tests.fixtures import TEST_SECRET, Factory, spec
from yap.db.models import Investor, PriceProvider
from yap.messages import msg
from yap.prices import ErrorKind, Listing, PriceError, ProviderConfig
from yap.services import price_providers, price_sources
from yap.services.common import ValidationError
from yap.services.price_providers import ProviderSpec
from yap.services.secrets import KeyBox

KEYS = KeyBox(TEST_SECRET)
SIX = Listing("VWRL.SW", "SIX", "CHF", "Vanguard FTSE All-World")
LSE = Listing("VWRL.L", "London", "USD", "Vanguard FTSE All-World")


class Scripted:
    """Answers lookups per provider and counts the calls (no HTTP)."""

    def __init__(self, answers: dict[str, list[Listing] | PriceError]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, str]] = []

    def __call__(self, config: ProviderConfig, client: httpx2.Client) -> Scripted.Adapter:
        return Scripted.Adapter(self, config.provider.value)

    class Adapter:
        def __init__(self, owner: Scripted, provider: str) -> None:
            self.owner, self.provider = owner, provider

        def lookup(self, ticker: str) -> list[Listing]:
            self.owner.calls.append((self.provider, ticker))
            answer = self.owner.answers[self.provider]
            if isinstance(answer, PriceError):
                raise answer
            return answer


def add(session: Session, factory: Factory, provider: str, **kw: object) -> PriceProvider:
    return price_providers.create_provider(
        session,
        factory.admin(),
        factory.clock,
        KEYS,
        ProviderSpec(provider, **kw),  # type: ignore[arg-type]
    )


def lookup(
    session: Session, factory: Factory, who: Investor, adapters: Scripted, ticker: str, **kw: bool
) -> price_sources.LookupResult:
    return price_sources.lookup(session, who, factory.clock, KEYS, adapters, ticker, **kw)


@pytest.mark.req("PRC-02", "PRC-03")
def test_lookup_is_cached_for_all_investors(session: Session, factory: Factory) -> None:
    add(session, factory, "yahoo")
    add(session, factory, "coingecko")
    adapters = Scripted({"yahoo": [SIX, LSE], "coingecko": []})
    alice, bob = factory.investor(), factory.investor()
    result = lookup(session, factory, alice, adapters, " vwrl ")
    assert (result.ticker, result.status) == ("VWRL", "found")
    assert [(x.symbol, x.quote_currency, x.provider.provider) for x in result.listings] == [
        ("VWRL.SW", "CHF", "yahoo"),
        ("VWRL.L", "USD", "yahoo"),
    ]
    assert adapters.calls == [("yahoo", "VWRL"), ("coingecko", "VWRL")]
    # Another investor gets the cached answer, including CoinGecko's "not found"
    again = lookup(session, factory, bob, adapters, "VWRL")
    assert [x.id for x in again.listings] == [x.id for x in result.listings]
    assert len(adapters.calls) == 2


@pytest.mark.req("PRC-02", "PRC-03", "PRC-06")
def test_not_found_is_cached_and_try_auto_asks_again_once_a_day(
    session: Session, factory: Factory
) -> None:
    add(session, factory, "yahoo")
    adapters = Scripted({"yahoo": []})
    alice = factory.investor()
    assert lookup(session, factory, alice, adapters, "NEW").status == "not_found"
    lookup(session, factory, alice, adapters, "NEW", retry=True)  # asked today already
    assert len(adapters.calls) == 1
    factory.clock.advance(days=1)
    adapters.answers["yahoo"] = [SIX]
    assert lookup(session, factory, alice, adapters, "NEW").status == "not_found"  # cached
    assert lookup(session, factory, alice, adapters, "NEW", retry=True).status == "found"
    assert len(adapters.calls) == 2
    # Without "try auto", "not found" expires after 7 days
    adapters.answers["yahoo"] = []
    lookup(session, factory, alice, adapters, "OTHER")
    factory.clock.advance(days=7)
    lookup(session, factory, alice, adapters, "OTHER")
    assert adapters.calls[-2:] == [("yahoo", "OTHER"), ("yahoo", "OTHER")]


@pytest.mark.req("PRC-03")
def test_found_expires_after_30_days_unless_an_investor_uses_it(
    session: Session, factory: Factory
) -> None:
    add(session, factory, "yahoo")
    adapters = Scripted({"yahoo": [SIX]})
    alice = factory.investor()
    found = lookup(session, factory, alice, adapters, "VWRL")
    factory.clock.advance(days=30)
    lookup(session, factory, alice, adapters, "VWRL")
    assert len(adapters.calls) == 2  # unused: asked again
    price_sources.set_source(
        session,
        alice,
        factory.clock,
        "VWRL",
        "auto",
        found.listings[0].id,
        name="V",
        asset_type="ETF",
    )
    factory.clock.advance(days=60)
    lookup(session, factory, alice, adapters, "VWRL")
    assert len(adapters.calls) == 2  # in use: kept


@pytest.mark.req("PRC-04")
def test_a_lookup_never_fails(session: Session, factory: Factory) -> None:
    alice = factory.investor()
    nobody = lookup(session, factory, alice, Scripted({}), "VWRL")
    assert nobody.status == "unresolved"
    assert [p.message.code for p in nobody.problems] == ["price_no_provider"]
    yahoo = add(session, factory, "yahoo")
    quota = PriceError(ErrorKind.QUOTA, msg("price_provider_quota", provider="Yahoo Finance"))
    failing = Scripted({"yahoo": quota})
    result = lookup(session, factory, alice, failing, "VWRL")
    assert result.status == "unresolved"
    assert [(p.provider, p.message.code) for p in result.problems] == [
        ("Yahoo Finance", "price_provider_quota")
    ]
    # An older "found" answer is used when the provider cannot be asked
    lookup(session, factory, alice, Scripted({"yahoo": [SIX]}), "VWRL")
    factory.clock.advance(days=31)
    stale = lookup(session, factory, alice, failing, "VWRL")
    assert (stale.status, len(stale.listings), len(stale.problems)) == ("found", 1, 1)
    # Disabled providers are not asked
    price_providers.update_provider(
        session,
        factory.admin(),
        factory.clock,
        KEYS,
        yahoo.id,
        ProviderSpec("yahoo", enabled=False),
    )
    assert lookup(session, factory, alice, failing, "VWRL").status == "unresolved"
    assert len(failing.calls) == 2


@pytest.mark.req("PRC-05", "PRC-02", "IMP-08")
def test_price_source_per_investor(session: Session, factory: Factory) -> None:
    add(session, factory, "yahoo")
    alice, bob = factory.investor(), factory.investor()
    listing = lookup(session, factory, alice, Scripted({"yahoo": [SIX, LSE]}), "VWRL").listings[0]
    with pytest.raises(ValidationError) as err:  # a ticker new to the catalog needs name, type
        price_sources.set_source(session, alice, factory.clock, "VWRL", "auto", listing.id)
    assert err.value.problems[0][1].code == "ticker_unknown_add"
    source = price_sources.set_source(
        session,
        alice,
        factory.clock,
        "vwrl",
        "auto",
        listing.id,
        name="All-World",
        asset_type="ETF",
    )
    assert (source.kind, source.listing_id, source.asset.ticker) == ("auto", listing.id, "VWRL")
    price_sources.set_source(session, bob, factory.clock, "VWRL", "manual")
    assert price_sources.source_for_ticker(session, alice, "VWRL").kind == "auto"  # type: ignore[union-attr]
    assert price_sources.source_for_ticker(session, bob, "VWRL").kind == "manual"  # type: ignore[union-attr]
    for kind, listing_id, code in (
        ("auto", None, "price_listing_unavailable"),
        ("auto", 999, "price_listing_unavailable"),
        ("magic", None, "price_source_kind_unknown"),
    ):
        with pytest.raises(ValidationError) as err:
            price_sources.set_source(session, alice, factory.clock, "VWRL", kind, listing_id)
        assert err.value.problems[0][1].code == code
    unresolved = price_sources.set_source(session, alice, factory.clock, "VWRL", "unresolved")
    assert (unresolved.kind, unresolved.listing_id) == ("unresolved", None)


@pytest.mark.req("PRC-05")
def test_the_assets_an_investor_uses(session: Session, factory: Factory) -> None:
    alice = factory.investor()
    policy = factory.active_policy(alice, [spec("BBB", 60), spec("AAA", 40)])
    portfolio = factory.portfolio(alice, policy)
    from decimal import Decimal

    from yap.services import snapshots
    from yap.services.snapshots import ValueSpec

    snapshots.create_snapshot(
        session,
        alice,
        factory.clock,
        portfolio.id,
        [ValueSpec("OLD", Decimal(5), "Old", "stock")],
    )
    price_sources.set_source(
        session, alice, factory.clock, "ZZZ", "manual", name="Z", asset_type="stock"
    )
    rows = price_sources.list_sources(session, alice)
    assert [(r.asset.ticker, r.source.kind if r.source else None) for r in rows] == [
        ("AAA", None),
        ("BBB", None),
        ("OLD", None),
        ("ZZZ", "manual"),
    ]
    assert price_sources.list_sources(session, factory.investor()) == []
