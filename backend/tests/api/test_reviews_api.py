"""Reviews through the API, with the background run (REV-01 to REV-19)."""

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


def _thesis_draft(client: TestClient, name: str = "Growth") -> int:
    """A policy with an active v1 and a draft v2, whose thesis is reviewed."""
    policy = ok(client.post("/api/policies", json={"name": name, "thesis_md": "# Thesis"}), 201)
    pid = policy["id"]
    ok(client.put(f"/api/policies/{pid}/draft", json={"positions": POSITIONS}))
    ok(client.post(f"/api/policies/{pid}/draft/activate", json={}))
    ok(client.post(f"/api/policies/{pid}/draft"), 201)
    return int(pid)


@pytest.mark.req("REV-01", "REV-08", "REV-11", "REV-12", "REV-16", "REV-17", "TL-02", "THS-08")
def test_thesis_review_flow(alice: TestClient, fake_llm: FakeLlm) -> None:
    fake_llm.answers = [thesis_answer()]
    tid = _thesis_draft(alice)
    started = ok(
        alice.post(f"/api/policies/{tid}/draft/thesis-review", json={"news_days": 60}), 202
    )
    assert started["state"] == "queued"
    # The background run has finished when the test client returns
    review = ok(alice.get(f"/api/reviews/{started['id']}"))
    assert review["state"] == "done"
    assert (
        review["ai_reviewer_name"],
        review["provider"],
        review["model"],
        review["scoring_version"],
    ) == ("Standard", "anthropic", "claude-x", "2")
    assert [a["name"] for a in review["aspects"]] == [
        "Belief",
        "Fit and implementation",
        "Opportunity",
        "Downside",
        "Invalidation, warnings and monitoring",
        "Current evidence",
    ]
    assert (review["total"], review["verdict"]) == (6.5, "needs_adaptation")
    assert (review["confirmed"], review["outdated"]) == (False, False)
    assert review["legacy_modification"] is None
    found = ok(alice.get(f"/api/policies/{tid}/versions/2/review?kind=thesis"))
    assert found["id"] == review["id"]
    # The version list carries the review in short (THS-08)
    versions = ok(alice.get(f"/api/policies/{tid}"))["versions"]
    assert versions[0]["thesis_review"] is None and versions[1]["review"] is None
    assert versions[1]["thesis_review"] == {
        "id": review["id"],
        "state": "done",
        "total": 6.5,
        "verdict": "needs_adaptation",
        "scoring_version": "2",
        "method": "ai",
        "model": "claude-x",
        "ai_reviewer_name": "Standard",
        "outdated": False,
    }
    usage = ok(alice.get("/api/reviews/usage"))
    assert (usage["used"], usage["left"], usage["unavailable_reason"]) == (1, 2, None)

    ok(alice.post(f"/api/policies/{tid}/draft/activate", json={"change_note": "Reviewed"}))
    assert ok(alice.get(f"/api/reviews/{review['id']}"))["confirmed"] is True
    event = ok(alice.get("/api/timeline?type=thesis_review_confirmed"))[0]
    assert event["summary"] == "Thesis review of Growth-v2: needs adaptation, 6.5 / 10"
    assert event["review_id"] == review["id"]
    # Reviews cannot be changed (REV-10 dropped)
    assert alice.put(f"/api/reviews/{review['id']}", json={"scores": {}}).status_code == 405


@pytest.mark.req("REV-01", "REV-05")
def test_policy_review_flow(alice: TestClient, fake_llm: FakeLlm) -> None:
    fake_llm.answers = [policy_answer()]
    pid = ok(alice.post("/api/policies", json={"name": "core", "thesis_md": "# Thesis"}), 201)["id"]
    ok(alice.put(f"/api/policies/{pid}/draft", json={"positions": POSITIONS}))
    started = ok(alice.post(f"/api/policies/{pid}/draft/review"), 202)
    review = ok(alice.get(f"/api/policies/{pid}/versions/1/review"))
    assert (review["id"], review["state"], review["total"]) == (started["id"], "done", 7.5)
    assert review["verdict"] is None and review["sources"] == []
    version = ok(alice.get(f"/api/policies/{pid}"))["versions"][0]
    assert (version["review"]["id"], version["review"]["total"]) == (review["id"], 7.5)


@pytest.mark.req("REV-19", "REV-16", "NFR-01")
def test_the_review_prompt_of_a_draft_changes_nothing(
    alice: TestClient, accounts_api: Accounts
) -> None:
    from yap.services.review_prompts import parse_prompt_id

    tid = _thesis_draft(alice)
    prompt = ok(alice.get(f"/api/policies/{tid}/draft/thesis-review-prompt?news_days=30"))
    ref = parse_prompt_id(prompt["prompt_id"])
    assert ref is not None and (ref.kind, ref.news_days) == ("thesis", 30)
    assert prompt["prompt_id"] in prompt["text"] and "# Thesis" in prompt["text"]
    assert "alice" not in prompt["text"]
    # No review is started and nothing counts towards the limit
    draft = ok(alice.get(f"/api/policies/{tid}"))["versions"][1]
    assert draft["thesis_review"] is None and ref.draft_id == draft["id"]
    assert ok(alice.get("/api/reviews/usage"))["used"] == 0
    assert (
        alice.get(f"/api/policies/{tid}/draft/thesis-review-prompt?news_days=0").status_code == 422
    )

    ok(alice.post(f"/api/policies/{tid}/draft/activate", json={"change_note": "x"}))
    assert (
        alice.get(f"/api/policies/{tid}/draft/thesis-review-prompt").status_code == 404
    )  # no draft
    pid = tid
    ok(alice.post(f"/api/policies/{pid}/draft"), 201)
    policy_prompt = ok(alice.get(f"/api/policies/{pid}/draft/review-prompt"))
    assert parse_prompt_id(policy_prompt["prompt_id"]).kind == "policy"  # type: ignore[union-attr]
    assert "<target_structure>" in policy_prompt["text"]

    accounts_api.create("bob")
    bob = accounts_api.client("bob")
    assert bob.get(f"/api/policies/{pid}/draft/review-prompt").status_code == 404


@pytest.mark.req("REV-18", "REV-16", "REV-17", "REV-11", "REV-12", "TL-02", "THS-08")
def test_manual_thesis_review_flow(alice: TestClient, fake_llm: FakeLlm) -> None:
    tid = _thesis_draft(alice)
    prompt = ok(alice.get(f"/api/policies/{tid}/draft/thesis-review-prompt?news_days=30"))
    answer = f"Sure, here it is:\n```json\n{thesis_answer(prompt_id=prompt['prompt_id'])}\n```"
    review = ok(
        alice.post(
            f"/api/policies/{tid}/draft/thesis-review/manual",
            json={"answer": answer, "model": "  ChatGPT   5 "},
        ),
        201,
    )
    assert (review["method"], review["provider"], review["model"]) == (
        "manual",
        "manual",
        "ChatGPT 5",
    )
    assert (review["state"], review["total"], review["verdict"]) == (
        "done",
        6.5,
        "needs_adaptation",
    )
    assert (review["prompt_id"], review["ai_reviewer_name"]) == (prompt["prompt_id"], None)
    assert (review["outdated"], review["confirmed"]) == (False, False)
    assert review["news_from"] is not None and len(review["sources"]) == 2
    # No AI reviewer was asked and nothing counts towards the limit
    assert fake_llm.requests == [] and ok(alice.get("/api/reviews/usage"))["used"] == 0

    ok(alice.post(f"/api/policies/{tid}/draft/activate", json={"change_note": "Reviewed"}))
    assert ok(alice.get(f"/api/reviews/{review['id']}"))["confirmed"] is True
    event = ok(alice.get("/api/timeline?type=thesis_review_confirmed"))[0]
    assert event["summary"] == "Thesis review of Growth-v2: needs adaptation, 6.5 / 10"


@pytest.mark.req("REV-18", "REV-09", "REV-05")
def test_a_manual_answer_replaces_the_review_and_is_outdated_after_a_change(
    alice: TestClient, accounts_api: Accounts, fake_llm: FakeLlm
) -> None:
    fake_llm.answers = [thesis_answer()]
    tid = _thesis_draft(alice)
    first = ok(alice.post(f"/api/policies/{tid}/draft/thesis-review", json={}), 202)
    prompt = ok(alice.get(f"/api/policies/{tid}/draft/thesis-review-prompt"))["prompt_id"]
    # The draft changes after the prompt was copied
    accounts_api.clock.advance(minutes=5)
    thesis = {"title": "Growth", "content_md": "new", "status": "intact"}
    ok(alice.put(f"/api/policies/{tid}/draft", json={"positions": POSITIONS, "thesis": thesis}))
    body = {"answer": thesis_answer(prompt_id=prompt), "model": "Gemini"}
    manual = ok(alice.post(f"/api/policies/{tid}/draft/thesis-review/manual", json=body), 201)
    assert manual["outdated"] is True
    assert first["method"] == "ai" and manual["method"] == "manual"
    draft = ok(alice.get(f"/api/policies/{tid}"))["versions"][1]
    assert draft["thesis_review"]["id"] == manual["id"]  # the AI review was replaced (REV-09)
    assert ok(alice.get(f"/api/reviews/{manual['id']}"))["model"] == "Gemini"

    # A policy review the same way
    pid = tid
    policy_prompt = ok(alice.get(f"/api/policies/{pid}/draft/review-prompt"))["prompt_id"]
    body = {"answer": policy_answer(prompt_id=policy_prompt), "model": "Claude"}
    policy_review = ok(alice.post(f"/api/policies/{pid}/draft/review/manual", json=body), 201)
    assert (policy_review["kind"], policy_review["total"], policy_review["outdated"]) == (
        "policy",
        7.5,
        False,
    )


@pytest.mark.req("REV-18", "REV-19")
def test_a_manual_answer_with_problems_lists_them_all(alice: TestClient) -> None:
    tid = _thesis_draft(alice)
    prompt = ok(alice.get(f"/api/policies/{tid}/draft/thesis-review-prompt"))["prompt_id"]
    url = f"/api/policies/{tid}/draft/thesis-review/manual"

    def problems(answer: str, model: str = "GPT") -> list[tuple[str, str]]:
        response = alice.post(url, json={"answer": answer, "model": model})
        assert response.status_code == 422, response.text
        return [(p["path"], p["code"]) for p in response.json()["problems"]]

    assert problems("no idea", model=" ") == [
        ("model", "review_model_required"),
        ("answer", "answer_prompt_id_unknown"),
        ("answer", "answer_no_json"),
    ]
    bad = thesis_answer(scores=(7, 6, 8, 5, 7, 6.3), prompt_id=prompt)
    assert problems(bad) == [("answer", "score_invalid")]
    other_draft = prompt.replace("T", "P", 1)
    assert problems(thesis_answer(prompt_id=other_draft)) == [
        ("answer", "answer_prompt_id_unknown")
    ]
    pid_tid = _thesis_draft(alice, "Other")
    other = ok(alice.get(f"/api/policies/{pid_tid}/draft/thesis-review-prompt"))["prompt_id"]
    assert problems(thesis_answer(prompt_id=other)) == [("answer", "answer_prompt_id_other_draft")]
    assert problems(thesis_answer(prompt_id=prompt), model="x" * 101) == [
        ("model", "review_model_too_long")
    ]
    # Nothing was stored
    assert ok(alice.get(f"/api/policies/{tid}"))["versions"][1]["thesis_review"] is None


@pytest.mark.req("USR-08", "REV-18")
def test_manual_can_be_the_default_review_method(alice: TestClient) -> None:
    me = ok(alice.get("/api/auth/me"))
    assert me["manual_review_default"] is False and me["ai_reviewer_id"] is not None
    choice = ok(
        alice.put("/api/ai-reviewers/choice", json={"ai_reviewer_id": None, "manual": True})
    )
    assert choice == {"ai_reviewer_id": None, "manual": True}
    me = ok(alice.get("/api/auth/me"))
    assert (me["manual_review_default"], me["ai_reviewer_id"]) == (True, None)
    reviewer = ok(alice.get("/api/ai-reviewers"))[0]["id"]
    choice = ok(alice.put("/api/ai-reviewers/choice", json={"ai_reviewer_id": reviewer}))
    assert choice == {"ai_reviewer_id": reviewer, "manual": False}


@pytest.mark.req("REV-16")
def test_starting_beyond_the_limit_is_refused(alice: TestClient, fake_llm: FakeLlm) -> None:
    fake_llm.answers = [thesis_answer()]
    tid = _thesis_draft(alice)
    for _ in range(3):
        ok(alice.post(f"/api/policies/{tid}/draft/thesis-review", json={}), 202)
    refused = alice.post(f"/api/policies/{tid}/draft/thesis-review", json={})
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
    started = alice.post(f"/api/policies/{tid}/draft/thesis-review", json={"ai_reviewer_id": deep})
    assert ok(started, 202)["ai_reviewer_name"] == "Deep"
    assert fake_llm.configs[-1].model == "gpt-x"
    ok(alice.post(f"/api/policies/{tid}/draft/activate", json={"change_note": "x"}))
    pid = ok(alice.post("/api/policies", json={"name": "core", "thesis_id": tid}), 201)["id"]
    refused = alice.post(f"/api/policies/{pid}/draft/review", json={"ai_reviewer_id": deep})
    assert refused.status_code == 409 and "All 1 reviews with Deep" in refused.text
