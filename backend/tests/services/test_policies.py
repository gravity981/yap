from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from tests.fixtures import Factory, spec
from yap.services import policies, versioning
from yap.services.common import ConflictError, NotFoundError, ValidationError
from yap.services.timeline import EventType, list_events


@pytest.mark.req("POL-01", "POL-02", "THS-01", "THS-04")
def test_a_new_policy_starts_as_draft_v1_with_its_thesis(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    policy = policies.create_policy(
        session, owner, factory.clock, name=" core ", thesis_md="# Investment Thesis"
    )
    (draft,) = policy.versions
    assert (policy.name, draft.version_no, draft.activated_at) == ("core", 1, None)
    assert (draft.thesis_title, draft.thesis_md) == (
        "core",  # the title defaults to the name
        "# Investment Thesis",
    )
    assert draft.positions == []
    # A thesis has no status set by the investor (THS-04)
    assert not hasattr(draft, "thesis_status")


@pytest.mark.req("POL-02", "THS-01")
def test_the_draft_holds_the_thesis_and_activation_freezes_it(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    policy = factory.policy_draft(owner, positions=[spec("AAA", 100)])
    thesis = policies.ThesisSpec("Growth", "# New text")
    draft = policies.update_thesis(session, owner, factory.clock, policy.id, thesis)
    assert (draft.thesis_title, draft.thesis_md) == ("Growth", "# New text")
    with pytest.raises(ValidationError) as err:
        policies.update_thesis(
            session, owner, factory.clock, policy.id, policies.ThesisSpec(" ", "")
        )
    assert err.value.problems[0][0] == "thesis_title"
    policies.activate_draft(session, owner, factory.clock, policy.id, None)
    with pytest.raises(NotFoundError):  # no draft any more
        policies.update_thesis(session, owner, factory.clock, policy.id, thesis)
    draft = policies.create_draft(session, owner, factory.clock, policy.id)
    assert (draft.thesis_title, draft.thesis_md) == ("Growth", "# New text")  # copied


@pytest.mark.req("POL-01")
def test_policy_names_are_unique_per_owner(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policies.create_policy(session, owner, factory.clock, name="core")
    with pytest.raises(ConflictError):
        policies.create_policy(session, owner, factory.clock, name="core")
    policies.create_policy(session, factory.investor(), factory.clock, name="core")


@pytest.mark.req("POL-02", "POL-03")
def test_draft_holds_target_structure_and_normalizes_tickers(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    policy = policies.create_policy(session, owner, factory.clock, name="core")
    draft = policies.update_draft(
        session,
        owner,
        factory.clock,
        policy.id,
        positions=[spec(" eth ", 60, type="crypto", exit=True), spec("XUS", 40)],
    )
    assert [(p.asset.ticker, p.exit) for p in draft.positions] == [("ETH", True), ("XUS", False)]


@pytest.mark.req("POL-04")
@pytest.mark.parametrize(
    ("position", "field"),
    [
        (spec("A", 100, buy=1), "buy_threshold_pct"),
        (spec("A", 100, buy=-101), "buy_threshold_pct"),
        (spec("A", 100, sell=-1), "sell_threshold_pct"),
        (spec("A", 101), "target_pct"),
    ],
)
def test_threshold_ranges(session: Session, factory: Factory, position, field) -> None:  # type: ignore[no-untyped-def]
    owner = factory.investor()
    policy = policies.create_policy(session, owner, factory.clock, name="p")
    with pytest.raises(ValidationError) as err:
        policies.update_draft(session, owner, factory.clock, policy.id, positions=[position])
    assert err.value.problems == [(f"positions[0].{field}", err.value.problems[0][1])]


@pytest.mark.req("POL-05")
def test_activation_requires_targets_summing_to_100(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policy = policies.create_policy(session, owner, factory.clock, name="p")
    policies.update_draft(session, owner, factory.clock, policy.id, positions=[spec("A", 90)])
    with pytest.raises(ValidationError, match="differs from 100"):
        policies.activate_draft(session, owner, factory.clock, policy.id, None)


@pytest.mark.req("POL-05")
def test_at_most_one_cash_buffer(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policy = policies.create_policy(session, owner, factory.clock, name="p")
    with pytest.raises(ValidationError, match="cash buffer"):
        policies.update_draft(
            session,
            owner,
            factory.clock,
            policy.id,
            positions=[spec("C1", 50, type="cash_buffer"), spec("C2", 50, type="cash_buffer")],
        )


@pytest.mark.req("POL-06")
def test_one_draft_at_a_time_copied_from_latest(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner)
    draft = policies.create_draft(session, owner, factory.clock, policy.id)
    assert draft.version_no == 2
    assert [p.asset.ticker for p in draft.positions] == ["AAA", "BBB"]
    with pytest.raises(ConflictError):
        policies.create_draft(session, owner, factory.clock, policy.id)
    policies.delete_draft(session, owner, policy.id)
    assert [v.version_no for v in policy.versions] == [1]


@pytest.mark.req("POL-06")
def test_change_note_required_from_v2(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner)  # v1 activated without note
    policies.create_draft(session, owner, factory.clock, policy.id)
    with pytest.raises(ValidationError, match="change note"):
        policies.activate_draft(session, owner, factory.clock, policy.id, " ")
    version = policies.activate_draft(session, owner, factory.clock, policy.id, "Rebalanced")
    assert version.change_note == "Rebalanced"


@pytest.mark.req("POL-16")
def test_discarding_the_first_draft_deletes_the_policy(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policy = policies.create_policy(session, owner, factory.clock, name="p")
    assert policies.delete_draft(session, owner, policy.id) is True
    with pytest.raises(NotFoundError):
        policies.get_policy(session, owner, policy.id)
    with pytest.raises(NotFoundError):  # nothing left to discard
        policies.delete_draft(session, owner, policy.id)


@pytest.mark.req("POL-07", "NFR-14")
def test_active_version_changes_at_the_moment_of_activation(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner)
    v1_activated = factory.clock.now()
    factory.clock.advance(days=180)
    policies.create_draft(session, owner, factory.clock, policy.id)
    v2 = policies.activate_draft(session, owner, factory.clock, policy.id, "v2")
    v2_activated = factory.clock.now()
    just_before = timedelta(microseconds=1)

    def version_at(t: datetime) -> int | None:
        version = versioning.active_version(policy, t)
        return None if version is None else version.version_no

    assert version_at(v1_activated - just_before) is None
    assert version_at(v1_activated) == 1
    assert version_at(v2_activated - just_before) == 1
    assert version_at(v2_activated) == 2
    assert v2.activated_at == v2_activated


@pytest.mark.req("POL-08", "TL-01")
def test_activation_lists_affected_portfolios(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner, name="core")
    factory.portfolio(owner, policy, name="Main")
    factory.portfolio(owner, policy, name="Extra")
    assert [p.name for p in policies.portfolios_using(session, policy)] == ["Extra", "Main"]
    policies.create_draft(session, owner, factory.clock, policy.id)
    policies.activate_draft(session, owner, factory.clock, policy.id, "Less BTC")
    event = list_events(session, owner)[-1]
    assert event.type == EventType.POLICY_ACTIVATED
    assert event.summary == "core-v2 activated (Extra, Main): Less BTC"


@pytest.mark.req("POL-09")
def test_compare_versions(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner, [spec("AAA", 60), spec("BBB", 40)])
    policies.create_draft(session, owner, factory.clock, policy.id)
    policies.update_draft(
        session,
        owner,
        factory.clock,
        policy.id,
        positions=[spec("AAA", 50, sell=30), spec("CCC", 50)],
    )
    v1, v2 = policy.versions
    diff = policies.compare_versions(v1, v2)
    assert [(c.ticker, c.change) for c in diff.positions] == [
        ("AAA", "changed"),
        ("CCC", "added"),
        ("BBB", "removed"),
    ]
    assert diff.positions[0].fields == {
        "target_pct": (Decimal(60), Decimal(50)),
        "sell_threshold_pct": (Decimal(20), Decimal(30)),
    }
    assert (diff.thesis_changed, diff.thesis_diff) == (False, "")
    policies.update_thesis(
        session,
        owner,
        factory.clock,
        policy.id,
        policies.ThesisSpec("Core thesis", "# New"),
    )
    diff = policies.compare_versions(v1, v2)
    assert diff.thesis_changed is True
    assert "-# Thesis\n+# New\n" in diff.thesis_diff


@pytest.mark.req("POL-12")
def test_versions_with_activation_periods(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner)
    t1 = factory.clock.now()
    t2 = factory.clock.advance(days=30)
    policies.create_draft(session, owner, factory.clock, policy.id)
    policies.activate_draft(session, owner, factory.clock, policy.id, "v2")
    policies.create_draft(session, owner, factory.clock, policy.id)
    periods = versioning.version_periods(policy)
    assert [(p.version.version_no, p.active_from, p.active_until) for p in periods] == [
        (1, t1, t2),
        (2, t2, None),
        (3, None, None),
    ]


@pytest.mark.req("POL-13")
def test_archive_only_without_portfolios(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    used = factory.active_policy(owner)
    factory.portfolio(owner, used)
    with pytest.raises(ConflictError):
        policies.archive_policy(session, owner, factory.clock, used.id)
    unused = factory.active_policy(owner)
    archived = policies.archive_policy(session, owner, factory.clock, unused.id)
    assert archived.archived_at == factory.clock.now()
    with pytest.raises(ConflictError):
        policies.create_draft(session, owner, factory.clock, unused.id)


@pytest.mark.req("USR-04")
def test_policies_of_others_are_not_found(session: Session, factory: Factory) -> None:
    owner, other = factory.investor(), factory.investor()
    policy = factory.active_policy(owner)
    with pytest.raises(NotFoundError):
        policies.get_policy(session, other, policy.id)
    with pytest.raises(NotFoundError):
        policies.get_version(session, other, policy.versions[0].id)
