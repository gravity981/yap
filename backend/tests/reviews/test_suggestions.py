"""Take over, dismiss and undo suggestions and proposals of a draft's review (REV-07,
REV-09, REV-22)."""

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.orm import Session

from tests.fixtures import Factory, spec
from yap.db.models import Investor, PolicyVersion, Review, ReviewSuggestion
from yap.domain.suggestions import section_text
from yap.messages import msg
from yap.services import policies, reviews, suggestions
from yap.services.common import ConflictError, NotFoundError


def _setup(session: Session, factory: Factory) -> tuple[Investor, PolicyVersion, Review]:
    """An active policy (AAA 60 %, BBB 40 %) with a draft v2 and its review."""
    owner = factory.investor("alice")
    policy = factory.active_policy(owner)
    draft = policies.create_draft(session, owner, factory.clock, policy.id)
    review = factory.review(owner, draft)
    factory.clock.advance(minutes=1)
    return owner, draft, review


def _rows(draft: PolicyVersion) -> dict[str, dict[str, Any]]:
    return {
        p.asset.ticker: {
            "target": p.target_pct,
            "sell": p.sell_threshold_pct,
            "exit": p.exit,
            "rationale": p.rationale_md,
        }
        for p in draft.positions
    }


def _take_over(
    session: Session, factory: Factory, owner: Investor, s: ReviewSuggestion
) -> PolicyVersion:
    return suggestions.take_over(session, owner, factory.clock, s.review_id, s.id)


def _undo(
    session: Session, factory: Factory, owner: Investor, s: ReviewSuggestion
) -> PolicyVersion:
    return suggestions.undo(session, owner, factory.clock, s.review_id, s.id)


@pytest.mark.req("REV-07", "REV-09")
def test_a_thesis_section_is_taken_over_and_undone(session: Session, factory: Factory) -> None:
    owner, draft, review = _setup(session, factory)
    s = factory.suggestion(review, change={"section": 7, "text": "- GDP below 2 %"})
    assert not reviews.outdated(review, draft)
    draft = _take_over(session, factory, owner, s)
    assert section_text(draft.thesis_md, 7) == "- GDP below 2 %"
    assert s.state == "taken_over"
    assert s.previous is not None
    assert (s.previous["section"], s.previous["text"]) == (7, None)
    assert s.previous["thesis_md"] == "# Thesis"
    # Taking over changes the draft, so the review no longer matches it (REV-09)
    assert reviews.outdated(review, draft)
    draft = _undo(session, factory, owner, s)
    assert draft.thesis_md == "# Thesis"  # exactly as before (REV-09)
    assert (s.state, s.previous) == ("open", None)


@pytest.mark.req("REV-07")
def test_an_existing_section_gets_its_old_text_back_on_undo(
    session: Session, factory: Factory
) -> None:
    owner, draft, review = _setup(session, factory)
    thesis = "# T\n\n## 1. Belief\nOld belief.\n\n## 2. Fit\nFit.\n"
    policies.update_thesis(
        session, owner, factory.clock, draft.policy_id, policies.ThesisSpec("T", thesis)
    )
    s = factory.suggestion(review, change={"section": 1, "text": "New belief."})
    draft = _take_over(session, factory, owner, s)
    assert section_text(draft.thesis_md, 1) == "New belief."
    assert s.previous is not None
    assert (s.previous["section"], s.previous["text"]) == (1, "Old belief.")
    draft = _undo(session, factory, owner, s)
    assert draft.thesis_md == thesis


@pytest.mark.req("REV-07")
@pytest.mark.parametrize(
    ("field", "value", "expected", "key"),
    [
        ("sell_threshold_pct", "30", Decimal(30), "sell"),
        ("target_pct", "55.5", Decimal("55.5"), "target"),
        ("exit", True, True, "exit"),
        ("rationale_md", "Core holding.", "Core holding.", "rationale"),
    ],
)
def test_a_field_of_a_position_is_changed_and_undone(
    session: Session, factory: Factory, field: str, value: Any, expected: Any, key: str
) -> None:
    owner, draft, review = _setup(session, factory)
    before = _rows(draft)
    s = factory.suggestion(
        review, "position_change", {"ticker": "AAA", "field": field, "value": value}
    )
    draft = _take_over(session, factory, owner, s)
    assert _rows(draft)["AAA"][key] == expected
    assert _rows(draft)["BBB"] == before["BBB"]
    assert s.previous is not None and s.previous["field"] == field
    draft = _undo(session, factory, owner, s)
    assert _rows(draft) == before


@pytest.mark.req("REV-07")
def test_a_new_position_is_added_with_its_asset_and_removed_on_undo(
    session: Session, factory: Factory
) -> None:
    owner, draft, review = _setup(session, factory)
    row = {
        "ticker": "NEWX",
        "name": "New fund",
        "type": "ETF",
        "target_pct": "10",
        "buy_threshold_pct": "-25",
        "sell_threshold_pct": "25",
        "exit": False,
        "rationale_md": "Diversifies.",
    }
    s = factory.suggestion(review, "position_add", {"position": row})
    draft = _take_over(session, factory, owner, s)
    assert [p.asset.ticker for p in draft.positions] == ["AAA", "BBB", "NEWX"]
    added = draft.positions[2]
    assert (added.asset.name, added.target_pct, added.rationale_md) == (
        "New fund",
        Decimal(10),
        "Diversifies.",
    )
    draft = _undo(session, factory, owner, s)
    assert [p.asset.ticker for p in draft.positions] == ["AAA", "BBB"]


@pytest.mark.req("REV-07")
def test_a_removed_position_comes_back_at_its_place_on_undo(
    session: Session, factory: Factory
) -> None:
    owner, draft, review = _setup(session, factory)
    before = _rows(draft)
    s = factory.suggestion(review, "position_remove", {"ticker": "AAA"})
    draft = _take_over(session, factory, owner, s)
    assert [p.asset.ticker for p in draft.positions] == ["BBB"]
    assert s.previous is not None and s.previous["index"] == 0
    draft = _undo(session, factory, owner, s)
    assert [p.asset.ticker for p in draft.positions] == ["AAA", "BBB"]
    assert _rows(draft) == before


@pytest.mark.req("REV-22")
def test_a_proposal_fills_the_target_structure_and_undo_empties_it(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor("alice")
    policy = factory.policy_draft(owner)
    draft = policy.versions[0]
    assert draft.positions == []
    review = factory.review(owner, draft, half_points=(14, 12, 16, 10, 14, 13))
    rows = [
        {
            "ticker": "VWRL",
            "name": "All-World",
            "type": "ETF",
            "target_pct": "85",
            "buy_threshold_pct": "-20",
            "sell_threshold_pct": "20",
            "exit": False,
            "rationale_md": "Core.",
        },
        {
            "ticker": "CASH",
            "name": "Cash buffer",
            "type": "cash_buffer",
            "target_pct": "15",
            "buy_threshold_pct": "0",
            "sell_threshold_pct": "0",
            "exit": False,
            "rationale_md": "",
        },
    ]
    s = factory.suggestion(review, "proposal", {"name": "Focused", "positions": rows}, "Close.")
    draft = _take_over(session, factory, owner, s)
    assert [(p.asset.ticker, p.target_pct) for p in draft.positions] == [
        ("VWRL", Decimal(85)),
        ("CASH", Decimal(15)),
    ]
    assert s.previous == {"positions": []}
    draft = _undo(session, factory, owner, s)
    assert draft.positions == []


@pytest.mark.req("REV-07")
def test_a_dismissed_suggestion_changes_nothing_and_can_be_reopened(
    session: Session, factory: Factory
) -> None:
    owner, draft, review = _setup(session, factory)
    thesis = draft.thesis_md
    s = factory.suggestion(review)
    draft = suggestions.dismiss(session, owner, review.id, s.id)
    assert (s.state, draft.thesis_md) == ("dismissed", thesis)
    assert not reviews.outdated(review, draft)
    with pytest.raises(ConflictError) as error:
        _take_over(session, factory, owner, s)
    assert error.value.message == msg("suggestion_not_open")
    draft = _undo(session, factory, owner, s)
    assert (s.state, draft.thesis_md) == ("open", thesis)


@pytest.mark.req("REV-07")
def test_a_suggestion_is_taken_over_once_and_undone_only_after(
    session: Session, factory: Factory
) -> None:
    owner, _, review = _setup(session, factory)
    s = factory.suggestion(review)
    with pytest.raises(ConflictError) as error:
        _undo(session, factory, owner, s)
    assert error.value.message == msg("suggestion_is_open")
    _take_over(session, factory, owner, s)
    with pytest.raises(ConflictError) as error:
        _take_over(session, factory, owner, s)
    assert error.value.message == msg("suggestion_not_open")
    with pytest.raises(ConflictError):
        suggestions.dismiss(session, owner, review.id, s.id)


@pytest.mark.req("REV-07")
def test_a_suggestion_for_a_position_the_draft_no_longer_has_cannot_be_taken_over(
    session: Session, factory: Factory
) -> None:
    owner, draft, review = _setup(session, factory)
    change = factory.suggestion(
        review, "position_change", {"ticker": "ZZZ", "field": "exit", "value": True}
    )
    with pytest.raises(ConflictError) as error:
        _take_over(session, factory, owner, change)
    assert error.value.message == msg("suggestion_position_missing", ticker="ZZZ")
    assert change.state == "open"
    add = factory.suggestion(
        review,
        "position_add",
        {
            "position": {
                "ticker": "AAA",
                "target_pct": "1",
                "buy_threshold_pct": "0",
                "sell_threshold_pct": "0",
                "exit": False,
            }
        },
    )
    with pytest.raises(ConflictError) as error:
        _take_over(session, factory, owner, add)
    assert error.value.message == msg("suggestion_position_exists", ticker="AAA")
    # Undoing a removal after the investor added the position again
    remove = factory.suggestion(review, "position_remove", {"ticker": "BBB"})
    _take_over(session, factory, owner, remove)
    policies.update_draft(
        session,
        owner,
        factory.clock,
        draft.policy_id,
        positions=[spec("AAA", 60), spec("BBB", 40)],
    )
    with pytest.raises(ConflictError) as error:
        _undo(session, factory, owner, remove)
    assert error.value.message == msg("suggestion_position_exists", ticker="BBB")
    # Undoing a change after the investor removed the position
    widen = factory.suggestion(
        review, "position_change", {"ticker": "BBB", "field": "exit", "value": True}
    )
    _take_over(session, factory, owner, widen)
    policies.update_draft(
        session, owner, factory.clock, draft.policy_id, positions=[spec("AAA", 100)]
    )
    with pytest.raises(ConflictError) as error:
        _undo(session, factory, owner, widen)
    assert error.value.message == msg("suggestion_position_missing", ticker="BBB")


@pytest.mark.req("REV-07", "REV-11")
def test_suggestions_of_a_confirmed_or_older_review_cannot_change(
    session: Session, factory: Factory
) -> None:
    owner, draft, review = _setup(session, factory)
    legacy = factory.suggestion(review, "thesis_text", {})
    legacy.change = None
    session.flush()
    with pytest.raises(ConflictError) as error:
        _take_over(session, factory, owner, legacy)
    assert error.value.message == msg("suggestion_without_change")
    s = factory.suggestion(review)
    policies.activate_draft(session, owner, factory.clock, draft.policy_id, "v2")
    with pytest.raises(ConflictError) as error:
        _take_over(session, factory, owner, s)
    assert error.value.message == msg("suggestion_review_confirmed")


@pytest.mark.req("REV-07", "NFR-03")
def test_suggestions_are_found_only_by_the_owner_of_their_review(
    session: Session, factory: Factory
) -> None:
    owner, _, review = _setup(session, factory)
    s = factory.suggestion(review)
    with pytest.raises(NotFoundError) as error:
        suggestions.take_over(session, owner, factory.clock, review.id, s.id + 100)
    assert error.value.message == msg("suggestion_not_found", id=s.id + 100)
    bob = factory.investor("bob")
    with pytest.raises(NotFoundError):
        suggestions.dismiss(session, bob, review.id, s.id)
    assert s.state == "open"
