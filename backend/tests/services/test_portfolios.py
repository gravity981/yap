from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.fixtures import Factory, spec
from yap.services import policies, portfolios, snapshots, versioning
from yap.services.assets import find_asset
from yap.services.common import ConflictError, NotFoundError, ValidationError
from yap.services.portfolios import PositionSettings
from yap.services.snapshots import ValueSpec
from yap.services.timeline import EventType, list_events


@pytest.mark.req("PTF-01", "PTF-02")
def test_portfolio_is_created_with_its_policy(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner, name="core")
    main = factory.portfolio(owner, policy, name="Main")
    extra = factory.portfolio(owner, policy, name="Extra")
    assert main.policy_id == extra.policy_id == policy.id
    assert [a.policy_id for a in main.assignments] == [policy.id]
    assert [p.name for p in portfolios.list_portfolios(session, owner)] == ["Extra", "Main"]


@pytest.mark.req("PTF-02")
def test_portfolio_without_policy_is_impossible(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    factory.portfolio(owner)
    session.commit()
    with pytest.raises(IntegrityError):
        session.execute(text("UPDATE portfolio SET policy_id = NULL"))


@pytest.mark.req("PTF-02")
def test_only_policies_with_active_version_can_be_assigned(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    draft_only = policies.create_policy(
        session, owner, factory.clock, name="draft", thesis_id=factory.thesis(owner).id
    )
    with pytest.raises(ConflictError, match="no active version"):
        portfolios.create_portfolio(
            session, owner, factory.clock, name="Main", policy_id=draft_only.id
        )


@pytest.mark.req("PTF-02")
def test_policy_of_another_investor_cannot_be_assigned(session: Session, factory: Factory) -> None:
    owner, other = factory.investor(), factory.investor()
    foreign = factory.active_policy(other)
    with pytest.raises(NotFoundError):
        portfolios.create_portfolio(
            session, owner, factory.clock, name="Main", policy_id=foreign.id
        )


@pytest.mark.req("PTF-03")
def test_settings_and_positions(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    portfolio = factory.portfolio(owner)
    portfolios.update_settings(
        session, owner, portfolio.id, default_contribution=Decimal(2000), precise_amounts=True
    )
    portfolios.set_positions(
        session,
        owner,
        portfolio.id,
        {
            "aaa": PositionSettings("Southbank"),
            "BBB": PositionSettings("Northbank", whole_units=False),
        },
    )
    portfolios.set_positions(session, owner, portfolio.id, {"BBB": PositionSettings("")})
    aaa, bbb = (find_asset(session, t) for t in ("AAA", "BBB"))
    assert aaa is not None and bbb is not None
    assert portfolio.default_contribution == 2000
    assert portfolio.precise_amounts is True
    assert portfolios.broker_for(portfolio, aaa.id) == "Southbank"
    assert portfolios.broker_for(portfolio, bbb.id) is None
    assert len(portfolio.positions) == 1  # BBB has neither broker nor whole-units setting
    with pytest.raises(ValidationError):
        portfolios.update_settings(
            session, owner, portfolio.id, default_contribution=Decimal(-1), precise_amounts=False
        )


@pytest.mark.req("PTF-03")
def test_whole_units_default_by_type_and_can_be_set_per_position(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    portfolio = factory.portfolio(
        owner,
        factory.active_policy(
            owner,
            [
                spec("ETF1", 40),
                spec("STK", 30, type="stock"),
                spec("BTC", 20, type="crypto"),
                spec("CASH", 10, type="cash_buffer"),
            ],
        ),
    )
    assets = {t: find_asset(session, t) for t in ("ETF1", "STK", "BTC", "CASH")}

    def whole(ticker: str) -> bool | None:
        asset = assets[ticker]
        assert asset is not None
        return portfolios.whole_units_for(portfolio, asset)

    assert [whole(t) for t in assets] == [True, True, False, None]
    portfolios.set_positions(
        session,
        owner,
        portfolio.id,
        {
            "ETF1": PositionSettings(whole_units=False),
            "BTC": PositionSettings(whole_units=True),
            "CASH": PositionSettings(whole_units=True),  # not applicable: ignored
        },
    )
    assert [whole(t) for t in assets] == [False, True, True, None]
    assert len(portfolio.positions) == 2


@pytest.mark.req("PTF-03", "USR-06")
def test_currency_defaults_to_base_currency_and_is_fixed_once_snapshots_exist(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()  # base currency CHF
    portfolio = factory.portfolio(owner)
    assert portfolio.currency == "CHF"
    other = factory.portfolio(owner, name="Euro", currency="eur")
    assert other.currency == "EUR"
    with pytest.raises(ValidationError):
        portfolios.create_portfolio(
            session,
            owner,
            factory.clock,
            name="Bad",
            policy_id=portfolio.policy_id,
            currency="euro",
        )

    def change(currency: str) -> None:
        portfolios.update_settings(
            session,
            owner,
            portfolio.id,
            default_contribution=Decimal(0),
            precise_amounts=False,
            currency=currency,
        )

    change("usd")
    assert portfolio.currency == "USD"
    snapshots.create_snapshot(
        session,
        owner,
        factory.clock,
        portfolio.id,
        [ValueSpec("AAA", units=Decimal(1), price=Decimal(1))],
    )
    with pytest.raises(ConflictError):
        change("CHF")
    change("USD")  # unchanged is fine
    assert portfolio.currency == "USD"


@pytest.mark.req("PTF-04", "TL-01")
def test_reassignment_is_recorded_with_its_time(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    core = factory.active_policy(owner, name="core")
    growth = factory.active_policy(owner, name="growth")
    portfolio = factory.portfolio(owner, core, name="Main")
    created = factory.clock.now()
    moved = factory.clock.advance(days=10)
    portfolios.reassign_portfolio(session, owner, factory.clock, portfolio.id, growth.id)
    assert portfolio.policy_id == growth.id
    assert [(a.policy_id, a.valid_from) for a in portfolio.assignments] == [
        (core.id, created),
        (growth.id, moved),
    ]
    assert versioning.policy_at(portfolio, moved - timedelta(microseconds=1)) == core.id
    assert versioning.policy_at(portfolio, moved) == growth.id
    assert versioning.policy_at(portfolio, created - timedelta(days=1)) is None
    summaries = [
        e.summary for e in list_events(session, owner) if e.type == EventType.PORTFOLIO_ASSIGNED
    ]
    assert summaries == [
        "Portfolio Main created with policy core (core-v1)",
        "Portfolio Main reassigned to policy growth (growth-v1)",
    ]
    with pytest.raises(ConflictError):
        portfolios.reassign_portfolio(session, owner, factory.clock, portfolio.id, growth.id)


@pytest.mark.req("PTF-06")
def test_archive_keeps_history(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    portfolio = factory.portfolio(owner)
    archived = portfolios.archive_portfolio(session, owner, factory.clock, portfolio.id)
    assert archived.archived_at == factory.clock.now()
    assert portfolios.list_portfolios(session, owner) == [portfolio]


@pytest.mark.req("PTF-01")
def test_portfolio_names_are_unique_per_owner(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner)
    factory.portfolio(owner, policy, name="Main")
    with pytest.raises(ConflictError):
        factory.portfolio(owner, policy, name="Main")
