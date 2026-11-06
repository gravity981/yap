"""Price providers: configured by the admin, with their API keys and daily call limits
(PRC-01, PRC-08, PRC-10). The built-in exchange rate source is listed like them but
cannot be changed (PRC-11)."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

import httpx2
from sqlalchemy import select
from sqlalchemy.orm import Session

from yap.db.models import Investor, PriceProvider, PriceSource, ProviderUsage
from yap.db.models import Listing as ListingRow
from yap.messages import Message, msg
from yap.prices import (
    AdapterFactory,
    ErrorKind,
    PriceError,
    Provider,
    ProviderConfig,
)
from yap.prices.base import KEY_POSSIBLE, KEY_REQUIRED, LISTING_PROVIDERS, NAMES
from yap.services.accounts import require_admin
from yap.services.common import (
    Clock,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from yap.services.secrets import KeyBox

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderSpec:
    """What the admin enters; `api_key` replaces the stored key only when given."""

    provider: str
    daily_call_limit: int | None = None
    enabled: bool = True
    api_key: str | None = None


def list_providers(session: Session, actor: Investor) -> list[PriceProvider]:
    """PRC-01: the built-in exchange rate source first, then the configured providers."""
    require_admin(actor)
    rows = session.scalars(select(PriceProvider).where(PriceProvider.archived_at.is_(None)))
    return sorted(rows, key=lambda p: (not p.built_in, NAMES[Provider(p.provider)]))


def addable_providers(session: Session, actor: Investor) -> list[Provider]:
    """Each provider can be added once (PRC-01)."""
    taken = {p.provider for p in list_providers(session, actor)}
    return [p for p in LISTING_PROVIDERS if p.value not in taken]


def get_provider(session: Session, provider_id: int) -> PriceProvider:
    row = session.get(PriceProvider, provider_id)
    if row is None or row.archived_at is not None:
        raise NotFoundError(msg("price_provider_not_found", id=provider_id))
    return row


def _changeable(session: Session, provider_id: int) -> PriceProvider:
    row = get_provider(session, provider_id)
    if row.built_in:
        raise ConflictError(msg("price_provider_built_in"))
    return row


def _check(
    session: Session, spec: ProviderSpec, row: PriceProvider | None, keys: KeyBox
) -> tuple[Provider, str | None]:
    problems: list[tuple[str, Message]] = []
    provider: Provider | None = None
    if spec.provider in {p.value for p in LISTING_PROVIDERS}:
        provider = Provider(spec.provider)
    else:  # unknown, or the built-in exchange rate source
        problems.append(("provider", msg("price_provider_unknown", provider=spec.provider)))
    if (
        row is None
        and provider is not None
        and session.scalar(
            select(PriceProvider.id).where(
                PriceProvider.provider == provider.value, PriceProvider.archived_at.is_(None)
            )
        )
    ):
        problems.append(("provider", msg("price_provider_exists", provider=NAMES[provider])))
    if spec.daily_call_limit is not None and spec.daily_call_limit < 0:
        problems.append(("daily_call_limit", msg("limit_negative")))
    new_key = (spec.api_key or "").strip() or None
    if provider is not None and provider not in KEY_POSSIBLE:
        new_key = None  # e.g. Yahoo: no key
    has_key = new_key is not None or (row is not None and row.api_key_encrypted is not None)
    if provider in KEY_REQUIRED and not has_key:
        problems.append(("api_key", msg("api_key_required")))
    if new_key and not keys.available:
        problems.append(("api_key", msg("api_key_no_secret")))
    if problems:
        raise ValidationError(problems)
    assert provider is not None
    return provider, new_key


def _apply(row: PriceProvider, spec: ProviderSpec, keys: KeyBox, new_key: str | None) -> None:
    row.daily_call_limit = spec.daily_call_limit
    row.enabled = spec.enabled
    if new_key:
        row.api_key_encrypted = keys.encrypt(new_key)
        row.api_key_last4 = new_key[-4:]


def create_provider(
    session: Session, actor: Investor, clock: Clock, keys: KeyBox, spec: ProviderSpec
) -> PriceProvider:
    """PRC-01: each provider at most once; keys encrypted like those of AI reviewers."""
    require_admin(actor)
    provider, new_key = _check(session, spec, None, keys)
    now = clock.now()
    row = PriceProvider(
        provider=provider.value, built_in=False, archived_at=None, created_at=now, updated_at=now
    )
    _apply(row, spec, keys, new_key)
    session.add(row)
    session.flush()
    return row


def update_provider(
    session: Session,
    actor: Investor,
    clock: Clock,
    keys: KeyBox,
    provider_id: int,
    spec: ProviderSpec,
) -> PriceProvider:
    """PRC-01: limit, key and enabled; the provider itself does not change."""
    require_admin(actor)
    row = _changeable(session, provider_id)
    _, new_key = _check(session, ProviderSpec(row.provider, *_rest(spec)), row, keys)
    _apply(row, spec, keys, new_key)
    row.updated_at = clock.now()
    if not row.enabled:
        _retire_all(session, row, clock)  # PRC-09
    session.flush()
    return row


def _rest(spec: ProviderSpec) -> tuple[int | None, bool, str | None]:
    return spec.daily_call_limit, spec.enabled, spec.api_key


def archive_provider(session: Session, actor: Investor, clock: Clock, provider_id: int) -> None:
    """PRC-01: instead of deleting; it can be added again afterwards. Its listings become
    unavailable (PRC-09)."""
    require_admin(actor)
    row = _changeable(session, provider_id)
    row.archived_at = clock.now()
    row.updated_at = row.archived_at
    _retire_all(session, row, clock)


def retire_listing(session: Session, listing: ListingRow, clock: Clock) -> None:
    """PRC-09: the listing becomes unavailable; investors using it switch to manual. Their
    source keeps the listing, so they see which one is gone."""
    listing.available = False
    for source in session.scalars(
        select(PriceSource).where(PriceSource.listing_id == listing.id, PriceSource.kind == "auto")
    ):
        source.kind = "manual"
        source.updated_at = clock.now()


def _retire_all(session: Session, row: PriceProvider, clock: Clock) -> None:
    for listing in session.scalars(select(ListingRow).where(ListingRow.provider_id == row.id)):
        retire_listing(session, listing, clock)


# --- Calls (PRC-08) -----------------------------------------------------------------------


def _day(now: datetime) -> str:
    return now.date().isoformat()  # the clock is in UTC (NFR-14)


def usage_today(session: Session, row: PriceProvider, clock: Clock) -> ProviderUsage:
    usage = session.get(ProviderUsage, (row.id, _day(clock.now())))
    if usage is None:
        usage = ProviderUsage(
            provider_id=row.id, day=_day(clock.now()), calls=0, quota_exhausted=False
        )
        session.add(usage)
        session.flush()
    return usage


def can_call(session: Session, row: PriceProvider, clock: Clock) -> bool:
    """PRC-08: not after the daily limit or after the provider said its quota is used up."""
    usage = usage_today(session, row, clock)
    limit = row.daily_call_limit
    return not usage.quota_exhausted and (limit is None or usage.calls < limit)


@contextmanager
def counted_client(session: Session, row: PriceProvider, clock: Clock) -> Iterator[httpx2.Client]:
    """An HTTP client that counts every request of the provider for today and refuses
    requests beyond the limit before anything is sent (PRC-08)."""
    name = NAMES[Provider(row.provider)]

    def before(request: httpx2.Request) -> None:
        if not can_call(session, row, clock):
            raise PriceError(ErrorKind.QUOTA, msg("price_provider_quota", provider=name))
        usage_today(session, row, clock).calls += 1

    def after(response: httpx2.Response) -> None:
        if response.status_code in (402, 429):
            usage_today(session, row, clock).quota_exhausted = True

    with httpx2.Client(event_hooks={"request": [before], "response": [after]}) as client:
        yield client


def config_for(row: PriceProvider, keys: KeyBox) -> ProviderConfig:
    key = keys.decrypt(row.api_key_encrypted) if row.api_key_encrypted else None
    return ProviderConfig(Provider(row.provider), key)


@dataclass(frozen=True)
class ConnectionResult:
    ok: bool
    message: Message


def test_connection(
    session: Session,
    actor: Investor,
    clock: Clock,
    keys: KeyBox,
    adapters: AdapterFactory,
    provider_id: int,
) -> ConnectionResult:
    """PRC-01: one request with the provider's settings; also for the built-in source."""
    require_admin(actor)
    row = get_provider(session, provider_id)
    name = NAMES[Provider(row.provider)]
    try:
        config = config_for(row, keys)
    except ConflictError as e:
        return ConnectionResult(False, e.message)
    try:
        with counted_client(session, row, clock) as client:
            adapters(config, client).check()
    except PriceError as e:
        return ConnectionResult(False, e.message)
    except Exception as e:
        log.exception("Connection test of price provider %s failed", provider_id)
        text = f"{type(e).__name__}: {e}"
        if config.api_key:
            text = text.replace(config.api_key, "***")
        return ConnectionResult(False, msg("test_failed_unexpectedly", detail=text[:300]))
    return ConnectionResult(True, msg("price_connection_ok", provider=name))
