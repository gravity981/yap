"""Reviews of the active version, the review log and the latest review (POL-20, REV-12,
REV-20, REV-21, REV-23)."""

from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from tests.fixtures import TEST_SECRET, Factory, FakeLlm
from tests.reviews.answers import quick_answer
from yap.db.engine import make_engine, make_session_factory
from yap.db.models import AiReviewer, Investor, Policy, Review, ReviewRun, ReviewSuggestion
from yap.domain.reviews import Verdict
from yap.messages import msg
from yap.services import policies, reviews
from yap.services.common import ConflictError, NotFoundError
from yap.services.secrets import KeyBox
from yap.services.timeline import EventType, TimelineFilter, list_events

KEYS = KeyBox(TEST_SECRET)

Run = Callable[[Review], Review]


@pytest.fixture
def fake() -> FakeLlm:
    return FakeLlm(answers=[quick_answer(verdict="broken")])


@pytest.fixture
def run(session: Session, db_url: str, factory: Factory, fake: FakeLlm) -> Iterator[Run]:
    """Runs a started review like the background job: in its own sessions."""
    engine = make_engine(db_url, writer_transactions=False)
    sessions = make_session_factory(engine)

    def run(review: Review) -> Review:
        session.commit()
        reviews.run_review(sessions, factory.clock, KEYS, fake, review.id)
        session.expire_all()
        return review

    yield run
    engine.dispose()


def _owner(session: Session, factory: Factory) -> Investor:
    owner = factory.investor("alice")
    factory.ai_reviewer("Standard", limit=10)
    owner.ai_reviewer_id = session.scalar(select(AiReviewer.id).order_by(AiReviewer.id))
    return owner


def _active(factory: Factory, owner: Investor, verdict: str | None = "good") -> Policy:
    """A policy whose v1 was activated with a review (or without one, verdict None)."""
    policy = factory.active_policy(owner, verdict=verdict)
    factory.clock.advance(days=30)
    return policy


def _again(session: Session, factory: Factory, owner: Investor, policy: Policy) -> Review:
    return reviews.start_review(session, owner, factory.clock, KEYS, policy.id, 30, active=True)


@pytest.mark.req("POL-20", "REV-12", "REV-21", "REV-26", "POL-11", "THS-04")
def test_an_ai_quick_review_of_the_active_version_is_saved_in_its_log(
    session: Session, factory: Factory, run: Run
) -> None:
    owner = _owner(session, factory)
    policy = _active(factory, owner)
    v1 = policy.versions[0]
    confirmed = reviews.current_review(v1)
    assert confirmed is not None and confirmed.saved_at == v1.activated_at

    review = _again(session, factory, owner, policy)
    assert (review.policy_version_id, review.saved_at) == (v1.id, None)
    # While it runs, the confirmed review still counts; the new one is pending
    session.expire_all()
    assert reviews.current_review(v1) is confirmed
    assert reviews.pending_review(v1) is review

    run(review)
    session.refresh(policy)
    assert [v.version_no for v in policy.versions] == [1]  # no new version
    assert (review.state, review.saved_at) == ("done", factory.clock.now())
    assert reviews.current_review(v1) is review  # the latest saved review counts
    assert reviews.pending_review(v1) is None
    assert reviews.review_semaphore(review) == Verdict.BROKEN
    # REV-26: verdict and news only; the score stays that of the review at activation
    assert (review.kind, list(review.aspects), list(review.suggestions)) == ("quick", [], [])
    assert reviews.scored_review(v1) is confirmed
    event = list_events(session, owner, TimelineFilter(types=frozenset({EventType.REVIEW_SAVED})))[
        0
    ]
    assert event.review_id == review.id
    assert event.summary == f"Quick review of {v1.label}: broken"
    assert event.params is not None and event.params["method"] == "ai"


@pytest.mark.req("POL-20", "REV-16")
def test_a_running_review_blocks_another_a_failed_one_is_replaced_and_runs_count(
    session: Session, factory: Factory
) -> None:
    owner = _owner(session, factory)
    policy = _active(factory, owner)
    first = _again(session, factory, owner, policy)
    with pytest.raises(ConflictError) as error:
        _again(session, factory, owner, policy)
    assert error.value.message == msg("review_running")
    first.state = "failed"
    session.flush()
    _again(session, factory, owner, policy)
    session.expire_all()
    version_reviews = session.scalars(
        select(Review).where(Review.policy_version_id == policy.versions[0].id)
    ).all()
    # The failed one is replaced; the review confirmed at activation stays
    assert sorted((r.state, r.saved_at is None) for r in version_reviews) == [
        ("done", False),
        ("queued", True),
    ]
    # Both runs count towards the limit (REV-16)
    runs = session.scalars(select(ReviewRun).where(ReviewRun.investor_id == owner.id)).all()
    assert len(runs) == 2
    assert reviews.usage(session, owner, factory.clock, KEYS).used == 2


@pytest.mark.req("POL-20")
def test_only_a_policy_with_an_active_version_is_reviewed_again(
    session: Session, factory: Factory
) -> None:
    owner = _owner(session, factory)
    policy = factory.policy_draft(owner)
    with pytest.raises(NotFoundError) as error:
        _again(session, factory, owner, policy)
    assert error.value.message == msg("review_policy_not_active", name=policy.name)
    with pytest.raises(NotFoundError):
        reviews.review_prompt(session, owner, factory.clock, policy.id, active=True)


@pytest.mark.req("POL-20", "REV-18", "REV-19", "REV-20", "REV-21", "REV-26")
def test_a_manual_quick_review_is_saved_at_once_and_does_not_clear_the_mark(
    session: Session, factory: Factory
) -> None:
    owner = _owner(session, factory)
    policy = _active(factory, owner, verdict=None)
    v1 = policy.versions[0]
    assert (v1.mark, reviews.effective_mark(v1), reviews.current_review(v1)) == (
        "not_reviewed",
        "not_reviewed",
        None,
    )
    prompt = reviews.review_prompt(session, owner, factory.clock, policy.id, active=True)
    assert prompt.prompt_id.startswith(f"R{v1.id}-")
    factory.clock.advance(minutes=5)
    review = reviews.submit_manual_review(
        session,
        owner,
        factory.clock,
        policy.id,
        quick_answer(verdict="good", prompt_id=prompt.prompt_id),
        active=True,
    )
    assert (review.method, review.saved_at) == ("manual", factory.clock.now())
    session.expire_all()
    assert reviews.current_review(v1) is review
    assert prompt.quick and reviews.scored_review(v1) is None
    # Only a review of the whole policy, made in a draft, clears a mark (REV-20)
    assert v1.mark == "not_reviewed"
    assert reviews.effective_mark(v1) == "not_reviewed"
    event = list_events(session, owner, TimelineFilter(types=frozenset({EventType.REVIEW_SAVED})))[
        0
    ]
    assert event.params is not None and event.params["method"] == "manual"
    # A draft's prompt does not fit the active version
    draft = policies.create_draft(session, owner, factory.clock, policy.id)
    other = reviews.review_prompt(session, owner, factory.clock, policy.id)
    assert other.prompt_id.startswith(f"R{draft.id}-")


@pytest.mark.req("REV-23", "REV-21")
def test_the_review_log_has_the_saved_reviews_newest_first(
    session: Session, factory: Factory
) -> None:
    owner = _owner(session, factory)
    policy = factory.active_policy(owner)
    v1 = policy.versions[0]
    # A version from before stage 2: a thesis and a policy review saved together
    legacy_thesis = factory.review(owner, v1, kind="thesis", verdict="needs_adaptation")
    legacy_policy = factory.review(owner, v1, kind="policy")
    for r in (legacy_thesis, legacy_policy):
        r.saved_at = v1.activated_at
    session.flush()
    # Of those saved together, the thesis review counts before the policy review
    session.expire_all()
    assert reviews.current_review(v1) is legacy_thesis
    factory.clock.advance(days=1)
    again = factory.review(owner, v1)
    again.saved_at = factory.clock.now()
    session.flush()
    # A draft's open review and an unsaved review are no part of the log
    draft = policies.create_draft(session, owner, factory.clock, policy.id)
    factory.review(owner, draft)
    unsaved = factory.review(owner, v1)
    unsaved.state = "failed"
    session.flush()
    session.expire_all()
    all_reviews = [r for v in policy.versions for r in v.reviews]
    log = reviews.review_log(all_reviews)
    assert [r.id for r in log] == [again.id, legacy_policy.id, legacy_thesis.id]
    assert reviews.current_review(v1) is again
    assert reviews.pending_review(v1) is unsaved
    assert reviews.pending_review(draft) is None


@pytest.mark.req("REV-12", "REV-11", "REV-07")
def test_a_saved_review_is_immutable_and_has_no_suggestions_left(
    session: Session, factory: Factory
) -> None:
    owner = _owner(session, factory)
    policy = factory.active_policy(owner)
    draft = policies.create_draft(session, owner, factory.clock, policy.id)
    review = factory.review(owner, draft)
    sid = factory.suggestion(review).id
    factory.clock.advance(minutes=1)
    policies.activate_draft(session, owner, factory.clock, policy.id, "v2")
    assert review.saved_at is not None
    # Activating removed the suggestions (REV-07)
    session.refresh(review)
    assert list(review.suggestions) == [] and session.get(ReviewSuggestion, sid) is None
    session.commit()
    for statement in (
        "UPDATE review SET verdict = 'broken' WHERE id = :id",
        "DELETE FROM review WHERE id = :id",
        "UPDATE review_aspect SET half_points = 0 WHERE review_id = :id",
        "INSERT INTO review_source (review_id, title, url) VALUES (:id, 't', 'u')",
    ):
        nested = session.begin_nested()
        with pytest.raises(DatabaseError, match="confirmed review is immutable"):
            session.connection().execute(text(statement), {"id": review.id})
        nested.rollback()
