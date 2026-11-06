"""Timeline (TL-01, TL-03)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from yap.api.deps import CurrentUser, DbSession
from yap.api.schemas import EventOut
from yap.services.timeline import EventType, TimelineFilter, list_events

router = APIRouter(tags=["timeline"])


@router.get("/timeline")
def timeline(
    session: DbSession,
    user: CurrentUser,
    portfolio_id: int | None = None,
    policy_id: int | None = None,
    type: Annotated[list[EventType] | None, Query()] = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[EventOut]:
    flt = TimelineFilter(
        portfolio_id=portfolio_id,
        policy_id=policy_id,
        types=frozenset(type) if type else None,
        start=start,
        end=end,
    )
    return [EventOut.of(e) for e in list_events(session, user, flt)]
