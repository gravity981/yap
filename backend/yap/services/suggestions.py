"""Take over, dismiss and undo suggestions and proposals of a draft's review (REV-07,
REV-22).

Nothing is applied without the investor's click. Taking over changes the draft like an
edit (POL-14): it is saved at once, and the review no longer matches the draft (REV-09).
The suggestion keeps what it replaced, so it can be undone.
"""

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from yap.db.models import Investor, PolicyPosition, PolicyVersion, ReviewSuggestion
from yap.domain.suggestions import (
    SuggestionKind,
    SuggestionState,
    replace_section,
    section_text,
)
from yap.messages import msg
from yap.services import policies, reviews
from yap.services.common import Clock, ConflictError, NotFoundError
from yap.services.policies import PositionSpec, ThesisSpec


def _row(p: PolicyPosition) -> dict[str, Any]:
    return {
        "ticker": p.asset.ticker,
        "name": p.asset.name,
        "type": p.asset.type,
        "target_pct": str(p.target_pct),
        "buy_threshold_pct": str(p.buy_threshold_pct),
        "sell_threshold_pct": str(p.sell_threshold_pct),
        "exit": p.exit,
        "rationale_md": p.rationale_md,
    }


def _spec(row: dict[str, Any]) -> PositionSpec:
    return PositionSpec(
        ticker=row["ticker"],
        name=row.get("name") or None,
        type=row.get("type") or None,
        target_pct=Decimal(row["target_pct"]),
        buy_threshold_pct=Decimal(row["buy_threshold_pct"]),
        sell_threshold_pct=Decimal(row["sell_threshold_pct"]),
        exit=bool(row["exit"]),
        rationale_md=row.get("rationale_md") or "",
    )


def _value(p: PolicyPosition, name: str) -> Any:
    value = getattr(p, name)
    return str(value) if isinstance(value, Decimal) else value


def _find(
    session: Session,
    actor: Investor,
    clock: Clock,
    review_id: int,
    suggestion_id: int,
) -> tuple[ReviewSuggestion, PolicyVersion]:
    """The suggestion and the draft it changes: the open draft its review belongs to.
    Activating the draft removes its suggestions (REV-07), so there are none to change on
    an activated version."""
    review = reviews.get_review(session, actor, review_id)
    suggestion = next((s for s in review.suggestions if s.id == suggestion_id), None)
    if suggestion is None:
        raise NotFoundError(msg("suggestion_not_found", id=suggestion_id))
    if suggestion.change is None:
        raise ConflictError(msg("suggestion_without_change"))
    version = reviews.draft_of(session, review)
    if version.activated_at is not None:
        raise ConflictError(msg("suggestion_review_confirmed"))
    return suggestion, version


def _rows(draft: PolicyVersion) -> list[dict[str, Any]]:
    return [_row(p) for p in draft.positions]


def _save_rows(
    session: Session,
    actor: Investor,
    clock: Clock,
    draft: PolicyVersion,
    rows: list[dict[str, Any]],
) -> None:
    policies.update_draft(
        session, actor, clock, draft.policy_id, positions=[_spec(r) for r in rows]
    )


def _index(rows: list[dict[str, Any]], ticker: str) -> int:
    i = next((i for i, r in enumerate(rows) if r["ticker"] == ticker), None)
    if i is None:
        raise ConflictError(msg("suggestion_position_missing", ticker=ticker))
    return i


def _apply(
    session: Session,
    actor: Investor,
    clock: Clock,
    draft: PolicyVersion,
    kind: SuggestionKind,
    change: dict[str, Any],
) -> dict[str, Any]:
    """Applies a change to the draft; returns what it replaced."""
    if kind == SuggestionKind.THESIS_SECTION:
        section = int(change["section"])
        before = draft.thesis_md
        old_text = section_text(before, section)
        thesis = replace_section(before, section, change["text"])
        policies.update_thesis(
            session, actor, clock, draft.policy_id, ThesisSpec(draft.thesis_title, thesis)
        )
        # The whole text before and after, so an undo right after restores it exactly
        return {"section": section, "text": old_text, "thesis_md": before, "applied_md": thesis}
    rows = _rows(draft)
    if kind == SuggestionKind.PROPOSAL:
        _save_rows(session, actor, clock, draft, list(change["positions"]))
        return {"positions": rows}
    if kind == SuggestionKind.POSITION_ADD:
        ticker = change["position"]["ticker"]
        if any(r["ticker"] == ticker for r in rows):
            raise ConflictError(msg("suggestion_position_exists", ticker=ticker))
        _save_rows(session, actor, clock, draft, [*rows, change["position"]])
        return {"ticker": ticker}
    i = _index(rows, change["ticker"])
    if kind == SuggestionKind.POSITION_REMOVE:
        removed = rows.pop(i)
        _save_rows(session, actor, clock, draft, rows)
        return {"position": removed, "index": i}
    # position_change
    name = change["field"]
    previous = {
        "ticker": change["ticker"],
        "field": name,
        "value": _value(draft.positions[i], name),
    }
    rows[i] = {**rows[i], name: change["value"]}
    _save_rows(session, actor, clock, draft, rows)
    return previous


def _revert(
    session: Session,
    actor: Investor,
    clock: Clock,
    draft: PolicyVersion,
    kind: SuggestionKind,
    previous: dict[str, Any],
) -> None:
    """Undoes a change with what it replaced."""
    if kind == SuggestionKind.THESIS_SECTION:
        if "thesis_md" in previous and draft.thesis_md == previous.get("applied_md"):
            thesis = previous["thesis_md"]  # unchanged since: exactly as before (REV-09)
        else:  # changed since: only the section goes back
            thesis = replace_section(draft.thesis_md, int(previous["section"]), previous["text"])
        policies.update_thesis(
            session, actor, clock, draft.policy_id, ThesisSpec(draft.thesis_title, thesis)
        )
        return
    rows = _rows(draft)
    if kind == SuggestionKind.PROPOSAL:
        rows = list(previous["positions"])
    elif kind == SuggestionKind.POSITION_ADD:
        rows.pop(_index(rows, previous["ticker"]))
    elif kind == SuggestionKind.POSITION_REMOVE:
        ticker = previous["position"]["ticker"]
        if any(r["ticker"] == ticker for r in rows):
            raise ConflictError(msg("suggestion_position_exists", ticker=ticker))
        rows.insert(min(int(previous["index"]), len(rows)), previous["position"])
    else:
        i = _index(rows, previous["ticker"])
        rows[i] = {**rows[i], previous["field"]: previous["value"]}
    _save_rows(session, actor, clock, draft, rows)


def take_over(
    session: Session, actor: Investor, clock: Clock, review_id: int, suggestion_id: int
) -> PolicyVersion:
    """REV-07, REV-22: applies an open suggestion or proposal to the draft."""
    suggestion, draft = _find(session, actor, clock, review_id, suggestion_id)
    if suggestion.state != SuggestionState.OPEN:
        raise ConflictError(msg("suggestion_not_open"))
    assert suggestion.change is not None
    suggestion.previous = _apply(
        session, actor, clock, draft, SuggestionKind(suggestion.kind), suggestion.change
    )
    suggestion.state = SuggestionState.TAKEN_OVER.value
    session.flush()
    session.refresh(draft)
    return draft


def dismiss(
    session: Session, actor: Investor, clock: Clock, review_id: int, suggestion_id: int
) -> PolicyVersion:
    """REV-07: the investor does not want an open suggestion: it is deleted, for good. The
    draft stays as it is."""
    suggestion, draft = _find(session, actor, clock, review_id, suggestion_id)
    if suggestion.state != SuggestionState.OPEN:
        raise ConflictError(msg("suggestion_not_open"))
    session.delete(suggestion)
    session.flush()
    return draft


def undo(
    session: Session, actor: Investor, clock: Clock, review_id: int, suggestion_id: int
) -> PolicyVersion:
    """REV-07: a taken over suggestion is reverted in the draft and is open again."""
    suggestion, draft = _find(session, actor, clock, review_id, suggestion_id)
    if suggestion.state != SuggestionState.TAKEN_OVER:
        raise ConflictError(msg("suggestion_is_open"))
    assert suggestion.previous is not None
    _revert(session, actor, clock, draft, SuggestionKind(suggestion.kind), suggestion.previous)
    suggestion.state = SuggestionState.OPEN.value
    suggestion.previous = None
    session.flush()
    session.refresh(draft)
    return draft
