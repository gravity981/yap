"""Timeline events (TL-01 to TL-03).

Events are written by the service that performs the action, in the same
transaction, so an action and its event are always stored together.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from yap.db.models import (
    Investor,
    PolicyVersion,
    Portfolio,
    PortfolioAssignment,
    TimelineEvent,
)
from yap.services.common import get_owned, require_investor


class EventType(StrEnum):
    POLICY_ACTIVATED = "policy_activated"
    PORTFOLIO_ASSIGNED = "portfolio_assigned"
    REBALANCE_CONFIRMED = "rebalance_confirmed"
    THESIS_REVIEW_CONFIRMED = "thesis_review_confirmed"
    POLICY_REVIEW_CONFIRMED = "policy_review_confirmed"
    THESIS_REVISED = "thesis_revised"  # only events from before policies held their thesis


def add_event(
    session: Session,
    investor_id: int,
    occurred_at: datetime,
    event_type: EventType,
    summary: str,
    params: dict[str, Any],
    *,
    portfolio_id: int | None = None,
    policy_version_id: int | None = None,
    rebalance_id: int | None = None,
    review_id: int | None = None,
) -> TimelineEvent:
    event = TimelineEvent(
        investor_id=investor_id,
        occurred_at=occurred_at,
        type=event_type.value,
        summary=summary,
        params=params,
        portfolio_id=portfolio_id,
        policy_version_id=policy_version_id,
        rebalance_id=rebalance_id,
        review_id=review_id,
    )
    session.add(event)
    return event


@dataclass(frozen=True)
class TimelineFilter:
    portfolio_id: int | None = None
    policy_id: int | None = None
    types: frozenset[EventType] | None = None
    start: datetime | None = None
    end: datetime | None = None


def list_events(
    session: Session, actor: Investor, flt: TimelineFilter | None = None
) -> list[TimelineEvent]:
    """Events of `actor` in chronological order (TL-01), optionally filtered (TL-03).

    Filtering by portfolio returns the portfolio's own events plus the events of the
    policies it was assigned to, limited to the periods in which they applied to it.
    """
    require_investor(actor)
    flt = flt or TimelineFilter()
    query = select(TimelineEvent).where(TimelineEvent.investor_id == actor.id)
    if flt.types is not None:
        query = query.where(TimelineEvent.type.in_([t.value for t in flt.types]))
    if flt.start is not None:
        query = query.where(TimelineEvent.occurred_at >= flt.start)
    if flt.end is not None:
        query = query.where(TimelineEvent.occurred_at < flt.end)
    if flt.policy_id is not None:
        query = query.where(
            TimelineEvent.policy_version_id.in_(
                select(PolicyVersion.id).where(PolicyVersion.policy_id == flt.policy_id)
            )
        )
    events = list(session.scalars(query.order_by(TimelineEvent.occurred_at, TimelineEvent.id)))
    if flt.portfolio_id is None:
        return events

    portfolio = get_owned(session, Portfolio, flt.portfolio_id, actor)
    periods = _assignment_periods(portfolio)

    def applies(event: TimelineEvent) -> bool:
        if event.portfolio_id is not None:
            return event.portfolio_id == portfolio.id
        if event.policy_version_id is None:
            return False
        policy_id = session.get(PolicyVersion, event.policy_version_id).policy_id  # type: ignore[union-attr]
        return any(
            pid == policy_id
            and start <= event.occurred_at
            and (end is None or event.occurred_at < end)
            for pid, start, end in periods
        )

    return [e for e in events if applies(e)]


def _assignment_periods(portfolio: Portfolio) -> list[tuple[int, datetime, datetime | None]]:
    assignments: list[PortfolioAssignment] = portfolio.assignments
    periods = []
    for i, a in enumerate(assignments):
        end = assignments[i + 1].valid_from if i + 1 < len(assignments) else None
        periods.append((a.policy_id, a.valid_from, end))
    return periods
