"""Portfolios (PTF-01 to PTF-06), snapshots and comparison (CMP-01 to CMP-09),
current-structure import (IMP-03)."""

from fastapi import APIRouter

from yap.api.deps import AppClock, CurrentUser, DbSession, RawBody
from yap.api.schemas import (
    AssignmentOut,
    AutoPriceOut,
    CurrentStructurePreviewOut,
    NewPortfolio,
    NewSnapshot,
    PortfolioOut,
    PortfolioSettings,
    PortfolioSummary,
    PositionSettingsIn,
    PositionSettingsOut,
    PrefillRowOut,
    Reassignment,
    SnapshotListItem,
    SnapshotOut,
    snapshot_list_item,
)
from yap.db.models import Asset, Investor, PolicyVersion, Portfolio
from yap.imports import importer
from yap.services import portfolios, reviews, snapshots
from yap.services.common import Clock, get_owned
from yap.services.portfolios import PositionSettings
from yap.services.snapshots import ValueSpec
from yap.services.versioning import active_version

router = APIRouter(tags=["portfolios"])


def _latest(session: DbSession, user: Investor, portfolio: Portfolio) -> SnapshotOut | None:
    latest = snapshots.latest_snapshot(session, user, portfolio.id)
    return SnapshotOut.of(snapshots.compare(latest)) if latest else None


def _summary(
    session: DbSession, user: Investor, clock: Clock, portfolio: Portfolio
) -> PortfolioSummary:
    # PTF-07: the semaphore of the active version of the portfolio's policy
    version = active_version(portfolio.policy, clock.now())
    latest = reviews.current_review(version) if version is not None else None
    semaphore = reviews.review_semaphore(latest)
    return PortfolioSummary(
        policy_semaphore=semaphore.value if semaphore else None,
        policy_semaphore_reason=latest.verdict_reason if latest and semaphore else None,
        id=portfolio.id,
        name=portfolio.name,
        currency=portfolio.currency,
        policy_id=portfolio.policy_id,
        policy_name=portfolio.policy.name,
        archived_at=portfolio.archived_at,
        latest_snapshot=_latest(session, user, portfolio),
    )


def _positions(
    session: DbSession, user: Investor, portfolio: Portfolio, version: PolicyVersion | None
) -> list[PositionSettingsOut]:
    """PTF-03: the positions of the active version and the latest snapshot, then those
    that only have settings."""
    latest = snapshots.latest_snapshot(session, user, portfolio.id)
    assets: dict[int, Asset] = {}
    for p in version.positions if version else []:
        assets.setdefault(p.asset.id, p.asset)
    for v in latest.values if latest else []:
        assets.setdefault(v.asset.id, v.asset)
    for entry in portfolio.positions:
        assets.setdefault(entry.asset.id, entry.asset)
    return [
        PositionSettingsOut(
            ticker=asset.ticker,
            name=asset.name,
            type=asset.type,
            broker=portfolios.broker_for(portfolio, asset.id),
            whole_units=portfolios.whole_units_for(portfolio, asset),
        )
        for asset in assets.values()
    ]


def _portfolio(
    session: DbSession, user: Investor, clock: Clock, portfolio: Portfolio
) -> PortfolioOut:
    version = active_version(portfolio.policy, clock.now())
    return PortfolioOut(
        **_summary(session, user, clock, portfolio).model_dump(),
        default_contribution=portfolio.default_contribution,
        precise_amounts=portfolio.precise_amounts,
        currency_locked=portfolios.has_snapshots(session, portfolio),
        active_version_label=version.label if version else None,
        brokers={p.asset.ticker: p.broker for p in portfolio.positions if p.broker},
        positions=_positions(session, user, portfolio, version),
        assignments=[
            AssignmentOut(policy_id=a.policy_id, policy_name=a.policy.name, valid_from=a.valid_from)
            for a in portfolio.assignments
        ],
    )


@router.get("/portfolios")
def list_portfolios(
    session: DbSession, clock: AppClock, user: CurrentUser
) -> list[PortfolioSummary]:
    """CMP-09: overview of all portfolios."""
    return [_summary(session, user, clock, p) for p in portfolios.list_portfolios(session, user)]


@router.post("/portfolios", status_code=201)
def create_portfolio(
    body: NewPortfolio, session: DbSession, clock: AppClock, user: CurrentUser
) -> PortfolioOut:
    portfolio = portfolios.create_portfolio(
        session,
        user,
        clock,
        name=body.name,
        policy_id=body.policy_id,
        default_contribution=body.default_contribution,
        precise_amounts=body.precise_amounts,
        currency=body.currency,
    )
    return _portfolio(session, user, clock, portfolio)


@router.get("/portfolios/{portfolio_id}")
def get_portfolio(
    portfolio_id: int, session: DbSession, clock: AppClock, user: CurrentUser
) -> PortfolioOut:
    return _portfolio(session, user, clock, get_owned(session, Portfolio, portfolio_id, user))


@router.put("/portfolios/{portfolio_id}/settings")
def update_settings(
    portfolio_id: int,
    body: PortfolioSettings,
    session: DbSession,
    clock: AppClock,
    user: CurrentUser,
) -> PortfolioOut:
    portfolio = portfolios.update_settings(
        session,
        user,
        portfolio_id,
        default_contribution=body.default_contribution,
        precise_amounts=body.precise_amounts,
        currency=body.currency,
    )
    return _portfolio(session, user, clock, portfolio)


@router.put("/portfolios/{portfolio_id}/positions")
def set_positions(
    portfolio_id: int,
    body: dict[str, PositionSettingsIn],
    session: DbSession,
    clock: AppClock,
    user: CurrentUser,
) -> PortfolioOut:
    """PTF-03: broker and whole units per position, by ticker."""
    portfolio = portfolios.set_positions(
        session,
        user,
        portfolio_id,
        {t: PositionSettings(p.broker, p.whole_units) for t, p in body.items()},
    )
    return _portfolio(session, user, clock, portfolio)


@router.post("/portfolios/{portfolio_id}/reassign")
def reassign(
    portfolio_id: int, body: Reassignment, session: DbSession, clock: AppClock, user: CurrentUser
) -> PortfolioOut:
    portfolio = portfolios.reassign_portfolio(session, user, clock, portfolio_id, body.policy_id)
    return _portfolio(session, user, clock, portfolio)


@router.post("/portfolios/{portfolio_id}/archive")
def archive(
    portfolio_id: int, session: DbSession, clock: AppClock, user: CurrentUser
) -> PortfolioOut:
    portfolio = portfolios.archive_portfolio(session, user, clock, portfolio_id)
    return _portfolio(session, user, clock, portfolio)


# --- Snapshots ----------------------------------------------------------------


@router.get("/portfolios/{portfolio_id}/prefill")
def prefill(
    portfolio_id: int, session: DbSession, clock: AppClock, user: CurrentUser
) -> list[PrefillRowOut]:
    return [
        PrefillRowOut(
            ticker=r.ticker,
            name=r.name,
            type=r.type,
            units=r.units,
            price=r.price,
            value=r.value,
            in_policy=r.in_policy,
            price_kind=r.source.kind,
            auto=AutoPriceOut.of(r.source.auto) if r.source.auto else None,
            notice=r.source.notice,
            listing_symbol=r.source.listing.symbol if r.source.listing else None,
        )
        for r in snapshots.prefill(session, user, clock, portfolio_id)
    ]


@router.get("/portfolios/{portfolio_id}/snapshots")
def list_snapshots(
    portfolio_id: int, session: DbSession, user: CurrentUser
) -> list[SnapshotListItem]:
    return [
        snapshot_list_item(snapshots.compare(s))
        for s in snapshots.list_snapshots(session, user, portfolio_id)
    ]


@router.post("/portfolios/{portfolio_id}/snapshots", status_code=201)
def create_snapshot(
    portfolio_id: int, body: NewSnapshot, session: DbSession, clock: AppClock, user: CurrentUser
) -> SnapshotOut:
    snapshot = snapshots.create_snapshot(
        session,
        user,
        clock,
        portfolio_id,
        [ValueSpec(v.ticker, v.value, v.name, v.type, v.units, v.price) for v in body.values],
        corrects_snapshot_id=body.corrects_snapshot_id,
        require_units=True,
    )
    return SnapshotOut.of(snapshots.compare(snapshot))


@router.get("/snapshots/{snapshot_id}")
def get_snapshot(snapshot_id: int, session: DbSession, user: CurrentUser) -> SnapshotOut:
    return SnapshotOut.of(snapshots.compare(snapshots.get_snapshot(session, user, snapshot_id)))


# --- Import (IMP-03, IMP-07) --------------------------------------------------


@router.post("/portfolios/{portfolio_id}/import", status_code=201)
def import_current_structure(
    portfolio_id: int, body: RawBody, session: DbSession, clock: AppClock, user: CurrentUser
) -> SnapshotOut:
    snapshot = importer.import_current_structure(session, user, clock, body, portfolio_id)
    return SnapshotOut.of(snapshots.compare(snapshot))


@router.post("/portfolios/{portfolio_id}/import/preview")
def preview_current_structure(
    portfolio_id: int, body: RawBody, session: DbSession, user: CurrentUser
) -> CurrentStructurePreviewOut:
    preview = importer.preview_current_structure(session, user, body, portfolio_id)
    return CurrentStructurePreviewOut(values=preview.values, new_tickers=preview.new_tickers)
