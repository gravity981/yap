"""Policies and versions with their thesis (POL-01 to POL-13), import of theses and target
structures (IMP-01, IMP-02)."""

from typing import Any

from fastapi import APIRouter

from yap.api.deps import AppClock, CurrentUser, DbSession, RawBody
from yap.api.schemas import (
    Activation,
    DraftIn,
    NewPolicy,
    PolicyOut,
    PolicySummary,
    PortfolioRef,
    PositionChangeOut,
    ThesisImportPreview,
    VersionDiffOut,
    VersionOut,
    VersionRef,
    version_summary,
)
from yap.db.models import Investor, Policy, PolicyVersion
from yap.domain.types import ThesisStatus
from yap.imports import importer
from yap.messages import msg
from yap.services import policies
from yap.services.common import Clock, NotFoundError
from yap.services.policies import PositionSpec, ThesisSpec, VersionDiff
from yap.services.versioning import active_version, version_periods

router = APIRouter(prefix="/policies", tags=["policies"])


def _policy(session: DbSession, user: Investor, clock: Clock, policy: Policy) -> PolicyOut:
    active = active_version(policy, clock.now())
    return PolicyOut(
        id=policy.id,
        name=policy.name,
        archived_at=policy.archived_at,
        created_at=policy.created_at,
        versions=[
            version_summary(p.version, p.active_from, p.active_until)
            for p in version_periods(policy)
        ],
        portfolios=[
            PortfolioRef(id=p.id, name=p.name) for p in policies.portfolios_using(session, policy)
        ],
        **_thesis_warning(active),
    )


def _thesis_warning(active: PolicyVersion | None) -> dict[str, Any]:
    """POL-11: warn when the thesis of the active version needs adaptation or is broken."""
    status = active.thesis_status if active else None
    return {
        "thesis_warning": status is not None and status != ThesisStatus.INTACT.value,
        "thesis_status": status,
    }


def _version(policy: Policy, version: PolicyVersion) -> VersionOut:
    period = next(p for p in version_periods(policy) if p.version.id == version.id)
    return VersionOut.of(version, period.active_from, period.active_until)


def _version_by_no(policy: Policy, version_no: int) -> PolicyVersion:
    version = next((v for v in policy.versions if v.version_no == version_no), None)
    if version is None:
        raise NotFoundError(msg("policy_version_no_not_found", number=version_no, name=policy.name))
    return version


@router.get("")
def list_policies(session: DbSession, clock: AppClock, user: CurrentUser) -> list[PolicySummary]:
    result = []
    for policy in policies.list_policies(session, user):
        active = active_version(policy, clock.now())
        result.append(
            PolicySummary(
                id=policy.id,
                name=policy.name,
                archived_at=policy.archived_at,
                active_version_label=active.label if active else None,
                has_draft=policies.get_draft(policy) is not None,
                **_thesis_warning(active),
            )
        )
    return result


@router.post("", status_code=201)
def create_policy(
    body: NewPolicy, session: DbSession, clock: AppClock, user: CurrentUser
) -> PolicyOut:
    policy = policies.create_policy(
        session,
        user,
        clock,
        name=body.name,
        thesis_title=body.thesis_title,
        thesis_md=body.thesis_md,
        thesis_status=body.thesis_status,
    )
    return _policy(session, user, clock, policy)


@router.get("/{policy_id}")
def get_policy(policy_id: int, session: DbSession, clock: AppClock, user: CurrentUser) -> PolicyOut:
    return _policy(session, user, clock, policies.get_policy(session, user, policy_id))


@router.get("/{policy_id}/versions/{version_no}")
def get_version(
    policy_id: int, version_no: int, session: DbSession, user: CurrentUser
) -> VersionOut:
    policy = policies.get_policy(session, user, policy_id)
    return _version(policy, _version_by_no(policy, version_no))


def _diff(diff: VersionDiff) -> VersionDiffOut:
    return VersionDiffOut(
        positions=[
            PositionChangeOut(
                ticker=c.ticker,
                change=c.change,
                fields={k: (str(a), str(b)) for k, (a, b) in c.fields.items()},
            )
            for c in diff.positions
        ],
        thesis_changed=diff.thesis_changed,
        thesis_diff=diff.thesis_diff,
    )


@router.get("/{policy_id}/compare")
def compare_versions(
    policy_id: int, from_version: int, to_version: int, session: DbSession, user: CurrentUser
) -> VersionDiffOut:
    """POL-09."""
    policy = policies.get_policy(session, user, policy_id)
    return _diff(
        policies.compare_versions(
            _version_by_no(policy, from_version), _version_by_no(policy, to_version)
        )
    )


@router.post("/{policy_id}/draft", status_code=201)
def create_draft(
    policy_id: int, session: DbSession, clock: AppClock, user: CurrentUser
) -> VersionOut:
    draft = policies.create_draft(session, user, clock, policy_id)
    return _version(draft.policy, draft)


@router.put("/{policy_id}/draft")
def update_draft(
    policy_id: int, body: DraftIn, session: DbSession, clock: AppClock, user: CurrentUser
) -> VersionOut:
    draft = policies.update_draft(
        session,
        user,
        clock,
        policy_id,
        positions=[PositionSpec(**p.model_dump()) for p in body.positions],
        thesis=ThesisSpec(body.thesis.title, body.thesis.content_md, body.thesis.status)
        if body.thesis
        else None,
    )
    return _version(draft.policy, draft)


@router.delete("/{policy_id}/draft", status_code=204)
def delete_draft(policy_id: int, session: DbSession, user: CurrentUser) -> None:
    policies.delete_draft(session, user, policy_id)


@router.post("/{policy_id}/draft/activate")
def activate_draft(
    policy_id: int, body: Activation, session: DbSession, clock: AppClock, user: CurrentUser
) -> VersionOut:
    version = policies.activate_draft(session, user, clock, policy_id, body.change_note)
    return _version(version.policy, version)


@router.post("/{policy_id}/archive")
def archive_policy(
    policy_id: int, session: DbSession, clock: AppClock, user: CurrentUser
) -> PolicyOut:
    policy = policies.archive_policy(session, user, clock, policy_id)
    return _policy(session, user, clock, policy)


# --- Import (IMP-01, IMP-02, IMP-07) -----------------------------------------


@router.post("/import-thesis", status_code=201)
def import_thesis_as_policy(
    body: RawBody, session: DbSession, clock: AppClock, user: CurrentUser
) -> PolicyOut:
    """IMP-01: a new policy whose draft v1 holds the thesis of the file."""
    draft = importer.import_thesis(session, user, clock, body)
    return _policy(session, user, clock, draft.policy)


@router.post("/import-thesis/preview")
def preview_thesis_as_policy(
    body: RawBody, session: DbSession, user: CurrentUser
) -> ThesisImportPreview:
    return ThesisImportPreview(**vars(importer.preview_thesis(session, user, body)))


@router.post("/{policy_id}/import-thesis", status_code=201)
def import_thesis(
    policy_id: int, body: RawBody, session: DbSession, clock: AppClock, user: CurrentUser
) -> VersionOut:
    """IMP-01: replaces the thesis of the policy's draft (created if there is none)."""
    draft = importer.import_thesis(session, user, clock, body, policy_id)
    return _version(draft.policy, draft)


@router.post("/{policy_id}/import-thesis/preview")
def preview_thesis(
    policy_id: int, body: RawBody, session: DbSession, user: CurrentUser
) -> ThesisImportPreview:
    return ThesisImportPreview(**vars(importer.preview_thesis(session, user, body, policy_id)))


@router.post("/{policy_id}/import", status_code=201)
def import_target_structure(
    policy_id: int, body: RawBody, session: DbSession, clock: AppClock, user: CurrentUser
) -> VersionOut:
    draft = importer.import_target_structure(session, user, clock, body, policy_id)
    return _version(draft.policy, draft)


@router.post("/{policy_id}/import/preview")
def preview_target_structure(
    policy_id: int, body: RawBody, session: DbSession, user: CurrentUser
) -> VersionDiffOut:
    return _diff(importer.preview_target_structure(session, user, body, policy_id))


# Not under /policies: a version is addressed by its own ID here (TL-02)
versions_router = APIRouter(prefix="/policy-versions", tags=["policies"])


@versions_router.get("/{version_id}")
def get_version_by_id(version_id: int, session: DbSession, user: CurrentUser) -> VersionRef:
    version = policies.get_version(session, user, version_id)
    return VersionRef(
        **_version(version.policy, version).model_dump(),
        policy_id=version.policy_id,
        policy_name=version.policy.name,
    )
