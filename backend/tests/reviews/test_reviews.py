"""Review lifecycle: start, run, limit, confirm (REV-01 to REV-17)."""

from collections.abc import Callable

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from tests.fixtures import TEST_SECRET, Factory, FakeLlm
from tests.reviews.answers import answer, thesis_answer
from yap.db.engine import make_engine, make_session_factory
from yap.db.models import AiReviewer, Investor, Review
from yap.domain.reviews import SCORING_VERSION
from yap.messages import msg
from yap.services import ai_reviewers, policies, reviews
from yap.services.common import ConflictError, NotFoundError, ValidationError
from yap.services.secrets import KeyBox
from yap.services.timeline import EventType, list_events

KEYS = KeyBox(TEST_SECRET)

Run = Callable[[Review], Review]


@pytest.fixture
def fake() -> FakeLlm:
    return FakeLlm(answers=[answer()])


@pytest.fixture
def run(session: Session, db_url: str, factory: Factory, fake: FakeLlm) -> Run:
    """Runs a started review like the background job: in its own sessions."""
    engine = make_engine(db_url, writer_transactions=False)
    sessions = make_session_factory(engine)

    def run(review: Review) -> Review:
        session.commit()
        reviews.run_review(sessions, factory.clock, KEYS, fake, review.id)
        session.expire_all()
        return review

    yield run  # type: ignore[misc]
    engine.dispose()


def _configure(
    session: Session, factory: Factory, name: str = "Standard", limit: int = 10
) -> AiReviewer:
    """An AI reviewer; investors without a choice get the first one when they start."""
    return factory.ai_reviewer(name, limit=limit)


def _choose_first(session: Session, owner: Investor) -> None:
    if owner.ai_reviewer_id is None:
        owner.ai_reviewer_id = session.scalar(select(AiReviewer.id).order_by(AiReviewer.id))


def _thesis_with_draft(factory: Factory, owner: Investor) -> int:
    """An active policy with a draft v2, which is reviewed; returns the policy."""
    policy = factory.active_policy(owner)
    policies.create_draft(factory.session, owner, factory.clock, policy.id)
    return policy.id


def _start(session: Session, factory: Factory, owner: Investor, policy_id: int) -> Review:
    _choose_first(session, owner)
    return reviews.start_review(session, owner, factory.clock, KEYS, policy_id, 30)


@pytest.mark.req(
    "REV-01", "REV-02", "REV-03", "REV-04", "REV-05", "REV-06", "REV-07", "REV-08", "REV-17"
)
def test_a_review_of_a_draft_runs_and_is_stored(
    session: Session, factory: Factory, run: Run, fake: FakeLlm
) -> None:
    _configure(session, factory)
    owner = factory.investor()
    policy_id = _thesis_with_draft(factory, owner)
    review = _start(session, factory, owner, policy_id)
    assert (review.kind, review.state, review.provider, review.model) == (
        "full",
        "queued",
        "openai",
        "gpt-x",
    )
    assert review.ai_reviewer_name == "Standard"
    assert (review.news_to - review.news_from).days == 30  # type: ignore[operator]
    run(review)
    assert review.state == "done" and review.completed_at is not None
    assert [a.aspect for a in review.aspects][:7] == ["P1", "P2", "P3", "P4", "P5", "P6", "T1"]
    assert {a.aspect: a.half_points for a in review.aspects}["T1"] == 14
    assert (review.verdict, review.verdict_reason) == (
        "warning",
        "Warning signals are observed [1].",
    )
    scores = reviews.scores(review)
    assert (scores.thesis, scores.structure, scores.total) == (13, 15, 14)
    assert reviews.total(review) == 14
    assert reviews.review_semaphore(review) == "warning"
    # The undated source keeps its link; its unreadable date is dropped
    assert [(s.title, s.published_on) for s in review.sources] == [
        ("ETF inflows rise", "2026-01-10"),
        ("Undated", None),
    ]
    assert review.suggestions[0].content_md == "Add a time horizon."
    assert review.scoring_version == SCORING_VERSION == "3"
    # One request with web search, for thesis and target structure together
    assert len(fake.requests) == 1 and fake.requests[0].web_search is True
    assert "<target_structure>" in fake.requests[0].prompt
    assert fake.configs[0].api_key == "sk-test"


@pytest.mark.req("REV-02")
def test_a_draft_without_positions_is_reviewed_on_its_thesis_only(
    session: Session, factory: Factory, run: Run, fake: FakeLlm
) -> None:
    _configure(session, factory)
    owner = factory.investor()
    policy = factory.policy_draft(owner)
    fake.answers = [thesis_answer()]
    review = run(_start(session, factory, owner, policy.id))
    assert review.state == "done"
    scores = reviews.scores(review)
    assert (scores.thesis, scores.structure, scores.total) == (13, None, 13)
    # An answer that scores the target structure anyway fails
    fake.answers = [answer()]
    again = run(_start(session, factory, owner, policy.id))
    assert again.state == "failed" and "exactly the aspects" in (again.error or "")


@pytest.mark.req("REV-01")
def test_only_drafts_of_own_policies_are_reviewed(session: Session, factory: Factory) -> None:
    _configure(session, factory)
    owner, other = factory.investor(), factory.investor()
    policy = factory.active_policy(owner)
    with pytest.raises(NotFoundError, match="no draft"):
        _start(session, factory, owner, policy.id)
    policies.create_draft(session, owner, factory.clock, policy.id)
    with pytest.raises(NotFoundError):
        _start(session, factory, other, policy.id)
    with pytest.raises(ValidationError):
        reviews.start_review(session, owner, factory.clock, KEYS, policy.id, 0)


@pytest.mark.req("REV-08")
@pytest.mark.parametrize(
    ("error", "answer", "message"),
    [
        ("OpenAI did not answer in time", None, "OpenAI did not answer in time"),
        (None, "not json", "no JSON object"),
    ],
)
def test_a_failed_run_keeps_its_reason(
    session: Session,
    factory: Factory,
    run: Run,
    fake: FakeLlm,
    error: str | None,
    answer: str | None,
    message: str,
) -> None:
    _configure(session, factory)
    owner = factory.investor()
    fake.error = error
    if answer:
        fake.answers = [answer]
    review = run(_start(session, factory, owner, _thesis_with_draft(factory, owner)))
    assert review.state == "failed" and message in (review.error or "")
    assert review.aspects == []


@pytest.mark.req("REV-08")
def test_an_unexpected_error_is_shown_with_its_type_but_without_the_key(
    session: Session, factory: Factory, run: Run, fake: FakeLlm
) -> None:
    _configure(session, factory)
    owner = factory.investor()
    fake.crash = ValueError("bad response for key sk-test")
    review = run(_start(session, factory, owner, _thesis_with_draft(factory, owner)))
    assert review.state == "failed"
    assert review.error == "The review failed unexpectedly (ValueError: bad response for key ***)"


@pytest.mark.req("REV-08")
def test_reviews_interrupted_by_a_restart_fail(session: Session, factory: Factory) -> None:
    _configure(session, factory)
    owner = factory.investor()
    review = _start(session, factory, owner, _thesis_with_draft(factory, owner))
    assert reviews.fail_interrupted(session, factory.clock) == 1
    assert review.state == "failed" and "restart" in (review.error or "")


@pytest.mark.req("REV-16")
def test_every_started_run_counts_towards_the_monthly_limit(
    session: Session, factory: Factory, run: Run, fake: FakeLlm
) -> None:
    _configure(session, factory, limit=2)
    owner = factory.investor()
    thesis_id = _thesis_with_draft(factory, owner)
    fake.error = "OpenAI answered with error 500"
    run(_start(session, factory, owner, thesis_id))  # failed runs count too
    fake.error = None
    run(_start(session, factory, owner, thesis_id))  # a re-run on the same draft counts
    usage = reviews.usage(session, owner, factory.clock, KEYS)
    assert (usage.used, usage.left) == (2, 0)
    with pytest.raises(ConflictError, match="All 2 reviews with Standard of this month are used"):
        _start(session, factory, owner, thesis_id)
    # Other investors have their own count; a new month starts at 0 (UTC)
    assert reviews.usage(session, factory.investor(), factory.clock, KEYS).used == 0
    factory.clock.advance(days=17)  # 2026-02-01
    assert reviews.usage(session, owner, factory.clock, KEYS).used == 0
    _start(session, factory, owner, thesis_id)


@pytest.mark.req("REV-16", "USR-08")
def test_the_chosen_ai_reviewer_decides(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    thesis_id = _thesis_with_draft(factory, owner)
    usage = reviews.usage(session, owner, factory.clock, KEYS)
    assert usage.unavailable_reason == msg("review_choose_reviewer")
    assert str(usage.unavailable_reason) == "Choose an AI reviewer"
    with pytest.raises(ConflictError, match="Choose an AI reviewer"):
        reviews.start_review(session, owner, factory.clock, KEYS, thesis_id, 30)
    none = _configure(session, factory, "None", limit=0)
    ai_reviewers.choose_reviewer(session, owner, none.id)
    assert "includes no reviews" in (
        str(reviews.usage(session, owner, factory.clock, KEYS).unavailable_reason)
    )
    with pytest.raises(ConflictError, match="includes no reviews"):
        _start(session, factory, owner, thesis_id)
    deep = _configure(session, factory, "Deep", limit=5)
    ai_reviewers.choose_reviewer(session, owner, deep.id)
    usage = reviews.usage(session, owner, factory.clock, KEYS)
    assert (usage.reviewer_name, usage.limit, usage.unavailable_reason) == ("Deep", 5, None)


@pytest.mark.req("USR-08", "REV-16", "REV-17")
def test_each_review_can_use_another_reviewer_than_the_default(
    session: Session, factory: Factory, run: Run, fake: FakeLlm
) -> None:
    owner = factory.investor()
    standard = _configure(session, factory, "Standard")
    deep = factory.ai_reviewer("Deep", provider="anthropic", model="claude-x", limit=1)
    off = factory.ai_reviewer("Off", enabled=False)
    ai_reviewers.choose_reviewer(session, owner, standard.id)
    thesis_id = _thesis_with_draft(factory, owner)
    review = reviews.start_review(
        session, owner, factory.clock, KEYS, thesis_id, 30, reviewer_id=deep.id
    )
    assert (review.ai_reviewer_name, review.provider) == ("Deep", "anthropic")
    run(review)
    assert fake.configs[-1].model == "claude-x"
    assert owner.ai_reviewer_id == standard.id  # the default stays
    # The limit is that of the reviewer used; the default is not touched
    assert reviews.usage(session, owner, factory.clock, KEYS, deep.id).left == 0
    assert reviews.usage(session, owner, factory.clock, KEYS).used == 0
    with pytest.raises(ConflictError, match="All 1 reviews with Deep"):
        reviews.start_review(
            session, owner, factory.clock, KEYS, thesis_id, 30, reviewer_id=deep.id
        )
    with pytest.raises(ConflictError, match="disabled"):
        reviews.start_review(session, owner, factory.clock, KEYS, thesis_id, 30, reviewer_id=off.id)
    with pytest.raises(NotFoundError):
        reviews.usage(session, owner, factory.clock, KEYS, 999)
    policy = factory.active_policy(owner)
    policies.create_draft(session, owner, factory.clock, policy.id)
    started = reviews.start_review(
        session, owner, factory.clock, KEYS, policy.id, reviewer_id=standard.id
    )
    assert started.ai_reviewer_name == "Standard"


@pytest.mark.req("REV-16")
def test_the_limit_counts_per_ai_reviewer(session: Session, factory: Factory, run: Run) -> None:
    owner = factory.investor()
    thesis_id = _thesis_with_draft(factory, owner)
    quick = _configure(session, factory, "Quick", limit=1)
    deep = _configure(session, factory, "Deep")
    ai_reviewers.choose_reviewer(session, owner, quick.id)
    run(_start(session, factory, owner, thesis_id))
    assert reviews.usage(session, owner, factory.clock, KEYS).left == 0
    ai_reviewers.choose_reviewer(session, owner, deep.id)
    usage = reviews.usage(session, owner, factory.clock, KEYS)
    assert (usage.reviewer_name, usage.used, usage.left) == ("Deep", 0, 10)
    _start(session, factory, owner, thesis_id)


@pytest.mark.req("REV-13", "REV-16")
@pytest.mark.parametrize(
    ("change", "message"),
    [("disable", "is disabled"), ("archive", "is no longer available")],
)
def test_disabled_or_archived_reviewers_run_no_reviews(
    session: Session, factory: Factory, run: Run, change: str, message: str
) -> None:
    owner = factory.investor()
    reviewer = _configure(session, factory)
    queued = _start(session, factory, owner, _thesis_with_draft(factory, owner))
    if change == "disable":
        reviewer.enabled = False
    else:
        ai_reviewers.archive_reviewer(session, factory.admin(), factory.clock, reviewer.id)
    assert message in str(reviews.usage(session, owner, factory.clock, KEYS).unavailable_reason)
    # A review started before runs on its reviewer, so it fails with the reason
    run(queued)
    assert queued.state == "failed" and message in (queued.error or "")


@pytest.mark.req("REV-09")
def test_a_new_run_replaces_the_previous_review_of_the_draft(
    session: Session, factory: Factory, run: Run, fake: FakeLlm
) -> None:
    _configure(session, factory)
    owner = factory.investor()
    thesis_id = _thesis_with_draft(factory, owner)
    first = _start(session, factory, owner, thesis_id)
    with pytest.raises(ConflictError, match="still running"):
        _start(session, factory, owner, thesis_id)
    run(first)
    fake.answers = [answer(verdict="good")]
    second = run(_start(session, factory, owner, thesis_id))
    assert session.scalars(select(Review)).all() == [second]
    assert second.verdict == "good"


@pytest.mark.req("REV-09", "REV-06")
def test_a_new_review_replaces_the_reviews_of_a_draft_from_before_stage_2(
    session: Session, factory: Factory, run: Run
) -> None:
    _configure(session, factory)
    owner = factory.investor()
    policy_id = _thesis_with_draft(factory, owner)
    draft = policies.get_draft(policies.get_policy(session, owner, policy_id))
    assert draft is not None
    factory.review(owner, draft, kind="thesis", verdict="intact", scoring_version="2")
    factory.review(owner, draft, kind="policy", scoring_version="2")
    review = run(_start(session, factory, owner, policy_id))
    assert session.scalars(select(Review)).all() == [review]


@pytest.mark.req("REV-09")
def test_a_review_is_outdated_when_the_draft_changes(
    session: Session, factory: Factory, run: Run, fake: FakeLlm
) -> None:
    _configure(session, factory)
    owner = factory.investor()
    thesis_id = _thesis_with_draft(factory, owner)
    review = run(_start(session, factory, owner, thesis_id))
    assert reviews.is_outdated(session, review) is False
    factory.clock.advance(minutes=5)
    policies.update_thesis(
        session, owner, factory.clock, thesis_id, policies.ThesisSpec("T", "new")
    )
    assert reviews.is_outdated(session, review) is True

    policy = factory.active_policy(owner)
    policies.create_draft(session, owner, factory.clock, policy.id)
    policy_review = run(_start(session, factory, owner, policy.id))
    factory.clock.advance(minutes=5)
    policies.update_draft(session, owner, factory.clock, policy.id, positions=[])
    assert reviews.is_outdated(session, policy_review) is True


@pytest.mark.req("REV-11", "REV-12", "TL-01", "TL-02", "NFR-05")
def test_activating_the_draft_confirms_the_review(
    session: Session, factory: Factory, run: Run
) -> None:
    _configure(session, factory)
    owner, reader = factory.investor(), factory.investor()
    thesis_id = _thesis_with_draft(factory, owner)
    review = run(_start(session, factory, owner, thesis_id))
    # A draft's review is the owner's only and is not in the timeline yet
    with pytest.raises(NotFoundError):
        reviews.get_review(session, reader, review.id)
    assert EventType.REVIEW_CONFIRMED not in [e.type for e in list_events(session, owner)]
    policies.activate_draft(session, owner, factory.clock, thesis_id, "Reviewed")
    assert reviews.is_confirmed(session, review)
    event = list_events(session, owner)[-1]
    label = reviews.draft_of(session, review).label
    assert event.type == EventType.REVIEW_CONFIRMED and event.review_id == review.id
    assert event.summary == f"Review of {label}: warning, 7 / 10"
    assert event.params == {"version": label, "verdict": "warning", "total": 7.0}
    with pytest.raises(NotFoundError):  # reviews are the owner's (REV-12)
        reviews.get_review(session, reader, review.id)
    review.aspects[0].half_points = 1
    with pytest.raises(DatabaseError, match="confirmed review is immutable"):
        session.flush()


@pytest.mark.req("REV-11", "REV-12", "TL-01", "REV-06")
def test_activating_confirms_reviews_from_before_stage_2_with_their_events(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner)
    draft = policies.create_draft(session, owner, factory.clock, policy.id)
    factory.review(owner, draft, kind="thesis", verdict="needs_adaptation", scoring_version="2")
    factory.review(owner, draft, kind="policy", half_points=(16,) * 6, scoring_version="2")
    policies.activate_draft(session, owner, factory.clock, policy.id, "Reviewed")
    events = sorted(list_events(session, owner)[-2:], key=lambda e: e.type)
    assert [(e.type, e.summary) for e in events] == [
        (EventType.POLICY_REVIEW_CONFIRMED, f"Policy review of {draft.label}: 8 / 10"),
        (EventType.THESIS_REVIEW_CONFIRMED, f"Thesis review of {draft.label}: warning, 6.5 / 10"),
    ]
    assert events[1].params == {"version": draft.label, "verdict": "warning", "total": 6.5}


@pytest.mark.req("REV-11")
def test_a_running_review_blocks_activation_and_deletion(
    session: Session, factory: Factory, run: Run, fake: FakeLlm
) -> None:
    _configure(session, factory)
    owner = factory.investor()
    thesis_id = _thesis_with_draft(factory, owner)
    review = _start(session, factory, owner, thesis_id)
    with pytest.raises(ConflictError, match="still running"):
        policies.activate_draft(session, owner, factory.clock, thesis_id, "x")
    with pytest.raises(ConflictError, match="still running"):
        policies.delete_draft(session, owner, thesis_id)
    fake.error = "OpenAI answered with error 500"
    run(review)
    review_id = review.id
    # A failed review is dropped on activation; it is not confirmed
    policies.activate_draft(session, owner, factory.clock, thesis_id, "x")
    assert session.get(Review, review_id) is None


@pytest.mark.req("REV-11")
def test_deleting_the_draft_deletes_its_review(
    session: Session, factory: Factory, run: Run
) -> None:
    _configure(session, factory)
    owner = factory.investor()
    thesis_id = _thesis_with_draft(factory, owner)
    review_id = run(_start(session, factory, owner, thesis_id)).id
    policies.delete_draft(session, owner, thesis_id)
    assert session.get(Review, review_id) is None


@pytest.mark.req("REV-18", "REV-09")
def test_no_manual_answer_while_an_ai_review_runs(session: Session, factory: Factory) -> None:
    from yap.services import review_prompts

    _configure(session, factory)
    owner = factory.investor()
    policy_id = _thesis_with_draft(factory, owner)
    queued = _start(session, factory, owner, policy_id)
    prompt = reviews.review_prompt(session, owner, factory.clock, policy_id)
    assert review_prompts.parse_prompt_id(prompt.prompt_id) is not None
    with pytest.raises(ConflictError, match="still running"):
        reviews.submit_manual_review(
            session, owner, factory.clock, policy_id, answer(prompt_id=prompt.prompt_id)
        )
    draft = reviews.draft_of(session, queued)
    assert reviews.current_review(draft) == queued


@pytest.mark.req("REV-18", "REV-17", "REV-19", "REV-03")
def test_a_manual_review_names_no_model(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policy_id = _thesis_with_draft(factory, owner)
    factory.clock.advance(minutes=1)
    prompt = reviews.review_prompt(session, owner, factory.clock, policy_id, news_days=60)
    review = reviews.submit_manual_review(
        session, owner, factory.clock, policy_id, answer(prompt_id=prompt.prompt_id)
    )
    assert (review.kind, review.method, review.provider, review.model) == (
        "full",
        "manual",
        "manual",
        None,
    )
    assert (review.ai_reviewer_id, review.prompt_id) == (None, prompt.prompt_id)
    assert (review.news_to - review.news_from).days == 60  # type: ignore[operator]
    assert review.verdict_reason == "Warning signals are observed [1]."
    assert reviews.total(review) == 14


@pytest.mark.req("REV-25")
def test_the_review_is_written_in_the_language_of_the_investor(
    session: Session, factory: Factory, run: Run, fake: FakeLlm
) -> None:
    _configure(session, factory)
    owner = factory.investor()
    owner.language = "de"
    policy_id = _thesis_with_draft(factory, owner)
    # The prompt to copy into an AI outside the app (REV-19) and the one of an AI reviewer
    manual = reviews.review_prompt(session, owner, factory.clock, policy_id)
    assert "in German" in manual.instructions
    run(_start(session, factory, owner, policy_id))
    assert "in German" in fake.requests[0].system
