from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from tests.fixtures import Factory
from yap.services import policies, versioning


@pytest.mark.req("POL-07", "CMP-03")
def test_active_version_is_latest_activation_at_or_before(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner)
    t1 = factory.clock.now()
    t2 = factory.clock.advance(days=1)
    policies.create_draft(session, owner, factory.clock, policy.id)
    policies.activate_draft(session, owner, factory.clock, policy.id, "v2")
    t3 = factory.clock.advance(days=1)
    policies.create_draft(session, owner, factory.clock, policy.id)
    policies.activate_draft(session, owner, factory.clock, policy.id, "v3")
    policies.create_draft(session, owner, factory.clock, policy.id)  # draft never counts

    def at(t):  # type: ignore[no-untyped-def]
        version = versioning.active_version(policy, t)
        return None if version is None else version.version_no

    assert at(t1 - timedelta(seconds=1)) is None
    assert at(t1) == 1
    assert at(t2) == 2
    assert at(t3 - timedelta(microseconds=1)) == 2
    assert at(t3 + timedelta(days=365)) == 3


@pytest.mark.req("POL-07")
def test_active_version_does_not_depend_on_list_order() -> None:
    from tests.fixtures import START
    from yap.db.models import Policy, PolicyVersion

    later = PolicyVersion(version_no=2, activated_at=START + timedelta(days=1))
    earlier = PolicyVersion(version_no=1, activated_at=START)
    policy = Policy(versions=[later, earlier])
    assert versioning.active_version(policy, START + timedelta(days=2)) is later


@pytest.mark.req("POL-07")
def test_same_instant_activations_are_ordered_by_version_number() -> None:
    from tests.fixtures import START
    from yap.db.models import Policy, PolicyVersion

    v2 = PolicyVersion(version_no=2, activated_at=START)
    v3 = PolicyVersion(version_no=3, activated_at=START)
    assert versioning.active_version(Policy(versions=[v2, v3]), START) is v3
    assert versioning.active_version(Policy(versions=[v3, v2]), START) is v3


@pytest.mark.req("POL-12")
def test_periods_of_policy_with_only_a_draft(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policy = policies.create_policy(session, owner, factory.clock, name="p")
    periods = versioning.version_periods(policy)
    assert [(p.version.version_no, p.active_from, p.active_until) for p in periods] == [
        (1, None, None)
    ]
