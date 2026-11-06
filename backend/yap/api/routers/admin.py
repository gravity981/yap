"""Account management (USR-02, USR-05, USR-06, USR-09) and AI reviewers (REV-13 to
REV-15) for admins."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from yap.api.deps import AppClock, AppKeys, CurrentAdmin, DbSession, LlmAdapters
from yap.db.models import AiReviewer, Investor
from yap.services import accounts, ai_reviewers

router = APIRouter(prefix="/admin/accounts", tags=["admin"])
reviewers_router = APIRouter(prefix="/admin/ai-reviewers", tags=["admin"])


class Account(BaseModel):
    id: int
    username: str
    is_admin: bool
    is_investor: bool
    base_currency: str | None
    active: bool
    must_change_password: bool
    created_at: datetime

    @classmethod
    def of(cls, investor: Investor) -> Account:
        return cls(
            id=investor.id,
            username=investor.username,
            is_admin=investor.is_admin,
            is_investor=investor.is_investor,
            base_currency=investor.base_currency,
            active=investor.active,
            must_change_password=investor.must_change_password,
            created_at=investor.created_at,
        )


class NewAccount(BaseModel):
    username: str
    temporary_password: str
    is_admin: bool = False
    is_investor: bool = True
    base_currency: str | None = None  # required with the investor role


class Roles(BaseModel):
    is_admin: bool
    is_investor: bool
    base_currency: str | None = None  # required when the investor role is added


class PasswordReset(BaseModel):
    temporary_password: str


class BaseCurrency(BaseModel):
    base_currency: str


@router.get("")
def list_accounts(session: DbSession, admin: CurrentAdmin) -> list[Account]:
    return [Account.of(a) for a in accounts.list_accounts(session, admin)]


@router.post("", status_code=201)
def create_account(
    body: NewAccount, session: DbSession, clock: AppClock, admin: CurrentAdmin
) -> Account:
    account = accounts.admin_create_account(
        session,
        admin,
        clock,
        username=body.username,
        temporary_password=body.temporary_password,
        admin=body.is_admin,
        investor=body.is_investor,
        base_currency=body.base_currency,
    )
    return Account.of(account)


@router.put("/{account_id}/roles")
def set_roles(account_id: int, body: Roles, session: DbSession, admin: CurrentAdmin) -> Account:
    """USR-09"""
    account = accounts.set_roles(
        session,
        admin,
        account_id,
        admin=body.is_admin,
        investor=body.is_investor,
        base_currency=body.base_currency,
    )
    return Account.of(account)


@router.post("/{account_id}/deactivate")
def deactivate(account_id: int, session: DbSession, admin: CurrentAdmin) -> Account:
    return Account.of(accounts.deactivate(session, admin, account_id))


@router.post("/{account_id}/reactivate")
def reactivate(account_id: int, session: DbSession, admin: CurrentAdmin) -> Account:
    return Account.of(accounts.reactivate(session, admin, account_id))


@router.post("/{account_id}/reset-password")
def reset_password(
    account_id: int, body: PasswordReset, session: DbSession, admin: CurrentAdmin
) -> Account:
    return Account.of(accounts.reset_password(session, admin, account_id, body.temporary_password))


@router.put("/{account_id}/base-currency")
def set_base_currency(
    account_id: int, body: BaseCurrency, session: DbSession, admin: CurrentAdmin
) -> Account:
    return Account.of(accounts.set_base_currency(session, admin, account_id, body.base_currency))


@router.delete("/{account_id}", status_code=204)
def delete_account(
    account_id: int, session: DbSession, clock: AppClock, admin: CurrentAdmin
) -> None:
    accounts.delete_account(session, admin, clock, account_id)


# --- AI reviewers (REV-13 to REV-15) ----------------------------------------------------


class AiReviewerSettings(BaseModel):
    """The stored key itself is never returned (REV-15)."""

    id: int
    name: str
    description: str | None
    provider: str
    model: str
    api_key_last4: str
    monthly_review_limit: int
    enabled: bool
    updated_at: datetime

    @classmethod
    def of(cls, reviewer: AiReviewer) -> AiReviewerSettings:
        return cls(
            id=reviewer.id,
            name=reviewer.name,
            description=reviewer.description,
            provider=reviewer.provider,
            model=reviewer.model,
            api_key_last4=reviewer.api_key_last4,
            monthly_review_limit=reviewer.monthly_review_limit,
            enabled=reviewer.enabled,
            updated_at=reviewer.updated_at,
        )


class AiReviewerIn(BaseModel):
    name: str
    description: str | None = None
    provider: str
    model: str
    monthly_review_limit: int
    enabled: bool = True
    api_key: str | None = None  # required for a new reviewer; otherwise replaces the key

    def spec(self) -> ai_reviewers.ReviewerSpec:
        return ai_reviewers.ReviewerSpec(
            name=self.name,
            description=self.description,
            provider=self.provider,
            model=self.model,
            monthly_review_limit=self.monthly_review_limit,
            enabled=self.enabled,
            api_key=self.api_key,
        )


class ConnectionTest(BaseModel):
    """The result in English (`message`) and as code with params (NFR-10)."""

    ok: bool
    message: str
    code: str
    params: dict[str, str | int | float]


class AiReviewerList(BaseModel):
    reviewers: list[AiReviewerSettings]
    keys_available: bool  # False: APP_SECRET_KEY is missing, keys cannot be saved


@reviewers_router.get("")
def list_reviewers(session: DbSession, keys: AppKeys, admin: CurrentAdmin) -> AiReviewerList:
    return AiReviewerList(
        reviewers=[AiReviewerSettings.of(r) for r in ai_reviewers.list_reviewers(session, admin)],
        keys_available=keys.available,
    )


@reviewers_router.post("", status_code=201)
def create_reviewer(
    body: AiReviewerIn, session: DbSession, clock: AppClock, keys: AppKeys, admin: CurrentAdmin
) -> AiReviewerSettings:
    reviewer = ai_reviewers.create_reviewer(session, admin, clock, keys, body.spec())
    return AiReviewerSettings.of(reviewer)


@reviewers_router.put("/{reviewer_id}")
def update_reviewer(
    reviewer_id: int,
    body: AiReviewerIn,
    session: DbSession,
    clock: AppClock,
    keys: AppKeys,
    admin: CurrentAdmin,
) -> AiReviewerSettings:
    reviewer = ai_reviewers.update_reviewer(session, admin, clock, keys, reviewer_id, body.spec())
    return AiReviewerSettings.of(reviewer)


@reviewers_router.post("/{reviewer_id}/archive", status_code=204)
def archive_reviewer(
    reviewer_id: int, session: DbSession, clock: AppClock, admin: CurrentAdmin
) -> None:
    """REV-13: archived instead of deleted"""
    ai_reviewers.archive_reviewer(session, admin, clock, reviewer_id)


@reviewers_router.post("/{reviewer_id}/test")
def test_connection(
    reviewer_id: int, session: DbSession, keys: AppKeys, adapters: LlmAdapters, admin: CurrentAdmin
) -> ConnectionTest:
    """REV-14: one request to the provider with the reviewer's settings."""
    result = ai_reviewers.test_connection(session, admin, keys, adapters, reviewer_id)
    return ConnectionTest(
        ok=result.ok,
        message=str(result.message),
        code=result.message.code,
        params=result.message.params,
    )
