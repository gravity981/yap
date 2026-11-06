"""price update: exchange rates, schedule, runs, auto prices in snapshots

Exchange rates and the schedule of the price update (PRC-07, PRC-11), its runs (PRC-10),
and in snapshot rows where an auto price came from (CMP-10). The default schedule is once a
day at 22:00 UTC.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-05 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import yap.db.types

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _decimal() -> yap.db.types.DecimalText:
    return yap.db.types.DecimalText(length=64)


def upgrade() -> None:
    time = yap.db.types.UTCDateTime(length=32)
    op.create_table(
        "fx_rate",
        sa.Column("base", sa.String(length=3), nullable=False),
        sa.Column("quote", sa.String(length=3), nullable=False),
        sa.Column("rate", _decimal(), nullable=False),
        sa.Column("rate_date", sa.String(length=10), nullable=False),
        sa.Column("updated_at", time, nullable=False),
        sa.PrimaryKeyConstraint("base", "quote"),
    )
    settings = op.create_table(
        "price_update_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("time_of_day", sa.String(length=5), nullable=False),
        sa.Column("time_zone", sa.String(length=64), nullable=False),
        sa.Column("interval_hours", sa.Integer(), nullable=False),
        sa.Column("next_run_at", time, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(
        settings, [{"id": 1, "time_of_day": "22:00", "time_zone": "UTC", "interval_hours": 24}]
    )
    op.create_table(
        "price_update_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(length=10), nullable=False),
        sa.Column("started_at", time, nullable=False),
        sa.Column("finished_at", time, nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    # Plain ADD COLUMN statements, so the history triggers of snapshot_value stay (NFR-05);
    # SQLite allows a reference in ADD COLUMN when the column may be null
    op.execute("ALTER TABLE snapshot_value ADD COLUMN listing_id INTEGER REFERENCES listing (id)")
    op.add_column("snapshot_value", sa.Column("listing_price", _decimal(), nullable=True))
    op.add_column(
        "snapshot_value", sa.Column("listing_currency", sa.String(length=3), nullable=True)
    )
    op.add_column("snapshot_value", sa.Column("price_date", sa.String(length=10), nullable=True))
    op.add_column("snapshot_value", sa.Column("fx_rate", _decimal(), nullable=True))


def downgrade() -> None:
    for column in ("fx_rate", "price_date", "listing_currency", "listing_price", "listing_id"):
        op.execute(f"ALTER TABLE snapshot_value DROP COLUMN {column}")
    op.drop_table("price_update_run")
    op.drop_table("price_update_settings")
    op.drop_table("fx_rate")
