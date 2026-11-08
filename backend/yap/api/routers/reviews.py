"""Reviews of policy drafts (REV-01 to REV-19)."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel

from yap.api.deps import AppClock, AppKeys, CurrentUser, DbSession, LlmAdapters
from yap.api.schemas import VersionOut, half
from yap.db.models import Investor, PolicyVersion, Review
from yap.messages import Message, msg
from yap.services import policies, reviews, suggestions
from yap.services.common import NotFoundError

router = APIRouter(tags=["reviews"])


class AspectOut(BaseModel):
    code: str
    name: str
    score: float
    reasoning_md: str


class SourceOut(BaseModel):
    title: str
    published_on: str | None
    url: str


class SuggestionOut(BaseModel):
    """REV-07, REV-22. `change` says what Take over applies (null for suggestions of older
    reviews, which can only be read); `previous` what it replaced."""

    id: int
    kind: str
    content_md: str
    change: dict[str, Any] | None
    previous: dict[str, Any] | None
    state: str  # open | taken_over | dismissed


class LegacyModificationOut(BaseModel):
    """Investor changes of a review from before REV-10 was dropped; read-only."""

    note: str | None
    verdict: str | None
    scores: dict[str, float]


class ReviewOut(BaseModel):
    id: int
    kind: str  # full; thesis | policy for reviews from before stage 2
    state: str  # queued | running | done | failed
    error: str | None
    policy_version_id: int | None
    method: str  # ai | manual (REV-18)
    ai_reviewer_name: str | None  # REV-17; null for manual reviews and those before reviewers
    provider: str  # "manual" for a manual review
    model: str | None  # null for a manual review (REV-17); named by the investor before
    prompt_id: str | None  # REV-19; null for reviews before it
    scoring_version: str  # REV-06
    news_from: datetime | None
    news_to: datetime | None
    started_at: datetime
    completed_at: datetime | None
    aspects: list[AspectOut]
    total: float | None  # the review's score (REV-02)
    thesis_score: float | None
    structure_score: float | None  # null without positions
    semaphore: str | None  # the verdict as good | warning | broken (REV-03, REV-06)
    verdict: str | None  # as stored; before scoring version 3 intact | needs_adaptation
    verdict_reason: str | None  # null before scoring version 3
    legacy_modification: LegacyModificationOut | None
    outdated: bool  # REV-09: the draft changed after the review was started
    confirmed: bool  # REV-11: the draft was activated
    sources: list[SourceOut]
    suggestions: list[SuggestionOut]


def _out(session: DbSession, review: Review) -> ReviewOut:
    names = reviews.aspect_names(review.kind, review.scoring_version)
    scores = reviews.scores(review)
    semaphore = reviews.review_semaphore(review)
    legacy = reviews.legacy_modification(review)
    return ReviewOut(
        id=review.id,
        kind=review.kind,
        state=review.state,
        error=review.error,
        policy_version_id=review.policy_version_id,
        method=review.method,
        ai_reviewer_name=review.ai_reviewer_name,
        prompt_id=review.prompt_id,
        provider=review.provider,
        model=review.model,
        scoring_version=review.scoring_version,
        news_from=review.news_from,
        news_to=review.news_to,
        started_at=review.started_at,
        completed_at=review.completed_at,
        aspects=[
            AspectOut(
                code=a.aspect,
                name=names[a.aspect],
                score=a.half_points / 2,
                reasoning_md=a.reasoning_md,
            )
            for a in review.aspects
        ],
        total=half(scores.total),
        thesis_score=half(scores.thesis),
        structure_score=half(scores.structure),
        semaphore=semaphore.value if semaphore else None,
        verdict=review.verdict,
        verdict_reason=review.verdict_reason,
        legacy_modification=(
            LegacyModificationOut(note=legacy.note, verdict=legacy.verdict, scores=legacy.scores)
            if legacy
            else None
        ),
        outdated=reviews.is_outdated(session, review),
        confirmed=reviews.is_confirmed(session, review),
        sources=[
            SourceOut(title=s.title, published_on=s.published_on, url=s.url) for s in review.sources
        ],
        suggestions=[
            SuggestionOut(
                id=s.id,
                kind=s.kind,
                content_md=s.content_md,
                change=s.change,
                previous=s.previous,
                state=s.state,
            )
            for s in review.suggestions
        ],
    )


class Usage(BaseModel):
    """REV-16: reviews used and left this month with the chosen AI reviewer;
    `unavailable_reason` explains why no review can be started, in English;
    `unavailable_code` and `unavailable_params` let the frontend translate it (NFR-10)."""

    ai_reviewer_id: int | None
    ai_reviewer_name: str | None
    used: int
    limit: int
    left: int
    unavailable_reason: str | None
    unavailable_code: str | None
    unavailable_params: dict[str, str | int | float]


class StartReview(BaseModel):
    news_days: int = reviews.NEWS_DAYS_DEFAULT  # REV-04
    ai_reviewer_id: int | None = None  # USR-08: null = the investor's default


def _schedule(
    request: Request,
    background: BackgroundTasks,
    session: DbSession,
    clock: AppClock,
    keys: AppKeys,
    adapters: LlmAdapters,
    review: Review,
) -> None:
    """The run starts after the response; the review must be committed before (REV-08)."""
    session.commit()
    background.add_task(
        reviews.run_review, request.app.state.session_factory, clock, keys, adapters, review.id
    )


@router.get("/reviews/usage")
def get_usage(
    session: DbSession,
    clock: AppClock,
    keys: AppKeys,
    user: CurrentUser,
    ai_reviewer_id: int | None = None,
) -> Usage:
    """For the given AI reviewer, or the investor's default (USR-08)."""
    usage = reviews.usage(session, user, clock, keys, ai_reviewer_id)
    return Usage(
        ai_reviewer_id=usage.reviewer_id,
        ai_reviewer_name=usage.reviewer_name,
        used=usage.used,
        limit=usage.limit,
        left=usage.left,
        unavailable_reason=str(reason) if (reason := usage.unavailable_reason) else None,
        unavailable_code=reason.code if reason else None,
        unavailable_params=reason.params if reason else {},
    )


@router.post("/policies/{policy_id}/draft/review", status_code=202)
def start_review(
    policy_id: int,
    request: Request,
    background: BackgroundTasks,
    session: DbSession,
    clock: AppClock,
    keys: AppKeys,
    adapters: LlmAdapters,
    user: CurrentUser,
    body: StartReview | None = None,
) -> ReviewOut:
    """REV-01, REV-04: starts a review of the policy draft; it runs in the background."""
    body = body or StartReview()
    review = reviews.start_review(
        session, user, clock, keys, policy_id, body.news_days, body.ai_reviewer_id
    )
    _schedule(request, background, session, clock, keys, adapters, review)
    return _out(session, review)


class ManualAnswer(BaseModel):
    """REV-18: the answer of an AI outside the app; the model is not asked for (REV-17)."""

    answer: str


class ReviewPromptOut(BaseModel):
    """REV-19: the review prompt to copy into an AI outside the app."""

    prompt_id: str
    text: str


@router.get("/policies/{policy_id}/draft/review-prompt")
def get_review_prompt(
    policy_id: int,
    session: DbSession,
    clock: AppClock,
    user: CurrentUser,
    news_days: int = reviews.NEWS_DAYS_DEFAULT,
) -> ReviewPromptOut:
    """REV-19: the prompt of the policy draft as it is saved now; changes nothing."""
    prompt = reviews.review_prompt(session, user, clock, policy_id, news_days)
    return ReviewPromptOut(prompt_id=prompt.prompt_id, text=prompt.text())


@router.post("/policies/{policy_id}/draft/review/manual", status_code=201)
def submit_manual_review(
    policy_id: int, body: ManualAnswer, session: DbSession, clock: AppClock, user: CurrentUser
) -> ReviewOut:
    """REV-18: stores the pasted answer as the review of the policy draft."""
    review = reviews.submit_manual_review(session, user, clock, policy_id, body.answer)
    return _out(session, review)


class SuggestionResult(BaseModel):
    """The review with the suggestion's new state, and the draft as it is now."""

    review: ReviewOut
    draft: VersionOut


def _result(
    session: DbSession, review_id: int, draft: PolicyVersion, user: Investor
) -> SuggestionResult:
    review = reviews.get_review(session, user, review_id)
    session.refresh(review)
    return SuggestionResult(review=_out(session, review), draft=VersionOut.of(draft, None, None))


@router.post("/reviews/{review_id}/suggestions/{suggestion_id}/take-over")
def take_over_suggestion(
    review_id: int, suggestion_id: int, session: DbSession, clock: AppClock, user: CurrentUser
) -> SuggestionResult:
    """REV-07, REV-22: applies the suggestion or proposal to the draft."""
    draft = suggestions.take_over(session, user, clock, review_id, suggestion_id)
    return _result(session, review_id, draft, user)


@router.post("/reviews/{review_id}/suggestions/{suggestion_id}/dismiss")
def dismiss_suggestion(
    review_id: int, suggestion_id: int, session: DbSession, user: CurrentUser
) -> SuggestionResult:
    """REV-07: marks the suggestion as dismissed; the draft stays as it is."""
    draft = suggestions.dismiss(session, user, review_id, suggestion_id)
    return _result(session, review_id, draft, user)


@router.post("/reviews/{review_id}/suggestions/{suggestion_id}/undo")
def undo_suggestion(
    review_id: int, suggestion_id: int, session: DbSession, clock: AppClock, user: CurrentUser
) -> SuggestionResult:
    """REV-07: reverts a taken over suggestion in the draft, or reopens a dismissed one."""
    draft = suggestions.undo(session, user, clock, review_id, suggestion_id)
    return _result(session, review_id, draft, user)


@router.get("/reviews/{review_id}")
def get_review(review_id: int, session: DbSession, user: CurrentUser) -> ReviewOut:
    return _out(session, reviews.get_review(session, user, review_id))


def _found(review: Review | None, missing: Message) -> Review:
    if review is None:
        raise NotFoundError(missing)
    return review


@router.get("/policies/{policy_id}/versions/{version_no}/review")
def get_version_review(
    policy_id: int, version_no: int, session: DbSession, user: CurrentUser
) -> ReviewOut:
    """The review that gives a version its score and semaphore: confirmed (REV-12) or of
    the draft."""
    policy = policies.get_policy(session, user, policy_id)
    version = next((v for v in policy.versions if v.version_no == version_no), None)
    if version is None:
        raise NotFoundError(
            msg("review_version_not_found", version_no=version_no, policy=policy.name)
        )
    missing = msg("review_version_no_review", version=version.label)
    return _out(session, _found(reviews.current_review(version), missing))
