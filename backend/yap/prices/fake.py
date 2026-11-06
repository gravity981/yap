"""Stand-in price providers for the end-to-end tests (test strategy §6): fixed listings,
prices and rates, never the internet. Enabled with PRICE_FAKE=1 and refused in production
(see api/app.py)."""

from datetime import date
from decimal import Decimal

import httpx2

from yap.prices.base import (
    Listing,
    Provider,
    ProviderConfig,
    Quote,
    Rate,
    not_found,
)

DAY = date(2026, 11, 2)
CRYPTO = {"BTC": ("bitcoin", Decimal("61234.57")), "ETH": ("ethereum", Decimal("2400.5"))}
# Tickers starting with this have no listing anywhere, to show the manual case
UNKNOWN = "NO"


class FakeAdapter:
    def __init__(self, config: ProviderConfig, client: httpx2.Client) -> None:
        self.provider = config.provider

    def check(self) -> None:
        return None

    def lookup(self, ticker: str) -> list[Listing]:
        ticker = ticker.upper()
        if ticker.startswith(UNKNOWN):
            return []
        if self.provider is Provider.COINGECKO:
            coin = CRYPTO.get(ticker)
            return [Listing(coin[0], "CoinGecko", "USD", ticker.title())] if coin else []
        if ticker in CRYPTO:
            return []
        return [
            Listing(f"{ticker}.SW", "SIX", "CHF", f"{ticker} (Swiss listing)"),
            Listing(f"{ticker}.L", "London", "USD", f"{ticker} (London listing)"),
        ]

    def price(self, symbol: str) -> Quote:
        for coin, price in CRYPTO.values():
            if symbol == coin:
                return Quote(price, "USD", DAY)
        if symbol.endswith(".SW"):
            return Quote(Decimal("100.00"), "CHF", DAY)
        if symbol.endswith(".L"):
            return Quote(Decimal("110.00"), "USD", DAY)
        raise not_found(self.provider, symbol)

    def rates(self, base: str, quotes: list[str]) -> dict[str, Rate]:
        to_chf = {"USD": Decimal("0.8"), "EUR": Decimal("0.93"), "CHF": Decimal(1)}
        if base not in to_chf:
            return {}
        return {q: Rate(to_chf[base] / to_chf[q], DAY) for q in quotes if q in to_chf and q != base}


def fake_adapter(config: ProviderConfig, client: httpx2.Client) -> FakeAdapter:
    return FakeAdapter(config, client)
