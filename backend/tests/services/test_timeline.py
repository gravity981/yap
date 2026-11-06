import pytest
from sqlalchemy.orm import Session

from tests.fixtures import Factory
from yap.services import policies, portfolios
from yap.services.timeline import EventType, TimelineFilter, list_events


@pytest.mark.req("TL-01", "TL-03")
def test_filter_by_portfolio_includes_its_policies_while_they_applied(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    core = factory.active_policy(owner, name="core")
    growth = factory.active_policy(owner, name="growth")
    factory.clock.advance(hours=1)  # v1 activations happen before Main exists
    main = factory.portfolio(owner, core, name="Main")
    factory.portfolio(owner, growth, name="Other")

    factory.clock.advance(days=1)
    policies.create_draft(session, owner, factory.clock, core.id)
    policies.activate_draft(
        session, owner, factory.clock, core.id, "core change while Main uses it"
    )
    factory.clock.advance(days=1)
    portfolios.reassign_portfolio(session, owner, factory.clock, main.id, growth.id)
    factory.clock.advance(days=1)
    policies.create_draft(session, owner, factory.clock, core.id)
    policies.activate_draft(session, owner, factory.clock, core.id, "core change after Main left")
    policies.create_draft(session, owner, factory.clock, growth.id)
    policies.activate_draft(session, owner, factory.clock, growth.id, "growth change")

    summaries = [
        e.summary for e in list_events(session, owner, TimelineFilter(portfolio_id=main.id))
    ]
    assert summaries == [
        "Portfolio Main created with policy core (core-v1)",
        "core-v2 activated (Main): core change while Main uses it",
        "Portfolio Main reassigned to policy growth (growth-v1)",
        "growth-v2 activated (Main, Other): growth change",
    ]
    # The values of the summaries, for the timeline in the UI's language (TL-02, NFR-10)
    params = [e.params for e in list_events(session, owner, TimelineFilter(portfolio_id=main.id))]
    assert params == [
        {"portfolio": "Main", "policy": "core", "version": "core-v1", "created": True},
        {"version": "core-v2", "portfolios": ["Main"], "note": "core change while Main uses it"},
        {"portfolio": "Main", "policy": "growth", "version": "growth-v1", "created": False},
        {"version": "growth-v2", "portfolios": ["Main", "Other"], "note": "growth change"},
    ]


@pytest.mark.req("TL-03")
def test_filter_by_policy_type_and_period(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    start = factory.clock.now()
    core = factory.active_policy(owner, name="core")
    factory.active_policy(owner, name="growth")
    factory.portfolio(owner, core, name="Main")
    end = factory.clock.advance(days=1)
    policies.create_draft(session, owner, factory.clock, core.id)
    policies.activate_draft(session, owner, factory.clock, core.id, "later")

    by_policy = list_events(session, owner, TimelineFilter(policy_id=core.id))
    assert all(e.summary.startswith(("core", "Portfolio Main")) for e in by_policy)
    activations = list_events(
        session,
        owner,
        TimelineFilter(types=frozenset({EventType.POLICY_ACTIVATED}), start=start, end=end),
    )
    assert [e.summary for e in activations] == [
        "core-v1 activated (no portfolios)",
        "growth-v1 activated (no portfolios)",
    ]


@pytest.mark.req("TL-01", "USR-04")
def test_timeline_contains_only_own_events(session: Session, factory: Factory) -> None:
    owner, other = factory.investor(), factory.investor()
    factory.active_policy(owner)
    assert list_events(session, other) == []
