"""Rebalancing a portfolio: preview, confirmation, simulation (RB-01 to RB-03, RB-16,
RB-17, RB-20, RB-24). The calculation itself is in domain/rebalancing.py."""

from dataclasses import dataclass, replace
from decimal import Decimal, localcontext
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from yap.db.models import (
    Investor,
    PolicyVersion,
    Portfolio,
    Rebalance,
    RebalanceAction,
    Snapshot,
    SnapshotValue,
)
from yap.domain.bands import Band
from yap.domain.rebalancing import (
    UNITS_PRECISION,
    AmountError,
    PositionInput,
    RebalanceResult,
    RebalancingError,
    rebalance,
    to_units,
)
from yap.domain.types import AssetType
from yap.messages import Message, msg
from yap.services import snapshots
from yap.services.assets import find_asset
from yap.services.common import (
    Clock,
    ConflictError,
    NotFoundError,
    ValidationError,
    get_owned,
)
from yap.services.portfolios import broker_for, whole_units_for
from yap.services.price_update import AutoPrice
from yap.services.snapshots import ValueSpec
from yap.services.timeline import EventType, add_event
from yap.services.versioning import active_version

MAX_SIMULATION_CYCLES = 120


@dataclass(frozen=True)
class Instruction:
    """One action of a rebalance (RB-11, RB-24); units None for positions without units."""

    phase: str  # 1A | 1B | 3
    ticker: str
    action: str
    broker: str | None
    amount: Decimal
    units: Decimal | None
    whole_units: bool | None


@dataclass(frozen=True)
class Plan:
    """A calculated rebalance; not stored until confirmed (RB-03)."""

    portfolio: Portfolio
    snapshot: Snapshot
    version: PolicyVersion
    contribution: Decimal
    withdrawal: Decimal
    result: RebalanceResult

    @property
    def actions(self) -> list[Instruction]:
        rows = []
        for r in self.result.positions:
            p = r.position
            whole = p.whole_units if p.has_units else None
            for phase, label, amount, units in (
                ("1A", r.phase1_action, r.buffer_buy, r.buffer_buy_units),
                ("1B", r.phase1_action, r.sell_amount, r.sell_units),
                ("3", r.phase3_action, r.buy_amount, r.buy_units),
                ("3", r.phase3_action, r.withdrawal_sell, r.withdrawal_sell_units),
            ):
                if amount > 0:
                    rows.append(
                        Instruction(phase, p.ticker, label.value, p.broker, amount, units, whole)
                    )
        return rows


def position_inputs(
    portfolio: Portfolio, snapshot: Snapshot, version: PolicyVersion
) -> list[PositionInput]:
    """Snapshot values, units and prices against the given policy version (RB-01, RB-24)."""
    values = {v.asset.ticker: v for v in snapshot.values}
    inputs: list[PositionInput] = []
    in_policy: set[str] = set()
    for p in version.positions:
        ticker = p.asset.ticker
        in_policy.add(ticker)
        held = values.get(ticker)
        inputs.append(
            PositionInput(
                ticker=ticker,
                name=p.asset.name,
                asset_type=AssetType(p.asset.type),
                value=held.value if held else Decimal(0),
                band=Band(p.target_pct, p.buy_threshold_pct, p.sell_threshold_pct),
                exit=p.exit,
                broker=broker_for(portfolio, p.asset_id),
                units=held.units if held else None,
                price=held.price if held else None,
                whole_units=whole_units_for(portfolio, p.asset),
            )
        )
    for ticker, v in values.items():
        if ticker not in in_policy:
            inputs.append(
                PositionInput(
                    ticker=ticker,
                    name=v.asset.name,
                    asset_type=AssetType(v.asset.type),
                    value=v.value,
                    broker=broker_for(portfolio, v.asset_id),
                    units=v.units,
                    price=v.price,
                    whole_units=whole_units_for(portfolio, v.asset),
                )
            )
    return inputs


def _calculate(
    inputs: list[PositionInput], contribution: Decimal, withdrawal: Decimal
) -> RebalanceResult:
    try:
        return to_units(rebalance(inputs, contribution, withdrawal))
    except RebalancingError as err:
        field = err.field if isinstance(err, AmountError) else ""
        raise ValidationError.single(err.message, field) from None


def plan(
    session: Session,
    actor: Investor,
    clock: Clock,
    portfolio_id: int,
    *,
    snapshot_id: int | None = None,
    contribution: Decimal | None = None,
    withdrawal: Decimal | None = None,
) -> Plan:
    """RB-01 to RB-03: instructions for the given or latest snapshot, active version now."""
    portfolio = get_owned(session, Portfolio, portfolio_id, actor)
    if snapshot_id is None:
        snapshot = snapshots.latest_snapshot(session, actor, portfolio.id)
        if snapshot is None:
            raise ConflictError(msg("rebalance_values_missing"))
    else:
        snapshot = snapshots.get_snapshot(session, actor, snapshot_id)
        if snapshot.portfolio_id != portfolio.id:
            raise NotFoundError(msg("rebalance_snapshot_not_found", id=snapshot_id))
    version = active_version(portfolio.policy, clock.now())
    assert version is not None  # a portfolio's policy always has an active version (PTF-02)
    amount = portfolio.default_contribution if contribution is None else contribution
    out = Decimal(0) if withdrawal is None else withdrawal
    result = _calculate(position_inputs(portfolio, snapshot, version), amount, out)
    return Plan(portfolio, snapshot, version, amount, out, result)


@dataclass(frozen=True)
class Executed:
    phase: str  # 1A | 1B | 3
    ticker: str
    amount: Decimal
    units: Decimal | None = None  # None: the calculated units (RB-16)


def confirm(
    session: Session,
    actor: Investor,
    clock: Clock,
    portfolio_id: int,
    *,
    snapshot_id: int,
    contribution: Decimal,
    withdrawal: Decimal = Decimal(0),
    policy_version_id: int,
    executed: list[Executed],
) -> Rebalance:
    """RB-16, RB-17: stores the rebalance with calculated and executed amounts, the
    resulting snapshot and a timeline event. The plan is recalculated here, so the
    stored instructions never come from the client."""
    p = plan(
        session,
        actor,
        clock,
        portfolio_id,
        snapshot_id=snapshot_id,
        contribution=contribution,
        withdrawal=withdrawal,
    )
    if p.version.id != policy_version_id:
        raise ConflictError(msg("rebalance_policy_changed"))

    calculated = {(i.phase, i.ticker): i for i in p.actions}
    amounts = {key: i.amount for key, i in calculated.items()}
    units = {key: i.units for key, i in calculated.items()}
    problems: list[tuple[str, Message]] = []
    for n, e in enumerate(executed):
        key = (e.phase, e.ticker.strip().upper())
        if key not in calculated:
            problems.append(
                (f"executed[{n}]", msg("rebalance_no_instruction", phase=e.phase, ticker=key[1]))
            )
            continue
        if e.amount < 0:
            problems.append((f"executed[{n}].amount", msg("rebalance_executed_negative")))
        else:
            amounts[key] = e.amount
        if e.units is not None and units[key] is not None:
            if e.units < 0:
                problems.append((f"executed[{n}].units", msg("rebalance_executed_negative")))
            else:
                units[key] = e.units
    if problems:
        raise ValidationError(problems)

    def done(phase: str, ticker: str) -> Decimal:
        return amounts.get((phase, ticker), Decimal(0))

    def done_units(phase: str, ticker: str) -> Decimal:
        return units.get((phase, ticker)) or Decimal(0)

    by_ticker = {r.position.ticker: r for r in p.result.positions}
    buffer = next((r for r in p.result.positions if r.position.is_cash_buffer), None)
    buffer_buys = sum((a for (phase, _), a in amounts.items() if phase == "1A"), Decimal(0))
    if buffer is not None and buffer_buys > buffer.position.value:
        problems.append(("executed", msg("rebalance_buffer_exceeded")))
    # Phase 3 is a buy, or a withdrawal sell (RB-22), never both for one position
    withdrawn = {t for t, r in by_ticker.items() if r.withdrawal_sell > 0}
    for phase, ticker in amounts:
        if phase == "1B" or (phase == "3" and ticker in withdrawn):
            position = by_ticker[ticker].position
            available = position.value + done("1A", ticker)
            units_held = (position.units or Decimal(0)) + done_units("1A", ticker)
            if phase == "3":
                available -= done("1B", ticker)
                units_held -= done_units("1B", ticker)
            too_many = position.has_units and done_units(phase, ticker) > units_held
            if done(phase, ticker) > available or too_many:
                problems.append(("executed", msg("rebalance_sell_exceeds", ticker=ticker)))
    if problems:
        raise ValidationError(problems)

    # RB-17: the resulting positions. With units: the input units +/- the executed units at
    # the input snapshot's price; otherwise the value +/- the executed amounts. Created
    # first: the rebalance row is append-only and references it.
    resulting: list[ValueSpec] = []
    input_rows = {v.asset.ticker: v for v in p.snapshot.values}
    for r in p.result.positions:
        position, ticker = r.position, r.position.ticker
        sign = -1 if ticker in withdrawn else 1
        if position.has_units:
            assert position.units is not None
            with localcontext() as context:  # no decimal of crypto units is lost
                context.prec = UNITS_PRECISION
                held = (
                    position.units
                    + done_units("1A", ticker)
                    - done_units("1B", ticker)
                    + sign * done_units("3", ticker)
                )
            if position.in_policy or held > 0:
                resulting.append(ValueSpec(ticker, units=held, **_same_price(input_rows, ticker)))
            continue
        value = position.value + done("1A", ticker) - done("1B", ticker) + sign * done("3", ticker)
        if position.is_cash_buffer:
            value -= buffer_buys
        if position.in_policy or value > 0:
            resulting.append(ValueSpec(ticker, value))
    result_snapshot = snapshots.create_snapshot(
        session, actor, clock, p.portfolio.id, resulting, source="rebalance"
    )

    now = clock.now()
    record = Rebalance(
        portfolio_id=p.portfolio.id,
        input_snapshot_id=p.snapshot.id,
        policy_version_id=p.version.id,
        contribution=p.contribution,
        withdrawal=p.withdrawal,
        precise_amounts=p.portfolio.precise_amounts,
        result_snapshot_id=result_snapshot.id,
        confirmed_at=now,
    )
    session.add(record)
    session.flush()
    for key, instruction in calculated.items():
        asset = find_asset(session, instruction.ticker)
        assert asset is not None
        session.add(
            RebalanceAction(
                rebalance_id=record.id,
                asset_id=asset.id,
                phase=instruction.phase,
                action=instruction.action,
                broker=instruction.broker,
                whole_units=instruction.whole_units,
                calculated_units=instruction.units,
                executed_units=units[key],
                calculated_amount=instruction.amount,
                executed_amount=amounts[key],
            )
        )

    sells = {(ph, t) for ph, t in amounts if ph == "1B" or (ph == "3" and t in withdrawn)}
    sold = sum((a for key, a in amounts.items() if key in sells), Decimal(0))
    bought = sum((a for key, a in amounts.items() if key not in sells), Decimal(0))
    fmt = ",.2f" if p.portfolio.precise_amounts else ",.0f"
    summary = f"{p.portfolio.name}: rebalanced, sold {sold:{fmt}}, bought {bought:{fmt}}"
    if p.withdrawal > 0:
        summary += f", withdrew {p.withdrawal:{fmt}}"
    add_event(
        session,
        actor.id,
        now,
        EventType.REBALANCE_CONFIRMED,
        summary,
        {
            "portfolio": p.portfolio.name,
            "sold": str(sold),
            "bought": str(bought),
            "withdrawal": str(p.withdrawal) if p.withdrawal > 0 else None,
            "precise": p.portfolio.precise_amounts,
        },
        portfolio_id=p.portfolio.id,
        policy_version_id=p.version.id,
        rebalance_id=record.id,
    )
    session.flush()
    session.refresh(record)
    return record


def _same_price(rows: dict[str, SnapshotValue], ticker: str) -> dict[str, Any]:
    """RB-17: the price of the input snapshot, an auto price with where it came from (CMP-10)."""
    row = rows.get(ticker)
    if row is not None and row.price_kind == "auto" and row.listing is not None:
        assert row.listing_price is not None and row.fx_rate is not None
        assert row.price is not None and row.price_date is not None
        auto = AutoPrice(row.listing, row.listing_price, row.fx_rate, row.price, row.price_date)
        return {"auto": auto}
    return {"price": row.price if row is not None else None}


def recalculate(session: Session, actor: Investor, rebalance_id: int) -> RebalanceResult:
    """The full result of a confirmed rebalance (RB-19), recalculated from its stored,
    immutable inputs. Brokers and whole-units settings are taken from the stored actions,
    as they were then; rebalances confirmed before units (RB-24) are recalculated without."""
    record = get_rebalance(session, actor, rebalance_id)
    portfolio = get_owned(session, Portfolio, record.portfolio_id, actor)
    snapshot = session.get(Snapshot, record.input_snapshot_id)
    version = session.get(PolicyVersion, record.policy_version_id)
    assert snapshot is not None and version is not None
    actions = list(
        session.scalars(select(RebalanceAction).where(RebalanceAction.rebalance_id == record.id))
    )
    brokers = {a.asset_id: a.broker for a in actions}
    whole_units = {a.asset_id: a.whole_units for a in actions if a.whole_units is not None}
    with_units = any(a.calculated_units is not None for a in actions)
    by_ticker = {v.asset.ticker: v.asset_id for v in snapshot.values}
    by_ticker.update({p.asset.ticker: p.asset_id for p in version.positions})
    inputs = []
    for p in position_inputs(portfolio, snapshot, version):
        asset_id = by_ticker[p.ticker]
        p = replace(p, broker=brokers.get(asset_id, p.broker))
        if not with_units:
            p = replace(p, units=None, price=None, whole_units=None)
        elif asset_id in whole_units:
            p = replace(p, whole_units=whole_units[asset_id])
        inputs.append(p)
    return _calculate(inputs, record.contribution, record.withdrawal)


def list_rebalances(session: Session, actor: Investor, portfolio_id: int) -> list[Rebalance]:
    portfolio = get_owned(session, Portfolio, portfolio_id, actor)
    return list(
        session.scalars(
            select(Rebalance)
            .where(Rebalance.portfolio_id == portfolio.id)
            .order_by(Rebalance.confirmed_at.desc(), Rebalance.id.desc())
        )
    )


def get_rebalance(session: Session, actor: Investor, rebalance_id: int) -> Rebalance:
    record = session.get(Rebalance, rebalance_id)
    if record is None:
        raise NotFoundError(msg("rebalance_not_found", id=rebalance_id))
    get_owned(session, Portfolio, record.portfolio_id, actor)
    return record


def simulate(
    session: Session,
    actor: Investor,
    clock: Clock,
    portfolio_id: int,
    cycles: int,
    *,
    snapshot_id: int | None = None,
    contribution: Decimal | None = None,
    withdrawal: Decimal | None = None,
) -> list[RebalanceResult]:
    """RB-20: N cycles with the same contribution and withdrawal and unchanged prices;
    nothing stored."""
    if not 1 <= cycles <= MAX_SIMULATION_CYCLES:
        raise ValidationError.single(
            msg("rebalance_cycles_invalid", max=MAX_SIMULATION_CYCLES), "cycles"
        )
    first = plan(
        session,
        actor,
        clock,
        portfolio_id,
        snapshot_id=snapshot_id,
        contribution=contribution,
        withdrawal=withdrawal,
    )
    results = [first.result]
    for _ in range(cycles - 1):
        previous = results[-1]
        inputs = [
            replace(r.position, value=r.value_after_phase3, units=r.units_after)
            for r in previous.positions
            if r.position.in_policy
        ]
        results.append(_calculate(inputs, first.contribution, first.withdrawal))
    return results
