"""End-to-end flows through the API (theses, policies, portfolios, imports, timeline)."""

import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from tests.fixtures import Accounts


@pytest.fixture
def alice(accounts_api: Accounts) -> TestClient:
    accounts_api.create("alice")
    return accounts_api.client("alice")


def ok(response, status: int = 200):  # type: ignore[no-untyped-def]
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def active_thesis(client: TestClient, body: dict[str, str]) -> dict[str, object]:
    """A new thesis with its first revision activated (THS-02)."""
    thesis: dict[str, object] = ok(client.post("/api/theses", json=body), 201)
    ok(client.post(f"/api/theses/{thesis['id']}/draft/activate", json={}))
    return thesis


def revise(client: TestClient, thesis_id: object, **body: str) -> dict[str, object]:
    """Draft, save and activate a new revision; returns the activated revision."""
    ok(client.post(f"/api/theses/{thesis_id}/draft"), 201)
    note = body.pop("change_note")
    ok(client.put(f"/api/theses/{thesis_id}/draft", json=body))
    revision: dict[str, object] = ok(
        client.post(f"/api/theses/{thesis_id}/draft/activate", json={"change_note": note})
    )
    return revision


def positions(*rows: tuple[str, int]) -> list[dict[str, object]]:
    return [
        {
            "ticker": t,
            "name": f"{t} name",
            "type": "ETF",
            "target_pct": target,
            "buy_threshold_pct": -20,
            "sell_threshold_pct": 20,
        }
        for t, target in rows
    ]


@pytest.mark.req("THS-01", "THS-02", "THS-03", "THS-08", "THS-10")
def test_thesis_flow(alice: TestClient, accounts_api: Accounts) -> None:
    thesis = ok(alice.post("/api/theses", json={"title": "T", "content_md": "a\nb\n"}), 201)
    tid = thesis["id"]
    assert thesis["revisions"][0]["is_draft"] is True
    listed = ok(alice.get("/api/theses"))[0]
    assert (listed["has_draft"], listed["active_revision_no"]) == (True, None)
    ok(alice.post(f"/api/theses/{tid}/draft/activate", json={}))

    draft = ok(alice.post(f"/api/theses/{tid}/draft"), 201)
    assert (draft["revision_no"], draft["is_draft"]) == (2, True)
    body = {"title": "T", "content_md": "a\nc\n", "status": "needs_adaptation"}
    ok(alice.put(f"/api/theses/{tid}/draft", json=body))
    missing_note = alice.post(f"/api/theses/{tid}/draft/activate", json={})
    assert missing_note.status_code == 422
    assert missing_note.json()["problems"][0]["path"] == "change_note"
    activated = ok(alice.post(f"/api/theses/{tid}/draft/activate", json={"change_note": "b→c"}))
    assert (activated["is_draft"], activated["status"]) == (False, "needs_adaptation")

    history = ok(alice.get(f"/api/theses/{tid}"))
    assert [(r["revision_no"], r["is_draft"]) for r in history["revisions"]] == [
        (1, False),
        (2, False),
    ]
    assert history["revisions"][1]["change_note"] == "b→c"
    revision = ok(alice.get(f"/api/theses/{tid}/revisions/1"))
    assert revision["content_md"] == "a\nb\n"
    diff = ok(alice.get(f"/api/theses/{tid}/diff?from_revision=1&to_revision=2"))
    assert "-b\n" in diff["unified_diff"] and "+c\n" in diff["unified_diff"]

    ok(alice.post(f"/api/theses/{tid}/draft"), 201)
    assert alice.put(f"/api/theses/{tid}/draft", json={**body, "status": "soft"}).status_code == 422
    assert alice.delete(f"/api/theses/{tid}/draft").status_code == 204

    ok(alice.put(f"/api/theses/{tid}/visibility", json={"visibility": "shared"}))
    accounts_api.create("bob")
    bob = accounts_api.client("bob")
    listed = ok(bob.get("/api/theses"))
    assert [(t["id"], t["is_own"]) for t in listed] == [(tid, False)]
    copy = ok(bob.post(f"/api/theses/{tid}/copy"), 201)
    assert copy["is_own"] is True and copy["visibility"] == "private"
    assert ok(bob.get(f"/api/theses/{copy['id']}/revisions/1"))["content_md"] == "a\nc\n"


@pytest.mark.req("POL-01", "POL-06", "POL-09", "POL-10", "POL-11", "POL-12")
def test_policy_flow(alice: TestClient) -> None:
    thesis = active_thesis(alice, {"title": "T", "content_md": ""})
    policy = ok(alice.post("/api/policies", json={"name": "core", "thesis_id": thesis["id"]}), 201)
    pid = policy["id"]
    draft = ok(
        alice.put(
            f"/api/policies/{pid}/draft",
            json={"positions": positions(("AAA", 60), ("BBB", 40))},
        )
    )
    assert draft["positions"][0]["sell_abs_pct"] == "72.0"
    v1 = ok(alice.post(f"/api/policies/{pid}/draft/activate", json={}))
    assert v1["label"] == "core-v1" and not v1["is_draft"]

    ok(alice.post(f"/api/policies/{pid}/draft"), 201)
    ok(
        alice.put(
            f"/api/policies/{pid}/draft",
            json={"positions": positions(("AAA", 50), ("CCC", 50))},
        )
    )
    missing_note = alice.post(f"/api/policies/{pid}/draft/activate", json={})
    assert missing_note.status_code == 422
    # NFR-10: with a code, so the frontend shows it in the user's language
    assert missing_note.json()["problems"] == [
        {
            "path": "change_note",
            "message": "A change note is required from v2 on",
            "code": "change_note_required_v2",
            "params": {},
        }
    ]
    ok(alice.post(f"/api/policies/{pid}/draft/activate", json={"change_note": "Swap BBB"}))
    diff = ok(alice.get(f"/api/policies/{pid}/compare?from_version=1&to_version=2"))
    assert [(c["ticker"], c["change"]) for c in diff["positions"]] == [
        ("AAA", "changed"),
        ("CCC", "added"),
        ("BBB", "removed"),
    ]
    assert diff["positions"][0]["fields"] == {"target_pct": ["60", "50"]}

    # A broken thesis revision: newer revision offered, warning only after adoption
    revise(alice, thesis["id"], title="T", content_md="", status="broken", change_note="broken")
    details = ok(alice.get(f"/api/policies/{pid}"))
    assert details["newer_thesis_revision_id"] is not None
    assert details["thesis_warning"] is False
    ok(alice.post(f"/api/policies/{pid}/adopt-thesis-revision"))
    ok(alice.post(f"/api/policies/{pid}/draft/activate", json={"change_note": "new thesis"}))
    details = ok(alice.get(f"/api/policies/{pid}"))
    assert details["thesis_warning"] is True
    assert [(v["label"], v["active_until"] is None) for v in details["versions"]] == [
        ("core-v1", False),
        ("core-v2", False),
        ("core-v3", True),
    ]
    assert ok(alice.get(f"/api/policies/{pid}/versions/3"))["thesis_status"] == "broken"
    assert ok(alice.get("/api/policies"))[0]["active_version_label"] == "core-v3"


@pytest.mark.req(
    "PTF-01", "PTF-03", "PTF-04", "PTF-05", "PTF-06", "CMP-01", "CMP-08", "CMP-09", "TL-03"
)
def test_portfolio_flow(alice: TestClient, accounts_api: Accounts) -> None:
    thesis = active_thesis(alice, {"title": "T", "content_md": ""})
    pids = []
    for name in ("core", "growth"):
        pid = ok(alice.post("/api/policies", json={"name": name, "thesis_id": thesis["id"]}), 201)[
            "id"
        ]
        ok(
            alice.put(
                f"/api/policies/{pid}/draft",
                json={"positions": positions(("AAA", 60), ("BBB", 40))},
            )
        )
        ok(alice.post(f"/api/policies/{pid}/draft/activate", json={}))
        pids.append(pid)
    accounts_api.clock.advance(hours=1)
    portfolio = ok(
        alice.post(
            "/api/portfolios",
            json={"name": "Main", "policy_id": pids[0], "default_contribution": "500"},
        ),
        201,
    )
    pfid = portfolio["id"]
    assert portfolio["active_version_label"] == "core-v1"
    ok(
        alice.put(
            f"/api/portfolios/{pfid}/settings",
            json={"default_contribution": 1000, "precise_amounts": True},
        )
    )
    saved = ok(
        alice.put(f"/api/portfolios/{pfid}/positions", json={"aaa": {"broker": "Southbank"}})
    )
    assert saved["brokers"] == {"AAA": "Southbank"}
    assert [(p["ticker"], p["broker"], p["whole_units"]) for p in saved["positions"]] == [
        ("AAA", "Southbank", True),
        ("BBB", None, True),
    ]

    prefill = ok(alice.get(f"/api/portfolios/{pfid}/prefill"))
    assert [(r["ticker"], r["units"], r["price"]) for r in prefill] == [
        ("AAA", "0", None),
        ("BBB", "0", None),
    ]
    assert (
        alice.post(
            f"/api/portfolios/{pfid}/snapshots", json={"values": [{"ticker": "AAA", "value": 1}]}
        ).status_code
        == 422  # units are needed (CMP-01)
    )
    snapshot = ok(
        alice.post(
            f"/api/portfolios/{pfid}/snapshots",
            json={
                "values": [
                    {"ticker": "AAA", "units": "7", "price": "100"},
                    {"ticker": "BBB", "units": 4, "value": 300},
                ]
            },
        ),
        201,
    )
    assert snapshot["currency"] == "CHF"
    assert [(r["units"], r["price"], r["value"]) for r in snapshot["rows"]] == [
        ("7", "100", "700.00"),
        ("4", "75", "300.00"),
    ]
    assert [(r["ticker"], Decimal(r["allocation_pct"]), r["status"]) for r in snapshot["rows"]] == [
        ("AAA", 70, "within_band"),
        ("BBB", 30, "below_buy_threshold"),  # buy threshold 40 x 0.8 = 32 %
    ]
    assert ok(alice.get(f"/api/snapshots/{snapshot['id']}"))["policy_version_label"] == "core-v1"

    accounts_api.clock.advance(hours=1)  # within the session idle timeout
    moved = ok(alice.post(f"/api/portfolios/{pfid}/reassign", json={"policy_id": pids[1]}))
    assert [a["policy_name"] for a in moved["assignments"]] == ["core", "growth"]
    accounts_api.clock.advance(hours=1)  # within the session idle timeout
    tiny = ok(
        alice.post(
            f"/api/portfolios/{pfid}/snapshots",
            json={"values": [{"ticker": "AAA", "units": "123.000000000000000001"}]},
        ),
        201,  # the price last entered (CMP-01)
    )
    # Every digit of the units, in plain notation (NFR-04): 18 decimals, like ETH
    assert tiny["rows"][0]["units"] == "123.000000000000000001"
    satoshi = ok(
        alice.post(
            f"/api/portfolios/{pfid}/snapshots",
            json={"values": [{"ticker": "AAA", "units": "0.00000001"}]},
        ),
        201,
    )
    assert satoshi["rows"][0]["units"] == "0.00000001"  # not 1E-8
    history = ok(alice.get(f"/api/portfolios/{pfid}/snapshots"))
    assert [s["policy_version_label"] for s in history] == ["growth-v1", "growth-v1", "core-v1"]

    overview = ok(alice.get("/api/portfolios"))
    assert overview[0]["latest_snapshot"]["policy_version_label"] == "growth-v1"
    events = ok(alice.get(f"/api/timeline?portfolio_id={pfid}&type=portfolio_assigned"))
    assert [e["summary"] for e in events] == [
        "Portfolio Main created with policy core (core-v1)",
        "Portfolio Main reassigned to policy growth (growth-v1)",
    ]
    assert ok(alice.post(f"/api/portfolios/{pfid}/archive"))["archived_at"] is not None


@pytest.mark.req("IMP-01", "IMP-02", "IMP-03", "IMP-06", "IMP-07", "IMP-09")
def test_import_flow(alice: TestClient) -> None:
    thesis_file = json.dumps({"schema_version": "1.0", "title": "Imported", "content_md": "x"})
    preview = ok(alice.post("/api/theses/import/preview", content=thesis_file))
    assert preview["creates_new_thesis"] is True
    revision = ok(alice.post("/api/theses/import", content=thesis_file), 201)
    assert (revision["revision_no"], revision["is_draft"]) == (1, True)
    tid = revision["thesis_id"]
    update = json.dumps(
        {"schema_version": "1.1", "title": "Imported", "content_md": "y", "change_note": "y"}
    )
    # Into the existing draft, then into a new draft; never activated by the import
    assert ok(alice.post(f"/api/theses/{tid}/import/preview", content=update))["revision_no"] == 1
    assert ok(alice.post(f"/api/theses/{tid}/import", content=update), 201)["revision_no"] == 1
    ok(alice.post(f"/api/theses/{tid}/draft/activate", json={}))
    assert ok(alice.post(f"/api/theses/{tid}/import/preview", content=update))["revision_no"] == 2
    draft = ok(alice.post(f"/api/theses/{tid}/import", content=update), 201)
    assert (draft["revision_no"], draft["is_draft"], draft["change_note"]) == (2, True, "y")
    ok(alice.post(f"/api/theses/{tid}/draft/activate", json={}))

    pid = ok(alice.post("/api/policies", json={"name": "core", "thesis_id": tid}), 201)["id"]
    structure = json.dumps({"schema_version": "1.0", "positions": positions(("AAA", 100))})
    diff = ok(alice.post(f"/api/policies/{pid}/import/preview", content=structure))
    assert diff["positions"] == [{"ticker": "AAA", "change": "added", "fields": {}}]
    draft = ok(alice.post(f"/api/policies/{pid}/import", content=structure), 201)
    assert draft["version_no"] == 1 and draft["positions"][0]["ticker"] == "AAA"
    ok(alice.post(f"/api/policies/{pid}/draft/activate", json={}))

    pfid = ok(alice.post("/api/portfolios", json={"name": "Main", "policy_id": pid}), 201)["id"]
    current = json.dumps({"schema_version": "1.0", "positions": [{"ticker": "AAA", "value": 5}]})
    assert (
        ok(alice.post(f"/api/portfolios/{pfid}/import/preview", content=current))["new_tickers"]
        == []
    )
    snapshot = ok(alice.post(f"/api/portfolios/{pfid}/import", content=current), 201)
    assert snapshot["source"] == "import"

    broken = alice.post(
        f"/api/portfolios/{pfid}/import",
        content='{"schema_version": "1.0", "positions": [{"value": 1}]}',
    )
    assert broken.status_code == 422
    # The library's English text stays inside the translated frame (NFR-10)
    assert broken.json()["problems"] == [
        {
            "path": "$.positions[0]",
            "message": "'ticker' is a required property",
            "code": "schema_error",
            "params": {"detail": "'ticker' is a required property"},
        }
    ]
    schema = ok(alice.get("/api/schemas/target-structure"))
    assert schema["$id"] == "target-structure.v1.schema.json"
    assert alice.get("/api/schemas/unknown").status_code == 404
    assert [a["ticker"] for a in ok(alice.get("/api/assets"))] == ["AAA"]


@pytest.mark.req("RB-02", "RB-03", "RB-11", "RB-12", "RB-13", "RB-16", "RB-17", "RB-20", "RB-22")
def test_rebalance_flow(alice: TestClient) -> None:
    thesis = active_thesis(alice, {"title": "T", "content_md": ""})
    pid = ok(alice.post("/api/policies", json={"name": "core", "thesis_id": thesis["id"]}), 201)[
        "id"
    ]
    ok(
        alice.put(
            f"/api/policies/{pid}/draft",
            json={"positions": positions(("AAA", 50), ("BBB", 50))},
        )
    )
    ok(alice.post(f"/api/policies/{pid}/draft/activate", json={}))
    pfid = ok(alice.post("/api/portfolios", json={"name": "Main", "policy_id": pid}), 201)["id"]
    assert alice.get(f"/api/portfolios/{pfid}/rebalance").status_code == 409  # no snapshot yet
    ok(
        alice.put(
            f"/api/portfolios/{pfid}/positions",
            json={"AAA": {"broker": "Southbank"}, "BBB": {"broker": "Northbank"}},
        )
    )
    ok(
        alice.post(
            f"/api/portfolios/{pfid}/snapshots",
            json={
                "values": [
                    {"ticker": "AAA", "units": 70, "price": 10},
                    {"ticker": "BBB", "units": 30, "price": 10},
                ]
            },
        ),
        201,
    )

    plan = ok(alice.get(f"/api/portfolios/{pfid}/rebalance?contribution=0"))
    assert plan["policy_version_label"] == "core-v1"
    assert [
        (i["phase"], i["ticker"], i["action"], i["broker"], Decimal(i["units"]), i["whole_units"])
        for i in plan["instructions"]
    ] == [
        ("1B", "AAA", "Sell", "Southbank", 15, True),  # RB-24: 150 at 10
        ("3", "BBB", "Buy (Below Target)", "Northbank", 15, True),
    ]
    assert Decimal(plan["result"]["total_sell_proceeds"]) == 150  # to midband 55 %
    assert {k: Decimal(v) for k, v in plan["result"]["buys_by_broker"].items()} == {
        "Northbank": 150
    }
    aaa = plan["result"]["positions"][0]
    assert (aaa["phase1_action"], Decimal(aaa["allocation_after_pct"])) == ("Sell", 55)
    assert ok(alice.get(f"/api/portfolios/{pfid}/rebalances")) == []  # preview stores nothing

    record = ok(
        alice.post(
            f"/api/portfolios/{pfid}/rebalances",
            json={
                "snapshot_id": plan["snapshot_id"],
                "contribution": "0",
                "policy_version_id": plan["policy_version_id"],
                "executed": [{"phase": "3", "ticker": "BBB", "amount": "141.50", "units": 14}],
            },
        ),
        201,
    )
    assert [
        (
            a["ticker"],
            Decimal(a["calculated_units"]),
            Decimal(a["executed_units"]),
            Decimal(a["calculated_amount"]),
            Decimal(a["executed_amount"]),
            a["whole_units"],
        )
        for a in record["actions"]
    ] == [("AAA", 15, 15, 150, 150, True), ("BBB", 15, 14, 150, Decimal("141.50"), True)]
    assert ok(alice.get(f"/api/rebalances/{record['id']}")) == record
    assert [r["id"] for r in ok(alice.get(f"/api/portfolios/{pfid}/rebalances"))] == [record["id"]]
    result = ok(alice.get(f"/api/snapshots/{record['result_snapshot_id']}"))
    # RB-17: the executed units at the input snapshot's price
    assert {r["ticker"]: (Decimal(r["units"]), Decimal(r["value"])) for r in result["rows"]} == {
        "AAA": (55, 550),
        "BBB": (44, 440),
    }

    # RB-22: from AAA 550 / BBB 440, F = 590; both are above target 295
    withdraw = ok(alice.get(f"/api/portfolios/{pfid}/rebalance?contribution=0&withdrawal=400"))
    assert Decimal(withdraw["withdrawal"]) == 400
    assert Decimal(withdraw["result"]["total_withdrawal_sells"]) == 400
    assert {(i["phase"], i["action"]) for i in withdraw["instructions"]} == {
        ("3", "Sell (Withdrawal)")
    }
    too_much = alice.get(f"/api/portfolios/{pfid}/rebalance?contribution=0&withdrawal=1000")
    assert too_much.status_code == 422

    cycles = ok(
        alice.post(
            f"/api/portfolios/{pfid}/simulate",
            json={"cycles": 3, "contribution": 100, "withdrawal": 50},
        )
    )
    assert len(cycles) == 3
    assert Decimal(cycles[2]["total_value_after"]) == Decimal(1140)  # 990 + 3 x (100 - 50)
    assert alice.post(f"/api/portfolios/{pfid}/simulate", json={"cycles": 0}).status_code == 422


@pytest.mark.req("TL-02", "POL-10", "POL-11")
def test_lookups_for_timeline_details_and_warnings(alice: TestClient) -> None:
    thesis = active_thesis(alice, {"title": "T", "content_md": "v1"})
    pid = ok(alice.post("/api/policies", json={"name": "core", "thesis_id": thesis["id"]}), 201)[
        "id"
    ]
    ok(
        alice.put(
            f"/api/policies/{pid}/draft",
            json={"positions": positions(("AAA", 100))},
        )
    )
    ok(alice.post(f"/api/policies/{pid}/draft/activate", json={}))
    summary = ok(alice.get("/api/policies"))[0]
    assert (summary["thesis_warning"], summary["newer_thesis_revision_id"]) == (False, None)

    revision = revise(
        alice, thesis["id"], title="T", content_md="v2", status="broken", change_note="broken"
    )
    events = ok(alice.get("/api/timeline"))
    activated = next(e for e in events if e["type"] == "policy_activated")
    revised = next(e for e in events if e["type"] == "thesis_revised")

    version = ok(alice.get(f"/api/policy-versions/{activated['policy_version_id']}"))
    assert (version["policy_id"], version["policy_name"], version["label"]) == (
        pid,
        "core",
        "core-v1",
    )
    assert version["positions"][0]["ticker"] == "AAA"
    found = ok(alice.get(f"/api/thesis-revisions/{revised['thesis_revision_id']}"))
    assert (found["thesis_id"], found["revision_no"], found["content_md"]) == (
        thesis["id"],
        2,
        "v2",
    )
    assert found["id"] == revision["id"]

    summary = ok(alice.get("/api/policies"))[0]
    assert summary["newer_thesis_revision_id"] == revision["id"]
    ok(alice.post(f"/api/policies/{pid}/adopt-thesis-revision"))
    ok(alice.post(f"/api/policies/{pid}/draft/activate", json={"change_note": "adopt"}))
    assert ok(alice.get("/api/policies"))[0]["thesis_warning"] is True


@pytest.mark.req("IMP-10", "RB-19")
def test_exports_and_rebalance_result(alice: TestClient) -> None:
    thesis = active_thesis(alice, {"title": "T", "content_md": "body"})
    pid = ok(
        alice.post("/api/policies", json={"name": "core / 2026", "thesis_id": thesis["id"]}), 201
    )["id"]
    ok(
        alice.put(
            f"/api/policies/{pid}/draft",
            json={"positions": positions(("AAA", 50), ("BBB", 50))},
        )
    )
    ok(alice.post(f"/api/policies/{pid}/draft/activate", json={}))
    pfid = ok(alice.post("/api/portfolios", json={"name": "Main", "policy_id": pid}), 201)["id"]
    ok(
        alice.put(
            f"/api/portfolios/{pfid}/positions",
            json={"AAA": {"broker": "Southbank"}, "BBB": {"broker": "Northbank"}},
        )
    )
    snapshot = ok(
        alice.post(
            f"/api/portfolios/{pfid}/snapshots",
            json={
                "values": [
                    {"ticker": "AAA", "units": 7, "price": 100},
                    {"ticker": "BBB", "units": 3, "price": 100},
                ]
            },
        ),
        201,
    )

    exported = alice.get(f"/api/theses/{thesis['id']}/revisions/1/export")
    assert (
        exported.headers["content-disposition"]
        == f'attachment; filename="thesis-{thesis["id"]}-r1.json"'
    )
    assert exported.json()["content_md"] == "body"
    version = alice.get(f"/api/policies/{pid}/versions/1/export")
    assert version.headers["content-disposition"] == 'attachment; filename="core___2026-v1.json"'
    assert [p["ticker"] for p in version.json()["positions"]] == ["AAA", "BBB"]
    values = alice.get(f"/api/snapshots/{snapshot['id']}/export").json()
    assert values["schema_version"] == "1.3"
    assert values["positions"][0] == {
        "ticker": "AAA",
        "units": 7,
        "price": 100,
        "value": 700.00,
        "name": "AAA name",
        "type": "ETF",
    }
    assert alice.get(f"/api/theses/{thesis['id']}/revisions/9/export").status_code == 404
    assert alice.get(f"/api/policies/{pid}/versions/9/export").status_code == 404

    plan = ok(alice.get(f"/api/portfolios/{pfid}/rebalance?contribution=0"))
    record = ok(
        alice.post(
            f"/api/portfolios/{pfid}/rebalances",
            json={
                "snapshot_id": plan["snapshot_id"],
                "contribution": "0",
                "policy_version_id": plan["policy_version_id"],
            },
        ),
        201,
    )
    # brokers changed afterwards; the report keeps the brokers of the rebalance
    ok(
        alice.put(
            f"/api/portfolios/{pfid}/positions",
            json={"AAA": {"broker": "Other"}, "BBB": {"broker": "Other"}},
        )
    )
    result = ok(alice.get(f"/api/rebalances/{record['id']}/result"))
    assert result == plan["result"]
