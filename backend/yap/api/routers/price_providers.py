"""Price providers and the built-in exchange rate source for admins (PRC-01, PRC-08,
PRC-10)."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from yap.api.deps import (
    AppClock,
    AppKeys,
    CurrentAdmin,
    DbSession,
    PriceAdapters,
)
from yap.api.routers.admin import ConnectionTest
from yap.db.models import PriceProvider
from yap.prices import Provider
from yap.prices.base import KEY_POSSIBLE, KEY_REQUIRED, NAMES
from yap.services import price_providers, price_update
from yap.services.common import Clock
from yap.services.price_providers import ProviderSpec

router = APIRouter(prefix="/admin/price-providers", tags=["admin"])


class PriceProviderSettings(BaseModel):
    """The stored key itself is never returned (REV-15)."""

    id: int
    provider: str
    name: str
    built_in: bool  # the exchange rate source: listed, not changeable (PRC-11)
    key_possible: bool
    key_required: bool
    api_key_last4: str | None
    daily_call_limit: int | None
    enabled: bool
    calls_today: int  # PRC-10, UTC day
    quota_exhausted: bool  # the provider said so today (PRC-08)
    listings_in_use: int  # PRC-10
    last_run: dict[str, int] | None  # PRC-10: updated, skipped, failed, not_found
    updated_at: datetime

    @classmethod
    def of(cls, session: DbSession, row: PriceProvider, clock: Clock) -> PriceProviderSettings:
        provider = Provider(row.provider)
        usage = price_providers.usage_today(session, row, clock)
        last = price_update.last_run(session)
        return cls(
            id=row.id,
            provider=row.provider,
            name=NAMES[provider],
            built_in=row.built_in,
            key_possible=provider in KEY_POSSIBLE,
            key_required=provider in KEY_REQUIRED,
            api_key_last4=row.api_key_last4,
            daily_call_limit=row.daily_call_limit,
            enabled=row.enabled,
            calls_today=usage.calls,
            quota_exhausted=usage.quota_exhausted,
            listings_in_use=price_update.listings_in_use_count(session, row),
            last_run=(last.result or {}).get(NAMES[provider]) if last else None,
            updated_at=row.updated_at,
        )


class AddableProvider(BaseModel):
    provider: str
    name: str
    key_possible: bool
    key_required: bool


class PriceProviderList(BaseModel):
    providers: list[PriceProviderSettings]
    addable: list[AddableProvider]  # each provider can be added once
    keys_available: bool  # False: APP_SECRET_KEY is missing, keys cannot be saved


class PriceProviderIn(BaseModel):
    provider: str
    daily_call_limit: int | None = None  # null: no limit
    enabled: bool = True
    api_key: str | None = None  # replaces the stored key when given

    def spec(self) -> ProviderSpec:
        return ProviderSpec(self.provider, self.daily_call_limit, self.enabled, self.api_key)


@router.get("")
def list_providers(
    session: DbSession, clock: AppClock, keys: AppKeys, admin: CurrentAdmin
) -> PriceProviderList:
    return PriceProviderList(
        providers=[
            PriceProviderSettings.of(session, p, clock)
            for p in price_providers.list_providers(session, admin)
        ],
        addable=[
            AddableProvider(
                provider=p.value,
                name=NAMES[p],
                key_possible=p in KEY_POSSIBLE,
                key_required=p in KEY_REQUIRED,
            )
            for p in price_providers.addable_providers(session, admin)
        ],
        keys_available=keys.available,
    )


@router.post("", status_code=201)
def create_provider(
    body: PriceProviderIn, session: DbSession, clock: AppClock, keys: AppKeys, admin: CurrentAdmin
) -> PriceProviderSettings:
    row = price_providers.create_provider(session, admin, clock, keys, body.spec())
    return PriceProviderSettings.of(session, row, clock)


@router.put("/{provider_id}")
def update_provider(
    provider_id: int,
    body: PriceProviderIn,
    session: DbSession,
    clock: AppClock,
    keys: AppKeys,
    admin: CurrentAdmin,
) -> PriceProviderSettings:
    row = price_providers.update_provider(session, admin, clock, keys, provider_id, body.spec())
    return PriceProviderSettings.of(session, row, clock)


@router.post("/{provider_id}/archive", status_code=204)
def archive_provider(
    provider_id: int, session: DbSession, clock: AppClock, admin: CurrentAdmin
) -> None:
    """PRC-01: archived instead of deleted"""
    price_providers.archive_provider(session, admin, clock, provider_id)


@router.post("/{provider_id}/test")
def test_connection(
    provider_id: int,
    session: DbSession,
    clock: AppClock,
    keys: AppKeys,
    adapters: PriceAdapters,
    admin: CurrentAdmin,
) -> ConnectionTest:
    """PRC-01: one request to the provider with its settings."""
    result = price_providers.test_connection(session, admin, clock, keys, adapters, provider_id)
    return ConnectionTest(
        ok=result.ok,
        message=str(result.message),
        code=result.message.code,
        params=result.message.params,
    )


# --- Schedule and runs of the price update (PRC-07, PRC-10) -------------------------------


class PriceUpdateRunOut(BaseModel):
    trigger: str  # schedule | cli
    started_at: datetime
    finished_at: datetime | None
    result: dict[str, dict[str, int]] | None


class PriceUpdateOut(BaseModel):
    time_of_day: str  # HH:MM in time_zone
    time_zone: str
    interval_hours: int
    intervals: list[int]
    next_run_at: datetime | None
    last_run: PriceUpdateRunOut | None


class PriceUpdateIn(BaseModel):
    time_of_day: str
    time_zone: str
    interval_hours: int


def _update_out(session: DbSession, clock: Clock) -> PriceUpdateOut:
    settings = price_update.get_settings(session)
    if settings.next_run_at is None:
        settings.next_run_at = price_update.next_run(settings, clock.now())
    last = price_update.last_run(session)
    return PriceUpdateOut(
        time_of_day=settings.time_of_day,
        time_zone=settings.time_zone,
        interval_hours=settings.interval_hours,
        intervals=list(price_update.INTERVALS),
        next_run_at=settings.next_run_at,
        last_run=PriceUpdateRunOut(
            trigger=last.trigger,
            started_at=last.started_at,
            finished_at=last.finished_at,
            result=last.result,
        )
        if last
        else None,
    )


update_router = APIRouter(prefix="/admin/price-update", tags=["admin"])


@update_router.get("")
def get_update(session: DbSession, clock: AppClock, admin: CurrentAdmin) -> PriceUpdateOut:
    return _update_out(session, clock)


@update_router.put("")
def set_update(
    body: PriceUpdateIn, session: DbSession, clock: AppClock, admin: CurrentAdmin
) -> PriceUpdateOut:
    """PRC-07: the time of day is read in the given time zone (USR-11, NFR-14)."""
    price_update.update_settings(
        session,
        admin,
        clock,
        time_of_day=body.time_of_day,
        time_zone=body.time_zone,
        interval_hours=body.interval_hours,
    )
    return _update_out(session, clock)
