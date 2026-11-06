"""Price providers and the exchange rate source (spec section 3.11)."""

import httpx2

from yap.prices.base import (
    AdapterFactory,
    ErrorKind,
    Listing,
    PriceAdapter,
    PriceError,
    Provider,
    ProviderConfig,
    Quote,
    Rate,
    RateAdapter,
)

__all__ = [
    "AdapterFactory",
    "ErrorKind",
    "Listing",
    "PriceAdapter",
    "PriceError",
    "Provider",
    "ProviderConfig",
    "Quote",
    "Rate",
    "RateAdapter",
    "adapter_for",
]


def adapter_for(config: ProviderConfig, client: httpx2.Client) -> PriceAdapter | RateAdapter:
    from yap.prices.coingecko import CoinGeckoAdapter
    from yap.prices.eodhd import EodhdAdapter
    from yap.prices.frankfurter import FrankfurterAdapter
    from yap.prices.yahoo import YahooAdapter

    adapters: dict[Provider, type[PriceAdapter | RateAdapter]] = {
        Provider.EODHD: EodhdAdapter,
        Provider.YAHOO: YahooAdapter,
        Provider.COINGECKO: CoinGeckoAdapter,
        Provider.FRANKFURTER: FrankfurterAdapter,
    }
    return adapters[config.provider](config, client)  # type: ignore[call-arg]
