"""JSON import (IMP-01 to IMP-08)."""

import json
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.fixtures import Factory
from yap.db.models import Asset, Policy, Snapshot
from yap.imports import importer
from yap.imports.models import ThesisFile
from yap.services import policies
from yap.services.common import ConflictError, NotFoundError, ValidationError


def thesis_json(**overrides: Any) -> str:
    data = {
        "schema_version": "1.0",
        "title": "Imported thesis",
        "visibility": "shared",
        "status": "intact",
        "content_md": "# Imported",
        **overrides,
    }
    return json.dumps({k: v for k, v in data.items() if v is not None})


def position(ticker: str, target: float, **overrides: Any) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "name": f"{ticker} name",
        "type": "ETF",
        "target_pct": target,
        "buy_threshold_pct": -20,
        "sell_threshold_pct": 25,
        **overrides,
    }


def target_json(positions: list[dict[str, Any]], **overrides: Any) -> str:
    return json.dumps({"schema_version": "1.0", "positions": positions, **overrides})


def current_json(positions: list[dict[str, Any]], version: str = "1.0") -> str:
    return json.dumps({"schema_version": version, "positions": positions})


def problems(err: pytest.ExceptionInfo[ValidationError]) -> list[str]:
    return [path for path, _ in err.value.problems]


# --- Thesis (IMP-01) ---------------------------------------------------------


@pytest.mark.req("IMP-01")
def test_thesis_import_without_selection_creates_a_new_policy(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    draft = importer.import_thesis(session, owner, factory.clock, thesis_json())
    assert (draft.version_no, draft.activated_at, draft.positions) == (1, None, [])
    assert (draft.policy.name, draft.thesis_title) == ("Imported thesis", "Imported thesis")
    # A second import of the same title collides with the policy name
    with pytest.raises(ConflictError):
        importer.import_thesis(session, owner, factory.clock, thesis_json())


@pytest.mark.req("IMP-01", "THS-04")
def test_thesis_import_with_selection_creates_a_draft_and_never_activates(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner)
    draft = importer.import_thesis(
        session,
        owner,
        factory.clock,
        thesis_json(status="needs_adaptation", change_note="Imported update"),
        selected_policy_id=policy.id,
    )
    assert (draft.version_no, draft.activated_at) == (2, None)
    # The status of older files is accepted and ignored: a thesis has none (THS-04)
    assert draft.thesis_title == "Imported thesis"
    assert not hasattr(draft, "thesis_status")
    assert [p.asset.ticker for p in draft.positions] == ["AAA", "BBB"]  # kept
    # A second import replaces the thesis of the same draft
    again = importer.import_thesis(
        session, owner, factory.clock, thesis_json(status="broken", title="Again"), policy.id
    )
    assert (again.id, again.thesis_title) == (draft.id, "Again")
    assert [v.version_no for v in policy.versions] == [1, 2]


@pytest.mark.req("IMP-01")
def test_selected_policy_must_be_own(session: Session, factory: Factory) -> None:
    owner, other = factory.investor(), factory.investor()
    foreign = factory.active_policy(other)
    with pytest.raises(NotFoundError):
        importer.import_thesis(session, owner, factory.clock, thesis_json(), foreign.id)


# --- Schema validation (IMP-04, IMP-06) --------------------------------------


@pytest.mark.req("IMP-04", "IMP-06")
@pytest.mark.parametrize(
    ("text", "path", "message"),
    [
        ("{not json", "$", "Invalid JSON"),
        (thesis_json(schema_version="2.0"), "$.schema_version", "not supported"),
        (thesis_json(schema_version=None), "$", "'schema_version' is a required property"),
        (thesis_json(status="soft"), "$.status", "is not valid under any of"),
        (thesis_json(unknown=1), "$", "Additional properties are not allowed"),
        (thesis_json(title=" "), "$.title", "does not match"),
    ],
)
def test_schema_errors_have_json_paths(text: str, path: str, message: str) -> None:
    with pytest.raises(ValidationError) as err:
        importer.parse(text, ThesisFile)
    assert err.value.problems[0][0] == path
    assert message in str(err.value.problems[0][1])


@pytest.mark.req("IMP-04")
def test_same_major_version_is_accepted() -> None:
    assert importer.parse(thesis_json(schema_version="1.7"), ThesisFile).schema_version == "1.7"


@pytest.mark.req("IMP-04")
def test_schema_reference_is_allowed() -> None:
    text = thesis_json(**{"$schema": "thesis.v1.schema.json"})
    assert importer.parse(text, ThesisFile).schema_ref == "thesis.v1.schema.json"


@pytest.mark.req("NFR-04")
def test_numbers_are_read_without_float_rounding(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner)
    text = (
        '{"schema_version":"1.0","positions":['
        + ",".join(
            json.dumps(position(t, 0)).replace('"target_pct": 0', f'"target_pct": {v}')
            for t, v in (("A", "33.3333333333333333"), ("B", "66.6666666666666667"))
        )
        + "]}"
    )
    draft = importer.import_target_structure(session, owner, factory.clock, text, policy.id)
    assert draft.positions[0].target_pct == Decimal("33.3333333333333333")


# --- Target structure (IMP-02, IMP-05) ----------------------------------------


@pytest.mark.req("IMP-02")
def test_target_structure_creates_draft_of_selected_policy(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner)
    draft = importer.import_target_structure(
        session,
        owner,
        factory.clock,
        target_json(
            [
                position("xus", 70, rationale_md="US"),
                position("ETH", 30, type="crypto", exit=True),
            ],
            reinvest_sells=False,  # files before 1.2 have it; accepted and ignored (IMP-02)
        ),
        policy.id,
    )
    assert draft.version_no == 2 and draft.activated_at is None
    assert draft.thesis_md == policy.versions[0].thesis_md  # the thesis stays (IMP-02)
    assert [(p.asset.ticker, p.exit, p.rationale_md) for p in draft.positions] == [
        ("XUS", False, "US"),
        ("ETH", True, ""),
    ]


@pytest.mark.req("IMP-02")
def test_target_structure_replaces_existing_draft(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner)
    existing = policies.create_draft(session, owner, factory.clock, policy.id)
    draft = importer.import_target_structure(
        session, owner, factory.clock, target_json([position("NEW", 100)]), policy.id
    )
    assert draft.id == existing.id
    assert [p.asset.ticker for p in draft.positions] == ["NEW"]


@pytest.mark.req("IMP-02")
def test_target_structure_needs_own_policy(session: Session, factory: Factory) -> None:
    owner, other = factory.investor(), factory.investor()
    foreign = factory.active_policy(other)
    with pytest.raises(NotFoundError):
        importer.import_target_structure(
            session, owner, factory.clock, target_json([position("A", 100)]), foreign.id
        )


@pytest.mark.req("IMP-05", "IMP-06")
def test_business_rules_are_checked_with_paths(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner)
    text = target_json(
        [
            position("A", 50),
            position("a", 30),
            position("C1", 5, type="cash_buffer"),
            position("C2", 5, type="cash_buffer"),
        ]
    )
    with pytest.raises(ValidationError) as err:
        importer.import_target_structure(session, owner, factory.clock, text, policy.id)
    assert problems(err) == ["$.positions[1].ticker", "$.positions", "$.positions"]
    assert "sum to 90" in str(err.value.problems[1][1])


@pytest.mark.req("IMP-05", "POL-04")
def test_threshold_ranges_are_checked_by_the_schema(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner)
    text = target_json([position("A", 100, buy_threshold_pct=10, sell_threshold_pct=-1)])
    with pytest.raises(ValidationError) as err:
        importer.import_target_structure(session, owner, factory.clock, text, policy.id)
    assert problems(err) == [
        "$.positions[0].buy_threshold_pct",
        "$.positions[0].sell_threshold_pct",
    ]


@pytest.mark.req("IMP-06", "IMP-08")
def test_failed_import_stores_nothing(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner)
    assets_before = session.scalar(select(func.count()).select_from(Asset))
    # NEW1 would be added to the catalog, but the type clash of AAA fails the import
    text = target_json([position("NEW1", 50), position("AAA", 50, type="crypto")])
    with pytest.raises(ValidationError) as err:
        importer.import_target_structure(session, owner, factory.clock, text, policy.id)
    assert problems(err) == ["$.positions[1].type"]
    assert session.scalar(select(func.count()).select_from(Asset)) == assets_before
    assert policies.get_draft(policy) is None


@pytest.mark.req("IMP-06")
@pytest.mark.parametrize(
    "error", [ValidationError.single("late", "positions"), RuntimeError("boom")]
)
def test_failure_after_first_write_rolls_back(
    session: Session, factory: Factory, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner)

    def failing_update(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr(policies, "update_draft", failing_update)
    with pytest.raises(type(error)) as err:
        importer.import_target_structure(
            session, owner, factory.clock, target_json([position("A", 100)]), policy.id
        )
    # The draft created before the failure is gone again
    session.refresh(policy)
    assert policies.get_draft(policy) is None
    if isinstance(error, ValidationError):
        assert err.value.problems == [("$.positions", "late")]  # type: ignore[attr-defined]


# --- Current structure (IMP-03, IMP-08) --------------------------------------


@pytest.mark.req("IMP-03", "IMP-08")
def test_current_structure_creates_snapshot(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    portfolio = factory.portfolio(owner)
    snapshot = importer.import_current_structure(
        session,
        owner,
        factory.clock,
        current_json(
            [
                {"ticker": "aaa", "value": 600},
                {"ticker": "OLD", "value": 50, "name": "Legacy", "type": "stock"},
            ]
        ),
        portfolio.id,
    )
    assert snapshot.source == "import"
    assert snapshot.taken_at == factory.clock.now()
    assert sorted((v.asset.ticker, v.value) for v in snapshot.values) == [
        ("AAA", 600),
        ("OLD", 50),
    ]


@pytest.mark.req("IMP-03", "IMP-06", "IMP-08")
def test_current_structure_errors(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    portfolio = factory.portfolio(owner)
    text = current_json(
        [
            {"ticker": "AAA", "value": -1},
            {"ticker": "UNKNOWN", "value": 1},
        ]
    )
    with pytest.raises(ValidationError) as err:
        importer.import_current_structure(session, owner, factory.clock, text, portfolio.id)
    assert problems(err) == ["$.positions[0].value"]
    text = current_json([{"ticker": "AAA", "value": 1}, {"ticker": "UNKNOWN", "value": 1}])
    with pytest.raises(ValidationError) as err:
        importer.import_current_structure(session, owner, factory.clock, text, portfolio.id)
    assert problems(err) == ["$.positions[1].ticker"]
    assert session.scalar(select(func.count()).select_from(Snapshot)) == 0


@pytest.mark.req("IMP-03", "CMP-01", "CMP-10")
def test_current_structure_with_units(session: Session, factory: Factory) -> None:
    """Since 1.3: units per position, with an optional price or value; without them, the
    price last entered."""
    owner = factory.investor()
    portfolio = factory.portfolio(owner)

    def run(positions: list[dict[str, Any]]) -> dict[str, tuple[Any, ...]]:
        factory.clock.advance(minutes=1)
        snapshot = importer.import_current_structure(
            session, owner, factory.clock, current_json(positions, "1.3"), portfolio.id
        )
        return {v.asset.ticker: (v.units, v.price, v.value) for v in snapshot.values}

    assert run(
        [{"ticker": "AAA", "units": 4, "price": 12.5}, {"ticker": "BBB", "units": 2, "value": 30}]
    ) == {
        "AAA": (Decimal(4), Decimal("12.5"), Decimal("50.00")),
        "BBB": (Decimal(2), Decimal(15), Decimal("30.00")),
    }
    assert run([{"ticker": "AAA", "units": 5}])["AAA"] == (
        Decimal(5),
        Decimal("12.5"),
        Decimal("62.50"),
    )
    with pytest.raises(ValidationError) as err:
        run([{"ticker": "AAA", "value": 5}, {"ticker": "BBB"}])
    assert [(p, m.code) for p, m in err.value.problems] == [
        ("$.positions[1]", "position_units_or_value")
    ]
    with pytest.raises(ValidationError) as err:
        run([{"ticker": "AAA", "value": 5}])  # 1.3 needs units
    assert [(p, m.code) for p, m in err.value.problems] == [
        ("$.positions[0].units", "units_required")
    ]


@pytest.mark.req("IMP-03")
def test_current_structure_needs_own_portfolio(session: Session, factory: Factory) -> None:
    owner, other = factory.investor(), factory.investor()
    foreign = factory.portfolio(other)
    with pytest.raises(NotFoundError):
        importer.import_current_structure(
            session, owner, factory.clock, current_json([]), foreign.id
        )


# --- Preview (IMP-07) ---------------------------------------------------------


@pytest.mark.req("IMP-07")
def test_preview_target_structure_shows_diff_and_stores_nothing(
    session: Session, factory: Factory
) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner)  # AAA 60, BBB 40
    diff = importer.preview_target_structure(
        session,
        owner,
        target_json(
            [position("AAA", 50, buy_threshold_pct=-20, sell_threshold_pct=20), position("NEW", 50)]
        ),
        policy.id,
    )
    assert [(c.ticker, c.change) for c in diff.positions] == [
        ("AAA", "changed"),
        ("NEW", "added"),
        ("BBB", "removed"),
    ]
    session.flush()
    assert policies.get_draft(policy) is None
    assert session.scalar(select(Asset).where(Asset.ticker == "NEW")) is None


@pytest.mark.req("IMP-07")
def test_preview_thesis(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policy = factory.active_policy(owner)
    new = importer.preview_thesis(session, owner, thesis_json())
    assert (new.creates_new_policy, new.version_no, new.title) == (True, 1, "Imported thesis")
    update = importer.preview_thesis(session, owner, thesis_json(), policy.id)
    assert (update.creates_new_policy, update.version_no) == (False, 2)
    policies.create_draft(session, owner, factory.clock, policy.id)
    # An existing draft is replaced, so the version number stays
    assert importer.preview_thesis(session, owner, thesis_json(), policy.id).version_no == 2
    assert session.scalar(select(func.count()).select_from(Policy)) == 1
    assert len(policy.versions) == 2


@pytest.mark.req("IMP-07")
def test_preview_current_structure(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    portfolio = factory.portfolio(owner)
    preview = importer.preview_current_structure(
        session,
        owner,
        current_json(
            [{"ticker": "aaa", "value": 1}, {"ticker": "N", "value": 2, "name": "N", "type": "ETF"}]
        ),
        portfolio.id,
    )
    assert preview.values == [("AAA", 1), ("N", 2)]
    assert preview.new_tickers == ["N"]
