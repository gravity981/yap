"""Migrations, column types and history protection."""

import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.fixtures import Factory
from yap.db.engine import make_engine
from yap.db.models import Base, Investor
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
    """Rebuilding thesis_revision and investor (0003, 0004) drops and recreates them, which
    foreign key checks would refuse while policy versions reference them."""
    from yap.db.migrate import upgrade

    _version_0002_with_history(db_url, engine)
    upgrade(db_url)
    assert _version(engine) == _head(db_url)
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        # No plan was configured, so there is no AI reviewer to keep (0007)
        assert connection.execute(text("SELECT ai_reviewer_id FROM investor")).scalar() is None
        activated = connection.execute(text("SELECT activated_at FROM thesis_revision")).scalar()
        assert activated == "2026-01-01T00:00:00+00:00"


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
    raw.execute("UPDATE policy_version SET thesis_revision_id = 99")
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
        "UPDATE thesis_revision SET content_md = 'rewritten'",
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
