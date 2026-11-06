"""The built-in exchange rate source: ECB reference rates via Frankfurter, no key (PRC-11).
https://frankfurter.dev"""

from datetime import date

import httpx2

from yap.prices.base import (
    Provider,
    ProviderConfig,
    Rate,
    decimal,
    get_json,
    unexpected,
)

LATEST = "https://api.frankfurter.dev/v1/latest"


class FrankfurterAdapter:
    def __init__(self, config: ProviderConfig, client: httpx2.Client) -> None:
        self.client = client

    def check(self) -> None:
        self.rates("EUR", ["USD"])

    def rates(self, base: str, quotes: list[str]) -> dict[str, Rate]:
        data = get_json(
            self.client,
            Provider.FRANKFURTER,
            LATEST,
            symbol=base,
            params={"base": base, "symbols": ",".join(quotes)},
        )
        try:
            day = date.fromisoformat(data["date"])
            return {
                str(currency): Rate(decimal(rate), day) for currency, rate in data["rates"].items()
            }
        except KeyError, TypeError, ValueError, AttributeError:
            raise unexpected(Provider.FRANKFURTER) from None
