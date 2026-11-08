"""Drafts and their review: fingerprints and matching, activation that confirms and never
blocks, marks, discard and the change note (POL-06, POL-14, POL-16, POL-17, REV-09,
REV-11, REV-20)."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from tests.fixtures import TEST_SECRET, Factory, FakeLlm, spec
from tests.reviews.answers import answer, suggestion
from yap.db.engine import make_engine, make_session_factory
from yap.db.models import AiReviewer, Investor, Review
from yap.domain.fingerprint import LENGTH, fingerprint
from yap.services import policies, review_prompts, reviews, suggestions
from yap.services.common import ConflictError, NotFoundError, ValidationError
from yap.services.policies import ThesisSpec
from yap.services.secrets import KeyBox

KEYS = KeyBox(TEST_SECRET)
Run = Callable[[Review], Review]


@pytest.fixture
def fake() -> FakeLlm:
    return FakeLlm(answers=[answer()])


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


def _owner(factory: Factory) -> Investor:
    reviewer: AiReviewer = factory.ai_reviewer("Standard")
    owner = factory.investor()
    owner.ai_reviewer_id = reviewer.id
    return owner


def _with_draft(factory: Factory, owner: Investor) -> int:
    """An active policy with a draft v2 that has positions."""
    policy = factory.active_policy(owner)
    policies.create_draft(factory.session, owner, factory.clock, policy.id)
    return policy.id


def _start(factory: Factory, owner: Investor, policy_id: int) -> Review:
    return reviews.start_review(factory.session, owner, factory.clock, KEYS, policy_id, 30)


def _draft(session: Session, owner: Investor, policy_id: int):  # type: ignore[no-untyped-def]
    draft = policies.get_draft(policies.get_policy(session, owner, policy_id))
    assert draft is not None
    return draft


# --- Fingerprints (REV-09) ---------------------------------------------------------------


@dataclass
class _Pos:
    target_pct: Decimal
    buy_threshold_pct: Decimal = Decimal(-20)
    sell_threshold_pct: Decimal = Decimal(20)
    exit: bool = False
    rationale_md: str = ""


@pytest.mark.req("REV-09")
def test_a_fingerprint_covers_title_thesis_and_every_field_of_every_position() -> None:
    base = fingerprint("T", "text", [("AAA", _Pos(Decimal(60))), ("BBB", _Pos(Decimal(40)))])
    assert len(base) == LENGTH and int(base, 16) >= 0
    # The same content gives the same fingerprint, whatever the scale of its numbers
    same = [("AAA", _Pos(Decimal("60.00"))), ("BBB", _Pos(Decimal("40.0")))]
    assert fingerprint("T", "text", same) == base
    changed = [
        fingerprint("T2", "text", same),
        fingerprint("T", "text2", same),
        fingerprint("T", "text", [("AAA", _Pos(Decimal(60)))]),
        fingerprint("T", "text", [same[1], same[0]]),  # the order of the positions
        fingerprint("T", "text", [("AAA", _Pos(Decimal(61))), same[1]]),
        fingerprint("T", "text", [("AAA", _Pos(Decimal(60), Decimal(-10))), same[1]]),
        fingerprint(
            "T", "text", [("AAA", _Pos(Decimal(60), sell_threshold_pct=Decimal(5))), same[1]]
        ),
        fingerprint("T", "text", [("AAA", _Pos(Decimal(60), exit=True)), same[1]]),
        fingerprint("T", "text", [("AAA", _Pos(Decimal(60), rationale_md="why")), same[1]]),
        fingerprint("T", "text", [("AAC", _Pos(Decimal(60))), same[1]]),
    ]
    assert base not in changed and len(set(changed)) == len(changed)


@pytest.mark.req("REV-09", "REV-19")
def test_the_prompt_id_carries_the_fingerprint_of_the_copied_content() -> None:
    issued = datetime(2026, 3, 1, 10, tzinfo=UTC)
    ref = review_prompts.PromptRef(7, issued, 90, "0123456789abcdef")
    assert ref.prompt_id.startswith("R7-20260301T100000Z-90-0123456789abcdef-")
    assert review_prompts.parse_prompt_id(ref.prompt_id) == ref
    # IDs without a fingerprint, from before, still parse
    old = review_prompts.PromptRef(7, issued, 90)
    assert review_prompts.parse_prompt_id(old.prompt_id) == old
    # A changed fingerprint breaks the checksum
    forged = ref.prompt_id.replace("0123456789abcdef", "fedcba9876543210")
    assert review_prompts.parse_prompt_id(forged) is None


# --- Matching (REV-09) -------------------------------------------------------------------


@pytest.mark.req("REV-09")
def test_a_review_no_longer_matches_a_changed_draft_and_matches_again_when_changed_back(
    session: Session, factory: Factory, run: Run
) -> None:
    owner = _owner(factory)
    pid = _with_draft(factory, owner)
    review = run(_start(factory, owner, pid))
    draft = _draft(session, owner, pid)
    assert review.fingerprint == reviews.draft_fingerprint(draft)
    assert reviews.outdated(review, draft) is False
    title, text = draft.thesis_title, draft.thesis_md
    positions = [
        spec(p.asset.ticker, str(p.target_pct), int(p.buy_threshold_pct), int(p.sell_threshold_pct))
        for p in draft.positions
    ]

    policies.update_thesis(session, owner, factory.clock, pid, ThesisSpec(title, "changed"))
    assert reviews.is_outdated(session, review) is True
    policies.update_thesis(session, owner, factory.clock, pid, ThesisSpec(title, text))
    assert reviews.is_outdated(session, review) is False

    policies.update_draft(session, owner, factory.clock, pid, positions=positions[:1])
    assert reviews.is_outdated(session, review) is True
    policies.update_draft(session, owner, factory.clock, pid, positions=positions)
    # Saving the same content again (auto-save) keeps the review matching
    policies.update_draft(session, owner, factory.clock, pid, positions=positions)
    assert reviews.is_outdated(session, review) is False


@pytest.mark.req("REV-09", "REV-18", "REV-19")
def test_a_manual_review_has_the_fingerprint_of_the_content_its_prompt_was_copied_from(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    pid = _with_draft(factory, owner)
    draft = _draft(session, owner, pid)
    title, text = draft.thesis_title, draft.thesis_md
    copied = reviews.draft_fingerprint(draft)
    prompt = reviews.review_prompt(session, owner, factory.clock, pid)
    assert copied in prompt.prompt_id
    # The draft changes after the prompt was copied, before the answer is pasted
    policies.update_thesis(session, owner, factory.clock, pid, ThesisSpec("T", "later"))
    review = reviews.submit_manual_review(
        session, owner, factory.clock, pid, answer(prompt_id=prompt.prompt_id)
    )
    assert review.fingerprint == copied
    assert reviews.is_outdated(session, review) is True
    policies.update_thesis(session, owner, factory.clock, pid, ThesisSpec(title, text))
    assert reviews.is_outdated(session, review) is False


@pytest.mark.req("REV-09", "REV-07")
def test_taking_over_a_suggestion_breaks_the_match_and_undo_restores_it(
    session: Session, factory: Factory, run: Run, fake: FakeLlm
) -> None:
    owner = _owner(factory)
    pid = _with_draft(factory, owner)
    fake.answers = [answer(suggestions=[suggestion("thesis_section", section=7, text="- GDP")])]
    review = run(_start(factory, owner, pid))
    assert reviews.is_outdated(session, review) is False
    (item,) = review.suggestions
    suggestions.take_over(session, owner, factory.clock, review.id, item.id)
    assert reviews.is_outdated(session, review) is True
    suggestions.undo(session, owner, factory.clock, review.id, item.id)
    assert reviews.is_outdated(session, review) is False
    # Edited after the take-over: the undo puts back only the section
    suggestions.take_over(session, owner, factory.clock, review.id, item.id)
    draft = _draft(session, owner, pid)
    edited = draft.thesis_md.replace("# Thesis", "# Thesis edited")
    policies.update_thesis(
        session, owner, factory.clock, pid, ThesisSpec(draft.thesis_title, edited)
    )
    suggestions.undo(session, owner, factory.clock, review.id, item.id)
    assert _draft(session, owner, pid).thesis_md.rstrip() == "# Thesis edited"


@pytest.mark.req("REV-09")
def test_reviews_without_a_fingerprint_compare_times(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    pid = _with_draft(factory, owner)
    draft = _draft(session, owner, pid)
    review = factory.review(owner, draft)
    assert review.fingerprint is None
    assert reviews.outdated(review, draft) is False
    factory.clock.advance(minutes=1)
    policies.update_thesis(session, owner, factory.clock, pid, ThesisSpec("T", "x"))
    assert reviews.outdated(review, draft) is True


# --- Activation (REV-11, REV-20) ---------------------------------------------------------


@pytest.mark.req("REV-11", "REV-20")
def test_activation_without_a_review_is_allowed_and_marks_the_version(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    pid = _with_draft(factory, owner)
    version = policies.activate_draft(session, owner, factory.clock, pid, "No review")
    assert version.activated_at is not None and version.mark == reviews.MARK_NOT_REVIEWED


@pytest.mark.req("REV-11", "REV-20")
def test_activation_with_a_failed_review_drops_it_and_marks_the_version(
    session: Session, factory: Factory, run: Run, fake: FakeLlm
) -> None:
    owner = _owner(factory)
    pid = _with_draft(factory, owner)
    fake.error = "OpenAI answered with error 500"
    review_id = run(_start(factory, owner, pid)).id
    version = policies.activate_draft(session, owner, factory.clock, pid, "x")
    assert version.mark == reviews.MARK_NOT_REVIEWED
    assert session.get(Review, review_id) is None


@pytest.mark.req("REV-11", "REV-20", "NFR-05")
def test_activation_with_a_review_that_no_longer_matches_confirms_it_as_it_is(
    session: Session, factory: Factory, run: Run
) -> None:
    owner = _owner(factory)
    pid = _with_draft(factory, owner)
    review = run(_start(factory, owner, pid))
    policies.update_thesis(session, owner, factory.clock, pid, ThesisSpec("T", "changed"))
    factory.clock.advance(hours=1)
    version = policies.activate_draft(session, owner, factory.clock, pid, "Anyway")
    assert version.mark == reviews.MARK_DID_NOT_MATCH
    session.refresh(review)
    assert review.saved_at == version.activated_at == factory.clock.now()
    assert reviews.is_confirmed(session, review) and not reviews.is_outdated(session, review)
    review.saved_at = None
    with pytest.raises(DatabaseError, match="confirmed review is immutable"):
        session.flush()


@pytest.mark.req("REV-11", "REV-20")
def test_activation_with_a_matching_review_leaves_no_mark(
    session: Session, factory: Factory, run: Run
) -> None:
    owner = _owner(factory)
    pid = _with_draft(factory, owner)
    review = run(_start(factory, owner, pid))
    version = policies.activate_draft(session, owner, factory.clock, pid, "Reviewed")
    assert version.mark is None
    session.refresh(review)
    assert review.saved_at == version.activated_at


@pytest.mark.req("REV-11", "POL-16")
def test_a_running_review_blocks_activation_and_discard(session: Session, factory: Factory) -> None:
    owner = _owner(factory)
    pid = _with_draft(factory, owner)
    _start(factory, owner, pid)
    with pytest.raises(ConflictError, match="still running"):
        policies.activate_draft(session, owner, factory.clock, pid, "x")
    with pytest.raises(ConflictError, match="still running"):
        policies.delete_draft(session, owner, pid)


# --- Discard (POL-16) --------------------------------------------------------------------


@pytest.mark.req("POL-16", "REV-11")
def test_discarding_a_draft_goes_back_to_the_active_version(
    session: Session, factory: Factory, run: Run
) -> None:
    owner = _owner(factory)
    pid = _with_draft(factory, owner)
    review_id = run(_start(factory, owner, pid)).id
    assert policies.delete_draft(session, owner, pid) is False
    policy = policies.get_policy(session, owner, pid)
    assert [v.version_no for v in policy.versions] == [1]
    assert policies.get_draft(policy) is None
    assert session.get(Review, review_id) is None
    # A new draft can be started again, as v2
    assert policies.create_draft(session, owner, factory.clock, pid).version_no == 2


@pytest.mark.req("POL-16", "REV-16")
def test_discarding_a_never_activated_policy_deletes_it(
    session: Session, factory: Factory, run: Run
) -> None:
    owner = _owner(factory)
    policy = factory.policy_draft(owner, positions=[spec("AAA", 100)])
    review_id = run(_start(factory, owner, policy.id)).id
    used = reviews.usage(session, owner, factory.clock, KEYS).used
    assert policies.delete_draft(session, owner, policy.id) is True
    with pytest.raises(NotFoundError):
        policies.get_policy(session, owner, policy.id)
    assert session.get(Review, review_id) is None
    # The run still counts towards the limit
    assert reviews.usage(session, owner, factory.clock, KEYS).used == used == 1
    # The name is free again
    factory.policy_draft(owner, name=policy.name)


# --- Change note and new drafts (POL-06, POL-14, POL-17) ---------------------------------


@pytest.mark.req("POL-14", "POL-17", "POL-06")
def test_the_change_note_is_saved_with_the_draft_and_used_at_activation(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    pid = _with_draft(factory, owner)
    draft = policies.update_change_note(session, owner, factory.clock, pid, "  Wider bands ")
    assert draft.change_note == "Wider bands"
    assert policies.update_change_note(session, owner, factory.clock, pid, "  ").change_note is None
    # From v2 on a note is needed: none saved and none given
    with pytest.raises(ValidationError):
        policies.activate_draft(session, owner, factory.clock, pid, None)
    policies.update_change_note(session, owner, factory.clock, pid, "Wider bands")
    version = policies.activate_draft(session, owner, factory.clock, pid, None)
    assert version.change_note == "Wider bands"
    with pytest.raises(NotFoundError):  # no draft any more
        policies.update_change_note(session, owner, factory.clock, pid, "x")


@pytest.mark.req("POL-14", "POL-01")
def test_a_draft_can_be_saved_in_any_state_e_g_text_only(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    policy = factory.policy_draft(owner)
    draft = policies.update_draft(
        session,
        owner,
        factory.clock,
        policy.id,
        positions=[],
        thesis=ThesisSpec("Only text", "## 1. Belief\nGrowth"),
    )
    assert (draft.thesis_title, draft.positions) == ("Only text", [])
    assert draft.updated_at == factory.clock.now()


@pytest.mark.req("POL-06")
def test_a_new_draft_copies_the_active_version_and_there_is_only_one(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner, thesis_title="Core")
    active = policy.versions[0]
    draft = policies.create_draft(session, owner, factory.clock, policy.id)
    assert (draft.version_no, draft.thesis_title, draft.thesis_md, draft.mark) == (
        2,
        active.thesis_title,
        active.thesis_md,
        None,
    )
    assert [(p.asset.ticker, p.target_pct) for p in draft.positions] == [
        (p.asset.ticker, p.target_pct) for p in active.positions
    ]
    with pytest.raises(ConflictError):
        policies.create_draft(session, owner, factory.clock, policy.id)


@pytest.mark.req("POL-17", "POL-08", "POL-09")
def test_the_summary_shows_the_changes_and_the_portfolios_that_follow(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner)
    portfolio = factory.portfolio(owner, policy)
    active = policy.versions[0]
    draft = policies.create_draft(session, owner, factory.clock, policy.id)
    rows = [
        spec(p.asset.ticker, str(p.target_pct), int(p.buy_threshold_pct), 40)
        for p in draft.positions
    ]
    policies.update_draft(session, owner, factory.clock, policy.id, positions=rows)
    diff = policies.compare_versions(active, draft)
    assert {c.change for c in diff.positions} == {"changed"}
    assert all("sell_threshold_pct" in c.fields for c in diff.positions)
    assert not diff.thesis_changed
    assert [p.id for p in policies.portfolios_using(session, policy)] == [portfolio.id]
