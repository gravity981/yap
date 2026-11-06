import pytest
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from tests.fixtures import Factory
from yap.services import policies, theses
from yap.services.common import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from yap.services.timeline import EventType, list_events


def _save_draft(factory: Factory, owner: object, thesis_id: int, **fields: str) -> None:
    values = {"title": "Core thesis", "content_md": "# Draft", "status": "intact", **fields}
    theses.update_draft(factory.session, owner, factory.clock, thesis_id, **values)  # type: ignore[arg-type]


@pytest.mark.req("THS-01", "THS-02")
def test_a_new_thesis_starts_as_draft_and_becomes_a_revision_on_activation(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    thesis = factory.thesis(owner, activate=False)
    draft = thesis.revisions[0]
    assert draft.is_draft and draft.revision_no == 1
    _save_draft(factory, owner, thesis.id, content_md="# Second save")
    _save_draft(factory, owner, thesis.id, content_md="# Third save")
    assert [r.revision_no for r in thesis.revisions] == [1]
    revision = theses.activate_draft(session, owner, factory.clock, thesis.id, None)
    assert not revision.is_draft and revision.activated_at == factory.clock.now()
    assert revision.content_md == "# Third save"


@pytest.mark.req("THS-02")
def test_a_new_draft_copies_the_latest_revision_and_there_is_only_one(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    thesis = factory.thesis(owner)
    draft = theses.create_draft(session, owner, factory.clock, thesis.id)
    assert (draft.revision_no, draft.content_md, draft.is_draft) == (2, "# Thesis", True)
    with pytest.raises(ConflictError):
        theses.create_draft(session, owner, factory.clock, thesis.id)
    _save_draft(factory, owner, thesis.id, content_md="# Updated")
    assert thesis.revisions[0].content_md == "# Thesis"


@pytest.mark.req("THS-02")
def test_a_draft_can_be_deleted_except_the_first_revision(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    new = factory.thesis(owner, activate=False)
    with pytest.raises(ConflictError):
        theses.delete_draft(session, owner, new.id)
    thesis = factory.thesis(owner)
    theses.create_draft(session, owner, factory.clock, thesis.id)
    theses.delete_draft(session, owner, thesis.id)
    assert [r.revision_no for r in thesis.revisions] == [1]


@pytest.mark.req("THS-02", "NFR-05")
def test_activated_revisions_are_immutable(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    thesis = factory.thesis(owner)
    with pytest.raises(NotFoundError):
        _save_draft(factory, owner, thesis.id)
    revision = thesis.revisions[0]
    revision.content_md = "rewritten"
    with pytest.raises(DatabaseError, match="immutable"):
        session.flush()


@pytest.mark.req("THS-03")
def test_activation_after_the_first_revision_needs_a_change_note(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    thesis = factory.thesis(owner)
    assert thesis.revisions[0].change_note is None
    theses.create_draft(session, owner, factory.clock, thesis.id)
    with pytest.raises(ValidationError) as err:
        theses.activate_draft(session, owner, factory.clock, thesis.id, "  ")
    assert err.value.problems[0][0] == "change_note"
    # A note saved with the draft is enough
    _save_draft(factory, owner, thesis.id, change_note="New drivers")
    revision = theses.activate_draft(session, owner, factory.clock, thesis.id, None)
    assert revision.change_note == "New drivers"


@pytest.mark.req("THS-04")
def test_status_is_changed_in_a_draft(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    thesis = factory.thesis(owner)
    revision = factory.revise_thesis(owner, thesis, status="needs_adaptation")
    assert revision.status == "needs_adaptation"
    revision = factory.revise_thesis(owner, thesis, status="broken")
    assert [r.status for r in thesis.revisions] == ["intact", "needs_adaptation", "broken"]


@pytest.mark.req("THS-04")
def test_unknown_status_is_rejected(session: Session, factory: Factory) -> None:
    with pytest.raises(ValidationError):
        theses.create_thesis(
            session, factory.investor(), factory.clock, title="t", content_md="", status="soft"
        )


@pytest.mark.req("THS-05")
def test_only_the_owner_edits(session: Session, factory: Factory) -> None:
    owner, other = factory.investor(), factory.investor()
    thesis = factory.thesis(owner, shared=True)
    with pytest.raises(NotFoundError):
        theses.create_draft(session, other, factory.clock, thesis.id)
    theses.create_draft(session, owner, factory.clock, thesis.id)
    with pytest.raises(NotFoundError):
        _save_draft(factory, other, thesis.id)
    with pytest.raises(NotFoundError):
        theses.activate_draft(session, other, factory.clock, thesis.id, "x")


@pytest.mark.req("THS-05", "THS-02")
def test_drafts_are_visible_only_to_the_owner(session: Session, factory: Factory) -> None:
    owner, other = factory.investor(), factory.investor()
    unpublished = factory.thesis(owner, title="new", shared=True, activate=False)
    thesis = factory.thesis(owner, shared=True)
    draft = theses.create_draft(session, owner, factory.clock, thesis.id)
    assert [t.id for t in theses.list_readable_theses(session, other)] == [thesis.id]
    assert theses.readable_revisions(session, other, thesis) == [thesis.revisions[0]]
    assert theses.readable_revisions(session, owner, thesis)[-1] == draft
    with pytest.raises(NotFoundError):
        theses.get_readable_revision(session, other, draft.id)
    with pytest.raises(NotFoundError):
        theses.get_readable_thesis(session, other, unpublished.id)


@pytest.mark.req("THS-05")
def test_shared_theses_are_readable_by_all_private_only_by_owner(
    session: Session, factory: Factory
) -> None:
    owner, other = factory.investor(), factory.investor()
    shared = factory.thesis(owner, title="shared", shared=True)
    private = factory.thesis(owner, title="private")
    assert [t.id for t in theses.list_readable_theses(session, other)] == [shared.id]
    with pytest.raises(NotFoundError):
        theses.get_readable_thesis(session, other, private.id)


@pytest.mark.req("THS-05")
def test_access_to_pinned_revision_survives_making_thesis_private(
    session: Session, factory: Factory
) -> None:
    owner, other = factory.investor(), factory.investor()
    thesis = factory.thesis(owner, shared=True)
    factory.active_policy(other, thesis=thesis)
    pinned = thesis.revisions[0]
    revision2 = factory.revise_thesis(owner, thesis, content_md="v2")
    theses.set_visibility(session, owner, thesis.id, "private")
    assert theses.get_readable_revision(session, other, pinned.id) == pinned
    with pytest.raises(NotFoundError):
        theses.get_readable_revision(session, other, revision2.id)


@pytest.mark.req("THS-10")
def test_a_copy_starts_as_a_private_draft(session: Session, factory: Factory) -> None:
    owner, other = factory.investor(), factory.investor()
    thesis = factory.thesis(owner, shared=True)
    copy = theses.copy_thesis(session, other, factory.clock, thesis.id)
    assert copy.owner_id == other.id and copy.visibility == "private"
    assert copy.revisions[0].is_draft


@pytest.mark.req("USR-05")
def test_admin_has_no_theses(session: Session, factory: Factory) -> None:
    with pytest.raises(ForbiddenError):
        theses.create_thesis(session, factory.admin(), factory.clock, title="t", content_md="")


@pytest.mark.req("TL-01", "POL-10")
def test_activating_a_revision_of_a_used_thesis_is_announced(
    session: Session, factory: Factory
) -> None:
    owner, user = factory.investor(), factory.investor()
    thesis = factory.thesis(owner, shared=True)
    policy = factory.active_policy(user, thesis=thesis)
    factory.clock.advance(hours=1)
    theses.create_draft(session, owner, factory.clock, thesis.id)
    _save_draft(factory, owner, thesis.id, status="broken")
    # A draft is no newer revision yet, and creates no event (TL-01)
    assert policies.newer_thesis_revision(session, user, policy, factory.clock.now()) is None
    assert EventType.THESIS_REVISED not in [e.type for e in list_events(session, user)]
    theses.activate_draft(session, owner, factory.clock, thesis.id, "Broken")
    events = list_events(session, user)
    assert [e.type for e in events][-1] == EventType.THESIS_REVISED
    assert events[-1].occurred_at == factory.clock.now()
    assert events[-1].params == {
        "title": thesis.revisions[-1].title,
        "revision": 2,
        "version": f"{policy.name}-v1",
        "used_revision": 1,
    }
    newer = policies.newer_thesis_revision(session, user, policy, factory.clock.now())
    assert newer is not None and newer.revision_no == 2
