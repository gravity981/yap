"""Lookup and price sources through the API, with the fake price providers (PRC-02 to
PRC-06, NFR-03)."""

import pytest

from tests.fixtures import Accounts


def ok(response, status: int = 200):  # type: ignore[no-untyped-def]
    assert response.status_code == status, response.text
    return response.json()


@pytest.fixture
def providers(accounts_api: Accounts) -> None:
    accounts_api.create("root", admin=True, investor=False)
    root = accounts_api.client("root")
    for provider in ("yahoo", "coingecko"):
        ok(root.post("/api/admin/price-providers", json={"provider": provider}), 201)


@pytest.mark.req("PRC-02", "PRC-05", "PRC-06", "NFR-03")
def test_investor_looks_up_and_chooses_listings(accounts_api: Accounts, providers: None) -> None:
    accounts_api.create("alice")
    accounts_api.create("bob")
    alice, bob = accounts_api.client("alice"), accounts_api.client("bob")
    found = ok(alice.post("/api/price-sources/lookup", json={"ticker": "xus"}))
    assert (found["ticker"], found["status"], found["source"]) == ("XUS", "found", None)
    assert [(x["symbol"], x["currency"], x["provider_name"]) for x in found["listings"]] == [
        ("XUS.SW", "CHF", "Yahoo Finance"),
        ("XUS.L", "USD", "Yahoo Finance"),
    ]
    chosen = ok(
        alice.put(
            "/api/price-sources/XUS",
            json={
                "kind": "auto",
                "listing_id": found["listings"][1]["id"],
                "name": "US Equity",
                "type": "ETF",
            },
        )
    )
    assert (chosen["kind"], chosen["listing"]["symbol"], chosen["listing"]["price"]) == (
        "auto",
        "XUS.L",
        None,  # prices come with the update (PRC-07)
    )
    again = ok(alice.post("/api/price-sources/lookup", json={"ticker": "XUS"}))
    assert again["source"]["kind"] == "auto"
    assert [s["ticker"] for s in ok(alice.get("/api/price-sources"))] == ["XUS"]
    # Bob's choice is their own; they do not see Alice's
    assert ok(bob.post("/api/price-sources/lookup", json={"ticker": "XUS"}))["source"] is None
    ok(bob.put("/api/price-sources/XUS", json={"kind": "manual"}))
    assert ok(alice.get("/api/price-sources"))[0]["kind"] == "auto"
    # Crypto only at CoinGecko; unknown tickers nowhere
    btc = ok(alice.post("/api/price-sources/lookup", json={"ticker": "BTC"}))
    assert [(x["symbol"], x["provider"]) for x in btc["listings"]] == [("bitcoin", "coingecko")]
    nothing = ok(alice.post("/api/price-sources/lookup", json={"ticker": "NOWHERE", "retry": True}))
    assert (nothing["status"], nothing["listings"], nothing["problems"]) == ("not_found", [], [])
    assert alice.post("/api/price-sources/lookup", json={"ticker": " "}).status_code == 422


@pytest.mark.req("PRC-04")
def test_without_providers_the_lookup_is_unresolved(accounts_api: Accounts) -> None:
    accounts_api.create("alice")
    result = ok(
        accounts_api.client("alice").post("/api/price-sources/lookup", json={"ticker": "X"})
    )
    assert result["status"] == "unresolved"
    assert result["problems"][0]["code"] == "price_no_provider"
