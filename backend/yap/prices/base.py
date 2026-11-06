"""Provider-neutral interface of the price providers and the exchange rate source (spec
section 3.11, PRC-01). Every adapter talks HTTP through an httpx2 client it is given, so the
service can count its calls (PRC-08) and tests can answer with recorded responses."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

import httpx2

from yap.messages import Message, msg

log = logging.getLogger(__name__)

TIMEOUT = 20.0
MAX_LOG = 4000  # characters of a provider's answer written to the server log
# Yahoo answers only browser-like clients
USER_AGENT = "Mozilla/5.0 (compatible; yap)"


class Provider(StrEnum):
    EODHD = "eodhd"
    YAHOO = "yahoo"
    COINGECKO = "coingecko"
    FRANKFURTER = "frankfurter"  # the built-in exchange rate source (PRC-11)


# Providers the admin can add (PRC-01); the exchange rate source is built in
LISTING_PROVIDERS = (Provider.EODHD, Provider.YAHOO, Provider.COINGECKO)
NAMES = {
    Provider.EODHD: "EODHD",
    Provider.YAHOO: "Yahoo Finance",
    Provider.COINGECKO: "CoinGecko",
    Provider.FRANKFURTER: "Frankfurter (ECB)",
}
# EODHD needs a key; CoinGecko works without one, with lower limits (Demo key optional)
KEY_REQUIRED = {Provider.EODHD}
KEY_POSSIBLE = {Provider.EODHD, Provider.COINGECKO}


class ErrorKind(StrEnum):
    UNREACHABLE = "unreachable"  # network, timeout, server error
    AUTH = "auth"  # key missing or refused
    QUOTA = "quota"  # call limit reached (PRC-08)
    NOT_FOUND = "not_found"  # no such symbol (PRC-09)
    UNEXPECTED = "unexpected"  # an answer that cannot be read


class PriceError(Exception):
    """A provider request failed; the message is safe to show (no key) and has a code
    (NFR-10)."""

    def __init__(self, kind: ErrorKind, message: Message) -> None:
        super().__init__(str(message))
        self.kind = kind
        self.message = message


@dataclass(frozen=True)
class Listing:
    """One asset as one provider offers it (spec 3.1)."""

    symbol: str  # the provider's symbol, e.g. VWRL.SW or bitcoin
    exchange: str
    currency: str  # ISO 4217 code of the quote
    name: str


@dataclass(frozen=True)
class Quote:
    price: Decimal  # in the listing's currency
    currency: str | None  # None: the provider does not say; the listing's currency applies
    date: date  # as reported by the provider


@dataclass(frozen=True)
class Rate:
    rate: Decimal  # 1 base = rate quote
    date: date


class PriceAdapter(Protocol):
    def check(self) -> None:
        """Verifies that the provider answers and accepts the key; raises PriceError."""
        ...

    def lookup(self, ticker: str) -> list[Listing]:
        """The listings of a ticker; empty if there is none (PRC-02). Raises PriceError."""
        ...

    def price(self, symbol: str) -> Quote:
        """The latest price of a listing; PriceError NOT_FOUND if there is none."""
        ...


class RateAdapter(Protocol):
    def check(self) -> None: ...

    def rates(self, base: str, quotes: list[str]) -> dict[str, Rate]:
        """Latest rates from `base` to each quote currency it knows (PRC-11)."""
        ...


@dataclass(frozen=True)
class ProviderConfig:
    provider: Provider
    api_key: str | None = None


AdapterFactory = Callable[[ProviderConfig, httpx2.Client], PriceAdapter | RateAdapter]


def get_json(
    client: httpx2.Client,
    provider: Provider,
    url: str,
    *,
    symbol: str = "",
    secret: str = "",
    **kwargs: Any,
) -> Any:
    """GET with the provider's errors turned into PriceError; `symbol` names what was asked
    for in a "not found", `secret` is removed from the server log. Numbers stay exact
    decimals (NFR-04)."""
    name = NAMES[provider]
    try:
        response = client.get(url, timeout=TIMEOUT, **kwargs)
    except httpx2.TransportError as e:
        detail = type(e).__name__
        log_provider_error(name, url, secret, f"{detail}: {e}")
        raise PriceError(
            ErrorKind.UNREACHABLE,
            msg("price_provider_unreachable", provider=name, detail=detail),
        ) from None
    status = response.status_code
    if status >= 400 and status != 404:  # a 404 is an unknown symbol, not a failure
        log_provider_error(name, url, secret, response.text, status)
    if status in (401, 403):
        raise PriceError(ErrorKind.AUTH, msg("price_provider_auth", provider=name))
    if status in (402, 429):
        raise PriceError(ErrorKind.QUOTA, msg("price_provider_quota", provider=name))
    if status == 404:
        raise not_found(provider, symbol)
    if status >= 400:
        kind = ErrorKind.UNREACHABLE if status >= 500 else ErrorKind.UNEXPECTED
        raise PriceError(kind, msg("price_provider_status", provider=name, status=status))
    try:
        return response.json(parse_float=Decimal)
    except ValueError:
        log_provider_error(name, url, secret, f"unreadable answer: {response.text}")
        raise unexpected(provider) from None


def log_provider_error(
    name: str, url: str, secret: str, text: str, status: int | None = None
) -> None:
    """Logs a failed provider request with the provider's complete answer, e.g. which
    quota was exceeded; the user only sees a short message. The key is removed."""
    if secret:
        text = text.replace(secret, "***")
    if len(text) > MAX_LOG:
        text = text[: MAX_LOG - 1] + "…"
    log.warning(
        "Price request to %s (%s) failed%s: %s",
        name,
        url,
        f" with status {status}" if status is not None else "",
        text,
    )


def unexpected(provider: Provider) -> PriceError:
    return PriceError(
        ErrorKind.UNEXPECTED, msg("price_provider_unexpected", provider=NAMES[provider])
    )


def not_found(provider: Provider, symbol: str) -> PriceError:
    return PriceError(
        ErrorKind.NOT_FOUND, msg("price_not_found", provider=NAMES[provider], symbol=symbol)
    )


def decimal(value: Any) -> Decimal:
    """A JSON number as exact decimal; integers come as int."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return Decimal(value)
    raise TypeError(f"Not a number: {value!r}")
