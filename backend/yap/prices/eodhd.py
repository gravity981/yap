"""EODHD: stocks, ETFs and funds on many exchanges, end-of-day prices; needs an API key.
Symbols are CODE.EXCHANGE, e.g. VWRL.SW (https://eodhd.com/financial-apis)."""

from datetime import date, timedelta
from typing import Any

import httpx2

from yap.prices.base import (
    Listing,
    Provider,
    ProviderConfig,
    Quote,
    decimal,
    get_json,
    not_found,
    unexpected,
)

BASE = "https://eodhd.com/api"
# Enough days back to reach the last close across weekends and holidays
LOOKBACK = timedelta(days=10)


class EodhdAdapter:
    def __init__(self, config: ProviderConfig, client: httpx2.Client) -> None:
        self.key = config.api_key or ""
        self.client = client

    def _get(self, path: str, symbol: str = "", **params: str) -> Any:
        return get_json(
            self.client,
            Provider.EODHD,
            f"{BASE}/{path}",
            symbol=symbol,
            secret=self.key,
            params={"api_token": self.key, "fmt": "json", **params},
        )

    def check(self) -> None:
        """The account endpoint answers only with a valid key."""
        if not isinstance(self._get("user"), dict):
            raise unexpected(Provider.EODHD)

    def lookup(self, ticker: str) -> list[Listing]:
        found = self._get(f"search/{ticker}", ticker)
        if not isinstance(found, list):
            raise unexpected(Provider.EODHD)
        return [
            Listing(
                symbol=f"{item['Code']}.{item['Exchange']}",
                exchange=str(item["Exchange"]),
                currency=str(item["Currency"]).upper(),
                name=str(item["Name"]),
            )
            for item in found
            if isinstance(item, dict)
            and str(item.get("Code", "")).upper() == ticker.upper()
            and item.get("Currency")
        ]

    def price(self, symbol: str) -> Quote:
        """The latest close; EODHD reports EOD prices without currency, so the caller's
        listing knows it (the currency of a symbol never changes)."""
        since = (date.today() - LOOKBACK).isoformat()
        rows = self._get(f"eod/{symbol}", symbol, order="d", **{"from": since})
        if not isinstance(rows, list):
            raise unexpected(Provider.EODHD)
        if not rows:
            raise not_found(Provider.EODHD, symbol)
        try:
            return Quote(decimal(rows[0]["close"]), None, date.fromisoformat(rows[0]["date"]))
        except KeyError, TypeError, ValueError:
            raise unexpected(Provider.EODHD) from None
