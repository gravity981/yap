"""AI reviewers: the LLMs that run reviews, configured by the admin (REV-13 to REV-15) and
chosen by each investor (USR-08)."""

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from yap.db.models import AiReviewer, Investor
from yap.llm import LlmConfig, LlmError, Provider
from yap.llm.base import AdapterFactory, unexpected_detail
from yap.messages import Message, msg
from yap.services.accounts import require_admin
from yap.services.common import (
    Clock,
    ConflictError,
    NotFoundError,
    ValidationError,
    require_investor,
)
from yap.services.secrets import KeyBox

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReviewerSpec:
    """What the admin enters; `api_key` replaces the stored key only when given."""

    name: str
    provider: str
    model: str
    monthly_review_limit: int
    description: str | None = None
    api_key: str | None = None
    enabled: bool = True


def list_reviewers(session: Session, actor: Investor) -> list[AiReviewer]:
    """All reviewers that are not archived, for the admin page (REV-14)."""
    require_admin(actor)
    return list(
        session.scalars(
            select(AiReviewer).where(AiReviewer.archived_at.is_(None)).order_by(AiReviewer.name)
        )
    )


def available_reviewers(session: Session, actor: Investor) -> list[AiReviewer]:
    """USR-08: the enabled reviewers an investor can choose from."""
    require_investor(actor)
    return list(
        session.scalars(
            select(AiReviewer)
            .where(AiReviewer.archived_at.is_(None), AiReviewer.enabled)
            .order_by(AiReviewer.name)
        )
    )


def get_reviewer(session: Session, reviewer_id: int) -> AiReviewer:
    """Archived reviewers are not found: they cannot be changed or chosen any more."""
    reviewer = session.get(AiReviewer, reviewer_id)
    if reviewer is None or reviewer.archived_at is not None:
        raise NotFoundError(msg("ai_reviewer_not_found", id=reviewer_id))
    return reviewer


def _check(
    session: Session, spec: ReviewerSpec, reviewer: AiReviewer | None, keys: KeyBox
) -> tuple[str, Provider, str, str | None]:
    problems: list[tuple[str, Message]] = []
    name = spec.name.strip()
    model = spec.model.strip()
    provider: Provider | None = None
    if not name:
        problems.append(("name", msg("ai_reviewer_name_required")))
    elif session.scalar(
        select(AiReviewer.id).where(
            AiReviewer.name == name,
            AiReviewer.archived_at.is_(None),
            AiReviewer.id != (reviewer.id if reviewer else -1),
        )
    ):
        problems.append(("name", msg("ai_reviewer_name_taken", name=name)))
    try:
        provider = Provider(spec.provider)
    except ValueError:
        problems.append(("provider", msg("provider_unknown", provider=spec.provider)))
    if not model:
        problems.append(("model", msg("model_required")))
    if spec.monthly_review_limit < 0:
        problems.append(("monthly_review_limit", msg("limit_negative")))
    new_key = (spec.api_key or "").strip() or None
    if reviewer is None and new_key is None:
        problems.append(("api_key", msg("api_key_required")))
    if new_key and not keys.available:
        problems.append(("api_key", msg("api_key_no_secret")))
    if problems:
        raise ValidationError(problems)
    assert provider is not None
    return name, provider, model, new_key


def _apply(
    reviewer: AiReviewer,
    spec: ReviewerSpec,
    keys: KeyBox,
    checked: tuple[str, Provider, str, str | None],
) -> None:
    name, provider, model, new_key = checked
    reviewer.name = name
    reviewer.description = (spec.description or "").strip() or None
    reviewer.provider = provider.value
    reviewer.model = model
    reviewer.monthly_review_limit = spec.monthly_review_limit
    reviewer.enabled = spec.enabled
    if new_key:
        reviewer.api_key_encrypted = keys.encrypt(new_key)
        reviewer.api_key_last4 = new_key[-4:]


def create_reviewer(
    session: Session, actor: Investor, clock: Clock, keys: KeyBox, spec: ReviewerSpec
) -> AiReviewer:
    """REV-13, REV-15: any number of reviewers, each with its own key."""
    require_admin(actor)
    checked = _check(session, spec, None, keys)
    now = clock.now()
    reviewer = AiReviewer(archived_at=None, created_at=now, updated_at=now)
    _apply(reviewer, spec, keys, checked)
    session.add(reviewer)
    session.flush()
    return reviewer


def update_reviewer(
    session: Session,
    actor: Investor,
    clock: Clock,
    keys: KeyBox,
    reviewer_id: int,
    spec: ReviewerSpec,
) -> AiReviewer:
    """REV-14: applies to reviews started afterwards."""
    require_admin(actor)
    reviewer = get_reviewer(session, reviewer_id)
    _apply(reviewer, spec, keys, _check(session, spec, reviewer, keys))
    reviewer.updated_at = clock.now()
    session.flush()
    return reviewer


def archive_reviewer(session: Session, actor: Investor, clock: Clock, reviewer_id: int) -> None:
    """REV-13: instead of deleting; past reviews and runs keep it, investors who chose it
    must choose another one."""
    require_admin(actor)
    reviewer = get_reviewer(session, reviewer_id)
    reviewer.archived_at = clock.now()
    reviewer.updated_at = reviewer.archived_at


def llm_config(reviewer: AiReviewer, keys: KeyBox) -> LlmConfig:
    return LlmConfig(
        Provider(reviewer.provider), reviewer.model, keys.decrypt(reviewer.api_key_encrypted)
    )


@dataclass(frozen=True)
class ConnectionResult:
    ok: bool
    message: Message


def test_connection(
    session: Session, actor: Investor, keys: KeyBox, adapters: AdapterFactory, reviewer_id: int
) -> ConnectionResult:
    """REV-14: checks the key and the model with one request to the provider."""
    require_admin(actor)
    reviewer = get_reviewer(session, reviewer_id)
    try:
        config = llm_config(reviewer, keys)
    except ConflictError as e:
        return ConnectionResult(False, e.message)
    try:
        adapters(config).check()
    except LlmError as e:
        return ConnectionResult(False, e.message)
    except Exception as e:
        log.exception("Connection test of AI reviewer %s failed", reviewer_id)
        detail = unexpected_detail(e, config.api_key)
        return ConnectionResult(False, msg("test_failed_unexpectedly", detail=detail))
    message = msg("connection_ok", provider=config.provider.value, model=config.model)
    return ConnectionResult(True, message)


def choose_reviewer(session: Session, actor: Investor, reviewer_id: int | None) -> Investor:
    """USR-08: the investor's own choice; None clears it."""
    require_investor(actor)
    if reviewer_id is None:
        actor.ai_reviewer_id = None
        return actor
    reviewer = get_reviewer(session, reviewer_id)
    if not reviewer.enabled:
        raise ConflictError(msg("ai_reviewer_disabled", name=reviewer.name))
    actor.ai_reviewer_id = reviewer.id
    return actor
