"""CoinGecko: crypto prices. Works without a key with lower limits; a Demo key is sent
when configured. Symbols are CoinGecko's coin IDs, e.g. bitcoin; prices are in USD and
converted into the portfolio currency (PRC-11)."""

from datetime import UTC, datetime
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

BASE = "https://api.coingecko.com/api/v3"
CURRENCY = "USD"
EXCHANGE = "CoinGecko"
MAX_CANDIDATES = 5


class CoinGeckoAdapter:
    def __init__(self, config: ProviderConfig, client: httpx2.Client) -> None:
        self.headers = {"x-cg-demo-api-key": config.api_key} if config.api_key else {}
        self.client = client

    def _get(self, path: str, symbol: str = "", **params: str) -> Any:
        return get_json(
            self.client,
            Provider.COINGECKO,
            f"{BASE}/{path}",
            symbol=symbol,
            secret=self.headers.get("x-cg-demo-api-key", ""),
            params=params,
            headers=self.headers,
        )

    def check(self) -> None:
        self._get("ping")

    def lookup(self, ticker: str) -> list[Listing]:
        """Coins whose symbol is the ticker, e.g. BTC: bitcoin (not wrapped variants
        named differently); by market capitalisation."""
        found = self._get("search", ticker, query=ticker)
        coins = found.get("coins") if isinstance(found, dict) else None
        if not isinstance(coins, list):
            raise unexpected(Provider.COINGECKO)
        return [
            Listing(symbol=str(c["id"]), exchange=EXCHANGE, currency=CURRENCY, name=str(c["name"]))
            for c in coins
            if isinstance(c, dict) and str(c.get("symbol", "")).upper() == ticker.upper()
        ][:MAX_CANDIDATES]

    def price(self, symbol: str) -> Quote:
        data = self._get(
            "simple/price",
            symbol,
            ids=symbol,
            vs_currencies=CURRENCY.lower(),
            include_last_updated_at="true",
        )
        coin = data.get(symbol) if isinstance(data, dict) else None
        if not coin:
            raise not_found(Provider.COINGECKO, symbol)
        try:
            updated = datetime.fromtimestamp(int(coin["last_updated_at"]), UTC)
            return Quote(decimal(coin[CURRENCY.lower()]), CURRENCY, updated.date())
        except KeyError, TypeError, ValueError:
            raise unexpected(Provider.COINGECKO) from None
