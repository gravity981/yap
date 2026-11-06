"""units in snapshots, currency per portfolio, time zone per account

Each portfolio gets its owner's base currency (PTF-03). portfolio_broker becomes
portfolio_position with a whole-units setting; the broker is optional there. Snapshot rows
get units, price and price kind (CMP-01, CMP-10); existing rows keep only their value and
show units and price as unknown. Accounts get a time zone (USR-11).

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-03 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import yap.db.types

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _decimal() -> yap.db.types.DecimalText:
    return yap.db.types.DecimalText(length=64)


def upgrade() -> None:
    # Plain ADD COLUMN statements, so the history triggers of snapshot_value stay (NFR-05)
    op.add_column("investor", sa.Column("time_zone", sa.String(length=64), nullable=True))
    op.add_column("snapshot_value", sa.Column("units", _decimal(), nullable=True))
    op.add_column("snapshot_value", sa.Column("price", _decimal(), nullable=True))
    op.add_column("snapshot_value", sa.Column("price_kind", sa.String(length=10), nullable=True))

    op.add_column("portfolio", sa.Column("currency", sa.String(length=3), nullable=True))
    op.execute(
        "UPDATE portfolio SET currency = "
        "(SELECT base_currency FROM investor WHERE investor.id = portfolio.owner_id)"
    )
    with op.batch_alter_table("portfolio") as batch_op:
        batch_op.alter_column("currency", existing_type=sa.String(length=3), nullable=False)

    op.create_table(
        "portfolio_position",
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("broker", sa.String(length=100), nullable=True),
        sa.Column("whole_units", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["asset.id"]),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolio.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("portfolio_id", "asset_id"),
    )
    op.execute(
        "INSERT INTO portfolio_position (portfolio_id, asset_id, broker) "
        "SELECT portfolio_id, asset_id, broker FROM portfolio_broker"
    )
    op.drop_table("portfolio_broker")


def downgrade() -> None:
    # Lossy: whole-units settings, units and prices are dropped
    op.create_table(
        "portfolio_broker",
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("broker", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["asset.id"]),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolio.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("portfolio_id", "asset_id"),
    )
    op.execute(
        "INSERT INTO portfolio_broker (portfolio_id, asset_id, broker) "
        "SELECT portfolio_id, asset_id, broker FROM portfolio_position WHERE broker IS NOT NULL"
    )
    op.drop_table("portfolio_position")
    with op.batch_alter_table("portfolio") as batch_op:
        batch_op.drop_column("currency")
    op.execute("ALTER TABLE snapshot_value DROP COLUMN price_kind")
    op.execute("ALTER TABLE snapshot_value DROP COLUMN price")
    op.execute("ALTER TABLE snapshot_value DROP COLUMN units")
    with op.batch_alter_table("investor") as batch_op:
        batch_op.drop_column("time_zone")
