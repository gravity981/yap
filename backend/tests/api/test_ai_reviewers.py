"""AI reviewers through the API: the admin configures them, investors choose one
(REV-13 to REV-15, USR-08)."""

import pytest
from fastapi.testclient import TestClient

from tests.fixtures import Accounts, FakeLlm

KEY = "sk-ant-secret-key-5678"
BODY = {
    "name": "Deep",
    "description": "Thorough, slower",
    "provider": "openai",
    "model": "gpt-x",
    "monthly_review_limit": 30,
    "api_key": KEY,
}


@pytest.fixture
def admin(accounts_api: Accounts) -> TestClient:
    accounts_api.create("root", admin=True, investor=False)
    return accounts_api.client("root")


def ok(response, status: int = 200):  # type: ignore[no-untyped-def]
    assert response.status_code == status, response.text
    return response.json()


@pytest.mark.req("REV-13", "REV-14", "REV-15")
def test_admin_configures_tests_and_archives_reviewers(
    admin: TestClient, fake_llm: FakeLlm
) -> None:
    assert ok(admin.get("/api/admin/ai-reviewers")) == {"reviewers": [], "keys_available": True}
    reviewer = ok(admin.post("/api/admin/ai-reviewers", json=BODY), 201)
    assert (reviewer["name"], reviewer["api_key_last4"], reviewer["enabled"]) == (
        "Deep",
        "5678",
        True,
    )
    url = f"/api/admin/ai-reviewers/{reviewer['id']}"
    # The stored key is never returned
    for response in (
        admin.get("/api/admin/ai-reviewers"),
        admin.put(url, json={**BODY, "api_key": None, "enabled": False}),
    ):
        assert response.status_code == 200 and KEY not in response.text
    assert ok(admin.get("/api/admin/ai-reviewers"))["reviewers"][0]["enabled"] is False

    result = ok(admin.post(f"{url}/test"))
    assert result == {
        "ok": True,
        "message": "Connected to openai, model gpt-x",
        "code": "connection_ok",
        "params": {"provider": "openai", "model": "gpt-x"},
    }
    assert fake_llm.configs[-1].api_key == KEY  # the key was kept
    fake_llm.error = "OpenAI rejected the API key"
    assert ok(admin.post(f"{url}/test"))["ok"] is False

    assert admin.put(url, json={**BODY, "provider": "x"}).status_code == 422
    assert admin.post("/api/admin/ai-reviewers", json=BODY).status_code == 422  # name taken
    assert admin.post(f"{url}/archive").status_code == 204
    assert ok(admin.get("/api/admin/ai-reviewers"))["reviewers"] == []
    assert admin.put(url, json=BODY).status_code == 404


@pytest.mark.req("USR-08", "REV-16")
def test_investor_chooses_a_reviewer_and_sees_its_usage(
    admin: TestClient, accounts_api: Accounts
) -> None:
    deep = ok(admin.post("/api/admin/ai-reviewers", json=BODY), 201)
    off = ok(
        admin.post("/api/admin/ai-reviewers", json={**BODY, "name": "Off", "enabled": False}), 201
    )
    accounts_api.create("alice")
    alice = accounts_api.client("alice")
    options = ok(alice.get("/api/ai-reviewers"))
    assert options == [
        {
            "id": deep["id"],
            "name": "Deep",
            "description": "Thorough, slower",
            "provider": "openai",
            "model": "gpt-x",
            "monthly_review_limit": 30,
        }
    ]
    assert KEY[-4:] not in alice.get("/api/ai-reviewers").text
    usage = ok(alice.get("/api/reviews/usage"))
    assert usage["unavailable_reason"] == "Choose an AI reviewer"

    assert ok(alice.put("/api/ai-reviewers/choice", json={"ai_reviewer_id": deep["id"]})) == {
        "ai_reviewer_id": deep["id"]
    }
    assert ok(alice.get("/api/auth/me"))["ai_reviewer_id"] == deep["id"]
    usage = ok(alice.get("/api/reviews/usage"))
    assert (usage["ai_reviewer_name"], usage["limit"], usage["left"]) == ("Deep", 30, 30)
    assert usage["unavailable_reason"] is None
    response = alice.put("/api/ai-reviewers/choice", json={"ai_reviewer_id": off["id"]})
    assert response.status_code == 409
    assert alice.put("/api/ai-reviewers/choice", json={"ai_reviewer_id": 999}).status_code == 404


@pytest.mark.req("USR-05", "USR-08")
def test_admins_configure_and_investors_choose(admin: TestClient, accounts_api: Accounts) -> None:
    accounts_api.create("alice")
    alice = accounts_api.client("alice")
    assert alice.get("/api/admin/ai-reviewers").status_code == 403
    assert alice.post("/api/admin/ai-reviewers", json=BODY).status_code == 403
    assert admin.get("/api/ai-reviewers").status_code == 403
    assert admin.put("/api/ai-reviewers/choice", json={"ai_reviewer_id": None}).status_code == 403
