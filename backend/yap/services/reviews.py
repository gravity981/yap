"""Thesis and policy reviews of drafts (REV-01 to REV-17).

A review is started on a draft, runs in the background (REV-08) and is confirmed by
activating the draft (REV-11). Every started run counts towards the monthly limit of its
AI reviewer (REV-16).
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from yap.db.models import (
    AiReviewer,
    Investor,
    Policy,
    PolicyVersion,
    Review,
    ReviewAspect,
    ReviewRun,
    ReviewSource,
    ReviewSuggestion,
    Thesis,
    ThesisRevision,
)
from yap.domain.reviews import (
    SCORING_VERSION,
    ReviewKind,
    aspects_of,
    total_half_points,
)
from yap.llm import LlmError
from yap.llm.base import AdapterFactory, LlmRequest, unexpected_detail
from yap.messages import Message, msg
from yap.services import review_prompts
from yap.services.ai_reviewers import llm_config
from yap.services.common import (
    Clock,
    ConflictError,
    NotFoundError,
    ValidationError,
    get_owned,
    require_investor,
)
from yap.services.secrets import KeyBox
from yap.services.timeline import EventType, add_event

log = logging.getLogger(__name__)

NEWS_DAYS_DEFAULT = 90  # REV-04
NEWS_DAYS_MAX = 365
UNFINISHED = ("queued", "running")


# --- Limit (REV-16) --------------------------------------------------------------------


@dataclass(frozen=True)
class Usage:
    """For one AI reviewer: the one chosen for a review, or the investor's default."""

    reviewer_id: int | None
    reviewer_name: str | None
    used: int
    limit: int
    unavailable_reason: Message | None  # set if the investor cannot start a review now

    @property
    def left(self) -> int:
        return max(self.limit - self.used, 0)


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _unavailable(reviewer: AiReviewer, keys: KeyBox) -> Message | None:
    """Why reviews cannot run on this reviewer, independent of the limit."""
    if reviewer.archived_at is not None:
        return msg("review_reviewer_archived", name=reviewer.name)
    if not reviewer.enabled:
        return msg("review_reviewer_disabled", name=reviewer.name)
    try:
        llm_config(reviewer, keys)
    except ConflictError as e:
        return msg("review_reviewer_unusable", name=reviewer.name, detail=str(e))
    return None


def usage(
    session: Session,
    actor: Investor,
    clock: Clock,
    keys: KeyBox,
    reviewer_id: int | None = None,
) -> Usage:
    """Reviews used and left this calendar month (UTC) on the given reviewer, or on the
    investor's default (USR-08), and why none can be started."""
    require_investor(actor)
    chosen = reviewer_id if reviewer_id is not None else actor.ai_reviewer_id
    reviewer = session.get(AiReviewer, chosen) if chosen is not None else None
    if reviewer is None and reviewer_id is not None:
        raise NotFoundError(msg("review_reviewer_not_found", id=reviewer_id))
    if reviewer is None:
        return Usage(None, None, 0, 0, msg("review_choose_reviewer"))
    used = (
        session.scalar(
            select(func.count())
            .select_from(ReviewRun)
            .where(
                ReviewRun.investor_id == actor.id,
                ReviewRun.ai_reviewer_id == reviewer.id,
                ReviewRun.started_at >= _month_start(clock.now()),
            )
        )
        or 0
    )
    limit = reviewer.monthly_review_limit
    reason = _unavailable(reviewer, keys)
    if reason is None and limit == 0:
        reason = msg("review_reviewer_no_reviews", name=reviewer.name)
    elif reason is None and used >= limit:
        reason = msg("review_limit_reached", limit=limit, name=reviewer.name)
    return Usage(reviewer.id, reviewer.name, used, limit, reason)


# --- Start -----------------------------------------------------------------------------


def _thesis_draft(session: Session, actor: Investor, thesis_id: int) -> ThesisRevision:
    thesis = get_owned(session, Thesis, thesis_id, actor)
    draft = next((r for r in thesis.revisions if r.is_draft), None)
    if draft is None:
        raise NotFoundError(msg("review_thesis_no_draft", id=thesis_id))
    return draft


def _policy_draft(session: Session, actor: Investor, policy_id: int) -> PolicyVersion:
    policy = get_owned(session, Policy, policy_id, actor)
    draft = next((v for v in policy.versions if v.activated_at is None), None)
    if draft is None:
        raise NotFoundError(msg("review_policy_no_draft", name=policy.name))
    return draft


def draft_review(session: Session, draft: ThesisRevision | PolicyVersion) -> Review | None:
    column = (
        Review.thesis_revision_id if isinstance(draft, ThesisRevision) else Review.policy_version_id
    )
    return session.scalar(select(Review).where(column == draft.id))


def _start(
    session: Session,
    actor: Investor,
    clock: Clock,
    keys: KeyBox,
    kind: ReviewKind,
    draft: ThesisRevision | PolicyVersion,
    news_days: int | None = None,
    reviewer_id: int | None = None,
) -> Review:
    status = usage(session, actor, clock, keys, reviewer_id)
    if status.unavailable_reason:
        raise ConflictError(status.unavailable_reason)
    previous = draft_review(session, draft)
    if previous is not None:
        if previous.state in UNFINISHED:
            raise ConflictError(msg("review_running"))
        session.delete(previous)  # a new run replaces the previous one (REV-09)
        session.flush()
    reviewer = session.get(AiReviewer, status.reviewer_id)
    assert reviewer is not None
    now = clock.now()
    session.add(
        ReviewRun(
            investor_id=actor.id,
            kind=kind.value,
            ai_reviewer_id=reviewer.id,
            provider=reviewer.provider,
            model=reviewer.model,
            started_at=now,
        )
    )
    review = Review(
        kind=kind.value,
        thesis_revision_id=draft.id if isinstance(draft, ThesisRevision) else None,
        policy_version_id=draft.id if isinstance(draft, PolicyVersion) else None,
        started_by=actor.id,
        state="queued",
        news_from=now - timedelta(days=news_days) if news_days else None,
        news_to=now if news_days else None,
        scoring_version=SCORING_VERSION,
        ai_reviewer_id=reviewer.id,
        ai_reviewer_name=reviewer.name,
        provider=reviewer.provider,
        model=reviewer.model,
        started_at=now,
    )
    session.add(review)
    session.flush()
    return review


def _check_news_days(news_days: int) -> None:
    if not 1 <= news_days <= NEWS_DAYS_MAX:
        raise ValidationError.single(
            msg("review_news_days_invalid", max=NEWS_DAYS_MAX), "news_days"
        )


def start_thesis_review(
    session: Session,
    actor: Investor,
    clock: Clock,
    keys: KeyBox,
    thesis_id: int,
    news_days: int = NEWS_DAYS_DEFAULT,
    reviewer_id: int | None = None,
) -> Review:
    """REV-01, REV-04: a review of the thesis draft, with news of the last `news_days`,
    by the given AI reviewer or the investor's default (USR-08)."""
    _check_news_days(news_days)
    draft = _thesis_draft(session, actor, thesis_id)
    return _start(session, actor, clock, keys, ReviewKind.THESIS, draft, news_days, reviewer_id)


def start_policy_review(
    session: Session,
    actor: Investor,
    clock: Clock,
    keys: KeyBox,
    policy_id: int,
    reviewer_id: int | None = None,
) -> Review:
    """REV-01, REV-05: a review of the policy draft against its pinned thesis revision."""
    draft = _policy_draft(session, actor, policy_id)
    return _start(session, actor, clock, keys, ReviewKind.POLICY, draft, None, reviewer_id)


# --- Prompt for a manual review (REV-19) -----------------------------------------------


def thesis_review_prompt(
    session: Session,
    actor: Investor,
    clock: Clock,
    thesis_id: int,
    news_days: int = NEWS_DAYS_DEFAULT,
) -> review_prompts.ReviewPrompt:
    """The review prompt of the thesis draft as it is saved now, the same an AI reviewer
    would receive. Making it changes nothing; it counts towards no limit (REV-16)."""
    _check_news_days(news_days)
    draft = _thesis_draft(session, actor, thesis_id)
    ref = review_prompts.PromptRef(ReviewKind.THESIS, draft.id, clock.now(), news_days)
    return _prompt(session, ref)


def policy_review_prompt(
    session: Session, actor: Investor, clock: Clock, policy_id: int
) -> review_prompts.ReviewPrompt:
    """The review prompt of the policy draft as it is saved now (REV-05, REV-19)."""
    draft = _policy_draft(session, actor, policy_id)
    ref = review_prompts.PromptRef(ReviewKind.POLICY, draft.id, clock.now(), 0)
    return _prompt(session, ref)


# --- Run (background job, REV-08) ------------------------------------------------------


def run_review(
    sessions: Callable[[], Session],
    clock: Clock,
    keys: KeyBox,
    adapters: AdapterFactory,
    review_id: int,
) -> None:
    """Runs a queued review. The provider request runs outside any transaction, so the
    app stays usable meanwhile; the review is never left half written."""
    with sessions() as session:
        review = session.get(Review, review_id)
        if review is None or review.state != "queued":
            return
        review.state = "running"
        # The reviewer the review was started with, even if the investor chose another since
        reviewer = session.get(AiReviewer, review.ai_reviewer_id) if review.ai_reviewer_id else None
        try:
            if reviewer is None:
                raise ConflictError(msg("review_no_reviewer"))
            reason = _unavailable(reviewer, keys)
            if reason is not None:
                raise ConflictError(reason)
            config = llm_config(reviewer, keys)
            request, prompt_id = _request(session, review)
        except ConflictError as e:
            _fail(review, clock, str(e))
            session.commit()
            return
        session.commit()

    try:
        answer = adapters(config).generate(request)
        parsed = review_prompts.parse_answer(ReviewKind(review.kind), answer, prompt_id)
        error = None
    except LlmError as e:
        error = str(e)
    except Exception as e:
        log.exception("Review %s failed", review_id)
        detail = unexpected_detail(e, config.api_key)
        error = str(msg("review_failed_unexpectedly", detail=detail))

    with sessions() as session:
        stored = session.get(Review, review_id)
        if stored is None:  # the draft was deleted meanwhile
            return
        if error is not None:
            _fail(stored, clock, error)
        else:
            _store(stored, parsed)
            stored.state = "done"
            stored.completed_at = clock.now()
        session.commit()


def _prompt_ref(review: Review) -> review_prompts.PromptRef:
    """The prompt of an AI review is made when the review starts."""
    if review.kind == ReviewKind.THESIS:
        assert review.thesis_revision_id and review.news_from and review.news_to
        return review_prompts.PromptRef(
            ReviewKind.THESIS,
            review.thesis_revision_id,
            review.started_at,
            (review.news_to - review.news_from).days,
        )
    assert review.policy_version_id
    return review_prompts.PromptRef(
        ReviewKind.POLICY, review.policy_version_id, review.started_at, 0
    )


def _prompt(session: Session, ref: review_prompts.PromptRef) -> review_prompts.ReviewPrompt:
    if ref.kind == ReviewKind.THESIS:
        revision = session.get(ThesisRevision, ref.draft_id)
        assert revision is not None
        return review_prompts.thesis_prompt(revision, ref)
    version = session.get(PolicyVersion, ref.draft_id)
    assert version is not None
    return review_prompts.policy_prompt(version, ref)


def _request(session: Session, review: Review) -> tuple[LlmRequest, str]:
    prompt = _prompt(session, _prompt_ref(review))
    return prompt.llm_request(), prompt.prompt_id


def _fail(review: Review, clock: Clock, error: str) -> None:
    review.state = "failed"
    review.error = error
    review.completed_at = clock.now()


def _store(review: Review, parsed: review_prompts.ParsedReview) -> None:
    review.verdict = parsed.verdict.value if parsed.verdict else None
    review.aspects = [
        ReviewAspect(aspect=a.code, half_points=a.half_points, reasoning_md=a.reasoning)
        for a in parsed.aspects
    ]
    review.sources = [
        ReviewSource(title=s.title[:500], published_on=_iso_date(s.published_on), url=s.url[:2000])
        for s in parsed.sources
    ]
    review.suggestions = [
        ReviewSuggestion(kind=s.kind, content_md=s.content) for s in parsed.suggestions
    ]


def _iso_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value).date().isoformat()
    except ValueError:
        return None


def fail_interrupted(session: Session, clock: Clock) -> int:
    """At startup: reviews interrupted by a restart failed and can be started again
    (spec section 2.5). Returns how many were marked."""
    unfinished = session.scalars(select(Review).where(Review.state.in_(UNFINISHED))).all()
    for review in unfinished:
        _fail(review, clock, str(msg("review_interrupted")))
    return len(unfinished)


# --- Read ----------------------------------------------------------------------


def draft_of(session: Session, review: Review) -> ThesisRevision | PolicyVersion:
    if review.thesis_revision_id is not None:
        revision = session.get(ThesisRevision, review.thesis_revision_id)
        assert revision is not None
        return revision
    version = session.get(PolicyVersion, review.policy_version_id)
    assert version is not None
    return version


def is_confirmed(session: Session, review: Review) -> bool:
    return draft_of(session, review).activated_at is not None


def is_outdated(session: Session, review: Review) -> bool:
    return outdated(review, draft_of(session, review))


def outdated(review: Review, draft: ThesisRevision | PolicyVersion) -> bool:
    """REV-09: the draft changed after the review was started."""
    return (
        draft.activated_at is None
        and draft.updated_at is not None
        and draft.updated_at > review.started_at
    )


def get_review(session: Session, actor: Investor, review_id: int) -> Review:
    """Thesis reviews are readable like their revision once confirmed (REV-12); drafts,
    and policy reviews, only by their owner."""
    from yap.services.theses import can_read_revision

    require_investor(actor)
    review = session.get(Review, review_id)
    if review is not None:
        draft = draft_of(session, review)
        if isinstance(draft, ThesisRevision):
            if can_read_revision(session, actor, draft):
                return review
        elif draft.policy.owner_id == actor.id:
            return review
    raise NotFoundError(msg("review_not_found", id=review_id))


def total(review: Review) -> int | None:
    """The total score in half points (REV-02), None without aspects."""
    if not review.aspects:
        return None
    return total_half_points([a.half_points for a in review.aspects])


@dataclass(frozen=True)
class LegacyModification:
    """Investor changes of a review from before REV-10 was dropped; shown read-only."""

    note: str | None
    verdict: str | None
    scores: dict[str, float]


def legacy_modification(review: Review) -> LegacyModification | None:
    if review.legacy_modification is None:
        return None
    data = json.loads(review.legacy_modification)
    return LegacyModification(
        note=data.get("note"),
        verdict=data.get("verdict"),
        scores={code: float(score) for code, score in (data.get("scores") or {}).items()},
    )


def aspect_names(kind: str, scoring_version: str) -> dict[str, str]:
    return {a.code: a.name for a in aspects_of(ReviewKind(kind), scoring_version)}


# --- Draft lifecycle (REV-11) ----------------------------------------------------------


def check_draft_can_change(session: Session, draft: ThesisRevision | PolicyVersion) -> None:
    """A draft whose review is still running can be neither activated nor deleted."""
    review = draft_review(session, draft)
    if review is not None and review.state in UNFINISHED:
        raise ConflictError(msg("review_running_wait"))


def delete_with_draft(session: Session, draft: ThesisRevision | PolicyVersion) -> None:
    """Deleting a draft deletes its review (REV-11)."""
    check_draft_can_change(session, draft)
    review = draft_review(session, draft)
    if review is not None:
        session.delete(review)
        session.flush()


def prepare_activation(session: Session, draft: ThesisRevision | PolicyVersion) -> None:
    """Before a draft is activated: no review may be running, and a failed one is
    dropped, as it cannot be changed once the draft is activated (REV-11)."""
    check_draft_can_change(session, draft)
    review = draft_review(session, draft)
    if review is not None and review.state == "failed":
        session.delete(review)
        session.flush()


def confirm_with_draft(
    session: Session, draft: ThesisRevision | PolicyVersion, owner_id: int, now: datetime
) -> None:
    """After a draft was activated: its finished review is confirmed with it and appears
    in the timeline (REV-11, REV-12)."""
    review = draft_review(session, draft)
    if review is None:
        return
    summary = _summary(review)
    params = _summary_params(review)
    if isinstance(draft, ThesisRevision):
        add_event(
            session,
            owner_id,
            now,
            EventType.THESIS_REVIEW_CONFIRMED,
            f"Thesis review of '{draft.title}' revision {draft.revision_no}: {summary}",
            {**params, "title": draft.title, "revision": draft.revision_no},
            review_id=review.id,
            thesis_revision_id=draft.id,
        )
    else:
        add_event(
            session,
            owner_id,
            now,
            EventType.POLICY_REVIEW_CONFIRMED,
            f"Policy review of {draft.label}: {summary}",
            {**params, "version": draft.label},
            review_id=review.id,
            policy_version_id=draft.id,
        )


def _summary_params(review: Review) -> dict[str, Any]:
    """The values of _summary for the timeline in the UI's language (TL-02, NFR-10)."""
    half_points = total(review)
    return {
        "verdict": review.verdict,
        "total": half_points / 2 if half_points is not None else None,
    }


def _summary(review: Review) -> str:
    """TL-02, e.g. 'needs adaptation, 6.5 / 10'."""
    parts = []
    if review.verdict:
        parts.append(review.verdict.replace("_", " "))
    half_points = total(review)
    if half_points is not None:
        parts.append(f"{half_points / 2:g} / 10")
    return ", ".join(parts)
