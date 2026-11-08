"""Data isolation over all API routes (NFR-03, test strategy §7).

Investor A owns data in every table. For every route, investor B calls it with A's
IDs and must get 404 (existence is not revealed), and so must an account with both
roles; the admin must get 403 on investment data, and unauthenticated calls get 401.
A route that is neither covered here nor listed as public makes this test fail.
"""

import json
import re
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.fixtures import Accounts, Factory
from yap.services import policies, snapshots
from yap.services.snapshots import ValueSpec

PUBLIC = {("GET", "/api/version"), ("GET", "/api/health"), ("POST", "/api/auth/login")}

# Routes without IDs; their isolation is tested by the list tests below
WITHOUT_IDS = {
    ("GET", "/api/auth/me"),
    ("POST", "/api/auth/logout"),
    ("POST", "/api/auth/password"),
    ("PUT", "/api/auth/language"),
    ("PUT", "/api/auth/time-zone"),
    ("GET", "/api/admin/accounts"),
    ("POST", "/api/admin/accounts"),
    ("GET", "/api/admin/ai-reviewers"),
    ("POST", "/api/admin/ai-reviewers"),
    ("GET", "/api/admin/price-providers"),
    ("GET", "/api/admin/price-update"),
    ("PUT", "/api/admin/price-update"),
    ("GET", "/api/price-sources"),
    ("POST", "/api/price-sources/lookup"),
    # Keyed by ticker, not by ID: each investor sets their own (PRC-05), tested separately
    ("PUT", "/api/price-sources/{ticker}"),
    ("POST", "/api/admin/price-providers"),
    ("GET", "/api/ai-reviewers"),
    ("PUT", "/api/ai-reviewers/choice"),
    ("GET", "/api/reviews/usage"),
    ("GET", "/api/assets"),
    ("POST", "/api/policies/import-thesis"),
    ("POST", "/api/policies/import-thesis/preview"),
    ("GET", "/api/policies"),
    ("POST", "/api/policies"),
    ("GET", "/api/portfolios"),
    ("POST", "/api/portfolios"),
    ("GET", "/api/timeline"),
    ("GET", "/api/schemas/{import_type}"),
}

POSITIONS = [
    {
        "ticker": "AAA",
        "name": "A",
        "type": "ETF",
        "target_pct": 100,
        "buy_threshold_pct": -10,
        "sell_threshold_pct": 10,
    }
]

# Valid bodies, so that a 404 is not masked by a 422 from body validation
BODIES: dict[tuple[str, str], Any] = {
    ("POST", "/api/policies/{policy_id}/import-thesis"): json.dumps(
        {"schema_version": "1.0", "title": "t", "content_md": "", "change_note": "x"}
    ),
    ("POST", "/api/policies/{policy_id}/import-thesis/preview"): json.dumps(
        {"schema_version": "1.0", "title": "t", "content_md": "", "change_note": "x"}
    ),
    ("PUT", "/api/policies/{policy_id}/draft"): {
        "positions": POSITIONS,
        "thesis": {"title": "t", "content_md": ""},
    },
    ("POST", "/api/policies/{policy_id}/draft/activate"): {"change_note": "x"},
    ("POST", "/api/policies/{policy_id}/import"): json.dumps(
        {"schema_version": "1.0", "positions": POSITIONS}
    ),
    ("POST", "/api/policies/{policy_id}/import/preview"): json.dumps(
        {"schema_version": "1.0", "positions": POSITIONS}
    ),
    ("PUT", "/api/portfolios/{portfolio_id}/settings"): {
        "default_contribution": 0,
        "precise_amounts": False,
    },
    ("PUT", "/api/portfolios/{portfolio_id}/positions"): {"AAA": {"broker": "x"}},
    ("POST", "/api/portfolios/{portfolio_id}/reassign"): {"policy_id": "{own_policy_id}"},
    ("POST", "/api/portfolios/{portfolio_id}/snapshots"): {
        "values": [{"ticker": "AAA", "units": 1, "price": 1}]
    },
    ("POST", "/api/portfolios/{portfolio_id}/import"): json.dumps(
        {"schema_version": "1.0", "positions": [{"ticker": "AAA", "value": 1}]}
    ),
    ("POST", "/api/portfolios/{portfolio_id}/import/preview"): json.dumps(
        {"schema_version": "1.0", "positions": [{"ticker": "AAA", "value": 1}]}
    ),
    ("POST", "/api/portfolios/{portfolio_id}/rebalances"): {
        "snapshot_id": "{snapshot_id}",
        "contribution": 0,
        "policy_version_id": "{active_version_id}",
        "executed": [],
    },
    ("POST", "/api/portfolios/{portfolio_id}/simulate"): {"cycles": 2},
    ("POST", "/api/admin/accounts/{account_id}/reset-password"): {
        "temporary_password": "temporary password 1"
    },
    ("PUT", "/api/admin/accounts/{account_id}/base-currency"): {"base_currency": "EUR"},
    ("PUT", "/api/admin/accounts/{account_id}/roles"): {
        "is_admin": True,
        "is_investor": True,
        "base_currency": "CHF",
    },
    ("POST", "/api/policies/{policy_id}/draft/review"): {"news_days": 30},
    ("POST", "/api/policies/{policy_id}/draft/review/manual"): {"answer": "{}"},
    ("PUT", "/api/admin/price-providers/{provider_id}"): {"provider": "yahoo"},
    ("POST", "/api/reviews/{review_id}/suggestions/{suggestion_id}/take-over"): None,
    ("POST", "/api/reviews/{review_id}/suggestions/{suggestion_id}/dismiss"): None,
    ("POST", "/api/reviews/{review_id}/suggestions/{suggestion_id}/undo"): None,
    ("PUT", "/api/admin/ai-reviewers/{reviewer_id}"): {
        "name": "x",
        "provider": "openai",
        "model": "m",
        "monthly_review_limit": 0,
    },
}

QUERIES: dict[tuple[str, str], str] = {
    ("GET", "/api/policies/{policy_id}/compare"): "?from_version=1&to_version=1",
}


def all_routes(app: Any) -> list[tuple[str, str]]:
    """All API routes and methods, from the OpenAPI description (the router keeps
    included routers nested, so app.routes does not list them)."""
    return sorted(
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    )


@pytest.fixture
def world(session: Session, factory: Factory, accounts_api: Accounts) -> dict[str, Any]:
    """A owns a policy with a draft and its reviews, and a portfolio with a snapshot."""
    a = accounts_api.create("alice")
    b = accounts_api.create("bob")
    accounts_api.create("root", admin=True, investor=False)
    accounts_api.create("both", admin=True, investor=True)
    reviewer = factory.ai_reviewer()
    policy = factory.active_policy(a)
    draft = policies.create_draft(session, a, factory.clock, policy.id)
    review = factory.review(a, draft)
    suggestion = factory.suggestion(review)
    portfolio = factory.portfolio(a, policy)
    snapshot = snapshots.create_snapshot(
        session, a, factory.clock, portfolio.id, [ValueSpec("AAA", Decimal(1))]
    )
    own_policy = factory.active_policy(b)  # B's own policy, e.g. as reassignment target
    from yap.services import rebalances

    record = rebalances.confirm(
        session,
        a,
        factory.clock,
        portfolio.id,
        snapshot_id=snapshot.id,
        contribution=Decimal(0),
        policy_version_id=policy.versions[0].id,
        executed=[],
    )
    session.commit()
    return {
        "policy_id": policy.id,
        "version_no": 1,
        "portfolio_id": portfolio.id,
        "snapshot_id": snapshot.id,
        "account_id": a.id,
        "own_policy_id": own_policy.id,
        "active_version_id": policy.versions[0].id,
        "version_id": policy.versions[0].id,
        "rebalance_id": record.id,
        "reviewer_id": reviewer.id,
        "provider_id": 1,  # the built-in exchange rate source
        "review_id": review.id,
        "suggestion_id": suggestion.id,
    }


def fill(template: Any, ids: dict[str, Any]) -> Any:
    if isinstance(template, str):
        match = re.fullmatch(r"\{(\w+)\}", template)
        if match:
            return ids[match.group(1)]
        return re.sub(r"\{(\w+)\}", lambda m: str(ids[m.group(1)]), template)
    if isinstance(template, dict):
        return {k: fill(v, ids) for k, v in template.items()}
    if isinstance(template, list):
        return [fill(v, ids) for v in template]
    return template


def call(client: TestClient, method: str, path: str, ids: dict[str, Any]):  # type: ignore[no-untyped-def]
    url = fill(path, ids) + QUERIES.get((method, path), "")
    body = BODIES.get((method, path))
    if isinstance(body, str):  # raw import file
        return client.request(method, url, content=fill(body, ids) if "{" not in body else body)
    return client.request(method, url, json=fill(body, ids) if body is not None else None)


def id_routes(app: Any) -> list[tuple[str, str]]:
    return [r for r in all_routes(app) if r not in PUBLIC and r not in WITHOUT_IDS]


@pytest.mark.req("NFR-03")
def test_every_route_is_covered(app: Any) -> None:
    # Guard against an empty route list, which would make every test here pass vacuously
    assert len(all_routes(app)) >= 50
    assert len(id_routes(app)) >= 30
    for method, path in id_routes(app):
        assert "{" in path, f"{method} {path} has no ID; add it to WITHOUT_IDS and test it"
        if method in ("POST", "PUT") and not path.endswith(
            (
                "/copy",
                "/draft",
                "/archive",
                "/deactivate",
                "/reactivate",
                "/test",
            )
        ):
            assert (method, path) in BODIES, f"Add an example body for {method} {path}"


@pytest.mark.req("NFR-03", "USR-04")
def test_other_investor_gets_404_for_everything(
    app: Any, accounts_api: Accounts, world: dict[str, Any]
) -> None:
    bob = accounts_api.client("bob")
    for method, path in id_routes(app):
        response = call(bob, method, path, world)
        expected = 403 if path.startswith("/api/admin") else 404
        assert response.status_code == expected, f"{method} {path}: {response.text}"


@pytest.mark.req("NFR-03", "USR-05")
def test_admin_gets_no_investment_data(
    app: Any, accounts_api: Accounts, world: dict[str, Any]
) -> None:
    root = accounts_api.client("root")
    for method, path in id_routes(app):
        if path.startswith("/api/admin"):
            continue
        response = call(root, method, path, world)
        assert response.status_code == 403, f"{method} {path}: {response.text}"
    for path in ("/api/policies", "/api/portfolios", "/api/timeline", "/api/assets"):
        assert root.get(path).status_code == 403, path


@pytest.mark.req("NFR-03", "USR-05", "USR-09")
def test_admin_who_is_also_investor_gets_404_for_other_investors_data(
    app: Any, accounts_api: Accounts, world: dict[str, Any]
) -> None:
    both = accounts_api.client("both")
    for method, path in id_routes(app):
        if path.startswith("/api/admin"):
            continue
        response = call(both, method, path, world)
        assert response.status_code == 404, f"{method} {path}: {response.text}"
    assert world["policy_id"] not in [p["id"] for p in both.get("/api/policies").json()]
    assert both.get("/api/portfolios").json() == []


@pytest.mark.req("NFR-03", "USR-01")
def test_unauthenticated_calls_are_rejected(
    app: Any, client: TestClient, world: dict[str, Any]
) -> None:
    for method, path in all_routes(app):
        if (method, path) in PUBLIC:
            continue
        response = call(client, method, path, {**world, "import_type": "thesis", "ticker": "AAA"})
        assert response.status_code == 401, f"{method} {path}: {response.text}"


@pytest.mark.req("NFR-03", "USR-04")
def test_lists_contain_only_own_data(accounts_api: Accounts, world: dict[str, Any]) -> None:
    bob = accounts_api.client("bob")
    assert world["policy_id"] not in [p["id"] for p in bob.get("/api/policies").json()]
    assert bob.get("/api/portfolios").json() == []
    bob_events = bob.get("/api/timeline").json()
    assert all("Portfolio" not in e["summary"] for e in bob_events)
    assert bob.get(f"/api/timeline?portfolio_id={world['portfolio_id']}").status_code == 404
    response = bob.post("/api/portfolios", json={"name": "x", "policy_id": world["policy_id"]})
    assert response.status_code == 404


@pytest.mark.req("NFR-03")
def test_unknown_ids_look_the_same_as_foreign_ids(
    accounts_api: Accounts, world: dict[str, Any]
) -> None:
    bob = accounts_api.client("bob")
    foreign = bob.get(f"/api/portfolios/{world['portfolio_id']}")
    missing = bob.get("/api/portfolios/999999")
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["detail"].replace(str(world["portfolio_id"]), "N") == missing.json()[
        "detail"
    ].replace("999999", "N")
