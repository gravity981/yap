"""Thesis and policy reviews (REV-01 to REV-17)."""

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel

from yap.api.deps import AppClock, AppKeys, CurrentUser, DbSession, LlmAdapters
from yap.db.models import Review
from yap.messages import Message, msg
from yap.services import policies, reviews, theses
from yap.services.common import NotFoundError

router = APIRouter(tags=["reviews"])


class AspectOut(BaseModel):
    code: str
    name: str
    ai_score: float
    score: float  # the investor's value if changed, otherwise the AI's (REV-10)
    modified: bool
    reasoning_md: str


class SourceOut(BaseModel):
    title: str
    published_on: str | None
    url: str


class SuggestionOut(BaseModel):
    kind: str
    content_md: str


class ReviewOut(BaseModel):
    id: int
    kind: str
    state: str  # queued | running | done | failed
    error: str | None
    thesis_revision_id: int | None
    policy_version_id: int | None
    ai_reviewer_name: str | None  # REV-17; null for reviews from before AI reviewers
    provider: str
    model: str
    scoring_version: str  # REV-06
    news_from: datetime | None
    news_to: datetime | None
    started_at: datetime
    completed_at: datetime | None
    aspects: list[AspectOut]
    ai_total: float | None
    total: float | None
    ai_verdict: str | None
    verdict: str | None  # the investor's value if changed, otherwise the AI's
    modified: bool
    modification_note: str | None
    outdated: bool  # REV-09: the draft changed after the review was started
    confirmed: bool  # REV-11: the draft was activated
    sources: list[SourceOut]
    suggestions: list[SuggestionOut]


def _out(session: DbSession, review: Review) -> ReviewOut:
    names = reviews.aspect_names(review.kind)
    total = reviews.totals(review)
    return ReviewOut(
        id=review.id,
        kind=review.kind,
        state=review.state,
        error=review.error,
        thesis_revision_id=review.thesis_revision_id,
        policy_version_id=review.policy_version_id,
        ai_reviewer_name=review.ai_reviewer_name,
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
                ai_score=a.ai_half_points / 2,
                score=(a.half_points if a.half_points is not None else a.ai_half_points) / 2,
                modified=a.half_points is not None,
                reasoning_md=a.reasoning_md,
            )
            for a in review.aspects
        ],
        ai_total=total.ai / 2 if total else None,
        total=total.effective / 2 if total else None,
        ai_verdict=review.ai_verdict,
        verdict=reviews.effective_verdict(review),
        modified=review.modified,
        modification_note=review.modification_note,
        outdated=reviews.is_outdated(session, review),
        confirmed=reviews.is_confirmed(session, review),
        sources=[
            SourceOut(title=s.title, published_on=s.published_on, url=s.url) for s in review.sources
        ],
        suggestions=[
            SuggestionOut(kind=s.kind, content_md=s.content_md) for s in review.suggestions
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


class StartThesisReview(BaseModel):
    news_days: int = reviews.NEWS_DAYS_DEFAULT
    ai_reviewer_id: int | None = None  # USR-08: null = the investor's default


class StartPolicyReview(BaseModel):
    ai_reviewer_id: int | None = None  # USR-08: null = the investor's default


class ReviewChange(BaseModel):
    """REV-10: scores per aspect code (null = the AI's) and the verdict (null = the AI's)."""

    scores: dict[str, float | None]
    verdict: str | None = None
    note: str | None = None


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


@router.post("/theses/{thesis_id}/draft/review", status_code=202)
def start_thesis_review(
    thesis_id: int,
    body: StartThesisReview,
    request: Request,
    background: BackgroundTasks,
    session: DbSession,
    clock: AppClock,
    keys: AppKeys,
    adapters: LlmAdapters,
    user: CurrentUser,
) -> ReviewOut:
    """REV-01, REV-04: starts a review of the thesis draft; it runs in the background."""
    review = reviews.start_thesis_review(
        session, user, clock, keys, thesis_id, body.news_days, body.ai_reviewer_id
    )
    _schedule(request, background, session, clock, keys, adapters, review)
    return _out(session, review)


@router.post("/policies/{policy_id}/draft/review", status_code=202)
def start_policy_review(
    policy_id: int,
    request: Request,
    background: BackgroundTasks,
    session: DbSession,
    clock: AppClock,
    keys: AppKeys,
    adapters: LlmAdapters,
    user: CurrentUser,
    body: StartPolicyReview | None = None,
) -> ReviewOut:
    """REV-01, REV-05: starts a review of the policy draft; it runs in the background."""
    reviewer_id = body.ai_reviewer_id if body else None
    review = reviews.start_policy_review(session, user, clock, keys, policy_id, reviewer_id)
    _schedule(request, background, session, clock, keys, adapters, review)
    return _out(session, review)


@router.get("/reviews/{review_id}")
def get_review(review_id: int, session: DbSession, user: CurrentUser) -> ReviewOut:
    return _out(session, reviews.get_review(session, user, review_id))


@router.put("/reviews/{review_id}")
def modify_review(
    review_id: int, body: ReviewChange, session: DbSession, user: CurrentUser
) -> ReviewOut:
    review = reviews.modify_review(
        session, user, review_id, scores=body.scores, verdict=body.verdict, note=body.note
    )
    return _out(session, review)


def _found(review: Review | None, missing: Message) -> Review:
    if review is None:
        raise NotFoundError(missing)
    return review


@router.get("/theses/{thesis_id}/revisions/{revision_no}/review")
def get_revision_review(
    thesis_id: int, revision_no: int, session: DbSession, user: CurrentUser
) -> ReviewOut:
    """The review of a revision: confirmed (REV-12) or, for the owner, of the draft."""
    thesis = theses.get_readable_thesis(session, user, thesis_id)
    revision = next(
        (
            r
            for r in theses.readable_revisions(session, user, thesis)
            if r.revision_no == revision_no
        ),
        None,
    )
    if revision is None:
        raise NotFoundError(
            msg("review_revision_not_found", revision_no=revision_no, thesis_id=thesis_id)
        )
    missing = msg("review_revision_no_review", revision_no=revision_no)
    review = _found(reviews.draft_review(session, revision), missing)
    return _out(session, review)


@router.get("/policies/{policy_id}/versions/{version_no}/review")
def get_version_review(
    policy_id: int, version_no: int, session: DbSession, user: CurrentUser
) -> ReviewOut:
    policy = policies.get_policy(session, user, policy_id)
    version = next((v for v in policy.versions if v.version_no == version_no), None)
    if version is None:
        raise NotFoundError(
            msg("review_version_not_found", version_no=version_no, policy=policy.name)
        )
    missing = msg("review_version_no_review", version=version.label)
    return _out(session, _found(reviews.draft_review(session, version), missing))
