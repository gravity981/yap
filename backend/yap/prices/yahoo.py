"""Yahoo Finance: stocks, ETFs, funds and crypto on many exchanges, without a key. An
unofficial interface without published limits; it may stop working (PRC-01). Symbols are
Yahoo's, e.g. VWRL.SW or BTC-USD."""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2

from yap.prices.base import (
    USER_AGENT,
    ErrorKind,
    Listing,
    PriceError,
    Provider,
    ProviderConfig,
    Quote,
    decimal,
    get_json,
    not_found,
    unexpected,
)

SEARCH = "https://query2.finance.yahoo.com/v1/finance/search"
CHART = "https://query2.finance.yahoo.com/v8/finance/chart"
TYPES = {"EQUITY", "ETF", "MUTUALFUND", "CRYPTOCURRENCY"}
# The search gives no currency; each candidate's chart does, one call each
MAX_CANDIDATES = 8


class YahooAdapter:
    def __init__(self, config: ProviderConfig, client: httpx2.Client) -> None:
        self.client = client

    def _get(self, url: str, symbol: str = "", **params: str) -> Any:
        return get_json(
            self.client,
            Provider.YAHOO,
            url,
            symbol=symbol,
            params=params,
            headers={"User-Agent": USER_AGENT},
        )

    def _meta(self, symbol: str) -> dict[str, Any]:
        data = self._get(f"{CHART}/{symbol}", symbol, range="5d", interval="1d")
        try:
            meta = data["chart"]["result"][0]["meta"]
        except KeyError, IndexError, TypeError:
            raise not_found(Provider.YAHOO, symbol) from None
        if not isinstance(meta, dict):
            raise unexpected(Provider.YAHOO)
        return meta

    def check(self) -> None:
        self._get(SEARCH, q="AAPL", quotesCount="1", newsCount="0")

    def lookup(self, ticker: str) -> list[Listing]:
        found = self._get(SEARCH, ticker, q=ticker, quotesCount="20", newsCount="0")
        quotes = found.get("quotes") if isinstance(found, dict) else None
        if not isinstance(quotes, list):
            raise unexpected(Provider.YAHOO)
        wanted = ticker.upper()
        symbols = [
            str(q["symbol"])
            for q in quotes
            if isinstance(q, dict)
            and q.get("quoteType") in TYPES
            and _matches(str(q.get("symbol", "")).upper(), wanted)
        ][:MAX_CANDIDATES]
        listings = []
        for symbol in symbols:
            try:
                meta = self._meta(symbol)
            except PriceError as e:
                if e.kind is ErrorKind.NOT_FOUND:
                    continue  # listed in the search, but without prices
                raise
            if meta.get("currency"):
                listings.append(
                    Listing(
                        symbol=symbol,
                        exchange=str(meta.get("fullExchangeName") or meta.get("exchangeName")),
                        currency=str(meta["currency"]).upper(),
                        name=str(meta.get("longName") or meta.get("shortName") or symbol),
                    )
                )
        return listings

    def price(self, symbol: str) -> Quote:
        meta = self._meta(symbol)
        try:
            price = decimal(meta["regularMarketPrice"])
            # The trading day at the exchange, not in UTC
            offset = timedelta(seconds=int(meta.get("gmtoffset") or 0))
            moment = datetime.fromtimestamp(int(meta["regularMarketTime"]), UTC) + offset
            return Quote(price, str(meta["currency"]).upper(), moment.date())
        except KeyError, TypeError, ValueError:
            raise unexpected(Provider.YAHOO) from None


def _matches(symbol: str, ticker: str) -> bool:
    """VWRL matches VWRL, VWRL.SW and VWRL.L; BTC matches BTC-USD, BTC-EUR."""
    return symbol == ticker or symbol.startswith((f"{ticker}.", f"{ticker}-"))
