"""Errors, clock and access helpers shared by all services."""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.orm import Session

from yap.db.models import Base, Investor
from yap.messages import Message, msg


class ServiceError(Exception):
    """Base class for errors the API turns into 4xx responses. The message has a code, so
    the frontend can show it in the user's language (NFR-10)."""

    def __init__(self, message: Message) -> None:
        super().__init__(str(message))
        self.message = message


class NotFoundError(ServiceError):
    """Missing, or belongs to someone else (not revealed, test strategy §7)."""


class ForbiddenError(ServiceError):
    pass


class ConflictError(ServiceError):
    pass


@dataclass
class ValidationError(ServiceError):
    """One or more validation problems; `path` is a JSON-path-like location."""

    problems: list[tuple[str, Message]] = field(default_factory=list)  # (path, message)

    def __post_init__(self) -> None:
        text = "; ".join(f"{p}: {m}" if p else str(m) for p, m in self.problems)
        Exception.__init__(self, text)
        # The first problem stands for the whole error, e.g. in a single-field form
        self.message = self.problems[0][1] if self.problems else msg("invalid_input")

    @classmethod
    def single(cls, message: Message, path: str = "") -> ValidationError:
        return cls([(path, message)])


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def require_investor(actor: Investor) -> None:
    """Investment data belongs to the investor role; the admin role gives no access to it
    (USR-05)."""
    if not actor.is_investor or not actor.active:
        raise ForbiddenError(msg("investors_only"))


def get_owned[ModelT: Base](
    session: Session, model: type[ModelT], obj_id: int, actor: Investor
) -> ModelT:
    """Loads an object owned by `actor`; anything else is reported as not found."""
    require_investor(actor)
    obj = session.get(model, obj_id)
    if obj is None or getattr(obj, "owner_id", None) != actor.id:
        raise NotFoundError(msg(f"{model.__tablename__}_not_found", id=obj_id))
    return obj


CURRENCY = re.compile(r"^[A-Z]{3}$")


def check_currency(currency: str, path: str) -> str:
    """An ISO 4217 code, trimmed and in uppercase (USR-06, PTF-03)."""
    currency = currency.strip().upper()
    if not CURRENCY.match(currency):
        raise ValidationError.single(msg("currency_invalid"), path)
    return currency


def require_text(value: str | None, path: str, message: Message) -> str:
    if value is None or not value.strip():
        raise ValidationError.single(message, path)
    return value.strip()
