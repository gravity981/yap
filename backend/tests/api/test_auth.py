"""Login, sessions, own password (USR-01, USR-03, USR-07, NFR-02)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.fixtures import PASSWORD, Accounts, FakeClock
from yap.db.models import Investor, UserSession


def login(client: TestClient, username: str, password: str = PASSWORD):  # type: ignore[no-untyped-def]
    return client.post("/api/auth/login", json={"username": username, "password": password})


@pytest.mark.req("USR-01")
def test_login_sets_session_and_me_returns_account(
    client: TestClient, accounts_api: Accounts
) -> None:
    accounts_api.create("alice")
    response = login(client, "alice")
    assert response.status_code == 200
    assert response.json()["username"] == "alice"
    me = client.get("/api/auth/me")
    assert me.json() == {
        "id": me.json()["id"],
        "username": "alice",
        "is_admin": False,
        "is_investor": True,
        "base_currency": "CHF",
        "ai_reviewer_id": None,
        "language": None,
        "time_zone": None,
        "must_change_password": False,
    }


@pytest.mark.req("USR-01")
def test_endpoints_require_a_session(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.set("itk_session", "forged", domain="testserver")
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.req("USR-01")
@pytest.mark.parametrize(
    ("username", "password"), [("alice", "wrong password!"), ("nobody", PASSWORD)]
)
def test_wrong_credentials_give_the_same_answer(
    client: TestClient, accounts_api: Accounts, username: str, password: str
) -> None:
    accounts_api.create("alice")
    response = login(client, username, password)
    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid username or password",
        "code": "login_invalid",
        "params": {},
    }


@pytest.mark.req("USR-01")
def test_logout_ends_the_session(client: TestClient, accounts_api: Accounts) -> None:
    accounts_api.create("alice")
    login(client, "alice")
    token = client.cookies.get("itk_session")
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.set("itk_session", token, domain="testserver")
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.req("NFR-02")
def test_session_cookie_flags_and_hashed_storage(
    client: TestClient, accounts_api: Accounts, session: Session
) -> None:
    accounts_api.create("alice")
    response = login(client, "alice")
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie
    token = client.cookies.get("itk_session")
    stored = session.scalars(select(UserSession.id)).all()
    assert token not in stored and len(stored) == 1


@pytest.mark.req("NFR-02")
def test_cookie_without_secure_flag_for_plain_http(
    db_url: str, clock: FakeClock, session: Session
) -> None:
    """Spec 2.6: in the LAN the app is served over HTTP, where browsers drop Secure cookies."""
    from yap.api.app import create_app
    from yap.api.settings import Settings

    app = create_app(
        Settings(database_url=db_url, migrate_on_startup=False, cookie_secure=False), clock
    )
    accounts = Accounts(session, clock, app)
    accounts.create("alice")
    with TestClient(app, base_url="http://server.lan") as plain:
        response = login(plain, "alice")
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie
        assert "secure" not in cookie
        assert plain.get("/api/auth/me").status_code == 200  # the browser sends it back
        logout = plain.post("/api/auth/logout").headers["set-cookie"].lower()
        assert "secure" not in logout


@pytest.mark.req("NFR-02")
def test_passwords_are_hashed_with_argon2(accounts_api: Accounts, session: Session) -> None:
    accounts_api.create("alice")
    hashed = session.scalar(select(Investor.password_hash).where(Investor.username == "alice"))
    assert hashed is not None and hashed.startswith("$argon2id$")


@pytest.mark.req("NFR-02")
def test_five_failures_lock_the_username_for_15_minutes(
    client: TestClient, accounts_api: Accounts
) -> None:
    accounts_api.create("alice")
    for _ in range(5):
        assert login(client, "alice", "wrong password!").status_code == 401
    locked = login(client, "alice")
    assert locked.status_code == 429
    assert locked.headers["retry-after"] == "900"
    accounts_api.clock.advance(minutes=14, seconds=59)
    assert login(client, "alice").status_code == 429
    accounts_api.clock.advance(seconds=1)
    assert login(client, "alice").status_code == 200


@pytest.mark.req("NFR-02")
def test_failures_spread_over_more_than_15_minutes_do_not_lock(
    client: TestClient, accounts_api: Accounts
) -> None:
    accounts_api.create("alice")
    for _ in range(5):
        login(client, "alice", "wrong password!")
        accounts_api.clock.advance(minutes=4)
    assert login(client, "alice").status_code == 200


@pytest.mark.req("USR-07")
def test_session_ends_after_8_hours_without_activity(
    client: TestClient, accounts_api: Accounts
) -> None:
    accounts_api.create("alice")
    login(client, "alice")
    accounts_api.clock.advance(hours=7, minutes=59)
    assert client.get("/api/auth/me").status_code == 200  # activity resets the idle timer
    accounts_api.clock.advance(hours=7, minutes=59)
    assert client.get("/api/auth/me").status_code == 200
    accounts_api.clock.advance(hours=8)
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.req("USR-07")
def test_session_ends_after_30_days(client: TestClient, accounts_api: Accounts) -> None:
    accounts_api.create("alice")
    login(client, "alice")
    for _ in range(4 * 30 - 1):  # active every 6 hours
        accounts_api.clock.advance(hours=6)
        assert client.get("/api/auth/me").status_code == 200
    accounts_api.clock.advance(hours=6)
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.req("USR-03", "USR-07")
def test_change_own_password(client: TestClient, accounts_api: Accounts) -> None:
    accounts_api.create("alice")
    login(client, "alice")
    short = client.post(
        "/api/auth/password", json={"current_password": PASSWORD, "new_password": "short"}
    )
    assert short.status_code == 422
    assert short.json()["problems"][0]["path"] == "new_password"
    wrong = client.post(
        "/api/auth/password",
        json={"current_password": "not the password", "new_password": "a new long password"},
    )
    assert wrong.status_code == 422
    same = client.post(
        "/api/auth/password", json={"current_password": PASSWORD, "new_password": PASSWORD}
    )
    assert same.status_code == 422
    ok = client.post(
        "/api/auth/password",
        json={"current_password": PASSWORD, "new_password": "a new long password"},
    )
    assert ok.status_code == 204
    client.post("/api/auth/logout")
    assert login(client, "alice").status_code == 401
    assert login(client, "alice", "a new long password").status_code == 200


@pytest.mark.req("USR-10")
def test_each_account_sets_its_own_language(accounts_api: Accounts) -> None:
    accounts_api.create("alice")
    accounts_api.create("root", admin=True, investor=False)
    alice = accounts_api.client("alice")
    assert alice.get("/api/auth/me").json()["language"] is None  # follows the browser
    response = alice.put("/api/auth/language", json={"language": "de"})
    assert response.status_code == 200 and response.json()["language"] == "de"
    assert alice.get("/api/auth/me").json()["language"] == "de"
    # Stored on the account, so it applies to every device; others keep theirs
    assert accounts_api.client("alice").get("/api/auth/me").json()["language"] == "de"
    root = accounts_api.client("root")
    assert root.get("/api/auth/me").json()["language"] is None
    assert root.put("/api/auth/language", json={"language": "en"}).json()["language"] == "en"
    invalid = alice.put("/api/auth/language", json={"language": "fr"})
    assert invalid.status_code == 422 and invalid.json()["problems"][0]["path"] == "language"
    assert alice.put("/api/auth/language", json={"language": None}).json()["language"] is None


@pytest.mark.req("USR-11")
def test_each_account_sets_its_own_time_zone(accounts_api: Accounts) -> None:
    accounts_api.create("alice")
    accounts_api.create("root", admin=True, investor=False)
    alice = accounts_api.client("alice")
    assert alice.get("/api/auth/me").json()["time_zone"] is None  # follows the browser
    response = alice.put("/api/auth/time-zone", json={"time_zone": "Europe/Zurich"})
    assert response.status_code == 200 and response.json()["time_zone"] == "Europe/Zurich"
    assert accounts_api.client("alice").get("/api/auth/me").json()["time_zone"] == "Europe/Zurich"
    root = accounts_api.client("root")  # also for admin-only accounts
    assert root.put("/api/auth/time-zone", json={"time_zone": "UTC"}).json()["time_zone"] == "UTC"
    invalid = alice.put("/api/auth/time-zone", json={"time_zone": "Mars/Olympus"})
    assert invalid.status_code == 422
    assert invalid.json()["problems"][0] == {
        "path": "time_zone",
        "message": "Unknown time zone Mars/Olympus",
        "code": "time_zone_unknown",
        "params": {"time_zone": "Mars/Olympus"},
    }
    assert alice.put("/api/auth/time-zone", json={"time_zone": None}).json()["time_zone"] is None
