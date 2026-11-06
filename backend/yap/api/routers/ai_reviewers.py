"""The AI reviewers an investor chooses from (USR-08)."""

from fastapi import APIRouter
from pydantic import BaseModel

from yap.api.deps import CurrentUser, DbSession
from yap.db.models import AiReviewer
from yap.services import ai_reviewers

router = APIRouter(prefix="/ai-reviewers", tags=["reviews"])


class AiReviewerOption(BaseModel):
    """What an investor sees of a reviewer: never its key."""

    id: int
    name: str
    description: str | None
    provider: str
    model: str
    monthly_review_limit: int

    @classmethod
    def of(cls, reviewer: AiReviewer) -> AiReviewerOption:
        return cls(
            id=reviewer.id,
            name=reviewer.name,
            description=reviewer.description,
            provider=reviewer.provider,
            model=reviewer.model,
            monthly_review_limit=reviewer.monthly_review_limit,
        )


class Choice(BaseModel):
    ai_reviewer_id: int | None


@router.get("")
def list_options(session: DbSession, user: CurrentUser) -> list[AiReviewerOption]:
    return [AiReviewerOption.of(r) for r in ai_reviewers.available_reviewers(session, user)]


@router.put("/choice")
def choose(body: Choice, session: DbSession, user: CurrentUser) -> Choice:
    investor = ai_reviewers.choose_reviewer(session, user, body.ai_reviewer_id)
    return Choice(ai_reviewer_id=investor.ai_reviewer_id)
