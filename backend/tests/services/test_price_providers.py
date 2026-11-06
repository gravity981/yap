"""Price providers configured by the admin, call counting and limits (PRC-01, PRC-08,
PRC-10, PRC-11)."""

from datetime import timedelta

import httpx2
import pytest
from sqlalchemy.orm import Session

from tests.fixtures import TEST_SECRET, Factory
from yap.db.models import Investor, PriceProvider
from yap.prices import ErrorKind, PriceError, ProviderConfig
from yap.services import price_providers
from yap.services.common import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from yap.services.price_providers import ProviderSpec
from yap.services.secrets import KeyBox

KEYS = KeyBox(TEST_SECRET)


def admin(factory: Factory) -> Investor:
    return factory.admin()


def built_in(session: Session) -> PriceProvider:
    row = session.query(PriceProvider).filter_by(built_in=True).one()
    return row


@pytest.mark.req("PRC-01", "PRC-11", "USR-05")
def test_the_built_in_rate_source_is_listed_and_cannot_be_changed(
    session: Session, factory: Factory
) -> None:
    root = admin(factory)
    rows = price_providers.list_providers(session, root)
    assert [(r.provider, r.built_in) for r in rows] == [("frankfurter", True)]
    with pytest.raises(ConflictError):
        price_providers.update_provider(
            session, root, factory.clock, KEYS, rows[0].id, ProviderSpec("frankfurter")
        )
    with pytest.raises(ConflictError):
        price_providers.archive_provider(session, root, factory.clock, rows[0].id)
    with pytest.raises(ForbiddenError):  # USR-05: admins only
        price_providers.list_providers(session, factory.investor())


@pytest.mark.req("PRC-01", "REV-15")
def test_each_provider_once_with_its_key(session: Session, factory: Factory) -> None:
    root = admin(factory)
    assert [p.value for p in price_providers.addable_providers(session, root)] == [
        "eodhd",
        "yahoo",
        "coingecko",
    ]

    def problems(spec: ProviderSpec) -> list[tuple[str, str]]:
        with pytest.raises(ValidationError) as err:
            price_providers.create_provider(session, root, factory.clock, KEYS, spec)
        return [(p, m.code) for p, m in err.value.problems]

    assert problems(ProviderSpec("eodhd")) == [("api_key", "api_key_required")]
    assert problems(ProviderSpec("frankfurter")) == [("provider", "price_provider_unknown")]
    assert problems(ProviderSpec("yahoo", daily_call_limit=-1)) == [
        ("daily_call_limit", "limit_negative")
    ]
    eodhd = price_providers.create_provider(
        session, root, factory.clock, KEYS, ProviderSpec("eodhd", 20, api_key="secret-key-9876")
    )
    assert (eodhd.api_key_last4, eodhd.daily_call_limit) == ("9876", 20)
    assert KEYS.decrypt(eodhd.api_key_encrypted or b"") == "secret-key-9876"
    assert problems(ProviderSpec("eodhd", api_key="x")) == [("provider", "price_provider_exists")]
    # Yahoo takes no key: one given is ignored
    yahoo = price_providers.create_provider(
        session, root, factory.clock, KEYS, ProviderSpec("yahoo", api_key="ignored")
    )
    assert yahoo.api_key_encrypted is None
    # Changing keeps the key unless a new one is given
    price_providers.update_provider(
        session, root, factory.clock, KEYS, eodhd.id, ProviderSpec("eodhd", None, enabled=False)
    )
    assert (eodhd.api_key_last4, eodhd.daily_call_limit, eodhd.enabled) == ("9876", None, False)
    # Archived, it can be added again
    price_providers.archive_provider(session, root, factory.clock, eodhd.id)
    with pytest.raises(NotFoundError):
        price_providers.get_provider(session, eodhd.id)
    assert "eodhd" in [p.value for p in price_providers.addable_providers(session, root)]


@pytest.mark.req("PRC-01")
def test_keys_cannot_be_stored_without_the_secret(session: Session, factory: Factory) -> None:
    with pytest.raises(ValidationError) as err:
        price_providers.create_provider(
            session, admin(factory), factory.clock, KeyBox(None), ProviderSpec("eodhd", api_key="k")
        )
    assert err.value.problems[0][1].code == "api_key_no_secret"


def counting(
    session: Session, factory: Factory, row: PriceProvider, statuses: list[int]
) -> list[int]:
    """Sends one request per status through the counted client; returns the answers."""
    answered = []
    with price_providers.counted_client(session, row, factory.clock) as http:
        http._transport = httpx2.MockTransport(  # type: ignore[attr-defined]
            lambda request: httpx2.Response(statuses[len(answered)])
        )
        for _ in statuses:
            answered.append(http.get("https://example.com").status_code)
    return answered


@pytest.mark.req("PRC-08", "PRC-10")
def test_calls_are_counted_per_utc_day_and_stop_at_the_limit(
    session: Session, factory: Factory
) -> None:
    root = admin(factory)
    row = price_providers.create_provider(
        session, root, factory.clock, KEYS, ProviderSpec("yahoo", daily_call_limit=2)
    )
    assert counting(session, factory, row, [200, 200]) == [200, 200]
    assert price_providers.usage_today(session, row, factory.clock).calls == 2
    with pytest.raises(PriceError) as err:  # refused before anything is sent
        counting(session, factory, row, [200])
    assert err.value.kind is ErrorKind.QUOTA
    assert price_providers.usage_today(session, row, factory.clock).calls == 2
    factory.clock.advance(days=1)  # a new UTC day
    assert price_providers.can_call(session, row, factory.clock)


@pytest.mark.req("PRC-08")
def test_a_provider_saying_its_quota_is_used_up_stops_it_for_the_day(
    session: Session, factory: Factory
) -> None:
    row = price_providers.create_provider(
        session, admin(factory), factory.clock, KEYS, ProviderSpec("yahoo")
    )
    assert counting(session, factory, row, [429]) == [429]
    assert not price_providers.can_call(session, row, factory.clock)
    factory.clock.current += timedelta(days=1)
    assert price_providers.can_call(session, row, factory.clock)


class Checked:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.configs: list[ProviderConfig] = []

    def __call__(self, config: ProviderConfig, client: httpx2.Client) -> Checked:
        self.configs.append(config)
        return self

    def check(self) -> None:
        if self.error:
            raise self.error


@pytest.mark.req("PRC-01", "PRC-11")
def test_connection_test(session: Session, factory: Factory) -> None:
    root = admin(factory)
    eodhd = price_providers.create_provider(
        session, root, factory.clock, KEYS, ProviderSpec("eodhd", api_key="secret-key-9876")
    )
    ok = Checked()
    result = price_providers.test_connection(session, root, factory.clock, KEYS, ok, eodhd.id)
    assert result.ok and result.message.code == "price_connection_ok"
    assert ok.configs[0].api_key == "secret-key-9876"  # decrypted for the request only
    refused = Checked(
        PriceError(ErrorKind.AUTH, price_providers.msg("price_provider_auth", provider="EODHD"))
    )
    result = price_providers.test_connection(session, root, factory.clock, KEYS, refused, eodhd.id)
    assert not result.ok and result.message.code == "price_provider_auth"
    broken = Checked(RuntimeError("boom with secret-key-9876"))
    result = price_providers.test_connection(session, root, factory.clock, KEYS, broken, eodhd.id)
    assert result.message.code == "test_failed_unexpectedly"
    assert "secret-key-9876" not in str(result.message)
    # The built-in source has a test too
    rates = price_providers.test_connection(
        session, root, factory.clock, KEYS, Checked(), built_in(session).id
    )
    assert rates.ok
