"""Theses and their revisions (THS-01 to THS-05, THS-08, TL-01).

A thesis is edited in a draft, like a policy version (THS-02): a revision is a draft
until it is activated, and immutable afterwards. Only the owner sees the draft.
"""

from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from yap.db.models import (
    Investor,
    Policy,
    PolicyVersion,
    Thesis,
    ThesisRevision,
)
from yap.domain.types import ThesisStatus, Visibility
from yap.messages import msg
from yap.services import reviews
from yap.services.common import (
    Clock,
    ConflictError,
    NotFoundError,
    ValidationError,
    get_owned,
    require_investor,
    require_text,
)
from yap.services.timeline import EventType, add_event
from yap.services.versioning import active_version


def _parse_status(status: ThesisStatus | str) -> ThesisStatus:
    try:
        return ThesisStatus(status)
    except ValueError:
        raise ValidationError.single(
            msg("thesis_status_unknown", status=str(status)), "status"
        ) from None


def _parse_visibility(visibility: Visibility | str) -> Visibility:
    try:
        return Visibility(visibility)
    except ValueError:
        raise ValidationError.single(
            msg("visibility_unknown", visibility=str(visibility)), "visibility"
        ) from None


def create_thesis(
    session: Session,
    actor: Investor,
    clock: Clock,
    *,
    title: str,
    content_md: str,
    visibility: Visibility | str = Visibility.PRIVATE,
    status: ThesisStatus | str = ThesisStatus.INTACT,
) -> Thesis:
    """A new thesis; its first revision is a draft (THS-02)."""
    require_investor(actor)
    now = clock.now()
    thesis = Thesis(
        owner_id=actor.id, visibility=_parse_visibility(visibility).value, created_at=now
    )
    session.add(thesis)
    session.flush()
    session.add(
        ThesisRevision(
            thesis_id=thesis.id,
            revision_no=1,
            title=require_text(title, "title", msg("title_required")),
            content_md=content_md,
            status=_parse_status(status).value,
            change_note=None,
            updated_at=now,
            created_at=now,
        )
    )
    session.flush()
    session.refresh(thesis)
    return thesis


def get_draft(thesis: Thesis) -> ThesisRevision | None:
    return next((r for r in thesis.revisions if r.is_draft), None)


def _require_draft(thesis: Thesis) -> ThesisRevision:
    draft = get_draft(thesis)
    if draft is None:
        raise NotFoundError(msg("thesis_has_no_draft", id=thesis.id))
    return draft


def create_draft(session: Session, actor: Investor, clock: Clock, thesis_id: int) -> ThesisRevision:
    """A new draft is a copy of the latest revision; at most one draft (THS-02)."""
    thesis = get_owned(session, Thesis, thesis_id, actor)
    if get_draft(thesis) is not None:
        raise ConflictError(msg("thesis_has_draft"))
    latest = latest_revision(thesis)
    now = clock.now()
    draft = ThesisRevision(
        thesis_id=thesis.id,
        revision_no=latest.revision_no + 1,
        title=latest.title,
        content_md=latest.content_md,
        status=latest.status,
        change_note=None,
        updated_at=now,
        created_at=now,
    )
    session.add(draft)
    session.flush()
    session.refresh(thesis)
    return draft


def update_draft(
    session: Session,
    actor: Investor,
    clock: Clock,
    thesis_id: int,
    *,
    title: str,
    content_md: str,
    status: ThesisStatus | str,
    change_note: str | None = None,
) -> ThesisRevision:
    """Saves the draft; it can be changed freely until it is activated (THS-02, THS-04)."""
    thesis = get_owned(session, Thesis, thesis_id, actor)
    draft = _require_draft(thesis)
    draft.title = require_text(title, "title", msg("title_required"))
    draft.content_md = content_md
    draft.status = _parse_status(status).value
    draft.change_note = change_note.strip() if change_note and change_note.strip() else None
    draft.updated_at = clock.now()
    session.flush()
    return draft


def delete_draft(session: Session, actor: Investor, thesis_id: int) -> None:
    thesis = get_owned(session, Thesis, thesis_id, actor)
    draft = _require_draft(thesis)
    if draft.revision_no == 1:
        raise ConflictError(msg("thesis_first_revision_kept"))
    reviews.delete_with_draft(session, draft)
    session.delete(draft)
    session.flush()
    session.refresh(thesis)


def activate_draft(
    session: Session, actor: Investor, clock: Clock, thesis_id: int, change_note: str | None
) -> ThesisRevision:
    """Activates the draft now; from revision 2 on it needs a change note (THS-03). The
    note given here replaces one saved with the draft."""
    thesis = get_owned(session, Thesis, thesis_id, actor)
    draft = _require_draft(thesis)
    note = (change_note or "").strip() or draft.change_note
    if draft.revision_no > 1 and not note:
        raise ValidationError.single(msg("change_note_required"), "change_note")
    now = clock.now()
    reviews.prepare_activation(session, draft)
    draft.change_note = note
    draft.activated_at = now
    session.flush()
    reviews.confirm_with_draft(session, draft, thesis.owner_id, now)  # REV-11
    _notify_policies_using(session, thesis, draft, now)
    session.refresh(thesis)
    return draft


def _notify_policies_using(
    session: Session, thesis: Thesis, revision: ThesisRevision, now: datetime
) -> None:
    """TL-01: investors whose active policy version pins an older revision get an event."""
    policies = session.scalars(
        select(Policy)
        .join(PolicyVersion, PolicyVersion.policy_id == Policy.id)
        .join(ThesisRevision, ThesisRevision.id == PolicyVersion.thesis_revision_id)
        .where(ThesisRevision.thesis_id == thesis.id)
        .distinct()
    )
    for policy in policies:
        version = active_version(policy, now)
        if version is None or version.thesis_revision.thesis_id != thesis.id:
            continue
        add_event(
            session,
            policy.owner_id,
            now,
            EventType.THESIS_REVISED,
            f"Thesis '{revision.title}' has a new revision {revision.revision_no} "
            f"(policy {version.label} uses revision {version.thesis_revision.revision_no})",
            {
                "title": revision.title,
                "revision": revision.revision_no,
                "version": version.label,
                "used_revision": version.thesis_revision.revision_no,
            },
            policy_version_id=version.id,
            thesis_revision_id=revision.id,
        )


def set_visibility(
    session: Session, actor: Investor, thesis_id: int, visibility: Visibility | str
) -> Thesis:
    thesis = get_owned(session, Thesis, thesis_id, actor)
    thesis.visibility = _parse_visibility(visibility).value
    return thesis


def copy_thesis(session: Session, actor: Investor, clock: Clock, thesis_id: int) -> Thesis:
    """THS-10: a private copy (as a draft) of the latest revision the investor can read."""
    source = get_readable_thesis(session, actor, thesis_id)
    revision = readable_revisions(session, actor, source)[-1]
    return create_thesis(
        session,
        actor,
        clock,
        title=revision.title,
        content_md=revision.content_md,
        visibility=Visibility.PRIVATE,
        status=revision.status,
    )


def latest_revision(thesis: Thesis) -> ThesisRevision:
    return thesis.revisions[-1]


def activated_revisions(revisions: list[ThesisRevision]) -> list[ThesisRevision]:
    """Only activated revisions can be pinned by a policy version (THS-02, POL-01)."""
    return [r for r in revisions if not r.is_draft]


def can_read_revision(session: Session, actor: Investor, revision: ThesisRevision) -> bool:
    """THS-05: owner, any investor if shared, and investors whose policy versions pin
    exactly this revision (they keep access if the thesis is made private again).
    A draft is visible only to the owner."""
    require_investor(actor)
    thesis = revision.thesis
    if thesis.owner_id == actor.id:
        return True
    if revision.is_draft:
        return False
    if thesis.visibility == Visibility.SHARED:
        return True
    return bool(
        session.scalar(
            select(
                exists()
                .where(PolicyVersion.thesis_revision_id == revision.id)
                .where(PolicyVersion.policy_id == Policy.id)
                .where(Policy.owner_id == actor.id)
            )
        )
    )


def get_readable_revision(session: Session, actor: Investor, revision_id: int) -> ThesisRevision:
    revision = session.get(ThesisRevision, revision_id)
    if revision is None or not can_read_revision(session, actor, revision):
        raise NotFoundError(msg("thesis_revision_not_found", id=revision_id))
    return revision


def get_readable_thesis(session: Session, actor: Investor, thesis_id: int) -> Thesis:
    thesis = session.get(Thesis, thesis_id)
    if thesis is None or not readable_revisions(session, actor, thesis):
        raise NotFoundError(msg("thesis_not_found", id=thesis_id))
    return thesis


def readable_revisions(session: Session, actor: Investor, thesis: Thesis) -> list[ThesisRevision]:
    return [r for r in thesis.revisions if can_read_revision(session, actor, r)]


def list_readable_theses(session: Session, actor: Investor) -> list[Thesis]:
    require_investor(actor)
    theses = session.scalars(select(Thesis).order_by(Thesis.id))
    return [t for t in theses if readable_revisions(session, actor, t)]
