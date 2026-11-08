"""Drafts through the API: discard, change note and the marks of activated versions
(POL-14, POL-16, POL-17, REV-11, REV-20)."""

import pytest
from fastapi.testclient import TestClient

from tests.fixtures import Accounts
from tests.reviews.answers import answer

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
    accounts_api.create("alice")
    client: TestClient = accounts_api.client("alice")
    return client


def _policy(client: TestClient, name: str) -> int:
    policy = ok(client.post("/api/policies", json={"name": name, "thesis_md": "# Thesis"}), 201)
    ok(client.put(f"/api/policies/{policy['id']}/draft", json={"positions": POSITIONS}))
    return int(policy["id"])


def _manual_review(client: TestClient, pid: int) -> None:
    prompt = ok(client.get(f"/api/policies/{pid}/draft/review-prompt"))
    body = {"answer": answer(prompt_id=prompt["prompt_id"])}
    ok(client.post(f"/api/policies/{pid}/draft/review/manual", json=body), 201)


def _marks(client: TestClient) -> dict[str, str | None]:
    return {p["name"]: p["mark"] for p in ok(client.get("/api/policies"))}


@pytest.mark.req("REV-11", "REV-20", "POL-17")
def test_activation_never_blocks_and_marks_versions_without_a_matching_review(
    alice: TestClient,
) -> None:
    # Not reviewed
    none = _policy(alice, "none")
    ok(alice.post(f"/api/policies/{none}/draft/activate", json={}))
    # Reviewed, then changed: the review no longer matches
    changed = _policy(alice, "changed")
    _manual_review(alice, changed)
    draft = ok(alice.get(f"/api/policies/{changed}"))["versions"][0]
    assert draft["review"]["outdated"] is False
    thesis = {"title": "changed", "content_md": "# Other"}
    ok(alice.put(f"/api/policies/{changed}/draft", json={"positions": POSITIONS, "thesis": thesis}))
    draft = ok(alice.get(f"/api/policies/{changed}"))["versions"][0]
    assert draft["review"]["outdated"] is True
    ok(alice.post(f"/api/policies/{changed}/draft/activate", json={}))
    # Reviewed and matching
    matching = _policy(alice, "matching")
    _manual_review(alice, matching)
    ok(alice.post(f"/api/policies/{matching}/draft/activate", json={}))

    assert _marks(alice) == {
        "changed": "review_did_not_match",
        "matching": None,
        "none": "not_reviewed",
    }
    policy = ok(alice.get(f"/api/policies/{changed}"))
    assert policy["mark"] == "review_did_not_match"
    assert policy["versions"][0]["mark"] == "review_did_not_match"
    # The confirmed review is kept with the version, and matches nothing any more
    assert policy["versions"][0]["review"]["outdated"] is False
    version = ok(alice.get(f"/api/policies/{none}/versions/1"))
    assert version["mark"] == "not_reviewed" and version["review"] is None

    # A later version activated with a matching review has no mark
    ok(alice.post(f"/api/policies/{none}/draft"), 201)
    _manual_review(alice, none)
    ok(alice.post(f"/api/policies/{none}/draft/activate", json={"change_note": "Reviewed"}))
    assert _marks(alice)["none"] is None
    versions = ok(alice.get(f"/api/policies/{none}"))["versions"]
    assert [v["mark"] for v in versions] == ["not_reviewed", None]


@pytest.mark.req("POL-16")
def test_discarding_a_draft(alice: TestClient) -> None:
    pid = _policy(alice, "core")
    ok(alice.post(f"/api/policies/{pid}/draft/activate", json={}))
    ok(alice.post(f"/api/policies/{pid}/draft"), 201)
    _manual_review(alice, pid)
    # Back to the active version
    assert ok(alice.delete(f"/api/policies/{pid}/draft")) == {"policy_deleted": False}
    versions = ok(alice.get(f"/api/policies/{pid}"))["versions"]
    assert [(v["version_no"], v["is_draft"]) for v in versions] == [(1, False)]
    ok(alice.delete(f"/api/policies/{pid}/draft"), 404)
    # A policy never activated goes with its draft
    new = _policy(alice, "new")
    assert ok(alice.delete(f"/api/policies/{new}/draft")) == {"policy_deleted": True}
    ok(alice.get(f"/api/policies/{new}"), 404)
    assert [p["name"] for p in ok(alice.get("/api/policies"))] == ["core"]


@pytest.mark.req("POL-14", "POL-17", "POL-06")
def test_the_change_note_is_saved_and_used_at_activation(alice: TestClient) -> None:
    pid = _policy(alice, "core")
    ok(alice.post(f"/api/policies/{pid}/draft/activate", json={}))
    ok(alice.post(f"/api/policies/{pid}/draft"), 201)
    # From v2 on a note is needed
    ok(alice.post(f"/api/policies/{pid}/draft/activate", json={}), 422)
    saved = ok(alice.put(f"/api/policies/{pid}/draft/change-note", json={"change_note": " Wider "}))
    assert (saved["version_no"], saved["change_note"], saved["is_draft"]) == (2, "Wider", True)
    version = ok(alice.post(f"/api/policies/{pid}/draft/activate", json={}))
    assert version["change_note"] == "Wider"
    ok(alice.put(f"/api/policies/{pid}/draft/change-note", json={"change_note": "x"}), 404)


@pytest.mark.req("POL-22", "REV-09", "REV-21")
def test_a_draft_is_reviewed_on_its_own_and_its_changes_are_flagged(alice: TestClient) -> None:
    pid = _policy(alice, "core")
    ok(alice.post(f"/api/policies/{pid}/draft/activate", json={}))
    ok(alice.post(f"/api/policies/{pid}/draft"), 201)
    draft = ok(alice.get(f"/api/policies/{pid}"))["draft"]
    assert draft["changed"] is False  # still the same content as the active version

    _manual_review(alice, pid)
    policy = ok(alice.get(f"/api/policies/{pid}"))
    # The review belongs to the draft; the active version has none
    assert policy["draft"]["review"] is not None
    assert policy["latest_review"] is None

    ok(
        alice.put(
            f"/api/policies/{pid}/draft",
            json={"positions": POSITIONS, "thesis": {"title": "T", "content_md": "# Changed"}},
        )
    )
    assert ok(alice.get(f"/api/policies/{pid}"))["draft"]["changed"] is True
    # Running the review of the draft again replaces it; it does not add up
    _manual_review(alice, pid)
    log = ok(alice.get(f"/api/policies/{pid}/reviews"))
    assert [r["version_no"] for r in log] == []  # a draft's review is no part of the log yet
