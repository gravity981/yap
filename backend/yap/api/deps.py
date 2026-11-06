"""Request dependencies: database session, clock, current user."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Cookie, Depends, Request
from sqlalchemy.orm import Session

from yap.db.models import Investor
from yap.llm.base import AdapterFactory
from yap.messages import msg
from yap.prices import AdapterFactory as PriceAdapterFactory
from yap.services import accounts
from yap.services.common import Clock, ForbiddenError
from yap.services.secrets import KeyBox

SESSION_COOKIE = "itk_session"


def get_session(request: Request) -> Iterator[Session]:
    """One transaction per request: committed on success, rolled back on error."""
    with request.app.state.session_factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def get_clock(request: Request) -> Clock:
    return request.app.state.clock  # type: ignore[no-any-return]


def get_keys(request: Request) -> KeyBox:
    return request.app.state.keys  # type: ignore[no-any-return]


def get_adapters(request: Request) -> AdapterFactory:
    """The LLM adapter factory; tests replace it with a fake (test strategy §6)."""
    return request.app.state.adapters  # type: ignore[no-any-return]


def get_price_adapters(request: Request) -> PriceAdapterFactory:
    """The price provider adapter factory; tests replace it with a fake (test strategy §6)."""
    return request.app.state.price_adapters  # type: ignore[no-any-return]


# scope="function": committed before the response is sent. With the default ("request"),
# FastAPI sends the response first, so a client acting on it at once (e.g. reloading
# after a change) could still read the old state.
DbSession = Annotated[Session, Depends(get_session, scope="function")]
AppClock = Annotated[Clock, Depends(get_clock)]
AppKeys = Annotated[KeyBox, Depends(get_keys)]
LlmAdapters = Annotated[AdapterFactory, Depends(get_adapters)]
PriceAdapters = Annotated[PriceAdapterFactory, Depends(get_price_adapters)]


def session_token(itk_session: Annotated[str | None, Cookie()] = None) -> str:
    if not itk_session:
        raise accounts.AuthenticationError(msg("not_logged_in"))
    return itk_session


Token = Annotated[str, Depends(session_token)]


def logged_in_user(session: DbSession, clock: AppClock, token: Token) -> Investor:
    """Any logged-in account, also one that must still change its password."""
    return accounts.resolve_session(session, clock, token)


AnyUser = Annotated[Investor, Depends(logged_in_user)]


def current_user(user: AnyUser) -> Investor:
    """A logged-in account that has completed a forced password change (USR-02)."""
    if user.must_change_password:
        raise ForbiddenError(msg("password_change_required"))
    return user


CurrentUser = Annotated[Investor, Depends(current_user)]


async def raw_body(request: Request) -> str:
    """Import files are passed as the raw request body, so the importer can report
    JSON syntax errors with line and column (IMP-06)."""
    return (await request.body()).decode("utf-8", errors="replace")


RawBody = Annotated[str, Depends(raw_body)]


def current_admin(user: CurrentUser) -> Investor:
    if not user.is_admin:
        raise ForbiddenError(msg("admins_only"))
    return user


CurrentAdmin = Annotated[Investor, Depends(current_admin)]
