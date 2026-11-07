"""Login, logout, own account (USR-01, USR-03, USR-07)."""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from yap.api.deps import SESSION_COOKIE, AnyUser, AppClock, DbSession, Token
from yap.db.models import Investor
from yap.services import accounts

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class Me(BaseModel):
    id: int
    username: str
    is_admin: bool  # USR-09: one or both roles
    is_investor: bool
    base_currency: str | None
    ai_reviewer_id: int | None  # USR-08
    manual_review_default: bool  # USR-08: the default method is manual (REV-18)
    language: str | None  # USR-10: en | de; null = the browser's
    time_zone: str | None  # USR-11: IANA name; null = the browser's
    must_change_password: bool

    @classmethod
    def of(cls, investor: Investor) -> Me:
        return cls(
            id=investor.id,
            username=investor.username,
            is_admin=investor.is_admin,
            is_investor=investor.is_investor,
            base_currency=investor.base_currency,
            ai_reviewer_id=investor.ai_reviewer_id,
            manual_review_default=investor.manual_review_default,
            language=investor.language,
            time_zone=investor.time_zone,
            must_change_password=investor.must_change_password,
        )


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class LanguageChoice(BaseModel):
    language: str | None  # en | de; null = follow the browser


class TimeZoneChoice(BaseModel):
    time_zone: str | None  # IANA name, e.g. Europe/Zurich; null = follow the browser


def _secure(request: Request) -> bool:
    """Secure unless the app is served over plain HTTP (COOKIE_SECURE=false, spec 2.6)."""
    return bool(request.app.state.settings.cookie_secure)


@router.post("/login")
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: DbSession,
    clock: AppClock,
) -> Me:
    try:
        token, investor = accounts.login(session, clock, body.username, body.password)
    except accounts.AuthenticationError:
        session.commit()  # keep the recorded failure for the rate limit (NFR-02)
        raise
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(accounts.SESSION_LIFETIME.total_seconds()),
        httponly=True,
        secure=_secure(request),
        samesite="strict",
        path="/",
    )
    return Me.of(investor)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, session: DbSession, token: Token) -> None:
    accounts.logout(session, token)
    response.delete_cookie(
        SESSION_COOKIE, path="/", secure=_secure(request), httponly=True, samesite="strict"
    )


@router.get("/me")
def me(user: AnyUser) -> Me:
    return Me.of(user)


@router.post("/password", status_code=204)
def change_password(body: PasswordChange, session: DbSession, user: AnyUser) -> None:
    accounts.change_password(session, user, body.current_password, body.new_password)


@router.put("/language")
def set_language(body: LanguageChoice, user: AnyUser) -> Me:
    """USR-10: also for admin-only accounts and before a temporary password is changed."""
    accounts.set_language(user, body.language)
    return Me.of(user)


@router.put("/time-zone")
def set_time_zone(body: TimeZoneChoice, user: AnyUser) -> Me:
    """USR-11: like the language, for every account."""
    accounts.set_time_zone(user, body.time_zone)
    return Me.of(user)
