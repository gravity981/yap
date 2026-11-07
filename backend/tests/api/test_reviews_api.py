"""Reviews through the API, with the background run (REV-01 to REV-17)."""

import pytest
from fastapi.testclient import TestClient

from tests.fixtures import Accounts, FakeLlm
from tests.reviews.answers import policy_answer, thesis_answer


def ok(response, status: int = 200):  # type: ignore[no-untyped-def]
    assert response.status_code == status, response.text
    return response.json() if response.content else None


@pytest.fixture
def alice(accounts_api: Accounts) -> TestClient:
    accounts_api.create("root", admin=True, investor=False)
    root = accounts_api.client("root")
    reviewer = {"name": "Standard", "provider": "anthropic", "model": "claude-x"}
    body = {**reviewer, "monthly_review_limit": 3, "api_key": "sk-ant-test"}
    reviewer_id = ok(root.post("/api/admin/ai-reviewers", json=body), 201)["id"]
    accounts_api.create("alice")
    client = accounts_api.client("alice")
    ok(client.put("/api/ai-reviewers/choice", json={"ai_reviewer_id": reviewer_id}))
    return client


def _thesis_draft(client: TestClient) -> int:
    thesis = ok(client.post("/api/theses", json={"title": "Growth", "content_md": "# Thesis"}), 201)
    ok(client.post(f"/api/theses/{thesis['id']}/draft/activate", json={}))
    ok(client.post(f"/api/theses/{thesis['id']}/draft"), 201)
    return int(thesis["id"])


@pytest.mark.req("REV-01", "REV-08", "REV-11", "REV-12", "REV-16", "REV-17", "TL-02", "THS-08")
def test_thesis_review_flow(alice: TestClient, fake_llm: FakeLlm) -> None:
    fake_llm.answers = [thesis_answer()]
    tid = _thesis_draft(alice)
    started = ok(alice.post(f"/api/theses/{tid}/draft/review", json={"news_days": 60}), 202)
    assert started["state"] == "queued"
    # The background run has finished when the test client returns
    review = ok(alice.get(f"/api/reviews/{started['id']}"))
    assert review["state"] == "done"
    assert (
        review["ai_reviewer_name"],
        review["provider"],
        review["model"],
        review["scoring_version"],
    ) == ("Standard", "anthropic", "claude-x", "1")
    assert [a["name"] for a in review["aspects"]][:2] == ["Core claim", "Value drivers"]
    assert (review["total"], review["verdict"]) == (6.5, "needs_adaptation")
    assert (review["confirmed"], review["outdated"]) == (False, False)
    assert review["legacy_modification"] is None
    assert ok(alice.get(f"/api/theses/{tid}/revisions/2/review"))["id"] == review["id"]
    # The revision list carries the review in short (THS-08)
    revisions = ok(alice.get(f"/api/theses/{tid}"))["revisions"]
    assert revisions[0]["review"] is None
    assert revisions[1]["review"] == {
        "id": review["id"],
        "state": "done",
        "total": 6.5,
        "verdict": "needs_adaptation",
        "outdated": False,
    }
    usage = ok(alice.get("/api/reviews/usage"))
    assert (usage["used"], usage["left"], usage["unavailable_reason"]) == (1, 2, None)

    ok(alice.post(f"/api/theses/{tid}/draft/activate", json={"change_note": "Reviewed"}))
    assert ok(alice.get(f"/api/reviews/{review['id']}"))["confirmed"] is True
    event = ok(alice.get("/api/timeline?type=thesis_review_confirmed"))[0]
    assert event["summary"] == "Thesis review of 'Growth' revision 2: needs adaptation, 6.5 / 10"
    assert event["review_id"] == review["id"]
    # Reviews cannot be changed (REV-10 dropped)
    assert alice.put(f"/api/reviews/{review['id']}", json={"scores": {}}).status_code == 405


@pytest.mark.req("REV-01", "REV-05")
def test_policy_review_flow(alice: TestClient, fake_llm: FakeLlm) -> None:
    fake_llm.answers = [policy_answer()]
    tid = _thesis_draft(alice)
    ok(alice.post(f"/api/theses/{tid}/draft/activate", json={"change_note": "x"}))
    pid = ok(alice.post("/api/policies", json={"name": "core", "thesis_id": tid}), 201)["id"]
    started = ok(alice.post(f"/api/policies/{pid}/draft/review"), 202)
    review = ok(alice.get(f"/api/policies/{pid}/versions/1/review"))
    assert (review["id"], review["state"], review["total"]) == (started["id"], "done", 7.5)
    assert review["verdict"] is None and review["sources"] == []
    version = ok(alice.get(f"/api/policies/{pid}"))["versions"][0]
    assert (version["review"]["id"], version["review"]["total"]) == (review["id"], 7.5)


@pytest.mark.req("REV-16")
def test_starting_beyond_the_limit_is_refused(alice: TestClient, fake_llm: FakeLlm) -> None:
    fake_llm.answers = [thesis_answer()]
    tid = _thesis_draft(alice)
    for _ in range(3):
        ok(alice.post(f"/api/theses/{tid}/draft/review", json={}), 202)
    refused = alice.post(f"/api/theses/{tid}/draft/review", json={})
    assert refused.status_code == 409
    assert "All 3 reviews with Standard of this month are used" in refused.text
    assert len(fake_llm.requests) == 3  # nothing was sent for the refused one
    assert ok(alice.get("/api/reviews/usage"))["left"] == 0


@pytest.mark.req("USR-08", "REV-16")
def test_a_review_runs_on_the_reviewer_chosen_for_it(
    alice: TestClient, accounts_api: Accounts, fake_llm: FakeLlm
) -> None:
    root = accounts_api.client("root")
    body = {"name": "Deep", "provider": "openai", "model": "gpt-x", "monthly_review_limit": 1}
    deep = ok(root.post("/api/admin/ai-reviewers", json={**body, "api_key": "sk-x"}), 201)["id"]
    usage = ok(alice.get(f"/api/reviews/usage?ai_reviewer_id={deep}"))
    assert (usage["ai_reviewer_name"], usage["left"]) == ("Deep", 1)
    assert ok(alice.get("/api/reviews/usage"))["ai_reviewer_name"] == "Standard"  # default
    assert alice.get("/api/reviews/usage?ai_reviewer_id=999").status_code == 404

    fake_llm.answers = [thesis_answer()]
    tid = _thesis_draft(alice)
    started = alice.post(f"/api/theses/{tid}/draft/review", json={"ai_reviewer_id": deep})
    assert ok(started, 202)["ai_reviewer_name"] == "Deep"
    assert fake_llm.configs[-1].model == "gpt-x"
    ok(alice.post(f"/api/theses/{tid}/draft/activate", json={"change_note": "x"}))
    pid = ok(alice.post("/api/policies", json={"name": "core", "thesis_id": tid}), 201)["id"]
    refused = alice.post(f"/api/policies/{pid}/draft/review", json={"ai_reviewer_id": deep})
    assert refused.status_code == 409 and "All 1 reviews with Deep" in refused.text
