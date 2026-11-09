"""Reviews through the API, with the background run (REV-01 to REV-19)."""

import pytest
from fastapi.testclient import TestClient

from tests.fixtures import Accounts, FakeClock, FakeLlm
from tests.reviews.answers import answer, proposal, suggestion, thesis_answer


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


def _draft(client: TestClient, name: str = "Growth") -> int:
    """A policy with an active v1 and a draft v2 with a position, which is reviewed."""
    policy = ok(client.post("/api/policies", json={"name": name, "thesis_md": "# Thesis"}), 201)
    pid = policy["id"]
    ok(client.put(f"/api/policies/{pid}/draft", json={"positions": POSITIONS}))
    ok(client.post(f"/api/policies/{pid}/draft/activate", json={}))
    ok(client.post(f"/api/policies/{pid}/draft"), 201)
    return int(pid)


@pytest.mark.req(
    "REV-01",
    "REV-02",
    "REV-03",
    "REV-08",
    "REV-11",
    "REV-12",
    "REV-16",
    "REV-17",
    "TL-02",
    "THS-04",
    "THS-08",
)
def test_review_flow(alice: TestClient, fake_llm: FakeLlm) -> None:
    fake_llm.answers = [answer()]
    pid = _draft(alice)
    started = ok(alice.post(f"/api/policies/{pid}/draft/review", json={"news_days": 60}), 202)
    assert (started["kind"], started["state"]) == ("full", "queued")
    # The background run has finished when the test client returns
    review = ok(alice.get(f"/api/reviews/{started['id']}"))
    assert review["state"] == "done"
    assert (
        review["ai_reviewer_name"],
        review["provider"],
        review["model"],
        review["scoring_version"],
    ) == ("Standard", "anthropic", "claude-x", "3")
    names = {a["code"]: a["name"] for a in review["aspects"]}
    assert len(names) == 12
    assert (names["T2"], names["T5"], names["P3"]) == (
        "Fit and implementation",
        "Invalidation, warnings and monitoring",
        "Bands",
    )
    assert (review["total"], review["thesis_score"], review["structure_score"]) == (7, 6.5, 7.5)
    assert (review["semaphore"], review["verdict"], review["verdict_reason"]) == (
        "warning",
        "warning",
        "Warning signals are observed [1].",
    )
    assert (review["confirmed"], review["outdated"], review["saved_at"]) == (False, False, None)
    assert review["legacy_modification"] is None
    found = ok(alice.get(f"/api/policies/{pid}/versions/2/review"))
    assert found["id"] == review["id"]
    # The version list carries the review in short (THS-08)
    policy = ok(alice.get(f"/api/policies/{pid}"))
    versions = policy["versions"]
    assert versions[0]["review"] is None and versions[0]["reviews"] == []
    brief = {
        "id": review["id"],
        "kind": "full",
        "state": "done",
        "total": 7.0,
        "thesis_score": 6.5,
        "structure_score": 7.5,
        "semaphore": "warning",
        "scoring_version": "3",
        "method": "ai",
        "model": "claude-x",
        "ai_reviewer_name": "Standard",
        "outdated": False,
        "completed_at": review["completed_at"],
        "saved_at": None,  # open while the draft is (REV-11)
    }
    assert versions[1]["review"] == brief and versions[1]["reviews"] == [brief]
    # v1 was activated without a review: not reviewed (THS-04)
    assert (policy["semaphore"], policy["thesis_warning"]) == (None, False)
    usage = ok(alice.get("/api/reviews/usage"))
    assert (usage["used"], usage["left"], usage["unavailable_reason"]) == (1, 2, None)

    ok(alice.post(f"/api/policies/{pid}/draft/activate", json={"change_note": "Reviewed"}))
    assert ok(alice.get(f"/api/reviews/{review['id']}"))["confirmed"] is True
    event = ok(alice.get("/api/timeline?type=review_confirmed"))[0]
    assert event["summary"] == "Review of Growth-v2: warning, 7 / 10"
    assert event["review_id"] == review["id"]
    # The semaphore of the active version now comes from its review (THS-04)
    policy = ok(alice.get(f"/api/policies/{pid}"))
    assert (policy["semaphore"], policy["thesis_warning"]) == ("warning", True)
    summary = ok(alice.get("/api/policies"))[0]
    assert (summary["semaphore"], summary["thesis_warning"]) == ("warning", True)
    # Reviews cannot be changed (REV-10 dropped)
    assert alice.put(f"/api/reviews/{review['id']}", json={"scores": {}}).status_code == 405


@pytest.mark.req("REV-01", "REV-02")
def test_a_new_policy_without_positions_is_reviewed_on_its_thesis(
    alice: TestClient, fake_llm: FakeLlm
) -> None:
    fake_llm.answers = [thesis_answer(verdict="good")]
    pid = ok(alice.post("/api/policies", json={"name": "core", "thesis_md": "# Thesis"}), 201)["id"]
    started = ok(alice.post(f"/api/policies/{pid}/draft/review"), 202)
    review = ok(alice.get(f"/api/policies/{pid}/versions/1/review"))
    assert (review["id"], review["state"]) == (started["id"], "done")
    assert (review["total"], review["thesis_score"], review["structure_score"]) == (6.5, 6.5, None)
    assert [a["code"] for a in review["aspects"]] == ["T1", "T2", "T3", "T4", "T5", "T6"]
    assert "(no positions yet)" in fake_llm.requests[0].prompt
    assert fake_llm.requests[0].web_search is True


@pytest.mark.req("REV-19", "REV-16", "REV-05", "NFR-01")
def test_the_review_prompt_of_a_draft_changes_nothing(
    alice: TestClient, accounts_api: Accounts
) -> None:
    from yap.services.review_prompts import parse_prompt_id

    pid = _draft(alice)
    prompt = ok(alice.get(f"/api/policies/{pid}/draft/review-prompt?news_days=30"))
    ref = parse_prompt_id(prompt["prompt_id"])
    assert ref is not None and ref.news_days == 30
    assert prompt["prompt_id"] in prompt["text"] and "# Thesis" in prompt["text"]
    assert "<target_structure>" in prompt["text"] and "| AAA | A | ETF | 100 |" in prompt["text"]
    assert "alice" not in prompt["text"]
    # No review is started and nothing counts towards the limit
    draft = ok(alice.get(f"/api/policies/{pid}"))["versions"][1]
    assert draft["review"] is None and ref.version_id == draft["id"]
    assert ok(alice.get("/api/reviews/usage"))["used"] == 0
    assert alice.get(f"/api/policies/{pid}/draft/review-prompt?news_days=0").status_code == 422

    ok(alice.post(f"/api/policies/{pid}/draft/activate", json={"change_note": "x"}))
    assert alice.get(f"/api/policies/{pid}/draft/review-prompt").status_code == 404  # no draft

    accounts_api.create("bob")
    bob = accounts_api.client("bob")
    ok(alice.post(f"/api/policies/{pid}/draft"), 201)
    assert bob.get(f"/api/policies/{pid}/draft/review-prompt").status_code == 404


@pytest.mark.req("REV-18", "REV-16", "REV-17", "REV-11", "REV-12", "TL-02", "THS-08")
def test_manual_review_flow(alice: TestClient, fake_llm: FakeLlm) -> None:
    pid = _draft(alice)
    prompt = ok(alice.get(f"/api/policies/{pid}/draft/review-prompt?news_days=30"))
    text = f"Sure, here it is:\n```json\n{answer(prompt_id=prompt['prompt_id'])}\n```"
    review = ok(alice.post(f"/api/policies/{pid}/draft/review/manual", json={"answer": text}), 201)
    # A manual review names no model (REV-17)
    assert (review["kind"], review["method"], review["provider"], review["model"]) == (
        "full",
        "manual",
        "manual",
        None,
    )
    assert (review["state"], review["total"], review["semaphore"]) == ("done", 7, "warning")
    assert (review["prompt_id"], review["ai_reviewer_name"]) == (prompt["prompt_id"], None)
    assert (review["outdated"], review["confirmed"]) == (False, False)
    assert review["news_from"] is not None and len(review["sources"]) == 2
    # No AI reviewer was asked and nothing counts towards the limit
    assert fake_llm.requests == [] and ok(alice.get("/api/reviews/usage"))["used"] == 0
    brief = ok(alice.get(f"/api/policies/{pid}"))["versions"][1]["review"]
    assert (brief["method"], brief["model"]) == ("manual", None)

    ok(alice.post(f"/api/policies/{pid}/draft/activate", json={"change_note": "Reviewed"}))
    assert ok(alice.get(f"/api/reviews/{review['id']}"))["confirmed"] is True
    event = ok(alice.get("/api/timeline?type=review_confirmed"))[0]
    assert event["summary"] == "Review of Growth-v2: warning, 7 / 10"


@pytest.mark.req("REV-18", "REV-09")
def test_a_manual_answer_replaces_the_review_and_is_outdated_after_a_change(
    alice: TestClient, accounts_api: Accounts, fake_llm: FakeLlm
) -> None:
    fake_llm.answers = [answer()]
    pid = _draft(alice)
    first = ok(alice.post(f"/api/policies/{pid}/draft/review", json={}), 202)
    prompt = ok(alice.get(f"/api/policies/{pid}/draft/review-prompt"))["prompt_id"]
    # The draft changes after the prompt was copied
    accounts_api.clock.advance(minutes=5)
    thesis = {"title": "Growth", "content_md": "new"}
    ok(alice.put(f"/api/policies/{pid}/draft", json={"positions": POSITIONS, "thesis": thesis}))
    body = {"answer": answer(prompt_id=prompt)}
    manual = ok(alice.post(f"/api/policies/{pid}/draft/review/manual", json=body), 201)
    assert manual["outdated"] is True
    assert first["method"] == "ai" and manual["method"] == "manual"
    draft = ok(alice.get(f"/api/policies/{pid}"))["versions"][1]
    assert draft["review"]["id"] == manual["id"]  # the AI review was replaced (REV-09)
    assert [r["id"] for r in draft["reviews"]] == [manual["id"]]


@pytest.mark.req("REV-18", "REV-19")
def test_a_manual_answer_with_problems_lists_them_all(alice: TestClient) -> None:
    pid = _draft(alice)
    prompt = ok(alice.get(f"/api/policies/{pid}/draft/review-prompt"))["prompt_id"]
    url = f"/api/policies/{pid}/draft/review/manual"

    def problems(text: str) -> list[tuple[str, str]]:
        response = alice.post(url, json={"answer": text})
        assert response.status_code == 422, response.text
        return [(p["path"], p["code"]) for p in response.json()["problems"]]

    assert problems("no idea") == [
        ("answer", "answer_prompt_id_unknown"),
        ("answer", "answer_no_json"),
    ]
    bad = answer(scores=(7, 6, 8, 5, 7, 6.3), prompt_id=prompt)
    assert problems(bad) == [("answer", "score_invalid")]
    # The draft has a position, so the target structure must be scored
    assert problems(thesis_answer(prompt_id=prompt)) == [("answer", "answer_aspects_wrong")]
    assert problems(answer(prompt_id=prompt.replace("R", "T", 1))) == [
        ("answer", "answer_prompt_id_unknown")
    ]
    other_pid = _draft(alice, "Other")
    other = ok(alice.get(f"/api/policies/{other_pid}/draft/review-prompt"))["prompt_id"]
    assert problems(answer(prompt_id=other)) == [("answer", "answer_prompt_id_other_draft")]
    # Nothing was stored
    assert ok(alice.get(f"/api/policies/{pid}"))["versions"][1]["review"] is None


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
    fake_llm.answers = [answer()]
    pid = _draft(alice)
    for _ in range(3):
        ok(alice.post(f"/api/policies/{pid}/draft/review", json={}), 202)
    refused = alice.post(f"/api/policies/{pid}/draft/review", json={})
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

    fake_llm.answers = [answer()]
    pid = _draft(alice)
    started = alice.post(f"/api/policies/{pid}/draft/review", json={"ai_reviewer_id": deep})
    assert ok(started, 202)["ai_reviewer_name"] == "Deep"
    assert fake_llm.configs[-1].model == "gpt-x"
    refused = alice.post(f"/api/policies/{pid}/draft/review", json={"ai_reviewer_id": deep})
    assert refused.status_code == 409 and "All 1 reviews with Deep" in refused.text


@pytest.mark.req("REV-07", "REV-09")
def test_suggestions_are_taken_over_dismissed_and_undone(
    alice: TestClient, accounts_api: Accounts, fake_llm: FakeLlm, clock: FakeClock
) -> None:
    fake_llm.answers = [
        answer(
            suggestions=[
                suggestion("thesis_section", "Measurable.", section=7, text="- GDP below 2 %"),
                suggestion("position_change", "Wider.", ticker="AAA", sell_threshold_pct=30),
            ],
            proposals=[proposal()],  # ignored: the draft has positions
        )
    ]
    pid = _draft(alice)
    rid = ok(alice.post(f"/api/policies/{pid}/draft/review", json={}), 202)["id"]
    review = ok(alice.get(f"/api/reviews/{rid}"))
    section, change = review["suggestions"]
    assert [s["kind"] for s in review["suggestions"]] == ["thesis_section", "position_change"]
    assert (section["state"], section["previous"]) == ("open", None)
    assert change["change"] == {"ticker": "AAA", "field": "sell_threshold_pct", "value": "30"}

    base = f"/api/reviews/{rid}/suggestions"
    clock.advance(minutes=1)
    result = ok(alice.post(f"{base}/{change['id']}/take-over"))
    assert result["draft"]["positions"][0]["sell_threshold_pct"] == "30"
    taken = result["review"]["suggestions"][1]
    assert (taken["state"], taken["previous"]["value"]) == ("taken_over", "20")
    assert result["review"]["outdated"] is True
    # The draft's summary says so too
    draft = ok(alice.get(f"/api/policies/{pid}"))["versions"][-1]
    assert draft["review"]["outdated"] is True

    result = ok(alice.post(f"{base}/{change['id']}/undo"))
    assert result["draft"]["positions"][0]["sell_threshold_pct"] == "20"
    assert result["review"]["suggestions"][1]["state"] == "open"

    # Dismissing deletes the suggestion for good: it cannot be taken over or undone any more
    result = ok(alice.post(f"{base}/{section['id']}/dismiss"))
    assert [s["id"] for s in result["review"]["suggestions"]] == [change["id"]]
    assert "## 7." not in result["draft"]["thesis_md"]
    assert alice.post(f"{base}/{section['id']}/take-over").status_code == 404
    assert alice.post(f"{base}/{section['id']}/undo").status_code == 404
    conflict = alice.post(f"{base}/{change['id']}/undo")  # open, not taken over
    assert conflict.status_code == 409 and conflict.json()["code"] == "suggestion_is_open"

    accounts_api.create("bob")
    bob = accounts_api.client("bob")
    assert bob.post(f"{base}/{change['id']}/undo").status_code == 404


@pytest.mark.req("REV-22")
def test_a_new_policy_gets_proposals_that_fill_its_target_structure(
    alice: TestClient, fake_llm: FakeLlm
) -> None:
    fake_llm.answers = [thesis_answer(proposals=[proposal(), proposal("Broader")])]
    pid = ok(alice.post("/api/policies", json={"name": "New", "thesis_md": "# T"}), 201)["id"]
    rid = ok(alice.post(f"/api/policies/{pid}/draft/review", json={}), 202)["id"]
    review = ok(alice.get(f"/api/reviews/{rid}"))
    proposals = [s for s in review["suggestions"] if s["kind"] == "proposal"]
    assert [(p["change"]["name"], p["content_md"]) for p in proposals] == [
        ("Focused", "Focused structure."),
        ("Broader", "Broader structure."),
    ]
    result = ok(alice.post(f"/api/reviews/{rid}/suggestions/{proposals[0]['id']}/take-over"))
    assert [(p["ticker"], p["target_pct"]) for p in result["draft"]["positions"]] == [
        ("VWRL", "85"),
        ("CASH", "15"),
    ]
    # The proposal can be activated as it is (POL-05)
    ok(alice.post(f"/api/policies/{pid}/draft/activate", json={}))
