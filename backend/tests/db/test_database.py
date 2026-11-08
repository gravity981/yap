"""Migrations, column types and history protection."""

import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.fixtures import Factory
from yap.db.engine import make_engine
from yap.db.models import Base, Investor, Review
from yap.db.types import DecimalText, UTCDateTime
from yap.services import snapshots
from yap.services.snapshots import ValueSpec


@pytest.fixture
def engine(db_url: str) -> Engine:
    return make_engine(db_url)


@pytest.mark.req("NFR-09")
def test_migrations_match_models(engine: Engine) -> None:
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == []


@pytest.mark.req("NFR-09")
def test_migrations_downgrade_and_upgrade_again(db_url: str, engine: Engine) -> None:
    from alembic import command
    from alembic.config import Config

    from yap.db.migrate import MIGRATIONS, upgrade

    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    config.set_main_option("sqlalchemy.url", db_url)
    command.downgrade(config, "base")
    with engine.connect() as connection:
        tables = connection.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name != 'alembic_version'")
        ).all()
    assert tables == []
    upgrade(db_url)
    test_migrations_match_models(engine)


def _alembic(db_url: str):  # type: ignore[no-untyped-def]
    from alembic.config import Config

    from yap.db.migrate import MIGRATIONS

    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    config.set_main_option("sqlalchemy.url", db_url)
    return config


def _version_0002_with_history(db_url: str, engine: Engine) -> None:
    """A database at 0002 with a policy version that references a thesis revision."""
    from alembic import command

    command.downgrade(_alembic(db_url), "0002")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO investor (id, username, password_hash, role, base_currency, active,"
                " must_change_password, created_at) VALUES"
                " (1, 'alice', 'x', 'investor', 'CHF', 1, 0, '2026-01-01T00:00:00+00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO thesis (id, owner_id, visibility, created_at)"
                " VALUES (1, 1, 'private', '2026-01-01T00:00:00+00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO thesis_revision (id, thesis_id, revision_no, title, content_md,"
                " status, created_at) VALUES (1, 1, 1, 'T', '', 'intact',"
                " '2026-01-01T00:00:00+00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO policy (id, owner_id, name, created_at)"
                " VALUES (1, 1, 'core', '2026-01-01T00:00:00+00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO policy_version (id, policy_id, version_no, thesis_revision_id,"
                " reinvest_sells, created_at) VALUES (1, 1, 1, 1, 1,"
                " '2026-01-01T00:00:00+00:00')"
            )
        )


def _head(db_url: str) -> str:
    from alembic.script import ScriptDirectory

    return str(ScriptDirectory.from_config(_alembic(db_url)).get_current_head())


def _version(engine: Engine) -> str:
    with engine.connect() as connection:
        return str(connection.execute(text("SELECT version_num FROM alembic_version")).scalar())


@pytest.mark.req("NFR-09", "NFR-05")
def test_table_rebuilds_work_while_rows_reference_the_table(db_url: str, engine: Engine) -> None:
    """Rebuilding thesis_revision and investor (0003, 0004) and policy_version (0018) drops
    and recreates them, which foreign key checks would refuse while rows reference them."""
    from yap.db.migrate import upgrade

    _version_0002_with_history(db_url, engine)
    upgrade(db_url)
    assert _version(engine) == _head(db_url)
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        # No plan was configured, so there is no AI reviewer to keep (0007)
        assert connection.execute(text("SELECT ai_reviewer_id FROM investor")).scalar() is None
        thesis = connection.execute(text("SELECT thesis_title, thesis_md FROM policy_version"))
        assert tuple(thesis.one()) == ("T", "")  # from the pinned revision (0018)


@pytest.mark.req("NFR-09", "USR-09")
def test_roles_become_flags_and_back(db_url: str, engine: Engine) -> None:
    """0006: `role` becomes is_admin/is_investor; downgrading keeps an account with both
    roles an investor, so its data stays reachable."""
    from alembic import command

    from yap.db.migrate import upgrade

    command.downgrade(_alembic(db_url), "0005")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO investor (id, username, password_hash, role, base_currency,"
                " plan_code, active, must_change_password, created_at) VALUES"
                " (1, 'root', 'x', 'admin', NULL, NULL, 1, 0, '2026-01-01T00:00:00+00:00'),"
                " (2, 'alice', 'x', 'investor', 'CHF', 'free', 1, 0, '2026-01-01T00:00:00+00:00')"
            )
        )
    upgrade(db_url)
    query = text("SELECT username, is_admin, is_investor FROM investor ORDER BY id")
    with engine.begin() as connection:
        assert connection.execute(query).all() == [("root", 1, 0), ("alice", 0, 1)]
        connection.execute(text("UPDATE investor SET is_investor = 1 WHERE id = 2"))
        connection.execute(text("UPDATE investor SET is_admin = 1 WHERE id = 2"))
    command.downgrade(_alembic(db_url), "0005")
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT username, role FROM investor ORDER BY id")).all()
    assert rows == [("root", "admin"), ("alice", "investor")]


def _triggers(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'trigger' ORDER BY name")
        )
        return [row[0] for row in rows]


@pytest.mark.req("NFR-09", "REV-13", "USR-08")
def test_configured_plans_become_ai_reviewers_and_back(db_url: str, engine: Engine) -> None:
    """0007: a configured plan becomes a reviewer of that name, its investors and runs
    keep it; unconfigured plans are dropped. History triggers survive both ways."""
    from alembic import command

    from yap.db.migrate import upgrade

    at_head = _triggers(engine)
    command.downgrade(_alembic(db_url), "0006")
    created = "'2026-01-01T00:00:00+00:00'"
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE plan SET provider = 'openai', model = 'gpt-x', api_key_encrypted = x'00',"
                f" api_key_last4 = '1234', monthly_review_limit = 5, updated_at = {created}"
                " WHERE code = 'pro'"
            )
        )
        connection.execute(
            text(
                "INSERT INTO investor (id, username, password_hash, is_admin, is_investor,"
                " base_currency, plan_code, active, must_change_password, created_at) VALUES"
                f" (1, 'alice', 'x', 0, 1, 'CHF', 'pro', 1, 0, {created}),"
                f" (2, 'bob', 'x', 0, 1, 'CHF', 'free', 1, 0, {created})"
            )
        )
        connection.execute(
            text(
                "INSERT INTO review_run (investor_id, kind, plan_code, provider, model,"
                f" started_at) VALUES (1, 'thesis', 'pro', 'openai', 'gpt-x', {created})"
            )
        )
    upgrade(db_url)
    with engine.connect() as connection:
        reviewers = connection.execute(
            text("SELECT id, name, monthly_review_limit, enabled FROM ai_reviewer")
        ).all()
        assert [tuple(r)[1:] for r in reviewers] == [("pro", 5, 1)]
        pro = reviewers[0][0]
        choices = connection.execute(text("SELECT ai_reviewer_id FROM investor ORDER BY id"))
        assert [c[0] for c in choices] == [pro, None]
        assert connection.execute(text("SELECT ai_reviewer_id FROM review_run")).scalar() == pro
    assert _triggers(engine) == at_head

    command.downgrade(_alembic(db_url), "0006")
    with engine.connect() as connection:
        plans = connection.execute(
            text("SELECT code, provider, monthly_review_limit FROM plan ORDER BY code")
        ).all()
        assert [tuple(p) for p in plans] == [("free", None, 0), ("pro", "openai", 5)]
        choices = connection.execute(text("SELECT plan_code FROM investor ORDER BY id"))
        assert [c[0] for c in choices] == ["pro", "free"]
        assert connection.execute(text("SELECT plan_code FROM review_run")).scalar() == "pro"
    upgrade(db_url)
    assert _triggers(engine) == at_head


@pytest.mark.req("NFR-09", "NFR-05", "POL-03")
def test_set_aside_rebalances_become_withdrawals_and_back(
    db_url: str, engine: Engine, session: Session, factory: Factory
) -> None:
    """0009: a rebalance confirmed with "reinvest sell proceeds" off gets its phase 1B
    sell proceeds as withdrawal, which recalculates to the same result."""
    from alembic import command

    from yap.db.migrate import upgrade
    from yap.services import rebalances

    owner = factory.investor()
    portfolio = factory.portfolio(owner)  # AAA 60 %, BBB 40 %, sell threshold +20 %
    snapshots.create_snapshot(
        session,
        owner,
        factory.clock,
        portfolio.id,
        [ValueSpec("AAA", Decimal(800)), ValueSpec("BBB", Decimal(200))],
    )
    # Old rule with reinvest off: F = V - S, S = 800 - 0.66 F -> F = 200 / 0.34. The same
    # amount as withdrawal gives the same sells, so this record could have been either.
    old_final = Decimal(200) / Decimal("0.34")
    set_aside = Decimal(800) - Decimal("0.66") * old_final
    plan = rebalances.plan(
        session, owner, factory.clock, portfolio.id, contribution=Decimal(0), withdrawal=set_aside
    )
    assert plan.result.total_sell_proceeds == set_aside
    record = rebalances.confirm(
        session,
        owner,
        factory.clock,
        portfolio.id,
        snapshot_id=plan.snapshot.id,
        contribution=Decimal(0),
        withdrawal=set_aside,
        policy_version_id=plan.version.id,
        executed=[],
    )
    session.commit()
    session.close()
    at_head = _triggers(engine)

    command.downgrade(_alembic(db_url), "0008")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT reinvest_sells FROM rebalance")).scalar() == 0
        assert connection.execute(text("SELECT reinvest_sells FROM policy_version")).scalar() == 1
    upgrade(db_url)
    assert _triggers(engine) == at_head
    with engine.connect() as connection:
        withdrawal = connection.execute(text("SELECT withdrawal FROM rebalance")).scalar()
    assert Decimal(withdrawal) == set_aside
    result = rebalances.recalculate(session, owner, record.id)
    assert abs(result.total_value_after - old_final) < Decimal("0.000001")
    assert result.available_cash == 0 and result.total_withdrawal_sells == 0


@pytest.mark.req("NFR-09", "NFR-05", "REV-02")
def test_modified_reviews_keep_the_ai_values_and_their_changes_read_only(
    db_url: str, engine: Engine, session: Session, factory: Factory
) -> None:
    """0016: a review keeps the AI's scores and verdict; the investor's changes from before
    REV-10 was dropped move to legacy_modification, also for confirmed reviews."""
    from alembic import command

    from yap.db.migrate import upgrade
    from yap.services import reviews

    owner = factory.investor()
    modified = factory.policy_draft(owner, name="Modified").versions[0]
    plain = factory.policy_draft(owner, name="Plain").versions[0]
    factory.review(owner, modified, verdict="needs_adaptation")  # T1 = 14
    factory.review(owner, plain)
    session.commit()
    session.close()
    at_head = _triggers(engine)

    command.downgrade(_alembic(db_url), "0015")
    with engine.begin() as connection:
        # Below 0018 the thesis review belongs to the revision of the version's thesis
        rid = connection.execute(
            text(
                "SELECT r.id FROM review r JOIN thesis_revision t ON t.id = r.thesis_revision_id"
                " WHERE t.title = 'Core thesis' ORDER BY r.id LIMIT 1"
            )
        ).scalar()
        connection.execute(
            text(
                "UPDATE review SET modified = 1, verdict = 'intact',"
                " modification_note = 'Too strict' WHERE id = :id"
            ),
            {"id": rid},
        )
        connection.execute(
            text(
                "UPDATE review_aspect SET half_points = 19 WHERE review_id = :id AND aspect = 'T1'"
            ),
            {"id": rid},
        )
        # Confirmed: the drafts are activated
        for table in ("thesis_revision", "policy_version"):
            connection.execute(
                text(f"UPDATE {table} SET activated_at = '2026-01-02T00:00:00+00:00'")
            )
    upgrade(db_url)
    assert _triggers(engine) == at_head
    with Session(engine) as fresh:
        rows = {r.policy_version_id: r for r in fresh.scalars(select(Review))}
        review = rows[modified.id]
        assert review.verdict == "needs_adaptation"
        assert [a.half_points for a in review.aspects] == [14, 12, 16, 10, 14, 13]
        assert reviews.legacy_modification(review) == reviews.LegacyModification(
            note="Too strict", verdict="intact", scores={"T1": 9.5}
        )
        assert reviews.legacy_modification(rows[plain.id]) is None
    with (
        pytest.raises(IntegrityError, match="confirmed review is immutable"),
        engine.begin() as connection,
    ):
        connection.execute(text("UPDATE review SET legacy_modification = NULL"))

    command.downgrade(_alembic(db_url), "0015")
    with engine.connect() as connection:
        restored = connection.execute(
            text(
                "SELECT ai_verdict, verdict, modification_note, modified FROM review WHERE id = :id"
            ),
            {"id": rid},
        ).one()
        assert tuple(restored) == ("needs_adaptation", "intact", "Too strict", 1)
        t1 = connection.execute(
            text(
                "SELECT ai_half_points, half_points FROM review_aspect"
                " WHERE review_id = :id AND aspect = 'T1'"
            ),
            {"id": rid},
        ).one()
        assert tuple(t1) == (14, 19)
        others = connection.execute(
            text("SELECT count(*) FROM review_aspect WHERE half_points IS NOT NULL")
        ).scalar()
        assert others == 1
    upgrade(db_url)
    assert _triggers(engine) == at_head


@pytest.mark.req("NFR-09", "NFR-05", "POL-02", "THS-01")
def test_theses_merge_into_policy_versions_and_back(db_url: str, engine: Engine) -> None:
    """0018: versions take the thesis of the revision they pinned, its confirmed review
    becomes their thesis review, an unused thesis becomes a policy with a draft, and
    drafts of used theses and their reviews are dropped. Downgrading gives every policy a
    thesis again."""
    from alembic import command

    from yap.db.migrate import upgrade

    at_head = _triggers(engine)
    command.downgrade(_alembic(db_url), "0017")
    t0, t1 = "'2026-01-01T00:00:00+00:00'", "'2026-02-01T00:00:00+00:00'"
    review = (
        "INSERT INTO review (id, kind, thesis_revision_id, policy_version_id, started_by,"
        " state, verdict, scoring_version, provider, model, started_at, method)"
        " VALUES ({id}, '{kind}', {rev}, {ver}, 1, 'done', {verdict}, '2', 'openai', 'm',"
        f" {t0}, 'ai')"
    )
    with engine.begin() as connection:
        for sql in (
            "INSERT INTO investor (id, username, password_hash, is_admin, is_investor,"
            " base_currency, active, must_change_password, created_at, manual_review_default)"
            f" VALUES (1, 'alice', 'x', 0, 1, 'CHF', 1, 0, {t0}, 0)",
            f"INSERT INTO thesis VALUES (1, 1, 'shared', {t0}), (2, 1, 'private', {t0})",
            "INSERT INTO thesis_revision (id, thesis_id, revision_no, title, content_md,"
            " status, activated_at, created_at) VALUES"
            f" (1, 1, 1, 'Growth', 'used text', 'broken', NULL, {t0}),"
            f" (2, 1, 2, 'Growth', 'draft text', 'intact', NULL, {t1}),"
            f" (3, 2, 1, 'Spare idea', 'spare text', 'intact', NULL, {t0})",
            f"INSERT INTO policy (id, owner_id, name, created_at) VALUES (1, 1, 'core', {t0})",
            "INSERT INTO policy_version (id, policy_id, version_no, thesis_revision_id,"
            f" activated_at, created_at) VALUES (1, 1, 1, 1, NULL, {t0})",
            review.format(id=1, kind="thesis", rev=1, ver="NULL", verdict="'broken'"),
            review.format(id=2, kind="policy", rev="NULL", ver=1, verdict="NULL"),
            review.format(id=3, kind="thesis", rev=2, ver="NULL", verdict="'intact'"),
            "INSERT INTO review_aspect (review_id, aspect, half_points, reasoning_md)"
            " VALUES (1, 'T1', 14, 'r'), (3, 'T1', 10, 'r')",
            # Activated after the review rows, which the history triggers protect then
            f"UPDATE thesis_revision SET activated_at = {t0} WHERE id = 1",
            f"UPDATE policy_version SET activated_at = {t0} WHERE id = 1",
            "INSERT INTO timeline_event (investor_id, occurred_at, type, review_id,"
            f" thesis_revision_id, summary) VALUES (1, {t1}, 'thesis_review_confirmed', 1, 1,"
            " 'Thesis review of Growth revision 1')",
        ):
            connection.execute(text(sql))
    command.upgrade(_alembic(db_url), "0018")
    assert _triggers(engine) == at_head
    with engine.connect() as connection:
        versions = connection.execute(
            text(
                "SELECT p.name, v.version_no, v.thesis_title, v.thesis_md, v.thesis_status,"
                " v.activated_at IS NULL FROM policy_version v JOIN policy p"
                " ON p.id = v.policy_id ORDER BY p.id"
            )
        ).all()
        assert [tuple(v) for v in versions] == [
            ("core", 1, "Growth", "used text", "broken", 0),
            ("Spare idea", 1, "Spare idea", "spare text", "intact", 1),  # a new draft
        ]
        reviews = connection.execute(
            text("SELECT id, kind, policy_version_id FROM review ORDER BY id")
        ).all()
        assert [tuple(r) for r in reviews] == [(1, "thesis", 1), (2, "policy", 1)]
        assert connection.execute(text("SELECT review_id FROM timeline_event")).scalar() == 1
        tables = connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        assert "thesis" not in {t[0] for t in tables}
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text("UPDATE policy_version SET thesis_md = 'x' WHERE id = 1"))

    command.downgrade(_alembic(db_url), "0017")
    with engine.connect() as connection:
        revisions = connection.execute(
            text(
                "SELECT r.id, r.title, r.content_md, r.activated_at IS NULL FROM thesis_revision r"
                " JOIN thesis t ON t.id = r.thesis_id ORDER BY r.id"
            )
        ).all()
        assert [tuple(r)[1:] for r in revisions] == [
            ("Growth", "used text", 0),
            ("Spare idea", "spare text", 1),
        ]
        moved = connection.execute(
            text("SELECT thesis_revision_id, policy_version_id FROM review WHERE id = 1")
        ).one()
        assert tuple(moved) == (revisions[0][0], None)
    upgrade(db_url)
    assert _triggers(engine) == at_head


@pytest.mark.req("NFR-09", "NFR-05", "THS-04", "REV-06", "REV-17")
def test_the_thesis_status_gives_way_to_the_semaphore_and_back(db_url: str, engine: Engine) -> None:
    """0019: the thesis status is dropped, reviews get a verdict reason and may have no
    model; old reviews keep their kinds and verdicts. Downgrading sets the status from the
    thesis review and turns reviews of the whole policy into thesis reviews."""
    from alembic import command

    from yap.db.migrate import upgrade

    at_head = _triggers(engine)
    command.downgrade(_alembic(db_url), "0018")
    t0 = "'2026-01-01T00:00:00+00:00'"
    with engine.begin() as connection:
        for sql in (
            "INSERT INTO investor (id, username, password_hash, is_admin, is_investor,"
            " base_currency, active, must_change_password, created_at, manual_review_default)"
            f" VALUES (1, 'alice', 'x', 0, 1, 'CHF', 1, 0, {t0}, 0)",
            f"INSERT INTO policy (id, owner_id, name, created_at) VALUES (1, 1, 'core', {t0})",
            "INSERT INTO policy_version (id, policy_id, version_no, thesis_title, thesis_md,"
            " thesis_status, activated_at, created_at) VALUES"
            f" (1, 1, 1, 'Growth', 'text', 'broken', NULL, {t0}),"
            f" (2, 1, 2, 'Growth', 'text', 'broken', NULL, {t0})",
            "INSERT INTO review (id, kind, policy_version_id, started_by, state, verdict,"
            " scoring_version, provider, model, started_at, method) VALUES"
            f" (1, 'thesis', 1, 1, 'done', 'needs_adaptation', '2', 'openai', 'm', {t0}, 'ai')",
            "INSERT INTO review_aspect (review_id, aspect, half_points, reasoning_md)"
            " VALUES (1, 'T1', 14, 'r')",
            f"UPDATE policy_version SET activated_at = {t0} WHERE id = 1",
        ):
            connection.execute(text(sql))
    upgrade(db_url)
    assert _triggers(engine) == at_head
    with engine.connect() as connection:
        columns = {r[1] for r in connection.execute(text("PRAGMA table_info(policy_version)"))}
        assert "thesis_status" not in columns
        review = connection.execute(
            text("SELECT kind, verdict, verdict_reason, model FROM review WHERE id = 1")
        ).one()
        assert tuple(review) == ("thesis", "needs_adaptation", None, "m")
    with engine.begin() as connection:
        # A manual review of the whole policy on the draft v2, without a model
        connection.execute(
            text(
                "INSERT INTO review (id, kind, policy_version_id, started_by, state, verdict,"
                " verdict_reason, scoring_version, provider, model, started_at, method) VALUES"
                f" (2, 'full', 2, 1, 'done', 'good', 'fine', '3', 'manual', NULL, {t0},"
                " 'manual')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO review_aspect (review_id, aspect, half_points, reasoning_md)"
                " VALUES (2, 'T1', 16, 'r'), (2, 'P1', 12, 'r')"
            )
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text("UPDATE review SET verdict = 'good' WHERE id = 1"))

    command.downgrade(_alembic(db_url), "0018")
    with engine.connect() as connection:
        statuses = connection.execute(
            text("SELECT id, thesis_status FROM policy_version ORDER BY id")
        ).all()
        # v1 from its thesis review; v2 from its review of the whole policy, now a thesis one
        assert [tuple(r) for r in statuses] == [(1, "needs_adaptation"), (2, "intact")]
        reviews = connection.execute(
            text("SELECT id, kind, verdict, model FROM review ORDER BY id")
        ).all()
        assert [tuple(r) for r in reviews] == [
            (1, "thesis", "needs_adaptation", "m"),
            (2, "thesis", "intact", "unknown"),
        ]
        aspects = connection.execute(
            text("SELECT aspect FROM review_aspect WHERE review_id = 2")
        ).all()
        assert [a[0] for a in aspects] == ["T1"]
    upgrade(db_url)
    assert _triggers(engine) == at_head


@pytest.mark.req("NFR-09", "NFR-05", "REV-07", "REV-22")
def test_suggestions_get_a_change_and_a_state_and_lose_them_again(
    db_url: str, engine: Engine
) -> None:
    """0020: suggestions get what Take over applies, what it replaced and their state;
    older ones have no change and are open. The history triggers stay in place."""
    from alembic import command

    from yap.db.migrate import upgrade

    at_head = _triggers(engine)
    command.downgrade(_alembic(db_url), "0019")
    t0 = "'2026-01-01T00:00:00+00:00'"
    with engine.begin() as connection:
        for sql in (
            "INSERT INTO investor (id, username, password_hash, is_admin, is_investor,"
            " base_currency, active, must_change_password, created_at, manual_review_default)"
            f" VALUES (1, 'alice', 'x', 0, 1, 'CHF', 1, 0, {t0}, 0)",
            f"INSERT INTO policy (id, owner_id, name, created_at) VALUES (1, 1, 'core', {t0})",
            "INSERT INTO policy_version (id, policy_id, version_no, thesis_title, thesis_md,"
            f" activated_at, created_at) VALUES (1, 1, 1, 'Growth', 'text', NULL, {t0})",
            "INSERT INTO review (id, kind, policy_version_id, started_by, state, verdict,"
            " scoring_version, provider, model, started_at, method) VALUES"
            f" (1, 'full', 1, 1, 'done', 'good', '3', 'openai', 'm', {t0}, 'ai')",
            "INSERT INTO review_suggestion (id, review_id, kind, content_md)"
            " VALUES (1, 1, 'thesis_text', 'Add a horizon.')",
            f"UPDATE policy_version SET activated_at = {t0} WHERE id = 1",
        ):
            connection.execute(text(sql))
    upgrade(db_url)
    assert _triggers(engine) == at_head
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT kind, change, previous, state FROM review_suggestion WHERE id = 1")
        ).one()
        assert tuple(row) == ("thesis_text", None, None, "open")
    # A suggestion of a confirmed review stays as it is (REV-11)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text("UPDATE review_suggestion SET state = 'dismissed'"))

    command.downgrade(_alembic(db_url), "0019")
    with engine.connect() as connection:
        columns = {r[1] for r in connection.execute(text("PRAGMA table_info(review_suggestion)"))}
        assert not columns & {"change", "previous", "state"}
        assert connection.execute(text("SELECT content_md FROM review_suggestion")).scalar() == (
            "Add a horizon."
        )
    upgrade(db_url)
    assert _triggers(engine) == at_head


def _trigger_sql(engine: Engine) -> list[tuple[str, str]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT name, sql FROM sqlite_master WHERE type = 'trigger' ORDER BY name")
        )
        return [(row[0], row[1]) for row in rows]


@pytest.mark.req("NFR-09", "NFR-05", "REV-09", "REV-11", "REV-20")
def test_reviews_get_fingerprints_and_confirmation_times_and_versions_marks(
    db_url: str, engine: Engine
) -> None:
    """0021: reviews of activated versions are confirmed at the activation time; versions
    activated without a finished review are marked not reviewed; the triggers stay."""
    from alembic import command

    from yap.db.migrate import upgrade

    at_head = _trigger_sql(engine)
    command.downgrade(_alembic(db_url), "0020")
    t0 = "'2026-01-01T00:00:00.000000+00:00'"
    t1 = "'2026-02-01T00:00:00.000000+00:00'"
    with engine.begin() as connection:
        for sql in (
            "INSERT INTO investor (id, username, password_hash, is_admin, is_investor,"
            " base_currency, active, must_change_password, created_at, manual_review_default)"
            f" VALUES (1, 'alice', 'x', 0, 1, 'CHF', 1, 0, {t0}, 0)",
            f"INSERT INTO policy (id, owner_id, name, created_at) VALUES (1, 1, 'core', {t0})",
            # v1 activated without a review, v2 with one, v3 a draft with one
            *(
                "INSERT INTO policy_version (id, policy_id, version_no, thesis_title,"
                f" thesis_md, activated_at, created_at) VALUES ({n}, 1, {n}, 'T', 'text',"
                f" NULL, {t0})"
                for n in (1, 2, 3)
            ),
            *(
                "INSERT INTO review (id, kind, policy_version_id, started_by, state, verdict,"
                " scoring_version, provider, model, started_at, method) VALUES"
                f" ({n}, 'full', {n}, 1, 'done', 'good', '3', 'openai', 'm', {t0}, 'ai')"
                for n in (2, 3)
            ),
            f"UPDATE policy_version SET activated_at = {t0} WHERE id = 1",
            f"UPDATE policy_version SET activated_at = {t1} WHERE id = 2",
        ):
            connection.execute(text(sql))
    upgrade(db_url)
    assert _trigger_sql(engine) == at_head
    with engine.connect() as connection:
        marks = connection.execute(text("SELECT id, mark FROM policy_version ORDER BY id")).all()
        assert [tuple(r) for r in marks] == [(1, "not_reviewed"), (2, None), (3, None)]
        saved = connection.execute(
            text("SELECT id, saved_at, fingerprint FROM review ORDER BY id")
        ).all()
        assert [tuple(r) for r in saved] == [(2, t1.strip("'"), None), (3, None, None)]
    # History stays protected after the backfill
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text("UPDATE policy_version SET mark = NULL WHERE id = 1"))
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text("UPDATE review SET saved_at = NULL WHERE id = 2"))

    command.downgrade(_alembic(db_url), "0020")
    with engine.connect() as connection:
        version_columns = {
            r[1] for r in connection.execute(text("PRAGMA table_info(policy_version)"))
        }
        review_columns = {r[1] for r in connection.execute(text("PRAGMA table_info(review)"))}
        assert "mark" not in version_columns
        assert not review_columns & {"fingerprint", "saved_at"}
    upgrade(db_url)
    assert _trigger_sql(engine) == at_head


@pytest.mark.req("NFR-09", "NFR-05", "PTF-03", "CMP-10")
def test_portfolios_get_a_currency_and_snapshots_keep_their_values(
    db_url: str, engine: Engine, session: Session, factory: Factory
) -> None:
    """0011: portfolios get their owner's base currency, brokers move to portfolio_position,
    existing snapshot rows keep only their value (units and price unknown)."""
    from alembic import command

    from yap.db.migrate import upgrade

    owner = factory.investor()  # CHF
    portfolio = factory.portfolio(owner)
    snapshots.create_snapshot(
        session,
        owner,
        factory.clock,
        portfolio.id,
        [ValueSpec("AAA", units=Decimal(2), price=Decimal(300))],
    )
    session.commit()
    session.close()
    at_head = _triggers(engine)

    command.downgrade(_alembic(db_url), "0010")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO portfolio_broker (portfolio_id, asset_id, broker) "
                "SELECT :portfolio, id, 'Southbank' FROM asset WHERE ticker = 'AAA'"
            ),
            {"portfolio": portfolio.id},
        )
        connection.execute(text("UPDATE investor SET base_currency = 'EUR'"))
    upgrade(db_url)
    assert _triggers(engine) == at_head
    with engine.connect() as connection:
        assert connection.execute(text("SELECT currency FROM portfolio")).scalar() == "EUR"
        assert connection.execute(
            text("SELECT broker, whole_units FROM portfolio_position")
        ).one() == ("Southbank", None)
        assert connection.execute(
            text("SELECT units, price, value, price_kind FROM snapshot_value")
        ).one() == (None, None, "600.00", None)


@pytest.mark.req("USR-09")
@pytest.mark.parametrize(
    ("is_admin", "is_investor", "currency"),
    [(False, False, None), (True, True, None), (False, True, None)],
)
def test_every_account_has_a_role_and_investors_a_currency(
    session: Session, is_admin: bool, is_investor: bool, currency: str | None
) -> None:
    session.add(
        Investor(
            username="x",
            password_hash="x",
            is_admin=is_admin,
            is_investor=is_investor,
            base_currency=currency,
            active=True,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    with pytest.raises(IntegrityError, match="CHECK constraint failed"):
        session.flush()


@pytest.mark.req("NFR-09")
def test_a_failing_migration_leaves_the_database_unchanged(db_url: str, engine: Engine) -> None:
    from yap.db.migrate import upgrade

    _version_0002_with_history(db_url, engine)
    engine.dispose()
    # A broken reference, which the foreign key check after the migrations reports; a
    # plain connection, because the app's connections enforce foreign keys
    raw = sqlite3.connect(db_url.removeprefix("sqlite:///"))
    raw.execute("UPDATE policy SET owner_id = 99")
    raw.commit()
    raw.close()
    with pytest.raises(RuntimeError, match="rolled back"):
        upgrade(db_url)
    assert _version(engine) == "0002"
    with engine.connect() as connection:
        columns = [r[1] for r in connection.execute(text("PRAGMA table_info(thesis_revision)"))]
        triggers = connection.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='thesis_revision'"
            )
        ).all()
    assert "activated_at" not in columns
    assert {t[0] for t in triggers} == {"thesis_revision_no_update", "thesis_revision_no_delete"}


@pytest.mark.req("NFR-09")
def test_sqlite_runs_in_wal_mode_with_foreign_keys(engine: Engine) -> None:
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1


@pytest.mark.req("NFR-04")
def test_decimals_round_trip_exactly(session: Session, factory: Factory) -> None:
    owner = factory.investor()
    portfolio = factory.portfolio(owner, default_contribution=Decimal("1234.567890123456789"))
    session.commit()
    session.expire_all()
    assert portfolio.default_contribution == Decimal("1234.567890123456789")


@pytest.mark.req("NFR-04")
def test_decimal_column_rejects_floats() -> None:
    with pytest.raises(TypeError):
        DecimalText().process_bind_param(0.1, None)  # type: ignore[arg-type]


@pytest.mark.req("NFR-14")
def test_timestamps_are_stored_in_utc() -> None:
    zurich_summer = timezone(timedelta(hours=2))
    stored = UTCDateTime().process_bind_param(
        datetime(2026, 7, 1, 12, 0, tzinfo=zurich_summer),
        None,  # type: ignore[arg-type]
    )
    assert stored == "2026-07-01T10:00:00.000000+00:00"
    assert UTCDateTime().process_result_value(stored, None) == datetime(  # type: ignore[arg-type]
        2026, 7, 1, 10, 0, tzinfo=UTC
    )


@pytest.mark.req("NFR-14")
def test_naive_timestamps_are_rejected(session: Session, factory: Factory) -> None:
    session.add(
        Investor(
            username="x",
            password_hash="x",
            is_investor=True,
            base_currency="CHF",
            active=True,
            created_at=datetime(2026, 1, 1),
        )
    )
    with pytest.raises(Exception, match="timezone-aware"):
        session.flush()


@pytest.mark.req("NFR-05")
@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE snapshot_value SET value = '1'",
        "DELETE FROM snapshot_value",
        "UPDATE snapshot SET taken_at = taken_at",
        "DELETE FROM snapshot",
        "UPDATE policy_version SET thesis_md = 'rewritten'",
        "DELETE FROM portfolio_assignment",
        "UPDATE timeline_event SET summary = 'rewritten'",
        "UPDATE policy_version SET change_note = 'rewritten' WHERE activated_at IS NOT NULL",
        "UPDATE policy_position SET target_pct = '1'",
        "DELETE FROM policy_position",
    ],
)
def test_history_cannot_be_changed(session: Session, factory: Factory, statement: str) -> None:
    owner = factory.investor()
    portfolio = factory.portfolio(owner)
    snapshots.create_snapshot(
        session, owner, factory.clock, portfolio.id, [ValueSpec("AAA", Decimal(1))]
    )
    session.commit()
    with pytest.raises(IntegrityError):
        session.execute(text(statement))
