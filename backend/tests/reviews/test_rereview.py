"""Reviews of the active version, the review log and the latest review (POL-20, REV-12,
REV-20, REV-21, REV-23)."""

from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from tests.fixtures import TEST_SECRET, Factory, FakeLlm
from tests.reviews.answers import answer, suggestion
from yap.db.engine import make_engine, make_session_factory
from yap.db.models import AiReviewer, Investor, Policy, Review, ReviewRun
from yap.domain.reviews import Verdict
from yap.messages import msg
from yap.services import policies, reviews, suggestions
from yap.services.common import ConflictError, NotFoundError
from yap.services.secrets import KeyBox
from yap.services.timeline import EventType, TimelineFilter, list_events

KEYS = KeyBox(TEST_SECRET)

Run = Callable[[Review], Review]


@pytest.fixture
def fake() -> FakeLlm:
    return FakeLlm(answers=[answer(verdict="broken")])


@pytest.fixture
def run(session: Session, db_url: str, factory: Factory, fake: FakeLlm) -> Iterator[Run]:
    """Runs a started review like the background job: in its own sessions."""
    engine = make_engine(db_url)
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


@pytest.mark.req("POL-20", "REV-12", "REV-21", "POL-11", "THS-04")
def test_an_ai_review_of_the_active_version_is_saved_in_its_log(
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
    event = list_events(session, owner, TimelineFilter(types=frozenset({EventType.REVIEW_SAVED})))[
        0
    ]
    assert event.review_id == review.id
    assert event.summary == f"Review of {v1.label} (again): broken, 7 / 10"
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


@pytest.mark.req("POL-20", "REV-18", "REV-19", "REV-20", "REV-21")
def test_a_manual_review_of_the_active_version_is_saved_at_once_and_clears_the_mark(
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
        answer(verdict="good", prompt_id=prompt.prompt_id),
        active=True,
    )
    assert (review.method, review.saved_at) == ("manual", factory.clock.now())
    session.expire_all()
    assert reviews.current_review(v1) is review
    assert v1.mark == "not_reviewed"  # stored as it was at activation
    assert reviews.effective_mark(v1) is None  # but it no longer counts
    assert reviews.effective_mark(v1) is None
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


@pytest.mark.req("REV-07", "POL-20")
def test_suggestions_of_a_review_of_the_active_version_go_into_a_draft(
    session: Session, factory: Factory, fake: FakeLlm, run: Run
) -> None:
    fake.answers = [
        answer(
            suggestions=[
                suggestion("position_change", "Wider.", ticker="AAA", sell_threshold_pct=30),
                suggestion("thesis_section", "Horizon.", section=1, text="Ten years."),
                suggestion("position_remove", "Drop.", ticker="BBB"),
            ]
        )
    ]
    owner = _owner(session, factory)
    policy = _active(factory, owner)
    review = run(_again(session, factory, owner, policy))
    change, section, remove = review.suggestions
    # Dismissing needs no draft
    assert suggestions.dismiss(session, owner, factory.clock, review.id, remove.id) is None
    assert policies.get_draft(policy) is None
    # Take over creates the draft of v2 and applies the change there
    draft = suggestions.take_over(session, owner, factory.clock, review.id, change.id)
    assert (draft.version_no, draft.activated_at) == (2, None)
    assert {p.asset.ticker: str(p.sell_threshold_pct) for p in draft.positions}["AAA"] == "30"
    assert change.state == "taken_over"
    # A second one goes into the same draft
    again = suggestions.take_over(session, owner, factory.clock, review.id, section.id)
    assert again.id == draft.id and "Ten years." in again.thesis_md
    # The active version stays as it was
    v1 = policy.versions[0]
    assert {p.asset.ticker: str(p.sell_threshold_pct) for p in v1.positions}["AAA"] != "30"
    # Undo works in the draft
    undone = suggestions.undo(session, owner, factory.clock, review.id, change.id)
    assert undone is not None and undone.id == draft.id
    assert change.state == "open"
    # Without the draft, a taken over suggestion cannot be undone
    policies.delete_draft(session, owner, policy.id)
    with pytest.raises(ConflictError) as error:
        suggestions.undo(session, owner, factory.clock, review.id, section.id)
    assert error.value.message == msg("suggestion_no_draft")
    # Reopening a dismissed one needs no draft either
    assert suggestions.undo(session, owner, factory.clock, review.id, remove.id) is None


@pytest.mark.req("REV-12", "REV-11", "POL-20")
def test_a_saved_review_is_immutable_but_its_suggestions_may_change_state(
    session: Session, factory: Factory
) -> None:
    owner = _owner(session, factory)
    policy = factory.active_policy(owner)
    draft = policies.create_draft(session, owner, factory.clock, policy.id)
    review = factory.review(owner, draft)
    s = factory.suggestion(review)
    factory.clock.advance(minutes=1)
    policies.activate_draft(session, owner, factory.clock, policy.id, "v2")
    assert review.saved_at is not None
    session.commit()
    session.connection().execute(
        text("UPDATE review_suggestion SET state = 'dismissed' WHERE id = :id"), {"id": s.id}
    )
    for statement in (
        "UPDATE review SET verdict = 'broken' WHERE id = :id",
        "DELETE FROM review WHERE id = :id",
        "UPDATE review_aspect SET half_points = 0 WHERE review_id = :id",
        "UPDATE review_suggestion SET content_md = 'x' WHERE review_id = :id",
        "INSERT INTO review_source (review_id, title, url) VALUES (:id, 't', 'u')",
    ):
        nested = session.begin_nested()
        with pytest.raises(DatabaseError, match="confirmed review is immutable"):
            session.connection().execute(text(statement), {"id": review.id})
        nested.rollback()
