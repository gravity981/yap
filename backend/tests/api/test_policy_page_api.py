"""The policy page and list through the API: review again, review log, latest review,
sharing and the semaphore on portfolios (POL-11, POL-18, POL-19, POL-20, PTF-07, REV-12,
REV-20, REV-21, REV-23)."""

import pytest
from fastapi.testclient import TestClient

from tests.fixtures import Accounts, FakeClock, FakeLlm
from tests.reviews.answers import answer, quick_answer

POSITIONS = [
    {
        "ticker": "AAA",
        "name": "A",
        "type": "ETF",
        "target_pct": 100,
        "buy_threshold_pct": -20,
        "sell_threshold_pct": 20,
    }
]


def ok(response, status: int = 200):  # type: ignore[no-untyped-def]
    assert response.status_code == status, response.text
    return response.json() if response.content else None


@pytest.fixture
def alice(accounts_api: Accounts) -> TestClient:
    accounts_api.create("root", admin=True, investor=False)
    root = accounts_api.client("root")
    body = {
        "name": "Standard",
        "provider": "anthropic",
        "model": "claude-x",
        "monthly_review_limit": 5,
        "api_key": "sk-ant-test",
    }
    reviewer_id = ok(root.post("/api/admin/ai-reviewers", json=body), 201)["id"]
    accounts_api.create("alice")
    client: TestClient = accounts_api.client("alice")
    ok(client.put("/api/ai-reviewers/choice", json={"ai_reviewer_id": reviewer_id}))
    return client


def _reviewed(client: TestClient, clock: FakeClock, name: str = "core") -> int:
    """A policy whose v1 was activated with a manual review (good, 7 / 10)."""
    pid = ok(client.post("/api/policies", json={"name": name, "thesis_md": "# T"}), 201)["id"]
    ok(client.put(f"/api/policies/{pid}/draft", json={"positions": POSITIONS}))
    prompt = ok(client.get(f"/api/policies/{pid}/draft/review-prompt"))
    body = {"answer": answer(verdict="good", prompt_id=prompt["prompt_id"])}
    ok(client.post(f"/api/policies/{pid}/draft/review/manual", json=body), 201)
    ok(client.post(f"/api/policies/{pid}/draft/activate", json={}))
    clock.advance(minutes=5)
    return int(pid)


@pytest.mark.req("POL-20", "REV-12", "REV-21", "REV-23", "REV-26", "POL-11", "THS-08")
def test_a_quick_review_of_the_active_version_adds_to_its_log(
    alice: TestClient, fake_llm: FakeLlm, clock: FakeClock
) -> None:
    pid = _reviewed(alice, clock)
    before = ok(alice.get(f"/api/policies/{pid}"))
    assert (before["semaphore"], before["thesis_warning"]) == ("good", False)
    assert before["latest_review"]["total"] == 7.0
    confirmed_at = before["latest_review"]["saved_at"]
    assert confirmed_at == before["active_from"]

    # AI quick review: broken; no new version
    fake_llm.answers = [quick_answer(verdict="broken", verdict_reason="A break condition is met.")]
    started = ok(alice.post(f"/api/policies/{pid}/active/review", json={"news_days": 30}), 202)
    review = ok(alice.get(f"/api/reviews/{started['id']}"))
    assert review["saved_at"] is not None and review["confirmed"] is True
    policy = ok(alice.get(f"/api/policies/{pid}"))
    assert [v["version_no"] for v in policy["versions"]] == [1]
    assert (policy["semaphore"], policy["thesis_warning"]) == ("broken", True)
    assert policy["semaphore_reason"] == "A break condition is met."
    assert policy["latest_review"]["id"] == review["id"]
    assert policy["pending_review"] is None
    # REV-26: the score stays that of the review at activation, there are no aspects
    assert (review["kind"], review["aspects"], review["suggestions"]) == ("quick", [], [])
    assert policy["latest_review"]["total"] == 7.0

    # Manual quick review a day later
    clock.advance(minutes=5)
    prompt = ok(alice.get(f"/api/policies/{pid}/active/review-prompt?news_days=60"))
    body = {"answer": quick_answer(verdict="warning", prompt_id=prompt["prompt_id"])}
    manual = ok(alice.post(f"/api/policies/{pid}/active/review/manual", json=body), 201)
    assert manual["saved_at"] is not None
    # A full answer is no answer to a quick prompt
    full = {"answer": answer(prompt_id=prompt["prompt_id"])}
    assert alice.post(f"/api/policies/{pid}/active/review/manual", json=full).status_code == 422

    log = ok(alice.get(f"/api/policies/{pid}/reviews"))
    assert [e["id"] for e in log] == [manual["id"], review["id"], log[2]["id"]]
    assert [e["at_activation"] for e in log] == [False, False, True]
    assert [e["semaphore"] for e in log] == ["warning", "broken", "good"]
    assert [e["method"] for e in log] == ["manual", "ai", "manual"]
    assert log[0]["version_label"] == "core-v1"
    assert [e["total"] for e in log] == [None, None, 7.0]  # only the full review has a score
    assert log[2]["saved_at"] == confirmed_at

    events = ok(alice.get("/api/timeline?type=review_saved"))
    assert [e["review_id"] for e in events] == [review["id"], manual["id"]]
    assert events[0]["summary"] == "Quick review of core-v1: broken"


@pytest.mark.req("REV-20", "POL-20", "REV-26")
def test_a_quick_review_does_not_clear_the_mark_of_a_version_activated_without_a_review(
    alice: TestClient, fake_llm: FakeLlm, clock: FakeClock
) -> None:
    pid = ok(alice.post("/api/policies", json={"name": "bare", "thesis_md": "# T"}), 201)["id"]
    ok(alice.put(f"/api/policies/{pid}/draft", json={"positions": POSITIONS}))
    ok(alice.post(f"/api/policies/{pid}/draft/activate", json={}))
    policy = ok(alice.get(f"/api/policies/{pid}"))
    assert (policy["mark"], policy["semaphore"], policy["latest_review"]) == (
        "not_reviewed",
        None,
        None,
    )
    clock.advance(minutes=5)
    fake_llm.answers = [quick_answer(verdict="good")]
    ok(alice.post(f"/api/policies/{pid}/active/review", json={}), 202)
    policy = ok(alice.get(f"/api/policies/{pid}"))
    # The quick review gives the semaphore, but no score and no review of the whole policy
    assert (policy["mark"], policy["semaphore"]) == ("not_reviewed", "good")
    assert policy["latest_review"]["total"] is None
    assert policy["versions"][0]["mark"] == "not_reviewed"
    listed = {p["name"]: p for p in ok(alice.get("/api/policies"))}
    assert listed["bare"]["mark"] == "not_reviewed"
    # Sharing needs a review with scores (REV-20)
    refused = alice.put(f"/api/policies/{pid}/sharing", json={"sharing": "text"})
    assert refused.status_code == 409


@pytest.mark.req("POL-18", "REV-20")
def test_sharing_levels_need_a_reviewed_active_version(alice: TestClient, clock: FakeClock) -> None:
    pid = ok(alice.post("/api/policies", json={"name": "new", "thesis_md": "# T"}), 201)["id"]
    assert ok(alice.get(f"/api/policies/{pid}"))["sharing"] == "private"
    refused = alice.put(f"/api/policies/{pid}/sharing", json={"sharing": "text"})
    assert refused.status_code == 409 and "review new first" in refused.text
    unknown = alice.put(f"/api/policies/{pid}/sharing", json={"sharing": "public"})
    assert unknown.status_code == 422 and "Unknown sharing level public" in unknown.text
    # Private is always possible
    assert (
        ok(alice.put(f"/api/policies/{pid}/sharing", json={"sharing": "private"}))["sharing"]
        == "private"
    )
    reviewed = _reviewed(alice, clock, "reviewed")
    for level in ("text", "all", "private"):
        policy = ok(alice.put(f"/api/policies/{reviewed}/sharing", json={"sharing": level}))
        assert policy["sharing"] == level
    ok(alice.put(f"/api/policies/{reviewed}/sharing", json={"sharing": "all"}))
    listed = {p["name"]: p for p in ok(alice.get("/api/policies"))}
    assert (listed["reviewed"]["sharing"], listed["new"]["sharing"]) == ("all", "private")


@pytest.mark.req("POL-19", "REV-21", "REV-09")
def test_the_policies_list_shows_state_review_draft_and_portfolios(
    alice: TestClient, clock: FakeClock
) -> None:
    pid = _reviewed(alice, clock)
    ok(alice.post("/api/portfolios", json={"name": "Main", "policy_id": pid}), 201)
    ok(alice.post(f"/api/policies/{pid}/draft"), 201)
    clock.advance(minutes=5)
    ok(alice.put(f"/api/policies/{pid}/draft", json={"positions": []}))
    ok(alice.post("/api/policies", json={"name": "fresh", "thesis_md": "# T"}), 201)
    listed = {p["name"]: p for p in ok(alice.get("/api/policies"))}
    core = listed["core"]
    assert (core["active_version_no"], core["active_version_label"]) == (1, "core-v1")
    assert core["active_from"] is not None
    assert (core["semaphore"], core["latest_review"]["total"]) == ("good", 7.0)
    assert core["latest_review"]["saved_at"] == core["active_from"]
    assert [p["name"] for p in core["portfolios"]] == ["Main"]
    assert core["draft"]["version_no"] == 2 and core["draft"]["label"] == "core-v2"
    assert (core["draft"]["positions"], core["draft"]["review"]) == (0, None)
    assert core["draft"]["updated_at"] is not None
    fresh = listed["fresh"]
    assert (fresh["active_version_no"], fresh["latest_review"], fresh["semaphore"]) == (
        None,
        None,
        None,
    )
    assert (fresh["draft"]["version_no"], fresh["portfolios"]) == (1, [])


@pytest.mark.req("PTF-07", "THS-04")
def test_portfolios_show_the_semaphore_of_their_policy_with_its_reason(
    alice: TestClient, fake_llm: FakeLlm, clock: FakeClock
) -> None:
    pid = _reviewed(alice, clock)
    pfid = ok(alice.post("/api/portfolios", json={"name": "Main", "policy_id": pid}), 201)["id"]
    overview = ok(alice.get("/api/portfolios"))[0]
    assert (overview["policy_semaphore"], overview["policy_semaphore_reason"]) == (
        "good",
        "Warning signals are observed [1].",
    )
    fake_llm.answers = [quick_answer(verdict="warning", verdict_reason="Growth slows down.")]
    ok(alice.post(f"/api/policies/{pid}/active/review", json={}), 202)
    portfolio = ok(alice.get(f"/api/portfolios/{pfid}"))
    assert (portfolio["policy_semaphore"], portfolio["policy_semaphore_reason"]) == (
        "warning",
        "Growth slows down.",
    )


@pytest.mark.req("POL-21")
def test_a_policy_can_be_renamed(alice: TestClient) -> None:
    pid = ok(alice.post("/api/policies", json={"name": "old", "thesis_md": "# T"}), 201)["id"]
    ok(alice.post("/api/policies", json={"name": "taken", "thesis_md": "# T"}), 201)
    renamed = ok(alice.put(f"/api/policies/{pid}/name", json={"name": "  new  "}))
    assert renamed["name"] == "new"
    # The versions are labelled with the new name
    assert ok(alice.get(f"/api/policies/{pid}"))["versions"][0]["label"] == "new-v1"
    # The same name stays possible, a name of another policy and an empty one are refused
    ok(alice.put(f"/api/policies/{pid}/name", json={"name": "new"}))
    assert alice.put(f"/api/policies/{pid}/name", json={"name": "taken"}).status_code == 409
    assert alice.put(f"/api/policies/{pid}/name", json={"name": "  "}).status_code == 422
