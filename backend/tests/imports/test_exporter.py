"""Export in the import formats (IMP-10)."""

import json
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.orm import Session

from tests.fixtures import Factory, spec
from yap.db.models import Snapshot
from yap.imports import exporter, importer
from yap.services import policies, snapshots
from yap.services.snapshots import ValueSpec


@pytest.mark.req("IMP-10", "NFR-04")
def test_decimals_are_written_as_exact_numbers() -> None:
    text = exporter.dumps(
        {"a": Decimal("33.3333333333333333"), "b": [Decimal("10.50"), 1], "c": "x"}
    )
    assert '"a": 33.3333333333333333' in text
    assert "10.5" in text
    assert json.loads(text, parse_float=Decimal)["a"] == Decimal("33.3333333333333333")


@pytest.mark.req("IMP-10")
def test_thesis_round_trip(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    thesis = factory.thesis(owner, shared=True)
    revision = factory.revise_thesis(
        owner,
        thesis,
        title="Ünïcode title",
        content_md="# Body\n\n- point",
        status="broken",
        change_note="why",
    )
    text = exporter.thesis(revision)
    data = json.loads(text)
    assert data["$schema"] == "thesis.v1.schema.json"
    assert (data["title"], data["visibility"], data["status"], data["change_note"]) == (
        "Ünïcode title",
        "shared",
        "broken",
        "why",
    )
    imported = importer.import_thesis(session, factory.investor(), factory.clock, text)
    assert (imported.title, imported.content_md, imported.status) == (
        "Ünïcode title",
        "# Body\n\n- point",
        "broken",
    )
    # the first revision has no change note; the field is left out
    assert "change_note" not in json.loads(exporter.thesis(thesis.revisions[0]))


@pytest.mark.req("IMP-10")
def test_target_structure_round_trip(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    policy = factory.active_policy(
        owner,
        [
            spec("AAA", "66.6666666666666667", buy=-15, sell=40),
            spec("BBB", "33.3333333333333333", exit=True),
        ],
    )
    text = exporter.target_structure(policy.versions[0])
    other = factory.active_policy(owner, name="other")
    draft = importer.import_target_structure(session, owner, factory.clock, text, other.id)
    assert [
        (p.asset.ticker, p.target_pct, p.buy_threshold_pct, p.exit) for p in draft.positions
    ] == [
        ("AAA", Decimal("66.6666666666666667"), Decimal(-15), False),
        ("BBB", Decimal("33.3333333333333333"), Decimal(-20), True),
    ]
    assert policies.compare_versions(policy.versions[0], draft).positions == []


@pytest.mark.req("IMP-10")
def test_current_structure_round_trip(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    portfolio = factory.portfolio(owner)
    original = snapshots.create_snapshot(
        session,
        owner,
        factory.clock,
        portfolio.id,
        [ValueSpec("AAA", Decimal("1234.56")), ValueSpec("OLD", Decimal(7), "Old", "stock")],
    )
    text = exporter.current_structure(original)
    factory.clock.advance(minutes=1)
    copy = importer.import_current_structure(session, owner, factory.clock, text, portfolio.id)
    assert sorted((v.asset.ticker, v.value) for v in copy.values) == [
        ("AAA", Decimal("1234.56")),
        ("OLD", Decimal(7)),
    ]
    # Rows without units are written in the last version without units (IMP-03)
    assert json.loads(text)["schema_version"] == "1.2"


@pytest.mark.req("IMP-10", "CMP-10")
def test_current_structure_round_trip_with_units(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    portfolio = factory.portfolio(owner)
    original = snapshots.create_snapshot(
        session,
        owner,
        factory.clock,
        portfolio.id,
        [
            ValueSpec("AAA", units=Decimal("3.25"), price=Decimal("101.37")),
            ValueSpec("BBB", units=Decimal(3), value=Decimal(100)),  # price 33.33...
        ],
    )
    text = exporter.current_structure(original)
    assert json.loads(text)["schema_version"] == "1.3"
    factory.clock.advance(minutes=1)
    copy = importer.import_current_structure(session, owner, factory.clock, text, portfolio.id)

    def rows(s: Snapshot) -> list[tuple[Any, ...]]:
        return [(v.asset.ticker, v.units, v.price, v.value) for v in s.values]

    assert rows(copy) == rows(original)
