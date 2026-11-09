"""Reviews of policy drafts (REV-01 to REV-19).

A review judges the whole draft: its thesis (T1-T6 and the verdict) and its target
structure (P1-P6). It is started on a draft, runs in the background (REV-08) and is
confirmed by activating the draft (REV-11). Every started run counts towards the monthly
limit of its AI reviewer (REV-16). Versions from before stage 2 can have a thesis and a
policy review instead (ReviewKind.THESIS, ReviewKind.POLICY).
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
)
from yap.domain.fingerprint import fingerprint
from yap.domain.reviews import (
    SCORING_VERSION,
    ReviewKind,
    Scores,
    Verdict,
    aspects_of,
    scores_of,
    semaphore,
)
from yap.llm import LlmError
from yap.llm.base import AdapterFactory, unexpected_detail
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
from yap.services.versioning import active_version

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


def _policy_draft(session: Session, actor: Investor, policy_id: int) -> PolicyVersion:
    policy = get_owned(session, Policy, policy_id, actor)
    draft = next((v for v in policy.versions if v.activated_at is None), None)
    if draft is None:
        raise NotFoundError(msg("review_policy_no_draft", name=policy.name))
    return draft


def _target(
    session: Session, actor: Investor, clock: Clock, policy_id: int, active: bool
) -> PolicyVersion:
    """The draft (REV-01), or the active version to review again (POL-20)."""
    if not active:
        return _policy_draft(session, actor, policy_id)
    policy = get_owned(session, Policy, policy_id, actor)
    version = active_version(policy, clock.now())
    if version is None:
        raise NotFoundError(msg("review_policy_not_active", name=policy.name))
    return version


# Of the reviews saved at the same moment (versions from before stage 2), the one of the
# whole policy counts first, then the thesis review
_KIND_ORDER = {ReviewKind.FULL: 2, ReviewKind.THESIS: 1, ReviewKind.POLICY: 0}


def current_review(version: PolicyVersion) -> Review | None:
    """The review that gives a version its score and semaphore (REV-21): for a draft its
    open review, for an activated version the latest saved one (the one confirmed at
    activation, or a later one saved on it, POL-20)."""
    if version.activated_at is None:
        candidates = list(version.reviews)
    else:
        candidates = [r for r in version.reviews if r.saved_at is not None]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda r: (r.saved_at or r.started_at, _KIND_ORDER.get(ReviewKind(r.kind), 0), r.id),
    )


def pending_review(version: PolicyVersion) -> Review | None:
    """A review of an activated version that is not saved yet: running or failed (POL-20)."""
    if version.activated_at is None:
        return None
    open_reviews = [r for r in version.reviews if r.saved_at is None]
    return max(open_reviews, key=lambda r: r.id) if open_reviews else None


def scored_review(version: PolicyVersion) -> Review | None:
    """REV-21: the review that gives a version its score: the latest one with scores. Quick
    reviews of the active version (REV-26) have none, so they leave the score as it is."""
    scored = [
        r
        for r in version.reviews
        if r.kind != ReviewKind.QUICK
        and r.state == "done"
        and (r.saved_at or version.activated_at is None)
    ]
    if not scored:
        return None
    return max(
        scored,
        key=lambda r: (r.saved_at or r.started_at, _KIND_ORDER.get(ReviewKind(r.kind), 0), r.id),
    )


def effective_mark(version: PolicyVersion) -> str | None:
    """REV-20: a version's mark counts until it gets a review with scores saved after its
    activation; a quick review (REV-26) does not clear it. Only reviews from before quick
    reviews existed can: they were full reviews of the active version."""
    if version.mark is None or version.activated_at is None:
        return version.mark
    activated = version.activated_at
    if any(
        r.kind != ReviewKind.QUICK and r.saved_at is not None and r.saved_at > activated
        for r in version.reviews
    ):
        return None
    return version.mark


def review_log(version_reviews: list[Review]) -> list[Review]:
    """REV-23: the saved reviews, newest first."""
    saved = [r for r in version_reviews if r.saved_at is not None and r.state == "done"]
    return sorted(saved, key=lambda r: (r.saved_at, r.id), reverse=True)


def _replace_previous(session: Session, version: PolicyVersion) -> None:
    """A draft has at most one review; a new one replaces it, and any reviews it has from
    before stage 2 (REV-09). On an active version, only a failed review that was never
    saved is replaced; the saved ones stay in its review log (REV-23)."""
    previous = [r for r in draft_reviews(session, version) if r.saved_at is None]
    if any(r.state in UNFINISHED for r in previous):
        raise ConflictError(msg("review_running"))
    for review in previous:
        session.delete(review)
    session.flush()


def _save_on_active(
    session: Session, review: Review, version: PolicyVersion, owner_id: int, now: datetime
) -> None:
    """POL-20: a finished review of the active version goes into its review log at once
    and appears in the timeline (TL-01). It is immutable from then on."""
    session.flush()  # its aspects and suggestions are written first
    review.saved_at = now
    add_event(
        session,
        owner_id,
        now,
        EventType.REVIEW_SAVED,
        f"Quick review of {version.label}: {_summary(review)}",
        {**_summary_params(review), "version": version.label, "method": review.method},
        review_id=review.id,
        policy_version_id=version.id,
    )
    session.flush()


def _check_news_days(news_days: int) -> None:
    if not 1 <= news_days <= NEWS_DAYS_MAX:
        raise ValidationError.single(
            msg("review_news_days_invalid", max=NEWS_DAYS_MAX), "news_days"
        )


def start_review(
    session: Session,
    actor: Investor,
    clock: Clock,
    keys: KeyBox,
    policy_id: int,
    news_days: int = NEWS_DAYS_DEFAULT,
    reviewer_id: int | None = None,
    active: bool = False,
) -> Review:
    """REV-01, REV-04: a review of the policy draft, or with `active` of its active version
    (POL-20), with news of the last `news_days`, by the given AI reviewer or the
    investor's default (USR-08)."""
    _check_news_days(news_days)
    draft = _target(session, actor, clock, policy_id, active)
    status = usage(session, actor, clock, keys, reviewer_id)
    if status.unavailable_reason:
        raise ConflictError(status.unavailable_reason)
    _replace_previous(session, draft)
    reviewer = session.get(AiReviewer, status.reviewer_id)
    assert reviewer is not None
    now = clock.now()
    kind = ReviewKind.QUICK if active else ReviewKind.FULL  # REV-26
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
        policy_version_id=draft.id,
        started_by=actor.id,
        state="queued",
        fingerprint=draft_fingerprint(draft),
        news_from=now - timedelta(days=news_days),
        news_to=now,
        scoring_version=SCORING_VERSION,
        method="ai",
        ai_reviewer_id=reviewer.id,
        ai_reviewer_name=reviewer.name,
        provider=reviewer.provider,
        model=reviewer.model,
        started_at=now,
    )
    session.add(review)
    session.flush()
    return review


# --- Prompt for a manual review (REV-19) -----------------------------------------------


def review_prompt(
    session: Session,
    actor: Investor,
    clock: Clock,
    policy_id: int,
    news_days: int = NEWS_DAYS_DEFAULT,
    active: bool = False,
) -> review_prompts.ReviewPrompt:
    """The review prompt of the policy draft as it is saved now (or of its active version,
    POL-20), the same an AI reviewer would receive. Making it changes nothing; it counts
    towards no limit (REV-16)."""
    _check_news_days(news_days)
    draft = _target(session, actor, clock, policy_id, active)
    ref = review_prompts.PromptRef(draft.id, clock.now(), news_days, draft_fingerprint(draft))
    return review_prompts.review_prompt(draft, ref, actor.language, quick=active)


# --- Manual review (REV-18) ------------------------------------------------------------


def submit_manual_review(
    session: Session,
    actor: Investor,
    clock: Clock,
    policy_id: int,
    answer: str,
    active: bool = False,
) -> Review:
    """REV-18: stores the answer of an AI outside the app as the review of the policy
    draft; it counts towards no limit (REV-16) and names no model (REV-17). It is made
    when its prompt was copied, so a later change of the draft makes it outdated (REV-09).
    Every problem of the answer is reported at once. With `active`, the review of the
    active version is saved in its review log (POL-20)."""
    draft = _target(session, actor, clock, policy_id, active)
    prompt_id = review_prompts.answer_prompt_id(answer)
    ref = review_prompts.parse_prompt_id(prompt_id) if prompt_id else None
    with_positions = bool(draft.positions)
    if ref is None:
        _, format_problems = review_prompts.check_answer(answer, "", with_positions, quick=active)
        problems = [
            msg("answer_prompt_id_unknown"),
            *(p for p in format_problems if p.code != "answer_prompt_id_wrong"),
        ]
        raise ValidationError([("answer", p) for p in problems])
    if ref.version_id != draft.id:
        raise ValidationError.single(msg("answer_prompt_id_other_draft"), "answer")
    tickers = [p.asset.ticker for p in draft.positions]
    parsed, problems = review_prompts.check_answer(
        answer, ref.prompt_id, with_positions, tickers, quick=active
    )
    if parsed is None:
        raise ValidationError([("answer", p) for p in problems])
    _replace_previous(session, draft)
    review = Review(
        kind=(ReviewKind.QUICK if active else ReviewKind.FULL).value,
        policy_version_id=draft.id,
        started_by=actor.id,
        state="done",
        news_from=ref.issued_at - timedelta(days=ref.news_days),
        news_to=ref.issued_at,
        scoring_version=SCORING_VERSION,
        method="manual",
        prompt_id=ref.prompt_id,
        # REV-09: the content when the prompt was copied
        fingerprint=ref.fingerprint or None,
        provider="manual",
        model=None,
        started_at=ref.issued_at,
        completed_at=clock.now(),
    )
    _store(review, parsed)
    session.add(review)
    session.flush()
    if draft.activated_at is not None:
        _save_on_active(session, review, draft, draft.policy.owner_id, clock.now())
    return review


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
            prompt = _prompt(session, review)
            review.fingerprint = draft_fingerprint(draft_of(session, review))
        except ConflictError as e:
            _fail(review, clock, str(e))
            session.commit()
            return
        session.commit()

    try:
        answer = adapters(config).generate(prompt.llm_request())
        parsed = review_prompts.parse_answer(
            answer, prompt.prompt_id, prompt.with_positions, prompt.tickers, prompt.quick
        )
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
            version = draft_of(session, stored)
            if version.activated_at is not None:  # POL-20
                _save_on_active(session, stored, version, version.policy.owner_id, clock.now())
        session.commit()


def _prompt(session: Session, review: Review) -> review_prompts.ReviewPrompt:
    """The prompt of an AI review is made from the draft as it is when the run starts."""
    assert review.news_from and review.news_to
    version = draft_of(session, review)
    ref = review_prompts.PromptRef(
        version.id, review.started_at, (review.news_to - review.news_from).days
    )
    owner = session.get(Investor, review.started_by)
    return review_prompts.review_prompt(
        version, ref, owner.language if owner else None, quick=review.kind == ReviewKind.QUICK
    )


def _fail(review: Review, clock: Clock, error: str) -> None:
    review.state = "failed"
    review.error = error
    review.completed_at = clock.now()


def _store(review: Review, parsed: review_prompts.ParsedReview) -> None:
    review.verdict = parsed.verdict.value
    review.verdict_reason = parsed.verdict_reason
    review.aspects = [
        ReviewAspect(aspect=a.code, half_points=a.half_points, reasoning_md=a.reasoning)
        for a in parsed.aspects
    ]
    review.sources = [
        ReviewSource(title=s.title[:500], published_on=_iso_date(s.published_on), url=s.url[:2000])
        for s in parsed.sources
    ]
    review.suggestions = [
        ReviewSuggestion(kind=s.kind.value, content_md=s.content_md, change=s.change, state="open")
        for s in parsed.suggestions
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


def draft_of(session: Session, review: Review) -> PolicyVersion:
    version = session.get(PolicyVersion, review.policy_version_id)
    assert version is not None
    return version


def is_confirmed(session: Session, review: Review) -> bool:
    return draft_of(session, review).activated_at is not None


def is_outdated(session: Session, review: Review) -> bool:
    return outdated(review, draft_of(session, review))


def draft_fingerprint(version: PolicyVersion) -> str:
    """REV-09: the fingerprint of a version's title, thesis and target structure."""
    return fingerprint(
        version.thesis_title,
        version.thesis_md,
        [(p.asset.ticker, p) for p in version.positions],
    )


def outdated(review: Review, draft: PolicyVersion) -> bool:
    """REV-09: the review no longer matches its open draft; it matches again when the
    draft gets back the reviewed content. Reviews from before fingerprints compare
    times."""
    if draft.activated_at is not None:
        return False
    if review.fingerprint is not None:
        return review.fingerprint != draft_fingerprint(draft)
    return draft.updated_at is not None and draft.updated_at > review.started_at


def get_review(session: Session, actor: Investor, review_id: int) -> Review:
    """Reviews are readable by the owner of their policy (REV-12)."""
    require_investor(actor)
    review = session.get(Review, review_id)
    if review is not None and draft_of(session, review).policy.owner_id == actor.id:
        return review
    raise NotFoundError(msg("review_not_found", id=review_id))


def scores(review: Review) -> Scores:
    """The thesis, target-structure and review scores in half points (REV-02)."""
    return scores_of({a.aspect: a.half_points for a in review.aspects})


def total(review: Review) -> int | None:
    """The review's score in half points (REV-02), None without aspects."""
    return scores(review).total


def review_semaphore(review: Review | None) -> Verdict | None:
    """The semaphore a finished review gives its version (THS-04, REV-03, REV-06)."""
    if review is None or review.state != "done":
        return None
    return semaphore(review.verdict)


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
    return {a.code: a.name for a in aspects_of(kind, scoring_version)}


# --- Draft lifecycle (REV-11) ----------------------------------------------------------


def draft_reviews(session: Session, draft: PolicyVersion) -> list[Review]:
    return list(session.scalars(select(Review).where(Review.policy_version_id == draft.id)))


def check_draft_can_change(session: Session, draft: PolicyVersion) -> None:
    """A draft whose review is still running can be neither activated nor deleted."""
    if any(r.state in UNFINISHED for r in draft_reviews(session, draft)):
        raise ConflictError(msg("review_running_wait"))


def delete_with_draft(session: Session, draft: PolicyVersion) -> None:
    """Deleting a draft deletes its reviews (REV-11)."""
    check_draft_can_change(session, draft)
    for review in draft_reviews(session, draft):
        session.delete(review)
    session.flush()


MARK_NOT_REVIEWED = "not_reviewed"
MARK_DID_NOT_MATCH = "review_did_not_match"


def activation_mark(session: Session, draft: PolicyVersion) -> str | None:
    """REV-20: the mark the draft gets if it is activated now: none with a matching
    review."""
    session.expire(draft, ["reviews"])
    review = current_review(draft)
    if review is None or review.state != "done":
        return MARK_NOT_REVIEWED
    return MARK_DID_NOT_MATCH if outdated(review, draft) else None


def prepare_activation(session: Session, draft: PolicyVersion, now: datetime) -> str | None:
    """Before a draft is activated: no review may be running, failed ones are dropped,
    and the others are confirmed as they are: saved with the version (REV-11). Returns the
    version's mark (REV-20). Reviews never block the activation."""
    check_draft_can_change(session, draft)
    for review in draft_reviews(session, draft):
        if review.state == "failed":
            session.delete(review)
    session.flush()
    mark = activation_mark(session, draft)
    for review in draft_reviews(session, draft):
        review.saved_at = now
    session.flush()
    return mark


def confirm_with_draft(
    session: Session, draft: PolicyVersion, owner_id: int, now: datetime
) -> None:
    """After a draft was activated: its finished reviews are confirmed with it and appear
    in the timeline (REV-11, REV-12)."""
    for review in draft_reviews(session, draft):
        summary = _summary(review)
        params = {**_summary_params(review), "version": draft.label}
        if review.kind == ReviewKind.THESIS:
            event, text = EventType.THESIS_REVIEW_CONFIRMED, f"Thesis review of {draft.label}"
        elif review.kind == ReviewKind.POLICY:
            event, text = EventType.POLICY_REVIEW_CONFIRMED, f"Policy review of {draft.label}"
        else:
            event, text = EventType.REVIEW_CONFIRMED, f"Review of {draft.label}"
        add_event(
            session,
            owner_id,
            now,
            event,
            f"{text}: {summary}",
            params,
            review_id=review.id,
            policy_version_id=draft.id,
        )


def _summary_params(review: Review) -> dict[str, Any]:
    """The values of _summary for the timeline in the UI's language (TL-02, NFR-10)."""
    half_points = total(review)
    verdict = semaphore(review.verdict)
    return {
        "verdict": verdict.value if verdict else None,
        "total": half_points / 2 if half_points is not None else None,
    }


def _summary(review: Review) -> str:
    """TL-02, e.g. 'warning, 6.5 / 10'."""
    parts = []
    verdict = semaphore(review.verdict)
    if verdict:
        parts.append(verdict.value)
    half_points = total(review)
    if half_points is not None:
        parts.append(f"{half_points / 2:g} / 10")
    return ", ".join(parts)
