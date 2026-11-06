"""Price provider adapters against recorded HTTP responses (test strategy §6); no provider
is called. The responses in responses/ were recorded from the providers and shortened; the
EODHD search answer follows EODHD's documentation (its demo key cannot search)."""

import json
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx2
import pytest

from yap.prices import ErrorKind, PriceError, Provider, ProviderConfig, adapter_for
from yap.prices.coingecko import CoinGeckoAdapter
from yap.prices.eodhd import EodhdAdapter
from yap.prices.fake import FakeAdapter
from yap.prices.frankfurter import FrankfurterAdapter
from yap.prices.yahoo import YahooAdapter

RESPONSES = Path(__file__).parent / "responses"
KEY = "eod-test-key-1234"


def recorded(name: str) -> Any:
    return json.loads((RESPONSES / name).read_text())


Route = Callable[[httpx2.Request], httpx2.Response]


def client(route: Route, requests: list[httpx2.Request] | None = None) -> httpx2.Client:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if requests is not None:
            requests.append(request)
        return route(request)

    return httpx2.Client(transport=httpx2.MockTransport(handler))


def answer(name: str, status: int = 200) -> Route:
    return lambda _: httpx2.Response(status, json=recorded(name))


def status(code: int) -> Route:
    return lambda _: httpx2.Response(code, text="error")


# --- EODHD --------------------------------------------------------------------------------


@pytest.mark.req("PRC-01", "PRC-02", "NFR-01")
def test_eodhd_looks_up_listings_with_the_key() -> None:
    requests: list[httpx2.Request] = []
    adapter = EodhdAdapter(
        ProviderConfig(Provider.EODHD, KEY), client(answer("eodhd_search_vwrl.json"), requests)
    )
    listings = adapter.lookup("vwrl")
    # VWRA is another fund; only the listings of the ticker itself
    assert [(x.symbol, x.exchange, x.currency) for x in listings] == [
        ("VWRL.SW", "SW", "CHF"),
        ("VWRL.LSE", "LSE", "GBP"),
    ]
    assert requests[0].url.path == "/api/search/vwrl"
    assert requests[0].url.params["api_token"] == KEY
    # NFR-01: the ticker and the key, nothing about the investor
    assert set(requests[0].url.params) == {"api_token", "fmt"}


@pytest.mark.req("PRC-07", "NFR-04")
def test_eodhd_price_is_the_latest_close_as_exact_decimal() -> None:
    adapter = EodhdAdapter(
        ProviderConfig(Provider.EODHD, KEY), client(answer("eodhd_eod_aapl.json"))
    )
    quote = adapter.price("AAPL.US")
    assert quote.price == Decimal("338.32") and isinstance(quote.price, Decimal)
    assert (quote.currency, quote.date) == (None, date(2026, 11, 2))


@pytest.mark.req("PRC-01")
def test_eodhd_check_uses_the_account() -> None:
    requests: list[httpx2.Request] = []
    EodhdAdapter(
        ProviderConfig(Provider.EODHD, KEY), client(answer("eodhd_user.json"), requests)
    ).check()
    assert requests[0].url.path == "/api/user"


# --- Yahoo --------------------------------------------------------------------------------


def yahoo_route(request: httpx2.Request) -> httpx2.Response:
    path = request.url.path
    if path.endswith("/search"):
        return httpx2.Response(200, json=recorded("yahoo_search_vwrl.json"))
    if path.endswith("/VWRL.SW"):
        return httpx2.Response(200, json=recorded("yahoo_chart_vwrl_sw.json"))
    return httpx2.Response(404, json=recorded("yahoo_chart_unknown.json"))


@pytest.mark.req("PRC-02")
def test_yahoo_lookup_takes_the_currency_from_each_listing() -> None:
    requests: list[httpx2.Request] = []
    adapter = YahooAdapter(ProviderConfig(Provider.YAHOO), client(yahoo_route, requests))
    listings = adapter.lookup("VWRL")
    # Only VWRL.SW has prices in this recording; the others are skipped
    assert [(x.symbol, x.exchange, x.currency, x.name) for x in listings] == [
        ("VWRL.SW", "Swiss", "CHF", "Vanguard FTSE All-World UCITS ETF")
    ]
    assert all(r.headers["User-Agent"].startswith("Mozilla/5.0") for r in requests)
    assert len(requests) == 1 + len(
        {
            q["symbol"]
            for q in recorded("yahoo_search_vwrl.json")["quotes"]
            if q["symbol"].startswith("VWRL.")
        }
    )


@pytest.mark.req("PRC-07")
def test_yahoo_price_has_the_trading_day_of_the_exchange() -> None:
    quote = YahooAdapter(ProviderConfig(Provider.YAHOO), client(yahoo_route)).price("VWRL.SW")
    meta = recorded("yahoo_chart_vwrl_sw.json")["chart"]["result"][0]["meta"]
    assert quote.price == Decimal(str(meta["regularMarketPrice"]))
    assert quote.currency == "CHF"
    assert quote.date.year == 2026


@pytest.mark.req("PRC-09")
def test_yahoo_unknown_symbol_is_not_found() -> None:
    with pytest.raises(PriceError) as err:
        YahooAdapter(ProviderConfig(Provider.YAHOO), client(yahoo_route)).price("NOPE.SW")
    assert err.value.kind is ErrorKind.NOT_FOUND
    assert err.value.message.code == "price_not_found"


# --- CoinGecko ----------------------------------------------------------------------------


@pytest.mark.req("PRC-02")
def test_coingecko_lookup_matches_the_symbol_and_sends_an_optional_key() -> None:
    requests: list[httpx2.Request] = []
    with_key = CoinGeckoAdapter(
        ProviderConfig(Provider.COINGECKO, "cg-key"),
        client(answer("coingecko_search_btc.json"), requests),
    )
    assert [(x.symbol, x.currency) for x in with_key.lookup("btc")] == [("bitcoin", "USD")]
    assert requests[0].headers["x-cg-demo-api-key"] == "cg-key"
    without = CoinGeckoAdapter(
        ProviderConfig(Provider.COINGECKO), client(answer("coingecko_search_btc.json"), requests)
    )
    without.lookup("BTC")
    assert "x-cg-demo-api-key" not in requests[1].headers


@pytest.mark.req("PRC-07", "NFR-04")
def test_coingecko_price_in_usd() -> None:
    adapter = CoinGeckoAdapter(
        ProviderConfig(Provider.COINGECKO), client(answer("coingecko_price_bitcoin.json"))
    )
    quote = adapter.price("bitcoin")
    recorded_price = recorded("coingecko_price_bitcoin.json")["bitcoin"]["usd"]
    assert (quote.price, quote.currency) == (Decimal(str(recorded_price)), "USD")
    with pytest.raises(PriceError) as err:
        adapter.price("no-such-coin")
    assert err.value.kind is ErrorKind.NOT_FOUND


# --- Frankfurter --------------------------------------------------------------------------


@pytest.mark.req("PRC-11", "NFR-04")
def test_frankfurter_rates_are_exact() -> None:
    requests: list[httpx2.Request] = []
    adapter = FrankfurterAdapter(
        ProviderConfig(Provider.FRANKFURTER),
        client(answer("frankfurter_latest_usd.json"), requests),
    )
    rates = adapter.rates("USD", ["CHF", "EUR"])
    assert rates["CHF"].rate == Decimal("0.81963")
    assert rates["EUR"].date == date(2026, 11, 2)
    assert dict(requests[0].url.params) == {"base": "USD", "symbols": "CHF,EUR"}


# --- Errors -------------------------------------------------------------------------------


@pytest.mark.req("PRC-01", "PRC-08")
@pytest.mark.parametrize(
    ("code", "kind", "message"),
    [
        (401, ErrorKind.AUTH, "price_provider_auth"),
        (403, ErrorKind.AUTH, "price_provider_auth"),
        (402, ErrorKind.QUOTA, "price_provider_quota"),
        (429, ErrorKind.QUOTA, "price_provider_quota"),
        (503, ErrorKind.UNREACHABLE, "price_provider_status"),
        (400, ErrorKind.UNEXPECTED, "price_provider_status"),
    ],
)
def test_error_statuses(code: int, kind: ErrorKind, message: str) -> None:
    adapter = EodhdAdapter(ProviderConfig(Provider.EODHD, KEY), client(status(code)))
    with pytest.raises(PriceError) as err:
        adapter.check()
    assert (err.value.kind, err.value.message.code) == (kind, message)
    assert KEY not in str(err.value)


@pytest.mark.req("PRC-01")
def test_error_logged_with_answer_without_key(caplog: pytest.LogCaptureFixture) -> None:
    answer = f'{{"error": "daily limit reached for token {KEY}"}}'
    adapter = EodhdAdapter(
        ProviderConfig(Provider.EODHD, KEY), client(lambda _: httpx2.Response(429, text=answer))
    )
    with pytest.raises(PriceError):
        adapter.check()
    [record] = [r for r in caplog.records if r.name == "yap.prices.base"]
    assert record.levelname == "WARNING"
    text = record.getMessage()
    assert "EODHD" in text and "status 429" in text and "daily limit reached" in text
    assert KEY not in text


@pytest.mark.req("PRC-01")
def test_unknown_symbol_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    adapter = EodhdAdapter(ProviderConfig(Provider.EODHD, KEY), client(status(404)))
    with pytest.raises(PriceError):
        adapter.lookup("AAA")
    assert not [r for r in caplog.records if r.name == "yap.prices.base"]


@pytest.mark.req("PRC-04")
def test_network_errors_and_unreadable_answers() -> None:
    def fail(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("down", request=request)

    with pytest.raises(PriceError) as err:
        FrankfurterAdapter(ProviderConfig(Provider.FRANKFURTER), client(fail)).check()
    assert err.value.kind is ErrorKind.UNREACHABLE
    for adapter in (
        EodhdAdapter(
            ProviderConfig(Provider.EODHD, KEY),
            client(lambda _: httpx2.Response(200, text="<html>")),
        ),
        YahooAdapter(
            ProviderConfig(Provider.YAHOO), client(lambda _: httpx2.Response(200, json={"x": 1}))
        ),
        CoinGeckoAdapter(
            ProviderConfig(Provider.COINGECKO), client(lambda _: httpx2.Response(200, json=[]))
        ),
    ):
        with pytest.raises(PriceError) as err:
            adapter.lookup("AAA")
        assert err.value.kind is ErrorKind.UNEXPECTED


@pytest.mark.req("PRC-01")
def test_factory_and_fake() -> None:
    http = client(status(500))
    assert isinstance(adapter_for(ProviderConfig(Provider.YAHOO), http), YahooAdapter)
    assert isinstance(adapter_for(ProviderConfig(Provider.FRANKFURTER), http), FrankfurterAdapter)
    fake = FakeAdapter(ProviderConfig(Provider.YAHOO), http)
    assert [x.symbol for x in fake.lookup("xus")] == ["XUS.SW", "XUS.L"]
    assert fake.lookup("NOWHERE") == [] and fake.lookup("BTC") == []
    assert fake.price("XUS.SW").currency == "CHF"
    btc = FakeAdapter(ProviderConfig(Provider.COINGECKO), http)
    assert btc.lookup("btc")[0].symbol == "bitcoin" and btc.price("bitcoin").currency == "USD"
    assert fake.rates("USD", ["CHF", "XXX"])["CHF"].rate == Decimal("0.8")
