"""Rebalance preview, confirmation and simulation (RB-01 to RB-03, RB-16, RB-20,
RB-22)."""

from decimal import ROUND_FLOOR, Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.fixtures import Factory, spec
from yap.db.models import (
    Asset,
    Investor,
    Portfolio,
    Rebalance,
    RebalanceAction,
)
from yap.domain.rebalancing import Mode
from yap.services import policies, portfolios, rebalances, snapshots
from yap.services.common import ConflictError, NotFoundError, ValidationError
from yap.services.portfolios import PositionSettings
from yap.services.snapshots import ValueSpec
from yap.services.timeline import EventType, list_events


def setup(
    factory: Factory, verdict: str | None = None, **values: int
) -> tuple[Investor, Portfolio]:
    """A 50/50 policy (sell +20 % -> 60 %, midband 55 %) plus a cash buffer, with values."""
    owner = factory.investor()
    policy = factory.active_policy(
        owner,
        [
            spec("AAA", 50, buy=-40, sell=20),
            spec("BBB", 45, buy=-40, sell=20),
            spec("CASH", 5, buy=-100, sell=100, type="cash_buffer"),
        ],
        name="core",
        verdict=verdict,
    )
    portfolio = factory.portfolio(owner, policy, name="Main", default_contribution=Decimal(100))
    portfolios.set_positions(
        factory.session,
        owner,
        portfolio.id,
        {"AAA": PositionSettings("Southbank"), "BBB": PositionSettings("Northbank")},
    )
    snapshots.create_snapshot(
        factory.session,
        owner,
        factory.clock,
        portfolio.id,
        [ValueSpec(t, Decimal(v)) for t, v in values.items()],
    )
    return owner, portfolio


@pytest.mark.req("RB-01", "RB-02", "RB-03")
def test_plan_uses_latest_snapshot_and_default_contribution(
    session: Session, factory: Factory
) -> None:
    owner, portfolio = setup(factory, AAA=500, BBB=450, CASH=50)
    plan = rebalances.plan(session, owner, factory.clock, portfolio.id)
    assert plan.contribution == 100
    assert plan.snapshot.taken_at == factory.clock.now()  # shown to the investor (RB-02)
    assert plan.version.label == "core-v1"
    assert session.scalar(select(func.count()).select_from(Rebalance)) == 0  # RB-03
    other = rebalances.plan(session, owner, factory.clock, portfolio.id, contribution=Decimal(0))
    assert other.result.available_cash == 0


@pytest.mark.req("RB-01")
def test_plan_needs_a_snapshot_and_rejects_negative_contribution(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    portfolio = factory.portfolio(owner)
    with pytest.raises(ConflictError, match="current values"):
        rebalances.plan(session, owner, factory.clock, portfolio.id)
    snapshots.create_snapshot(
        session, owner, factory.clock, portfolio.id, [ValueSpec("AAA", Decimal(1))]
    )
    with pytest.raises(ValidationError) as err:
        rebalances.plan(session, owner, factory.clock, portfolio.id, contribution=Decimal(-1))
    assert err.value.problems[0][0] == "contribution"


@pytest.mark.req("RB-01")
def test_snapshot_must_belong_to_the_portfolio(session: Session, factory: Factory) -> None:
    owner, portfolio = setup(factory, AAA=1)
    other = factory.portfolio(owner, name="Other")
    foreign = snapshots.create_snapshot(
        session, owner, factory.clock, other.id, [ValueSpec("AAA", Decimal(1))]
    )
    with pytest.raises(NotFoundError):
        rebalances.plan(session, owner, factory.clock, portfolio.id, snapshot_id=foreign.id)


@pytest.mark.req("RB-01", "RB-13")
def test_plan_uses_active_version_and_brokers(session: Session, factory: Factory) -> None:
    owner, portfolio = setup(factory, AAA=500, BBB=450, CASH=50)
    plan = rebalances.plan(session, owner, factory.clock, portfolio.id)
    assert set(plan.result.buys_by_broker) <= {"Southbank", "Northbank", None}
    assert [(i.phase, i.ticker) for i in plan.actions if i.phase == "3"] == [
        ("3", "AAA"),
        ("3", "BBB"),
        ("3", "CASH"),  # the buffer has a 5 % target
    ]


def confirm(session: Session, owner: Investor, factory: Factory, portfolio: Portfolio, **kw):  # type: ignore[no-untyped-def]
    plan = rebalances.plan(session, owner, factory.clock, portfolio.id, **kw)
    return plan, rebalances.confirm(
        session,
        owner,
        factory.clock,
        portfolio.id,
        snapshot_id=plan.snapshot.id,
        contribution=plan.contribution,
        withdrawal=plan.withdrawal,
        policy_version_id=plan.version.id,
    )


@pytest.mark.req("RB-16", "TL-01")
def test_confirm_stores_the_calculated_instructions(session: Session, factory: Factory) -> None:
    # AAA 70 % > 60 % -> sell to midband 55 % of 1000 = 550 -> sell 150
    owner, portfolio = setup(factory, AAA=700, BBB=300, CASH=0)
    factory.clock.advance(hours=1)
    plan, record = confirm(session, owner, factory, portfolio, contribution=Decimal(0))
    rows = session.execute(
        select(RebalanceAction, Asset.ticker)
        .join(Asset, Asset.id == RebalanceAction.asset_id)
        .where(RebalanceAction.rebalance_id == record.id)
    ).all()
    actions = {(a.phase, t): (a.action, a.calculated_amount) for a, t in rows}
    assert actions[("1B", "AAA")] == ("Sell", Decimal(150))
    label, _ = actions[("3", "BBB")]
    assert label == "Buy (Below Target)"
    bought = sum(amount for (phase, _), (_, amount) in actions.items() if phase == "3")
    assert record.policy_version_id == plan.version.id
    assert record.confirmed_at == factory.clock.now()

    # Confirming commits to the trades; the values change only when they are recorded
    assert record.result_snapshot_id is None
    assert snapshots.latest_snapshot(session, owner, portfolio.id) == plan.snapshot

    event = list_events(session, owner)[-1]
    assert event.type == EventType.REBALANCE_CONFIRMED
    assert event.summary == f"Main: rebalanced, sold 150, bought {bought:,.0f}"
    # The values of the summary, for the timeline in the UI's language (TL-02, NFR-10)
    assert event.params == {
        "portfolio": "Main",
        "sold": "150.0000",
        "bought": str(bought),
        "withdrawal": None,
        "mode": "normal",
        "precise": False,
    }
    assert event.rebalance_id == record.id


@pytest.mark.req("RB-16")
def test_confirm_refuses_when_policy_changed_since_preview(
    session: Session, factory: Factory
) -> None:
    owner, portfolio = setup(factory, AAA=500, BBB=450, CASH=50)
    plan = rebalances.plan(session, owner, factory.clock, portfolio.id)
    factory.clock.advance(minutes=5)
    policies.create_draft(session, owner, factory.clock, portfolio.policy_id)
    policies.activate_draft(session, owner, factory.clock, portfolio.policy_id, "changed")
    with pytest.raises(ConflictError, match="changed since the preview"):
        rebalances.confirm(
            session,
            owner,
            factory.clock,
            portfolio.id,
            snapshot_id=plan.snapshot.id,
            contribution=plan.contribution,
            policy_version_id=plan.version.id,
        )


@pytest.mark.req("RB-18", "NFR-05")
def test_confirmed_rebalance_cannot_be_changed(session: Session, factory: Factory) -> None:
    owner, portfolio = setup(factory, AAA=500, BBB=450, CASH=50)
    _, record = confirm(session, owner, factory, portfolio)
    session.commit()
    assert rebalances.list_rebalances(session, owner, portfolio.id) == [record]
    assert rebalances.get_rebalance(session, owner, record.id) == record
    with pytest.raises(IntegrityError):
        session.execute(text("UPDATE rebalance SET contribution = '0'"))
    session.rollback()
    with pytest.raises(NotFoundError):
        rebalances.get_rebalance(session, factory.investor(), record.id)


@pytest.mark.req("RB-20")
def test_simulation_runs_cycles_without_storing(session: Session, factory: Factory) -> None:
    owner, portfolio = setup(factory, AAA=700, BBB=300, CASH=0)
    snapshots.create_snapshot(
        session,
        owner,
        factory.clock,
        portfolio.id,
        [
            *(ValueSpec(t, Decimal(v)) for t, v in (("AAA", 700), ("BBB", 300))),
            ValueSpec("OLD", Decimal(50), "Old", "stock"),
        ],
    )
    results = rebalances.simulate(
        session, owner, factory.clock, portfolio.id, 3, contribution=Decimal(100)
    )
    assert len(results) == 3
    # each cycle starts where the previous one ended, plus the same contribution
    assert results[1].total_value_before == results[0].total_value_after
    assert results[2].total_value_before == results[1].total_value_after
    assert results[2].total_value_after == results[2].total_value_before + 100
    assert "OLD" not in [r.position.ticker for r in results[1].positions]
    assert session.scalar(select(func.count()).select_from(Rebalance)) == 0
    with pytest.raises(ValidationError):
        rebalances.simulate(session, owner, factory.clock, portfolio.id, 0)
    with pytest.raises(ValidationError):
        rebalances.simulate(session, owner, factory.clock, portfolio.id, 121)


@pytest.mark.req("RB-01")
def test_plan_rejects_a_withdrawal_above_value_plus_contribution(
    session: Session, factory: Factory
) -> None:
    owner, portfolio = setup(factory, AAA=500, BBB=450, CASH=50)
    plan = rebalances.plan(session, owner, factory.clock, portfolio.id)
    assert plan.withdrawal == 0  # no default from the portfolio
    for amount in (Decimal(-1), Decimal("1100.01")):
        with pytest.raises(ValidationError) as err:
            rebalances.plan(session, owner, factory.clock, portfolio.id, withdrawal=amount)
        assert err.value.problems[0][0] == "withdrawal"


@pytest.mark.req("RB-16", "RB-22")
def test_confirm_with_withdrawal_sells_in_phase_3(session: Session, factory: Factory) -> None:
    # F = 1000 - 200 = 800; no sell threshold reached, so all 200 come from the positions
    # above target, which end at their target values 400 / 360 / 40
    owner, portfolio = setup(factory, AAA=500, BBB=450, CASH=50)
    plan, record = confirm(
        session,
        owner,
        factory,
        portfolio,
        contribution=Decimal(0),
        withdrawal=Decimal(200),
    )
    sells = {i.ticker: i.amount for i in plan.actions if i.action == "Sell (Withdrawal)"}
    assert set(sells) == {"AAA", "BBB", "CASH"}
    assert abs(sells["AAA"] - 100) < Decimal("0.01")
    assert sum(sells.values()) == 200
    assert record.withdrawal == 200

    event = list_events(session, owner)[-1]
    assert event.summary == "Main: rebalanced, sold 200, bought 0, withdrew 200"
    assert event.params is not None and event.params["withdrawal"] == "200"

    recalculated = rebalances.recalculate(session, owner, record.id)
    assert recalculated.total_withdrawal_sells == 200


@pytest.mark.req("RB-20")
def test_simulation_repeats_the_withdrawal(session: Session, factory: Factory) -> None:
    owner, portfolio = setup(factory, AAA=500, BBB=450, CASH=50)
    results = rebalances.simulate(
        session,
        owner,
        factory.clock,
        portfolio.id,
        3,
        contribution=Decimal(100),
        withdrawal=Decimal(150),
    )
    assert [r.total_value_after for r in results] == [Decimal(950), Decimal(900), Decimal(850)]


# --- Units (RB-24) --------------------------------------------------------------


def unit_setup(factory: Factory, **units: tuple[int, int]) -> tuple[Investor, Portfolio]:
    """`setup` with units and prices: AAA=(units, price) etc.; whole units by default."""
    owner, portfolio = setup(factory, AAA=0, BBB=0, CASH=0)
    factory.clock.advance(minutes=1)
    snapshots.create_snapshot(
        factory.session,
        owner,
        factory.clock,
        portfolio.id,
        [
            ValueSpec(t, value=Decimal(u))
            if t == "CASH"
            else ValueSpec(t, units=Decimal(u), price=Decimal(p))
            for t, (u, p) in units.items()
        ],
        require_units=True,
    )
    return owner, portfolio


@pytest.mark.req("RB-24", "RB-11")
def test_plan_converts_amounts_into_units(session: Session, factory: Factory) -> None:
    # AAA 70 units at 10 = 700 (70 %) -> sell to midband 55 % of 1000: 150 = 15 units;
    # the buy of BBB is 150 at 40 = 3.75 units -> 3 units = 120, 30 left unallocated
    owner, portfolio = unit_setup(factory, AAA=(70, 10), BBB=(7, 40), CASH=(20, 1))
    plan = rebalances.plan(session, owner, factory.clock, portfolio.id, contribution=Decimal(0))
    assert [(i.phase, i.ticker, i.units, i.amount, i.whole_units) for i in plan.actions][:2] == [
        ("1B", "AAA", 15, 150, True),
        ("3", "BBB", 3, 120, True),
    ]
    # The cash buffer keeps its amount; what rounding leaves is unallocated
    assert all(i.units is None for i in plan.actions if i.ticker == "CASH")
    assert plan.result.rounding_cash > 0
    # Fractional units for BBB: no rounding
    portfolios.set_positions(
        session, owner, portfolio.id, {"BBB": PositionSettings("Northbank", whole_units=False)}
    )
    fractional = rebalances.plan(
        session, owner, factory.clock, portfolio.id, contribution=Decimal(0)
    )
    bbb = next(i for i in fractional.actions if i.ticker == "BBB")
    # Fractional units have 18 decimals, rounded down; the amount stays as calculated
    assert bbb.units == (bbb.amount / 40).quantize(Decimal("1E-18"), rounding=ROUND_FLOOR)
    assert bbb.whole_units is False
    assert fractional.result.rounding_cash == 0


@pytest.mark.req("RB-16", "RB-24")
def test_confirm_stores_the_calculated_units(session: Session, factory: Factory) -> None:
    owner, portfolio = unit_setup(factory, AAA=(70, 10), BBB=(30, 10), CASH=(0, 1))
    factory.clock.advance(hours=1)
    _, record = confirm(session, owner, factory, portfolio, contribution=Decimal(0))
    actions = {
        ticker: (a.calculated_units, a.calculated_amount, a.whole_units)
        for a, ticker in session.execute(
            select(RebalanceAction, Asset.ticker)
            .join(Asset, Asset.id == RebalanceAction.asset_id)
            .where(RebalanceAction.rebalance_id == record.id)
        )
    }
    assert actions["AAA"] == (15, 150, True)
    # The stored actions keep whole units even if the setting changes afterwards
    portfolios.set_positions(
        session, owner, portfolio.id, {"AAA": PositionSettings(whole_units=False)}
    )
    again = rebalances.recalculate(session, owner, record.id)
    assert [r.sell_units for r in again.positions if r.position.ticker == "AAA"] == [15]


@pytest.mark.req("RB-19", "RB-24")
def test_rebalances_from_before_units_are_recalculated_without_units(
    session: Session, factory: Factory
) -> None:
    owner, portfolio = unit_setup(factory, AAA=(70, 10), BBB=(7, 40), CASH=(0, 1))
    _, record = confirm(session, owner, factory, portfolio, contribution=Decimal(0))
    session.execute(text("DROP TRIGGER rebalance_action_no_update"))
    session.execute(text("UPDATE rebalance_action SET calculated_units = NULL"))
    result = rebalances.recalculate(session, owner, record.id)
    assert all(r.buy_units is None and r.sell_units is None for r in result.positions)
    assert result.rounding_cash == 0


@pytest.mark.req("RB-20", "RB-24")
def test_simulation_continues_with_the_units_after_each_cycle(
    session: Session, factory: Factory
) -> None:
    owner, portfolio = unit_setup(factory, AAA=(50, 10), BBB=(45, 10), CASH=(50, 1))
    cycles = rebalances.simulate(
        session, owner, factory.clock, portfolio.id, 3, contribution=Decimal(100)
    )
    units = [{r.position.ticker: r.units_after for r in c.positions} for c in cycles]
    assert units[0]["AAA"] is not None and units[1]["AAA"] is not None
    assert units[2]["AAA"] >= units[1]["AAA"] >= units[0]["AAA"]  # type: ignore[operator]
    assert all(
        c.positions[0].position.units == u["AAA"]
        for c, u in zip(cycles[1:], units[:-1], strict=True)
    )


@pytest.mark.req("RB-25", "RB-26", "THS-04")
def test_plan_carries_the_semaphore_and_its_reason(session: Session, factory: Factory) -> None:
    owner, portfolio = setup(factory, verdict="warning", AAA=500, BBB=450, CASH=50)
    plan = rebalances.plan(session, owner, factory.clock, portfolio.id)
    assert plan.semaphore is not None and plan.semaphore.value == "warning"
    assert plan.mode is Mode.NORMAL
    owner, portfolio = setup(factory, AAA=500, BBB=450, CASH=50)
    unreviewed = rebalances.plan(session, owner, factory.clock, portfolio.id)
    assert (unreviewed.semaphore, unreviewed.semaphore_reason) == (None, None)


@pytest.mark.req("RB-25")
def test_selling_the_whole_portfolio_is_only_for_a_broken_thesis(
    session: Session, factory: Factory
) -> None:
    for verdict in ("good", "warning", None):
        owner, portfolio = setup(factory, verdict=verdict, AAA=500, BBB=450, CASH=50)
        with pytest.raises(ConflictError, match="only offered when the thesis is broken"):
            rebalances.plan(session, owner, factory.clock, portfolio.id, mode=Mode.SELL_ALL)
        latest = snapshots.latest_snapshot(session, owner, portfolio.id)
        assert latest is not None
        with pytest.raises(ConflictError, match="only offered when the thesis is broken"):
            rebalances.confirm(
                session,
                owner,
                factory.clock,
                portfolio.id,
                snapshot_id=latest.id,
                contribution=Decimal(0),
                policy_version_id=1,
                mode=Mode.SELL_ALL,
            )
    assert session.scalar(select(func.count()).select_from(Rebalance)) == 0
    with pytest.raises(ValidationError):
        rebalances.parse_mode("sell_everything")


@pytest.mark.req("RB-25", "TL-02", "RB-16")
def test_confirming_the_sale_of_the_whole_portfolio(session: Session, factory: Factory) -> None:
    owner, portfolio = setup(factory, verdict="broken", AAA=500, BBB=450, CASH=50)
    p = rebalances.plan(session, owner, factory.clock, portfolio.id, mode=Mode.SELL_ALL)
    assert p.semaphore is not None and p.semaphore.value == "broken"
    assert {(i.ticker, i.amount) for i in p.actions} == {
        ("AAA", Decimal(500)),
        ("BBB", Decimal(450)),
    }
    record = rebalances.confirm(
        session,
        owner,
        factory.clock,
        portfolio.id,
        snapshot_id=p.snapshot.id,
        contribution=p.contribution,
        policy_version_id=p.version.id,
        mode=Mode.SELL_ALL,
    )
    assert record.mode == "sell_all"
    (event,) = [e for e in list_events(session, owner) if e.type == EventType.REBALANCE_CONFIRMED]
    assert event.summary == "Main: sold completely, thesis broken"
    assert event.params["mode"] == "sell_all"
    assert event.rebalance_id == record.id
    # Recalculated for its report (RB-19) in the mode it was confirmed in
    result = rebalances.recalculate(session, owner, record.id)
    assert sum(r.sell_amount for r in result.positions) == 950


@pytest.mark.req("RB-25", "RB-22")
def test_the_sale_of_the_whole_portfolio_pays_a_withdrawal_from_the_buffer(
    session: Session, factory: Factory
) -> None:
    owner, portfolio = setup(factory, verdict="broken", AAA=500, BBB=450, CASH=50)
    p = rebalances.plan(
        session,
        owner,
        factory.clock,
        portfolio.id,
        contribution=Decimal(0),
        withdrawal=Decimal(980),
        mode=Mode.SELL_ALL,
    )
    assert {(i.ticker, i.amount) for i in p.actions} == {
        ("AAA", Decimal(500)),
        ("BBB", Decimal(450)),
        ("CASH", Decimal(30)),
    }
    record = rebalances.confirm(
        session,
        owner,
        factory.clock,
        portfolio.id,
        snapshot_id=p.snapshot.id,
        contribution=Decimal(0),
        withdrawal=Decimal(980),
        policy_version_id=p.version.id,
        mode=Mode.SELL_ALL,
    )
    assert record.withdrawal == 980


@pytest.mark.req("RB-25")
def test_the_usual_rebalance_stays_possible_with_a_broken_thesis(
    session: Session, factory: Factory
) -> None:
    owner, portfolio = setup(factory, verdict="broken", AAA=500, BBB=450, CASH=50)
    preselected = rebalances.plan(session, owner, factory.clock, portfolio.id)
    assert preselected.mode is Mode.SELL_ALL  # preselected, not forced
    p = rebalances.plan(session, owner, factory.clock, portfolio.id, mode=Mode.NORMAL)
    assert p.mode is Mode.NORMAL
    record = rebalances.confirm(
        session,
        owner,
        factory.clock,
        portfolio.id,
        snapshot_id=p.snapshot.id,
        contribution=p.contribution,
        policy_version_id=p.version.id,
    )
    assert record.mode == "normal"
