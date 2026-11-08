"""Account management (USR-02, USR-05, USR-06)."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.fixtures import PASSWORD, Accounts, Factory
from yap.services import snapshots
from yap.services.snapshots import ValueSpec

TEMP = "temporary password 1"


@pytest.fixture
def admin(accounts_api: Accounts) -> TestClient:
    accounts_api.create("root", admin=True, investor=False)
    return accounts_api.client("root")


def create(admin: TestClient, username: str = "alice", currency: str = "chf"):  # type: ignore[no-untyped-def]
    return admin.post(
        "/api/admin/accounts",
        json={"username": username, "temporary_password": TEMP, "base_currency": currency},
    )


@pytest.mark.req("USR-02", "USR-06")
def test_admin_creates_investor_with_temporary_password(
    admin: TestClient, accounts_api: Accounts
) -> None:
    response = create(admin)
    assert response.status_code == 201
    assert response.json()["base_currency"] == "CHF"
    assert response.json()["must_change_password"] is True
    alice = accounts_api.client("alice", TEMP)
    assert alice.get("/api/auth/me").json()["must_change_password"] is True
    assert alice.get("/api/admin/accounts").status_code == 403  # blocked until changed
    assert (
        alice.post(
            "/api/auth/password",
            json={"current_password": TEMP, "new_password": "my own long password"},
        ).status_code
        == 204
    )
    assert alice.get("/api/auth/me").json()["must_change_password"] is False


@pytest.mark.req("USR-02")
@pytest.mark.parametrize(
    ("body", "status", "path"),
    [
        ({"username": "x", "temporary_password": "short", "base_currency": "CHF"}, 422, "password"),
        (
            {"username": "x", "temporary_password": TEMP, "base_currency": "Swiss"},
            422,
            "base_currency",
        ),
        (
            {"username": "deleted-1", "temporary_password": TEMP, "base_currency": "CHF"},
            422,
            "username",
        ),
        ({"username": " ", "temporary_password": TEMP, "base_currency": "CHF"}, 422, "username"),
    ],
)
def test_invalid_new_accounts(
    admin: TestClient, body: dict[str, str], status: int, path: str
) -> None:
    response = admin.post("/api/admin/accounts", json=body)
    assert response.status_code == status
    assert response.json()["problems"][0]["path"] == path


@pytest.mark.req("USR-02")
def test_usernames_are_unique(admin: TestClient) -> None:
    create(admin)
    assert create(admin).status_code == 409


@pytest.mark.req("USR-02")
def test_no_self_registration_and_only_admins_manage(accounts_api: Accounts) -> None:
    accounts_api.create("alice")
    alice = accounts_api.client("alice")
    assert create(alice).status_code == 403
    assert alice.get("/api/admin/accounts").status_code == 403


@pytest.mark.req("USR-02")
def test_deactivate_ends_sessions_and_reactivate(admin: TestClient, accounts_api: Accounts) -> None:
    alice_id = accounts_api.create("alice").id
    alice = accounts_api.client("alice")
    assert admin.post(f"/api/admin/accounts/{alice_id}/deactivate").json()["active"] is False
    assert alice.get("/api/auth/me").status_code == 401
    assert (
        alice.post("/api/auth/login", json={"username": "alice", "password": PASSWORD}).status_code
        == 401
    )
    admin.post(f"/api/admin/accounts/{alice_id}/reactivate")
    assert accounts_api.client("alice").get("/api/auth/me").status_code == 200


@pytest.mark.req("USR-02")
def test_delete_anonymises_and_is_irreversible(
    admin: TestClient, accounts_api: Accounts, session: Session
) -> None:
    alice_id = accounts_api.create("alice").id
    assert admin.delete(f"/api/admin/accounts/{alice_id}").status_code == 204
    assert [a["username"] for a in admin.get("/api/admin/accounts").json()] == ["root"]
    assert admin.post(f"/api/admin/accounts/{alice_id}/reactivate").status_code == 404
    session.expire_all()
    from yap.db.models import Investor

    deleted = session.get(Investor, alice_id)
    assert deleted is not None
    assert (deleted.username, deleted.password_hash, deleted.active) == (
        f"deleted-{alice_id}",
        "",
        False,
    )
    assert create(admin, "alice").status_code == 201  # the name is free again


@pytest.mark.req("USR-02")
def test_admin_cannot_lock_out_itself(admin: TestClient) -> None:
    root_id = admin.get("/api/auth/me").json()["id"]
    assert admin.post(f"/api/admin/accounts/{root_id}/deactivate").status_code == 409
    assert admin.delete(f"/api/admin/accounts/{root_id}").status_code == 409


@pytest.mark.req("USR-02", "NFR-02")
def test_reset_password_ends_sessions_and_unlocks(
    admin: TestClient, accounts_api: Accounts
) -> None:
    alice_id = accounts_api.create("alice").id
    alice = accounts_api.client("alice")
    for _ in range(5):
        alice.post("/api/auth/login", json={"username": "alice", "password": "wrong password!"})
    response = admin.post(
        f"/api/admin/accounts/{alice_id}/reset-password", json={"temporary_password": TEMP}
    )
    assert response.json()["must_change_password"] is True
    assert alice.get("/api/auth/me").status_code == 401
    assert accounts_api.client("alice", TEMP).get("/api/auth/me").status_code == 200


@pytest.mark.req("USR-06", "PTF-03")
def test_base_currency_changes_at_any_time_and_only_presets_new_portfolios(
    admin: TestClient, accounts_api: Accounts, factory: Factory, session: Session
) -> None:
    alice = accounts_api.create("alice")
    url = f"/api/admin/accounts/{alice.id}/base-currency"
    assert admin.put(url, json={"base_currency": "eur"}).json()["base_currency"] == "EUR"
    session.refresh(alice)
    portfolio = factory.portfolio(alice)
    snapshots.create_snapshot(
        session, alice, factory.clock, portfolio.id, [ValueSpec("AAA", Decimal(1))]
    )
    session.commit()
    assert admin.put(url, json={"base_currency": "USD"}).json()["base_currency"] == "USD"
    session.refresh(portfolio)
    assert portfolio.currency == "EUR"  # existing portfolios keep their currency
    root_id = admin.get("/api/auth/me").json()["id"]
    assert (
        admin.put(
            f"/api/admin/accounts/{root_id}/base-currency", json={"base_currency": "USD"}
        ).status_code
        == 409
    )


@pytest.mark.req("USR-05")
def test_admin_accounts_have_no_currency(admin: TestClient) -> None:
    assert admin.get("/api/auth/me").json()["base_currency"] is None


def roles(admin: TestClient, account_id: int, **body: object):  # type: ignore[no-untyped-def]
    return admin.put(f"/api/admin/accounts/{account_id}/roles", json=body)


@pytest.mark.req("USR-09")
@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"is_admin": True, "base_currency": "chf"}, (True, True, "CHF")),
        ({"is_admin": True, "is_investor": False}, (True, False, None)),
        ({"base_currency": "EUR"}, (False, True, "EUR")),
    ],
)
def test_admin_creates_accounts_with_one_or_both_roles(
    admin: TestClient, body: dict[str, object], expected: tuple[object, ...]
) -> None:
    response = admin.post(
        "/api/admin/accounts", json={"username": "alice", "temporary_password": TEMP, **body}
    )
    assert response.status_code == 201, response.text
    account = response.json()
    assert (
        account["is_admin"],
        account["is_investor"],
        account["base_currency"],
    ) == expected


@pytest.mark.req("USR-09")
@pytest.mark.parametrize(
    ("body", "path"),
    [
        ({"is_admin": False, "is_investor": False}, "roles"),
        ({"is_investor": True}, "base_currency"),
    ],
)
def test_new_accounts_need_a_role_and_investors_a_currency(
    admin: TestClient, body: dict[str, object], path: str
) -> None:
    response = admin.post(
        "/api/admin/accounts", json={"username": "alice", "temporary_password": TEMP, **body}
    )
    assert response.status_code == 422
    assert response.json()["problems"][0]["path"] == path


@pytest.mark.req("USR-09", "USR-05")
def test_admin_becomes_investor_too_and_sees_only_own_data(
    admin: TestClient, accounts_api: Accounts, factory: Factory, session: Session
) -> None:
    alice = accounts_api.create("alice")
    factory.policy_draft(alice)
    session.commit()
    root_id = admin.get("/api/auth/me").json()["id"]
    assert roles(admin, root_id, is_admin=True, is_investor=True).status_code == 422
    response = roles(admin, root_id, is_admin=True, is_investor=True, base_currency="chf")
    assert response.status_code == 200, response.text
    me = admin.get("/api/auth/me").json()
    assert (me["is_admin"], me["is_investor"], me["base_currency"]) == (True, True, "CHF")
    assert admin.get("/api/policies").json() == []  # alice's policy stays hidden
    created = admin.post("/api/policies", json={"name": "Mine", "thesis_md": "x"})
    assert created.status_code == 201, created.text
    assert admin.get("/api/admin/accounts").status_code == 200  # still an admin


@pytest.mark.req("USR-09")
def test_investor_role_is_removed_only_without_investment_data(
    admin: TestClient, accounts_api: Accounts, factory: Factory, session: Session
) -> None:
    alice = accounts_api.create("alice")
    bob = accounts_api.create("bob")
    factory.policy_draft(alice)
    session.commit()
    assert roles(admin, alice.id, is_admin=True, is_investor=False).status_code == 409
    response = roles(admin, bob.id, is_admin=True, is_investor=False)
    assert response.status_code == 200, response.text
    assert response.json()["base_currency"] is None
    client = accounts_api.client("bob")
    assert client.get("/api/policies").status_code == 403
    assert client.get("/api/admin/accounts").status_code == 200
    assert roles(admin, bob.id, is_admin=False, is_investor=False).status_code == 422


@pytest.mark.req("USR-09")
def test_the_last_active_admin_keeps_the_admin_role(
    admin: TestClient, accounts_api: Accounts
) -> None:
    root_id = admin.get("/api/auth/me").json()["id"]
    as_investor = {"is_admin": False, "is_investor": True, "base_currency": "CHF"}
    assert roles(admin, root_id, **as_investor).status_code == 409
    carol = accounts_api.create("carol", admin=True, investor=False)
    admin.post(f"/api/admin/accounts/{carol.id}/deactivate")
    assert roles(admin, root_id, **as_investor).status_code == 409  # carol is deactivated
    admin.post(f"/api/admin/accounts/{carol.id}/reactivate")
    assert roles(admin, root_id, **as_investor).status_code == 200
    assert admin.get("/api/admin/accounts").status_code == 403
