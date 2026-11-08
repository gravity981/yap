"""Rebalance preview, confirmation, history and simulation (RB-01 to RB-03, RB-11 to
RB-17, RB-20)."""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from yap.api.decimals import PlainDecimal
from yap.api.deps import AppClock, CurrentUser, DbSession
from yap.db.models import Asset, Rebalance, RebalanceAction
from yap.domain.rebalancing import PositionResult, RebalanceResult
from yap.services import rebalances
from yap.services.rebalances import Executed, Plan

router = APIRouter(tags=["rebalances"])


class PositionResultOut(BaseModel):
    """RB-11: one row per position, all phases."""

    ticker: str
    name: str
    type: str
    broker: str | None
    in_policy: bool
    exit: bool
    target_pct: PlainDecimal | None
    value_before: PlainDecimal
    allocation_before_pct: PlainDecimal
    buffer_buy: PlainDecimal
    buffer_deployed: PlainDecimal
    sell_amount: PlainDecimal
    phase1_action: str
    value_after_phase1: PlainDecimal
    allocation_after_phase1_pct: PlainDecimal
    buy_amount: PlainDecimal
    withdrawal_sell: PlainDecimal
    phase3_action: str
    value_after: PlainDecimal
    allocation_after_pct: PlainDecimal
    difference_to_target_pct: PlainDecimal | None
    # RB-24: null for positions without units (cash buffer, unknown units or price)
    units_before: PlainDecimal | None
    price: PlainDecimal | None
    whole_units: bool | None
    buffer_buy_units: PlainDecimal | None
    sell_units: PlainDecimal | None
    buy_units: PlainDecimal | None
    withdrawal_sell_units: PlainDecimal | None
    units_after: PlainDecimal | None

    @classmethod
    def of(cls, r: PositionResult) -> PositionResultOut:
        p = r.position
        return cls(
            ticker=p.ticker,
            name=p.name,
            type=p.asset_type.value,
            broker=p.broker,
            in_policy=p.in_policy,
            exit=p.exit,
            target_pct=p.band.target_pct if p.band else None,
            value_before=p.value,
            allocation_before_pct=r.allocation_before_pct,
            buffer_buy=r.buffer_buy,
            buffer_deployed=r.buffer_deployed,
            sell_amount=r.sell_amount,
            phase1_action=r.phase1_action.value,
            value_after_phase1=r.value_after_phase1,
            allocation_after_phase1_pct=r.allocation_after_phase1_pct,
            buy_amount=r.buy_amount,
            withdrawal_sell=r.withdrawal_sell,
            phase3_action=r.phase3_action.value,
            value_after=r.value_after_phase3,
            allocation_after_pct=r.allocation_after_phase3_pct,
            difference_to_target_pct=r.difference_to_target_pct,
            units_before=p.units if p.has_units else None,
            price=p.price if p.has_units else None,
            whole_units=p.whole_units if p.has_units else None,
            buffer_buy_units=r.buffer_buy_units,
            sell_units=r.sell_units,
            buy_units=r.buy_units,
            withdrawal_sell_units=r.withdrawal_sell_units,
            units_after=r.units_after,
        )


class ResultOut(BaseModel):
    """RB-12, RB-13: totals, cash calculation, buys per broker."""

    total_value_before: PlainDecimal
    total_buffer_used: PlainDecimal
    total_sell_proceeds: PlainDecimal
    available_cash: PlainDecimal
    total_withdrawal_sells: PlainDecimal
    unallocated_cash: PlainDecimal
    rounding_cash: PlainDecimal  # part of the unallocated cash left by whole units (RB-24)
    total_value_after: PlainDecimal
    buys_by_broker: dict[str, PlainDecimal]
    positions: list[PositionResultOut]

    @classmethod
    def of(cls, result: RebalanceResult) -> ResultOut:
        return cls(
            total_value_before=result.total_value_before,
            total_buffer_used=result.total_buffer_used,
            total_sell_proceeds=result.total_sell_proceeds,
            available_cash=result.available_cash,
            total_withdrawal_sells=result.total_withdrawal_sells,
            unallocated_cash=result.unallocated_cash,
            rounding_cash=result.rounding_cash,
            total_value_after=result.total_value_after,
            buys_by_broker={(b or ""): a for b, a in result.buys_by_broker.items()},
            positions=[PositionResultOut.of(r) for r in result.positions],
        )


class InstructionOut(BaseModel):
    phase: str
    ticker: str
    action: str
    broker: str | None
    amount: PlainDecimal
    units: PlainDecimal | None  # RB-24; null without units
    whole_units: bool | None


class PlanOut(BaseModel):
    """RB-02, RB-03: instructions; nothing is stored."""

    snapshot_id: int
    snapshot_taken_at: datetime
    policy_version_id: int
    policy_version_label: str
    policy_id: int
    policy_name: str
    mode: str  # RB-25: normal | sell_all
    # THS-04, RB-25, RB-26: the semaphore of the active version, with the reason of its review
    semaphore: str | None
    semaphore_reason: str | None
    contribution: PlainDecimal
    withdrawal: PlainDecimal
    precise_amounts: bool
    instructions: list[InstructionOut]
    result: ResultOut

    @classmethod
    def of(cls, plan: Plan) -> PlanOut:
        return cls(
            snapshot_id=plan.snapshot.id,
            snapshot_taken_at=plan.snapshot.taken_at,
            policy_version_id=plan.version.id,
            policy_version_label=plan.version.label,
            policy_id=plan.version.policy_id,
            policy_name=plan.version.policy.name,
            mode=plan.mode.value,
            semaphore=plan.semaphore.value if plan.semaphore else None,
            semaphore_reason=plan.semaphore_reason,
            contribution=plan.contribution,
            withdrawal=plan.withdrawal,
            precise_amounts=plan.portfolio.precise_amounts,
            instructions=[
                InstructionOut(
                    phase=i.phase,
                    ticker=i.ticker,
                    action=i.action,
                    broker=i.broker,
                    amount=i.amount,
                    units=i.units,
                    whole_units=i.whole_units,
                )
                for i in plan.actions
            ],
            result=ResultOut.of(plan.result),
        )


class ExecutedIn(BaseModel):
    phase: str
    ticker: str
    amount: PlainDecimal
    units: PlainDecimal | None = None  # null: the calculated units (RB-16)


class Confirmation(BaseModel):
    snapshot_id: int
    contribution: PlainDecimal
    withdrawal: PlainDecimal = Decimal(0)
    policy_version_id: int
    mode: str = "normal"  # RB-25
    executed: list[ExecutedIn] = []


class ActionOut(BaseModel):
    phase: str
    ticker: str
    action: str
    broker: str | None
    whole_units: bool | None
    calculated_units: PlainDecimal | None
    executed_units: PlainDecimal | None
    calculated_amount: PlainDecimal
    executed_amount: PlainDecimal


class RebalanceOut(BaseModel):
    id: int
    portfolio_id: int
    confirmed_at: datetime
    input_snapshot_id: int
    result_snapshot_id: int | None
    policy_version_id: int
    contribution: PlainDecimal
    withdrawal: PlainDecimal
    mode: str
    precise_amounts: bool
    actions: list[ActionOut]


class SimulationIn(BaseModel):
    cycles: int
    contribution: PlainDecimal | None = None
    withdrawal: PlainDecimal | None = None
    snapshot_id: int | None = None


def _rebalance(session: DbSession, record: Rebalance) -> RebalanceOut:
    actions = session.execute(
        select(RebalanceAction, Asset.ticker)
        .join(Asset, Asset.id == RebalanceAction.asset_id)
        .where(RebalanceAction.rebalance_id == record.id)
        .order_by(RebalanceAction.id)
    ).all()
    return RebalanceOut(
        id=record.id,
        portfolio_id=record.portfolio_id,
        confirmed_at=record.confirmed_at,
        input_snapshot_id=record.input_snapshot_id,
        result_snapshot_id=record.result_snapshot_id,
        policy_version_id=record.policy_version_id,
        contribution=record.contribution,
        withdrawal=record.withdrawal,
        mode=record.mode,
        precise_amounts=record.precise_amounts,
        actions=[
            ActionOut(
                phase=a.phase,
                ticker=ticker,
                action=a.action,
                broker=a.broker,
                whole_units=a.whole_units,
                calculated_units=a.calculated_units,
                executed_units=a.executed_units,
                calculated_amount=a.calculated_amount,
                executed_amount=a.executed_amount,
            )
            for a, ticker in actions
        ],
    )


@router.get("/portfolios/{portfolio_id}/rebalance")
def preview(
    portfolio_id: int,
    session: DbSession,
    clock: AppClock,
    user: CurrentUser,
    snapshot_id: int | None = None,
    contribution: PlainDecimal | None = None,
    withdrawal: PlainDecimal | None = None,
    mode: str | None = None,  # RB-25: without one, a broken thesis preselects the sale
) -> PlanOut:
    return PlanOut.of(
        rebalances.plan(
            session,
            user,
            clock,
            portfolio_id,
            snapshot_id=snapshot_id,
            contribution=contribution,
            withdrawal=withdrawal,
            mode=rebalances.parse_mode(mode) if mode else None,
        )
    )


@router.post("/portfolios/{portfolio_id}/rebalances", status_code=201)
def confirm(
    portfolio_id: int,
    body: Confirmation,
    session: DbSession,
    clock: AppClock,
    user: CurrentUser,
) -> RebalanceOut:
    record = rebalances.confirm(
        session,
        user,
        clock,
        portfolio_id,
        snapshot_id=body.snapshot_id,
        contribution=body.contribution,
        withdrawal=body.withdrawal,
        policy_version_id=body.policy_version_id,
        executed=[Executed(e.phase, e.ticker, e.amount, e.units) for e in body.executed],
        mode=rebalances.parse_mode(body.mode),
    )
    return _rebalance(session, record)


@router.get("/portfolios/{portfolio_id}/rebalances")
def list_rebalances(portfolio_id: int, session: DbSession, user: CurrentUser) -> list[RebalanceOut]:
    return [_rebalance(session, r) for r in rebalances.list_rebalances(session, user, portfolio_id)]


@router.get("/rebalances/{rebalance_id}")
def get_rebalance(rebalance_id: int, session: DbSession, user: CurrentUser) -> RebalanceOut:
    return _rebalance(session, rebalances.get_rebalance(session, user, rebalance_id))


@router.get("/rebalances/{rebalance_id}/result")
def get_rebalance_result(rebalance_id: int, session: DbSession, user: CurrentUser) -> ResultOut:
    """RB-19: all phase tables of a confirmed rebalance, for its report."""
    return ResultOut.of(rebalances.recalculate(session, user, rebalance_id))


@router.post("/portfolios/{portfolio_id}/simulate")
def simulate(
    portfolio_id: int,
    body: SimulationIn,
    session: DbSession,
    clock: AppClock,
    user: CurrentUser,
) -> list[ResultOut]:
    results = rebalances.simulate(
        session,
        user,
        clock,
        portfolio_id,
        body.cycles,
        snapshot_id=body.snapshot_id,
        contribution=body.contribution,
        withdrawal=body.withdrawal,
    )
    return [ResultOut.of(r) for r in results]
