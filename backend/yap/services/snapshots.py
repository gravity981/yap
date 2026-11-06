"""Snapshots and their comparison with the policy (CMP-01 to CMP-10)."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from yap.db.models import (
    Asset,
    Investor,
    Portfolio,
    Snapshot,
    SnapshotValue,
)
from yap.domain.bands import Band, BandStatus, allocation_pct
from yap.domain.types import AssetType
from yap.messages import Message, msg
from yap.services.assets import get_or_create_asset
from yap.services.common import (
    Clock,
    ConflictError,
    NotFoundError,
    ValidationError,
    get_owned,
    require_investor,
)
from yap.services.policies import get_policy
from yap.services.price_update import AutoPrice, PriceInfo, price_info
from yap.services.versioning import active_version


@dataclass(frozen=True)
class ValueSpec:
    """One entered position (CMP-01): its units and either the price or the value; without
    both, the price of the previous snapshot. Without units, only the value is known (rows
    from before price tracking, CMP-10). Name and type are only needed for tickers not yet
    known (IMP-08)."""

    ticker: str
    value: Decimal | None = None
    name: str | None = None
    type: AssetType | str | None = None
    units: Decimal | None = None
    price: Decimal | None = None
    # An auto price to use instead of the current one, e.g. the input price of a rebalance
    auto: AutoPrice | None = None


SOURCES = ("manual", "import", "rebalance")
CENT = Decimal("0.01")
MANUAL, AUTO = "manual", "auto"


def money(amount: Decimal) -> Decimal:
    """A value rounded to 0.01 (CMP-01, NFR-04)."""
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class _Row:
    units: Decimal | None
    price: Decimal | None
    value: Decimal
    price_kind: str | None
    auto: AutoPrice | None = None


def _row(
    spec: ValueSpec,
    asset: Asset,
    previous_price: Decimal | None,
    require_units: bool,
    path: str,
    auto: AutoPrice | None = None,
) -> _Row:
    """CMP-01: value = units x price, rounded to 0.01; or price = value / units. Without
    price and value, the auto price of the position's price source, otherwise the price last
    entered. Signs are checked before (_sign_problems)."""
    ticker = asset.ticker
    if asset.type == AssetType.CASH_BUFFER:
        # Only an amount: units = value, price 1
        amount = spec.value if spec.value is not None else spec.units
        if amount is None:
            raise ValidationError.single(msg("position_units_or_value"), f"{path}.value")
        amount = money(amount)
        return _Row(amount, Decimal(1), amount, MANUAL)
    if spec.units is None:
        if require_units or spec.value is None:
            raise ValidationError.single(msg("units_required", ticker=ticker), f"{path}.units")
        return _Row(None, None, spec.value, None)
    units = spec.units
    if spec.price is not None:
        return _Row(units, spec.price, money(units * spec.price), MANUAL)
    if spec.value is not None:
        if units == 0:
            if spec.value != 0:
                raise ValidationError.single(msg("value_without_units"), f"{path}.value")
            return _Row(units, previous_price or Decimal(0), Decimal(0), MANUAL)
        return _Row(units, spec.value / units, money(spec.value), MANUAL)
    if auto is not None:
        return _Row(units, auto.price, money(units * auto.price), AUTO, auto)
    if units == 0:
        return _Row(units, previous_price or Decimal(0), Decimal(0), MANUAL)
    if previous_price is None:
        raise ValidationError.single(msg("price_required", ticker=ticker), f"{path}.price")
    return _Row(units, previous_price, money(units * previous_price), MANUAL)


def _sign_problems(spec: ValueSpec, path: str) -> list[tuple[str, Message]]:
    problems: list[tuple[str, Message]] = []
    for field, amount, code in (
        ("units", spec.units, "units_min"),
        ("price", spec.price, "price_min"),
        ("value", spec.value, "value_min"),
    ):
        if amount is not None and amount < 0:
            problems.append((f"{path}.{field}", msg(code)))
    return problems


def previous_prices(session: Session, portfolio: Portfolio) -> dict[int, Decimal]:
    """CMP-01: the price of each position in the portfolio's latest snapshot that has one
    (the price of a manual position is the one last entered, spec 4.1)."""
    prices: dict[int, Decimal] = {}
    for snapshot in session.scalars(
        select(Snapshot)
        .where(Snapshot.portfolio_id == portfolio.id)
        .order_by(Snapshot.taken_at.desc(), Snapshot.id.desc())
    ):
        for v in snapshot.values:
            if v.price is not None:
                prices.setdefault(v.asset_id, v.price)
    return prices


def create_snapshot(
    session: Session,
    actor: Investor,
    clock: Clock,
    portfolio_id: int,
    values: list[ValueSpec],
    *,
    source: str = "manual",
    corrects_snapshot_id: int | None = None,
    path: str = "values",
    require_units: bool = False,
) -> Snapshot:
    """Saves the positions now and ties the snapshot to the version active now (CMP-01,
    CMP-03). With `require_units`, every position except the cash buffer needs its units;
    otherwise a position may have only a value (imports of older files, CMP-10)."""
    if source not in SOURCES:
        raise ValueError(f"Unknown snapshot source {source}")
    portfolio = get_owned(session, Portfolio, portfolio_id, actor)
    problems: list[tuple[str, Message]] = []
    seen: set[str] = set()
    for i, v in enumerate(values):
        ticker = v.ticker.strip().upper()
        if ticker in seen:
            problems.append((f"{path}[{i}].ticker", msg("ticker_duplicate", ticker=ticker)))
        seen.add(ticker)
        problems.extend(_sign_problems(v, f"{path}[{i}]"))
    if problems:
        raise ValidationError(problems)
    if corrects_snapshot_id is not None:
        corrected = session.get(Snapshot, corrects_snapshot_id)
        if corrected is None or corrected.portfolio_id != portfolio.id:
            raise NotFoundError(msg("snapshot_not_found", id=corrects_snapshot_id))

    now = clock.now()
    version = active_version(portfolio.policy, now)
    if version is None:  # cannot happen while PTF-02 holds
        raise ConflictError(msg("policy_no_active_version", name=portfolio.policy.name))
    assets = [
        get_or_create_asset(session, v.ticker, v.name, v.type, f"{path}[{i}]")
        for i, v in enumerate(values)
    ]
    prices = previous_prices(session, portfolio)
    rows: list[_Row] = []
    for i, (v, asset) in enumerate(zip(values, assets, strict=True)):
        auto = v.auto or price_info(session, actor, asset, portfolio.currency).auto
        try:
            rows.append(_row(v, asset, prices.get(asset.id), require_units, f"{path}[{i}]", auto))
        except ValidationError as err:
            problems.extend(err.problems)
    if problems:
        raise ValidationError(problems)
    snapshot = Snapshot(
        portfolio_id=portfolio.id,
        policy_version_id=version.id,
        taken_at=now,
        source=source,
        corrects_snapshot_id=corrects_snapshot_id,
    )
    session.add(snapshot)
    session.flush()
    session.add_all(
        SnapshotValue(
            snapshot_id=snapshot.id,
            asset_id=asset.id,
            units=row.units,
            price=row.price,
            value=row.value,
            price_kind=row.price_kind,
            listing_id=row.auto.listing.id if row.auto else None,
            listing_price=row.auto.listing_price if row.auto else None,
            listing_currency=row.auto.listing.quote_currency if row.auto else None,
            price_date=row.auto.price_date if row.auto else None,
            fx_rate=row.auto.fx_rate if row.auto else None,
        )
        for row, asset in zip(rows, assets, strict=True)
    )
    session.flush()
    session.refresh(snapshot)
    return snapshot


def get_snapshot(session: Session, actor: Investor, snapshot_id: int) -> Snapshot:
    require_investor(actor)
    snapshot = session.get(Snapshot, snapshot_id)
    if snapshot is None:
        raise NotFoundError(msg("snapshot_not_found", id=snapshot_id))
    get_owned(session, Portfolio, snapshot.portfolio_id, actor)
    return snapshot


def list_snapshots(session: Session, actor: Investor, portfolio_id: int) -> list[Snapshot]:
    """CMP-08: newest first."""
    portfolio = get_owned(session, Portfolio, portfolio_id, actor)
    return list(
        session.scalars(
            select(Snapshot)
            .where(Snapshot.portfolio_id == portfolio.id)
            .order_by(Snapshot.taken_at.desc(), Snapshot.id.desc())
        )
    )


def latest_snapshot(session: Session, actor: Investor, portfolio_id: int) -> Snapshot | None:
    snapshots = list_snapshots(session, actor, portfolio_id)
    return snapshots[0] if snapshots else None


@dataclass(frozen=True)
class PrefillRow:
    ticker: str
    name: str
    type: str
    units: Decimal | None  # None: unknown (no previous snapshot, or a row without units)
    price: Decimal | None  # the auto price, or the price last entered (CMP-01)
    value: Decimal  # of the previous snapshot
    in_policy: bool
    source: PriceInfo  # the price source and its auto price or notice (PRC-09, PRC-11)


def prefill(session: Session, actor: Investor, clock: Clock, portfolio_id: int) -> list[PrefillRow]:
    """CMP-01: positions of the active version and the other positions of the previous
    snapshot; units from the previous snapshot, the price last entered for each position."""
    portfolio = get_owned(session, Portfolio, portfolio_id, actor)
    version = active_version(get_policy(session, actor, portfolio.policy_id), clock.now())
    previous = latest_snapshot(session, actor, portfolio_id)
    previous_values = {v.asset.ticker: v for v in previous.values} if previous else {}
    prices = previous_prices(session, portfolio)

    def row(asset: Asset, prev: SnapshotValue | None, in_policy: bool) -> PrefillRow:
        info = price_info(session, actor, asset, portfolio.currency)
        return PrefillRow(
            asset.ticker,
            asset.name,
            asset.type,
            prev.units if prev else Decimal(0),
            info.auto.price if info.auto else prices.get(asset.id),
            prev.value if prev else Decimal(0),
            in_policy,
            info,
        )

    rows: list[PrefillRow] = []
    policy_tickers: set[str] = set()
    for p in version.positions if version else []:
        policy_tickers.add(p.asset.ticker)
        rows.append(row(p.asset, previous_values.get(p.asset.ticker), True))
    rows.extend(
        row(v.asset, v, False) for t, v in previous_values.items() if t not in policy_tickers
    )
    return rows


@dataclass(frozen=True)
class ComparisonRow:
    ticker: str
    name: str
    type: str
    units: Decimal | None  # None: not in the snapshot, or a row without units (CMP-10)
    price: Decimal | None
    price_kind: str | None
    held: SnapshotValue | None  # the stored row with where its price came from (CMP-10)
    value: Decimal
    allocation_pct: Decimal
    band: Band | None
    exit: bool
    status: BandStatus

    @property
    def deviation_pct(self) -> Decimal | None:
        """Allocation minus target in percentage points (CMP-05)."""
        return None if self.band is None else self.allocation_pct - self.band.target_pct


@dataclass(frozen=True)
class Comparison:
    snapshot: Snapshot
    total_value: Decimal
    rows: list[ComparisonRow]


def compare(snapshot: Snapshot) -> Comparison:
    """CMP-02, CMP-05: always against the snapshot's own policy version (CMP-03, CMP-04)."""
    values = {v.asset.ticker: v for v in snapshot.values}
    total = sum((v.value for v in snapshot.values), Decimal(0))
    rows: list[ComparisonRow] = []
    policy_tickers: set[str] = set()
    for p in snapshot.policy_version.positions:
        policy_tickers.add(p.asset.ticker)
        held = values.get(p.asset.ticker)
        value = held.value if held else Decimal(0)
        band = Band(p.target_pct, p.buy_threshold_pct, p.sell_threshold_pct)
        alloc = allocation_pct(value, total)
        rows.append(
            ComparisonRow(
                p.asset.ticker,
                p.asset.name,
                p.asset.type,
                held.units if held else None,
                held.price if held else None,
                held.price_kind if held else None,
                held,
                value,
                alloc,
                band,
                p.exit,
                band.status(alloc),
            )
        )
    for ticker, v in values.items():
        if ticker in policy_tickers:
            continue
        rows.append(
            ComparisonRow(
                ticker,
                v.asset.name,
                v.asset.type,
                v.units,
                v.price,
                v.price_kind,
                v,
                v.value,
                allocation_pct(v.value, total),
                None,
                False,
                BandStatus.NOT_IN_POLICY,
            )
        )
    return Comparison(snapshot=snapshot, total_value=total, rows=rows)


@dataclass(frozen=True)
class PortfolioOverview:
    portfolio: Portfolio
    policy_name: str
    latest: Comparison | None


def overview(session: Session, actor: Investor) -> list[PortfolioOverview]:
    """CMP-09: all portfolios with their policy and the band status of the latest snapshot."""
    from yap.services.portfolios import list_portfolios

    result = []
    for portfolio in list_portfolios(session, actor):
        snapshot = latest_snapshot(session, actor, portfolio.id)
        result.append(
            PortfolioOverview(
                portfolio, portfolio.policy.name, compare(snapshot) if snapshot else None
            )
        )
    return result
