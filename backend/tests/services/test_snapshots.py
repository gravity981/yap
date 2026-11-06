from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from tests.fixtures import Factory, spec
from yap.domain.bands import BandStatus
from yap.services import policies, portfolios, snapshots
from yap.services.common import NotFoundError, ValidationError
from yap.services.snapshots import ValueSpec


def values(**amounts: int) -> list[ValueSpec]:
    return [ValueSpec(t, Decimal(v)) for t, v in amounts.items()]


@pytest.mark.req("CMP-01", "NFR-14")
def test_snapshot_gets_the_time_it_is_saved(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    portfolio = factory.portfolio(owner)
    saved = factory.clock.advance(hours=3)
    snapshot = snapshots.create_snapshot(
        session, owner, factory.clock, portfolio.id, values(AAA=600, BBB=400)
    )
    assert snapshot.taken_at == saved
    assert snapshot.source == "manual"


@pytest.mark.req("CMP-01")
def test_values_must_be_zero_or_more_and_unique(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    portfolio = factory.portfolio(owner)
    with pytest.raises(ValidationError) as err:
        snapshots.create_snapshot(
            session,
            owner,
            factory.clock,
            portfolio.id,
            [ValueSpec("AAA", Decimal(-1)), ValueSpec("aaa", Decimal(1))],
        )
    assert [p for p, _ in err.value.problems] == ["values[0].value", "values[1].ticker"]


@pytest.mark.req("CMP-01")
def test_prefill_uses_policy_positions_and_previous_values(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    portfolio = factory.portfolio(owner)
    assert [
        (r.ticker, r.value) for r in snapshots.prefill(session, owner, factory.clock, portfolio.id)
    ] == [
        ("AAA", 0),
        ("BBB", 0),
    ]
    snapshots.create_snapshot(
        session,
        owner,
        factory.clock,
        portfolio.id,
        [*values(AAA=600), ValueSpec("OLD", Decimal(50), "Legacy stock", "stock")],
    )
    rows = snapshots.prefill(session, owner, factory.clock, portfolio.id)
    assert [(r.ticker, r.value, r.in_policy) for r in rows] == [
        ("AAA", 600, True),
        ("BBB", 0, True),
        ("OLD", 50, False),
    ]


@pytest.mark.req("CMP-02", "CMP-05", "IMP-08")
def test_comparison_rows(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policy = factory.active_policy(
        owner, [spec("AAA", 50, buy=-20, sell=20), spec("BBB", 30), spec("CCC", 20, exit=True)]
    )
    portfolio = factory.portfolio(owner, policy)
    with pytest.raises(ValidationError, match="name and type"):
        snapshots.create_snapshot(
            session, owner, factory.clock, portfolio.id, [ValueSpec("NEW", Decimal(1))]
        )
    snapshot = snapshots.create_snapshot(
        session,
        owner,
        factory.clock,
        portfolio.id,
        [*values(AAA=650, BBB=200), ValueSpec("OLD", Decimal(150), "Legacy", "stock")],
    )
    comparison = snapshots.compare(snapshot)
    assert comparison.total_value == 1000
    rows = {r.ticker: r for r in comparison.rows}
    assert rows["AAA"].allocation_pct == 65
    assert rows["AAA"].deviation_pct == 15
    assert rows["AAA"].band is not None and rows["AAA"].band.sell_abs == 60
    assert rows["AAA"].status is BandStatus.ABOVE_SELL_THRESHOLD
    assert rows["BBB"].status is BandStatus.BELOW_BUY_THRESHOLD
    assert rows["CCC"].value == 0 and rows["CCC"].exit is True
    assert rows["OLD"].status is BandStatus.NOT_IN_POLICY
    assert rows["OLD"].deviation_pct is None


@pytest.mark.req("CMP-03", "CMP-04", "NFR-05")
def test_snapshots_keep_the_version_active_when_they_were_taken(
    session: Session, factory: Factory
) -> None:
    """January-June against v1, July-December against v2 (CMP-04 example)."""
    owner = factory.investor()
    policy = factory.active_policy(owner, [spec("AAA", 60), spec("BBB", 40)], name="core")
    portfolio = factory.portfolio(owner, policy)
    january = snapshots.create_snapshot(
        session, owner, factory.clock, portfolio.id, values(AAA=600, BBB=400)
    )
    factory.clock.advance(days=170)
    policies.create_draft(session, owner, factory.clock, policy.id)
    policies.update_draft(
        session,
        owner,
        factory.clock,
        policy.id,
        positions=[spec("AAA", 40), spec("BBB", 60)],
    )
    policies.activate_draft(session, owner, factory.clock, policy.id, "Shift to BBB")
    factory.clock.advance(days=10)
    july = snapshots.create_snapshot(
        session, owner, factory.clock, portfolio.id, values(AAA=600, BBB=400)
    )

    assert january.policy_version.label == "core-v1"
    assert july.policy_version.label == "core-v2"
    january_aaa = next(r for r in snapshots.compare(january).rows if r.ticker == "AAA")
    july_aaa = next(r for r in snapshots.compare(july).rows if r.ticker == "AAA")
    assert january_aaa.deviation_pct == 0
    assert july_aaa.deviation_pct == 20


@pytest.mark.req("CMP-04", "PTF-04")
def test_reassignment_applies_to_later_snapshots_only(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    core = factory.active_policy(owner, name="core")
    growth = factory.active_policy(owner, name="growth")
    portfolio = factory.portfolio(owner, core)
    before = snapshots.create_snapshot(session, owner, factory.clock, portfolio.id, values(AAA=1))
    factory.clock.advance(days=1)
    portfolios.reassign_portfolio(session, owner, factory.clock, portfolio.id, growth.id)
    factory.clock.advance(seconds=1)
    after = snapshots.create_snapshot(session, owner, factory.clock, portfolio.id, values(AAA=1))
    assert before.policy_version.policy_id == core.id
    assert after.policy_version.policy_id == growth.id


@pytest.mark.req("CMP-06")
def test_correction_is_a_new_snapshot(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    portfolio = factory.portfolio(owner)
    wrong = snapshots.create_snapshot(session, owner, factory.clock, portfolio.id, values(AAA=6000))
    factory.clock.advance(minutes=1)
    fixed = snapshots.create_snapshot(
        session, owner, factory.clock, portfolio.id, values(AAA=600), corrects_snapshot_id=wrong.id
    )
    assert fixed.corrects_snapshot_id == wrong.id
    assert wrong.values[0].value == 6000
    assert snapshots.latest_snapshot(session, owner, portfolio.id) == fixed


@pytest.mark.req("CMP-08")
def test_past_snapshots_newest_first(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    portfolio = factory.portfolio(owner)
    first = snapshots.create_snapshot(session, owner, factory.clock, portfolio.id, values(AAA=1))
    factory.clock.advance(days=1)
    second = snapshots.create_snapshot(session, owner, factory.clock, portfolio.id, values(AAA=2))
    assert snapshots.list_snapshots(session, owner, portfolio.id) == [second, first]


@pytest.mark.req("CMP-09")
def test_overview_of_all_portfolios(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner, name="core")
    with_values = factory.portfolio(owner, policy, name="A")
    factory.portfolio(owner, policy, name="B")
    snapshots.create_snapshot(session, owner, factory.clock, with_values.id, values(AAA=1))
    rows = snapshots.overview(session, owner)
    assert [(r.portfolio.name, r.policy_name, r.latest is not None) for r in rows] == [
        ("A", "core", True),
        ("B", "core", False),
    ]


@pytest.mark.req("USR-04")
def test_snapshots_of_others_are_not_found(session: Session, factory: Factory) -> None:
    owner, other = factory.investor(), factory.investor()
    portfolio = factory.portfolio(owner)
    snapshot = snapshots.create_snapshot(session, owner, factory.clock, portfolio.id, values(AAA=1))
    with pytest.raises(NotFoundError):
        snapshots.get_snapshot(session, other, snapshot.id)
    with pytest.raises(NotFoundError):
        snapshots.create_snapshot(session, other, factory.clock, portfolio.id, values(AAA=1))
    assert snapshots.get_snapshot(session, owner, snapshot.id) == snapshot


def d(amount: str | int) -> Decimal:
    return Decimal(str(amount))


@pytest.mark.req("CMP-01", "CMP-10", "NFR-04")
def test_value_is_units_times_price_or_price_is_value_per_unit(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    portfolio = factory.portfolio(
        owner,
        factory.active_policy(
            owner, [spec("AAA", 50), spec("BBB", 40), spec("CSH", 10, type="cash_buffer")]
        ),
    )
    snapshot = snapshots.create_snapshot(
        session,
        owner,
        factory.clock,
        portfolio.id,
        [
            ValueSpec("AAA", units=d("3.5"), price=d("10.005")),
            ValueSpec("BBB", units=d(3), value=d(100)),
            ValueSpec("CSH", value=d("250.5")),
        ],
        require_units=True,
    )
    rows = {v.asset.ticker: v for v in snapshot.values}
    aaa, bbb, csh = rows["AAA"], rows["BBB"], rows["CSH"]
    # 3.5 x 10.005 = 35.0175, rounded to 0.01 (half up)
    assert (aaa.units, aaa.price, aaa.value, aaa.price_kind) == (
        d("3.5"),
        d("10.005"),
        d("35.02"),
        "manual",
    )
    assert bbb.value == d("100.00") and bbb.price is not None
    assert bbb.price * 3 == pytest.approx(d(100))
    # The cash buffer has only an amount: units = value, price 1
    assert (csh.units, csh.price, csh.value) == (d("250.50"), d(1), d("250.50"))
    comparison = snapshots.compare(snapshot)
    assert [(r.ticker, r.units, r.price_kind) for r in comparison.rows] == [
        ("AAA", d("3.5"), "manual"),
        ("BBB", d(3), "manual"),
        ("CSH", d("250.50"), "manual"),
    ]


@pytest.mark.req("CMP-01")
def test_without_price_and_value_the_price_last_entered_is_used(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    portfolio = factory.portfolio(owner)

    def save(*specs: ValueSpec) -> dict[str, tuple[Decimal | None, Decimal | None, Decimal]]:
        s = snapshots.create_snapshot(
            session, owner, factory.clock, portfolio.id, list(specs), require_units=True
        )
        return {v.asset.ticker: (v.units, v.price, v.value) for v in s.values}

    with pytest.raises(ValidationError) as err:
        save(ValueSpec("AAA", units=d(2)))  # no earlier price
    assert [(p, m.code) for p, m in err.value.problems] == [("values[0].price", "price_required")]
    save(ValueSpec("AAA", units=d(2), price=d(50)), ValueSpec("BBB", units=d(1), price=d(9)))
    factory.clock.advance(days=1)
    # BBB is left out of this snapshot; its price stays the one last entered
    assert save(ValueSpec("AAA", units=d(3))) == {"AAA": (d(3), d(50), d("150.00"))}
    factory.clock.advance(days=1)
    assert save(ValueSpec("AAA", units=d(0)), ValueSpec("BBB", units=d(4)))["BBB"] == (
        d(4),
        d(9),
        d("36.00"),
    )
    prefill = {r.ticker: r for r in snapshots.prefill(session, owner, factory.clock, portfolio.id)}
    assert (prefill["AAA"].units, prefill["AAA"].price) == (d(0), d(50))
    assert (prefill["BBB"].units, prefill["BBB"].price) == (d(4), d(9))


@pytest.mark.req("CMP-01")
def test_units_rules(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    portfolio = factory.portfolio(
        owner, factory.active_policy(owner, [spec("AAA", 90), spec("CSH", 10, type="cash_buffer")])
    )

    def problems(*specs: ValueSpec, require_units: bool = True) -> list[tuple[str, str]]:
        with pytest.raises(ValidationError) as err:
            snapshots.create_snapshot(
                session,
                owner,
                factory.clock,
                portfolio.id,
                list(specs),
                require_units=require_units,
            )
        return [(p, m.code) for p, m in err.value.problems]

    assert problems(ValueSpec("AAA", value=d(5))) == [("values[0].units", "units_required")]
    assert problems(ValueSpec("AAA", units=d(-1), price=d(-2), value=d(-3))) == [
        ("values[0].units", "units_min"),
        ("values[0].price", "price_min"),
        ("values[0].value", "value_min"),
    ]
    assert problems(ValueSpec("AAA", units=d(0), value=d(5))) == [
        ("values[0].value", "value_without_units")
    ]
    # Without required units, a position may have only its value; but not nothing
    assert problems(ValueSpec("AAA"), require_units=False) == [
        ("values[0].units", "units_required")
    ]
    assert problems(ValueSpec("CSH")) == [("values[0].value", "position_units_or_value")]
    zero = snapshots.create_snapshot(
        session,
        owner,
        factory.clock,
        portfolio.id,
        [ValueSpec("AAA", units=d(0), value=d(0)), ValueSpec("CSH", units=d(20))],
        require_units=True,
    )
    assert [(v.units, v.price, v.value) for v in zero.values] == [
        (d(0), d(0), d(0)),  # no earlier price: 0
        (d("20.00"), d(1), d("20.00")),
    ]


@pytest.mark.req("CMP-10", "IMP-03")
def test_rows_without_units_keep_only_their_value(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    portfolio = factory.portfolio(owner)
    snapshot = snapshots.create_snapshot(
        session, owner, factory.clock, portfolio.id, values(AAA=600, BBB=400)
    )
    assert [(v.units, v.price, v.value, v.price_kind) for v in snapshot.values] == [
        (None, None, d(600), None),
        (None, None, d(400), None),
    ]
    prefill = snapshots.prefill(session, owner, factory.clock, portfolio.id)
    # Units unknown: the form asks for them, showing the previous value
    assert [(r.units, r.price, r.value) for r in prefill] == [
        (None, None, d(600)),
        (None, None, d(400)),
    ]
