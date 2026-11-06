"""Price providers through the API: the admin adds, changes, tests and archives them; the
built-in exchange rate source is listed but fixed (PRC-01, PRC-10, PRC-11)."""

import pytest
from fastapi.testclient import TestClient

from tests.fixtures import Accounts

KEY = "eodhd-secret-key-5678"


@pytest.fixture
def admin(accounts_api: Accounts) -> TestClient:
    accounts_api.create("root", admin=True, investor=False)
    return accounts_api.client("root")


def ok(response, status: int = 200):  # type: ignore[no-untyped-def]
    assert response.status_code == status, response.text
    return response.json()


@pytest.mark.req("PRC-01", "PRC-10", "PRC-11", "REV-15")
def test_admin_manages_price_providers(admin: TestClient, accounts_api: Accounts) -> None:
    listed = ok(admin.get("/api/admin/price-providers"))
    assert [(p["provider"], p["name"], p["built_in"]) for p in listed["providers"]] == [
        ("frankfurter", "Frankfurter (ECB)", True)
    ]
    assert [a["provider"] for a in listed["addable"]] == ["eodhd", "yahoo", "coingecko"]
    assert listed["keys_available"] is True
    rates = listed["providers"][0]
    assert ok(admin.post(f"/api/admin/price-providers/{rates['id']}/test"))["ok"] is True
    assert admin.post(f"/api/admin/price-providers/{rates['id']}/archive").status_code == 409

    eodhd = ok(
        admin.post(
            "/api/admin/price-providers",
            json={"provider": "eodhd", "daily_call_limit": 20, "api_key": KEY},
        ),
        201,
    )
    assert (eodhd["api_key_last4"], eodhd["daily_call_limit"], eodhd["key_required"]) == (
        "5678",
        20,
        True,
    )
    url = f"/api/admin/price-providers/{eodhd['id']}"
    changed = ok(admin.put(url, json={"provider": "eodhd", "enabled": False}))
    assert (changed["enabled"], changed["daily_call_limit"]) == (False, None)
    # The stored key is never returned
    assert KEY not in admin.get("/api/admin/price-providers").text
    test = ok(admin.post(f"{url}/test"))
    assert (test["ok"], test["code"], test["params"]) == (
        True,
        "price_connection_ok",
        {"provider": "EODHD"},
    )
    # Calls today are listed (PRC-10); the fake sends no request, counting is tested with
    # the service
    providers = ok(admin.get("/api/admin/price-providers"))["providers"]
    assert {p["provider"]: (p["calls_today"], p["quota_exhausted"]) for p in providers} == {
        "frankfurter": (0, False),
        "eodhd": (0, False),
    }
    duplicate = admin.post("/api/admin/price-providers", json={"provider": "eodhd", "api_key": "x"})
    assert duplicate.status_code == 422
    assert admin.post(f"{url}/archive").status_code == 204
    assert "eodhd" in [
        a["provider"] for a in ok(admin.get("/api/admin/price-providers"))["addable"]
    ]
    # Investors have no access (USR-05)
    accounts_api.create("alice")
    assert accounts_api.client("alice").get("/api/admin/price-providers").status_code == 403


@pytest.mark.req("PRC-07", "PRC-10", "NFR-14")
def test_admin_sets_the_schedule_and_sees_the_last_run(admin: TestClient, app) -> None:  # type: ignore[no-untyped-def]
    from yap.api.app import scheduled_price_update

    update = ok(admin.get("/api/admin/price-update"))
    assert (update["time_of_day"], update["time_zone"], update["interval_hours"]) == (
        "22:00",
        "UTC",
        24,
    )
    assert update["intervals"] == [1, 2, 3, 4, 6, 8, 12, 24] and update["last_run"] is None
    changed = ok(
        admin.put(
            "/api/admin/price-update",
            json={"time_of_day": "18:30", "time_zone": "Europe/Zurich", "interval_hours": 12},
        )
    )
    # The test clock is 15 Jan 2026, 09:00 UTC: next is 18:30 in Zurich, 17:30 UTC
    assert changed["next_run_at"] == "2026-01-15T17:30:00Z"
    bad = admin.put(
        "/api/admin/price-update",
        json={"time_of_day": "7pm", "time_zone": "UTC", "interval_hours": 24},
    )
    assert bad.status_code == 422 and bad.json()["problems"][0]["code"] == "time_of_day_invalid"
    # The scheduler runs the update when it is due
    app.state.clock.advance(hours=5)
    scheduled_price_update(app)  # not due yet
    assert ok(admin.get("/api/admin/price-update"))["last_run"] is None
    app.state.clock.advance(hours=4)
    scheduled_price_update(app)
    last = ok(admin.get("/api/admin/price-update"))["last_run"]
    assert last["trigger"] == "schedule" and last["finished_at"] is not None
    providers = ok(admin.get("/api/admin/price-providers"))["providers"]
    assert (providers[0]["listings_in_use"], providers[0]["last_run"]) == (0, None)
