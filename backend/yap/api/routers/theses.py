"""Theses (THS-01 to THS-10) and thesis import (IMP-01)."""

import difflib

from fastapi import APIRouter

from yap.api.deps import AppClock, CurrentUser, DbSession, RawBody
from yap.api.schemas import (
    Activation,
    NewThesis,
    ReviewBrief,
    RevisionDiff,
    RevisionOut,
    RevisionSummary,
    ThesisDraftIn,
    ThesisImportPreview,
    ThesisOut,
    ThesisSummary,
    VisibilityIn,
)
from yap.db.models import Investor, Thesis, ThesisRevision
from yap.imports import importer
from yap.messages import msg
from yap.services import theses
from yap.services.common import NotFoundError

router = APIRouter(tags=["theses"])


def _summary(revision: ThesisRevision) -> RevisionSummary:
    return RevisionSummary(
        id=revision.id,
        revision_no=revision.revision_no,
        title=revision.title,
        status=revision.status,
        change_note=revision.change_note,
        is_draft=revision.is_draft,
        activated_at=revision.activated_at,
        created_at=revision.created_at,
        review=ReviewBrief.of(revision),
    )


def _revision(revision: ThesisRevision) -> RevisionOut:
    return RevisionOut(
        **_summary(revision).model_dump(),
        thesis_id=revision.thesis_id,
        content_md=revision.content_md,
    )


def _thesis(session: DbSession, user: Investor, thesis: Thesis) -> ThesisOut:
    return ThesisOut(
        id=thesis.id,
        is_own=thesis.owner_id == user.id,
        visibility=thesis.visibility,
        created_at=thesis.created_at,
        revisions=[_summary(r) for r in theses.readable_revisions(session, user, thesis)],
    )


@router.get("/theses")
def list_theses(session: DbSession, user: CurrentUser) -> list[ThesisSummary]:
    result = []
    for thesis in theses.list_readable_theses(session, user):
        revisions = theses.readable_revisions(session, user, thesis)
        activated = theses.activated_revisions(revisions)
        result.append(
            ThesisSummary(
                id=thesis.id,
                is_own=thesis.owner_id == user.id,
                visibility=thesis.visibility,
                latest=_summary(revisions[-1]),
                has_draft=revisions[-1].is_draft,
                active_revision_no=activated[-1].revision_no if activated else None,
            )
        )
    return result


@router.post("/theses", status_code=201)
def create_thesis(
    body: NewThesis, session: DbSession, clock: AppClock, user: CurrentUser
) -> ThesisOut:
    thesis = theses.create_thesis(
        session,
        user,
        clock,
        title=body.title,
        content_md=body.content_md,
        visibility=body.visibility,
        status=body.status,
    )
    return _thesis(session, user, thesis)


@router.get("/theses/{thesis_id}")
def get_thesis(thesis_id: int, session: DbSession, user: CurrentUser) -> ThesisOut:
    return _thesis(session, user, theses.get_readable_thesis(session, user, thesis_id))


@router.post("/theses/{thesis_id}/draft", status_code=201)
def create_draft(
    thesis_id: int, session: DbSession, clock: AppClock, user: CurrentUser
) -> RevisionOut:
    """THS-02: a new draft as a copy of the latest revision."""
    return _revision(theses.create_draft(session, user, clock, thesis_id))


@router.put("/theses/{thesis_id}/draft")
def update_draft(
    thesis_id: int, body: ThesisDraftIn, session: DbSession, clock: AppClock, user: CurrentUser
) -> RevisionOut:
    draft = theses.update_draft(
        session,
        user,
        clock,
        thesis_id,
        title=body.title,
        content_md=body.content_md,
        status=body.status,
        change_note=body.change_note,
    )
    return _revision(draft)


@router.delete("/theses/{thesis_id}/draft", status_code=204)
def delete_draft(thesis_id: int, session: DbSession, user: CurrentUser) -> None:
    theses.delete_draft(session, user, thesis_id)


@router.post("/theses/{thesis_id}/draft/activate")
def activate_draft(
    thesis_id: int, body: Activation, session: DbSession, clock: AppClock, user: CurrentUser
) -> RevisionOut:
    """THS-02, THS-03: the draft becomes an immutable revision."""
    return _revision(theses.activate_draft(session, user, clock, thesis_id, body.change_note))


@router.put("/theses/{thesis_id}/visibility")
def set_visibility(
    thesis_id: int, body: VisibilityIn, session: DbSession, user: CurrentUser
) -> ThesisOut:
    return _thesis(session, user, theses.set_visibility(session, user, thesis_id, body.visibility))


@router.post("/theses/{thesis_id}/copy", status_code=201)
def copy_thesis(
    thesis_id: int, session: DbSession, clock: AppClock, user: CurrentUser
) -> ThesisOut:
    return _thesis(session, user, theses.copy_thesis(session, user, clock, thesis_id))


def _revision_by_no(
    session: DbSession, user: Investor, thesis_id: int, revision_no: int
) -> ThesisRevision:
    thesis = theses.get_readable_thesis(session, user, thesis_id)
    for revision in theses.readable_revisions(session, user, thesis):
        if revision.revision_no == revision_no:
            return revision
    raise NotFoundError(msg("thesis_revision_no_not_found", number=revision_no, id=thesis_id))


@router.get("/theses/{thesis_id}/revisions/{revision_no}")
def get_revision(
    thesis_id: int, revision_no: int, session: DbSession, user: CurrentUser
) -> RevisionOut:
    return _revision(_revision_by_no(session, user, thesis_id, revision_no))


@router.get("/theses/{thesis_id}/diff")
def diff_revisions(
    thesis_id: int, from_revision: int, to_revision: int, session: DbSession, user: CurrentUser
) -> RevisionDiff:
    """THS-02: compare any two readable revisions."""
    old = _revision_by_no(session, user, thesis_id, from_revision)
    new = _revision_by_no(session, user, thesis_id, to_revision)
    lines = difflib.unified_diff(
        f"# {old.title}\n{old.content_md}".splitlines(keepends=True),
        f"# {new.title}\n{new.content_md}".splitlines(keepends=True),
        fromfile=f"revision {old.revision_no}",
        tofile=f"revision {new.revision_no}",
    )
    return RevisionDiff(
        from_revision_no=old.revision_no,
        to_revision_no=new.revision_no,
        unified_diff="".join(lines),
    )


# --- Import (IMP-01, IMP-07) --------------------------------------------------


@router.post("/theses/import", status_code=201)
def import_new_thesis(
    body: RawBody, session: DbSession, clock: AppClock, user: CurrentUser
) -> RevisionOut:
    return _revision(importer.import_thesis(session, user, clock, body))


@router.post("/theses/import/preview")
def preview_new_thesis(body: RawBody, session: DbSession, user: CurrentUser) -> ThesisImportPreview:
    return ThesisImportPreview(**vars(importer.preview_thesis(session, user, body)))


@router.post("/theses/{thesis_id}/import", status_code=201)
def import_thesis_revision(
    thesis_id: int, body: RawBody, session: DbSession, clock: AppClock, user: CurrentUser
) -> RevisionOut:
    return _revision(importer.import_thesis(session, user, clock, body, thesis_id))


@router.post("/theses/{thesis_id}/import/preview")
def preview_thesis_revision(
    thesis_id: int, body: RawBody, session: DbSession, user: CurrentUser
) -> ThesisImportPreview:
    return ThesisImportPreview(**vars(importer.preview_thesis(session, user, body, thesis_id)))


@router.get("/thesis-revisions/{revision_id}")
def get_revision_by_id(revision_id: int, session: DbSession, user: CurrentUser) -> RevisionOut:
    """A revision addressed by its own ID (e.g. from a timeline event, TL-02)."""
    return _revision(theses.get_readable_revision(session, user, revision_id))
