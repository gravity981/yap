"""Login, sessions and account management (USR-01 to USR-07, USR-09, NFR-02)."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import available_timezones

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, exists, func, select
from sqlalchemy.orm import Session

from yap.db.models import (
    Investor,
    LoginFailure,
    Policy,
    Portfolio,
    UserSession,
)
from yap.messages import msg
from yap.services.common import (
    Clock,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceError,
    ValidationError,
    check_currency,
    require_text,
)

MIN_PASSWORD_LENGTH = 12
SESSION_LIFETIME = timedelta(days=30)
SESSION_IDLE_TIMEOUT = timedelta(hours=8)
MAX_FAILURES = 5
FAILURE_WINDOW = timedelta(minutes=15)
LOCK_DURATION = timedelta(minutes=15)
LANGUAGES = ("en", "de")  # USR-10, NFR-10

_hasher = PasswordHasher()


class AuthenticationError(ServiceError):
    """Wrong credentials or no valid session; deliberately not more specific."""


@dataclass
class LockedError(ServiceError):
    until: datetime

    def __post_init__(self) -> None:
        super().__init__(msg("login_locked", until=self.until.isoformat()))


# --- Passwords ----------------------------------------------------------------


def _check_password_policy(password: str, path: str = "password") -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError.single(msg("password_too_short", min=MIN_PASSWORD_LENGTH), path)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def _verify(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerificationError, InvalidHashError:
        return False


# --- Sessions -----------------------------------------------------------------


def _token_id(token: str) -> str:
    """Only a hash of the session token is stored, so a database copy holds no sessions."""
    return hashlib.sha256(token.encode()).hexdigest()


def _locked_until(session: Session, username: str, now: datetime) -> datetime | None:
    """NFR-02: 5 failures within 15 minutes lock the username for 15 minutes."""
    failures = list(
        session.scalars(
            select(LoginFailure.failed_at)
            .where(LoginFailure.username == username)
            .where(LoginFailure.failed_at > now - FAILURE_WINDOW - LOCK_DURATION)
            .order_by(LoginFailure.failed_at)
        )
    )
    for i in range(MAX_FAILURES - 1, len(failures)):
        if failures[i] - failures[i - MAX_FAILURES + 1] <= FAILURE_WINDOW:
            until = failures[i] + LOCK_DURATION
            if until > now:
                return until
    return None


def login(session: Session, clock: Clock, username: str, password: str) -> tuple[str, Investor]:
    """Returns a new session token and the investor (USR-01)."""
    now = clock.now()
    username = username.strip()
    locked = _locked_until(session, username, now)
    if locked is not None:
        raise LockedError(locked)
    investor = session.scalar(select(Investor).where(Investor.username == username))
    if investor is None or not investor.active or not _verify(investor.password_hash, password):
        session.add(LoginFailure(username=username, failed_at=now))
        session.flush()
        raise AuthenticationError(msg("login_invalid"))
    if _hasher.check_needs_rehash(investor.password_hash):
        investor.password_hash = hash_password(password)
    token = secrets.token_urlsafe(32)
    session.add(
        UserSession(
            id=_token_id(token),
            investor_id=investor.id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + SESSION_LIFETIME,
        )
    )
    session.flush()
    return token, investor


def resolve_session(session: Session, clock: Clock, token: str) -> Investor:
    """USR-07: valid for 30 days, or until 8 hours without activity."""
    now = clock.now()
    user_session = session.get(UserSession, _token_id(token))
    if user_session is None:
        raise AuthenticationError(msg("not_logged_in"))
    investor = session.get(Investor, user_session.investor_id)
    if (
        investor is None
        or not investor.active
        or now >= user_session.expires_at
        or now - user_session.last_seen_at >= SESSION_IDLE_TIMEOUT
    ):
        session.delete(user_session)
        session.flush()
        raise AuthenticationError(msg("session_expired"))
    user_session.last_seen_at = now
    return investor


def logout(session: Session, token: str) -> None:
    session.execute(delete(UserSession).where(UserSession.id == _token_id(token)))


def _end_sessions(session: Session, investor: Investor) -> None:
    session.execute(delete(UserSession).where(UserSession.investor_id == investor.id))


def change_password(
    session: Session, investor: Investor, current_password: str, new_password: str
) -> None:
    """USR-03; also completes a forced change after a reset."""
    if not _verify(investor.password_hash, current_password):
        raise ValidationError.single(msg("password_wrong"), "current_password")
    _check_password_policy(new_password, "new_password")
    if new_password == current_password:
        raise ValidationError.single(msg("password_unchanged"), "new_password")
    investor.password_hash = hash_password(new_password)
    investor.must_change_password = False


def set_language(investor: Investor, language: str | None) -> None:
    """USR-10: the own UI language; None follows the browser."""
    if language is not None and language not in LANGUAGES:
        raise ValidationError.single(
            msg("language_unknown", language=language, languages=", ".join(LANGUAGES)), "language"
        )
    investor.language = language


def set_time_zone(investor: Investor, time_zone: str | None) -> None:
    """USR-11: the own time zone (IANA name); None follows the browser."""
    if time_zone is not None and time_zone not in available_timezones():
        raise ValidationError.single(msg("time_zone_unknown", time_zone=time_zone), "time_zone")
    investor.time_zone = time_zone


# --- Account management (admin) -----------------------------------------------


def require_admin(actor: Investor) -> None:
    if not actor.is_admin or not actor.active:
        raise ForbiddenError(msg("admins_only"))


def _check_currency(currency: str) -> str:
    return check_currency(currency, "base_currency")


def create_account(
    session: Session,
    clock: Clock,
    *,
    username: str,
    password: str,
    admin: bool = False,
    investor: bool = True,
    base_currency: str | None = None,
    must_change_password: bool = True,
) -> Investor:
    """Creates an account with one or both roles (USR-09). The admin UI passes a
    temporary password (USR-02); the CLI creates the first admin without a forced
    change."""
    username = require_text(username, "username", msg("username_empty"))
    if username.startswith("deleted-"):
        raise ValidationError.single(msg("username_reserved"), "username")
    if session.scalar(select(exists().where(Investor.username == username))):
        raise ConflictError(msg("username_taken", username=username))
    if not admin and not investor:
        raise ValidationError.single(msg("roles_required"), "roles")
    # Without the investor role there is no investment data (USR-05)
    base_currency = _investor_currency(base_currency) if investor else None
    _check_password_policy(password)
    account = Investor(
        username=username,
        password_hash=hash_password(password),
        is_admin=admin,
        is_investor=investor,
        base_currency=base_currency,
        active=True,
        must_change_password=must_change_password,
        created_at=clock.now(),
    )
    session.add(account)
    session.flush()
    return account


def _investor_currency(base_currency: str | None) -> str:
    if base_currency is None or not base_currency.strip():
        raise ValidationError.single(msg("base_currency_required"), "base_currency")
    return _check_currency(base_currency)


def admin_create_account(
    session: Session,
    actor: Investor,
    clock: Clock,
    *,
    username: str,
    temporary_password: str,
    admin: bool = False,
    investor: bool = True,
    base_currency: str | None = None,
) -> Investor:
    """USR-02, USR-06, USR-09: only admins create accounts. Investors choose their AI
    reviewer themselves (USR-08)."""
    require_admin(actor)
    return create_account(
        session,
        clock,
        username=username,
        password=temporary_password,
        admin=admin,
        investor=investor,
        base_currency=base_currency,
    )


def _owns_investment_data(session: Session, account: Investor) -> bool:
    return any(
        session.scalar(select(exists().where(model.owner_id == account.id)))
        for model in (Policy, Portfolio)
    )


def _other_active_admins(session: Session, account: Investor) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(Investor)
            .where(Investor.is_admin, Investor.active, Investor.id != account.id)
        )
        or 0
    )


def set_roles(
    session: Session,
    actor: Investor,
    account_id: int,
    *,
    admin: bool,
    investor: bool,
    base_currency: str | None = None,
) -> Investor:
    """USR-09: the investor role needs a base currency and can only be removed while the
    account owns no investment data; the last active admin keeps the admin role."""
    require_admin(actor)
    account = get_account(session, account_id)
    if not admin and not investor:
        raise ValidationError.single(msg("roles_required"), "roles")
    removes_admin = account.is_admin and not admin and account.active
    if removes_admin and not _other_active_admins(session, account):
        raise ConflictError(msg("last_admin_keeps_role"))
    if investor and not account.is_investor:
        account.base_currency = _investor_currency(base_currency)
    elif not investor and account.is_investor:
        if _owns_investment_data(session, account):
            raise ConflictError(msg("investor_role_in_use"))
        account.base_currency = None
        account.ai_reviewer_id = None
    account.is_admin = admin
    account.is_investor = investor
    session.flush()
    return account


def get_account(session: Session, account_id: int) -> Investor:
    account = session.get(Investor, account_id)
    if account is None or account.deleted_at is not None:
        raise NotFoundError(msg("account_not_found", id=account_id))
    return account


def list_accounts(session: Session, actor: Investor) -> list[Investor]:
    require_admin(actor)
    return list(
        session.scalars(
            select(Investor).where(Investor.deleted_at.is_(None)).order_by(Investor.username)
        )
    )


def _not_self(actor: Investor, account: Investor) -> None:
    if actor.id == account.id:
        raise ConflictError(msg("own_account_status"))


def deactivate(session: Session, actor: Investor, account_id: int) -> Investor:
    require_admin(actor)
    account = get_account(session, account_id)
    _not_self(actor, account)
    account.active = False
    _end_sessions(session, account)
    return account


def reactivate(session: Session, actor: Investor, account_id: int) -> Investor:
    require_admin(actor)
    account = get_account(session, account_id)
    account.active = True
    return account


def delete_account(session: Session, actor: Investor, clock: Clock, account_id: int) -> None:
    """USR-02: irreversible; deactivated and anonymised, history stays unreachable."""
    require_admin(actor)
    account = get_account(session, account_id)
    _not_self(actor, account)
    _end_sessions(session, account)
    account.active = False
    account.username = f"deleted-{account.id}"
    account.password_hash = ""
    account.deleted_at = clock.now()


def reset_password(
    session: Session, actor: Investor, account_id: int, temporary_password: str
) -> Investor:
    """USR-02: temporary password, forced change at next login, all sessions end."""
    require_admin(actor)
    account = get_account(session, account_id)
    _check_password_policy(temporary_password, "temporary_password")
    account.password_hash = hash_password(temporary_password)
    account.must_change_password = True
    _end_sessions(session, account)
    session.execute(delete(LoginFailure).where(LoginFailure.username == account.username))
    return account


def set_base_currency(
    session: Session, actor: Investor, account_id: int, base_currency: str
) -> Investor:
    """USR-06: changeable at any time; it only presets the currency of new portfolios."""
    require_admin(actor)
    account = get_account(session, account_id)
    if not account.is_investor:
        raise ConflictError(msg("base_currency_investors_only"))
    account.base_currency = _check_currency(base_currency)
    return account
