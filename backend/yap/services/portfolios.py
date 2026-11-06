"""Portfolios and their assignment to policies (PTF-01 to PTF-06)."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from yap.db.models import (
    Asset,
    Investor,
    Policy,
    Portfolio,
    PortfolioAssignment,
    PortfolioPosition,
    Snapshot,
)
from yap.domain.types import AssetType
from yap.messages import msg
from yap.services.assets import get_or_create_asset
from yap.services.common import (
    Clock,
    ConflictError,
    ValidationError,
    check_currency,
    get_owned,
    require_investor,
    require_text,
)
from yap.services.policies import get_policy
from yap.services.timeline import EventType, add_event
from yap.services.versioning import active_version


def _assignable_policy(session: Session, actor: Investor, policy_id: int, at: datetime) -> Policy:
    """PTF-02: an own, non-archived policy with an active version."""
    policy = get_policy(session, actor, policy_id)
    if policy.archived_at is not None:
        raise ConflictError(msg("policy_archived", name=policy.name))
    if active_version(policy, at) is None:
        raise ConflictError(msg("policy_not_active_yet", name=policy.name))
    return policy


def _validate_contribution(amount: Decimal) -> Decimal:
    if amount < 0:
        raise ValidationError.single(msg("contribution_min"), "default_contribution")
    return amount


def create_portfolio(
    session: Session,
    actor: Investor,
    clock: Clock,
    *,
    name: str,
    policy_id: int,
    default_contribution: Decimal = Decimal(0),
    precise_amounts: bool = False,
    currency: str | None = None,
) -> Portfolio:
    """A portfolio is created together with its first assignment (PTF-01, PTF-02). Its
    currency defaults to the investor's base currency (PTF-03, USR-06)."""
    require_investor(actor)
    name = require_text(name, "name", msg("name_required"))
    currency = check_currency(currency or actor.base_currency or "", "currency")
    if session.scalar(
        select(Portfolio).where(Portfolio.owner_id == actor.id, Portfolio.name == name)
    ):
        raise ConflictError(msg("portfolio_name_taken", name=name))
    now = clock.now()
    policy = _assignable_policy(session, actor, policy_id, now)
    portfolio = Portfolio(
        owner_id=actor.id,
        policy_id=policy.id,
        name=name,
        currency=currency,
        default_contribution=_validate_contribution(default_contribution),
        precise_amounts=precise_amounts,
        created_at=now,
    )
    session.add(portfolio)
    session.flush()
    _record_assignment(session, portfolio, policy, now, created=True)
    session.refresh(portfolio)
    return portfolio


def reassign_portfolio(
    session: Session, actor: Investor, clock: Clock, portfolio_id: int, policy_id: int
) -> Portfolio:
    """PTF-04: takes effect now; earlier snapshots keep their policy version."""
    portfolio = get_owned(session, Portfolio, portfolio_id, actor)
    now = clock.now()
    policy = _assignable_policy(session, actor, policy_id, now)
    if policy.id == portfolio.policy_id:
        raise ConflictError(
            msg("portfolio_already_follows", portfolio=portfolio.name, policy=policy.name)
        )
    portfolio.policy_id = policy.id
    _record_assignment(session, portfolio, policy, now, created=False)
    session.refresh(portfolio)
    return portfolio


def _record_assignment(
    session: Session, portfolio: Portfolio, policy: Policy, now: datetime, *, created: bool
) -> None:
    session.add(PortfolioAssignment(portfolio_id=portfolio.id, policy_id=policy.id, valid_from=now))
    version = active_version(policy, now)
    assert version is not None
    verb = "created with" if created else "reassigned to"
    add_event(
        session,
        portfolio.owner_id,
        now,
        EventType.PORTFOLIO_ASSIGNED,
        f"Portfolio {portfolio.name} {verb} policy {policy.name} ({version.label})",
        {
            "portfolio": portfolio.name,
            "policy": policy.name,
            "version": version.label,
            "created": created,
        },
        portfolio_id=portfolio.id,
        policy_version_id=version.id,
    )
    session.flush()


def has_snapshots(session: Session, portfolio: Portfolio) -> bool:
    return bool(session.scalar(select(exists().where(Snapshot.portfolio_id == portfolio.id))))


def update_settings(
    session: Session,
    actor: Investor,
    portfolio_id: int,
    *,
    default_contribution: Decimal,
    precise_amounts: bool,
    currency: str | None = None,
) -> Portfolio:
    """PTF-03: the currency can only change while the portfolio has no snapshots."""
    portfolio = get_owned(session, Portfolio, portfolio_id, actor)
    if currency is not None:
        currency = check_currency(currency, "currency")
        if currency != portfolio.currency and has_snapshots(session, portfolio):
            raise ConflictError(msg("portfolio_currency_locked"))
        portfolio.currency = currency
    portfolio.default_contribution = _validate_contribution(default_contribution)
    portfolio.precise_amounts = precise_amounts
    return portfolio


@dataclass(frozen=True)
class PositionSettings:
    """PTF-03: an empty broker removes it; whole_units None means the default by type."""

    broker: str | None = None
    whole_units: bool | None = None


def set_positions(
    session: Session, actor: Investor, portfolio_id: int, positions: dict[str, PositionSettings]
) -> Portfolio:
    """PTF-03: broker and whole units per position (by ticker). An entry without broker and
    whole-units setting is removed."""
    portfolio = get_owned(session, Portfolio, portfolio_id, actor)
    existing = {p.asset_id: p for p in portfolio.positions}
    for ticker, settings in positions.items():
        asset = get_or_create_asset(session, ticker, None, None, f"positions.{ticker}")
        broker = (settings.broker or "").strip() or None
        whole_units = None if asset.type == AssetType.CASH_BUFFER else settings.whole_units
        entry = existing.get(asset.id)
        if broker is None and whole_units is None:
            if entry is not None:
                portfolio.positions.remove(entry)
        elif entry is None:
            portfolio.positions.append(
                PortfolioPosition(asset_id=asset.id, broker=broker, whole_units=whole_units)
            )
        else:
            entry.broker = broker
            entry.whole_units = whole_units
    session.flush()
    return portfolio


def _position(portfolio: Portfolio, asset_id: int) -> PortfolioPosition | None:
    return next((p for p in portfolio.positions if p.asset_id == asset_id), None)


def broker_for(portfolio: Portfolio, asset_id: int) -> str | None:
    entry = _position(portfolio, asset_id)
    return entry.broker if entry else None


def default_whole_units(asset_type: str) -> bool | None:
    """PTF-03: whole units for ETFs and stocks, fractional for crypto; none for the cash
    buffer, which has only an amount."""
    if asset_type == AssetType.CASH_BUFFER:
        return None
    return asset_type != AssetType.CRYPTO


def whole_units_for(portfolio: Portfolio, asset: Asset) -> bool | None:
    entry = _position(portfolio, asset.id)
    if entry is not None and entry.whole_units is not None:
        return entry.whole_units
    return default_whole_units(asset.type)


def archive_portfolio(
    session: Session, actor: Investor, clock: Clock, portfolio_id: int
) -> Portfolio:
    """PTF-06: snapshots and rebalances stay in the history."""
    portfolio = get_owned(session, Portfolio, portfolio_id, actor)
    if portfolio.archived_at is None:
        portfolio.archived_at = clock.now()
    return portfolio


def list_portfolios(session: Session, actor: Investor) -> list[Portfolio]:
    require_investor(actor)
    return list(
        session.scalars(
            select(Portfolio).where(Portfolio.owner_id == actor.id).order_by(Portfolio.name)
        )
    )
